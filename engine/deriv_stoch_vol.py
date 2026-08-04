"""engine/deriv_stoch_vol.py — Stochastic & alternative volatility models.

Heston (semi-analytic via characteristic-function integration), SABR (Hagan
implied-vol expansion), Dupire local volatility (from a call-price surface),
rough Bergomi (Monte Carlo), Variance Gamma and Normal Inverse Gaussian
(Monte Carlo subordinated processes), and the displaced-diffusion model.

Numba rules (CLAUDE.md §3.1): MC kernels are stateless @njit with cache=True and
consume pre-drawn standard normals. Heston's characteristic-function integral is
evaluated in pure Python with SciPy/NumPy complex arithmetic (njit complex
support is limited), which is correct per the "closed-form in wrapper" guidance.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit, prange
from scipy import integrate

from engine.deriv_options_vanilla import black_scholes_european_option

__all__ = [
    "heston_stochastic_volatility_model",
    "sabr_volatility_model",
    "local_volatility_dupire_model",
    "rough_volatility_rbergomi_model",
    "variance_gamma_model",
    "normal_inverse_gaussian_model",
    "displaced_diffusion_model",
]


# ── Heston (characteristic function, Gatheral form) ────────────────────────────


def _heston_char(
    u: complex,
    spot: float,
    rate: float,
    tau: float,
    v0: float,
    kappa: float,
    theta: float,
    sigma: float,
    rho: float,
) -> complex:
    """Heston characteristic function of log-spot (Gatheral 'little trap' form)."""
    xi = kappa - sigma * rho * 1j * u
    d = np.sqrt(xi**2 + sigma**2 * (1j * u + u**2))
    g = (xi - d) / (xi + d)
    exp_dt = np.exp(-d * tau)
    c_term = rate * 1j * u * tau + (kappa * theta / sigma**2) * (
        (xi - d) * tau - 2.0 * np.log((1.0 - g * exp_dt) / (1.0 - g))
    )
    d_term = ((xi - d) / sigma**2) * ((1.0 - exp_dt) / (1.0 - g * exp_dt))
    return complex(np.exp(c_term + d_term * v0 + 1j * u * np.log(spot)))


def heston_stochastic_volatility_model(
    spot: float,
    strike: float,
    rate: float,
    tau: float,
    v0: float,
    kappa: float,
    theta: float,
    sigma: float,
    rho: float,
    option_type: str = "call",
) -> dict:  # type: ignore[type-arg]
    """Heston stochastic-volatility European option price (semi-analytic).

    Prices via the single-integral representation using the characteristic
    function. As ``sigma`` (vol-of-vol) → 0 with ``v0 = theta`` the price tends
    to Black-Scholes with constant vol ``sqrt(theta)``.

    Args:
        spot: Underlying spot.
        strike: Strike.
        rate: Risk-free rate (continuous).
        tau: Time to maturity (years, > 0).
        v0: Initial variance.
        kappa: Mean-reversion speed of variance.
        theta: Long-run variance.
        sigma: Volatility of variance (vol-of-vol).
        rho: Spot/variance correlation in [-1, 1].
        option_type: ``"call"`` or ``"put"``.

    Returns:
        Dict with ``price`` and the two probabilities ``P1``, ``P2``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or tau <= 0 or v0 < 0 or theta < 0 or sigma <= 0:
        raise ValueError("invalid Heston parameters")
    if not -1.0 <= rho <= 1.0:
        raise ValueError("rho must be in [-1, 1]")

    log_k = math.log(strike)

    def integrand(u: float, add_i: float) -> float:
        cf = _heston_char(u - add_i * 1j, spot, rate, tau, v0, kappa, theta, sigma, rho)
        return float((np.exp(-1j * u * log_k) * cf / (1j * u)).real)

    p1_int, _ = integrate.quad(lambda u: integrand(u, 1.0), 1e-8, 200.0, limit=200)
    p2_int, _ = integrate.quad(lambda u: integrand(u, 0.0), 1e-8, 200.0, limit=200)
    # normalise by the forward factor for P1
    cf0 = _heston_char(-1j, spot, rate, tau, v0, kappa, theta, sigma, rho).real
    p1 = 0.5 + p1_int / (math.pi * cf0)
    p2 = 0.5 + p2_int / math.pi
    call = spot * p1 - strike * math.exp(-rate * tau) * p2
    if option_type == "call":
        price = call
    else:
        price = call - spot + strike * math.exp(-rate * tau)  # put-call parity
    return {
        "price": round(float(max(price, 0.0)), 8),
        "P1": round(float(p1), 8),
        "P2": round(float(p2), 8),
    }


# ── SABR (Hagan lognormal implied vol) ─────────────────────────────────────────


def sabr_volatility_model(
    forward: float,
    strike: float,
    tau: float,
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
) -> dict:  # type: ignore[type-arg]
    """SABR implied (lognormal/Black) volatility via Hagan's expansion.

    Returns the Black implied volatility for the given strike under the SABR
    dynamics. At-the-money it reduces to the well-known ATM SABR vol.

    Args:
        forward: Forward price/rate.
        strike: Strike.
        tau: Time to maturity (years, > 0).
        alpha: Initial volatility level (> 0).
        beta: CEV exponent in [0, 1].
        rho: Correlation in [-1, 1].
        nu: Vol-of-vol (>= 0).

    Returns:
        Dict with ``implied_vol``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if forward <= 0 or strike <= 0 or tau <= 0 or alpha <= 0:
        raise ValueError("forward, strike, tau, alpha must be positive")
    if not 0.0 <= beta <= 1.0:
        raise ValueError("beta must be in [0, 1]")
    if not -1.0 <= rho <= 1.0:
        raise ValueError("rho must be in [-1, 1]")
    if nu < 0:
        raise ValueError("nu must be >= 0")

    one_beta = 1.0 - beta
    if abs(forward - strike) < 1e-12:  # ATM
        fk_beta = forward**one_beta
        term1 = alpha / fk_beta
        term2 = (
            1.0
            + (
                (one_beta**2 / 24.0) * (alpha**2 / fk_beta**2)
                + (rho * beta * nu * alpha) / (4.0 * fk_beta)
                + ((2.0 - 3.0 * rho**2) / 24.0) * nu**2
            )
            * tau
        )
        vol = term1 * term2
    else:
        log_fk = math.log(forward / strike)
        fk_beta = (forward * strike) ** (one_beta / 2.0)
        z = (nu / alpha) * fk_beta * log_fk
        x_z = math.log((math.sqrt(1.0 - 2.0 * rho * z + z**2) + z - rho) / (1.0 - rho))
        denom = fk_beta * (
            1.0 + (one_beta**2 / 24.0) * log_fk**2 + (one_beta**4 / 1920.0) * log_fk**4
        )
        factor = (
            1.0
            + (
                (one_beta**2 / 24.0) * (alpha**2 / fk_beta**2)
                + (rho * beta * nu * alpha) / (4.0 * fk_beta)
                + ((2.0 - 3.0 * rho**2) / 24.0) * nu**2
            )
            * tau
        )
        vol = (alpha / denom) * (z / x_z) * factor
    return {"implied_vol": round(float(vol), 8)}


# ── Dupire local volatility ────────────────────────────────────────────────────


def local_volatility_dupire_model(
    strikes: np.ndarray,
    maturities: np.ndarray,
    call_surface: np.ndarray,
    rate: float,
    spot: float,
) -> dict:  # type: ignore[type-arg]
    """Dupire local volatility surface from a call-price surface.

    Uses finite differences of the Dupire equation
    ``σ_loc² = (∂C/∂T + r K ∂C/∂K) / (½ K² ∂²C/∂K²)`` on the supplied grid.

    Args:
        strikes: 1-D ascending strike grid.
        maturities: 1-D ascending maturity grid (years).
        call_surface: ``(len(maturities), len(strikes))`` call prices.
        rate: Risk-free rate (continuous).
        spot: Underlying spot (validation only).

    Returns:
        Dict with ``local_vol`` (interior-grid surface), ``strikes_inner`` and
        ``maturities_inner``.

    Raises:
        ValueError: If the surface shape is inconsistent or grids too small.
    """
    k = np.asarray(strikes, dtype=np.float64)
    t = np.asarray(maturities, dtype=np.float64)
    c = np.asarray(call_surface, dtype=np.float64)
    if c.shape != (t.size, k.size):
        raise ValueError("call_surface must be (len(maturities), len(strikes))")
    if k.size < 3 or t.size < 2:
        raise ValueError("need >=3 strikes and >=2 maturities")
    if spot <= 0:
        raise ValueError("spot must be positive")

    loc = np.zeros((t.size - 1, k.size - 2), dtype=np.float64)
    for i in range(t.size - 1):
        dt = t[i + 1] - t[i]
        for j in range(1, k.size - 1):
            dk_up = k[j + 1] - k[j]
            dk_dn = k[j] - k[j - 1]
            dc_dt = (c[i + 1, j] - c[i, j]) / dt
            dc_dk = (c[i, j + 1] - c[i, j - 1]) / (dk_up + dk_dn)
            d2c_dk2 = (c[i, j + 1] - 2.0 * c[i, j] + c[i, j - 1]) / (0.5 * (dk_up + dk_dn)) ** 2
            numer = dc_dt + rate * k[j] * dc_dk
            denom = 0.5 * k[j] ** 2 * d2c_dk2
            var = numer / denom if denom > 1e-12 else 0.0
            loc[i, j - 1] = math.sqrt(var) if var > 0 else 0.0
    return {
        "local_vol": loc.tolist(),
        "strikes_inner": k[1:-1].tolist(),
        "maturities_inner": t[:-1].tolist(),
    }


# ── Rough Bergomi (Monte Carlo) ────────────────────────────────────────────────


@njit(cache=True)
def _rbergomi_volterra_driver(hurst: float, z_v: np.ndarray, dt: float) -> np.ndarray:
    """Fractional Volterra driver W~(t_k), k=1..n_steps, for one path's normals.

    Riemann-sum discretisation of int_0^t (t-s)^(H-0.5) dW_s (Bayer, Friz &
    Gatheral 2016, "Pricing under rough volatility", Quantitative Finance
    16(6)): at output time t_now = k*dt, the weight on the increment drawn at
    step j (j <= k) is (t_now - t_j)^(H-0.5) -- the GAP to t_now, recomputed
    at every step.

    A previous version froze each increment's weight at (t_j)^(H-0.5), the
    value AT THE MOMENT it was drawn, and never revisited it as t_now moved
    on -- giving the right marginal variance at any single t_now (both
    formulations Riemann-sum to t_now^(2H)/(2H)) but the wrong autocovariance
    structure between different t_now's, since old increments never lost the
    (large, since t_j^(H-0.5) is largest for small t_j when H<0.5) weight
    they started with. That's silent: a option-price-level test comparing
    against a single Black-Scholes band can't see an autocovariance defect at
    all, since it never depends on more than one time point. See
    tests/test_deriv_stoch_vol.py::test_rbergomi_volterra_driver_matches_hand_calc
    for a hand-computed impulse-response check that only the corrected
    (gap-based) formula passes.

    O(n_steps^2) per path -- n_steps is small (default 50) so this is not a
    bottleneck; _rbergomi_paths below calls this once per path inside its
    parallel loop.
    """
    n_steps = z_v.shape[0]
    out = np.empty(n_steps, dtype=np.float64)
    sqrt_dt = math.sqrt(dt)
    for step in range(n_steps):
        t_now = (step + 1) * dt
        wv = 0.0
        for k in range(step + 1):
            gap = t_now - k * dt
            wv += (gap ** (hurst - 0.5)) * z_v[k] * sqrt_dt
        out[step] = wv
    return out


@njit(cache=True)
def _rbergomi_discrete_variance(hurst: float, dt: float, n_steps: int) -> np.ndarray:
    """Exact martingale-correction term 2H*Var(wv(t_k)) at each t_k, k=1..n_steps.

    For iid standard-normal increments, Var(wv(t_k)) = dt^(2H) * sum_{m=1}^{k}
    m^(2H-1) exactly (each of the k terms in the Riemann sum is an
    independent, known-variance normal); this returns 2H times that, i.e. the
    exact discrete replacement for the continuum correction term t_k^(2H) used
    in the variance process (xi * exp(eta*sqrt(2H)*wv - 0.5*eta^2*<this>)) --
    NOT Var(wv) itself (the continuum identity Var(wv_continuum(t))=t^(2H)/(2H)
    is exactly why the *un*-scaled continuum limit t_k^(2H) was usable as the
    correction directly; the discrete Var(wv) needs the same 2H scaling to be
    a drop-in replacement).

    At the modest n_steps this model runs at (default 50), the naive
    Riemann-sum discretisation of the singular (H-0.5) kernel underestimates
    the continuum variance substantially (empirically ~59% of it at
    n_steps=50, hurst=0.1, converging towards 100% only as n_steps grows into
    the thousands). Using the continuum correction at n_steps=50 over-corrects
    and pulls E[var_t] well below xi (verified: ~0.60*xi with the continuum
    correction vs. ~1.00*xi with this exact discrete one, both at n_steps=50,
    20000-path Monte Carlo check); the exact discrete correction removes that
    bias regardless of how coarse n_steps is. Shared across all paths
    (depends only on hurst/dt/n_steps, not the random draws), so this is
    computed once per _rbergomi_paths call, not once per path.
    """
    out = np.empty(n_steps, dtype=np.float64)
    two_h = 2.0 * hurst
    dt_2h = dt**two_h
    acc = 0.0
    for k in range(1, n_steps + 1):
        acc += float(k) ** (two_h - 1.0)
        out[k - 1] = two_h * dt_2h * acc
    return out


@njit(cache=True, parallel=True)
def _rbergomi_paths(
    spot: float,
    strike: float,
    rate: float,
    tau: float,
    xi: float,
    eta: float,
    hurst: float,
    rho: float,
    z_v: np.ndarray,
    z_s: np.ndarray,
    n_steps: int,
    is_call: bool,
) -> np.ndarray:
    """Discounted rough-Bergomi terminal payoffs from pre-drawn normals.

    Uses a Riemann-sum approximation of the Volterra variance process (see
    _rbergomi_volterra_driver). Returns per-path discounted payoffs (float64
    array).
    """
    n_paths = z_v.shape[0]
    dt = tau / n_steps
    sqrt_dt = math.sqrt(dt)
    disc = math.exp(-rate * tau)
    # Shared across all paths -- see _rbergomi_discrete_variance's docstring
    # for why this exact discrete variance is used instead of the continuum
    # limit t_now^(2H).
    discrete_var = _rbergomi_discrete_variance(hurst, dt, n_steps)
    out = np.empty(n_paths, dtype=np.float64)
    for p in prange(n_paths):
        wv_path = _rbergomi_volterra_driver(hurst, z_v[p], dt)
        log_s = math.log(spot)
        for step in range(n_steps):
            # PREDICTABLE variance: wv_path[step] and discrete_var[step] both
            # represent t_now = (step+1)*dt and therefore already include
            # THIS step's own increment z_v[p, step] -- the same increment
            # used a few lines below inside dw for the price update over
            # THIS same interval. Using wv_path[step]/discrete_var[step]
            # directly here would make var (and hence vol) correlated with
            # the very shock it is meant to be evaluated independently of,
            # breaking the risk-neutral drift and E[S_T] = S0*exp(rT):
            # verified via put-call parity, C - P landed at -15.2 instead of
            # the correct 1.98 (S=K=100, r=0.02, T=1) with the pre-step
            # (step-1) value below fixes it back to ~2.01, and E[S_T] moves
            # from ~84.5 to ~102.05 against a target of 102.02.
            # Correct: use the value as of the START of this interval --
            # i.e. built only from increments strictly before this step --
            # which is v(0) = xi at step 0.
            if step == 0:
                var = xi
            else:
                var = xi * math.exp(
                    eta * math.sqrt(2.0 * hurst) * wv_path[step - 1]
                    - 0.5 * eta * eta * discrete_var[step - 1]
                )
            vol = math.sqrt(var if var > 0.0 else 1e-12)
            dw = rho * z_v[p, step] + math.sqrt(1.0 - rho * rho) * z_s[p, step]
            log_s += (rate - 0.5 * var) * dt + vol * sqrt_dt * dw
        st = math.exp(log_s)
        if is_call:
            payoff = st - strike if st > strike else 0.0
        else:
            payoff = strike - st if strike > st else 0.0
        out[p] = disc * payoff
    return out


def rough_volatility_rbergomi_model(
    spot: float,
    strike: float,
    rate: float,
    tau: float,
    xi: float = 0.04,
    eta: float = 1.5,
    hurst: float = 0.1,
    rho: float = -0.7,
    n_steps: int = 50,
    n_simulations: int = 50_000,
    option_type: str = "call",
    seed: int = 2024,
) -> dict:  # type: ignore[type-arg]
    """Rough Bergomi (rBergomi) European option price via Monte Carlo.

    A rough-volatility model with Hurst exponent ``H < 0.5``. Randoms are
    pre-drawn in pure Python (CLAUDE.md §3.1 RULE 3).

    Three independent numerical-correctness bugs were fixed here (task #18,
    found via the Tier 3 #2 test-reference audit and its follow-up
    verification -- see _rbergomi_volterra_driver, _rbergomi_discrete_variance
    and _rbergomi_paths' docstrings/comments for each in detail):

    1. The fractional driver froze each increment's weight at the moment it
       was drawn instead of recomputing it (as a gap to the current time) at
       every later step -- right marginal variance, wrong autocovariance,
       invisible to any test that only checks a single time point.
    2. The martingale correction used the CONTINUUM-limit variance
       (``t^(2H)``), which the naive discrete Riemann sum undershoots
       substantially at this model's default ``n_steps`` -- pulling
       ``E[var_t]`` well below ``xi``.
    3. The variance applied to a given step's price shock was computed using
       that SAME step's own Brownian draw rather than a value predictable
       from strictly prior information -- correlating "random" volatility
       with the shock it should be independent of and breaking the
       risk-neutral drift (``E[S_T] != S0*exp(rT)``; put-call parity was off
       by more than 15, not a rounding-level miss).

    Verified (not merely believed) via three checks the code lacked before:
    an exact hand-computable impulse-response test on the fractional driver
    (bug 1), an ``eta -> 0`` reduction to flat-vol Black-Scholes (bugs 2 & 3
    together -- degenerate case has no vol-of-vol to expose either), and
    put-call parity at the model's actual default parameters (bug 3
    specifically, since parity holds regardless of how the volatility itself
    is modelled).

    Args:
        spot: Underlying spot.
        strike: Strike.
        rate: Risk-free rate (continuous).
        tau: Time to maturity (years, > 0).
        xi: Forward variance level.
        eta: Vol-of-vol parameter.
        hurst: Hurst exponent in (0, 0.5).
        rho: Spot/vol correlation in [-1, 1].
        n_steps: Time-discretisation steps.
        n_simulations: Number of paths.
        option_type: ``"call"`` or ``"put"``.
        seed: RNG seed.

    Returns:
        Dict with ``price``, ``std_error``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or tau <= 0 or xi <= 0:
        raise ValueError("spot, strike, tau, xi must be positive")
    if not 0.0 < hurst < 0.5:
        raise ValueError("hurst must be in (0, 0.5)")
    if not -1.0 <= rho <= 1.0:
        raise ValueError("rho must be in [-1, 1]")

    rng = np.random.default_rng(seed)
    z_v = rng.standard_normal((int(n_simulations), int(n_steps))).astype(np.float64)
    z_s = rng.standard_normal((int(n_simulations), int(n_steps))).astype(np.float64)
    payoffs = _rbergomi_paths(
        spot,
        strike,
        rate,
        tau,
        xi,
        eta,
        hurst,
        rho,
        z_v,
        z_s,
        int(n_steps),
        option_type == "call",
    )
    price = float(np.mean(payoffs))
    se = float(np.std(payoffs) / math.sqrt(n_simulations))
    return {"price": round(price, 8), "std_error": round(se, 8)}


# ── Variance Gamma (Monte Carlo) ───────────────────────────────────────────────


@njit(cache=True, parallel=True)
def _levy_subordinated_payoff(
    spot: float,
    strike: float,
    rate: float,
    tau: float,
    omega: float,
    theta: float,
    sigma: float,
    subordinator: np.ndarray,
    z: np.ndarray,
    is_call: bool,
) -> np.ndarray:
    """Discounted terminal payoff for a subordinated jump model (VG / NIG).

    ``log S_T = log S_0 + (r + omega) tau + theta G + sigma sqrt(G) Z`` where
    ``G`` is the (pre-drawn) subordinator increment. Returns float64 payoffs.
    """
    n = subordinator.shape[0]
    disc = math.exp(-rate * tau)
    out = np.empty(n, dtype=np.float64)
    for i in prange(n):
        g = subordinator[i]
        log_s = math.log(spot) + (rate + omega) * tau + theta * g + sigma * math.sqrt(g) * z[i]
        st = math.exp(log_s)
        if is_call:
            payoff = st - strike if st > strike else 0.0
        else:
            payoff = strike - st if strike > st else 0.0
        out[i] = disc * payoff
    return out


def variance_gamma_model(
    spot: float,
    strike: float,
    rate: float,
    tau: float,
    sigma: float = 0.2,
    theta: float = -0.1,
    nu: float = 0.2,
    n_simulations: int = 100_000,
    option_type: str = "call",
    seed: int = 7,
) -> dict:  # type: ignore[type-arg]
    """Variance Gamma European option price via Monte Carlo.

    Time-changes Brownian motion by a Gamma subordinator (mean 1, variance
    ``nu``). The martingale drift correction ``omega`` is computed in closed
    form so the discounted spot is a martingale.

    Args:
        spot: Underlying spot.
        strike: Strike.
        rate: Risk-free rate (continuous).
        tau: Time to maturity (years, > 0).
        sigma: Diffusion volatility.
        theta: Drift of the subordinated Brownian motion (skew).
        nu: Variance rate of the Gamma subordinator (> 0).
        n_simulations: Number of paths.
        option_type: ``"call"`` or ``"put"``.
        seed: RNG seed.

    Returns:
        Dict with ``price``, ``std_error``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or tau <= 0 or sigma <= 0 or nu <= 0:
        raise ValueError("spot, strike, tau, sigma, nu must be positive")
    # martingale correction
    omega = math.log(1.0 - theta * nu - 0.5 * sigma * sigma * nu) / nu

    rng = np.random.default_rng(seed)
    g = rng.gamma(shape=tau / nu, scale=nu, size=int(n_simulations)).astype(np.float64)
    z = rng.standard_normal(int(n_simulations)).astype(np.float64)
    payoffs = _levy_subordinated_payoff(
        spot, strike, rate, tau, omega, theta, sigma, g, z, option_type == "call"
    )
    price = float(np.mean(payoffs))
    se = float(np.std(payoffs) / math.sqrt(n_simulations))
    return {"price": round(price, 8), "std_error": round(se, 8)}


def normal_inverse_gaussian_model(
    spot: float,
    strike: float,
    rate: float,
    tau: float,
    alpha: float = 15.0,
    beta: float = -5.0,
    delta: float = 0.5,
    n_simulations: int = 100_000,
    option_type: str = "call",
    seed: int = 11,
) -> dict:  # type: ignore[type-arg]
    """Normal Inverse Gaussian European option price via Monte Carlo.

    NIG is Brownian motion subordinated by an inverse-Gaussian process. The
    drift is corrected so the discounted spot is a martingale.

    Args:
        spot: Underlying spot.
        strike: Strike.
        rate: Risk-free rate (continuous).
        tau: Time to maturity (years, > 0).
        alpha: Tail heaviness (> |beta|).
        beta: Skewness parameter.
        delta: Scale (> 0).
        n_simulations: Number of paths.
        option_type: ``"call"`` or ``"put"``.
        seed: RNG seed.

    Returns:
        Dict with ``price``, ``std_error``.

    Raises:
        ValueError: If inputs are invalid (notably ``alpha > |beta|``).
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or tau <= 0 or delta <= 0:
        raise ValueError("spot, strike, tau, delta must be positive")
    if alpha <= abs(beta):
        raise ValueError("alpha must exceed |beta|")

    gamma = math.sqrt(alpha**2 - beta**2)
    # cumulant correction so E[S_T] = S_0 e^{rT}
    omega = delta * (math.sqrt(alpha**2 - (beta + 1.0) ** 2) - gamma)
    sigma = 1.0  # NIG sigma absorbed into IG variance scaling

    rng = np.random.default_rng(seed)
    # IG subordinator with mean delta*tau/gamma and shape (delta*tau)^2
    mu_ig = delta * tau / gamma
    lam_ig = (delta * tau) ** 2
    ig = _sample_inverse_gaussian(rng, mu_ig, lam_ig, int(n_simulations))
    z = rng.standard_normal(int(n_simulations)).astype(np.float64)
    payoffs = _levy_subordinated_payoff(
        spot, strike, rate, tau, omega, beta, sigma, ig, z, option_type == "call"
    )
    price = float(np.mean(payoffs))
    se = float(np.std(payoffs) / math.sqrt(n_simulations))
    return {"price": round(price, 8), "std_error": round(se, 8)}


def _sample_inverse_gaussian(
    rng: np.random.Generator, mu: float, lam: float, size: int
) -> np.ndarray:
    """Sample an inverse-Gaussian(mu, lambda) via Michael-Schucany-Haas."""
    nu = rng.standard_normal(size)
    y = nu * nu
    x = (
        mu
        + (mu**2 * y) / (2.0 * lam)
        - (mu / (2.0 * lam)) * np.sqrt(4.0 * mu * lam * y + mu**2 * y**2)
    )
    u = rng.random(size)
    out = np.where(u <= mu / (mu + x), x, mu**2 / x)
    return out.astype(np.float64)


def displaced_diffusion_model(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    displacement: float,
    option_type: str = "call",
    div_yield: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Displaced-diffusion (shifted lognormal) European option price.

    Prices ``(S + a)`` as a lognormal with vol scaled by ``S/(S+a)`` — a simple
    way to interpolate between lognormal (a=0) and normal-like dynamics. Reduces
    exactly to Black-Scholes when ``displacement == 0``.

    Args:
        spot: Underlying spot.
        strike: Strike.
        rate: Risk-free rate (continuous).
        sigma: Lognormal volatility of the displaced process.
        tau: Time to maturity (years, > 0).
        displacement: Shift ``a`` applied to spot and strike.
        option_type: ``"call"`` or ``"put"``.
        div_yield: Continuous dividend yield.

    Returns:
        Dict with ``price``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")
    if spot + displacement <= 0 or strike + displacement <= 0:
        raise ValueError("displaced spot and strike must be positive")

    bs = black_scholes_european_option(
        spot + displacement, strike + displacement, rate, sigma, tau, option_type, div_yield
    )
    return {"price": bs["price"]}

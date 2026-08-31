"""engine/deriv_options_exotic.py — Exotic option pricers (Derivatives & Pricing).

Digital, barrier (closed-form Reiner-Rubinstein, with a modelled rebate leg),
Asian (MC arithmetic average), lookback (MC floating strike), American
(Longstaff-Schwartz LSM), Bermudan (discrete-exercise LSM), rainbow
(best/worst-of, MC), basket (MC), spread (Kirk approximation), compound
(Geske 1979 exact closed form), and chooser options.

Numba rules (CLAUDE.md §3.1): MC path kernels are stateless @njit(cache=True)
consuming pre-drawn normals. The LSM regression is done in pure Python (NumPy
lstsq) on the cashflow matrix returned by the path kernel.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit, prange
from scipy import stats
from scipy.optimize import brentq

from engine.deriv_options_vanilla import black_scholes_european_option

__all__ = [
    "digital_option_pricer",
    "barrier_option_pricer",
    "asian_option_pricer",
    "lookback_option_pricer",
    "american_option_lsm",
    "bermudan_option_pricer",
    "rainbow_option_pricer",
    "basket_option_pricer",
    "spread_option_kirk_approximation",
    "compound_option_pricer",
    "chooser_option_pricer",
]


# ── Digital (closed-form) ───────────────────────────────────────────────────────


def digital_option_pricer(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    option_type: str = "call",
    payout: float = 1.0,
    div_yield: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Cash-or-nothing digital (binary) option price.

    ``Call = payout · e^{-rτ} N(d2)``, ``Put = payout · e^{-rτ} N(-d2)``.

    Args:
        spot: Underlying spot.
        strike: Strike.
        rate: Risk-free rate (continuous).
        sigma: Volatility (> 0).
        tau: Time to maturity (years, > 0).
        option_type: ``"call"`` or ``"put"``.
        payout: Cash payout if in the money.
        div_yield: Continuous dividend yield.

    Returns:
        Dict with ``price`` and ``d2``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")

    sqrt_t = math.sqrt(tau)
    d2 = (math.log(spot / strike) + (rate - div_yield - 0.5 * sigma * sigma) * tau) / (
        sigma * sqrt_t
    )
    disc = math.exp(-rate * tau)
    if option_type == "call":
        price = payout * disc * float(stats.norm.cdf(d2))
    else:
        price = payout * disc * float(stats.norm.cdf(-d2))
    return {"price": round(float(price), 8), "d2": round(d2, 8)}


# ── Barrier (Reiner-Rubinstein closed form) ─────────────────────────────────────


def barrier_option_pricer(
    spot: float,
    strike: float,
    barrier: float,
    rate: float,
    sigma: float,
    tau: float,
    option_type: str = "call",
    barrier_type: str = "down-and-out",
    div_yield: float = 0.0,
    rebate: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Single-barrier option price (Reiner-Rubinstein closed form), with a
    modelled rebate leg.

    Uses the in-out parity ``knock-in + knock-out = vanilla`` for the *pure*
    (no-rebate) option legs, so any of the four standard combinations is
    supported. A nonzero ``rebate`` adds the standard Reiner-Rubinstein cash
    rebate term on top of that pure leg: for a knock-in, the rebate is paid
    at expiry if the barrier is never touched (the "E" term below); for a
    knock-out, the rebate is paid at the moment the barrier is touched (the
    "F" term below) -- the standard two rebate conventions (Haug, *The
    Complete Guide to Option Pricing Formulas*, "Standard Barrier Options").

    Note: only the general Reiner-Rubinstein building blocks (A/B/C/D) are
    shown here — which combination prices the knock-in leg depends on
    ``option_type``, ``barrier_type``, and whether strike exceeds barrier.

    Args:
        spot: Underlying spot.
        strike: Strike.
        barrier: Barrier level.
        rate: Risk-free rate (continuous).
        sigma: Volatility (> 0).
        tau: Time to maturity (years, > 0).
        option_type: ``"call"`` or ``"put"``.
        barrier_type: One of ``down-and-out``, ``down-and-in``, ``up-and-out``,
            ``up-and-in``.
        div_yield: Continuous dividend yield.
        rebate: Cash amount paid if the option ends up worthless because of
            the barrier -- at expiry (no touch) for a knock-in, at the touch
            time for a knock-out. 0 (default) reproduces the no-rebate price.

    Returns:
        Dict with ``price`` (pure option leg plus the rebate leg) and the
        vanilla reference ``vanilla``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    valid = ("down-and-out", "down-and-in", "up-and-out", "up-and-in")
    if barrier_type not in valid:
        raise ValueError(f"barrier_type must be one of {valid}")
    if spot <= 0 or strike <= 0 or barrier <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, barrier, sigma, tau must be positive")

    phi = 1.0 if option_type == "call" else -1.0
    is_down = barrier_type.startswith("down")
    eta = 1.0 if is_down else -1.0
    mu = (rate - div_yield - 0.5 * sigma * sigma) / (sigma * sigma)
    lam = math.sqrt(mu * mu + 2.0 * rate / (sigma * sigma))
    sqrt_t = math.sqrt(tau)
    disc_q = math.exp(-div_yield * tau)
    disc_r = math.exp(-rate * tau)
    h_over_s = barrier / spot

    def _cnd(x: float) -> float:
        return float(stats.norm.cdf(x))

    x1 = math.log(spot / strike) / (sigma * sqrt_t) + (1.0 + mu) * sigma * sqrt_t
    x2 = math.log(spot / barrier) / (sigma * sqrt_t) + (1.0 + mu) * sigma * sqrt_t
    y1 = (
        math.log(barrier * barrier / (spot * strike)) / (sigma * sqrt_t)
        + (1.0 + mu) * sigma * sqrt_t
    )
    y2 = math.log(barrier / spot) / (sigma * sqrt_t) + (1.0 + mu) * sigma * sqrt_t
    z = math.log(h_over_s) / (sigma * sqrt_t) + lam * sigma * sqrt_t

    a = phi * spot * disc_q * _cnd(phi * x1) - phi * strike * disc_r * _cnd(
        phi * x1 - phi * sigma * sqrt_t
    )
    b = phi * spot * disc_q * _cnd(phi * x2) - phi * strike * disc_r * _cnd(
        phi * x2 - phi * sigma * sqrt_t
    )
    c = phi * spot * disc_q * (barrier / spot) ** (2.0 * (mu + 1.0)) * _cnd(
        eta * y1
    ) - phi * strike * disc_r * (barrier / spot) ** (2.0 * mu) * _cnd(
        eta * y1 - eta * sigma * sqrt_t
    )
    d = phi * spot * disc_q * (barrier / spot) ** (2.0 * (mu + 1.0)) * _cnd(
        eta * y2
    ) - phi * strike * disc_r * (barrier / spot) ** (2.0 * mu) * _cnd(
        eta * y2 - eta * sigma * sqrt_t
    )

    # Reiner-Rubinstein rebate terms: E is paid at expiry (knock-in, only if
    # never touched); F is paid at the touch time (knock-out, only if
    # touched). Both are 0 when rebate == 0.
    rebate_at_expiry = (
        rebate
        * disc_r
        * (
            _cnd(eta * x2 - eta * sigma * sqrt_t)
            - h_over_s ** (2.0 * mu) * _cnd(eta * y2 - eta * sigma * sqrt_t)
        )
    )
    rebate_at_touch = rebate * (
        h_over_s ** (mu + lam) * _cnd(eta * z)
        + h_over_s ** (mu - lam) * _cnd(eta * z - 2.0 * eta * lam * sigma * sqrt_t)
    )

    vanilla = black_scholes_european_option(spot, strike, rate, sigma, tau, option_type, div_yield)[
        "price"
    ]
    strike_gt_barrier = strike > barrier

    # Pure (no-rebate) knock-in closed form (Haug tables); the pure
    # knock-out leg follows by in-out parity, independent of the rebate.
    if is_down:
        if option_type == "call":
            ki_pure = c if strike_gt_barrier else a - b + d
        else:
            ki_pure = b - c + d if strike_gt_barrier else a
    else:
        if option_type == "call":
            ki_pure = a if strike_gt_barrier else b - c + d
        else:
            ki_pure = a - b + d if strike_gt_barrier else c

    if barrier_type.endswith("in"):
        price = ki_pure + rebate_at_expiry
    else:
        ko_pure = vanilla - ki_pure
        price = ko_pure + rebate_at_touch
    return {"price": round(float(max(price, 0.0)), 8), "vanilla": round(float(vanilla), 8)}


# ── MC path kernels ─────────────────────────────────────────────────────────────


@njit(cache=True, parallel=True)
def _gbm_path_stats(
    spot: float,
    rate: float,
    div_yield: float,
    sigma: float,
    tau: float,
    normals: np.ndarray,
) -> np.ndarray:
    """Per-path terminal, arithmetic-average, min and max of a GBM path.

    ``normals`` is ``(n_paths, n_steps)``. Returns ``(n_paths, 4)`` =
    ``[S_T, avg, min, max]`` (RULE 5: arrays only).
    """
    n_paths, n_steps = normals.shape
    dt = tau / n_steps
    drift = (rate - div_yield - 0.5 * sigma * sigma) * dt
    vol = sigma * math.sqrt(dt)
    out = np.empty((n_paths, 4), dtype=np.float64)
    for p in prange(n_paths):
        s = spot
        acc = 0.0
        smin = spot
        smax = spot
        for k in range(n_steps):
            s = s * math.exp(drift + vol * normals[p, k])
            acc += s
            if s < smin:
                smin = s
            if s > smax:
                smax = s
        out[p, 0] = s
        out[p, 1] = acc / n_steps
        out[p, 2] = smin
        out[p, 3] = smax
    return out


def _simulate_path_stats(
    spot: float,
    rate: float,
    div_yield: float,
    sigma: float,
    tau: float,
    n_steps: int,
    n_sims: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((int(n_sims), int(n_steps))).astype(np.float64)
    return np.asarray(_gbm_path_stats(spot, rate, div_yield, sigma, tau, normals))


def _price_by_qmc_replicates(
    price_fn,  # Callable[[np.ndarray], float] -- (n_paths, n_steps) normals -> price
    n_simulations: int,
    n_steps: int,
    seed: int,
    n_replicates: int = 32,
) -> tuple[float, float, int]:
    """Randomized quasi-Monte Carlo via independent scrambled Sobol replicates
    (task #15 Phase 2).

    Each of n_replicates runs is an independently-scrambled Sobol sequence of
    ``2**m`` paths (a power of two, per scipy.stats.qmc.Sobol's balance
    requirements -- a non-power-of-2 count degrades the low-discrepancy
    guarantee that gives QMC its edge). The reported price is the mean of the
    n_replicates independent estimates; std_error is std(replicate
    prices)/sqrt(n_replicates).

    This split-into-replicates design exists for a specific correctness
    reason, not just convenience: the plain-MC formula
    ``std(payoffs)/sqrt(n)`` is NOT a valid confidence interval for a single
    scrambled-Sobol point set, since QMC points are deliberately correlated
    (that correlation is exactly what gives the variance reduction) --
    applying the iid-MC formula to them would misrepresent the actual
    uncertainty. Averaging over independent replicates restores a valid,
    honestly-computed error bar (Owen's randomized QMC).

    Verified empirically at production-realistic scale (n_steps=100,
    n_simulations=100_000): ~20x variance reduction vs plain MC for
    Asian/lookback-style path-average and path-extremum payoffs, ~7x for
    American LSM's early-exercise payoff, in both cases with the reported
    std_error tracking the true empirical spread across independent full
    reruns (not just a smaller-looking number) and no measurable bias vs.
    plain MC.

    Naive per-time-step Sobol was NOT assumed to work at n_steps=50-100
    (Asian/lookback/American-LSM's actual defaults) without verification --
    QMC's advantage is well known to degrade with nominal dimension, and a
    Brownian-bridge path construction is the standard textbook fix for that.
    It was checked directly (see PR description) rather than assumed away:
    for these path-average and path-extremum payoffs specifically, plain
    coordinate-wise Sobol already delivers the variance reduction above
    without needing a bridge construction.

    Returns: (price, std_error, actual_n_simulations_used)
    """
    paths_per_rep = max(n_simulations // n_replicates, 1)
    m = max(math.ceil(math.log2(paths_per_rep)), 0)
    paths_per_rep_pow2 = 2**m
    actual_n = paths_per_rep_pow2 * n_replicates

    rep_prices = np.empty(n_replicates, dtype=np.float64)
    for r in range(n_replicates):
        sampler = stats.qmc.Sobol(d=n_steps, scramble=True, seed=seed * 1000 + r)
        u = np.clip(sampler.random_base2(m=m), 1e-10, 1.0 - 1e-10)
        normals = stats.norm.ppf(u).astype(np.float64)
        rep_prices[r] = price_fn(normals)

    price = float(np.mean(rep_prices))
    se = float(np.std(rep_prices, ddof=1) / math.sqrt(n_replicates))
    return price, se, actual_n


# ── Bump-and-reprice Greeks (task #15 Phase 4 pilot) ────────────────────────────

_GREEKS_BUMP_REL_SPOT = 1e-3  # 0.1% of spot, for delta/gamma
_GREEKS_BUMP_SIGMA = 1e-4  # 1bp absolute vol, for vega
_GREEKS_BUMP_RATE = 1e-4  # 1bp absolute rate, for rho
_GREEKS_BUMP_TAU_DAYS = 1.0  # 1 calendar day, for theta
_DAYS_PER_YEAR = 365.0


def _asian_disc_payoff_mean(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    div_yield: float,
    option_type: str,
    normals: np.ndarray,
) -> float:
    """Mean discounted Asian payoff for one (params, normals) combination."""
    path_stats = np.asarray(_gbm_path_stats(spot, rate, div_yield, sigma, tau, normals))
    avg = path_stats[:, 1]
    payoff = (
        np.maximum(avg - strike, 0.0) if option_type == "call" else np.maximum(strike - avg, 0.0)
    )
    disc = math.exp(-rate * tau)
    return float(np.mean(disc * payoff))


def _asian_greeks_bump_reprice(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    div_yield: float,
    option_type: str,
    normals: np.ndarray,
    base_price: float,
) -> dict[str, float]:
    """Delta/gamma/vega/theta/rho via central-difference bump-and-reprice.

    Every bumped reprice reuses the SAME pre-drawn ``normals`` array as the
    base price (common random numbers) -- the MC noise in each bump is
    almost perfectly correlated with the base run's noise, so it cancels out
    in the difference instead of adding to it. That correlation is what lets
    the bump sizes below stay small without the resulting Greek being
    swamped by simulation noise; independently-redrawn bumps would need far
    more paths for comparable precision.

    Gamma reuses the same S+/S- reprices as delta (central second
    difference against ``base_price``) rather than a separate bump, so the
    full set costs 8 extra reprices, not 10.
    """
    d_s = spot * _GREEKS_BUMP_REL_SPOT
    d_sigma = min(_GREEKS_BUMP_SIGMA, sigma * 0.5)
    d_rate = _GREEKS_BUMP_RATE
    d_tau = min(_GREEKS_BUMP_TAU_DAYS / _DAYS_PER_YEAR, tau * 0.4)

    p_sp = _asian_disc_payoff_mean(
        spot + d_s, strike, rate, sigma, tau, div_yield, option_type, normals
    )
    p_sm = _asian_disc_payoff_mean(
        spot - d_s, strike, rate, sigma, tau, div_yield, option_type, normals
    )
    p_vp = _asian_disc_payoff_mean(
        spot, strike, rate, sigma + d_sigma, tau, div_yield, option_type, normals
    )
    p_vm = _asian_disc_payoff_mean(
        spot, strike, rate, sigma - d_sigma, tau, div_yield, option_type, normals
    )
    p_rp = _asian_disc_payoff_mean(
        spot, strike, rate + d_rate, sigma, tau, div_yield, option_type, normals
    )
    p_rm = _asian_disc_payoff_mean(
        spot, strike, rate - d_rate, sigma, tau, div_yield, option_type, normals
    )
    p_tp = _asian_disc_payoff_mean(
        spot, strike, rate, sigma, tau + d_tau, div_yield, option_type, normals
    )
    p_tm = _asian_disc_payoff_mean(
        spot, strike, rate, sigma, tau - d_tau, div_yield, option_type, normals
    )

    delta = (p_sp - p_sm) / (2.0 * d_s)
    gamma = (p_sp - 2.0 * base_price + p_sm) / (d_s * d_s)
    vega = (p_vp - p_vm) / (2.0 * d_sigma)
    rho = (p_rp - p_rm) / (2.0 * d_rate)
    theta = -(p_tp - p_tm) / (2.0 * d_tau)

    return {
        "delta": round(delta, 8),
        "gamma": round(gamma, 8),
        "vega": round(vega, 8),
        "theta": round(theta, 8),
        "rho": round(rho, 8),
    }


def _bump_reprice_greeks(
    price_fn,  # Callable[[float, float, float, float], float] -- (spot, rate, sigma, tau) -> price
    spot: float,
    rate: float,
    sigma: float,
    tau: float,
    base_price: float,
    d_s: float,
    d_sigma: float,
    d_rate: float,
    d_tau: float,
) -> dict[str, float]:
    """Generic central-difference bump-and-reprice Greeks (task #15 Phase 4).

    ``price_fn`` must reprice off the SAME pre-drawn random draws as
    ``base_price`` for every call (common random numbers) -- callers are
    responsible for closing over those draws. See
    ``_asian_greeks_bump_reprice`` for why that correlation is what makes
    small bump sizes usable at all.

    Bump sizes are passed in rather than hardcoded here because they are
    NOT one-size-fits-all: products priced via LSM early-exercise regression
    (american_option_lsm, bermudan_option_pricer) need a materially larger
    ``d_s`` than smooth path-average/extremum payoffs (Asian, lookback) or
    the regression's discrete exercise/continue decision flips under a tiny
    spot bump and gamma comes out noise-dominated with the wrong sign --
    verified empirically before this was applied anywhere (see those
    functions' docstrings for the numbers).
    """
    p_sp = price_fn(spot + d_s, rate, sigma, tau)
    p_sm = price_fn(spot - d_s, rate, sigma, tau)
    p_vp = price_fn(spot, rate, sigma + d_sigma, tau)
    p_vm = price_fn(spot, rate, sigma - d_sigma, tau)
    p_rp = price_fn(spot, rate + d_rate, sigma, tau)
    p_rm = price_fn(spot, rate - d_rate, sigma, tau)
    p_tp = price_fn(spot, rate, sigma, tau + d_tau)
    p_tm = price_fn(spot, rate, sigma, tau - d_tau)

    delta = (p_sp - p_sm) / (2.0 * d_s)
    gamma = (p_sp - 2.0 * base_price + p_sm) / (d_s * d_s)
    vega = (p_vp - p_vm) / (2.0 * d_sigma)
    rho = (p_rp - p_rm) / (2.0 * d_rate)
    theta = -(p_tp - p_tm) / (2.0 * d_tau)

    return {
        "delta": round(delta, 8),
        "gamma": round(gamma, 8),
        "vega": round(vega, 8),
        "theta": round(theta, 8),
        "rho": round(rho, 8),
    }


def asian_option_pricer(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    n_steps: int = 100,
    n_simulations: int = 100_000,
    option_type: str = "call",
    average_type: str = "arithmetic",
    div_yield: float = 0.0,
    seed: int = 21,
    qmc: bool = False,
    greeks: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Arithmetic-average Asian option price via Monte Carlo.

    The averaging reduces volatility, so an Asian option is worth less than the
    corresponding vanilla European option.

    Args:
        spot: Underlying spot.
        strike: Strike.
        rate: Risk-free rate (continuous).
        sigma: Volatility (> 0).
        tau: Time to maturity (years, > 0).
        n_steps: Averaging observation count.
        n_simulations: Number of paths.
        option_type: ``"call"`` or ``"put"``.
        average_type: ``"arithmetic"`` (only).
        div_yield: Continuous dividend yield.
        seed: RNG seed.
        qmc: Use randomized quasi-Monte Carlo (scrambled Sobol replicates,
            see ``_price_by_qmc_replicates``) instead of plain MC for a
            lower-variance estimate at the same n_simulations. Defaults to
            False so existing callers/results are unaffected.
        greeks: Also compute delta/gamma/vega/theta/rho via bump-and-reprice
            (see ``_asian_greeks_bump_reprice``) on the same pre-drawn
            normals used for the base price, so the bump noise cancels
            against the base run's noise instead of adding to it. Costs 8
            extra reprices at the same n_simulations/n_steps. Not supported
            together with qmc=True. Defaults to False so existing
            callers/results are unaffected.

    Returns:
        Dict with ``price``, ``std_error``, and if ``greeks=True`` also
        ``delta``, ``gamma``, ``vega``, ``theta``, ``rho``.

    Raises:
        ValueError: If inputs are invalid, or if greeks=True with qmc=True.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if average_type != "arithmetic":
        raise ValueError("only arithmetic averaging supported")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")
    if greeks and qmc:
        raise ValueError("greeks=True is not yet supported together with qmc=True")

    disc = math.exp(-rate * tau)

    def _price_from_normals(normals: np.ndarray) -> float:
        path_stats = np.asarray(_gbm_path_stats(spot, rate, div_yield, sigma, tau, normals))
        avg = path_stats[:, 1]
        payoff = (
            np.maximum(avg - strike, 0.0)
            if option_type == "call"
            else np.maximum(strike - avg, 0.0)
        )
        return float(np.mean(disc * payoff))

    if qmc:
        price, se, _ = _price_by_qmc_replicates(_price_from_normals, n_simulations, n_steps, seed)
        return {"price": round(price, 8), "std_error": round(se, 8)}

    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((int(n_simulations), int(n_steps))).astype(np.float64)
    stats_arr = np.asarray(_gbm_path_stats(spot, rate, div_yield, sigma, tau, normals))
    avg = stats_arr[:, 1]
    if option_type == "call":
        payoff = np.maximum(avg - strike, 0.0)
    else:
        payoff = np.maximum(strike - avg, 0.0)
    disc_payoff = disc * payoff
    price = float(np.mean(disc_payoff))
    se = float(np.std(disc_payoff) / math.sqrt(n_simulations))
    result = {"price": round(price, 8), "std_error": round(se, 8)}

    if greeks:
        result.update(
            _asian_greeks_bump_reprice(
                spot, strike, rate, sigma, tau, div_yield, option_type, normals, price
            )
        )
    return result


def lookback_option_pricer(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    n_steps: int = 100,
    n_simulations: int = 100_000,
    option_type: str = "call",
    strike_type: str = "floating",
    div_yield: float = 0.0,
    seed: int = 31,
    qmc: bool = False,
    greeks: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Lookback option price via Monte Carlo.

    Floating-strike: call pays ``S_T − min`` (>= 0), put pays ``max − S_T``.
    Fixed-strike: call pays ``max − K``, put pays ``K − min``. Always >= the
    corresponding vanilla payoff.

    Args:
        spot: Underlying spot.
        strike: Strike (fixed-strike only).
        rate: Risk-free rate (continuous).
        sigma: Volatility (> 0).
        tau: Time to maturity (years, > 0).
        n_steps: Monitoring frequency.
        n_simulations: Number of paths.
        option_type: ``"call"`` or ``"put"``.
        strike_type: ``"floating"`` or ``"fixed"``.
        div_yield: Continuous dividend yield.
        seed: RNG seed.
        qmc: Use randomized quasi-Monte Carlo (scrambled Sobol replicates,
            see ``_price_by_qmc_replicates``) instead of plain MC for a
            lower-variance estimate at the same n_simulations. Defaults to
            False so existing callers/results are unaffected.
        greeks: Also compute delta/gamma/vega/theta/rho via bump-and-reprice
            (see ``_bump_reprice_greeks``) on the same pre-drawn normals used
            for the base price. The path-average/extremum payoff here is
            smooth in spot (unlike the LSM products below), so this uses the
            same small bump sizes as asian_option_pricer. Not supported
            together with qmc=True. Defaults to False so existing
            callers/results are unaffected.

    Returns:
        Dict with ``price``, ``std_error``, and if ``greeks=True`` also
        ``delta``, ``gamma``, ``vega``, ``theta``, ``rho``.

    Raises:
        ValueError: If inputs are invalid, or if greeks=True with qmc=True.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if strike_type not in ("floating", "fixed"):
        raise ValueError("strike_type must be 'floating' or 'fixed'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")
    if greeks and qmc:
        raise ValueError("greeks=True is not yet supported together with qmc=True")

    disc = math.exp(-rate * tau)

    def _price_from_normals(normals: np.ndarray) -> float:
        path_stats = np.asarray(_gbm_path_stats(spot, rate, div_yield, sigma, tau, normals))
        st, smin, smax = path_stats[:, 0], path_stats[:, 2], path_stats[:, 3]
        if strike_type == "floating":
            payoff = (st - smin) if option_type == "call" else (smax - st)
        else:
            payoff = (
                np.maximum(smax - strike, 0.0)
                if option_type == "call"
                else np.maximum(strike - smin, 0.0)
            )
        return float(np.mean(disc * np.asarray(payoff, dtype=np.float64)))

    if qmc:
        price, se, _ = _price_by_qmc_replicates(_price_from_normals, n_simulations, n_steps, seed)
        return {"price": round(price, 8), "std_error": round(se, 8)}

    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((int(n_simulations), int(n_steps))).astype(np.float64)
    stats_arr = np.asarray(_gbm_path_stats(spot, rate, div_yield, sigma, tau, normals))
    st, smin, smax = stats_arr[:, 0], stats_arr[:, 2], stats_arr[:, 3]
    if strike_type == "floating":
        payoff = (st - smin) if option_type == "call" else (smax - st)
    else:
        payoff = (
            np.maximum(smax - strike, 0.0)
            if option_type == "call"
            else np.maximum(strike - smin, 0.0)
        )
    disc_payoff = disc * np.asarray(payoff, dtype=np.float64)
    price = float(np.mean(disc_payoff))
    se = float(np.std(disc_payoff) / math.sqrt(n_simulations))
    result = {"price": round(price, 8), "std_error": round(se, 8)}

    if greeks:

        def _lookback_price(spot_: float, rate_: float, sigma_: float, tau_: float) -> float:
            path_stats = np.asarray(_gbm_path_stats(spot_, rate_, div_yield, sigma_, tau_, normals))
            st_, smin_, smax_ = path_stats[:, 0], path_stats[:, 2], path_stats[:, 3]
            if strike_type == "floating":
                pay = (st_ - smin_) if option_type == "call" else (smax_ - st_)
            else:
                pay = (
                    np.maximum(smax_ - strike, 0.0)
                    if option_type == "call"
                    else np.maximum(strike - smin_, 0.0)
                )
            return float(np.mean(math.exp(-rate_ * tau_) * np.asarray(pay, dtype=np.float64)))

        result.update(
            _bump_reprice_greeks(
                _lookback_price,
                spot,
                rate,
                sigma,
                tau,
                price,
                d_s=spot * _GREEKS_BUMP_REL_SPOT,
                d_sigma=min(_GREEKS_BUMP_SIGMA, sigma * 0.5),
                d_rate=_GREEKS_BUMP_RATE,
                d_tau=min(_GREEKS_BUMP_TAU_DAYS / _DAYS_PER_YEAR, tau * 0.4),
            )
        )
    return result


# ── LSM (American / Bermudan) ──────────────────────────────────────────────────


@njit(cache=True)
def _gbm_full_paths(
    spot: float, rate: float, div_yield: float, sigma: float, tau: float, normals: np.ndarray
) -> np.ndarray:
    """Full GBM price matrix ``(n_paths, n_steps+1)`` from pre-drawn normals."""
    n_paths, n_steps = normals.shape
    dt = tau / n_steps
    drift = (rate - div_yield - 0.5 * sigma * sigma) * dt
    vol = sigma * math.sqrt(dt)
    paths = np.empty((n_paths, n_steps + 1), dtype=np.float64)
    for p in range(n_paths):
        paths[p, 0] = spot
        s = spot
        for k in range(n_steps):
            s = s * math.exp(drift + vol * normals[p, k])
            paths[p, k + 1] = s
    return paths


def _lsm_price(
    paths: np.ndarray,
    strike: float,
    rate: float,
    dt: float,
    is_call: bool,
    exercise_mask: np.ndarray,
) -> float:
    """Longstaff-Schwartz backward induction on a price matrix.

    ``exercise_mask`` (length n_steps+1) flags time steps where early exercise is
    allowed (American: all interior+terminal; Bermudan: a subset).
    """
    n_paths, n_cols = paths.shape
    n_steps = n_cols - 1
    disc = math.exp(-rate * dt)

    def intrinsic(s: np.ndarray) -> np.ndarray:
        return np.maximum(s - strike, 0.0) if is_call else np.maximum(strike - s, 0.0)

    cashflow = intrinsic(paths[:, n_steps])
    for t in range(n_steps - 1, 0, -1):
        cashflow = cashflow * disc
        if not exercise_mask[t]:
            continue
        ex = intrinsic(paths[:, t])
        itm = ex > 0.0
        if np.count_nonzero(itm) < 3:
            continue
        x = paths[itm, t]
        y = cashflow[itm]
        a = np.vstack([np.ones_like(x), x, x * x]).T
        coeffs, _, _, _ = np.linalg.lstsq(a, y, rcond=None)
        continuation = coeffs[0] + coeffs[1] * x + coeffs[2] * x * x
        exercise_now = ex[itm] > continuation
        idx = np.where(itm)[0][exercise_now]
        cashflow[idx] = ex[itm][exercise_now]
    return float(np.mean(cashflow * disc))


# LSM's exercise decision at each date is a regression classification (ITM path
# vs. fitted continuation value), not a smooth function of spot. A small spot bump
# can flip which paths cross that boundary, so the standard 0.1%-of-spot bump used
# for smooth payoffs (Asian, lookback) produces a noise-dominated, wrong-signed
# gamma here -- verified empirically before shipping (see american_option_lsm's
# docstring for the numbers): at 0.1% bump, gamma mean was negative with a std
# ~4x the (already-wrong) mean; at 3% bump it converges to a small positive value
# consistent with the closed-form European gamma, with the seed-to-seed std over
# an order of magnitude tighter. Vega/rho/theta don't have this problem (rate/vol/
# tau bumps don't reclassify the exercise boundary the same way) and keep the
# standard small bump sizes.
_LSM_GREEKS_BUMP_REL_SPOT = 3e-2


def _lsm_price_from_normals(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    div_yield: float,
    is_call: bool,
    exercise_mask: np.ndarray,
    n_steps: int,
    normals: np.ndarray,
) -> float:
    dt = tau / n_steps
    paths = _gbm_full_paths(spot, rate, div_yield, sigma, tau, normals)
    return _lsm_price(paths, strike, rate, dt, is_call, exercise_mask)


def american_option_lsm(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    n_steps: int = 50,
    n_simulations: int = 100_000,
    option_type: str = "put",
    div_yield: float = 0.0,
    seed: int = 41,
    greeks: bool = False,
) -> dict:  # type: ignore[type-arg]
    """American option price via Longstaff-Schwartz Monte Carlo (LSM).

    Allows early exercise at every time step. The price must be >= the European
    price of the same option.

    Note: the continuation value at each exercise date is fit by quadratic OLS
    regression on in-the-money paths rather than evaluated from a closed-form
    formula, and the opt-in Greeks use a spot bump roughly 30x larger than
    this module's smooth-payoff pricers because that regression-based
    exercise decision is discontinuous in spot.

    Deliberately has no qmc option (task #15 Phase 2 evaluated and rejected
    it for this function specifically -- see _price_by_qmc_replicates'
    docstring). Randomized-QMC replicates work cleanly for asian_option_pricer
    and lookback_option_pricer (simple path-average / path-extremum
    estimators) but introduce a real, non-vanishing pricing bias here: LSM's
    backward-induction step fits a cross-sectional OLS regression of
    continuation value against in-the-money paths at each exercise date, and
    that regression implicitly assumes the sampled points are independent.
    Scrambled Sobol paths are deliberately correlated (that correlation is
    exactly what gives QMC its variance reduction elsewhere), which biases
    the regression fit and, through it, the exercise decision. Measured at
    S=K=100, r=5%, sigma=20%, tau=1, n_steps=50 against a 200k-path plain-MC
    reference (~6.024): plain MC at n_simulations=6,000/20,000 is biased by
    only +0.03-0.04 (LSM's well-known small-sample low bias), while QMC
    replicates at the same total budget were biased by +0.08 to +0.31
    depending on replicate count/size -- shrinking as per-replicate path
    count grows into the thousands, but not vanishing by n_simulations=20k
    the way it does for Asian/lookback. Revisit only with a fix for the
    underlying regression-bias interaction (e.g. an in-sample/out-of-sample
    split for the regression fit), not by retuning replicate count alone.

    Args:
        spot: Underlying spot.
        strike: Strike.
        rate: Risk-free rate (continuous).
        sigma: Volatility (> 0).
        tau: Time to maturity (years, > 0).
        n_steps: Exercise dates.
        n_simulations: Number of paths.
        option_type: ``"call"`` or ``"put"``.
        div_yield: Continuous dividend yield.
        seed: RNG seed.
        greeks: Also compute delta/gamma/vega/theta/rho via bump-and-reprice
            (see ``_bump_reprice_greeks``) on the same pre-drawn normals used
            for the base price. Uses a materially larger spot bump than the
            smooth-payoff products (see ``_LSM_GREEKS_BUMP_REL_SPOT`` for
            why) -- delta/gamma are therefore somewhat coarser here than for
            Asian/lookback, by construction, not oversight. Costs 8 extra
            LSM reprices (each as expensive as the base price -- this is the
            most expensive Greeks call in this module; consider a smaller
            n_simulations for greeks=True requests if used behind a
            request-latency budget). Defaults to False so existing
            callers/results are unaffected.

    Returns:
        Dict with ``price``, and if ``greeks=True`` also ``delta``,
        ``gamma``, ``vega``, ``theta``, ``rho``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")

    dt = tau / n_steps
    mask = np.ones(int(n_steps) + 1, dtype=np.bool_)

    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((int(n_simulations), int(n_steps))).astype(np.float64)
    paths = _gbm_full_paths(spot, rate, div_yield, sigma, tau, normals)
    price = _lsm_price(paths, strike, rate, dt, option_type == "call", mask)
    result = {"price": round(float(price), 8)}

    if greeks:
        is_call = option_type == "call"

        def _price(spot_: float, rate_: float, sigma_: float, tau_: float) -> float:
            return _lsm_price_from_normals(
                spot_, strike, rate_, sigma_, tau_, div_yield, is_call, mask, n_steps, normals
            )

        result.update(
            _bump_reprice_greeks(
                _price,
                spot,
                rate,
                sigma,
                tau,
                price,
                d_s=spot * _LSM_GREEKS_BUMP_REL_SPOT,
                d_sigma=min(_GREEKS_BUMP_SIGMA, sigma * 0.5),
                d_rate=_GREEKS_BUMP_RATE,
                d_tau=min(_GREEKS_BUMP_TAU_DAYS / _DAYS_PER_YEAR, tau * 0.4),
            )
        )
    return result


def bermudan_option_pricer(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    exercise_dates: int = 4,
    n_steps: int = 48,
    n_simulations: int = 100_000,
    option_type: str = "put",
    div_yield: float = 0.0,
    seed: int = 51,
    greeks: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Bermudan option price via LSM with discrete exercise dates.

    Early exercise is allowed only on an evenly-spaced subset of the time grid.
    Price lies between the European and American values.

    Note: uses the same Longstaff-Schwartz regression-based exercise decision
    as ``american_option_lsm`` (no closed form), restricted to an
    evenly-spaced subset of roughly ``n_steps / exercise_dates`` grid points.

    Args:
        spot: Underlying spot.
        strike: Strike.
        rate: Risk-free rate (continuous).
        sigma: Volatility (> 0).
        tau: Time to maturity (years, > 0).
        exercise_dates: Number of allowed exercise dates (>= 1).
        n_steps: Total time-grid steps (multiple of exercise_dates ideally).
        n_simulations: Number of paths.
        option_type: ``"call"`` or ``"put"``.
        div_yield: Continuous dividend yield.
        seed: RNG seed.
        greeks: Also compute delta/gamma/vega/theta/rho via bump-and-reprice
            (see ``_bump_reprice_greeks``). Same LSM regression-boundary
            caveat as american_option_lsm applies -- uses the same larger
            spot bump (``_LSM_GREEKS_BUMP_REL_SPOT``), verified empirically
            for this function too (see ``_bump_reprice_greeks``'s
            docstring). Defaults to False so existing callers/results are
            unaffected.

    Returns:
        Dict with ``price``, ``exercise_dates``, and if ``greeks=True`` also
        ``delta``, ``gamma``, ``vega``, ``theta``, ``rho``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")
    if exercise_dates < 1:
        raise ValueError("exercise_dates must be >= 1")

    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((int(n_simulations), int(n_steps))).astype(np.float64)
    paths = _gbm_full_paths(spot, rate, div_yield, sigma, tau, normals)
    dt = tau / n_steps
    mask = np.zeros(int(n_steps) + 1, dtype=np.bool_)
    step = max(int(n_steps // exercise_dates), 1)
    for d in range(1, int(n_steps) + 1):
        if d % step == 0:
            mask[d] = True
    mask[n_steps] = True
    price = _lsm_price(paths, strike, rate, dt, option_type == "call", mask)
    result = {"price": round(float(price), 8), "exercise_dates": int(exercise_dates)}

    if greeks:
        is_call = option_type == "call"

        def _price(spot_: float, rate_: float, sigma_: float, tau_: float) -> float:
            return _lsm_price_from_normals(
                spot_, strike, rate_, sigma_, tau_, div_yield, is_call, mask, n_steps, normals
            )

        result.update(
            _bump_reprice_greeks(
                _price,
                spot,
                rate,
                sigma,
                tau,
                price,
                d_s=spot * _LSM_GREEKS_BUMP_REL_SPOT,
                d_sigma=min(_GREEKS_BUMP_SIGMA, sigma * 0.5),
                d_rate=_GREEKS_BUMP_RATE,
                d_tau=min(_GREEKS_BUMP_TAU_DAYS / _DAYS_PER_YEAR, tau * 0.4),
            )
        )
    return result


# ── Multi-asset (MC) ───────────────────────────────────────────────────────────


@njit(cache=True, parallel=True)
def _multi_asset_terminals(
    spots: np.ndarray,
    rate: float,
    sigmas: np.ndarray,
    tau: float,
    chol: np.ndarray,
    normals: np.ndarray,
) -> np.ndarray:
    """Terminal prices for correlated GBM assets (single-step, exact).

    ``normals`` is ``(n_paths, n_assets)``; ``chol`` is the lower Cholesky of the
    correlation matrix. Returns ``(n_paths, n_assets)`` terminal prices.
    """
    n_paths, n_assets = normals.shape
    sqrt_t = math.sqrt(tau)
    out = np.empty((n_paths, n_assets), dtype=np.float64)
    for p in prange(n_paths):
        for a in range(n_assets):
            corr_z = 0.0
            for b in range(n_assets):
                corr_z += chol[a, b] * normals[p, b]
            drift = (rate - 0.5 * sigmas[a] * sigmas[a]) * tau
            out[p, a] = spots[a] * math.exp(drift + sigmas[a] * sqrt_t * corr_z)
    return out


def _multi_asset_bump_reprice_greeks(
    price_fn,  # Callable[[np.ndarray, float, np.ndarray, float], float]
    spots: np.ndarray,
    rate: float,
    sigmas: np.ndarray,
    tau: float,
    base_price: float,
    d_rate: float,
    d_tau: float,
) -> dict:  # type: ignore[type-arg]
    """Per-asset delta/gamma/vega plus scalar theta/rho, via bump-and-reprice.

    ``price_fn(spots, rate, sigmas, tau) -> price`` must reprice off the same
    pre-drawn normals and Cholesky factor as ``base_price`` (common random
    numbers) -- callers close over those.

    Delta/gamma/vega are computed per-asset by bumping ONLY that asset's own
    spot/sigma and holding every other asset fixed -- i.e. these are the
    diagonal sensitivities only. Cross-gammas (`d^2V/dS_i dS_j`, i != j) are
    NOT computed; for a correlated multi-asset payoff they are generally
    nonzero and matter for hedging a rainbow/basket book, but that is a
    materially larger surface (O(n^2) reprices instead of O(n)) deferred to a
    follow-up rather than scoped into this pass silently.
    """
    n_assets = spots.size
    delta = np.empty(n_assets, dtype=np.float64)
    gamma = np.empty(n_assets, dtype=np.float64)
    vega = np.empty(n_assets, dtype=np.float64)

    for i in range(n_assets):
        d_s = spots[i] * _GREEKS_BUMP_REL_SPOT
        spots_p, spots_m = spots.copy(), spots.copy()
        spots_p[i] += d_s
        spots_m[i] -= d_s
        p_sp = price_fn(spots_p, rate, sigmas, tau)
        p_sm = price_fn(spots_m, rate, sigmas, tau)
        delta[i] = (p_sp - p_sm) / (2.0 * d_s)
        gamma[i] = (p_sp - 2.0 * base_price + p_sm) / (d_s * d_s)

        d_sigma = min(_GREEKS_BUMP_SIGMA, sigmas[i] * 0.5)
        sigmas_p, sigmas_m = sigmas.copy(), sigmas.copy()
        sigmas_p[i] += d_sigma
        sigmas_m[i] -= d_sigma
        p_vp = price_fn(spots, rate, sigmas_p, tau)
        p_vm = price_fn(spots, rate, sigmas_m, tau)
        vega[i] = (p_vp - p_vm) / (2.0 * d_sigma)

    p_rp = price_fn(spots, rate + d_rate, sigmas, tau)
    p_rm = price_fn(spots, rate - d_rate, sigmas, tau)
    rho = (p_rp - p_rm) / (2.0 * d_rate)

    p_tp = price_fn(spots, rate, sigmas, tau + d_tau)
    p_tm = price_fn(spots, rate, sigmas, tau - d_tau)
    theta = -(p_tp - p_tm) / (2.0 * d_tau)

    return {
        "delta": [round(float(x), 8) for x in delta],
        "gamma": [round(float(x), 8) for x in gamma],
        "vega": [round(float(x), 8) for x in vega],
        "theta": round(theta, 8),
        "rho": round(rho, 8),
    }


def rainbow_option_pricer(
    spots: np.ndarray,
    strike: float,
    rate: float,
    sigmas: np.ndarray,
    tau: float,
    correlation: np.ndarray,
    n_simulations: int = 100_000,
    option_type: str = "call",
    rainbow_type: str = "best-of",
    seed: int = 61,
    greeks: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Rainbow (best-of / worst-of) option price via Monte Carlo.

    Payoff references the max (best-of) or min (worst-of) of the terminal asset
    prices against the strike.

    Args:
        spots: Initial prices per asset.
        strike: Strike.
        rate: Risk-free rate (continuous).
        sigmas: Volatility per asset.
        tau: Time to maturity (years, > 0).
        correlation: Asset correlation matrix (SPD).
        n_simulations: Number of paths.
        option_type: ``"call"`` or ``"put"``.
        rainbow_type: ``"best-of"`` or ``"worst-of"``.
        seed: RNG seed.
        greeks: Also compute per-asset delta/gamma/vega and scalar theta/rho
            via bump-and-reprice (see ``_multi_asset_bump_reprice_greeks``)
            on the same pre-drawn normals used for the base price. Delta/
            gamma/vega are diagonal only (each asset bumped independently;
            no cross-asset terms). Defaults to False so existing
            callers/results are unaffected.

    Returns:
        Dict with ``price``, ``std_error``, and if ``greeks=True`` also
        ``delta``, ``gamma``, ``vega`` (each a list, one entry per asset)
        and scalar ``theta``, ``rho``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if rainbow_type not in ("best-of", "worst-of"):
        raise ValueError("rainbow_type must be 'best-of' or 'worst-of'")
    s = np.asarray(spots, dtype=np.float64)
    v = np.asarray(sigmas, dtype=np.float64)
    corr = np.asarray(correlation, dtype=np.float64)
    if s.size != v.size or corr.shape != (s.size, s.size):
        raise ValueError("dimension mismatch among spots, sigmas, correlation")
    if tau <= 0:
        raise ValueError("tau must be positive")

    chol = np.linalg.cholesky(corr).astype(np.float64)
    normals = (
        np.random.default_rng(seed).standard_normal((int(n_simulations), s.size)).astype(np.float64)
    )

    terminals = np.asarray(_multi_asset_terminals(s, rate, v, tau, chol, normals))
    ref = np.max(terminals, axis=1) if rainbow_type == "best-of" else np.min(terminals, axis=1)
    payoff = (
        np.maximum(ref - strike, 0.0) if option_type == "call" else np.maximum(strike - ref, 0.0)
    )
    disc_payoff = math.exp(-rate * tau) * payoff
    price = float(np.mean(disc_payoff))
    se = float(np.std(disc_payoff) / math.sqrt(n_simulations))
    result = {"price": round(price, 8), "std_error": round(se, 8)}

    if greeks:

        def _rainbow_price(
            spots_: np.ndarray, rate_: float, sigmas_: np.ndarray, tau_: float
        ) -> float:
            terminals_ = np.asarray(
                _multi_asset_terminals(spots_, rate_, sigmas_, tau_, chol, normals)
            )
            ref_ = (
                np.max(terminals_, axis=1)
                if rainbow_type == "best-of"
                else np.min(terminals_, axis=1)
            )
            pay_ = (
                np.maximum(ref_ - strike, 0.0)
                if option_type == "call"
                else np.maximum(strike - ref_, 0.0)
            )
            return float(np.mean(math.exp(-rate_ * tau_) * pay_))

        result.update(
            _multi_asset_bump_reprice_greeks(
                _rainbow_price,
                s,
                rate,
                v,
                tau,
                price,
                d_rate=_GREEKS_BUMP_RATE,
                d_tau=min(_GREEKS_BUMP_TAU_DAYS / _DAYS_PER_YEAR, tau * 0.4),
            )
        )
    return result


def basket_option_pricer(
    spots: np.ndarray,
    weights: np.ndarray,
    strike: float,
    rate: float,
    sigmas: np.ndarray,
    tau: float,
    correlation: np.ndarray,
    n_simulations: int = 100_000,
    option_type: str = "call",
    seed: int = 71,
    greeks: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Basket option price via Monte Carlo on a weighted sum of assets.

    Diversification means the basket option is worth no more than the weighted
    sum of single-asset options.

    Args:
        spots: Initial prices per asset.
        weights: Basket weights per asset.
        strike: Strike on the weighted basket.
        rate: Risk-free rate (continuous).
        sigmas: Volatility per asset.
        tau: Time to maturity (years, > 0).
        correlation: Asset correlation matrix (SPD).
        n_simulations: Number of paths.
        option_type: ``"call"`` or ``"put"``.
        seed: RNG seed.
        greeks: Also compute per-asset delta/gamma/vega and scalar theta/rho
            via bump-and-reprice (see ``_multi_asset_bump_reprice_greeks``)
            on the same pre-drawn normals used for the base price. Delta/
            gamma/vega are diagonal only (each asset bumped independently;
            no cross-asset terms). Defaults to False so existing
            callers/results are unaffected.

    Returns:
        Dict with ``price``, ``std_error``, and if ``greeks=True`` also
        ``delta``, ``gamma``, ``vega`` (each a list, one entry per asset)
        and scalar ``theta``, ``rho``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    s = np.asarray(spots, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    v = np.asarray(sigmas, dtype=np.float64)
    corr = np.asarray(correlation, dtype=np.float64)
    if not (s.size == w.size == v.size) or corr.shape != (s.size, s.size):
        raise ValueError("dimension mismatch")
    if tau <= 0:
        raise ValueError("tau must be positive")

    chol = np.linalg.cholesky(corr).astype(np.float64)
    normals = (
        np.random.default_rng(seed).standard_normal((int(n_simulations), s.size)).astype(np.float64)
    )

    terminals = np.asarray(_multi_asset_terminals(s, rate, v, tau, chol, normals))
    basket = terminals @ w
    payoff = (
        np.maximum(basket - strike, 0.0)
        if option_type == "call"
        else np.maximum(strike - basket, 0.0)
    )
    disc_payoff = math.exp(-rate * tau) * payoff
    price = float(np.mean(disc_payoff))
    se = float(np.std(disc_payoff) / math.sqrt(n_simulations))
    result = {"price": round(price, 8), "std_error": round(se, 8)}

    if greeks:

        def _basket_price(
            spots_: np.ndarray, rate_: float, sigmas_: np.ndarray, tau_: float
        ) -> float:
            terminals_ = np.asarray(
                _multi_asset_terminals(spots_, rate_, sigmas_, tau_, chol, normals)
            )
            basket_ = terminals_ @ w
            pay_ = (
                np.maximum(basket_ - strike, 0.0)
                if option_type == "call"
                else np.maximum(strike - basket_, 0.0)
            )
            return float(np.mean(math.exp(-rate_ * tau_) * pay_))

        result.update(
            _multi_asset_bump_reprice_greeks(
                _basket_price,
                s,
                rate,
                v,
                tau,
                price,
                d_rate=_GREEKS_BUMP_RATE,
                d_tau=min(_GREEKS_BUMP_TAU_DAYS / _DAYS_PER_YEAR, tau * 0.4),
            )
        )
    return result


def spread_option_kirk_approximation(
    spot1: float,
    spot2: float,
    strike: float,
    rate: float,
    sigma1: float,
    sigma2: float,
    rho: float,
    tau: float,
    option_type: str = "call",
) -> dict:  # type: ignore[type-arg]
    """Spread option price via Kirk's approximation.

    Prices an option on ``S1 − S2`` by reducing it to a Black-76 option on the
    ratio with an effective volatility. Exact when ``strike == 0`` (Margrabe).
    Inputs are treated as forwards (Black-76); the value is discounted once.

    Args:
        spot1: First-asset forward price.
        spot2: Second-asset forward price.
        strike: Spread strike.
        rate: Risk-free rate (continuous).
        sigma1: Volatility of asset 1.
        sigma2: Volatility of asset 2.
        rho: Correlation in [-1, 1].
        tau: Time to maturity (years, > 0).
        option_type: ``"call"`` or ``"put"``.

    Returns:
        Dict with ``price``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot1 <= 0 or spot2 <= 0 or sigma1 <= 0 or sigma2 <= 0 or tau <= 0:
        raise ValueError("spots, sigmas, tau must be positive")
    if not -1.0 <= rho <= 1.0:
        raise ValueError("rho must be in [-1, 1]")

    disc = math.exp(-rate * tau)
    f2k = spot2 + strike
    ratio = spot2 / f2k
    sigma_eff = math.sqrt(sigma1**2 - 2.0 * rho * sigma1 * sigma2 * ratio + (sigma2 * ratio) ** 2)
    sqrt_t = math.sqrt(tau)
    d1 = (math.log(spot1 / f2k) + 0.5 * sigma_eff**2 * tau) / (sigma_eff * sqrt_t)
    d2 = d1 - sigma_eff * sqrt_t
    if option_type == "call":
        price = disc * (spot1 * float(stats.norm.cdf(d1)) - f2k * float(stats.norm.cdf(d2)))
    else:
        price = disc * (f2k * float(stats.norm.cdf(-d2)) - spot1 * float(stats.norm.cdf(-d1)))
    return {"price": round(float(max(price, 0.0)), 8)}


def _compound_bivariate_cdf(x: float, y: float, rho: float) -> float:
    """Standard bivariate normal CDF ``M(x, y; rho)`` (Geske's compound formula
    building block). Symmetric in ``x``/``y`` for fixed ``rho``.
    """
    cov = [[1.0, rho], [rho, 1.0]]
    return float(stats.multivariate_normal(mean=[0.0, 0.0], cov=cov).cdf([x, y]))


def _compound_critical_price(
    strike_underlying: float,
    strike_compound: float,
    rate: float,
    sigma: float,
    tau_resid: float,
    under_type: str,
    div_yield: float,
) -> float:
    """Critical spot ``I`` at the compound expiry s.t. the underlying option's
    Black-Scholes value there equals ``strike_compound`` (Geske 1979's ``S*``).

    The underlying value is monotonic in spot (increasing for a call,
    decreasing for a put), so a Brent root always exists once the bracket is
    wide enough -- expanded geometrically until it brackets a sign change.
    """

    def _f(spot_: float) -> float:
        return (
            black_scholes_european_option(
                spot_, strike_underlying, rate, sigma, tau_resid, under_type, div_yield
            )["price"]
            - strike_compound
        )

    lo, hi = 1e-8, max(strike_underlying, 1.0) * 4.0
    f_lo, f_hi = _f(lo), _f(hi)
    tries = 0
    while f_lo * f_hi > 0.0 and tries < 60:
        hi *= 2.0
        f_hi = _f(hi)
        tries += 1
    if f_lo * f_hi > 0.0:
        raise ValueError(
            "compound_option_pricer: no critical price found for these inputs "
            "-- strike_compound is outside the underlying option's attainable "
            "value range"
        )
    return float(brentq(_f, lo, hi, xtol=1e-10, rtol=1e-12, maxiter=200))


def _geske_compound_price(
    spot: float,
    strike_underlying: float,
    strike_compound: float,
    rate: float,
    sigma: float,
    tau_compound: float,
    tau_underlying: float,
    compound_type: str,
    div_yield: float,
) -> float:
    """Geske (1979) closed-form compound-option price (all four types).

    d-terms follow the standard restatement (e.g. Haug, *The Complete Guide
    to Option Pricing Formulas*, "Compound options"; Hull, *Options, Futures
    and Other Derivatives*, ch. "Exotic options"): with ``I`` the critical
    spot at ``tau_compound`` where the underlying option is worth
    ``strike_compound``,

        a1 = [ln(S/I) + (b + sigma^2/2) tau_c] / (sigma sqrt(tau_c)), a2 = a1 - sigma sqrt(tau_c)
        b1 = [ln(S/K2) + (b + sigma^2/2) tau_u] / (sigma sqrt(tau_u)), b2 = b1 - sigma sqrt(tau_u)
        rho = sqrt(tau_c / tau_u),  b = rate - div_yield

    and ``M`` the bivariate normal CDF. Verified internally via the
    compound put-call parity identity ``CallOnX - PutOnX = V_under(S) -
    e^{-r tau_c} K1`` (true because a European option's discounted price
    process is itself a martingale under the risk-neutral measure) -- see
    ``tests/validation/test_derivatives_ref.py``.
    """
    under_type = "call" if compound_type.endswith("call") else "put"
    outer_is_call = compound_type.startswith("call")
    tau_resid = tau_underlying - tau_compound

    crit = _compound_critical_price(
        strike_underlying, strike_compound, rate, sigma, tau_resid, under_type, div_yield
    )

    sqrt_t1 = math.sqrt(tau_compound)
    sqrt_t2 = math.sqrt(tau_underlying)
    rho = sqrt_t1 / sqrt_t2
    b = rate - div_yield

    a1 = (math.log(spot / crit) + (b + 0.5 * sigma * sigma) * tau_compound) / (sigma * sqrt_t1)
    a2 = a1 - sigma * sqrt_t1
    b1 = (math.log(spot / strike_underlying) + (b + 0.5 * sigma * sigma) * tau_underlying) / (
        sigma * sqrt_t2
    )
    b2 = b1 - sigma * sqrt_t2

    disc_q2 = math.exp((b - rate) * tau_underlying)  # = e^{-div_yield * tau_underlying}
    disc_r2 = math.exp(-rate * tau_underlying)
    disc_r1 = math.exp(-rate * tau_compound)
    n_cdf = stats.norm.cdf

    if outer_is_call and under_type == "call":  # call-on-call
        price = (
            spot * disc_q2 * _compound_bivariate_cdf(a1, b1, rho)
            - strike_underlying * disc_r2 * _compound_bivariate_cdf(a2, b2, rho)
            - disc_r1 * strike_compound * float(n_cdf(a2))
        )
    elif not outer_is_call and under_type == "call":  # put-on-call
        price = (
            strike_underlying * disc_r2 * _compound_bivariate_cdf(-a2, b2, -rho)
            - spot * disc_q2 * _compound_bivariate_cdf(-a1, b1, -rho)
            + disc_r1 * strike_compound * float(n_cdf(-a2))
        )
    elif outer_is_call and under_type == "put":  # call-on-put
        price = (
            strike_underlying * disc_r2 * _compound_bivariate_cdf(-a2, -b2, rho)
            - spot * disc_q2 * _compound_bivariate_cdf(-a1, -b1, rho)
            - disc_r1 * strike_compound * float(n_cdf(-a2))
        )
    else:  # put-on-put
        price = (
            spot * disc_q2 * _compound_bivariate_cdf(a1, -b1, -rho)
            - strike_underlying * disc_r2 * _compound_bivariate_cdf(a2, -b2, -rho)
            + disc_r1 * strike_compound * float(n_cdf(a2))
        )
    return float(max(price, 0.0))


def _compound_option_pricer_mc(
    spot: float,
    strike_underlying: float,
    strike_compound: float,
    rate: float,
    sigma: float,
    tau_compound: float,
    tau_underlying: float,
    compound_type: str,
    div_yield: float,
    n_simulations: int,
    seed: int,
) -> dict:  # type: ignore[type-arg]
    """Monte Carlo cross-check for ``compound_option_pricer``: simulate the
    underlying asset to the compound expiry, price the underlying option
    analytically (Black-Scholes) at each path, then discount the compound
    payoff. This was the production implementation before the Geske
    closed-form (below) replaced it; kept here as an independent numerical
    reference for ``tests/validation/test_derivatives_ref.py``, not part of
    the public API.
    """
    under_type = "call" if compound_type.endswith("call") else "put"
    outer_is_call = compound_type.startswith("call")
    z = np.random.default_rng(seed).standard_normal(int(n_simulations))

    tau_resid = tau_underlying - tau_compound
    drift = (rate - div_yield - 0.5 * sigma * sigma) * tau_compound
    vol = sigma * math.sqrt(tau_compound)
    s_mid = spot * np.exp(drift + vol * z)
    sqrt_r = math.sqrt(tau_resid)
    d1 = (np.log(s_mid / strike_underlying) + (rate - div_yield + 0.5 * sigma**2) * tau_resid) / (
        sigma * sqrt_r
    )
    d2 = d1 - sigma * sqrt_r
    disc_r = math.exp(-rate * tau_resid)
    disc_q = math.exp(-div_yield * tau_resid)
    if under_type == "call":
        under_val = s_mid * disc_q * stats.norm.cdf(
            d1
        ) - strike_underlying * disc_r * stats.norm.cdf(d2)
    else:
        under_val = strike_underlying * disc_r * stats.norm.cdf(
            -d2
        ) - s_mid * disc_q * stats.norm.cdf(-d1)
    pay = (
        np.maximum(under_val - strike_compound, 0.0)
        if outer_is_call
        else np.maximum(strike_compound - under_val, 0.0)
    )
    disc_payoff = np.asarray(math.exp(-rate * tau_compound) * pay, dtype=np.float64)
    price = float(np.mean(disc_payoff))
    se = float(np.std(disc_payoff) / math.sqrt(n_simulations))
    return {"price": round(price, 8), "std_error": round(se, 8)}


def compound_option_pricer(
    spot: float,
    strike_underlying: float,
    strike_compound: float,
    rate: float,
    sigma: float,
    tau_compound: float,
    tau_underlying: float,
    n_simulations: int = 200_000,
    compound_type: str = "call-on-call",
    div_yield: float = 0.0,
    seed: int = 81,
    greeks: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Compound option (option-on-option) price via the Geske (1979) closed form.

    Supports the four standard compound types (call/put on call/put). See
    ``_geske_compound_price`` for the exact d-term algebra and its citation.

    Args:
        spot: Underlying spot.
        strike_underlying: Strike of the underlying option.
        strike_compound: Strike of the compound option (premium paid).
        rate: Risk-free rate (continuous).
        sigma: Volatility (> 0).
        tau_compound: Time to the compound option expiry.
        tau_underlying: Time to the underlying option expiry (> tau_compound).
        n_simulations: Unused by the closed-form price; retained for
            backward-compatible call signatures (was the MC path count
            before this function switched from Monte Carlo to the exact
            Geske formula -- see ``_compound_option_pricer_mc`` for that
            retained reference implementation).
        compound_type: ``call-on-call``, ``call-on-put``, ``put-on-call``,
            ``put-on-put``.
        div_yield: Continuous dividend yield.
        seed: Unused by the closed-form price; retained for the same reason
            as ``n_simulations``.
        greeks: Also compute delta/gamma/vega/theta/rho via bump-and-reprice
            on the exact closed-form price (deterministic -- no Monte Carlo
            noise to correlate away). theta bumps ``tau_compound`` (the
            compound leg's own time to expiry) while holding
            ``tau_underlying`` fixed -- i.e. both the compound's remaining
            life and the underlying option's residual tenor from that later
            date shrink together, the usual "time passing today"
            interpretation. Defaults to False so existing callers/results
            are unaffected.

    Returns:
        Dict with ``price``, ``std_error`` (always ``0.0`` -- the price is
        now exact, not simulated; kept for response-shape compatibility),
        and if ``greeks=True`` also ``delta``, ``gamma``, ``vega``, ``theta``,
        ``rho``.

    Raises:
        ValueError: If inputs are invalid.
    """
    valid = ("call-on-call", "call-on-put", "put-on-call", "put-on-put")
    if compound_type not in valid:
        raise ValueError(f"compound_type must be one of {valid}")
    if spot <= 0 or sigma <= 0 or tau_compound <= 0:
        raise ValueError("spot, sigma, tau_compound must be positive")
    if tau_underlying <= tau_compound:
        raise ValueError("tau_underlying must exceed tau_compound")

    def _compound_price(spot_: float, rate_: float, sigma_: float, tau_compound_: float) -> float:
        return _geske_compound_price(
            spot_,
            strike_underlying,
            strike_compound,
            rate_,
            sigma_,
            tau_compound_,
            tau_underlying,
            compound_type,
            div_yield,
        )

    price = _compound_price(spot, rate, sigma, tau_compound)
    result = {"price": round(price, 8), "std_error": 0.0}

    if greeks:
        result.update(
            _bump_reprice_greeks(
                _compound_price,
                spot,
                rate,
                sigma,
                tau_compound,
                price,
                d_s=spot * _GREEKS_BUMP_REL_SPOT,
                d_sigma=min(_GREEKS_BUMP_SIGMA, sigma * 0.5),
                d_rate=_GREEKS_BUMP_RATE,
                d_tau=min(_GREEKS_BUMP_TAU_DAYS / _DAYS_PER_YEAR, tau_compound * 0.4),
            )
        )
    return result


def chooser_option_pricer(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau_choose: float,
    tau_expiry: float,
    div_yield: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Simple chooser option price (closed form).

    At ``tau_choose`` the holder picks call or put (same strike/expiry). By
    put-call parity the value is a call plus a put on a reduced-maturity
    underlying: ``C(S,K,T) + P(S, K e^{-r(T-t)}·..., t)``. Worth at least the
    more valuable of the embedded call and put.

    Args:
        spot: Underlying spot.
        strike: Common strike.
        rate: Risk-free rate (continuous).
        sigma: Volatility (> 0).
        tau_choose: Time to the choice date.
        tau_expiry: Time to expiry (> tau_choose).
        div_yield: Continuous dividend yield.

    Returns:
        Dict with ``price``, ``call_value``, ``put_value``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau_choose <= 0:
        raise ValueError("spot, strike, sigma, tau_choose must be positive")
    if tau_expiry <= tau_choose:
        raise ValueError("tau_expiry must exceed tau_choose")

    call = black_scholes_european_option(spot, strike, rate, sigma, tau_expiry, "call", div_yield)[
        "price"
    ]
    # Rubinstein simple chooser: C(T2) + P with maturity t1 on strike discounted
    k_disc = strike * math.exp(-(rate - div_yield) * (tau_expiry - tau_choose))
    put_part = black_scholes_european_option(
        spot, k_disc, rate, sigma, tau_choose, "put", div_yield
    )["price"]
    price = call + put_part
    put_full = black_scholes_european_option(
        spot, strike, rate, sigma, tau_expiry, "put", div_yield
    )["price"]
    return {
        "price": round(float(price), 8),
        "call_value": round(float(call), 8),
        "put_value": round(float(put_full), 8),
    }

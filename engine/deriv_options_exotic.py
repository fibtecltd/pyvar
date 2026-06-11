"""engine/deriv_options_exotic.py — Exotic option pricers (Derivatives & Pricing).

Digital, barrier (closed-form Reiner-Rubinstein), Asian (MC arithmetic average),
lookback (MC floating strike), American (Longstaff-Schwartz LSM), Bermudan
(discrete-exercise LSM), rainbow (best/worst-of, MC), basket (MC), spread (Kirk
approximation), compound (Geske, MC), and chooser options.

Numba rules (CLAUDE.md §3.1): MC path kernels are stateless @njit(cache=True)
consuming pre-drawn normals. The LSM regression is done in pure Python (NumPy
lstsq) on the cashflow matrix returned by the path kernel.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit, prange
from scipy import stats

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
    d2 = (math.log(spot / strike) + (rate - div_yield - 0.5 * sigma * sigma) * tau) / (sigma * sqrt_t)
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
    """Single-barrier option price (Reiner-Rubinstein closed form).

    Uses the in-out parity ``knock-in + knock-out = vanilla`` so any of the four
    standard combinations is supported. Rebates are not modelled (set to 0).

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
        rebate: Unused placeholder (kept for API compatibility).

    Returns:
        Dict with ``price`` and the vanilla reference ``vanilla``.

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

    def _cnd(x: float) -> float:
        return float(stats.norm.cdf(x))

    x1 = math.log(spot / strike) / (sigma * sqrt_t) + (1.0 + mu) * sigma * sqrt_t
    x2 = math.log(spot / barrier) / (sigma * sqrt_t) + (1.0 + mu) * sigma * sqrt_t
    y1 = math.log(barrier * barrier / (spot * strike)) / (sigma * sqrt_t) + (1.0 + mu) * sigma * sqrt_t
    y2 = math.log(barrier / spot) / (sigma * sqrt_t) + (1.0 + mu) * sigma * sqrt_t

    a = phi * spot * disc_q * _cnd(phi * x1) - phi * strike * disc_r * _cnd(phi * x1 - phi * sigma * sqrt_t)
    b = phi * spot * disc_q * _cnd(phi * x2) - phi * strike * disc_r * _cnd(phi * x2 - phi * sigma * sqrt_t)
    c = phi * spot * disc_q * (barrier / spot) ** (2.0 * (mu + 1.0)) * _cnd(eta * y1) - phi * strike * disc_r * (
        barrier / spot
    ) ** (2.0 * mu) * _cnd(eta * y1 - eta * sigma * sqrt_t)
    d = phi * spot * disc_q * (barrier / spot) ** (2.0 * (mu + 1.0)) * _cnd(eta * y2) - phi * strike * disc_r * (
        barrier / spot
    ) ** (2.0 * mu) * _cnd(eta * y2 - eta * sigma * sqrt_t)

    vanilla = black_scholes_european_option(spot, strike, rate, sigma, tau, option_type, div_yield)["price"]
    strike_gt_barrier = strike > barrier

    # Knock-in closed forms (Haug tables); knock-out by in-out parity.
    if barrier_type == "down-and-in":
        if option_type == "call":
            ki = c if strike_gt_barrier else a - b + d
        else:
            ki = b - c + d if strike_gt_barrier else a
    elif barrier_type == "up-and-in":
        if option_type == "call":
            ki = a if strike_gt_barrier else b - c + d
        else:
            ki = a - b + d if strike_gt_barrier else c
    else:
        ki = None

    if barrier_type.endswith("in"):
        price = ki
    else:  # knock-out via parity
        in_type = barrier_type.replace("out", "in")
        ki_price = barrier_option_pricer(
            spot, strike, barrier, rate, sigma, tau, option_type, in_type, div_yield
        )["price"]
        price = vanilla - ki_price
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
    spot: float, rate: float, div_yield: float, sigma: float, tau: float,
    n_steps: int, n_sims: int, seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((int(n_sims), int(n_steps))).astype(np.float64)
    return _gbm_path_stats(spot, rate, div_yield, sigma, tau, normals)


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

    Returns:
        Dict with ``price``, ``std_error``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if average_type != "arithmetic":
        raise ValueError("only arithmetic averaging supported")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")

    stats_arr = _simulate_path_stats(spot, rate, div_yield, sigma, tau, n_steps, n_simulations, seed)
    avg = stats_arr[:, 1]
    if option_type == "call":
        payoff = np.maximum(avg - strike, 0.0)
    else:
        payoff = np.maximum(strike - avg, 0.0)
    disc = math.exp(-rate * tau)
    disc_payoff = disc * payoff
    price = float(np.mean(disc_payoff))
    se = float(np.std(disc_payoff) / math.sqrt(n_simulations))
    return {"price": round(price, 8), "std_error": round(se, 8)}


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

    Returns:
        Dict with ``price``, ``std_error``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if strike_type not in ("floating", "fixed"):
        raise ValueError("strike_type must be 'floating' or 'fixed'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")

    stats_arr = _simulate_path_stats(spot, rate, div_yield, sigma, tau, n_steps, n_simulations, seed)
    st, smin, smax = stats_arr[:, 0], stats_arr[:, 2], stats_arr[:, 3]
    if strike_type == "floating":
        payoff = (st - smin) if option_type == "call" else (smax - st)
    else:
        payoff = np.maximum(smax - strike, 0.0) if option_type == "call" else np.maximum(strike - smin, 0.0)
    disc = math.exp(-rate * tau)
    disc_payoff = disc * np.asarray(payoff, dtype=np.float64)
    price = float(np.mean(disc_payoff))
    se = float(np.std(disc_payoff) / math.sqrt(n_simulations))
    return {"price": round(price, 8), "std_error": round(se, 8)}


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
    paths: np.ndarray, strike: float, rate: float, dt: float, is_call: bool,
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
) -> dict:  # type: ignore[type-arg]
    """American option price via Longstaff-Schwartz Monte Carlo (LSM).

    Allows early exercise at every time step. The price must be >= the European
    price of the same option.

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

    Returns:
        Dict with ``price``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")

    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((int(n_simulations), int(n_steps))).astype(np.float64)
    paths = _gbm_full_paths(spot, rate, div_yield, sigma, tau, normals)
    dt = tau / n_steps
    mask = np.ones(int(n_steps) + 1, dtype=np.bool_)
    price = _lsm_price(paths, strike, rate, dt, option_type == "call", mask)
    return {"price": round(float(price), 8)}


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
) -> dict:  # type: ignore[type-arg]
    """Bermudan option price via LSM with discrete exercise dates.

    Early exercise is allowed only on an evenly-spaced subset of the time grid.
    Price lies between the European and American values.

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

    Returns:
        Dict with ``price``, ``exercise_dates``.

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
    return {"price": round(float(price), 8), "exercise_dates": int(exercise_dates)}


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


def _correlated_terminals(
    spots: np.ndarray, rate: float, sigmas: np.ndarray, tau: float,
    corr: np.ndarray, n_sims: int, seed: int,
) -> np.ndarray:
    chol = np.linalg.cholesky(corr).astype(np.float64)
    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((int(n_sims), spots.size)).astype(np.float64)
    return _multi_asset_terminals(spots, rate, sigmas, tau, chol, normals)


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

    Returns:
        Dict with ``price``, ``std_error``.

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

    terminals = _correlated_terminals(s, rate, v, tau, corr, n_simulations, seed)
    ref = np.max(terminals, axis=1) if rainbow_type == "best-of" else np.min(terminals, axis=1)
    payoff = np.maximum(ref - strike, 0.0) if option_type == "call" else np.maximum(strike - ref, 0.0)
    disc_payoff = math.exp(-rate * tau) * payoff
    price = float(np.mean(disc_payoff))
    se = float(np.std(disc_payoff) / math.sqrt(n_simulations))
    return {"price": round(price, 8), "std_error": round(se, 8)}


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

    Returns:
        Dict with ``price``, ``std_error``.

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

    terminals = _correlated_terminals(s, rate, v, tau, corr, n_simulations, seed)
    basket = terminals @ w
    payoff = np.maximum(basket - strike, 0.0) if option_type == "call" else np.maximum(strike - basket, 0.0)
    disc_payoff = math.exp(-rate * tau) * payoff
    price = float(np.mean(disc_payoff))
    se = float(np.std(disc_payoff) / math.sqrt(n_simulations))
    return {"price": round(price, 8), "std_error": round(se, 8)}


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
) -> dict:  # type: ignore[type-arg]
    """Compound option (option-on-option) price via nested valuation / MC.

    Simulates the underlying asset to the compound expiry, computes the
    Black-Scholes value of the underlying option there, then discounts the
    compound payoff. Supports the four standard compound types.

    Args:
        spot: Underlying spot.
        strike_underlying: Strike of the underlying option.
        strike_compound: Strike of the compound option (premium paid).
        rate: Risk-free rate (continuous).
        sigma: Volatility (> 0).
        tau_compound: Time to the compound option expiry.
        tau_underlying: Time to the underlying option expiry (> tau_compound).
        n_simulations: Number of paths.
        compound_type: ``call-on-call``, ``call-on-put``, ``put-on-call``,
            ``put-on-put``.
        div_yield: Continuous dividend yield.
        seed: RNG seed.

    Returns:
        Dict with ``price``, ``std_error``.

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

    under_type = "call" if compound_type.endswith("call") else "put"
    outer_is_call = compound_type.startswith("call")
    tau_resid = tau_underlying - tau_compound

    rng = np.random.default_rng(seed)
    z = rng.standard_normal(int(n_simulations))
    drift = (rate - div_yield - 0.5 * sigma * sigma) * tau_compound
    vol = sigma * math.sqrt(tau_compound)
    s_mid = spot * np.exp(drift + vol * z)
    # value the underlying option at the compound expiry for each path
    sqrt_r = math.sqrt(tau_resid)
    d1 = (np.log(s_mid / strike_underlying) + (rate - div_yield + 0.5 * sigma**2) * tau_resid) / (sigma * sqrt_r)
    d2 = d1 - sigma * sqrt_r
    disc_r = math.exp(-rate * tau_resid)
    disc_q = math.exp(-div_yield * tau_resid)
    if under_type == "call":
        under_val = s_mid * disc_q * stats.norm.cdf(d1) - strike_underlying * disc_r * stats.norm.cdf(d2)
    else:
        under_val = strike_underlying * disc_r * stats.norm.cdf(-d2) - s_mid * disc_q * stats.norm.cdf(-d1)
    if outer_is_call:
        payoff = np.maximum(under_val - strike_compound, 0.0)
    else:
        payoff = np.maximum(strike_compound - under_val, 0.0)
    disc_payoff = math.exp(-rate * tau_compound) * payoff
    price = float(np.mean(disc_payoff))
    se = float(np.std(disc_payoff) / math.sqrt(n_simulations))
    return {"price": round(price, 8), "std_error": round(se, 8)}


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

    call = black_scholes_european_option(spot, strike, rate, sigma, tau_expiry, "call", div_yield)["price"]
    # Rubinstein simple chooser: C(T2) + P with maturity t1 on strike discounted
    k_disc = strike * math.exp(-(rate - div_yield) * (tau_expiry - tau_choose))
    put_part = black_scholes_european_option(spot, k_disc, rate, sigma, tau_choose, "put", div_yield)["price"]
    price = call + put_part
    put_full = black_scholes_european_option(spot, strike, rate, sigma, tau_expiry, "put", div_yield)["price"]
    return {
        "price": round(float(price), 8),
        "call_value": round(float(call), 8),
        "put_value": round(float(put_full), 8),
    }

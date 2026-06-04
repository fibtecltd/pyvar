"""engine/volatility.py — Volatility & correlation models (Market Risk).

Implied-volatility surface construction, the GARCH family (GARCH(1,1), EGARCH,
GJR-GARCH) for conditional-volatility forecasting, realised volatility,
historical and DCC-GARCH correlation, and risk-factor PCA.

Numba rules (CLAUDE.md §3.1): the conditional-variance recursions are the
loop-carried sequential kernels Numba is built for — they are @njit(cache=True),
operate on float64 arrays and return arrays. Public wrappers may use SciPy.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy import stats

__all__ = [
    "volatility_surface_implied_vol",
    "garch_11_volatility_forecast",
]


def _bs_price(
    spot: float, strike: float, rate: float, sigma: float, tau: float, option_type: str
) -> float:
    """Black-Scholes price (no dividends) used by the implied-vol solver."""
    sqrt_t = np.sqrt(tau)
    d1 = (np.log(spot / strike) + (rate + 0.5 * sigma * sigma) * tau) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if option_type == "call":
        return float(spot * stats.norm.cdf(d1) - strike * np.exp(-rate * tau) * stats.norm.cdf(d2))
    return float(strike * np.exp(-rate * tau) * stats.norm.cdf(-d2) - spot * stats.norm.cdf(-d1))


def _implied_vol(
    price: float, spot: float, strike: float, rate: float, tau: float, option_type: str
) -> float:
    """Invert Black-Scholes for implied volatility by bisection (monotone in σ)."""
    lo, hi = 1e-6, 5.0
    mid = 0.5 * (lo + hi)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        diff = _bs_price(spot, strike, rate, mid, tau, option_type) - price
        if abs(diff) < 1e-10:
            break
        if diff > 0.0:
            hi = mid
        else:
            lo = mid
    return mid


def volatility_surface_implied_vol(
    market_prices: np.ndarray,
    strikes: np.ndarray,
    expiries: np.ndarray,
    spot: float,
    rate: float,
    option_type: str = "call",
) -> dict:  # type: ignore[type-arg]
    """Back out the implied-volatility surface from market option prices.

    For each quoted option the Black-Scholes equation is inverted for implied
    volatility by bisection. Round-tripping (pricing at the recovered IV)
    reproduces the input price.

    Args:
        market_prices: Observed option prices.
        strikes: Strike of each option.
        expiries: Time to expiry (years) of each option.
        spot: Underlying spot price.
        rate: Continuously-compounded risk-free rate.
        option_type: ``"call"`` or ``"put"``.

    Returns:
        Dict with ``implied_vols`` (aligned to inputs) and ``points`` (list of
        ``{strike, expiry, iv}``).

    Raises:
        ValueError: If inputs differ in length or ``option_type`` is invalid.
    """
    p = np.asarray(market_prices, dtype=np.float64)
    k = np.asarray(strikes, dtype=np.float64)
    t = np.asarray(expiries, dtype=np.float64)
    if not (p.size == k.size == t.size):
        raise ValueError("market_prices, strikes, expiries must be equal length")
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")

    ivs = np.empty(p.size, dtype=np.float64)
    points = []
    for i in range(p.size):
        iv = _implied_vol(float(p[i]), spot, float(k[i]), rate, float(t[i]), option_type)
        ivs[i] = iv
        points.append({"strike": float(k[i]), "expiry": float(t[i]), "iv": round(iv, 8)})
    return {
        "implied_vols": [round(float(v), 8) for v in ivs],
        "points": points,
    }


@njit(cache=True)
def _garch11_filter(
    residuals: np.ndarray, omega: float, alpha: float, beta: float, long_run: float
) -> np.ndarray:
    """GARCH(1,1) conditional-variance recursion σ²_t = ω + α ε²_{t-1} + β σ²_{t-1}."""
    n = residuals.shape[0]
    variance = np.empty(n, dtype=np.float64)
    variance[0] = long_run
    for t in range(1, n):
        variance[t] = omega + alpha * residuals[t - 1] * residuals[t - 1] + beta * variance[t - 1]
    return variance


def garch_11_volatility_forecast(
    returns: np.ndarray,
    alpha: float = 0.1,
    beta: float = 0.85,
    omega: float | None = None,
    horizon: int = 10,
) -> dict:  # type: ignore[type-arg]
    """GARCH(1,1) conditional-volatility filter and multi-step forecast.

    Filters the conditional variance and projects it forward. The h-step
    forecast mean-reverts to the long-run variance ``ω/(1−α−β)`` at rate
    ``(α+β)`` — the defining property of a stationary GARCH(1,1). If ``omega`` is
    not supplied it is set by variance targeting, ``ω = (1−α−β)·Var(returns)``.

    Args:
        returns: 1-D return series (demeaned internally to form residuals).
        alpha: ARCH coefficient (weight on the last squared shock).
        beta: GARCH coefficient (weight on the last variance).
        omega: Long-run variance constant; variance-targeted if None.
        horizon: Forecast horizon in periods.

    Returns:
        Dict with ``current_vol``, ``long_run_vol``, ``persistence`` (α+β) and
        the ``forecast_vol_path`` (length ``horizon``).

    Raises:
        ValueError: If the process is non-stationary (α+β >= 1) or inputs invalid.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size < 2:
        raise ValueError("returns must have at least 2 observations")
    persistence = alpha + beta
    if not 0.0 < persistence < 1.0:
        raise ValueError("require 0 < alpha + beta < 1 for stationarity")

    residuals = r - float(np.mean(r))
    sample_var = float(np.var(residuals))
    omega_val = (1.0 - persistence) * sample_var if omega is None else float(omega)
    long_run = omega_val / (1.0 - persistence)

    variance = _garch11_filter(residuals, omega_val, alpha, beta, long_run)
    # One-step-ahead then mean-reversion recursion for the forecast path.
    sigma2_next = omega_val + alpha * residuals[-1] ** 2 + beta * variance[-1]
    forecast_path = np.empty(horizon, dtype=np.float64)
    for k in range(horizon):
        forecast_path[k] = long_run + (persistence**k) * (sigma2_next - long_run)
    return {
        "current_vol": round(float(np.sqrt(variance[-1])), 8),
        "long_run_vol": round(float(np.sqrt(long_run)), 8),
        "persistence": round(float(persistence), 8),
        "forecast_vol_path": [round(float(np.sqrt(v)), 8) for v in forecast_path],
    }

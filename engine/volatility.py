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
    "egarch_volatility_model",
    "gjr_garch_asymmetric_model",
    "realised_volatility",
    "correlation_matrix_historical",
    "dcc_garch_dynamic_correlation",
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


@njit(cache=True)
def _egarch_filter(
    residuals: np.ndarray, omega: float, alpha: float, gamma: float, beta: float
) -> np.ndarray:
    """EGARCH(1,1) log-variance recursion (returns the variance series)."""
    n = residuals.shape[0]
    log_var = np.empty(n, dtype=np.float64)
    log_var[0] = omega / (1.0 - beta)
    e_abs_z = np.sqrt(2.0 / np.pi)
    for t in range(1, n):
        sigma_prev = np.sqrt(np.exp(log_var[t - 1]))
        z = residuals[t - 1] / sigma_prev if sigma_prev > 0.0 else 0.0
        log_var[t] = omega + beta * log_var[t - 1] + alpha * (np.abs(z) - e_abs_z) + gamma * z
    return np.exp(log_var)


def egarch_volatility_model(
    returns: np.ndarray,
    omega: float = -0.1,
    alpha: float = 0.1,
    gamma: float = -0.05,
    beta: float = 0.95,
) -> dict:  # type: ignore[type-arg]
    """EGARCH(1,1) asymmetric volatility model (Nelson 1991).

    Models log-variance, so conditional variance is positive for any parameters.
    The leverage term ``gamma`` makes negative shocks raise volatility more than
    positive shocks of equal size (when ``gamma < 0``).

    Args:
        returns: 1-D return series (demeaned internally).
        omega: Log-variance intercept.
        alpha: Magnitude (|z|) coefficient.
        gamma: Leverage coefficient (negative => negative shocks raise vol more).
        beta: Log-variance persistence (|beta| < 1 for stationarity).

    Returns:
        Dict with ``current_vol`` and the one-step ``forecast_vol``.

    Raises:
        ValueError: If ``returns`` is too short or ``beta`` is non-stationary.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size < 2:
        raise ValueError("returns must have at least 2 observations")
    if abs(beta) >= 1.0:
        raise ValueError("require |beta| < 1 for stationarity")

    residuals = r - float(np.mean(r))
    variance = _egarch_filter(residuals, omega, alpha, gamma, beta)
    log_var_last = float(np.log(variance[-1]))
    sigma_last = float(np.sqrt(variance[-1]))
    z_last = residuals[-1] / sigma_last if sigma_last > 0.0 else 0.0
    e_abs_z = np.sqrt(2.0 / np.pi)
    log_var_next = omega + beta * log_var_last + alpha * (abs(z_last) - e_abs_z) + gamma * z_last
    return {
        "current_vol": round(sigma_last, 8),
        "forecast_vol": round(float(np.sqrt(np.exp(log_var_next))), 8),
    }


@njit(cache=True)
def _gjr_filter(
    residuals: np.ndarray, omega: float, alpha: float, gamma: float, beta: float, long_run: float
) -> np.ndarray:
    """GJR-GARCH(1,1) conditional-variance recursion with a leverage indicator."""
    n = residuals.shape[0]
    variance = np.empty(n, dtype=np.float64)
    variance[0] = long_run
    for t in range(1, n):
        prev = residuals[t - 1]
        indicator = 1.0 if prev < 0.0 else 0.0
        variance[t] = omega + (alpha + gamma * indicator) * prev * prev + beta * variance[t - 1]
    return variance


def gjr_garch_asymmetric_model(
    returns: np.ndarray,
    alpha: float = 0.03,
    gamma: float = 0.08,
    beta: float = 0.88,
    omega: float | None = None,
) -> dict:  # type: ignore[type-arg]
    """GJR-GARCH(1,1) asymmetric volatility model (Glosten-Jagannathan-Runkle).

    A leverage indicator adds ``gamma`` to the ARCH coefficient when the prior
    shock was negative, so (for ``gamma > 0``) downside shocks raise volatility
    more. The long-run variance is ``ω/(1 − α − β − γ/2)``.

    Args:
        returns: 1-D return series (demeaned internally).
        alpha: Symmetric ARCH coefficient.
        gamma: Asymmetry coefficient applied to negative shocks.
        beta: GARCH persistence coefficient.
        omega: Variance intercept; variance-targeted if None.

    Returns:
        Dict with ``current_vol``, ``long_run_vol``, ``persistence`` and the
        one-step ``forecast_vol``.

    Raises:
        ValueError: If inputs are invalid or the process is non-stationary.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size < 2:
        raise ValueError("returns must have at least 2 observations")
    persistence = alpha + beta + 0.5 * gamma
    if not 0.0 < persistence < 1.0:
        raise ValueError("require 0 < alpha + beta + gamma/2 < 1 for stationarity")

    residuals = r - float(np.mean(r))
    sample_var = float(np.var(residuals))
    omega_val = (1.0 - persistence) * sample_var if omega is None else float(omega)
    long_run = omega_val / (1.0 - persistence)

    variance = _gjr_filter(residuals, omega_val, alpha, gamma, beta, long_run)
    prev = residuals[-1]
    indicator = 1.0 if prev < 0.0 else 0.0
    sigma2_next = omega_val + (alpha + gamma * indicator) * prev * prev + beta * variance[-1]
    return {
        "current_vol": round(float(np.sqrt(variance[-1])), 8),
        "long_run_vol": round(float(np.sqrt(long_run)), 8),
        "persistence": round(float(persistence), 8),
        "forecast_vol": round(float(np.sqrt(sigma2_next)), 8),
    }


def realised_volatility(
    returns: np.ndarray,
    annualisation_factor: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Realised volatility from a block of (typically high-frequency) returns.

    Realised variance is the sum of squared returns; realised volatility is its
    square root, and the annualised figure scales by ``sqrt(annualisation_factor)``.

    Args:
        returns: 1-D array of returns over the measurement block.
        annualisation_factor: Periods per year for annualisation (e.g. 252).

    Returns:
        Dict with ``realised_variance``, ``realised_vol`` and ``annualised_vol``.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size == 0:
        raise ValueError("returns must be non-empty")
    realised_var = float(np.sum(r * r))
    realised_vol = float(np.sqrt(realised_var))
    annualised = realised_vol * np.sqrt(annualisation_factor)
    return {
        "realised_variance": round(realised_var, 10),
        "realised_vol": round(realised_vol, 10),
        "annualised_vol": round(float(annualised), 10),
    }


def correlation_matrix_historical(returns_matrix: np.ndarray) -> dict:  # type: ignore[type-arg]
    """Historical (Pearson) correlation matrix of asset returns.

    Args:
        returns_matrix: ``(T, N)`` matrix of T observations on N assets.

    Returns:
        Dict with the ``correlation`` matrix, its ``is_symmetric`` flag and
        ``n_assets``.

    Raises:
        ValueError: If fewer than 2 observations or 1 asset are supplied.
    """
    a = np.asarray(returns_matrix, dtype=np.float64)
    if a.ndim != 2 or a.shape[0] < 2 or a.shape[1] < 1:
        raise ValueError("returns_matrix must be (T>=2, N>=1)")
    corr = np.corrcoef(a, rowvar=False)
    corr = np.atleast_2d(corr)
    return {
        "correlation": corr.tolist(),
        "is_symmetric": bool(np.allclose(corr, corr.T)),
        "n_assets": int(a.shape[1]),
    }


def dcc_garch_dynamic_correlation(
    returns_matrix: np.ndarray,
    a: float = 0.02,
    b: float = 0.95,
) -> dict:  # type: ignore[type-arg]
    """DCC-GARCH dynamic conditional correlation (Engle 2002), terminal R_T.

    Standardises each series, then evolves the quasi-correlation
    ``Q_t = (1−a−b) Q̄ + a z_{t-1} z_{t-1}' + b Q_{t-1}`` and normalises to a
    correlation matrix. With ``a = b = 0`` it collapses to the constant
    unconditional correlation Q̄.

    Args:
        returns_matrix: ``(T, N)`` matrix of T observations on N assets.
        a: DCC news coefficient.
        b: DCC persistence coefficient (require a + b < 1).

    Returns:
        Dict with the terminal ``dynamic_correlation`` matrix and ``a``, ``b``.

    Raises:
        ValueError: If shapes are invalid or ``a + b >= 1``.
    """
    x = np.asarray(returns_matrix, dtype=np.float64)
    if x.ndim != 2 or x.shape[0] < 2 or x.shape[1] < 1:
        raise ValueError("returns_matrix must be (T>=2, N>=1)")
    if not 0.0 <= a + b < 1.0:
        raise ValueError("require 0 <= a + b < 1")

    std = np.std(x, axis=0)
    std = np.where(std > 0.0, std, 1.0)
    z = (x - np.mean(x, axis=0)) / std  # standardised residuals
    q_bar = np.corrcoef(z, rowvar=False)
    q_bar = np.atleast_2d(q_bar)
    q = q_bar.copy()
    for t in range(1, z.shape[0]):
        outer = np.outer(z[t - 1], z[t - 1])
        q = (1.0 - a - b) * q_bar + a * outer + b * q
    d_inv = np.diag(1.0 / np.sqrt(np.diag(q)))
    r_t = d_inv @ q @ d_inv
    return {
        "dynamic_correlation": r_t.tolist(),
        "a": round(float(a), 8),
        "b": round(float(b), 8),
    }

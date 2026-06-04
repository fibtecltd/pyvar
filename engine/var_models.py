"""engine/var_models.py — Value-at-Risk model family (Market Risk).

Implements the VaR sub-domain of the Market Risk function set: parametric,
historical, filtered-historical, Cornish-Fisher, and the allocation /
decomposition measures (component, marginal, incremental, by-risk-factor) plus
the percentile fan chart.

Numba rules (CLAUDE.md §3.1) are honoured exactly:
  * @njit kernels are stateless, take only float64 arrays / scalars, never
    import internally, and return NumPy arrays.
  * All randomness is pre-drawn in pure Python before the JIT region.
  * Public wrappers convert results to Python types and may use SciPy.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy import stats

from engine.montecarlo import run_monte_carlo_var

# Re-export: CSV function "Monte Carlo VaR (Parametric Normal)" is the existing
# engine entry point. Exposed here under the VaR-family namespace for cohesion.
monte_carlo_var_parametric_normal = run_monte_carlo_var

__all__ = [
    "monte_carlo_var_parametric_normal",
    "historical_simulation_var",
    "filtered_historical_simulation_var",
    "parametric_delta_normal_var",
    "cornish_fisher_var",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _empirical_var_es(sorted_losses: np.ndarray, confidence_level: float) -> np.ndarray:
    """Empirical VaR and ES from an ascending sorted loss array.

    Returns a 2-element float64 array ``[var, es]`` (RULE 5: arrays only).
    """
    n = sorted_losses.shape[0]
    idx = int(np.floor(confidence_level * n))
    if idx > n - 1:
        idx = n - 1
    var = sorted_losses[idx]
    tail_sum = 0.0
    count = 0
    for i in range(idx, n):
        tail_sum += sorted_losses[i]
        count += 1
    es = tail_sum / count if count > 0 else var
    out = np.empty(2, dtype=np.float64)
    out[0] = var
    out[1] = es
    return out


@njit(cache=True)
def _ewma_vol(returns: np.ndarray, lam: float) -> np.ndarray:
    """RiskMetrics EWMA conditional volatility series (sequential recursion).

    A scalar recursion is exactly the loop-carried dependency Numba excels at;
    kept JIT-compiled for backtest sweeps over long histories.
    """
    n = returns.shape[0]
    variance = np.empty(n, dtype=np.float64)
    v = returns[0] * returns[0]
    variance[0] = v
    for t in range(1, n):
        v = lam * v + (1.0 - lam) * returns[t - 1] * returns[t - 1]
        variance[t] = v
    return np.sqrt(variance)


# ── Public functions ─────────────────────────────────────────────────────────


def historical_simulation_var(
    returns: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.99,
) -> dict:  # type: ignore[type-arg]
    """Non-parametric Historical Simulation VaR.

    Re-prices the portfolio under each observed historical return and reads the
    empirical loss quantile — making no distributional assumption.

    Args:
        returns: 1-D array of historical portfolio returns (fraction, not pct).
        portfolio_value: Current portfolio value in base currency.
        confidence_level: VaR confidence in [0.90, 0.9999], e.g. 0.99.

    Returns:
        Dict with ``var_pct``, ``var_abs``, ``cvar_pct``, ``cvar_abs`` and the
        observation count ``n_obs``.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if returns.size == 0:
        raise ValueError("returns must be non-empty")

    sorted_losses = np.sort(-returns)  # ascending losses
    var, es = _empirical_var_es(sorted_losses, confidence_level)
    var_pct = float(var)
    cvar_pct = float(es)
    return {
        "var_pct": round(var_pct, 8),
        "var_abs": round(var_pct * portfolio_value, 2),
        "cvar_pct": round(cvar_pct, 8),
        "cvar_abs": round(cvar_pct * portfolio_value, 2),
        "confidence_level": confidence_level,
        "n_obs": int(returns.size),
    }


def filtered_historical_simulation_var(
    returns: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.99,
    lambda_decay: float = 0.94,
) -> dict:  # type: ignore[type-arg]
    """Filtered Historical Simulation VaR (Barone-Adesi & Giannopoulos).

    Standardises returns by their EWMA conditional volatility, then re-scales
    the standardised residuals by the *current* volatility forecast before
    taking the empirical quantile. This captures volatility clustering that
    plain historical simulation ignores.

    Args:
        returns: 1-D array of historical portfolio returns.
        portfolio_value: Current portfolio value in base currency.
        confidence_level: VaR confidence in [0.90, 0.9999].
        lambda_decay: EWMA decay factor (RiskMetrics default 0.94).

    Returns:
        Dict with ``var_pct``, ``var_abs``, ``cvar_pct``, ``cvar_abs``,
        ``sigma_forecast``.

    Raises:
        ValueError: If fewer than 2 observations are supplied.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if returns.size < 2:
        raise ValueError("filtered HS requires at least 2 observations")

    sigma = _ewma_vol(returns, lambda_decay)
    standardized = returns / np.where(sigma > 0.0, sigma, 1.0)
    # One-step-ahead volatility forecast from the last observation.
    sigma_forecast = float(
        np.sqrt(lambda_decay * sigma[-1] ** 2 + (1.0 - lambda_decay) * returns[-1] ** 2)
    )
    simulated = sigma_forecast * standardized
    sorted_losses = np.sort(-simulated)
    var, es = _empirical_var_es(sorted_losses, confidence_level)
    var_pct = float(var)
    cvar_pct = float(es)
    return {
        "var_pct": round(var_pct, 8),
        "var_abs": round(var_pct * portfolio_value, 2),
        "cvar_pct": round(cvar_pct, 8),
        "cvar_abs": round(cvar_pct * portfolio_value, 2),
        "sigma_forecast": round(sigma_forecast, 8),
        "confidence_level": confidence_level,
    }


def parametric_delta_normal_var(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.99,
    horizon_days: int = 1,
) -> dict:  # type: ignore[type-arg]
    """Variance-covariance (delta-normal) VaR.

    Assumes asset returns are jointly normal so portfolio loss is normal with
    standard deviation ``sqrt(w' Σ w)``. VaR is the scaled normal quantile.

    Args:
        weights: Portfolio weights per asset (need not sum to 1).
        cov_matrix: Asset return covariance matrix (per-period).
        portfolio_value: Current portfolio value in base currency.
        confidence_level: VaR confidence in [0.90, 0.9999].
        horizon_days: Risk horizon in trading days (sqrt-time scaling).

    Returns:
        Dict with ``var_pct``, ``var_abs``, ``sigma_p`` (per-period portfolio
        volatility) and ``z_score``.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    w = np.asarray(weights, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    if cov.shape != (w.size, w.size):
        raise ValueError("cov_matrix must be (n_assets, n_assets) matching weights")

    portfolio_var = float(w @ cov @ w)
    sigma_p = np.sqrt(max(portfolio_var, 0.0))
    z = float(stats.norm.ppf(confidence_level))
    var_pct = z * sigma_p * np.sqrt(horizon_days)
    return {
        "var_pct": round(float(var_pct), 8),
        "var_abs": round(float(var_pct) * portfolio_value, 2),
        "sigma_p": round(float(sigma_p), 8),
        "z_score": round(z, 6),
        "confidence_level": confidence_level,
        "horizon_days": horizon_days,
    }


def cornish_fisher_var(
    returns: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.99,
    skewness: float | None = None,
    excess_kurtosis: float | None = None,
) -> dict:  # type: ignore[type-arg]
    """Cornish-Fisher (modified) VaR.

    Expands the Gaussian quantile with the third and fourth moments so the VaR
    reflects skewness and fat tails. When skewness and excess kurtosis are both
    zero it collapses exactly to the parametric delta-normal VaR.

    Args:
        returns: 1-D array of historical portfolio returns.
        portfolio_value: Current portfolio value in base currency.
        confidence_level: VaR confidence in [0.90, 0.9999].
        skewness: Override sample skewness (computed from data if None).
        excess_kurtosis: Override sample excess kurtosis (computed if None).

    Returns:
        Dict with ``var_pct``, ``var_abs``, ``z_cf`` (modified quantile),
        ``skewness``, ``excess_kurtosis``.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if returns.size == 0:
        raise ValueError("returns must be non-empty")

    mu = float(np.mean(returns))
    sigma = float(np.std(returns))
    s = float(stats.skew(returns)) if skewness is None else float(skewness)
    k = (
        float(stats.kurtosis(returns, fisher=True))
        if excess_kurtosis is None
        else float(excess_kurtosis)
    )

    z = float(stats.norm.ppf(confidence_level))
    z_cf = (
        z
        + (z**2 - 1.0) / 6.0 * s
        + (z**3 - 3.0 * z) / 24.0 * k
        - (2.0 * z**3 - 5.0 * z) / 36.0 * s**2
    )
    var_pct = z_cf * sigma - mu  # loss is positive
    return {
        "var_pct": round(float(var_pct), 8),
        "var_abs": round(float(var_pct) * portfolio_value, 2),
        "z_cf": round(float(z_cf), 6),
        "skewness": round(s, 6),
        "excess_kurtosis": round(k, 6),
        "confidence_level": confidence_level,
    }

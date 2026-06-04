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
    "component_var",
    "marginal_var",
    "incremental_var",
    "var_by_risk_factor",
    "var_fan_chart",
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


def marginal_var(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
    confidence_level: float = 0.99,
) -> dict:  # type: ignore[type-arg]
    """Marginal VaR — sensitivity of portfolio VaR to each position weight.

    For the delta-normal model VaR = z * sqrt(w' Σ w), the marginal VaR is the
    gradient ``∂VaR/∂w_i = z * (Σ w)_i / sigma_p``.

    Args:
        weights: Portfolio weights per asset.
        cov_matrix: Asset return covariance matrix.
        confidence_level: VaR confidence in [0.90, 0.9999].

    Returns:
        Dict with ``marginal`` (per-asset gradient list), ``sigma_p`` and the
        total ``var_pct``.

    Raises:
        ValueError: If the covariance shape does not match the weights.
    """
    w = np.asarray(weights, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    if cov.shape != (w.size, w.size):
        raise ValueError("cov_matrix must be (n_assets, n_assets) matching weights")

    sigma_p = float(np.sqrt(max(float(w @ cov @ w), 0.0)))
    z = float(stats.norm.ppf(confidence_level))
    if sigma_p == 0.0:
        marginal = np.zeros_like(w)
    else:
        marginal = z * (cov @ w) / sigma_p
    return {
        "marginal": [round(float(m), 8) for m in marginal],
        "sigma_p": round(sigma_p, 8),
        "var_pct": round(z * sigma_p, 8),
        "confidence_level": confidence_level,
    }


def component_var(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.99,
) -> dict:  # type: ignore[type-arg]
    """Component VaR via Euler allocation.

    Allocates total VaR to each position as ``w_i * marginal_i``. Because VaR is
    homogeneous of degree 1 in the weights, the components sum exactly to the
    total VaR (Euler's theorem) — the property regulators require for a
    coherent risk decomposition.

    Args:
        weights: Portfolio weights per asset.
        cov_matrix: Asset return covariance matrix.
        portfolio_value: Current portfolio value in base currency.
        confidence_level: VaR confidence in [0.90, 0.9999].

    Returns:
        Dict with ``component`` (per-asset VaR list, % terms),
        ``component_abs``, total ``var_pct``/``var_abs``.

    Raises:
        ValueError: If the covariance shape does not match the weights.
    """
    w = np.asarray(weights, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    if cov.shape != (w.size, w.size):
        raise ValueError("cov_matrix must be (n_assets, n_assets) matching weights")

    sigma_p = float(np.sqrt(max(float(w @ cov @ w), 0.0)))
    z = float(stats.norm.ppf(confidence_level))
    if sigma_p == 0.0:
        components = np.zeros_like(w)
    else:
        components = z * w * (cov @ w) / sigma_p  # Euler component
    var_pct = float(np.sum(components))
    return {
        "component": [round(float(c), 8) for c in components],
        "component_abs": [round(float(c) * portfolio_value, 2) for c in components],
        "var_pct": round(var_pct, 8),
        "var_abs": round(var_pct * portfolio_value, 2),
        "confidence_level": confidence_level,
    }


def incremental_var(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
    position_index: int,
    portfolio_value: float,
    confidence_level: float = 0.99,
) -> dict:  # type: ignore[type-arg]
    """Incremental VaR of a single position.

    The exact (non-marginal) effect of a position on portfolio VaR:
    ``VaR(full) − VaR(portfolio with position i removed)``.

    Args:
        weights: Portfolio weights per asset.
        cov_matrix: Asset return covariance matrix.
        position_index: Index of the position whose contribution is measured.
        portfolio_value: Current portfolio value in base currency.
        confidence_level: VaR confidence in [0.90, 0.9999].

    Returns:
        Dict with ``incremental_pct``, ``incremental_abs``, ``var_full_pct`` and
        ``var_without_pct``.

    Raises:
        ValueError: If shapes mismatch or ``position_index`` is out of range.
    """
    w = np.asarray(weights, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    if cov.shape != (w.size, w.size):
        raise ValueError("cov_matrix must be (n_assets, n_assets) matching weights")
    if not 0 <= position_index < w.size:
        raise ValueError("position_index out of range")

    z = float(stats.norm.ppf(confidence_level))
    var_full = z * float(np.sqrt(max(float(w @ cov @ w), 0.0)))
    w_without = w.copy()
    w_without[position_index] = 0.0
    var_without = z * float(np.sqrt(max(float(w_without @ cov @ w_without), 0.0)))
    incremental = var_full - var_without
    return {
        "incremental_pct": round(incremental, 8),
        "incremental_abs": round(incremental * portfolio_value, 2),
        "var_full_pct": round(var_full, 8),
        "var_without_pct": round(var_without, 8),
        "position_index": position_index,
        "confidence_level": confidence_level,
    }


def var_by_risk_factor(
    factor_exposures: np.ndarray,
    factor_cov: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.99,
    factor_names: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Decompose VaR across systematic risk factors (Euler allocation).

    Identical Euler decomposition to :func:`component_var` but expressed in
    risk-factor space: given portfolio factor exposures ``b`` and factor
    covariance ``F``, the factor contribution is
    ``z * b_i * (F b)_i / sigma_p`` and contributions sum to the total VaR.

    Args:
        factor_exposures: Portfolio sensitivity (beta) to each risk factor.
        factor_cov: Risk-factor covariance matrix.
        portfolio_value: Current portfolio value in base currency.
        confidence_level: VaR confidence in [0.90, 0.9999].
        factor_names: Optional labels; defaults to ``factor_0, factor_1, ...``.

    Returns:
        Dict with ``contributions`` (name -> VaR%), ``var_pct`` and ``var_abs``.

    Raises:
        ValueError: If the covariance shape does not match the exposures.
    """
    b = np.asarray(factor_exposures, dtype=np.float64)
    cov = np.asarray(factor_cov, dtype=np.float64)
    if cov.shape != (b.size, b.size):
        raise ValueError("factor_cov must be (n_factors, n_factors) matching exposures")
    if factor_names is None:
        factor_names = [f"factor_{i}" for i in range(b.size)]

    sigma_p = float(np.sqrt(max(float(b @ cov @ b), 0.0)))
    z = float(stats.norm.ppf(confidence_level))
    if sigma_p == 0.0:
        contrib = np.zeros_like(b)
    else:
        contrib = z * b * (cov @ b) / sigma_p
    var_pct = float(np.sum(contrib))
    return {
        "contributions": {factor_names[i]: round(float(contrib[i]), 8) for i in range(b.size)},
        "var_pct": round(var_pct, 8),
        "var_abs": round(var_pct * portfolio_value, 2),
        "confidence_level": confidence_level,
    }


def var_fan_chart(
    returns: np.ndarray,
    portfolio_value: float,
    confidence_levels: tuple[float, ...] = (0.90, 0.95, 0.99),
    horizon_days: int = 10,
) -> dict:  # type: ignore[type-arg]
    """VaR fan chart — parametric VaR bands across confidence levels and horizons.

    Produces, for each confidence level, the VaR projected over 1..H days using
    square-root-of-time volatility scaling — the standard visualisation of how
    the loss envelope widens with the holding period.

    Args:
        returns: 1-D array of historical portfolio returns.
        portfolio_value: Current portfolio value in base currency.
        confidence_levels: Confidence levels for the fan bands (each in
            [0.90, 0.9999]).
        horizon_days: Maximum projection horizon in trading days.

    Returns:
        Dict with ``horizons`` (1..H), ``bands`` (confidence -> per-horizon VaR%)
        and ``bands_abs`` in currency terms.

    Raises:
        ValueError: If ``returns`` is empty or ``horizon_days`` < 1.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if returns.size == 0:
        raise ValueError("returns must be non-empty")
    if horizon_days < 1:
        raise ValueError("horizon_days must be >= 1")

    mu = float(np.mean(returns))
    sigma = float(np.std(returns))
    horizons = list(range(1, horizon_days + 1))
    bands: dict[str, list[float]] = {}
    bands_abs: dict[str, list[float]] = {}
    for cl in confidence_levels:
        z = float(stats.norm.ppf(cl))
        series = [z * sigma * np.sqrt(h) - mu * h for h in horizons]
        key = f"cl_{int(round(cl * 10000)):04d}"
        bands[key] = [round(float(v), 8) for v in series]
        bands_abs[key] = [round(float(v) * portfolio_value, 2) for v in series]
    return {
        "horizons": horizons,
        "bands": bands,
        "bands_abs": bands_abs,
    }

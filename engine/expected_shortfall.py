"""engine/expected_shortfall.py — Expected Shortfall (CVaR) family (Market Risk).

Expected Shortfall is the Basel IV / FRTB standard market-risk measure. Every
function here computes ES as the **mean** of losses **beyond** the VaR threshold
(CLAUDE.md §4.2) — never the median or the max — and the decompositions are
Euler-additive so the components sum exactly to total ES.

Numba rules (CLAUDE.md §3.1): the tail-mean kernel is a stateless @njit function
operating on float64 arrays; public wrappers convert to Python types.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy import stats

from engine.montecarlo import run_monte_carlo_var

__all__ = [
    "conditional_var_es",
    "historical_expected_shortfall",
    "monte_carlo_expected_shortfall",
    "cvar_decomposition_euler",
    "stressed_expected_shortfall",
]


@njit(cache=True)
def _tail_mean(sorted_losses: np.ndarray, confidence_level: float) -> np.ndarray:
    """VaR and ES (mean of the tail beyond VaR) from ascending sorted losses.

    Returns a 2-element float64 array ``[var, es]``. ES is the arithmetic mean
    of every loss at or beyond the VaR index — the regulatory definition.
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


def conditional_var_es(
    returns: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.975,
) -> dict:  # type: ignore[type-arg]
    """Conditional VaR (Expected Shortfall) from a return series.

    The FRTB IMA capital metric is ES at 97.5% (hence the default). ES is the
    mean loss conditional on exceeding the VaR threshold and is always >= VaR.

    Args:
        returns: 1-D array of historical portfolio returns.
        portfolio_value: Current portfolio value in base currency.
        confidence_level: ES confidence in [0.90, 0.9999]; FRTB uses 0.975.

    Returns:
        Dict with ``var_pct``, ``es_pct``, ``var_abs``, ``es_abs``.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if returns.size == 0:
        raise ValueError("returns must be non-empty")
    sorted_losses = np.sort(-returns)
    var, es = _tail_mean(sorted_losses, confidence_level)
    return {
        "var_pct": round(float(var), 8),
        "es_pct": round(float(es), 8),
        "var_abs": round(float(var) * portfolio_value, 2),
        "es_abs": round(float(es) * portfolio_value, 2),
        "confidence_level": confidence_level,
    }


def historical_expected_shortfall(
    returns: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.975,
) -> dict:  # type: ignore[type-arg]
    """Non-parametric historical Expected Shortfall.

    Identical tail-mean definition as :func:`conditional_var_es` but framed as
    the historical-simulation ES: no distributional assumption, the empirical
    tail is averaged directly.

    Args:
        returns: 1-D array of historical portfolio returns.
        portfolio_value: Current portfolio value in base currency.
        confidence_level: ES confidence in [0.90, 0.9999].

    Returns:
        Dict with ``es_pct``, ``es_abs``, ``var_pct``, ``n_tail`` (tail count).

    Raises:
        ValueError: If ``returns`` is empty.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if returns.size == 0:
        raise ValueError("returns must be non-empty")
    sorted_losses = np.sort(-returns)
    var, es = _tail_mean(sorted_losses, confidence_level)
    n = sorted_losses.size
    idx = min(int(np.floor(confidence_level * n)), n - 1)
    return {
        "es_pct": round(float(es), 8),
        "es_abs": round(float(es) * portfolio_value, 2),
        "var_pct": round(float(var), 8),
        "n_tail": int(n - idx),
        "confidence_level": confidence_level,
    }


def monte_carlo_expected_shortfall(
    returns: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.975,
    n_simulations: int = 100_000,
    horizon_days: int = 1,
    seed: int | None = 42,
) -> dict:  # type: ignore[type-arg]
    """Monte Carlo Expected Shortfall.

    Runs the parametric-normal Monte Carlo engine and reads the ES (CVaR) from
    the simulated loss distribution. Deterministic for a fixed seed.

    Args:
        returns: 1-D array of historical portfolio returns (fits mu, sigma).
        portfolio_value: Current portfolio value in base currency.
        confidence_level: ES confidence in [0.90, 0.9999].
        n_simulations: Number of Monte Carlo paths.
        horizon_days: Risk horizon in trading days.
        seed: RNG seed for reproducibility.

    Returns:
        Dict with ``es_pct``, ``es_abs``, ``var_pct``, ``var_abs``,
        ``n_simulations``.
    """
    mc = run_monte_carlo_var(
        returns,
        portfolio_value=portfolio_value,
        confidence_level=confidence_level,
        horizon_days=horizon_days,
        n_simulations=n_simulations,
        seed=seed,
    )
    return {
        "es_pct": mc["cvar_pct"],
        "es_abs": mc["cvar_abs"],
        "var_pct": mc["var_pct"],
        "var_abs": mc["var_abs"],
        "n_simulations": mc["n_simulations"],
        "confidence_level": confidence_level,
    }


def cvar_decomposition_euler(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.975,
) -> dict:  # type: ignore[type-arg]
    """Euler decomposition of Gaussian Expected Shortfall.

    Under the normal model ES = sigma_p * φ(z) / (1 − α). ES is homogeneous of
    degree 1 in the weights, so component ES_i = w_i * (Σ w)_i / sigma_p *
    φ(z)/(1 − α) and the components sum exactly to total ES (Euler's theorem).

    Args:
        weights: Portfolio weights per asset.
        cov_matrix: Asset return covariance matrix.
        portfolio_value: Current portfolio value in base currency.
        confidence_level: ES confidence in [0.90, 0.9999].

    Returns:
        Dict with ``component`` (per-asset ES%), ``component_abs``, ``es_pct``,
        ``es_abs``.

    Raises:
        ValueError: If the covariance shape does not match the weights.
    """
    w = np.asarray(weights, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    if cov.shape != (w.size, w.size):
        raise ValueError("cov_matrix must be (n_assets, n_assets) matching weights")

    sigma_p = float(np.sqrt(max(float(w @ cov @ w), 0.0)))
    z = float(stats.norm.ppf(confidence_level))
    es_factor = float(stats.norm.pdf(z) / (1.0 - confidence_level))  # φ(z)/(1−α)
    if sigma_p == 0.0:
        components = np.zeros_like(w)
    else:
        components = (w * (cov @ w) / sigma_p) * es_factor
    es_pct = float(np.sum(components))
    return {
        "component": [round(float(c), 8) for c in components],
        "component_abs": [round(float(c) * portfolio_value, 2) for c in components],
        "es_pct": round(es_pct, 8),
        "es_abs": round(es_pct * portfolio_value, 2),
        "confidence_level": confidence_level,
    }


def stressed_expected_shortfall(
    returns: np.ndarray,
    stress_start: int,
    stress_end: int,
    portfolio_value: float,
    confidence_level: float = 0.975,
) -> dict:  # type: ignore[type-arg]
    """Stressed Expected Shortfall (FRTB IMA).

    FRTB requires ES to be calibrated to a historical period of significant
    financial stress. This computes ES over the supplied stressed window
    ``returns[stress_start:stress_end]`` only.

    Args:
        returns: Full 1-D array of historical portfolio returns.
        stress_start: Inclusive start index of the stressed window.
        stress_end: Exclusive end index of the stressed window.
        portfolio_value: Current portfolio value in base currency.
        confidence_level: ES confidence in [0.90, 0.9999]; FRTB uses 0.975.

    Returns:
        Dict with ``stressed_es_pct``, ``stressed_es_abs``,
        ``stressed_var_pct``, ``window_size``.

    Raises:
        ValueError: If the window is empty or out of range.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if not 0 <= stress_start < stress_end <= returns.size:
        raise ValueError("invalid stress window indices")
    window = returns[stress_start:stress_end]
    if window.size == 0:
        raise ValueError("stress window must be non-empty")
    sorted_losses = np.sort(-window)
    var, es = _tail_mean(sorted_losses, confidence_level)
    return {
        "stressed_es_pct": round(float(es), 8),
        "stressed_es_abs": round(float(es) * portfolio_value, 2),
        "stressed_var_pct": round(float(var), 8),
        "window_size": int(window.size),
        "confidence_level": confidence_level,
    }

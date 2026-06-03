"""
engine/metrics.py — Derived risk metrics computed from the VaR loss distribution

Reasoning:
- All metrics are pure NumPy functions operating on the sorted loss array
  returned by run_monte_carlo_var. No re-simulation needed.
- Keeping metrics separate from the engine makes each testable in isolation
  and allows new metrics to be added without touching the JIT kernel.
"""

import numpy as np


def compute_cvar(sorted_losses: np.ndarray, confidence_level: float) -> float:
    """
    Conditional VaR (Expected Shortfall) — mean of losses beyond VaR threshold.
    Regulatory standard under Basel III / FRTB for market risk capital.
    """
    cutoff = int(np.floor(confidence_level * len(sorted_losses)))
    return float(np.mean(sorted_losses[cutoff:]))


def compute_loss_percentiles(
    sorted_losses: np.ndarray,
    percentiles: list[float] | None = None,
) -> dict[str, float]:
    """
    Returns a dict of {percentile_label: loss_value} for fan chart display.
    Default percentiles cover the standard regulatory range.
    """
    if percentiles is None:
        percentiles = [0.50, 0.75, 0.90, 0.95, 0.99, 0.995]

    result = {}
    n = len(sorted_losses)
    for p in percentiles:
        idx = min(int(np.floor(p * n)), n - 1)
        result[f"p{int(p * 1000):04d}"] = round(float(sorted_losses[idx]), 6)
    return result


def compute_rolling_var(
    returns: np.ndarray,
    window: int = 250,
    confidence_level: float = 0.99,
) -> np.ndarray:
    """
    Parametric (Gaussian) rolling VaR using a expanding window.
    Fast approximation for backtesting — not the full Monte Carlo.
    Uses scipy.stats.norm for the quantile function.

    Returns array of VaR estimates, same length as returns (NaN for first window obs).
    """
    from scipy.stats import norm

    n = len(returns)
    rolling_var = np.full(n, np.nan)
    q = norm.ppf(confidence_level)

    for i in range(window, n):
        window_returns = returns[i - window : i]
        mu = np.mean(window_returns)
        sigma = np.std(window_returns)
        rolling_var[i] = -(mu - q * sigma)  # loss is positive

    return rolling_var


def compute_breaches(
    actual_returns: np.ndarray,
    var_estimates: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """
    Backtesting: count days where actual loss exceeded VaR estimate.
    Basel traffic-light zones:
      Green  < 5 breaches / 250 days
      Yellow 5-9 breaches
      Red    >= 10 breaches
    """
    losses = -actual_returns
    breaches = losses > var_estimates
    n_breaches = int(np.sum(breaches[~np.isnan(var_estimates)]))
    n_obs = int(np.sum(~np.isnan(var_estimates)))

    if n_breaches < 5:
        zone = "green"
    elif n_breaches < 10:
        zone = "yellow"
    else:
        zone = "red"

    return {
        "n_breaches": n_breaches,
        "n_observations": n_obs,
        "breach_rate_pct": round(100 * n_breaches / max(n_obs, 1), 2),
        "basel_zone": zone,
    }

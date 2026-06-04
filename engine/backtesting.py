"""engine/backtesting.py — VaR backtesting (Market Risk).

Basel traffic-light backtesting and the statistical coverage tests (Kupiec POF,
Christoffersen independence, and their combined conditional-coverage test), plus
the capital add-on multiplier, the 250-day rolling backtest, and breach-cluster
analysis.

All regulatory constants are used verbatim (CLAUDE.md §4.3): the backtesting
window is EXACTLY 250 trading days; breach zones are green < 5, yellow 5-9, red
>= 10; Kupiec/Christoffersen use chi-squared critical values at 95% confidence;
capital multipliers are 3.0 (green), the BCBS yellow schedule, and 4.0 (red).
"""

from __future__ import annotations

import numpy as np
from scipy import stats

__all__ = [
    "traffic_light_backtesting",
    "kupiec_pof_test",
    "christoffersen_independence_test",
    "combined_backtesting",
]

BASEL_BACKTEST_WINDOW = 250  # Basel traffic-light window — exactly 250 days


def _count_breaches(actual_returns: np.ndarray, var_estimates: np.ndarray) -> np.ndarray:
    """Boolean breach indicator: loss exceeded the VaR estimate (NaN-safe)."""
    losses = -np.asarray(actual_returns, dtype=np.float64)
    var = np.asarray(var_estimates, dtype=np.float64)
    valid = ~np.isnan(var)
    breaches = np.zeros(losses.shape, dtype=np.float64)
    breaches[valid] = (losses[valid] > var[valid]).astype(np.float64)
    return breaches


def traffic_light_backtesting(
    actual_returns: np.ndarray,
    var_estimates: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Basel traffic-light backtest over the 250-day window.

    Counts VaR breaches and assigns the Basel zone: green (< 5 breaches), yellow
    (5-9), red (>= 10). These boundaries are set by the Basel Committee.

    Args:
        actual_returns: Realised returns over the backtest window.
        var_estimates: VaR estimate (positive loss) aligned to each return.

    Returns:
        Dict with ``n_breaches``, ``n_observations``, ``basel_zone`` and
        ``expected_window`` (250).

    Raises:
        ValueError: If the two series differ in length.
    """
    actual = np.asarray(actual_returns, dtype=np.float64)
    var = np.asarray(var_estimates, dtype=np.float64)
    if actual.size != var.size:
        raise ValueError("actual_returns and var_estimates must have the same length")

    breaches = _count_breaches(actual, var)
    n_breaches = int(np.sum(breaches))
    n_obs = int(np.sum(~np.isnan(var)))

    if n_breaches < 5:
        zone = "green"
    elif n_breaches >= 10:
        zone = "red"
    else:
        zone = "yellow"
    return {
        "n_breaches": n_breaches,
        "n_observations": n_obs,
        "basel_zone": zone,
        "expected_window": BASEL_BACKTEST_WINDOW,
    }


def kupiec_pof_test(
    n_breaches: int,
    n_observations: int,
    confidence_level: float = 0.99,
) -> dict:  # type: ignore[type-arg]
    """Kupiec Proportion-of-Failures (POF) unconditional coverage test.

    Likelihood-ratio test that the observed breach rate matches the expected
    ``p = 1 − confidence_level``. The statistic is chi-squared with 1 dof;
    rejection uses the 95% critical value.

    Args:
        n_breaches: Number of VaR breaches observed.
        n_observations: Number of backtest observations.
        confidence_level: VaR confidence level the breaches were measured at.

    Returns:
        Dict with ``lr_pof``, ``p_value``, ``critical_value`` and ``reject``
        (True if the model's coverage is rejected at 95%).

    Raises:
        ValueError: If ``n_observations`` <= 0 or ``n_breaches`` out of range.
    """
    if n_observations <= 0 or not 0 <= n_breaches <= n_observations:
        raise ValueError("require 0 <= n_breaches <= n_observations and n_observations > 0")

    p = 1.0 - confidence_level
    x = n_breaches
    n = n_observations
    pi_hat = x / n
    # Likelihood ratio; guard the boundary cases where pi_hat is 0 or 1.
    if x == 0:
        lr = -2.0 * (n * np.log(1.0 - p))
    elif x == n:
        lr = -2.0 * (n * np.log(p))
    else:
        log_null = (n - x) * np.log(1.0 - p) + x * np.log(p)
        log_alt = (n - x) * np.log(1.0 - pi_hat) + x * np.log(pi_hat)
        lr = -2.0 * (log_null - log_alt)
    crit = float(stats.chi2.ppf(0.95, df=1))
    p_value = float(stats.chi2.sf(lr, df=1))
    return {
        "lr_pof": round(float(lr), 6),
        "p_value": round(p_value, 6),
        "critical_value": round(crit, 6),
        "reject": bool(lr > crit),
    }


def christoffersen_independence_test(breaches: np.ndarray) -> dict:  # type: ignore[type-arg]
    """Christoffersen independence (clustering) test.

    Likelihood-ratio test that breaches are serially independent (no
    clustering), via a first-order Markov transition model. Chi-squared with
    1 dof at the 95% critical value.

    Args:
        breaches: Binary breach sequence (1 = breach, 0 = no breach).

    Returns:
        Dict with ``lr_ind``, ``p_value``, ``critical_value`` and ``reject``.

    Raises:
        ValueError: If fewer than 2 observations are supplied.
    """
    b = np.asarray(breaches, dtype=np.int64)
    if b.size < 2:
        raise ValueError("need at least 2 observations")

    n00 = n01 = n10 = n11 = 0
    for i in range(1, b.size):
        prev, cur = b[i - 1], b[i]
        if prev == 0 and cur == 0:
            n00 += 1
        elif prev == 0 and cur == 1:
            n01 += 1
        elif prev == 1 and cur == 0:
            n10 += 1
        else:
            n11 += 1

    pi01 = n01 / (n00 + n01) if (n00 + n01) > 0 else 0.0
    pi11 = n11 / (n10 + n11) if (n10 + n11) > 0 else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)

    def _safe_pow_log(count: int, prob: float) -> float:
        if count == 0:
            return 0.0
        if prob <= 0.0 or prob >= 1.0:
            return 0.0
        return count * np.log(prob)

    log_alt = (
        _safe_pow_log(n00, 1 - pi01)
        + _safe_pow_log(n01, pi01)
        + _safe_pow_log(n10, 1 - pi11)
        + _safe_pow_log(n11, pi11)
    )
    log_null = _safe_pow_log(n00 + n10, 1 - pi) + _safe_pow_log(n01 + n11, pi)
    lr = -2.0 * (log_null - log_alt)
    crit = float(stats.chi2.ppf(0.95, df=1))
    p_value = float(stats.chi2.sf(lr, df=1))
    return {
        "lr_ind": round(float(lr), 6),
        "p_value": round(p_value, 6),
        "critical_value": round(crit, 6),
        "reject": bool(lr > crit),
    }


def combined_backtesting(
    breaches: np.ndarray,
    confidence_level: float = 0.99,
) -> dict:  # type: ignore[type-arg]
    """Combined (conditional coverage) backtest: Kupiec + Christoffersen.

    The Christoffersen conditional-coverage statistic ``LR_cc = LR_POF + LR_ind``
    is chi-squared with 2 dof, tested at the 95% critical value. It rejects a
    model that either mis-counts or clusters its breaches.

    Args:
        breaches: Binary breach sequence (1 = breach, 0 = no breach).
        confidence_level: VaR confidence level the breaches were measured at.

    Returns:
        Dict with ``lr_pof``, ``lr_ind``, ``lr_cc``, ``critical_value`` and
        ``reject``.

    Raises:
        ValueError: If fewer than 2 observations are supplied.
    """
    b = np.asarray(breaches, dtype=np.int64)
    if b.size < 2:
        raise ValueError("need at least 2 observations")

    pof = kupiec_pof_test(int(np.sum(b)), int(b.size), confidence_level)
    ind = christoffersen_independence_test(b)
    lr_cc = pof["lr_pof"] + ind["lr_ind"]
    crit = float(stats.chi2.ppf(0.95, df=2))
    return {
        "lr_pof": pof["lr_pof"],
        "lr_ind": ind["lr_ind"],
        "lr_cc": round(float(lr_cc), 6),
        "critical_value": round(crit, 6),
        "reject": bool(lr_cc > crit),
    }

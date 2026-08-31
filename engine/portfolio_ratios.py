"""engine/portfolio_ratios.py — Risk-adjusted performance ratios.

Implements the Risk-Adjusted Performance sub-domain of Portfolio Analytics:
Sharpe, Sortino, Calmar, Information, Treynor, Jensen's Alpha, Omega and the
Tail/Ulcer measures plus the closely-related drawdown-derived ratios.

Numba rules (CLAUDE.md §3.1) are honoured: @njit kernels are stateless, take
only float64 arrays / scalars, never import internally, and return NumPy
arrays. Public wrappers convert results to Python types.

Conventions:
  * ``returns`` are per-period simple returns (fractions, not percent).
  * ``risk_free`` and ``target`` are expressed per the same period as returns.
  * ``periods_per_year`` controls annualisation (252 daily, 12 monthly, 1 none).
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "sharpe_ratio",
    "sortino_ratio",
    "calmar_ratio",
    "information_ratio",
    "treynor_ratio",
    "jensens_alpha",
    "omega_ratio",
    "tail_ratio",
    "ulcer_index",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _mean_std(x: np.ndarray) -> np.ndarray:
    """Sample mean and population standard deviation of ``x``.

    Returns a 2-element float64 array ``[mean, std]`` (RULE 5: arrays only).
    """
    n = x.shape[0]
    s = 0.0
    for i in range(n):
        s += x[i]
    mean = s / n if n > 0 else 0.0
    var_acc = 0.0
    for i in range(n):
        d = x[i] - mean
        var_acc += d * d
    std = np.sqrt(var_acc / n) if n > 0 else 0.0
    out = np.empty(2, dtype=np.float64)
    out[0] = mean
    out[1] = std
    return out


@njit(cache=True)
def _downside_deviation(x: np.ndarray, target: float) -> float:
    """Downside deviation of ``x`` relative to ``target`` (RMS of shortfalls)."""
    n = x.shape[0]
    acc = 0.0
    for i in range(n):
        d = x[i] - target
        if d < 0.0:
            acc += d * d
    return float(np.sqrt(acc / n)) if n > 0 else 0.0


@njit(cache=True)
def _ulcer_index_kernel(equity: np.ndarray) -> float:
    """Ulcer Index: RMS of percentage drawdowns from the running peak."""
    n = equity.shape[0]
    if n == 0:
        return 0.0
    peak = equity[0]
    acc = 0.0
    for i in range(n):
        if equity[i] > peak:
            peak = equity[i]
        if peak > 0.0:
            dd = (equity[i] - peak) / peak * 100.0
        else:
            dd = 0.0
        acc += dd * dd
    return float(np.sqrt(acc / n))


# ── Public functions ──────────────────────────────────────────────────────────


def sharpe_ratio(
    returns: np.ndarray,
    risk_free: float = 0.0,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Annualised Sharpe ratio.

    Mean excess return divided by return volatility, annualised by
    ``sqrt(periods_per_year)``.

    Volatility is the population standard deviation (divide by n) of
    per-period excess returns, not the n-1 sample standard deviation.

    Args:
        returns: 1-D array of per-period simple returns.
        risk_free: Per-period risk-free rate (same period as returns).
        periods_per_year: Annualisation factor (252 daily, 12 monthly).

    Returns:
        Dict with ``sharpe`` (annualised), ``sharpe_period`` (un-annualised),
        ``mean_excess`` and ``volatility``.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size == 0:
        raise ValueError("returns must be non-empty")

    excess = r - risk_free
    stats_arr = _mean_std(excess)
    mean_excess = float(stats_arr[0])
    vol = float(stats_arr[1])
    sharpe_period = mean_excess / vol if vol > 0.0 else 0.0
    sharpe = sharpe_period * np.sqrt(periods_per_year)
    return {
        "sharpe": round(float(sharpe), 8),
        "sharpe_period": round(float(sharpe_period), 8),
        "mean_excess": round(mean_excess, 10),
        "volatility": round(vol, 10),
        "periods_per_year": periods_per_year,
    }


def sortino_ratio(
    returns: np.ndarray,
    risk_free: float = 0.0,
    target: float = 0.0,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Annualised Sortino ratio.

    Like Sharpe but penalises only downside deviation below ``target``, so
    upside volatility is not treated as risk.

    The numerator's excess return is measured against ``risk_free`` while
    the downside-deviation denominator measures shortfalls of the raw (not
    risk-free-adjusted) returns below the separate ``target``, so when
    ``target != risk_free`` the two are distinct reference rates by
    construction.

    Args:
        returns: 1-D array of per-period simple returns.
        risk_free: Per-period risk-free rate subtracted from returns.
        target: Minimum acceptable per-period return for downside deviation.
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``sortino`` (annualised), ``sortino_period``,
        ``mean_excess`` and ``downside_deviation``.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size == 0:
        raise ValueError("returns must be non-empty")

    excess = r - risk_free
    mean_excess = float(np.mean(excess))
    dd = _downside_deviation(r, target)
    sortino_period = mean_excess / dd if dd > 0.0 else 0.0
    sortino = sortino_period * np.sqrt(periods_per_year)
    return {
        "sortino": round(float(sortino), 8),
        "sortino_period": round(float(sortino_period), 8),
        "mean_excess": round(mean_excess, 10),
        "downside_deviation": round(float(dd), 10),
        "periods_per_year": periods_per_year,
    }


def calmar_ratio(
    returns: np.ndarray,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Calmar ratio — annualised return over maximum drawdown.

    Args:
        returns: 1-D array of per-period simple returns.
        periods_per_year: Annualisation factor for the CAGR numerator.

    Returns:
        Dict with ``calmar``, ``annualised_return`` and ``max_drawdown``
        (positive fraction).

    Raises:
        ValueError: If ``returns`` is empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size == 0:
        raise ValueError("returns must be non-empty")

    equity = np.cumprod(1.0 + r)
    n = r.size
    total_growth = float(equity[-1])
    # Compound annual growth rate.
    ann_return = total_growth ** (periods_per_year / n) - 1.0 if total_growth > 0.0 else -1.0
    running_max = np.maximum.accumulate(equity)
    drawdowns = (equity - running_max) / running_max
    max_dd = float(-np.min(drawdowns))  # positive magnitude
    calmar = ann_return / max_dd if max_dd > 0.0 else 0.0
    return {
        "calmar": round(float(calmar), 8),
        "annualised_return": round(float(ann_return), 8),
        "max_drawdown": round(max_dd, 8),
        "periods_per_year": periods_per_year,
    }


def information_ratio(
    returns: np.ndarray,
    benchmark_returns: np.ndarray,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Information ratio — active return over tracking error.

    Args:
        returns: 1-D array of portfolio per-period returns.
        benchmark_returns: 1-D array of benchmark per-period returns.
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``information_ratio`` (annualised), ``active_return`` and
        ``tracking_error`` (per period).

    Raises:
        ValueError: If the arrays differ in length or are empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    b = np.asarray(benchmark_returns, dtype=np.float64)
    if r.size == 0 or r.size != b.size:
        raise ValueError("returns and benchmark_returns must be non-empty and equal length")

    active = r - b
    stats_arr = _mean_std(active)
    mean_active = float(stats_arr[0])
    te = float(stats_arr[1])
    ir_period = mean_active / te if te > 0.0 else 0.0
    ir = ir_period * np.sqrt(periods_per_year)
    return {
        "information_ratio": round(float(ir), 8),
        "active_return": round(mean_active, 10),
        "tracking_error": round(te, 10),
        "periods_per_year": periods_per_year,
    }


def treynor_ratio(
    returns: np.ndarray,
    benchmark_returns: np.ndarray,
    risk_free: float = 0.0,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Treynor ratio — annualised excess return per unit of systematic risk (beta).

    Args:
        returns: 1-D array of portfolio per-period returns.
        benchmark_returns: 1-D array of market per-period returns.
        risk_free: Per-period risk-free rate.
        periods_per_year: Annualisation factor for the numerator.

    Returns:
        Dict with ``treynor``, ``beta`` and ``mean_excess`` (per period).

    Raises:
        ValueError: If the arrays differ in length or are empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    b = np.asarray(benchmark_returns, dtype=np.float64)
    if r.size == 0 or r.size != b.size:
        raise ValueError("returns and benchmark_returns must be non-empty and equal length")

    cov = float(np.cov(r, b, bias=True)[0, 1])
    var_b = float(np.var(b))
    beta = cov / var_b if var_b > 0.0 else 0.0
    mean_excess = float(np.mean(r - risk_free))
    treynor = (mean_excess * periods_per_year) / beta if beta != 0.0 else 0.0
    return {
        "treynor": round(float(treynor), 8),
        "beta": round(beta, 8),
        "mean_excess": round(mean_excess, 10),
        "periods_per_year": periods_per_year,
    }


def jensens_alpha(
    returns: np.ndarray,
    benchmark_returns: np.ndarray,
    risk_free: float = 0.0,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Jensen's alpha from the CAPM single-factor regression.

    ``alpha = mean(r - rf) - beta * mean(b - rf)`` per period; annualised by
    multiplication by ``periods_per_year``.

    Args:
        returns: 1-D array of portfolio per-period returns.
        benchmark_returns: 1-D array of market per-period returns.
        risk_free: Per-period risk-free rate.
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``alpha`` (annualised), ``alpha_period`` and ``beta``.

    Raises:
        ValueError: If the arrays differ in length or are empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    b = np.asarray(benchmark_returns, dtype=np.float64)
    if r.size == 0 or r.size != b.size:
        raise ValueError("returns and benchmark_returns must be non-empty and equal length")

    excess_r = r - risk_free
    excess_b = b - risk_free
    cov = float(np.cov(excess_r, excess_b, bias=True)[0, 1])
    var_b = float(np.var(excess_b))
    beta = cov / var_b if var_b > 0.0 else 0.0
    alpha_period = float(np.mean(excess_r) - beta * np.mean(excess_b))
    return {
        "alpha": round(alpha_period * periods_per_year, 8),
        "alpha_period": round(alpha_period, 10),
        "beta": round(beta, 8),
        "periods_per_year": periods_per_year,
    }


def omega_ratio(
    returns: np.ndarray,
    threshold: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Omega ratio — probability-weighted gains over losses about a threshold.

    ``Omega = sum(max(r - threshold, 0)) / sum(max(threshold - r, 0))``.

    Args:
        returns: 1-D array of per-period returns.
        threshold: Per-period return threshold separating gains from losses.

    Returns:
        Dict with ``omega``, ``gain`` (sum of excess above threshold) and
        ``loss`` (sum of shortfall below threshold).

    Raises:
        ValueError: If ``returns`` is empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size == 0:
        raise ValueError("returns must be non-empty")

    diff = r - threshold
    gain = float(np.sum(np.where(diff > 0.0, diff, 0.0)))
    loss = float(np.sum(np.where(diff < 0.0, -diff, 0.0)))
    omega = gain / loss if loss > 0.0 else float("inf")
    return {
        "omega": round(float(omega), 8) if np.isfinite(omega) else float("inf"),
        "gain": round(gain, 10),
        "loss": round(loss, 10),
        "threshold": threshold,
    }


def tail_ratio(
    returns: np.ndarray,
    tail: float = 0.05,
) -> dict:  # type: ignore[type-arg]
    """Tail ratio — magnitude of the right tail relative to the left tail.

    ``|quantile(1 - tail)| / |quantile(tail)|``. A value above 1 indicates the
    right (gain) tail is larger than the left (loss) tail.

    Args:
        returns: 1-D array of per-period returns.
        tail: Tail probability in (0, 0.5), e.g. 0.05 for the 5%/95% tails.

    Returns:
        Dict with ``tail_ratio``, ``right_tail`` and ``left_tail``.

    Raises:
        ValueError: If ``returns`` is empty or ``tail`` is not in (0, 0.5).
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size == 0:
        raise ValueError("returns must be non-empty")
    if not 0.0 < tail < 0.5:
        raise ValueError("tail must be in (0, 0.5)")

    right = float(np.quantile(r, 1.0 - tail))
    left = float(np.quantile(r, tail))
    ratio = abs(right) / abs(left) if left != 0.0 else float("inf")
    return {
        "tail_ratio": round(float(ratio), 8) if np.isfinite(ratio) else float("inf"),
        "right_tail": round(right, 10),
        "left_tail": round(left, 10),
        "tail": tail,
    }


def ulcer_index(
    returns: np.ndarray,
    is_equity_curve: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Ulcer Index — root-mean-square of percentage drawdowns from peak.

    A depth-and-duration-sensitive risk measure: deeper, longer drawdowns are
    penalised quadratically.

    Args:
        returns: 1-D array of per-period returns, or an equity curve if
            ``is_equity_curve`` is True.
        is_equity_curve: If True, ``returns`` is treated as a value series
            directly rather than being compounded.

    Returns:
        Dict with ``ulcer_index`` (in percentage points) and ``n_obs``.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size == 0:
        raise ValueError("returns must be non-empty")

    equity = r if is_equity_curve else np.cumprod(1.0 + r)
    ui = _ulcer_index_kernel(np.ascontiguousarray(equity))
    return {
        "ulcer_index": round(float(ui), 8),
        "n_obs": int(r.size),
    }

"""engine/portfolio_drawdown.py — Drawdown analytics.

Implements the drawdown sub-domain of Portfolio Analytics: maximum drawdown,
average drawdown, drawdown duration, and Conditional Drawdown at Risk (CDaR).

Numba rules (CLAUDE.md §3.1): @njit kernels are stateless, take only float64
arrays / scalars, never import internally, and return NumPy arrays. The peak /
trough recursion over an equity curve is exactly the loop-carried dependency
Numba excels at, so the drawdown series is computed in a JIT kernel.

Conventions:
  * ``returns`` are per-period simple returns unless ``is_equity_curve``.
  * Drawdowns are reported as positive fractions in [0, 1].
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "maximum_drawdown",
    "average_drawdown",
    "drawdown_duration",
    "conditional_drawdown_at_risk",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _drawdown_series(equity: np.ndarray) -> np.ndarray:
    """Per-period drawdown (negative fraction) from the running peak."""
    n = equity.shape[0]
    out = np.empty(n, dtype=np.float64)
    peak = equity[0]
    for i in range(n):
        if equity[i] > peak:
            peak = equity[i]
        if peak > 0.0:
            out[i] = (equity[i] - peak) / peak
        else:
            out[i] = 0.0
    return out


@njit(cache=True)
def _max_drawdown_with_dates(equity: np.ndarray) -> np.ndarray:
    """Maximum drawdown plus peak/trough indices.

    Returns a 3-element float64 array ``[max_dd, peak_idx, trough_idx]`` where
    ``max_dd`` is a positive fraction (RULE 5: arrays only).
    """
    n = equity.shape[0]
    peak = equity[0]
    peak_idx = 0
    max_dd = 0.0
    best_peak_idx = 0
    best_trough_idx = 0
    for i in range(n):
        if equity[i] > peak:
            peak = equity[i]
            peak_idx = i
        dd = (peak - equity[i]) / peak if peak > 0.0 else 0.0
        if dd > max_dd:
            max_dd = dd
            best_peak_idx = peak_idx
            best_trough_idx = i
    out = np.empty(3, dtype=np.float64)
    out[0] = max_dd
    out[1] = float(best_peak_idx)
    out[2] = float(best_trough_idx)
    return out


@njit(cache=True)
def _max_drawdown_duration(equity: np.ndarray) -> np.ndarray:
    """Longest underwater run length and the current underwater run length.

    Returns ``[max_duration, current_duration]`` in periods (RULE 5).
    """
    n = equity.shape[0]
    peak = equity[0]
    max_dur = 0.0
    cur = 0.0
    for i in range(n):
        if equity[i] >= peak:
            peak = equity[i]
            cur = 0.0
        else:
            cur += 1.0
            if cur > max_dur:
                max_dur = cur
    out = np.empty(2, dtype=np.float64)
    out[0] = max_dur
    out[1] = cur
    return out


# ── Public helpers ────────────────────────────────────────────────────────────


def _to_equity(returns: np.ndarray, is_equity_curve: bool) -> np.ndarray:
    """Build a contiguous equity curve from returns or pass through."""
    r = np.asarray(returns, dtype=np.float64)
    if r.size == 0:
        raise ValueError("returns must be non-empty")
    equity = r if is_equity_curve else np.cumprod(1.0 + r)
    return np.ascontiguousarray(equity, dtype=np.float64)


# ── Public functions ──────────────────────────────────────────────────────────


def maximum_drawdown(
    returns: np.ndarray,
    is_equity_curve: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Maximum drawdown — largest peak-to-trough decline.

    Args:
        returns: 1-D array of per-period returns, or an equity curve.
        is_equity_curve: If True, ``returns`` is a value series directly.

    Returns:
        Dict with ``max_drawdown`` (positive fraction in [0, 1]),
        ``peak_index`` and ``trough_index``.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    equity = _to_equity(returns, is_equity_curve)
    res = _max_drawdown_with_dates(equity)
    return {
        "max_drawdown": round(float(res[0]), 8),
        "peak_index": int(res[1]),
        "trough_index": int(res[2]),
        "n_obs": int(equity.size),
    }


def average_drawdown(
    returns: np.ndarray,
    is_equity_curve: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Average drawdown — mean of the drawdown series magnitude.

    Args:
        returns: 1-D array of per-period returns, or an equity curve.
        is_equity_curve: If True, ``returns`` is a value series directly.

    Returns:
        Dict with ``average_drawdown`` (positive fraction) and ``max_drawdown``.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    equity = _to_equity(returns, is_equity_curve)
    dd = _drawdown_series(equity)
    avg = float(-np.mean(dd))
    return {
        "average_drawdown": round(avg, 8),
        "max_drawdown": round(float(-np.min(dd)), 8),
        "n_obs": int(equity.size),
    }


def drawdown_duration(
    returns: np.ndarray,
    is_equity_curve: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Drawdown duration — longest and current underwater run lengths.

    Counts consecutive periods spent below the prior peak.

    Args:
        returns: 1-D array of per-period returns, or an equity curve.
        is_equity_curve: If True, ``returns`` is a value series directly.

    Returns:
        Dict with ``max_duration`` and ``current_duration`` in periods.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    equity = _to_equity(returns, is_equity_curve)
    res = _max_drawdown_duration(equity)
    return {
        "max_duration": int(res[0]),
        "current_duration": int(res[1]),
        "n_obs": int(equity.size),
    }


def conditional_drawdown_at_risk(
    returns: np.ndarray,
    confidence_level: float = 0.95,
    is_equity_curve: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Conditional Drawdown at Risk (CDaR).

    The mean of the worst ``(1 - confidence_level)`` fraction of drawdowns —
    the drawdown analogue of Expected Shortfall (Chekhlov, Uryasev, Zabarankin).

    Args:
        returns: 1-D array of per-period returns, or an equity curve.
        confidence_level: CDaR confidence in [0.90, 0.9999].
        is_equity_curve: If True, ``returns`` is a value series directly.

    Returns:
        Dict with ``cdar`` (positive fraction), ``dar`` (drawdown-at-risk
        threshold) and ``confidence_level``.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    equity = _to_equity(returns, is_equity_curve)
    dd = -_drawdown_series(equity)  # positive drawdowns
    sorted_dd = np.sort(dd)  # ascending
    n = sorted_dd.size
    idx = int(np.floor(confidence_level * n))
    if idx > n - 1:
        idx = n - 1
    dar = float(sorted_dd[idx])
    tail = sorted_dd[idx:]
    cdar = float(np.mean(tail)) if tail.size > 0 else dar
    return {
        "cdar": round(cdar, 8),
        "dar": round(dar, 8),
        "confidence_level": confidence_level,
        "n_obs": int(n),
    }

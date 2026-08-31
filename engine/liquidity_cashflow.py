"""engine/liquidity_cashflow.py — contractual cash-flow ladders and gap analysis.

Builds maturity-bucketed cash-flow ladders and the derived liquidity gap /
funding tenor analytics. The cumulative-gap recursion over time buckets is a
genuine loop-carried dependency, so it is implemented as an @njit kernel
(CLAUDE.md §3.1): stateless, float64 arrays in/out, ``cache=True``.

Standard Basel maturity buckets used across pyvar:
    overnight, 1w, 2w, 1m, 3m, 6m, 1y, >1y
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "cash_flow_ladder_30_day",
    "cash_flow_ladder_1_year",
    "liquidity_gap_analysis",
    "funding_tenor_analysis",
]

# Day offsets for the 30-day daily ladder.
_BUCKETS_1Y = ["overnight", "1w", "2w", "1m", "3m", "6m", "1y", ">1y"]


@njit(cache=True)
def _cumulative_gap(inflows: np.ndarray, outflows: np.ndarray) -> np.ndarray:
    """Per-bucket net gap and cumulative gap from inflow/outflow arrays.

    Returns a 2-row float64 array: row 0 is the per-bucket net gap, row 1 is the
    running cumulative gap. The cumulative running sum is a loop-carried
    recursion — the canonical Numba use case (RULE 5: arrays only).
    """
    n = inflows.shape[0]
    out = np.empty((2, n), dtype=np.float64)
    running = 0.0
    for i in range(n):
        net = inflows[i] - outflows[i]
        running += net
        out[0, i] = net
        out[1, i] = running
    return out


def cash_flow_ladder_30_day(
    daily_inflows: np.ndarray,
    daily_outflows: np.ndarray,
    opening_balance: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """30-day daily contractual cash-flow ladder.

    Projects the daily net and cumulative liquidity position over a 30-day
    horizon. The minimum cumulative balance (including the opening balance) is
    the tightest liquidity point — if negative the institution faces a funding
    shortfall on that day.

    Args:
        daily_inflows: Length-30 array of daily contractual inflows.
        daily_outflows: Length-30 array of daily contractual outflows.
        opening_balance: Starting cash / HQLA balance at day 0.

    Returns:
        Dict with ``net_gap`` (per-day), ``cumulative_gap`` (per-day, including
        opening balance), ``min_cumulative`` and ``min_day``.

    Raises:
        ValueError: If arrays are not both length 30.
    """
    inflows = np.asarray(daily_inflows, dtype=np.float64)
    outflows = np.asarray(daily_outflows, dtype=np.float64)
    if inflows.shape[0] != 30 or outflows.shape[0] != 30:
        raise ValueError("30-day ladder requires length-30 inflow/outflow arrays")

    gap = _cumulative_gap(inflows, outflows)
    cumulative = gap[1] + opening_balance
    min_day = int(np.argmin(cumulative))
    return {
        "net_gap": [round(float(x), 2) for x in gap[0]],
        "cumulative_gap": [round(float(x), 2) for x in cumulative],
        "min_cumulative": round(float(cumulative[min_day]), 2),
        "min_day": min_day,
        "horizon_days": 30,
    }


def cash_flow_ladder_1_year(
    bucket_inflows: np.ndarray,
    bucket_outflows: np.ndarray,
    opening_balance: float = 0.0,
    buckets: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """One-year bucketed contractual cash-flow ladder.

    Aggregates inflows and outflows into the standard maturity buckets and
    computes the per-bucket and cumulative liquidity gap.

    Args:
        bucket_inflows: Inflow per maturity bucket (one entry per bucket).
        bucket_outflows: Outflow per maturity bucket.
        opening_balance: Starting balance carried into the first bucket.
        buckets: Optional bucket labels; defaults to the standard 8-bucket set.

    Returns:
        Dict with ``buckets``, ``net_gap``, ``cumulative_gap`` and
        ``min_cumulative``.

    Raises:
        ValueError: If array lengths differ or mismatch the bucket labels.
    """
    inflows = np.asarray(bucket_inflows, dtype=np.float64)
    outflows = np.asarray(bucket_outflows, dtype=np.float64)
    if buckets is None:
        buckets = _BUCKETS_1Y
    if inflows.shape != outflows.shape:
        raise ValueError("bucket_inflows and bucket_outflows must have equal length")
    if inflows.shape[0] != len(buckets):
        raise ValueError("array length must match number of buckets")

    gap = _cumulative_gap(inflows, outflows)
    cumulative = gap[1] + opening_balance
    return {
        "buckets": list(buckets),
        "net_gap": [round(float(x), 2) for x in gap[0]],
        "cumulative_gap": [round(float(x), 2) for x in cumulative],
        "min_cumulative": round(float(np.min(cumulative)), 2),
    }


def liquidity_gap_analysis(
    asset_maturities: np.ndarray,
    liability_maturities: np.ndarray,
    buckets: list[str] | None = None,
    opening_balance: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Maturity-bucket liquidity gap (assets vs liabilities).

    Computes the structural maturity mismatch: ``gap_i = assets_i -
    liabilities_i`` per bucket, plus the cumulative gap. A positive cumulative
    gap means more assets than liabilities mature by that point (a funding
    surplus); a negative gap signals a refinancing need.

    Like the two cash-flow-ladder functions above, an optional opening balance
    is added to every cumulative-gap entry — the starting cash / HQLA position
    carried into the first bucket. It defaults to 0.0, so existing callers see
    no change in behaviour.

    Args:
        asset_maturities: Asset cash inflows maturing in each bucket.
        liability_maturities: Liability cash outflows maturing in each bucket.
        buckets: Optional bucket labels; defaults to the standard 8-bucket set.
        opening_balance: Starting cash / HQLA balance carried into the first
            bucket. Added to every cumulative-gap entry. Defaults to 0.0.

    Returns:
        Dict with ``buckets``, ``periodic_gap``, ``cumulative_gap`` (including
        ``opening_balance``) and the ``gap_ratio`` (assets / liabilities) per
        bucket.

    Raises:
        ValueError: If lengths differ or mismatch the bucket labels.
    """
    assets = np.asarray(asset_maturities, dtype=np.float64)
    liabilities = np.asarray(liability_maturities, dtype=np.float64)
    if buckets is None:
        buckets = _BUCKETS_1Y
    if assets.shape != liabilities.shape:
        raise ValueError("asset and liability arrays must have equal length")
    if assets.shape[0] != len(buckets):
        raise ValueError("array length must match number of buckets")

    gap = _cumulative_gap(assets, liabilities)
    cumulative = gap[1] + opening_balance
    ratio = np.where(
        liabilities != 0.0, assets / np.where(liabilities != 0.0, liabilities, 1.0), np.inf
    )
    return {
        "buckets": list(buckets),
        "periodic_gap": [round(float(x), 2) for x in gap[0]],
        "cumulative_gap": [round(float(x), 2) for x in cumulative],
        "gap_ratio": [round(float(x), 6) if np.isfinite(x) else None for x in ratio],
    }


def funding_tenor_analysis(
    funding_amounts: np.ndarray,
    tenors_days: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Weighted-average funding tenor and short-term reliance.

    Computes the amount-weighted average tenor of the funding base and the
    proportion of funding maturing within 90 days — a core ILAAP structural
    metric (longer WAL == more stable funding).

    Args:
        funding_amounts: Outstanding amount of each funding tranche.
        tenors_days: Residual tenor in days for each tranche.

    Returns:
        Dict with ``weighted_avg_tenor_days``, ``short_term_ratio`` (<= 90d) and
        ``total_funding``.

    Raises:
        ValueError: If lengths differ, total funding is zero, or tenors are
            negative.
    """
    amounts = np.asarray(funding_amounts, dtype=np.float64)
    tenors = np.asarray(tenors_days, dtype=np.float64)
    if amounts.shape != tenors.shape:
        raise ValueError("funding_amounts and tenors_days must have equal length")
    if np.any(tenors < 0.0):
        raise ValueError("tenors_days must be non-negative")
    total = float(np.sum(amounts))
    if total == 0:
        raise ValueError("total funding must be positive")

    wat = float(np.sum(amounts * tenors) / total)
    short_term = float(np.sum(amounts[tenors <= 90.0]) / total)
    return {
        "weighted_avg_tenor_days": round(wat, 4),
        "short_term_ratio": round(short_term, 6),
        "total_funding": round(total, 2),
    }

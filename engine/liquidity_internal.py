"""engine/liquidity_internal.py — internal liquidity metrics and analytics.

Covers the ILAAP internal-metrics and advanced-analytics sub-domains: the
internal liquidity metric, risk-appetite thresholds, early-warning indicators,
central-bank facility eligibility, contingent liquidity risk, scorecard
aggregation, deposit stability classification, and the cross-currency liquidity
bridge.

Aggregation / scoring wrappers (no heavy array math) per CLAUDE.md §3.1.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "ilaap_internal_liquidity_metric",
    "liquidity_risk_appetite_threshold",
    "early_warning_indicator_liquidity",
    "central_bank_facility_eligibility",
    "contingent_liquidity_risk",
    "liquidity_scorecard_aggregation",
    "deposit_stability_classification",
    "cross_currency_liquidity_bridge",
]


def ilaap_internal_liquidity_metric(
    counterbalancing_capacity: float,
    stressed_net_outflow: float,
    survival_days: float,
    minimum_survival_days: float = 90.0,
) -> dict:  # type: ignore[type-arg]
    """ILAAP internal liquidity adequacy metric.

    Combines the institution's own counterbalancing-capacity coverage ratio
    (CBC / stressed outflow) with the survival-horizon adequacy versus the
    internal minimum (commonly 90 days). Both must hold for internal adequacy.

    Args:
        counterbalancing_capacity: Total monetisable liquidity (CBC).
        stressed_net_outflow: Stressed net outflow over the horizon.
        survival_days: Modelled survival horizon in days.
        minimum_survival_days: Internal minimum survival target.

    Returns:
        Dict with ``coverage_ratio``, ``survival_days``, ``meets_survival`` and
        an overall ``adequate`` flag.

    Raises:
        ValueError: If the stressed outflow is non-positive.
    """
    if stressed_net_outflow <= 0:
        raise ValueError("stressed_net_outflow must be positive")
    coverage = counterbalancing_capacity / stressed_net_outflow
    meets_survival = survival_days >= minimum_survival_days
    return {
        "coverage_ratio": round(float(coverage), 6),
        "survival_days": round(float(survival_days), 2),
        "meets_survival": bool(meets_survival),
        "adequate": bool(coverage >= 1.0 and meets_survival),
    }


def liquidity_risk_appetite_threshold(
    metric_value: float,
    green_threshold: float,
    amber_threshold: float,
    higher_is_better: bool = True,
) -> dict:  # type: ignore[type-arg]
    """Map a liquidity metric to a RAG (red/amber/green) risk-appetite zone.

    For ``higher_is_better`` metrics (LCR, NSFR, survival days) green is at or
    above ``green_threshold`` and red below ``amber_threshold``. For
    lower-is-better metrics (e.g. funding concentration) the comparison inverts.

    Args:
        metric_value: Current metric value.
        green_threshold: Boundary for the green zone.
        amber_threshold: Boundary for the amber zone.
        higher_is_better: Direction of the metric.

    Returns:
        Dict with ``zone`` (``"green"``/``"amber"``/``"red"``) and ``breach``
        (True when red).

    Raises:
        ValueError: If thresholds are inconsistent with the direction.
    """
    if higher_is_better:
        if green_threshold < amber_threshold:
            raise ValueError("green_threshold must be >= amber_threshold when higher is better")
        if metric_value >= green_threshold:
            zone = "green"
        elif metric_value >= amber_threshold:
            zone = "amber"
        else:
            zone = "red"
    else:
        if green_threshold > amber_threshold:
            raise ValueError("green_threshold must be <= amber_threshold when lower is better")
        if metric_value <= green_threshold:
            zone = "green"
        elif metric_value <= amber_threshold:
            zone = "amber"
        else:
            zone = "red"
    return {"zone": zone, "breach": bool(zone == "red")}


def early_warning_indicator_liquidity(
    indicators: dict,
    thresholds: dict,
    directions: dict | None = None,
) -> dict:  # type: ignore[type-arg]
    """Liquidity early-warning indicator (EWI) dashboard.

    Evaluates each EWI against its threshold and a per-indicator direction
    (``"higher_breach"`` means a value above threshold is a warning, e.g. funding
    spread; ``"lower_breach"`` means below threshold is a warning, e.g. LCR). The
    aggregate signal escalates with the number of triggered indicators.

    Args:
        indicators: Mapping ``name -> current value``.
        thresholds: Mapping ``name -> threshold``.
        directions: Optional mapping ``name -> "higher_breach"|"lower_breach"``;
            defaults to ``"lower_breach"`` for all.

    Returns:
        Dict with ``triggered`` (list), ``num_triggered`` and ``signal``
        (``"normal"``/``"watch"``/``"alert"``).

    Raises:
        ValueError: If ``thresholds`` is empty.
    """
    if not thresholds:
        raise ValueError("thresholds must be non-empty")
    if directions is None:
        directions = {}
    triggered = []
    for name, thr in thresholds.items():
        val = indicators.get(name)
        if val is None:
            continue
        direction = directions.get(name, "lower_breach")
        if direction == "higher_breach" and val > thr:
            triggered.append(name)
        elif direction == "lower_breach" and val < thr:
            triggered.append(name)
    n = len(triggered)
    if n == 0:
        signal = "normal"
    elif n <= 2:
        signal = "watch"
    else:
        signal = "alert"
    return {"triggered": triggered, "num_triggered": n, "signal": signal}


def central_bank_facility_eligibility(
    asset_ratings: np.ndarray,
    min_rating: int,
    asset_values: np.ndarray,
    cb_haircuts: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Central-bank facility collateral eligibility and borrowing capacity.

    Filters assets meeting the central bank's minimum credit rating (encoded as
    an ordinal where higher = better) and computes the post-central-bank-haircut
    borrowing capacity from eligible assets.

    Args:
        asset_ratings: Ordinal credit rating per asset (higher = better).
        min_rating: Minimum ordinal rating accepted by the facility.
        asset_values: Market value per asset.
        cb_haircuts: Central-bank haircut per asset, each in [0, 1].

    Returns:
        Dict with ``eligible_count``, ``borrowing_capacity`` (post-haircut, from
        eligible assets only) and ``eligible_mask``.

    Raises:
        ValueError: If array lengths differ or haircuts lie outside [0, 1].
    """
    ratings = np.asarray(asset_ratings, dtype=np.float64)
    values = np.asarray(asset_values, dtype=np.float64)
    hc = np.asarray(cb_haircuts, dtype=np.float64)
    if not (ratings.shape == values.shape == hc.shape):
        raise ValueError("all arrays must have equal length")
    if np.any(hc < 0.0) or np.any(hc > 1.0):
        raise ValueError("cb_haircuts must lie in [0, 1]")

    eligible = ratings >= min_rating
    capacity = float(np.sum(values[eligible] * (1.0 - hc[eligible])))
    return {
        "eligible_count": int(np.sum(eligible)),
        "borrowing_capacity": round(capacity, 2),
        "eligible_mask": [bool(e) for e in eligible],
    }


def contingent_liquidity_risk(
    commitment_amounts: np.ndarray,
    draw_probabilities: np.ndarray,
    ccf: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Contingent liquidity risk from undrawn commitments and guarantees.

    Estimates the expected contingent outflow as ``commitment * draw_probability
    * credit-conversion-factor`` — the liquidity that off-balance-sheet
    commitments (undrawn lines, guarantees) could absorb in stress.

    Args:
        commitment_amounts: Notional of each undrawn commitment / guarantee.
        draw_probabilities: Probability of drawdown per commitment, in [0, 1].
        ccf: Optional credit conversion factor per commitment (default all 1.0).

    Returns:
        Dict with ``expected_contingent_outflow`` and ``max_contingent_outflow``
        (full drawdown at CCF).

    Raises:
        ValueError: If lengths differ or probabilities lie outside [0, 1].
    """
    amounts = np.asarray(commitment_amounts, dtype=np.float64)
    probs = np.asarray(draw_probabilities, dtype=np.float64)
    if amounts.shape != probs.shape:
        raise ValueError("commitment_amounts and draw_probabilities must have equal length")
    if np.any(probs < 0.0) or np.any(probs > 1.0):
        raise ValueError("draw_probabilities must lie in [0, 1]")
    conv = np.ones_like(amounts) if ccf is None else np.asarray(ccf, dtype=np.float64)
    if conv.shape != amounts.shape:
        raise ValueError("ccf must match commitment_amounts length")

    expected = float(np.sum(amounts * probs * conv))
    maximum = float(np.sum(amounts * conv))
    return {
        "expected_contingent_outflow": round(expected, 2),
        "max_contingent_outflow": round(maximum, 2),
    }


def liquidity_scorecard_aggregation(
    scores: np.ndarray,
    weights: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Weighted liquidity scorecard aggregation.

    Combines individual liquidity metric scores (each typically 0-100) into a
    single weighted composite score and maps it to a RAG rating.

    Args:
        scores: Individual component scores.
        weights: Weight per component (need not sum to 1; normalised).

    Returns:
        Dict with ``composite_score`` (weighted, normalised) and ``rating``
        (``"green"`` >= 70, ``"amber"`` >= 40, else ``"red"``).

    Raises:
        ValueError: If lengths differ or weights sum to zero.
    """
    s = np.asarray(scores, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    if s.shape != w.shape:
        raise ValueError("scores and weights must have equal length")
    total_w = float(np.sum(w))
    if total_w <= 0:
        raise ValueError("weights must sum to a positive value")

    composite = float(np.sum(s * w) / total_w)
    if composite >= 70.0:
        rating = "green"
    elif composite >= 40.0:
        rating = "amber"
    else:
        rating = "red"
    return {"composite_score": round(composite, 4), "rating": rating}


def deposit_stability_classification(
    deposit_features: np.ndarray,
    stable_threshold: float = 0.5,
) -> dict:  # type: ignore[type-arg]
    """Classify deposits as stable vs less-stable from a stability score.

    Each deposit carries a stability score in [0, 1] (e.g. derived from
    insurance coverage, transactional relationship, tenor). Deposits at or above
    ``stable_threshold`` are classified stable (lower LCR run-off), the rest
    less-stable.

    Args:
        deposit_features: Stability score per deposit, each in [0, 1].
        stable_threshold: Cut-off for the stable classification.

    Returns:
        Dict with ``num_stable``, ``num_less_stable`` and ``stable_fraction``.

    Raises:
        ValueError: If scores lie outside [0, 1] or the array is empty.
    """
    scores = np.asarray(deposit_features, dtype=np.float64)
    if scores.size == 0:
        raise ValueError("deposit_features must be non-empty")
    if np.any(scores < 0.0) or np.any(scores > 1.0):
        raise ValueError("deposit_features must lie in [0, 1]")

    stable = scores >= stable_threshold
    num_stable = int(np.sum(stable))
    return {
        "num_stable": num_stable,
        "num_less_stable": int(scores.size - num_stable),
        "stable_fraction": round(float(num_stable / scores.size), 6),
    }


def cross_currency_liquidity_bridge(
    shortfall_ccy: str,
    shortfall_amount: float,
    surplus_ccy: str,
    surplus_amount: float,
    fx_rate: float,
    swap_haircut: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Cross-currency liquidity bridge via FX swap.

    Sizes the FX swap needed to fund a shortfall in one currency using surplus
    in another. ``fx_rate`` converts one unit of the surplus currency into the
    shortfall currency; a ``swap_haircut`` reduces the usable surplus to reflect
    swap-market stress.

    Args:
        shortfall_ccy: Currency in deficit.
        shortfall_amount: Amount of the deficit (in shortfall_ccy).
        surplus_ccy: Currency with surplus to swap.
        surplus_amount: Available surplus (in surplus_ccy).
        fx_rate: Units of shortfall_ccy per unit of surplus_ccy.
        swap_haircut: Haircut on usable surplus, in [0, 1].

    Returns:
        Dict with ``coverable_amount`` (in shortfall_ccy), ``residual_shortfall``
        and a ``fully_bridged`` flag.

    Raises:
        ValueError: If amounts/rate are negative or haircut is out of range.
    """
    if shortfall_amount < 0 or surplus_amount < 0 or fx_rate <= 0:
        raise ValueError("amounts must be non-negative and fx_rate positive")
    if not 0.0 <= swap_haircut <= 1.0:
        raise ValueError("swap_haircut must lie in [0, 1]")

    usable_surplus = surplus_amount * (1.0 - swap_haircut)
    coverable = min(shortfall_amount, usable_surplus * fx_rate)
    residual = shortfall_amount - coverable
    return {
        "shortfall_ccy": shortfall_ccy,
        "surplus_ccy": surplus_ccy,
        "coverable_amount": round(float(coverable), 2),
        "residual_shortfall": round(float(residual), 2),
        "fully_bridged": bool(residual <= 1e-6),
    }

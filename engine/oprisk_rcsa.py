"""engine/oprisk_rcsa.py — RCSA, BEICF factors, and loss-data frameworks.

Implements the Risk & Control Self-Assessment (RCSA) sub-domain, the Business
Environment & Internal Control Factors (BEICF) used to adjust capital, the Basel
loss-event classification, and the internal / external loss-data collection
frameworks.

RCSA scoring uses the standard 5×5 heat-map scale (likelihood × impact -> 1-25).
These are scoring / aggregation wrappers — no heavy array math, so no @njit
kernels (CLAUDE.md §3.1 guidance).
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "rcsa_risk_identification",
    "rcsa_inherent_risk_scoring",
    "rcsa_residual_risk_scoring",
    "rcsa_control_effectiveness",
    "control_testing_effectiveness",
    "business_environment_factor_bei",
    "internal_control_factor_icf",
    "loss_event_classification_basel",
    "loss_data_collection_framework",
    "external_loss_data_integration",
]

# Basel II Level-1 operational risk event-type categories (BCBS 128, Annex 9).
_BASEL_EVENT_TYPES = (
    "internal_fraud",
    "external_fraud",
    "employment_practices",
    "clients_products_business",
    "damage_physical_assets",
    "business_disruption_systems",
    "execution_delivery_process",
)


def _rag_from_score(score: float) -> str:
    """Map a 1-25 RCSA score to a RAG band (green <=6, amber <=12, else red)."""
    if score <= 6.0:
        return "green"
    if score <= 12.0:
        return "amber"
    return "red"


def rcsa_risk_identification(
    risk_register: list[dict],  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """Validate and summarise an RCSA risk register.

    Checks each risk entry exposes a ``risk_id`` and a Basel ``category`` and
    summarises counts by category — the identification step of the RCSA cycle.

    This is validation plus a count-by-category aggregation, not a numeric
    formula; ``category`` is a per-entry dict key rather than a top-level
    function parameter.

    Args:
        risk_register: List of risk dicts, each with ``risk_id`` and
            ``category``.

    Returns:
        Dict with ``num_risks`` and ``by_category`` (category -> count).

    Raises:
        ValueError: If the register is empty or an entry lacks required keys, or
            uses an invalid Basel category.
    """
    if not risk_register:
        raise ValueError("risk_register must be non-empty")
    by_category: dict[str, int] = {}
    for entry in risk_register:
        if "risk_id" not in entry or "category" not in entry:
            raise ValueError("each risk must have 'risk_id' and 'category'")
        cat = entry["category"]
        if cat not in _BASEL_EVENT_TYPES:
            raise ValueError(f"invalid Basel category: {cat}")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {"num_risks": len(risk_register), "by_category": by_category}


def rcsa_inherent_risk_scoring(
    likelihood: int,
    impact: int,
) -> dict:  # type: ignore[type-arg]
    """Inherent risk score on the 5×5 RCSA heat map.

    Inherent risk is the gross exposure before controls: ``likelihood × impact``
    on the 1-5 scale, giving a 1-25 score mapped to a RAG band.

    Args:
        likelihood: Likelihood rating in 1-5.
        impact: Impact rating in 1-5.

    Returns:
        Dict with ``inherent_score`` (1-25) and ``rating`` (RAG band).

    Raises:
        ValueError: If either rating lies outside 1-5.
    """
    if not (1 <= likelihood <= 5 and 1 <= impact <= 5):
        raise ValueError("likelihood and impact must be in 1-5")
    score = likelihood * impact
    return {"inherent_score": int(score), "rating": _rag_from_score(score)}


def rcsa_residual_risk_scoring(
    inherent_score: float,
    control_effectiveness: float,
) -> dict:  # type: ignore[type-arg]
    """Residual risk after control mitigation.

    Residual = ``inherent × (1 − control_effectiveness)``: effective controls
    reduce the inherent score toward zero. The residual is mapped to a RAG band.

    Args:
        inherent_score: Inherent risk score (1-25).
        control_effectiveness: Control effectiveness in [0, 1] (1 = fully
            effective).

    Returns:
        Dict with ``residual_score`` and ``rating``.

    Raises:
        ValueError: If effectiveness lies outside [0, 1] or inherent is negative.
    """
    if inherent_score < 0:
        raise ValueError("inherent_score must be non-negative")
    if not 0.0 <= control_effectiveness <= 1.0:
        raise ValueError("control_effectiveness must lie in [0, 1]")
    residual = inherent_score * (1.0 - control_effectiveness)
    return {"residual_score": round(float(residual), 4), "rating": _rag_from_score(residual)}


def rcsa_control_effectiveness(
    design_score: float,
    operating_score: float,
    design_weight: float = 0.4,
) -> dict:  # type: ignore[type-arg]
    """Composite control effectiveness from design and operating effectiveness.

    Combines design effectiveness (is the control well-designed?) and operating
    effectiveness (does it operate as intended?) into a single [0, 1] score via a
    weighted average.

    Args:
        design_score: Design effectiveness in [0, 1].
        operating_score: Operating effectiveness in [0, 1].
        design_weight: Weight on design (operating weight = 1 − this).

    Returns:
        Dict with ``effectiveness`` and a ``rating``
        (``"effective"``/``"partial"``/``"ineffective"``).

    Raises:
        ValueError: If any input lies outside [0, 1].
    """
    if not all(0.0 <= x <= 1.0 for x in (design_score, operating_score, design_weight)):
        raise ValueError("scores and weight must lie in [0, 1]")
    eff = design_weight * design_score + (1.0 - design_weight) * operating_score
    if eff >= 0.8:
        rating = "effective"
    elif eff >= 0.5:
        rating = "partial"
    else:
        rating = "ineffective"
    return {"effectiveness": round(float(eff), 6), "rating": rating}


def control_testing_effectiveness(
    tests_passed: int,
    tests_total: int,
) -> dict:  # type: ignore[type-arg]
    """Control testing pass rate and effectiveness conclusion.

    The empirical pass rate from control testing samples; an exception rate above
    a supervisory tolerance (default >5% failures) downgrades the conclusion.

    Args:
        tests_passed: Number of control tests passed.
        tests_total: Total control tests performed (> 0).

    Returns:
        Dict with ``pass_rate``, ``exception_rate`` and ``conclusion``
        (``"effective"`` if pass_rate >= 0.95).

    Raises:
        ValueError: If totals are invalid (passed > total or total <= 0).
    """
    if tests_total <= 0 or tests_passed < 0 or tests_passed > tests_total:
        raise ValueError("require 0 <= tests_passed <= tests_total and total > 0")
    pass_rate = tests_passed / tests_total
    return {
        "pass_rate": round(float(pass_rate), 6),
        "exception_rate": round(float(1.0 - pass_rate), 6),
        "conclusion": "effective" if pass_rate >= 0.95 else "deficient",
    }


def business_environment_factor_bei(
    factor_scores: np.ndarray,
    baseline: float = 3.0,
    sensitivity: float = 0.05,
) -> dict:  # type: ignore[type-arg]
    """Business Environment Indicator (BEI) capital adjustment multiplier.

    Translates forward-looking business-environment factor scores (e.g. on a 1-5
    scale where higher = riskier) into a capital multiplier around 1.0: scores
    above the baseline increase capital, below decrease it. Part of the BEICF
    overlay permitted under the AMA.

    Args:
        factor_scores: Business-environment factor scores.
        baseline: Neutral score that maps to a 1.0 multiplier.
        sensitivity: Capital sensitivity per unit of average score deviation.

    Returns:
        Dict with ``avg_score``, ``bei_multiplier`` (floored at 0) and
        ``capital_impact`` (multiplier − 1).

    Raises:
        ValueError: If the score array is empty.
    """
    scores = np.asarray(factor_scores, dtype=np.float64)
    if scores.size == 0:
        raise ValueError("factor_scores must be non-empty")
    avg = float(np.mean(scores))
    multiplier = max(1.0 + sensitivity * (avg - baseline), 0.0)
    return {
        "avg_score": round(avg, 6),
        "bei_multiplier": round(float(multiplier), 6),
        "capital_impact": round(float(multiplier - 1.0), 6),
    }


def internal_control_factor_icf(
    control_scores: np.ndarray,
    baseline: float = 0.8,
    sensitivity: float = 0.25,
) -> dict:  # type: ignore[type-arg]
    """Internal Control Factor (ICF) capital adjustment multiplier.

    Stronger internal controls (higher average effectiveness in [0, 1]) reduce
    the capital multiplier below 1.0; weaker controls increase it. The BEICF
    counterpart to :func:`business_environment_factor_bei`.

    Args:
        control_scores: Control effectiveness scores in [0, 1].
        baseline: Neutral effectiveness that maps to a 1.0 multiplier.
        sensitivity: Capital sensitivity per unit of effectiveness deviation.

    Returns:
        Dict with ``avg_effectiveness``, ``icf_multiplier`` and
        ``capital_impact``.

    Raises:
        ValueError: If the array is empty or scores lie outside [0, 1].
    """
    scores = np.asarray(control_scores, dtype=np.float64)
    if scores.size == 0:
        raise ValueError("control_scores must be non-empty")
    if np.any(scores < 0.0) or np.any(scores > 1.0):
        raise ValueError("control_scores must lie in [0, 1]")
    avg = float(np.mean(scores))
    # Better controls (avg > baseline) reduce capital.
    multiplier = max(1.0 - sensitivity * (avg - baseline), 0.0)
    return {
        "avg_effectiveness": round(avg, 6),
        "icf_multiplier": round(float(multiplier), 6),
        "capital_impact": round(float(multiplier - 1.0), 6),
    }


def loss_event_classification_basel(
    event_type: str,
) -> dict:  # type: ignore[type-arg]
    """Classify a loss event into a Basel II Level-1 event-type category.

    Validates the event type against the seven Basel II Level-1 categories
    (BCBS 128, Annex 9) and returns its ordinal index for downstream bucketing.

    This is a membership lookup against the fixed seven Basel II categories, not
    a numeric equation.

    Args:
        event_type: Candidate Basel Level-1 event-type key.

    Returns:
        Dict with ``event_type``, ``valid`` and ``category_index`` (or -1).

    Raises:
        ValueError: If ``event_type`` is empty.
    """
    if not event_type:
        raise ValueError("event_type must be a non-empty string")
    valid = event_type in _BASEL_EVENT_TYPES
    idx = _BASEL_EVENT_TYPES.index(event_type) if valid else -1
    return {"event_type": event_type, "valid": valid, "category_index": idx}


def loss_data_collection_framework(
    loss_events: list[dict],  # type: ignore[type-arg]
    reporting_threshold: float,
) -> dict:  # type: ignore[type-arg]
    """Internal loss-data collection above a reporting threshold.

    Filters loss events at or above the firm's de-minimis reporting threshold and
    summarises count and total — the internal loss dataset feeding the LDA.

    Args:
        loss_events: List of events, each with a ``gross_amount`` key.
        reporting_threshold: De-minimis threshold (>= 0).

    Returns:
        Dict with ``reportable_count``, ``total_loss``, ``max_loss`` and
        ``below_threshold_count``.

    Raises:
        ValueError: If the threshold is negative or an event lacks
            ``gross_amount``.
    """
    if reporting_threshold < 0:
        raise ValueError("reporting_threshold must be non-negative")
    amounts = []
    below = 0
    for e in loss_events:
        if "gross_amount" not in e:
            raise ValueError("each loss event must have 'gross_amount'")
        amt = float(e["gross_amount"])
        if amt >= reporting_threshold:
            amounts.append(amt)
        else:
            below += 1
    arr = np.asarray(amounts, dtype=np.float64)
    return {
        "reportable_count": int(arr.size),
        "total_loss": round(float(np.sum(arr)), 2) if arr.size else 0.0,
        "max_loss": round(float(np.max(arr)), 2) if arr.size else 0.0,
        "below_threshold_count": below,
    }


def external_loss_data_integration(
    internal_losses: np.ndarray,
    external_losses: np.ndarray,
    scaling_factor: float,
) -> dict:  # type: ignore[type-arg]
    """Integrate scaled external loss data with internal data.

    External (consortium / public) losses are scaled to the firm's size by a
    ``scaling_factor`` (e.g. ratio of revenues) before being pooled with internal
    losses — the standard approach for enriching a sparse internal tail.

    Args:
        internal_losses: Internal loss amounts.
        external_losses: External loss amounts (pre-scaling).
        scaling_factor: Multiplicative size adjustment (> 0).

    Returns:
        Dict with ``combined_count``, ``combined_mean`` and
        ``external_weight`` (share of pooled count that is external).

    Raises:
        ValueError: If the scaling factor is non-positive.
    """
    if scaling_factor <= 0:
        raise ValueError("scaling_factor must be positive")
    internal = np.asarray(internal_losses, dtype=np.float64)
    external = np.asarray(external_losses, dtype=np.float64) * scaling_factor
    combined = np.concatenate([internal, external]) if internal.size or external.size else internal
    n = combined.size
    return {
        "combined_count": int(n),
        "combined_mean": round(float(np.mean(combined)), 4) if n else 0.0,
        "external_weight": round(float(external.size / n), 6) if n else 0.0,
    }

"""engine/oprisk_governance.py — OpRisk governance, reporting, and emerging risks.

Implements the governance / reporting sub-domain and the emerging-risk category
scorers: cyber, conduct, model, IT, third-party/vendor and business-continuity
risk, plus near-miss capture, root-cause analysis, risk-appetite statements,
escalation thresholds, the heat-map generator, regulatory-compliance scoring and
audit-finding scoring.

These are scoring / aggregation wrappers (5×5 heat-map scale, weighted indices)
with no heavy array math, so no @njit kernels are used (CLAUDE.md §3.1 guidance).
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "cyber_risk_loss_estimation",
    "conduct_risk_metric",
    "model_risk_assessment",
    "it_risk_scoring",
    "third_party_vendor_risk",
    "business_continuity_risk_score",
    "near_miss_capture_framework",
    "root_cause_analysis_template",
    "risk_appetite_statement_oprisk",
    "escalation_threshold_calculation",
    "oprisk_heat_map_generator",
    "regulatory_compliance_score",
    "audit_finding_risk_scorer",
]


def _rag_from_score(score: float) -> str:
    """Map a 1-25 heat-map score to a RAG band (green <=6, amber <=12, red)."""
    if score <= 6.0:
        return "green"
    if score <= 12.0:
        return "amber"
    return "red"


def cyber_risk_loss_estimation(
    records_exposed: float,
    cost_per_record: float,
    breach_probability: float,
    business_interruption_cost: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Estimate expected and worst-case cyber loss.

    Worst-case (given a breach) = ``records_exposed × cost_per_record +
    business_interruption_cost``; expected loss multiplies by the annual breach
    probability — a FAIR-style single-loss-expectancy estimate.

    Args:
        records_exposed: Number of data records at risk.
        cost_per_record: Cost per breached record (regulatory + remediation).
        breach_probability: Annual breach probability in [0, 1].
        business_interruption_cost: Additional BI cost given a breach.

    Returns:
        Dict with ``worst_case_loss``, ``expected_loss`` and
        ``breach_probability``.

    Raises:
        ValueError: If inputs are negative or probability is out of range.
    """
    if records_exposed < 0 or cost_per_record < 0 or business_interruption_cost < 0:
        raise ValueError("cost inputs must be non-negative")
    if not 0.0 <= breach_probability <= 1.0:
        raise ValueError("breach_probability must lie in [0, 1]")
    worst = records_exposed * cost_per_record + business_interruption_cost
    expected = worst * breach_probability
    return {
        "worst_case_loss": round(float(worst), 2),
        "expected_loss": round(float(expected), 2),
        "breach_probability": round(float(breach_probability), 6),
    }


def conduct_risk_metric(
    complaints: float,
    customers: float,
    redress_paid: float,
    revenue: float,
) -> dict:  # type: ignore[type-arg]
    """Composite conduct-risk metric from complaints and redress intensity.

    Combines the complaints-per-1000-customers rate and the redress-to-revenue
    ratio into a normalised 0-100 conduct-risk index (higher = worse) with a RAG
    band.

    Args:
        complaints: Number of upheld complaints in the period.
        customers: Active customer count (> 0).
        redress_paid: Total customer redress paid.
        revenue: Period revenue (> 0).

    Returns:
        Dict with ``complaints_per_1000``, ``redress_ratio``, ``conduct_index``
        and ``rating``.

    Raises:
        ValueError: If customers or revenue are non-positive, or inputs negative.
    """
    if customers <= 0 or revenue <= 0:
        raise ValueError("customers and revenue must be positive")
    if complaints < 0 or redress_paid < 0:
        raise ValueError("complaints and redress_paid must be non-negative")
    cpk = complaints / customers * 1000.0
    redress_ratio = redress_paid / revenue
    # Bounded composite index (caps each driver's contribution at 50).
    index = min(cpk, 50.0) + min(redress_ratio * 500.0, 50.0)
    if index <= 20.0:
        rating = "green"
    elif index <= 50.0:
        rating = "amber"
    else:
        rating = "red"
    return {
        "complaints_per_1000": round(float(cpk), 4),
        "redress_ratio": round(float(redress_ratio), 6),
        "conduct_index": round(float(index), 4),
        "rating": rating,
    }


def model_risk_assessment(
    materiality: int,
    complexity: int,
    validation_score: float,
) -> dict:  # type: ignore[type-arg]
    """Model risk tier from materiality, complexity, and validation quality.

    Combines model materiality and complexity (1-5 each) into an inherent score,
    then discounts by validation quality (in [0, 1]) to a residual model-risk
    tier (SR 11-7 / PRA SS1/23 style).

    Args:
        materiality: Model materiality rating 1-5.
        complexity: Model complexity rating 1-5.
        validation_score: Validation effectiveness in [0, 1] (1 = strong).

    Returns:
        Dict with ``inherent_score`` (1-25), ``residual_score`` and ``tier``
        (RAG band).

    Raises:
        ValueError: If ratings are out of 1-5 or validation outside [0, 1].
    """
    if not (1 <= materiality <= 5 and 1 <= complexity <= 5):
        raise ValueError("materiality and complexity must be in 1-5")
    if not 0.0 <= validation_score <= 1.0:
        raise ValueError("validation_score must lie in [0, 1]")
    inherent = materiality * complexity
    residual = inherent * (1.0 - validation_score)
    return {
        "inherent_score": int(inherent),
        "residual_score": round(float(residual), 4),
        "tier": _rag_from_score(residual),
    }


def it_risk_scoring(
    availability: float,
    incident_count: float,
    patch_compliance: float,
) -> dict:  # type: ignore[type-arg]
    """IT operational-risk score from availability, incidents and patching.

    Blends system availability (fraction), incident frequency and patch
    compliance (fraction) into a 0-100 IT-risk score (higher = worse) with a RAG
    band.

    Args:
        availability: System availability in [0, 1] (e.g. 0.999).
        incident_count: Number of IT incidents in the period (>= 0).
        patch_compliance: Patch compliance in [0, 1].

    Returns:
        Dict with ``it_risk_score`` and ``rating``.

    Raises:
        ValueError: If fractions are out of [0, 1] or incidents negative.
    """
    if not (0.0 <= availability <= 1.0 and 0.0 <= patch_compliance <= 1.0):
        raise ValueError("availability and patch_compliance must lie in [0, 1]")
    if incident_count < 0:
        raise ValueError("incident_count must be non-negative")
    # Each shortfall contributes to the risk score.
    score = (
        (1.0 - availability) * 40.0
        + min(incident_count, 20.0) * 2.0
        + (1.0 - patch_compliance) * 20.0
    )
    score = min(score, 100.0)
    if score <= 20.0:
        rating = "green"
    elif score <= 50.0:
        rating = "amber"
    else:
        rating = "red"
    return {"it_risk_score": round(float(score), 4), "rating": rating}


def third_party_vendor_risk(
    criticality: int,
    financial_health: float,
    concentration: float,
    substitutability: float,
) -> dict:  # type: ignore[type-arg]
    """Third-party / vendor risk score.

    Weighted index of vendor criticality (1-5), inverse financial health,
    concentration and inverse substitutability — all normalised to a 0-100 score
    (higher = worse).

    Args:
        criticality: Service criticality 1-5.
        financial_health: Vendor financial health in [0, 1] (1 = strong).
        concentration: Reliance concentration in [0, 1] (1 = sole supplier).
        substitutability: Ease of replacement in [0, 1] (1 = easily replaced).

    Returns:
        Dict with ``vendor_risk_score`` and ``rating``.

    Raises:
        ValueError: If ratings are out of range.
    """
    if not 1 <= criticality <= 5:
        raise ValueError("criticality must be in 1-5")
    for name, val in (
        ("financial_health", financial_health),
        ("concentration", concentration),
        ("substitutability", substitutability),
    ):
        if not 0.0 <= val <= 1.0:
            raise ValueError(f"{name} must lie in [0, 1]")
    score = (
        (criticality / 5.0) * 30.0
        + (1.0 - financial_health) * 30.0
        + concentration * 20.0
        + (1.0 - substitutability) * 20.0
    )
    if score <= 30.0:
        rating = "green"
    elif score <= 60.0:
        rating = "amber"
    else:
        rating = "red"
    return {"vendor_risk_score": round(float(score), 4), "rating": rating}


def business_continuity_risk_score(
    rto_hours: float,
    rpo_hours: float,
    max_tolerable_downtime: float,
    bcp_maturity: float,
) -> dict:  # type: ignore[type-arg]
    """Business-continuity risk from RTO versus tolerance and BCP maturity.

    Flags where the recovery time objective (RTO) exceeds the maximum tolerable
    downtime (MTD) and discounts the residual risk by BCP maturity. A breach of
    MTD is the dominant driver.

    Note:
        ``rpo_hours`` is accepted as an input (and range-validated) but does
        not currently affect the computed score — only ``rto_hours`` versus
        ``max_tolerable_downtime`` and ``bcp_maturity`` drive
        ``bc_risk_score``. See ``docs/p11-caveat-triage-plan.md`` (Tier 1)
        for the triage of this dead parameter.

    Args:
        rto_hours: Recovery time objective in hours.
        rpo_hours: Recovery point objective in hours. Validated but not
            currently used in the score computation (see Note above).
        max_tolerable_downtime: Maximum tolerable downtime in hours (> 0).
        bcp_maturity: BCP programme maturity in [0, 1].

    Returns:
        Dict with ``mtd_breach`` (RTO > MTD), ``bc_risk_score`` (0-100) and
        ``rating``.

    Raises:
        ValueError: If times are negative, MTD non-positive, or maturity out of
            range.
    """
    if rto_hours < 0 or rpo_hours < 0 or max_tolerable_downtime <= 0:
        raise ValueError("times must be non-negative and MTD positive")
    if not 0.0 <= bcp_maturity <= 1.0:
        raise ValueError("bcp_maturity must lie in [0, 1]")
    breach = rto_hours > max_tolerable_downtime
    coverage_gap = min(rto_hours / max_tolerable_downtime, 2.0) / 2.0  # 0..1
    raw = (50.0 if breach else 0.0) + coverage_gap * 50.0
    score = raw * (1.0 - 0.5 * bcp_maturity)  # mature BCP halves residual at most
    score = min(score, 100.0)
    return {
        "mtd_breach": bool(breach),
        "bc_risk_score": round(float(score), 4),
        "rating": "red" if score > 50.0 else ("amber" if score > 20.0 else "green"),
    }


def near_miss_capture_framework(
    events: list[dict],  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """Summarise captured near-miss events.

    A near-miss is an event with zero actual loss but a non-zero potential loss.
    Validates events and summarises the count and aggregate potential loss — a
    leading indicator of control weakness.

    Args:
        events: List of events, each with ``actual_loss`` and ``potential_loss``.

    Returns:
        Dict with ``near_miss_count``, ``total_potential_loss`` and
        ``actual_loss_count`` (events that were not near-misses).

    Raises:
        ValueError: If an event lacks the required keys.
    """
    near_misses = 0
    actual_events = 0
    potential = 0.0
    for e in events:
        if "actual_loss" not in e or "potential_loss" not in e:
            raise ValueError("each event needs 'actual_loss' and 'potential_loss'")
        if float(e["actual_loss"]) == 0.0 and float(e["potential_loss"]) > 0.0:
            near_misses += 1
            potential += float(e["potential_loss"])
        else:
            actual_events += 1
    return {
        "near_miss_count": near_misses,
        "total_potential_loss": round(potential, 2),
        "actual_loss_count": actual_events,
    }


def root_cause_analysis_template(
    causal_factors: dict,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """Aggregate root-cause contributions into a normalised attribution.

    Normalises the supplied causal-factor weights (e.g. people, process,
    systems, external) to sum to 1 and identifies the dominant root cause — the
    quantitative backbone of an RCA template.

    Args:
        causal_factors: Mapping ``factor -> contribution weight`` (>= 0).

    Returns:
        Dict with ``attribution`` (factor -> share), ``primary_cause`` and
        ``num_factors``.

    Raises:
        ValueError: If empty, any weight is negative, or weights sum to zero.
    """
    if not causal_factors:
        raise ValueError("causal_factors must be non-empty")
    if any(v < 0 for v in causal_factors.values()):
        raise ValueError("causal weights must be non-negative")
    total = float(sum(causal_factors.values()))
    if total <= 0:
        raise ValueError("causal weights must sum to a positive value")
    attribution = {k: round(float(v) / total, 6) for k, v in causal_factors.items()}
    primary = max(attribution, key=lambda k: attribution[k])
    return {
        "attribution": attribution,
        "primary_cause": primary,
        "num_factors": len(causal_factors),
    }


def risk_appetite_statement_oprisk(
    current_metric: float,
    appetite_limit: float,
    tolerance_limit: float,
    higher_is_worse: bool = True,
) -> dict:  # type: ignore[type-arg]
    """Assess an OpRisk metric against appetite and tolerance limits.

    Maps a metric to ``within_appetite`` / ``within_tolerance`` / ``breach``
    against a two-tier limit structure: appetite (the desired ceiling) and
    tolerance (the absolute maximum before escalation).

    Args:
        current_metric: Current value of the OpRisk metric.
        appetite_limit: Risk-appetite limit.
        tolerance_limit: Risk-tolerance (harder) limit.
        higher_is_worse: Whether higher values are adverse.

    Returns:
        Dict with ``status`` and ``utilisation`` (metric / tolerance for
        higher-is-worse metrics).

    Raises:
        ValueError: If limits are ordered inconsistently with the direction.
    """
    if higher_is_worse:
        if tolerance_limit < appetite_limit:
            raise ValueError("tolerance_limit must be >= appetite_limit when higher is worse")
        if current_metric <= appetite_limit:
            status = "within_appetite"
        elif current_metric <= tolerance_limit:
            status = "within_tolerance"
        else:
            status = "breach"
        utilisation = current_metric / tolerance_limit if tolerance_limit != 0 else 0.0
    else:
        if tolerance_limit > appetite_limit:
            raise ValueError("tolerance_limit must be <= appetite_limit when lower is worse")
        if current_metric >= appetite_limit:
            status = "within_appetite"
        elif current_metric >= tolerance_limit:
            status = "within_tolerance"
        else:
            status = "breach"
        utilisation = tolerance_limit / current_metric if current_metric != 0 else 0.0
    return {"status": status, "utilisation": round(float(utilisation), 6)}


def escalation_threshold_calculation(
    loss_amount: float,
    thresholds: dict,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """Determine the escalation level for a loss against tiered thresholds.

    Maps a loss amount to the highest governance tier whose threshold it meets or
    exceeds (e.g. ``{"team": 1e3, "head": 1e4, "exco": 1e5, "board": 1e6}``).

    Args:
        loss_amount: Loss amount to route (>= 0).
        thresholds: Mapping ``level -> minimum amount`` for that level.

    Returns:
        Dict with ``escalation_level`` (highest triggered, or ``None``) and the
        triggered ``threshold``.

    Raises:
        ValueError: If thresholds are empty or the loss is negative.
    """
    if not thresholds:
        raise ValueError("thresholds must be non-empty")
    if loss_amount < 0:
        raise ValueError("loss_amount must be non-negative")
    triggered = {lvl: thr for lvl, thr in thresholds.items() if loss_amount >= thr}
    if not triggered:
        return {"escalation_level": None, "threshold": 0.0}
    level = max(triggered, key=lambda k: triggered[k])
    return {"escalation_level": level, "threshold": round(float(triggered[level]), 2)}


def oprisk_heat_map_generator(
    likelihoods: np.ndarray,
    impacts: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Generate a 5×5 OpRisk heat-map distribution.

    Buckets each (likelihood, impact) risk into the 5×5 grid and computes the
    score (likelihood × impact) and RAG band for each, plus a count matrix of
    risks per cell.

    Args:
        likelihoods: Likelihood rating per risk (1-5).
        impacts: Impact rating per risk (1-5).

    Returns:
        Dict with ``scores`` (per risk), ``ratings`` (per risk) and ``matrix``
        (5×5 count grid as nested lists).

    Raises:
        ValueError: If lengths differ or any rating is outside 1-5.
    """
    like = np.asarray(likelihoods, dtype=np.int64)
    imp = np.asarray(impacts, dtype=np.int64)
    if like.shape != imp.shape:
        raise ValueError("likelihoods and impacts must have equal length")
    if like.size == 0:
        raise ValueError("at least one risk is required")
    if np.any(like < 1) or np.any(like > 5) or np.any(imp < 1) or np.any(imp > 5):
        raise ValueError("ratings must be in 1-5")

    scores = (like * imp).astype(np.float64)
    matrix = np.zeros((5, 5), dtype=np.int64)
    for i in range(like.size):
        matrix[like[i] - 1, imp[i] - 1] += 1
    return {
        "scores": [int(s) for s in scores],
        "ratings": [_rag_from_score(float(s)) for s in scores],
        "matrix": matrix.tolist(),
    }


def regulatory_compliance_score(
    requirements_met: np.ndarray,
    weights: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Weighted regulatory-compliance score.

    Computes the weighted fraction of regulatory requirements met (each 0 = not
    met, 1 = met, or a partial value in between) as a 0-100 compliance score with
    a RAG band.

    Args:
        requirements_met: Compliance status per requirement, each in [0, 1].
        weights: Optional importance weights (default equal).

    Returns:
        Dict with ``compliance_score`` (0-100), ``num_requirements`` and
        ``rating``.

    Raises:
        ValueError: If statuses are out of [0, 1] or weights mismatch / sum to 0.
    """
    met = np.asarray(requirements_met, dtype=np.float64)
    if met.size == 0:
        raise ValueError("requirements_met must be non-empty")
    if np.any(met < 0.0) or np.any(met > 1.0):
        raise ValueError("requirements_met must lie in [0, 1]")
    if weights is None:
        w = np.ones_like(met)
    else:
        w = np.asarray(weights, dtype=np.float64)
        if w.shape != met.shape:
            raise ValueError("weights must match requirements_met length")
    total_w = float(np.sum(w))
    if total_w <= 0:
        raise ValueError("weights must sum to a positive value")
    score = float(np.sum(met * w) / total_w) * 100.0
    if score >= 95.0:
        rating = "green"
    elif score >= 80.0:
        rating = "amber"
    else:
        rating = "red"
    return {
        "compliance_score": round(score, 4),
        "num_requirements": int(met.size),
        "rating": rating,
    }


def audit_finding_risk_scorer(
    severity: int,
    likelihood: int,
    overdue_days: float,
) -> dict:  # type: ignore[type-arg]
    """Score an outstanding audit finding by severity, likelihood and ageing.

    Base score is severity × likelihood on the 5×5 scale; overdue remediation
    escalates the score (each 30-day block adds an uplift), capped at 25.

    Args:
        severity: Finding severity 1-5.
        likelihood: Likelihood of materialisation 1-5.
        overdue_days: Days the remediation is past due (>= 0).

    Returns:
        Dict with ``base_score``, ``adjusted_score`` (capped 25) and ``rating``.

    Raises:
        ValueError: If ratings are out of 1-5 or overdue_days is negative.
    """
    if not (1 <= severity <= 5 and 1 <= likelihood <= 5):
        raise ValueError("severity and likelihood must be in 1-5")
    if overdue_days < 0:
        raise ValueError("overdue_days must be non-negative")
    base = severity * likelihood
    uplift = (overdue_days // 30) * 2.0
    adjusted = min(base + uplift, 25.0)
    return {
        "base_score": int(base),
        "adjusted_score": round(float(adjusted), 2),
        "rating": _rag_from_score(adjusted),
    }

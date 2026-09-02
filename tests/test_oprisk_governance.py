"""tests/test_oprisk_governance.py — governance/reporting/emerging-risk tests."""

import numpy as np
import pytest

from engine.oprisk_governance import (
    audit_finding_risk_scorer,
    business_continuity_risk_score,
    conduct_risk_metric,
    cyber_risk_loss_estimation,
    escalation_threshold_calculation,
    it_risk_scoring,
    model_risk_assessment,
    near_miss_capture_framework,
    oprisk_heat_map_generator,
    regulatory_compliance_score,
    risk_appetite_statement_oprisk,
    root_cause_analysis_template,
    third_party_vendor_risk,
)


def test_cyber_loss_estimation():
    r = cyber_risk_loss_estimation(10000, 150.0, 0.1, business_interruption_cost=500000.0)
    assert r["worst_case_loss"] == 10000 * 150.0 + 500000.0
    assert r["expected_loss"] == round(r["worst_case_loss"] * 0.1, 2)


def test_cyber_invalid_prob_raises():
    with pytest.raises(ValueError):
        cyber_risk_loss_estimation(100, 1.0, 1.5)


def test_conduct_risk_metric():
    r = conduct_risk_metric(100, 100000, 50000.0, 10000000.0)
    assert r["complaints_per_1000"] == 1.0
    assert "rating" in r


def test_conduct_invalid_customers_raises():
    with pytest.raises(ValueError):
        conduct_risk_metric(10, 0, 0.0, 100.0)


def test_model_risk_residual():
    r = model_risk_assessment(5, 5, validation_score=0.0)
    assert r["inherent_score"] == 25
    assert r["residual_score"] == 25.0
    assert r["tier"] == "red"
    # strong validation reduces residual
    assert model_risk_assessment(5, 5, 1.0)["residual_score"] == 0.0


def test_model_risk_invalid_raises():
    with pytest.raises(ValueError):
        model_risk_assessment(6, 5, 0.5)


def test_it_risk_scoring_high():
    r = it_risk_scoring(availability=0.90, incident_count=10, patch_compliance=0.5)
    assert r["it_risk_score"] > 0
    # perfect IT -> 0 score green
    assert it_risk_scoring(1.0, 0, 1.0)["rating"] == "green"


def test_it_risk_invalid_raises():
    with pytest.raises(ValueError):
        it_risk_scoring(1.5, 0, 1.0)


def test_vendor_risk_high():
    r = third_party_vendor_risk(5, financial_health=0.2, concentration=0.9, substitutability=0.1)
    assert r["vendor_risk_score"] > 60
    assert r["rating"] == "red"


def test_vendor_risk_invalid_raises():
    with pytest.raises(ValueError):
        third_party_vendor_risk(6, 0.5, 0.5, 0.5)


def test_bcp_mtd_breach():
    r = business_continuity_risk_score(48.0, 4.0, max_tolerable_downtime=24.0, bcp_maturity=0.0)
    assert r["mtd_breach"] is True
    assert r["bc_risk_score"] > 50


def test_bcp_mature_reduces_score():
    high = business_continuity_risk_score(48.0, 4.0, 24.0, 0.0)["bc_risk_score"]
    low = business_continuity_risk_score(48.0, 4.0, 24.0, 1.0)["bc_risk_score"]
    assert low < high


# ── rpo_target_hours opt-in (caveat-triage batch 1) ──────────────────────────
# docs/p11-caveat-triage-plan.md Tier 1: rpo_hours was accepted and
# range-validated but had no effect on the score at all. Default (omitted)
# behaviour must stay byte-identical to before; rpo_target_hours is the new
# opt-in that actually scores it.


def test_bcp_default_omits_rpo_breach_and_matches_pre_change_output():
    r = business_continuity_risk_score(48.0, 4.0, max_tolerable_downtime=24.0, bcp_maturity=0.0)
    assert "rpo_breach" not in r
    assert r == {"mtd_breach": True, "bc_risk_score": 100.0, "rating": "red"}


def test_bcp_rpo_breach_detected_and_drives_score_when_worse_than_rto():
    # RTO is fine (well inside MTD) but RPO badly breaches its own target --
    # the RPO axis alone must drive bc_risk_score up, not get diluted away
    # by the healthy RTO side.
    r = business_continuity_risk_score(
        rto_hours=1.0,
        rpo_hours=48.0,
        max_tolerable_downtime=24.0,
        bcp_maturity=0.0,
        rpo_target_hours=4.0,
    )
    assert r["mtd_breach"] is False
    assert r["rpo_breach"] is True
    assert r["bc_risk_score"] > 50.0


def test_bcp_rpo_within_target_no_breach():
    r = business_continuity_risk_score(
        rto_hours=1.0,
        rpo_hours=2.0,
        max_tolerable_downtime=24.0,
        bcp_maturity=0.0,
        rpo_target_hours=4.0,
    )
    assert r["mtd_breach"] is False
    assert r["rpo_breach"] is False


def test_bcp_score_is_worse_of_rto_and_rpo_not_an_average():
    # Both axes breach, RPO worse -- score must match the RPO-only-breach
    # case (the max), not something diluted between the two.
    both_breach = business_continuity_risk_score(
        rto_hours=25.0,
        rpo_hours=100.0,
        max_tolerable_downtime=24.0,
        bcp_maturity=0.0,
        rpo_target_hours=4.0,
    )
    rpo_only = business_continuity_risk_score(
        rto_hours=1.0,
        rpo_hours=100.0,
        max_tolerable_downtime=24.0,
        bcp_maturity=0.0,
        rpo_target_hours=4.0,
    )
    assert both_breach["bc_risk_score"] == rpo_only["bc_risk_score"]


def test_bcp_invalid_rpo_target_raises():
    with pytest.raises(ValueError):
        business_continuity_risk_score(1.0, 1.0, 24.0, 0.0, rpo_target_hours=0.0)


def test_near_miss_capture():
    events = [
        {"actual_loss": 0.0, "potential_loss": 1000.0},
        {"actual_loss": 500.0, "potential_loss": 500.0},
        {"actual_loss": 0.0, "potential_loss": 2000.0},
    ]
    r = near_miss_capture_framework(events)
    assert r["near_miss_count"] == 2
    assert r["total_potential_loss"] == 3000.0
    assert r["actual_loss_count"] == 1


def test_near_miss_missing_key_raises():
    with pytest.raises(ValueError):
        near_miss_capture_framework([{"actual_loss": 0.0}])


def test_rca_attribution():
    r = root_cause_analysis_template({"people": 2.0, "process": 6.0, "systems": 2.0})
    assert abs(sum(r["attribution"].values()) - 1.0) < 1e-9
    assert r["primary_cause"] == "process"


def test_rca_zero_weights_raises():
    with pytest.raises(ValueError):
        root_cause_analysis_template({"a": 0.0})


def test_risk_appetite_statement_tiers():
    assert risk_appetite_statement_oprisk(5.0, 10.0, 20.0)["status"] == "within_appetite"
    assert risk_appetite_statement_oprisk(15.0, 10.0, 20.0)["status"] == "within_tolerance"
    assert risk_appetite_statement_oprisk(25.0, 10.0, 20.0)["status"] == "breach"


def test_risk_appetite_inconsistent_raises():
    with pytest.raises(ValueError):
        risk_appetite_statement_oprisk(5.0, 20.0, 10.0, higher_is_worse=True)


def test_escalation_threshold():
    thr = {"team": 1e3, "head": 1e4, "exco": 1e5, "board": 1e6}
    assert escalation_threshold_calculation(50000.0, thr)["escalation_level"] == "head"
    assert escalation_threshold_calculation(100.0, thr)["escalation_level"] is None
    assert escalation_threshold_calculation(2e6, thr)["escalation_level"] == "board"


def test_escalation_empty_raises():
    with pytest.raises(ValueError):
        escalation_threshold_calculation(100.0, {})


def test_heat_map_generator():
    r = oprisk_heat_map_generator(np.array([5, 1, 3]), np.array([5, 1, 4]))
    assert r["scores"] == [25, 1, 12]
    assert r["ratings"] == ["red", "green", "amber"]
    assert r["matrix"][4][4] == 1  # one risk in (5,5)


def test_heat_map_invalid_rating_raises():
    with pytest.raises(ValueError):
        oprisk_heat_map_generator(np.array([6]), np.array([1]))


def test_regulatory_compliance_score():
    r = regulatory_compliance_score(np.array([1.0, 1.0, 0.0, 1.0]))
    assert r["compliance_score"] == 75.0
    assert r["rating"] == "red"
    assert regulatory_compliance_score(np.array([1.0, 1.0]))["rating"] == "green"


def test_regulatory_compliance_invalid_raises():
    with pytest.raises(ValueError):
        regulatory_compliance_score(np.array([1.5]))


def test_audit_finding_overdue_uplift():
    r = audit_finding_risk_scorer(3, 3, overdue_days=90.0)
    # base 9, uplift (90//30)*2 = 6 -> 15
    assert r["base_score"] == 9
    assert r["adjusted_score"] == 15.0
    assert r["rating"] == "red"


def test_audit_finding_capped_at_25():
    r = audit_finding_risk_scorer(5, 5, overdue_days=300.0)
    assert r["adjusted_score"] == 25.0


def test_audit_finding_invalid_raises():
    with pytest.raises(ValueError):
        audit_finding_risk_scorer(0, 3, 0.0)

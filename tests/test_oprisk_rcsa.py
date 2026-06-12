"""tests/test_oprisk_rcsa.py — RCSA, BEICF, loss-data framework tests."""

import numpy as np
import pytest

from engine.oprisk_rcsa import (
    business_environment_factor_bei,
    control_testing_effectiveness,
    external_loss_data_integration,
    internal_control_factor_icf,
    loss_data_collection_framework,
    loss_event_classification_basel,
    rcsa_control_effectiveness,
    rcsa_inherent_risk_scoring,
    rcsa_residual_risk_scoring,
    rcsa_risk_identification,
)


def test_risk_identification_summary():
    register = [
        {"risk_id": "R1", "category": "internal_fraud"},
        {"risk_id": "R2", "category": "internal_fraud"},
        {"risk_id": "R3", "category": "external_fraud"},
    ]
    r = rcsa_risk_identification(register)
    assert r["num_risks"] == 3
    assert r["by_category"]["internal_fraud"] == 2


def test_risk_identification_invalid_category_raises():
    with pytest.raises(ValueError):
        rcsa_risk_identification([{"risk_id": "R1", "category": "bogus"}])


def test_risk_identification_empty_raises():
    with pytest.raises(ValueError):
        rcsa_risk_identification([])


def test_inherent_scoring():
    r = rcsa_inherent_risk_scoring(5, 5)
    assert r["inherent_score"] == 25
    assert r["rating"] == "red"
    assert rcsa_inherent_risk_scoring(1, 2)["rating"] == "green"


def test_inherent_out_of_range_raises():
    with pytest.raises(ValueError):
        rcsa_inherent_risk_scoring(6, 1)


def test_residual_reduces_with_controls():
    r = rcsa_residual_risk_scoring(20.0, control_effectiveness=0.5)
    assert r["residual_score"] == 10.0
    # full control -> zero residual
    assert rcsa_residual_risk_scoring(20.0, 1.0)["residual_score"] == 0.0


def test_residual_invalid_effectiveness_raises():
    with pytest.raises(ValueError):
        rcsa_residual_risk_scoring(20.0, 1.5)


def test_control_effectiveness_weighted():
    r = rcsa_control_effectiveness(0.9, 0.7, design_weight=0.5)
    assert r["effectiveness"] == 0.8
    assert r["rating"] == "effective"


def test_control_effectiveness_invalid_raises():
    with pytest.raises(ValueError):
        rcsa_control_effectiveness(1.5, 0.5)


def test_control_testing_pass_rate():
    r = control_testing_effectiveness(96, 100)
    assert r["pass_rate"] == 0.96
    assert r["conclusion"] == "effective"
    assert control_testing_effectiveness(80, 100)["conclusion"] == "deficient"


def test_control_testing_invalid_raises():
    with pytest.raises(ValueError):
        control_testing_effectiveness(110, 100)


def test_bei_multiplier_above_baseline():
    # avg 4 vs baseline 3 -> 1 + 0.05*1 = 1.05
    r = business_environment_factor_bei(np.array([4.0, 4.0]))
    assert r["bei_multiplier"] == 1.05


def test_bei_empty_raises():
    with pytest.raises(ValueError):
        business_environment_factor_bei(np.array([]))


def test_icf_better_controls_reduce_capital():
    # avg 0.9 vs baseline 0.8 -> 1 - 0.25*0.1 = 0.975
    r = internal_control_factor_icf(np.array([0.9, 0.9]))
    assert r["icf_multiplier"] == 0.975
    assert r["capital_impact"] < 0


def test_icf_invalid_score_raises():
    with pytest.raises(ValueError):
        internal_control_factor_icf(np.array([1.5]))


def test_loss_event_classification_valid():
    r = loss_event_classification_basel("execution_delivery_process")
    assert r["valid"] is True
    assert r["category_index"] == 6


def test_loss_event_classification_invalid():
    r = loss_event_classification_basel("made_up")
    assert r["valid"] is False
    assert r["category_index"] == -1


def test_loss_event_empty_raises():
    with pytest.raises(ValueError):
        loss_event_classification_basel("")


def test_loss_data_collection_threshold():
    events = [
        {"gross_amount": 5000.0},
        {"gross_amount": 500.0},
        {"gross_amount": 20000.0},
    ]
    r = loss_data_collection_framework(events, reporting_threshold=1000.0)
    assert r["reportable_count"] == 2
    assert r["total_loss"] == 25000.0
    assert r["below_threshold_count"] == 1
    assert r["max_loss"] == 20000.0


def test_loss_data_missing_amount_raises():
    with pytest.raises(ValueError):
        loss_data_collection_framework([{"foo": 1}], 0.0)


def test_external_loss_integration_scaling():
    r = external_loss_data_integration(
        np.array([100.0, 200.0]), np.array([1000.0]), scaling_factor=0.5
    )
    # external scaled to 500; combined = [100, 200, 500]
    assert r["combined_count"] == 3
    assert abs(r["external_weight"] - 1 / 3) < 1e-6


def test_external_loss_invalid_scaling_raises():
    with pytest.raises(ValueError):
        external_loss_data_integration(np.array([1.0]), np.array([1.0]), 0.0)

"""tests/test_liquidity_internal.py — internal liquidity metrics tests."""

import numpy as np
import pytest

from engine.liquidity_internal import (
    central_bank_facility_eligibility,
    contingent_liquidity_risk,
    cross_currency_liquidity_bridge,
    deposit_stability_classification,
    early_warning_indicator_liquidity,
    ilaap_internal_liquidity_metric,
    liquidity_risk_appetite_threshold,
    liquidity_scorecard_aggregation,
)


def test_ilaap_metric_adequate():
    r = ilaap_internal_liquidity_metric(120.0, 100.0, survival_days=100.0)
    assert r["coverage_ratio"] == 1.2
    assert r["adequate"] is True


def test_ilaap_metric_inadequate_survival():
    r = ilaap_internal_liquidity_metric(120.0, 100.0, survival_days=30.0)
    assert r["adequate"] is False


def test_ilaap_metric_zero_outflow_raises():
    with pytest.raises(ValueError):
        ilaap_internal_liquidity_metric(100.0, 0.0, 90.0)


def test_risk_appetite_higher_better():
    assert liquidity_risk_appetite_threshold(1.2, 1.1, 1.0)["zone"] == "green"
    assert liquidity_risk_appetite_threshold(1.05, 1.1, 1.0)["zone"] == "amber"
    r = liquidity_risk_appetite_threshold(0.9, 1.1, 1.0)
    assert r["zone"] == "red"
    assert r["breach"] is True


def test_risk_appetite_lower_better():
    r = liquidity_risk_appetite_threshold(0.2, 0.3, 0.5, higher_is_better=False)
    assert r["zone"] == "green"
    r2 = liquidity_risk_appetite_threshold(0.6, 0.3, 0.5, higher_is_better=False)
    assert r2["zone"] == "red"


def test_risk_appetite_inconsistent_raises():
    with pytest.raises(ValueError):
        liquidity_risk_appetite_threshold(1.0, 0.5, 1.0, higher_is_better=True)


def test_ewi_alert_on_three():
    r = early_warning_indicator_liquidity(
        {"lcr": 0.9, "spread": 200, "concentration": 0.6},
        {"lcr": 1.0, "spread": 100, "concentration": 0.5},
        {"lcr": "lower_breach", "spread": "higher_breach", "concentration": "higher_breach"},
    )
    assert r["num_triggered"] == 3
    assert r["signal"] == "alert"


def test_ewi_normal():
    r = early_warning_indicator_liquidity({"lcr": 1.2}, {"lcr": 1.0})
    assert r["signal"] == "normal"


def test_central_bank_eligibility():
    r = central_bank_facility_eligibility(
        np.array([5, 2, 4]), min_rating=4, asset_values=np.array([100.0, 100.0, 100.0]),
        cb_haircuts=np.array([0.1, 0.1, 0.2]),
    )
    # ratings 5 and 4 eligible: 90 + 80 = 170
    assert r["eligible_count"] == 2
    assert r["borrowing_capacity"] == 170.0


def test_central_bank_invalid_haircut_raises():
    with pytest.raises(ValueError):
        central_bank_facility_eligibility(
            np.array([5]), 4, np.array([100.0]), np.array([1.5])
        )


def test_contingent_liquidity_expected():
    r = contingent_liquidity_risk(np.array([1000.0, 500.0]), np.array([0.1, 0.2]))
    assert r["expected_contingent_outflow"] == 200.0  # 100 + 100
    assert r["max_contingent_outflow"] == 1500.0


def test_contingent_invalid_prob_raises():
    with pytest.raises(ValueError):
        contingent_liquidity_risk(np.array([1.0]), np.array([1.5]))


def test_scorecard_green():
    r = liquidity_scorecard_aggregation(np.array([80.0, 90.0]), np.array([1.0, 1.0]))
    assert r["composite_score"] == 85.0
    assert r["rating"] == "green"


def test_scorecard_red():
    r = liquidity_scorecard_aggregation(np.array([20.0, 30.0]), np.array([1.0, 1.0]))
    assert r["rating"] == "red"


def test_scorecard_zero_weights_raises():
    with pytest.raises(ValueError):
        liquidity_scorecard_aggregation(np.array([50.0]), np.array([0.0]))


def test_deposit_stability_classification():
    r = deposit_stability_classification(np.array([0.8, 0.3, 0.6, 0.2]))
    assert r["num_stable"] == 2
    assert r["num_less_stable"] == 2
    assert r["stable_fraction"] == 0.5


def test_deposit_stability_invalid_score_raises():
    with pytest.raises(ValueError):
        deposit_stability_classification(np.array([1.5]))


def test_cross_currency_bridge_full():
    r = cross_currency_liquidity_bridge("USD", 100.0, "EUR", 200.0, fx_rate=1.0)
    assert r["coverable_amount"] == 100.0
    assert r["fully_bridged"] is True


def test_cross_currency_bridge_partial_with_haircut():
    r = cross_currency_liquidity_bridge("USD", 100.0, "EUR", 50.0, fx_rate=1.0, swap_haircut=0.2)
    # usable = 40, coverable 40, residual 60
    assert r["coverable_amount"] == 40.0
    assert r["residual_shortfall"] == 60.0
    assert r["fully_bridged"] is False


def test_cross_currency_invalid_rate_raises():
    with pytest.raises(ValueError):
        cross_currency_liquidity_bridge("USD", 100.0, "EUR", 50.0, fx_rate=0.0)

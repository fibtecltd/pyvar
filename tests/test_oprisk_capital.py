"""tests/test_oprisk_capital.py — OpRisk capital tests (SMA, allocation, EC)."""

import numpy as np
import pytest

from engine.oprisk_capital import (
    basel_standardised_measurement_sma,
    diversification_benefit_oprisk,
    insurance_offset_calculation,
    oprisk_capital_allocation,
    oprisk_economic_capital,
    oprisk_stress_testing,
    tail_risk_scenario_oprisk,
)


def test_sma_bucket1_ilm_one():
    # BI 500m -> BIC = 12% * 500m = 60m, bucket 1 -> ILM = 1
    r = basel_standardised_measurement_sma(500_000_000.0, loss_component=10_000_000.0)
    assert r["bic"] == 60_000_000.0
    assert r["ilm"] == 1.0
    assert r["sma_capital"] == 60_000_000.0


def test_sma_bucket2_piecewise():
    # BI 2bn -> 12%*1bn + 15%*1bn = 270m BIC
    r = basel_standardised_measurement_sma(2_000_000_000.0, loss_component=0.0, use_ilm=False)
    assert r["bic"] == 270_000_000.0


def test_sma_ilm_equals_one_when_lc_matches():
    # LC = BIC -> ratio 1 -> ln(e-1+1) = ln(e) = 1
    bi = 2_000_000_000.0
    bic = 270_000_000.0
    r = basel_standardised_measurement_sma(bi, loss_component=bic, use_ilm=True)
    assert abs(r["ilm"] - 1.0) < 1e-6


def test_sma_negative_bi_raises():
    with pytest.raises(ValueError):
        basel_standardised_measurement_sma(-1.0)


def test_capital_allocation_sums_to_total():
    r = oprisk_capital_allocation(1000.0, np.array([30.0, 50.0, 20.0]))
    assert abs(sum(r["allocations"]) - 1000.0) < 0.01
    assert r["allocations"][1] == 500.0  # 50% share


def test_capital_allocation_zero_risk_raises():
    with pytest.raises(ValueError):
        oprisk_capital_allocation(1000.0, np.array([0.0, 0.0]))


def test_diversification_benefit_independent():
    # perfectly independent (rho=0): diversified < sum
    r = diversification_benefit_oprisk(np.array([100.0, 100.0]), correlation=0.0)
    assert r["sum_standalone"] == 200.0
    assert r["diversified_capital"] < 200.0
    assert r["diversification_benefit"] > 0


def test_diversification_benefit_perfect_correlation():
    # rho=1: no benefit
    r = diversification_benefit_oprisk(np.array([100.0, 100.0]), correlation=1.0)
    assert abs(r["diversified_capital"] - 200.0) < 0.01
    assert r["diversification_benefit"] == 0.0


def test_diversification_invalid_corr_raises():
    with pytest.raises(ValueError):
        diversification_benefit_oprisk(np.array([100.0]), correlation=1.5)


def test_economic_capital_net_of_mitigants():
    r = oprisk_economic_capital(1000.0, 200.0, insurance_offset=100.0, diversification_benefit=50.0)
    # gross UL = 800, net = 800 - 150 = 650
    assert r["gross_capital"] == 800.0
    assert r["economic_capital"] == 650.0


def test_economic_capital_floored_at_zero():
    r = oprisk_economic_capital(300.0, 200.0, insurance_offset=500.0)
    assert r["economic_capital"] == 0.0


def test_insurance_offset_basic():
    r = insurance_offset_calculation(1000.0, policy_limit=800.0, deductible=100.0)
    # above deductible 900, capped at 800
    assert r["recoverable"] == 800.0
    assert r["net_loss"] == 200.0


def test_insurance_offset_haircut():
    r = insurance_offset_calculation(1000.0, 1000.0, 0.0, haircut=0.25)
    assert r["recoverable"] == 750.0


def test_insurance_offset_invalid_haircut_raises():
    with pytest.raises(ValueError):
        insurance_offset_calculation(100.0, 100.0, 0.0, haircut=1.5)


def test_tail_risk_scenario_uplift():
    losses = np.arange(1.0, 1001.0)
    r = tail_risk_scenario_oprisk(losses, tail_confidence=0.99, severity_multiplier=2.0)
    assert r["stressed_tail_es"] == round(r["base_tail_es"] * 2.0, 2)
    assert r["capital_uplift"] > 0


def test_tail_risk_multiplier_below_one_raises():
    with pytest.raises(ValueError):
        tail_risk_scenario_oprisk(np.array([1.0]), severity_multiplier=0.5)


def test_oprisk_stress_multiplicative():
    r = oprisk_stress_testing(1000.0, frequency_shock=0.5, severity_shock=0.2)
    # 1000 * 1.5 * 1.2 = 1800
    assert r["stressed_capital"] == 1800.0
    assert r["capital_increase"] == 800.0


def test_oprisk_stress_invalid_shock_raises():
    with pytest.raises(ValueError):
        oprisk_stress_testing(1000.0, -2.0, 0.0)

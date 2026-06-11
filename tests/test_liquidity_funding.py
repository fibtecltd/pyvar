"""tests/test_liquidity_funding.py — funding risk and pricing tests."""

import numpy as np
import pytest

from engine.liquidity_funding import (
    asset_encumbrance_ratio,
    collateral_availability_analysis,
    contingency_funding_plan_trigger,
    funding_cost_analysis,
    fx_liquidity_risk_by_currency,
    intragroup_liquidity_flow,
    liquidity_buffer_sizing,
    liquidity_transfer_pricing,
    repo_market_stress_haircut,
    retail_deposit_runoff_rate,
    secured_funding_rollover_risk,
    wholesale_funding_concentration,
)


def test_buffer_sizing_peak():
    r = liquidity_buffer_sizing(np.array([10.0, 20.0, -5.0, 30.0]))
    # cumulative: 10, 30, 25, 55 -> peak 55
    assert r["peak_cumulative_outflow"] == 55.0
    assert r["required_buffer"] == 55.0


def test_buffer_sizing_with_confidence():
    r = liquidity_buffer_sizing(np.array([100.0]), confidence_buffer=0.10)
    assert r["required_buffer"] == 110.0


def test_buffer_sizing_empty_raises():
    with pytest.raises(ValueError):
        liquidity_buffer_sizing(np.array([]))


def test_cfp_trigger_breach():
    r = contingency_funding_plan_trigger(
        {"lcr": 0.95, "survival_days": 40}, {"lcr": 1.0, "survival_days": 30}
    )
    assert "lcr" in r["breached"]
    assert "survival_days" not in r["breached"]
    assert r["cfp_activated"] is True


def test_cfp_trigger_no_breach():
    r = contingency_funding_plan_trigger({"lcr": 1.2}, {"lcr": 1.0})
    assert r["cfp_activated"] is False


def test_wholesale_concentration_hhi():
    # equal across 4 -> HHI = 4*(0.25^2) = 0.25, effective = 4
    r = wholesale_funding_concentration(np.array([25.0, 25.0, 25.0, 25.0]))
    assert abs(r["hhi"] - 0.25) < 1e-9
    assert abs(r["effective_counterparties"] - 4.0) < 1e-6


def test_wholesale_concentration_single():
    r = wholesale_funding_concentration(np.array([100.0]))
    assert r["hhi"] == 1.0
    assert r["top1_share"] == 1.0


def test_retail_runoff_blended():
    r = retail_deposit_runoff_rate(np.array([100.0, 100.0]), np.array([0.05, 0.15]))
    assert r["total_runoff"] == 20.0
    assert r["blended_rate"] == 0.1


def test_secured_rollover_gap():
    r = secured_funding_rollover_risk(np.array([100.0, 100.0]), np.array([1.0, 0.5]))
    assert r["rollover_gap"] == 50.0
    assert r["effective_rollover_rate"] == 0.75


def test_encumbrance_ratio():
    r = asset_encumbrance_ratio(30.0, 100.0)
    assert r["encumbrance_ratio"] == 0.3
    assert r["unencumbered_assets"] == 70.0


def test_encumbrance_exceeds_total_raises():
    with pytest.raises(ValueError):
        asset_encumbrance_ratio(150.0, 100.0)


def test_collateral_availability_net_pledged():
    r = collateral_availability_analysis(
        np.array([100.0, 100.0]), np.array([0.10, 0.50]), np.array([0.0, 20.0])
    )
    # post haircut: 90, 50; net pledged: 90, 30 -> total 120
    assert r["available_collateral"] == 120.0


def test_collateral_invalid_haircut_raises():
    with pytest.raises(ValueError):
        collateral_availability_analysis(np.array([1.0]), np.array([1.5]))


def test_repo_stress_margin_call():
    r = repo_market_stress_haircut(
        np.array([0.02, 0.05]), np.array([2.0, 2.0]), np.array([1000.0, 1000.0])
    )
    # stressed: 0.04, 0.10; delta: 0.02, 0.05 -> margin 20 + 50 = 70
    assert r["additional_margin"] == 70.0


def test_repo_multiplier_below_one_raises():
    with pytest.raises(ValueError):
        repo_market_stress_haircut(np.array([0.02]), np.array([0.5]), np.array([100.0]))


def test_fx_liquidity_net_position():
    r = fx_liquidity_risk_by_currency(
        {"USD": 100.0, "EUR": 50.0}, {"USD": 150.0, "EUR": 20.0}
    )
    assert r["net_by_ccy"]["USD"] == -50.0
    assert r["net_by_ccy"]["EUR"] == 30.0
    assert r["largest_short_ccy"] == "USD"


def test_fx_liquidity_empty_raises():
    with pytest.raises(ValueError):
        fx_liquidity_risk_by_currency({}, {})


def test_intragroup_flow_netting():
    r = intragroup_liquidity_flow({"A": 100.0, "B": -60.0, "C": -40.0})
    assert r["total_provided"] == 100.0
    assert r["balanced"] is True
    assert "A" in r["net_providers"]


def test_intragroup_empty_raises():
    with pytest.raises(ValueError):
        intragroup_liquidity_flow({})


def test_funding_cost_weighted_avg():
    r = funding_cost_analysis(np.array([100.0, 100.0]), np.array([0.02, 0.04]))
    assert r["weighted_avg_cost"] == 0.03
    assert r["total_annual_cost"] == 6.0


def test_funding_cost_zero_total_raises():
    with pytest.raises(ValueError):
        funding_cost_analysis(np.array([0.0]), np.array([0.02]))


def test_ltp_all_in_rate():
    r = liquidity_transfer_pricing(1000.0, 5.0, 0.02, 0.01, 0.005)
    assert r["all_in_rate"] == 0.035
    assert r["annual_charge"] == 35.0
    assert r["lifetime_charge"] == 175.0


def test_ltp_negative_notional_raises():
    with pytest.raises(ValueError):
        liquidity_transfer_pricing(-1.0, 5.0, 0.02, 0.01)

"""tests/test_liquidity_stress.py — liquidity stress and survival tests."""

import numpy as np
import pytest

from engine.liquidity_stress import (
    combined_stress_scenario,
    idiosyncratic_stress_scenario,
    ilaap_stress_testing_framework,
    intraday_liquidity_monitor,
    intraday_liquidity_stress_test,
    liquidity_stress_scenario,
    liquidity_var_liqvar,
    market_wide_stress_scenario,
    survival_horizon_calculator,
)


def test_generic_stress_outflow():
    r = liquidity_stress_scenario(np.array([1000.0, 500.0]), np.array([0.10, 0.50]), hqla=400.0)
    assert r["stressed_outflow"] == 350.0  # 100 + 250
    assert r["survives"] is True


def test_generic_stress_invalid_rate_raises():
    with pytest.raises(ValueError):
        liquidity_stress_scenario(np.array([1.0]), np.array([1.5]), 1.0)


def test_idiosyncratic_full_wholesale_runoff():
    r = idiosyncratic_stress_scenario(1000.0, 500.0, hqla=200.0)
    assert r["stressed_outflow"] == 600.0  # 100 + 500
    assert r["survives"] is False


def test_market_wide_haircut_reduces_hqla():
    r = market_wide_stress_scenario(np.array([100.0, 100.0]), np.array([0.0, 0.20]), outflow=150.0)
    assert r["stressed_hqla"] == 180.0  # 100 + 80
    assert r["survives"] is True


def test_combined_worse_than_components():
    hqla = np.array([100.0, 100.0])
    hc = np.array([0.0, 0.20])
    combined = combined_stress_scenario(1000.0, 500.0, hqla, hc)
    # outflow = 150 + 500 = 650, stressed hqla = 180 -> deficit
    assert combined["surplus_deficit"] == 180.0 - 650.0
    assert combined["survives"] is False


def test_combined_stress_scenario_categorised_matches_default_when_equivalent():
    # A single-category array carrying the whole retail balance at the same
    # rate as the scalar default must reproduce the scalar path exactly.
    hqla = np.array([100.0, 100.0])
    hc = np.array([0.0, 0.20])
    scalar = combined_stress_scenario(1000.0, 500.0, hqla, hc, retail_runoff=0.15)
    categorised = combined_stress_scenario(
        1000.0,
        500.0,
        hqla,
        hc,
        retail_deposits_by_category=np.array([1000.0]),
        retail_runoff_rates=np.array([0.15]),
    )
    assert categorised == scalar


def test_combined_stress_scenario_categorised_differs_from_default_rate():
    # BCBS-238-style split (stable/less-stable) at rates below the 15% flat
    # default must produce a smaller outflow than the default convention.
    hqla = np.array([100.0, 100.0])
    hc = np.array([0.0, 0.20])
    default = combined_stress_scenario(1000.0, 500.0, hqla, hc)
    categorised = combined_stress_scenario(
        1000.0,
        500.0,
        hqla,
        hc,
        retail_deposits_by_category=np.array([700.0, 300.0]),
        retail_runoff_rates=np.array([0.05, 0.10]),  # 700*0.05 + 300*0.10 = 65 < 150
    )
    assert categorised["stressed_outflow"] < default["stressed_outflow"]
    assert categorised["stressed_outflow"] == pytest.approx(65.0 + 500.0)


def test_combined_stress_scenario_categorised_partial_args_raises():
    hqla = np.array([100.0, 100.0])
    hc = np.array([0.0, 0.20])
    with pytest.raises(ValueError):
        combined_stress_scenario(
            1000.0, 500.0, hqla, hc, retail_deposits_by_category=np.array([1000.0])
        )
    with pytest.raises(ValueError):
        combined_stress_scenario(1000.0, 500.0, hqla, hc, retail_runoff_rates=np.array([0.15]))


def test_combined_stress_scenario_categorised_must_sum_to_retail_deposits():
    hqla = np.array([100.0, 100.0])
    hc = np.array([0.0, 0.20])
    with pytest.raises(ValueError):
        combined_stress_scenario(
            1000.0,
            500.0,
            hqla,
            hc,
            retail_deposits_by_category=np.array([700.0, 200.0]),  # sums to 900, not 1000
            retail_runoff_rates=np.array([0.05, 0.10]),
        )


def test_combined_stress_scenario_categorised_rejects_out_of_range_rate():
    hqla = np.array([100.0, 100.0])
    hc = np.array([0.0, 0.20])
    with pytest.raises(ValueError):
        combined_stress_scenario(
            1000.0,
            500.0,
            hqla,
            hc,
            retail_deposits_by_category=np.array([1000.0]),
            retail_runoff_rates=np.array([1.5]),
        )


def test_survival_horizon_partial():
    r = survival_horizon_calculator(100.0, np.array([30.0, 30.0, 30.0, 30.0]))
    # day0: 70, day1: 40, day2: 10, day3: -20 -> survives 3 full days
    assert r["survival_days"] == 3


def test_survival_horizon_full_path():
    r = survival_horizon_calculator(1000.0, np.array([10.0, 10.0]))
    assert r["survival_days"] == 2  # never breaches


def test_survival_horizon_empty_raises():
    with pytest.raises(ValueError):
        survival_horizon_calculator(100.0, np.array([]))


def test_intraday_monitor_peak_usage():
    r = intraday_liquidity_monitor(
        np.array([1.0, 2.0, 3.0]), np.array([-50.0, -30.0, 60.0]), opening_balance=100.0
    )
    # path: 50, 20, 80 -> min 20, usage 80
    assert r["min_balance"] == 20.0
    assert r["max_usage"] == 80.0


def test_intraday_monitor_non_monotonic_raises():
    with pytest.raises(ValueError):
        intraday_liquidity_monitor(np.array([2.0, 1.0]), np.array([1.0, 1.0]), 10.0)


def test_intraday_stress_sharpens_usage():
    flows = np.array([100.0, -80.0, -80.0])
    base = intraday_liquidity_monitor(np.array([1.0, 2, 3]), flows, 50.0)["max_usage"]
    stressed = intraday_liquidity_stress_test(flows, 50.0, delay_factor=1.0)
    # delaying all inflow makes the path worse
    assert stressed["stressed_max_usage"] >= base


def test_intraday_stress_invalid_delay_raises():
    with pytest.raises(ValueError):
        intraday_liquidity_stress_test(np.array([1.0]), 1.0, delay_factor=2.0)


def test_ilaap_framework_binding_scenario():
    scenarios = {
        "idio": {"surplus_deficit": 100.0},
        "market": {"surplus_deficit": -50.0},
        "combined": {"surplus_deficit": -200.0},
    }
    r = ilaap_stress_testing_framework(scenarios)
    assert r["binding_scenario"] == "combined"
    assert r["num_breached"] == 2
    assert r["adequate"] is False


def test_ilaap_framework_empty_raises():
    with pytest.raises(ValueError):
        ilaap_stress_testing_framework({})


def test_liqvar_positive_and_above_expected():
    r = liquidity_var_liqvar(1000.0, 0.20, confidence_level=0.99)
    assert r["liqvar"] > r["expected_outflow"]


def test_liqvar_deterministic_with_seed():
    r1 = liquidity_var_liqvar(1000.0, 0.20, seed=7)
    r2 = liquidity_var_liqvar(1000.0, 0.20, seed=7)
    assert r1["liqvar"] == r2["liqvar"]


def test_liqvar_close_to_analytic():
    r = liquidity_var_liqvar(1000.0, 0.20, confidence_level=0.99, n_simulations=200_000)
    assert abs(r["liqvar"] - r["liqvar_analytic"]) / r["liqvar_analytic"] < 0.05


def test_liqvar_invalid_confidence_raises():
    with pytest.raises(ValueError):
        liquidity_var_liqvar(1000.0, 0.20, confidence_level=0.5)

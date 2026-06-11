"""tests/test_alm_irrbb.py — numerical-correctness tests for IRRBB framework.

No mocking. Verifies the six BCBS shock names & sign properties, standardised
worst-case selection, repricing gap cumulation, outlier capital test at the 15%
threshold, and mismatch index zero when immunised.
"""

import numpy as np
import pytest

from engine.alm_irrbb import (
    SIX_SHOCKS,
    asset_liability_mismatch_index,
    basis_risk_irrbb,
    dynamic_gap_analysis,
    interest_rate_risk_capital_irrbb,
    irrbb_internal_model,
    irrbb_six_standard_rate_shocks,
    irrbb_standardised_framework,
    option_risk_irrbb,
    pipeline_risk_measurement,
    repricing_gap_analysis,
    repricing_maturity_profile,
    static_gap_analysis,
)


def test_six_shocks_names_and_parallel_signs():
    tenors = np.array([0.5, 1, 2, 5, 10])
    shocks = irrbb_six_standard_rate_shocks(tenors)
    assert set(shocks.keys()) == set(SIX_SHOCKS)
    assert len(shocks) == 6
    up = np.array(shocks["parallel_up"])
    down = np.array(shocks["parallel_down"])
    assert np.allclose(up, -down)
    assert np.all(up > 0)


def test_short_shock_decays_with_tenor():
    tenors = np.array([0.25, 1.0, 5.0, 20.0])
    s = np.array(irrbb_six_standard_rate_shocks(tenors)["short_up"])
    assert s[0] > s[-1]  # short shock larger at short end


def test_standardised_worst_case_is_min():
    cf = np.array([100.0, 100.0, -50.0, -200.0])
    t = np.array([1.0, 2.0, 5.0, 10.0])
    r0 = np.array([0.02, 0.025, 0.03, 0.035])
    res = irrbb_standardised_framework(cf, t, r0)
    assert res["worst_case"] == min(res["delta_eve"].values())
    assert res["worst_scenario"] in SIX_SHOCKS


def test_internal_model_runs():
    cf = np.array([100.0, -80.0, -50.0])
    t = np.array([1.0, 3.0, 5.0])
    r0 = np.array([0.02, 0.03, 0.035])
    rng = np.random.default_rng(0)
    scen = rng.normal(0, 0.01, size=(500, 3))
    res = irrbb_internal_model(cf, t, r0, scen)
    assert res["worst_case_99"] <= res["mean_delta_eve"]


def test_repricing_gap_cumulative():
    res = repricing_gap_analysis(np.array([100.0, 200.0]), np.array([150.0, 100.0]))
    assert res["cumulative_gap"][-1] == pytest.approx(res["total_gap"])


def test_repricing_maturity_profile_conserves_balance():
    bal = np.array([100.0, 200.0, 50.0])
    rt = np.array([0.3, 2.0, 7.0])
    edges = np.array([0.0, 1.0, 5.0, 30.0])
    res = repricing_maturity_profile(bal, rt, 3, edges)
    assert sum(res["profile"]) == pytest.approx(350.0)


def test_static_gap_ratio():
    res = static_gap_analysis(np.array([100.0, 100.0]), np.array([80.0, 120.0]))
    assert res["gap_ratio"] == pytest.approx(200.0 / 200.0)


def test_dynamic_gap_path_length():
    res = dynamic_gap_analysis(
        np.array([100.0]), np.array([80.0]), np.array([0.05]), np.array([0.03]), 3
    )
    assert len(res["projected_total_gap"]) == 3


def test_basis_risk_sign():
    res = basis_risk_irrbb(np.array([1000.0]), np.array([0.01]), np.array([800.0]), np.array([0.005]))
    assert res["basis_risk_nii"] == pytest.approx(1000.0 * 0.01 - 800.0 * 0.005)


def test_option_risk_sum():
    res = option_risk_irrbb(50.0, 30.0, 10000.0)
    assert res["total_option_risk"] == pytest.approx(80.0)
    assert res["option_risk_ratio"] == pytest.approx(0.008)


def test_pipeline_risk():
    res = pipeline_risk_measurement(1e6, 0.8, 0.25, 0.1)
    assert res["expected_exposure"] == pytest.approx(8e5)
    assert res["rate_risk"] > 0


def test_irrbb_capital_outlier_threshold():
    # decline 20% of T1 -> outlier
    res = interest_rate_risk_capital_irrbb(-200.0, 1000.0, 0.15)
    assert res["is_outlier"] is True
    assert res["capital_add_on"] == pytest.approx(200.0 - 150.0)
    # within threshold -> not outlier
    res2 = interest_rate_risk_capital_irrbb(-100.0, 1000.0, 0.15)
    assert res2["is_outlier"] is False
    assert res2["capital_add_on"] == 0.0


def test_mismatch_index_zero_when_immunised():
    res = asset_liability_mismatch_index(
        np.array([4.0]), np.array([1000.0]), np.array([5.0]), np.array([800.0])
    )
    # D_A*A = 4000, D_L*L = 4000 -> immunised
    assert res["mismatch_index"] == pytest.approx(0.0, abs=1e-9)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        interest_rate_risk_capital_irrbb(-100.0, 0.0)
    with pytest.raises(ValueError):
        pipeline_risk_measurement(1e6, 1.5, 0.25, 0.1)

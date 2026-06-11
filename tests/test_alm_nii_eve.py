"""tests/test_alm_nii_eve.py — numerical-correctness tests for NII/EVE.

No mocking. Verifies stressed NII direction with betas, EVE = PV(A)-PV(L), EVE
sensitivity six-shock coverage and worst case, liquidity-adjusted carry sign.
"""

import numpy as np
import pytest

from engine.alm_irrbb import SIX_SHOCKS
from engine.alm_nii_eve import (
    economic_value_of_equity_eve,
    eve_sensitivity_analysis,
    liquidity_adjusted_nii,
    nii_simulation_stress,
)


def test_stress_nii_asset_sensitive_gains_when_rates_rise():
    # assets reprice fully (beta 1), liabilities lag (beta 0.5)
    r = nii_simulation_stress(
        np.array([1000.0]), np.array([0.04]),
        np.array([800.0]), np.array([0.01]),
        rate_shock=0.01, asset_beta=1.0, liability_beta=0.5,
    )
    assert r["delta_nii"] > 0
    assert r["delta_nii"] == pytest.approx(1000.0 * 0.01 - 800.0 * 0.005)


def test_eve_equals_pv_assets_minus_liabilities():
    r = economic_value_of_equity_eve(
        np.array([1050.0]), np.array([1.0]),
        np.array([1020.0]), np.array([1.0]),
        np.array([0.05]), np.array([0.03]),
    )
    assert r["eve"] == pytest.approx(r["pv_assets"] - r["pv_liabilities"], abs=1e-9)


def test_eve_sensitivity_covers_six_shocks():
    cf = np.array([100.0, 50.0, -40.0, -200.0])
    t = np.array([1.0, 2.0, 5.0, 10.0])
    r0 = np.array([0.02, 0.025, 0.03, 0.035])
    res = eve_sensitivity_analysis(cf, t, r0)
    assert set(res["delta_eve"].keys()) == set(SIX_SHOCKS)
    assert res["worst_case"] == min(res["delta_eve"].values())


def test_eve_sensitivity_long_liability_loses_when_rates_fall():
    # net cashflows dominated by long-dated negative (liability) flows
    cf = np.array([0.0, 0.0, -1000.0])
    t = np.array([1.0, 5.0, 10.0])
    r0 = np.array([0.03, 0.03, 0.03])
    res = eve_sensitivity_analysis(cf, t, r0)
    # parallel_down lowers discount rate -> liability PV rises -> EVE falls
    assert res["delta_eve"]["parallel_down"] < 0


def test_liquidity_adjusted_carry_drag():
    r = liquidity_adjusted_nii(1000.0, 5000.0, 0.02, 0.025, 0.005)
    assert r["buffer_carry"] < 0  # negative carry
    assert r["adjusted_nii"] < 1000.0


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        economic_value_of_equity_eve(
            np.array([1.0, 2.0]), np.array([1.0]), np.array([1.0]),
            np.array([1.0]), np.array([0.05]), np.array([0.03]),
        )
    with pytest.raises(ValueError):
        liquidity_adjusted_nii(1000.0, -1.0, 0.02, 0.025, 0.005)

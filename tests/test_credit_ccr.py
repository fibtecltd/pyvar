"""tests/test_credit_ccr.py — numerical-correctness tests for CCR exposure family.

No mocking. Verifies: current exposure floored at zero, SA-CCR alpha scaling,
PFE >= EE pointwise, EEPE >= EPE (non-decreasing profile), PFE grows with
horizon, haircut reduces collateral.
"""

import numpy as np
import pytest

from engine.credit_ccr import (
    collateral_haircut_calculation,
    counterparty_credit_risk_ccr_exposure,
    current_exposure_method_cem,
    effective_epe_regulatory,
    expected_positive_exposure_epe,
    potential_future_exposure_pfe,
    standardised_approach_ccr_sa_ccr,
)


def test_ccr_exposure_floored_and_collateral():
    r = counterparty_credit_risk_ccr_exposure(-50.0, add_on=10.0, collateral=0.0)
    assert r["current_exposure"] == 0.0
    assert r["exposure"] == 10.0
    r2 = counterparty_credit_risk_ccr_exposure(100.0, 10.0, collateral=40.0)
    assert r2["current_exposure"] == 60.0


def test_cem_ead_components():
    r = current_exposure_method_cem(mark_to_market=20.0, notional=1000.0, add_on_factor=0.015)
    assert abs(r["replacement_cost"] - 20.0) < 1e-9
    assert abs(r["potential_future_exposure"] - 15.0) < 1e-9
    assert abs(r["ead"] - 35.0) < 1e-9


def test_sa_ccr_alpha_scaling():
    r = standardised_approach_ccr_sa_ccr(
        mark_to_market=100.0, collateral=0.0, add_on_aggregate=50.0, alpha=1.4
    )
    # In-the-money, no excess collateral -> multiplier == 1.
    assert abs(r["multiplier"] - 1.0) < 1e-9
    assert abs(r["ead"] - 1.4 * (100.0 + 50.0)) < 1e-6


def test_sa_ccr_multiplier_below_one_when_overcollateralised():
    r = standardised_approach_ccr_sa_ccr(
        mark_to_market=0.0, collateral=80.0, add_on_aggregate=50.0
    )
    assert r["multiplier"] < 1.0
    assert r["replacement_cost"] == 0.0


def test_pfe_exceeds_ee_and_grows_with_horizon():
    t = np.array([0.25, 0.5, 1.0, 2.0])
    r = potential_future_exposure_pfe(
        initial_value=0.0, volatility=0.2, time_steps=t, quantile=0.95,
        n_paths=20_000, seed=5,
    )
    for ee, pfe in zip(r["ee"], r["pfe"]):
        assert pfe >= ee - 1e-9
    # PFE increases with horizon for a diffusive value.
    assert r["pfe"][-1] > r["pfe"][0]
    assert abs(r["peak_pfe"] - max(r["pfe"])) < 1e-6


def test_epe_trapezoidal_constant_profile():
    ee = np.array([10.0, 10.0, 10.0])
    t = np.array([0.0, 0.5, 1.0])
    r = expected_positive_exposure_epe(ee, t)
    assert abs(r["epe"] - 10.0) < 1e-9


def test_eepe_ge_epe_for_decreasing_profile():
    # Decreasing EE: EEE stays at the early peak so EEPE > EPE.
    ee = np.array([10.0, 6.0, 2.0])
    t = np.array([0.0, 0.5, 1.0])
    epe = expected_positive_exposure_epe(ee, t)["epe"]
    eepe = effective_epe_regulatory(ee, t)["eepe"]
    assert eepe >= epe
    # Effective EE is non-decreasing.
    res = effective_epe_regulatory(ee, t)
    assert all(res["eee"][i] <= res["eee"][i + 1] for i in range(len(res["eee"]) - 1))


def test_haircut_reduces_collateral():
    r = collateral_haircut_calculation(100.0, haircut_collateral=0.15, haircut_fx=0.08)
    assert abs(r["adjusted_collateral"] - 77.0) < 1e-6
    assert abs(r["total_haircut"] - 0.23) < 1e-9


def test_haircut_rejects_bad_input():
    with pytest.raises(ValueError):
        collateral_haircut_calculation(100.0, haircut_collateral=1.5)

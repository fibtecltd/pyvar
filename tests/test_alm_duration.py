"""tests/test_alm_duration.py — numerical-correctness tests for ALM duration.

No mocking. Verifies duration signs, gap formula, NII sensitivity sign, baseline
NII arithmetic.
"""

import numpy as np
import pytest

from engine.alm_duration import (
    convexity_gap,
    duration_gap_analysis,
    effective_duration_alm,
    macaulay_duration_balance_sheet,
    modified_duration_balance_sheet,
    nii_sensitivity_rate_shock,
    nii_simulation_baseline,
)


def test_macaulay_zero_coupon_equals_time():
    d = macaulay_duration_balance_sheet(np.array([100.0]), np.array([5.0]), 0.03)["macaulay_duration"]
    assert d == pytest.approx(5.0, abs=1e-8)


def test_modified_le_macaulay():
    cf = np.array([5.0, 5.0, 105.0])
    t = np.array([1.0, 2.0, 3.0])
    mac = macaulay_duration_balance_sheet(cf, t, 0.04)["macaulay_duration"]
    mod = modified_duration_balance_sheet(cf, t, 0.04)["modified_duration"]
    assert mod < mac


def test_effective_duration_formula():
    eff = effective_duration_alm(1000.0, 980.0, 1020.0, 0.01)["effective_duration"]
    assert eff == pytest.approx((1020.0 - 980.0) / (2.0 * 1000.0 * 0.01))


def test_duration_gap_positive_asset_heavy():
    r = duration_gap_analysis(5.0, 2.0, 1000.0, 800.0, 0.01)
    assert r["duration_gap"] > 0
    assert r["delta_eve"] < 0  # rate up hurts asset-heavy duration gap
    assert r["equity"] == pytest.approx(200.0)


def test_convexity_gap_runs():
    r = convexity_gap(40.0, 20.0, 1000.0, 800.0)
    assert r["convexity_gap"] == pytest.approx(40.0 - 0.8 * 20.0)


def test_nii_sensitivity_positive_gap_gains_when_rates_rise():
    r = nii_sensitivity_rate_shock(1000.0, 600.0, 0.01)
    assert r["repricing_gap"] == pytest.approx(400.0)
    assert r["delta_nii"] > 0


def test_nii_baseline_arithmetic():
    r = nii_simulation_baseline(np.array([1000.0]), np.array([0.05]), np.array([800.0]), np.array([0.02]))
    assert r["nii"] == pytest.approx(50.0 - 16.0)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        effective_duration_alm(0.0, 980.0, 1020.0, 0.01)
    with pytest.raises(ValueError):
        duration_gap_analysis(5.0, 2.0, 0.0, 800.0)

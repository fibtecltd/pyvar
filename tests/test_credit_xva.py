"""tests/test_credit_xva.py — numerical-correctness tests for the XVA family.

No mocking. Verifies: CVA >= 0 and grows with spread, CVA scales linearly with
EPE, single-bucket CVA matches the closed form, FVA/KVA/MVA grow with their
spreads, XVA sign convention (DVA subtracts), CS01 positive, WWR multiplier.
"""

import numpy as np
import pytest

from engine.credit_xva import (
    capital_valuation_adjustment_kva,
    credit_valuation_adjustment_cva,
    cva_sensitivity_cva_greeks,
    debt_valuation_adjustment_dva,
    funding_valuation_adjustment_fva,
    margin_valuation_adjustment_mva,
    wrong_way_risk_adjustment,
    xva_aggregation,
)


@pytest.fixture
def profile():
    t = np.array([0.5, 1.0, 1.5, 2.0])
    epe = np.array([100.0, 90.0, 70.0, 40.0])
    df = np.exp(-0.02 * t)
    return epe, t, df


def test_cva_positive_and_grows_with_spread(profile):
    epe, t, df = profile
    low = credit_valuation_adjustment_cva(epe, t, df, 0.005)
    high = credit_valuation_adjustment_cva(epe, t, df, 0.02)
    assert high["cva"] > low["cva"] > 0.0


def test_cva_linear_in_epe(profile):
    epe, t, df = profile
    a = credit_valuation_adjustment_cva(epe, t, df, 0.01)["cva"]
    b = credit_valuation_adjustment_cva(2.0 * epe, t, df, 0.01)["cva"]
    assert abs(b - 2.0 * a) < 1e-4


def test_cva_single_bucket_closed_form():
    t = np.array([1.0])
    epe = np.array([100.0])
    df = np.array([0.95])
    r = credit_valuation_adjustment_cva(epe, t, df, 0.012, recovery_rate=0.4)
    lgd = 0.6
    hazard = 0.012 / lgd
    dpd = 1.0 - np.exp(-hazard * 1.0)
    expected = lgd * 100.0 * 0.95 * dpd
    assert abs(r["cva"] - expected) < 1e-6


def test_cva_zero_spread_is_zero(profile):
    epe, t, df = profile
    r = credit_valuation_adjustment_cva(epe, t, df, 0.0)
    assert abs(r["cva"]) < 1e-12


def test_dva_mirrors_cva(profile):
    epe, t, df = profile
    cva = credit_valuation_adjustment_cva(epe, t, df, 0.015)["cva"]
    dva = debt_valuation_adjustment_dva(epe, t, df, 0.015)["dva"]
    assert abs(cva - dva) < 1e-9


def test_fva_grows_with_spread(profile):
    epe, t, df = profile
    low = funding_valuation_adjustment_fva(epe, t, df, 0.005)["fva"]
    high = funding_valuation_adjustment_fva(epe, t, df, 0.02)["fva"]
    assert high > low > 0.0


def test_kva_and_mva_proportional(profile):
    epe, t, df = profile
    kva = capital_valuation_adjustment_kva(epe, t, df, cost_of_capital=0.10)["kva"]
    kva2 = capital_valuation_adjustment_kva(epe, t, df, cost_of_capital=0.20)["kva"]
    assert abs(kva2 - 2.0 * kva) < 1e-4
    mva = margin_valuation_adjustment_mva(epe, t, df, 0.01)["mva"]
    assert mva > 0.0


def test_xva_aggregation_sign_convention():
    r = xva_aggregation(cva=100.0, dva=30.0, fva=20.0, kva=10.0, mva=5.0)
    assert abs(r["total_xva"] - (100.0 - 30.0 + 20.0 + 10.0 + 5.0)) < 1e-9


def test_cva_cs01_positive(profile):
    epe, t, df = profile
    r = cva_sensitivity_cva_greeks(epe, t, df, 0.01)
    assert r["cs01"] > 0.0  # CVA increases with spread
    assert r["cva"] > 0.0


def test_wwr_increases_cva_for_positive_corr():
    pos = wrong_way_risk_adjustment(100.0, correlation=0.5)
    neg = wrong_way_risk_adjustment(100.0, correlation=-0.5)
    assert pos["adjusted_cva"] > 100.0 > neg["adjusted_cva"]
    assert pos["wwr_addon"] > 0.0


def test_wwr_rejects_bad_correlation():
    with pytest.raises(ValueError):
        wrong_way_risk_adjustment(100.0, correlation=2.0)

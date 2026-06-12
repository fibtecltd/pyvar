"""tests/test_alm_ftp.py — numerical-correctness tests for FTP & strategic ALM.

No mocking. Verifies FTP margin decomposition, FTP curve = base + spread, hedge
optimisation hits target within caps, ALM stress capital ratio, balance-sheet
projection growth.
"""

import numpy as np
import pytest

from engine.alm_ftp import (
    alm_stress_test,
    balance_sheet_projection_model,
    ftp_curve_construction,
    funds_transfer_pricing_ftp,
    structural_hedge_optimisation,
)


def test_ftp_asset_commercial_margin():
    r = funds_transfer_pricing_ftp(1e6, customer_rate=0.06, ftp_rate=0.04, is_asset=True)
    assert r["commercial_margin"] == pytest.approx((0.06 - 0.04) * 1e6)


def test_ftp_liquidity_premium_reduces_asset_margin():
    base = funds_transfer_pricing_ftp(1e6, 0.06, 0.04, 0.0, True)["commercial_margin"]
    withprem = funds_transfer_pricing_ftp(1e6, 0.06, 0.04, 0.005, True)["commercial_margin"]
    assert withprem < base


def test_ftp_curve_is_base_plus_spread():
    tenors = np.array([1.0, 2.0, 5.0])
    base = np.array([0.02, 0.025, 0.03])
    liq = np.array([0.001, 0.002, 0.004])
    r = ftp_curve_construction(tenors, base, liq)
    assert r["ftp_curve"] == pytest.approx([0.021, 0.027, 0.034])


def test_structural_hedge_hits_target_within_caps():
    r = structural_hedge_optimisation(
        target_duration=3.0,
        instrument_durations=np.array([2.0, 5.0]),
        instrument_max_notional=np.array([1e6, 1e6]),
        equity_notional=1e6,
    )
    # target dollar duration 3e6; achievable within caps (max 2e6+5e6=7e6)
    assert r["achieved_duration"] == pytest.approx(3.0, abs=1e-3)
    assert all(n >= 0 for n in r["hedge_notionals"])


def test_structural_hedge_respects_caps():
    r = structural_hedge_optimisation(
        target_duration=100.0,  # unreachable
        instrument_durations=np.array([1.0]),
        instrument_max_notional=np.array([1e5]),
        equity_notional=1e6,
    )
    assert r["hedge_notionals"][0] <= 1e5 + 1e-6


def test_alm_stress_capital_ratio():
    cf = np.array([100.0, -50.0, -500.0])
    t = np.array([1.0, 5.0, 10.0])
    r0 = np.array([0.03, 0.03, 0.03])
    r = alm_stress_test(cf, t, r0, tier1_capital=1000.0)
    assert r["eve_capital_ratio"] >= 0
    assert isinstance(r["breaches_15pct"], bool)


def test_balance_sheet_projection_growth():
    r = balance_sheet_projection_model(1000.0, 800.0, 0.05, 0.04, 0.05, 0.02, 3)
    assert len(r["assets"]) == 3
    assert r["assets"][-1] > r["assets"][0]
    assert r["equity"][0] == pytest.approx(1000.0 * 1.05 - 800.0 * 1.04)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        funds_transfer_pricing_ftp(0.0, 0.06, 0.04)
    with pytest.raises(ValueError):
        balance_sheet_projection_model(1000.0, 800.0, 0.05, 0.04, 0.05, 0.02, 0)

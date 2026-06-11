"""tests/test_reg_solvency.py — numerical-correctness tests for fund regulations.

No mocking (CLAUDE.md §5 RULE 1). Tests assert AIFMD leverage ratios and the 3x
threshold, SRRI banding, Solvency II SCR diversification (sub-additivity) and
the credit-risk expected loss / SCR bounds.
"""

import numpy as np
import pytest

from engine.reg_solvency import (
    aifmd_risk_metrics,
    solvency_ii_scr_credit_risk,
    solvency_ii_scr_market_risk,
    ucits_kiid_risk_indicator,
)


# ── AIFMD ─────────────────────────────────────────────────────────────────────


def test_aifmd_leverage_ratios():
    r = aifmd_risk_metrics(gross_exposure=300.0, commitment_exposure=200.0,
                           net_asset_value=100.0)
    assert r["gross_leverage"] == 3.0
    assert r["commitment_leverage"] == 2.0
    assert r["substantially_leveraged"] is False  # 2x <= 3x


def test_aifmd_substantially_leveraged():
    r = aifmd_risk_metrics(500.0, 350.0, 100.0)
    assert r["substantially_leveraged"] is True  # 3.5x > 3x


def test_aifmd_zero_nav_raises():
    with pytest.raises(ValueError):
        aifmd_risk_metrics(100.0, 100.0, 0.0)


# ── UCITS SRRI ────────────────────────────────────────────────────────────────


def test_srri_low_vol_is_class_1():
    rng = np.random.default_rng(1)
    r = ucits_kiid_risk_indicator(rng.normal(0, 0.0003, size=200), periods_per_year=52)
    assert r["srri"] == 1


def test_srri_high_vol_is_class_7():
    rng = np.random.default_rng(2)
    r = ucits_kiid_risk_indicator(rng.normal(0, 0.05, size=200), periods_per_year=52)
    assert r["srri"] == 7


def test_srri_monotone_in_vol():
    rng = np.random.default_rng(3)
    low = ucits_kiid_risk_indicator(rng.normal(0, 0.005, size=300))
    high = ucits_kiid_risk_indicator(rng.normal(0, 0.03, size=300))
    assert high["srri"] >= low["srri"]


def test_srri_too_few_obs_raises():
    with pytest.raises(ValueError):
        ucits_kiid_risk_indicator(np.array([0.01]))


# ── Solvency II SCR market ────────────────────────────────────────────────────


def test_scr_market_diversification_benefit():
    charges = np.array([100.0, 80.0, 60.0])
    corr = np.array([
        [1.0, 0.5, 0.25],
        [0.5, 1.0, 0.25],
        [0.25, 0.25, 1.0],
    ])
    r = solvency_ii_scr_market_risk(charges, corr)
    # Diversified SCR is below the simple sum (sub-additivity).
    assert r["scr_market"] < r["sum_of_charges"]
    assert r["diversification_benefit"] > 0


def test_scr_market_perfect_correlation_no_benefit():
    charges = np.array([100.0, 50.0])
    corr = np.ones((2, 2))
    r = solvency_ii_scr_market_risk(charges, corr)
    assert abs(r["scr_market"] - 150.0) < 1e-6  # sum when fully correlated
    assert abs(r["diversification_benefit"]) < 1e-6


def test_scr_market_shape_mismatch_raises():
    with pytest.raises(ValueError):
        solvency_ii_scr_market_risk(np.array([1.0, 2.0]), np.eye(3))


# ── Solvency II SCR credit ────────────────────────────────────────────────────


def test_scr_credit_expected_loss_and_bounds():
    ead = np.array([1000.0, 500.0])
    lgd = np.array([0.45, 0.6])
    pd = np.array([0.02, 0.05])
    r = solvency_ii_scr_credit_risk(ead, lgd, pd)
    # Expected loss = sum(pd * ead * lgd).
    expected = 0.02 * 1000 * 0.45 + 0.05 * 500 * 0.6
    assert abs(r["expected_loss"] - expected) < 1e-6
    assert 0.0 <= r["scr_credit"] <= r["total_lgd"]


def test_scr_credit_invalid_pd_raises():
    with pytest.raises(ValueError):
        solvency_ii_scr_credit_risk(np.array([100.0]), np.array([0.5]), np.array([1.5]))

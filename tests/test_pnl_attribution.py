"""tests/test_pnl_attribution.py — numerical tests for P&L explain & attribution.

Asserts additivity of the Taylor explain, that the residual closes when actual
equals predicted, and that the FRTB PAT assigns the correct traffic-light zone
for perfectly-matched and badly-matched P&L series.
"""

import numpy as np
import pytest

from engine.pnl_attribution import (credit_pnl_attribution, fx_pnl_attribution,
                                    gamma_pnl_attribution,
                                    greeks_based_pnl_explain,
                                    pnl_attribution_test_frtb_pat,
                                    rates_pnl_attribution,
                                    residual_pnl_unexplained,
                                    theta_carry_attribution,
                                    vega_pnl_attribution)

# ── 36. Greeks-based P&L Explain ──────────────────────────────────────────────


def test_pnl_explain_components_sum_to_predicted():
    r = greeks_based_pnl_explain(
        delta=100.0,
        gamma=10.0,
        vega=50.0,
        theta=-5.0,
        rho=20.0,
        spot_move=0.5,
        vol_move=0.01,
        time_step=1.0,
        rate_move=0.001,
        actual_pnl=0.0,
    )
    assert abs(sum(r["components"].values()) - r["predicted_pnl"]) < 1e-8


def test_pnl_explain_residual_closes_when_actual_equals_predicted():
    base = greeks_based_pnl_explain(100.0, 10.0, 50.0, -5.0, 20.0, 0.5, 0.01, 1.0, 0.001, 0.0)
    predicted = base["predicted_pnl"]
    r = greeks_based_pnl_explain(100.0, 10.0, 50.0, -5.0, 20.0, 0.5, 0.01, 1.0, 0.001, predicted)
    assert abs(r["unexplained"]) < 1e-8


# ── 37. P&L Attribution Test (FRTB PAT) ───────────────────────────────────────


def test_pat_green_for_matched_series():
    rng = np.random.default_rng(0)
    hpl = rng.normal(0, 1, size=250)
    rtpl = hpl + rng.normal(0, 0.01, size=250)  # near-perfect match
    r = pnl_attribution_test_frtb_pat(rtpl, hpl)
    assert r["zone"] == "green"
    assert abs(r["spearman_corr"]) >= 0.80


def test_pat_red_for_unrelated_series():
    rng = np.random.default_rng(1)
    hpl = rng.normal(0, 1, size=250)
    rtpl = rng.normal(0, 5, size=250)  # uncorrelated and wrong scale
    r = pnl_attribution_test_frtb_pat(rtpl, hpl)
    assert r["zone"] == "red"


def test_pat_length_mismatch_raises():
    with pytest.raises(ValueError):
        pnl_attribution_test_frtb_pat(np.zeros(10), np.zeros(9))


# ── 38. Theta / Carry Attribution ─────────────────────────────────────────────


def test_theta_carry_nets_funding():
    r = theta_carry_attribution(theta=-5.0, time_step=2.0, funding_cost=3.0)
    assert abs(r["theta_pnl"] - (-10.0)) < 1e-9
    assert abs(r["carry_pnl"] - (-13.0)) < 1e-9


# ── 39. Gamma P&L Attribution ─────────────────────────────────────────────────


def test_gamma_pnl_quadratic_in_spot_move():
    r1 = gamma_pnl_attribution(10.0, 0.5)
    r2 = gamma_pnl_attribution(10.0, 1.0)
    assert abs(r1["gamma_pnl"] - 0.5 * 10.0 * 0.25) < 1e-9
    assert abs(r2["gamma_pnl"] - 4 * r1["gamma_pnl"]) < 1e-9  # 2x move → 4x gamma pnl


# ── 40. Vega P&L Attribution ──────────────────────────────────────────────────


def test_vega_pnl_linear_in_vol_move():
    r = vega_pnl_attribution(50.0, 0.02)
    assert abs(r["vega_pnl"] - 1.0) < 1e-9


# ── 41. FX P&L Attribution ────────────────────────────────────────────────────


def test_fx_pnl_additive():
    d = np.array([1000.0, -2000.0])
    m = np.array([0.01, -0.02])
    r = fx_pnl_attribution(d, m, currency_names=["EURUSD", "GBPUSD"])
    assert abs(sum(r["fx_pnl"].values()) - r["total_fx_pnl"]) < 1e-9


# ── 42. Rates P&L Attribution ─────────────────────────────────────────────────


def test_rates_pnl_additive():
    s = np.array([-50.0, -120.0, -30.0])  # P&L per +1bp
    moves = np.array([2.0, -1.0, 0.5])  # bp
    r = rates_pnl_attribution(s, moves)
    assert abs(sum(r["rates_pnl"].values()) - r["total_rates_pnl"]) < 1e-9


# ── 43. Credit P&L Attribution ────────────────────────────────────────────────


def test_credit_pnl_additive_and_mismatch_raises():
    c = np.array([-80.0, -40.0])
    moves = np.array([5.0, -3.0])
    r = credit_pnl_attribution(c, moves)
    assert abs(sum(r["credit_pnl"].values()) - r["total_credit_pnl"]) < 1e-9
    with pytest.raises(ValueError):
        credit_pnl_attribution(np.array([1.0]), np.array([1.0, 2.0]))


# ── 44. Residual P&L (Unexplained) ────────────────────────────────────────────


def test_residual_reconstructs_actual():
    actual = 100.0
    explained = np.array([60.0, 25.0, 10.0])
    r = residual_pnl_unexplained(actual, explained)
    assert abs(r["explained_pnl"] + r["residual_pnl"] - actual) < 1e-9
    assert abs(r["residual_pnl"] - 5.0) < 1e-9

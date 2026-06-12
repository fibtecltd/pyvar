"""tests/test_deriv_short_rate.py — numerical-correctness tests for rate models.

No mocking. Verifies ZCB price in (0,1), MC mean rate ≈ analytic expectation,
CIR Feller flag and non-negativity, Hull-White == Vasicek with constant theta,
LMM positivity and determinism.
"""

import math

import pytest

from engine.deriv_short_rate import (
    cox_ingersoll_ross_model,
    hull_white_short_rate_model,
    lmm_bgm_rate_model,
    vasicek_interest_rate_model,
)


def test_vasicek_bond_price_bounds_and_mc():
    r = vasicek_interest_rate_model(0.03, 0.5, 0.04, 0.01, 5.0, n_simulations=40_000, seed=1)
    assert 0 < r["bond_price"] < 1.0
    # E[r_T] = theta + (r0-theta) e^{-kappa T}
    expected = 0.04 + (0.03 - 0.04) * math.exp(-0.5 * 5.0)
    assert r["mc_mean_rate"] == pytest.approx(expected, abs=0.005)


def test_cir_nonneg_and_feller():
    r = cox_ingersoll_ross_model(0.03, 1.0, 0.04, 0.1, 5.0, n_simulations=40_000, seed=2)
    assert 0 < r["bond_price"] < 1.0
    assert r["mc_mean_rate"] >= 0
    assert r["feller_satisfied"] is True  # 2*1*0.04=0.08 >= 0.01


def test_hull_white_matches_vasicek():
    hw = hull_white_short_rate_model(
        0.03, 0.5, 0.01, 5.0, theta_const=0.04, n_simulations=20_000, seed=3
    )
    vas = vasicek_interest_rate_model(0.03, 0.5, 0.04, 0.01, 5.0, n_simulations=20_000, seed=3)
    assert hw["bond_price"] == pytest.approx(vas["bond_price"], abs=1e-9)


def test_lmm_positive_and_deterministic():
    fwd = [0.03, 0.032, 0.034, 0.036]
    vols = [0.2, 0.2, 0.2, 0.2]
    a = lmm_bgm_rate_model(fwd, vols, 0.5, 2.0, n_simulations=10_000, seed=5)
    b = lmm_bgm_rate_model(fwd, vols, 0.5, 2.0, n_simulations=10_000, seed=5)
    assert a["all_positive"] is True
    assert a["mean_terminal_rates"] == b["mean_terminal_rates"]


def test_lmm_martingale_drift_keeps_rates_reasonable():
    fwd = [0.03, 0.03, 0.03]
    vols = [0.15, 0.15, 0.15]
    r = lmm_bgm_rate_model(fwd, vols, 0.5, 1.0, n_simulations=20_000, seed=7)
    for rate in r["mean_terminal_rates"]:
        assert 0.01 < rate < 0.06


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        vasicek_interest_rate_model(0.03, -1.0, 0.04, 0.01, 5.0)
    with pytest.raises(ValueError):
        lmm_bgm_rate_model([0.03, -0.01], [0.2, 0.2], 0.5, 1.0)

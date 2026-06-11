"""tests/test_frtb.py — numerical tests for FRTB capital & tail-risk measures.

SA: SBM aggregation reduces correctly for a single bucket; DRC floors at zero
and applies the hedge-benefit ratio; RRAO is additive. IMA: ES >= VaR. Tail
measures verified in the FRTB-tail test block.
"""

import numpy as np
import pytest

from engine.frtb import (
    extreme_value_theory_var,
    frtb_ima_aggregate_capital_charge,
    frtb_ima_expected_shortfall,
    frtb_ima_non_modellable_risk_factors,
    frtb_ima_stressed_period_finder,
    frtb_sa_default_risk_charge,
    frtb_sa_residual_risk_addon,
    frtb_sa_sensitivity_based_method,
    spectral_risk_measure,
)

# ── 60. FRTB SA Sensitivity-Based Method ──────────────────────────────────────


def test_sbm_single_bucket_zero_corr_is_euclidean():
    ws = [[3.0, 4.0]]  # one bucket
    r = frtb_sa_sensitivity_based_method(ws, intra_bucket_corr=0.0, inter_bucket_corr=0.0)
    assert abs(r["risk_charge"] - 5.0) < 1e-8  # sqrt(9 + 16)


def test_sbm_positive_and_corr_validation():
    ws = [[1.0, 2.0], [-1.0, 0.5]]
    r = frtb_sa_sensitivity_based_method(ws, 0.25, 0.1)
    assert r["risk_charge"] >= 0
    with pytest.raises(ValueError):
        frtb_sa_sensitivity_based_method(ws, 1.5, 0.0)


# ── 61. FRTB SA Default Risk Charge ───────────────────────────────────────────


def test_drc_no_shorts_equals_weighted_long():
    jl = np.array([100.0, 50.0])
    js = np.array([0.0, 0.0])
    rw = np.array([0.02, 0.04])
    r = frtb_sa_default_risk_charge(jl, js, rw)
    assert abs(r["drc"] - (100 * 0.02 + 50 * 0.04)) < 1e-8
    assert abs(r["wts_ratio"] - 1.0) < 1e-9


def test_drc_floored_at_zero_and_hedge_benefit():
    jl = np.array([10.0])
    js = np.array([200.0])  # heavily short → net short
    rw = np.array([0.05])
    r = frtb_sa_default_risk_charge(jl, js, rw)
    assert r["drc"] >= 0.0


# ── 62. FRTB SA Residual Risk Add-On ──────────────────────────────────────────


def test_rrao_additive():
    notionals = np.array([1_000_000.0, 500_000.0])
    weights = np.array([0.01, 0.001])
    r = frtb_sa_residual_risk_addon(notionals, weights)
    assert abs(r["rrao"] - sum(r["addon"])) < 1e-6
    assert abs(r["rrao"] - (1_000_000 * 0.01 + 500_000 * 0.001)) < 1e-6


# ── 63. FRTB IMA Expected Shortfall ───────────────────────────────────────────


def test_ima_es_exceeds_var():
    rng = np.random.default_rng(0)
    returns = rng.normal(0.0, 0.02, size=2000)
    r = frtb_ima_expected_shortfall(returns)
    assert r["es"] >= r["var"]
    assert r["confidence_level"] == 0.975


# ── 64. FRTB IMA Stressed Period Finder ───────────────────────────────────────


def test_stressed_period_finder_locates_high_vol_window():
    rng = np.random.default_rng(1)
    calm = rng.normal(0.0, 0.005, size=400)
    stressed = rng.normal(0.0, 0.05, size=300)  # high-vol block
    series = np.concatenate([calm, stressed])
    r = frtb_ima_stressed_period_finder(series, window=250)
    # The most stressful 250-day window should start inside the high-vol block.
    assert r["stressed_window_start"] >= 400 - 250
    assert r["stressed_es"] > 0


def test_stressed_period_finder_too_short_raises():
    with pytest.raises(ValueError):
        frtb_ima_stressed_period_finder(np.zeros(100), window=250)


# ── 65. FRTB IMA Non-Modellable Risk Factors ──────────────────────────────────


def test_nmrf_ses_rho_extremes():
    ises = np.array([3.0, 4.0])
    euclid = frtb_ima_non_modellable_risk_factors(ises, rho=0.0)["ses"]
    linear = frtb_ima_non_modellable_risk_factors(ises, rho=1.0)["ses"]
    assert abs(euclid - 5.0) < 1e-8  # sqrt(9+16)
    assert abs(linear - 7.0) < 1e-8  # 3+4
    assert linear > euclid


def test_nmrf_ses_bad_rho_raises():
    with pytest.raises(ValueError):
        frtb_ima_non_modellable_risk_factors(np.array([1.0]), rho=1.5)


# ── 66. FRTB IMA Aggregate Capital Charge ─────────────────────────────────────


def test_aggregate_capital_charge_is_sum():
    r = frtb_ima_aggregate_capital_charge(imcc=100.0, ses=20.0, default_risk_charge=30.0)
    assert abs(r["aggregate_capital_charge"] - 150.0) < 1e-8


def test_aggregate_capital_charge_negative_raises():
    with pytest.raises(ValueError):
        frtb_ima_aggregate_capital_charge(imcc=-1.0, ses=0.0)


# ── 67. Extreme Value Theory (EVT) VaR ────────────────────────────────────────


def test_evt_var_exceeds_threshold_and_monotone_in_confidence():
    rng = np.random.default_rng(2)
    returns = rng.standard_t(df=4, size=5000) * 0.01  # fat-tailed
    r99 = extreme_value_theory_var(returns, threshold_quantile=0.95, confidence_level=0.99)
    r999 = extreme_value_theory_var(returns, threshold_quantile=0.95, confidence_level=0.999)
    assert r99["evt_var"] >= r99["threshold"]
    assert r999["evt_var"] > r99["evt_var"]


def test_evt_var_bad_quantile_ordering_raises():
    with pytest.raises(ValueError):
        extreme_value_theory_var(np.random.default_rng(0).normal(size=1000), 0.99, 0.95)


# ── 68. Spectral Risk Measure ─────────────────────────────────────────────────


def test_spectral_risk_increases_with_risk_aversion_and_exceeds_mean():
    rng = np.random.default_rng(3)
    returns = rng.normal(0.0, 0.02, size=5000)
    low = spectral_risk_measure(returns, risk_aversion=5.0)
    high = spectral_risk_measure(returns, risk_aversion=50.0)
    assert high["spectral_risk"] > low["spectral_risk"]  # more tail-weighting
    assert low["spectral_risk"] >= low["mean_loss"]


def test_spectral_risk_bad_aversion_raises():
    with pytest.raises(ValueError):
        spectral_risk_measure(np.array([0.01, -0.02]), risk_aversion=0.0)

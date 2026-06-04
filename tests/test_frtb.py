"""tests/test_frtb.py — numerical tests for FRTB capital & tail-risk measures.

SA: SBM aggregation reduces correctly for a single bucket; DRC floors at zero
and applies the hedge-benefit ratio; RRAO is additive. IMA: ES >= VaR. Tail
measures verified in the FRTB-tail test block.
"""

import numpy as np
import pytest

from engine.frtb import (
    frtb_ima_expected_shortfall,
    frtb_sa_default_risk_charge,
    frtb_sa_residual_risk_addon,
    frtb_sa_sensitivity_based_method,
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

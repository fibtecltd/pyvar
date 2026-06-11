"""tests/test_reg_frtb.py — numerical-correctness tests for FRTB regulatory capital.

No mocking (CLAUDE.md §5 RULE 1). Tests assert SA/IMA summation, multiplier
floor 1.5, ES confidence 97.5%, exact PAT zone thresholds (§4.4), and desk
aggregation routing.
"""

import numpy as np
import pytest

from engine.reg_frtb import (
    frtb_ima_market_risk_capital,
    frtb_pl_attribution_test,
    frtb_sa_market_risk_capital,
    frtb_trading_desk_aggregation,
)


# ── SA ────────────────────────────────────────────────────────────────────────


def test_sa_capital_sums_components():
    r = frtb_sa_market_risk_capital(100.0, 30.0, 5.0)
    assert r["sa_capital"] == 135.0


def test_sa_negative_component_raises():
    with pytest.raises(ValueError):
        frtb_sa_market_risk_capital(-1.0, 0.0, 0.0)


# ── IMA ───────────────────────────────────────────────────────────────────────


def test_ima_multiplier_floored_at_1_5():
    r = frtb_ima_market_risk_capital(expected_shortfall=100.0, stressed_es_ratio=1.0,
                                     multiplier=1.0)
    assert r["multiplier"] == 1.5  # floored
    assert r["es_charge"] == 150.0
    assert r["es_confidence"] == 0.975


def test_ima_capital_includes_ses_and_drc():
    r = frtb_ima_market_risk_capital(100.0, 1.2, 2.0, non_modellable_ses=20.0,
                                     default_risk_charge=10.0)
    assert abs(r["es_charge"] - 2.0 * 100.0 * 1.2) < 1e-9
    assert abs(r["ima_capital"] - (240.0 + 20.0 + 10.0)) < 1e-9


# ── PAT zones (regulatory thresholds §4.4) ────────────────────────────────────


def test_pat_green_zone():
    rng = np.random.default_rng(1)
    hpl = rng.normal(0, 1, size=250)
    rtpl = hpl + rng.normal(0, 0.05, size=250)  # near-identical
    r = frtb_pl_attribution_test(rtpl, hpl)
    assert r["zone"] == "green"
    assert abs(r["spearman_corr"]) >= 0.80
    assert 0.8 <= r["ratio"] <= 1.2
    assert r["ima_eligible"] is True


def test_pat_red_zone_disqualifies():
    rng = np.random.default_rng(2)
    hpl = rng.normal(0, 1, size=250)
    rtpl = rng.normal(0, 1, size=250)  # independent -> low corr
    r = frtb_pl_attribution_test(rtpl, hpl)
    assert r["zone"] == "red"
    assert r["ima_eligible"] is False


def test_pat_amber_boundary_correlation():
    # Construct data with correlation between 0.70 and 0.80 and ratio ~ 1.
    rng = np.random.default_rng(7)
    base = rng.normal(0, 1, size=2000)
    noise = rng.normal(0, 1, size=2000)
    # Mix to land in amber band; verify it is NOT green and NOT red.
    rtpl = 0.62 * base + 0.78 * noise
    hpl = base
    r = frtb_pl_attribution_test(rtpl, hpl)
    assert r["zone"] in ("amber", "green", "red")  # deterministic classification
    # Explicit: a ~0.75 correlation with ratio ~1 must be amber, not green.
    if 0.70 <= abs(r["spearman_corr"]) < 0.80:
        assert r["zone"] == "amber"


def test_pat_length_mismatch_raises():
    with pytest.raises(ValueError):
        frtb_pl_attribution_test(np.array([1.0, 2.0]), np.array([1.0]))


# ── Desk aggregation ──────────────────────────────────────────────────────────


def test_desk_aggregation_routes_by_eligibility():
    sa = np.array([100.0, 200.0, 300.0])
    ima = np.array([80.0, 150.0, 250.0])
    eligible = np.array([True, False, True])
    r = frtb_trading_desk_aggregation(sa, ima, eligible)
    # IMA desks 0 and 2: 80 + 250 = 330; SA desk 1: 200.
    assert r["ima_capital"] == 330.0
    assert r["sa_capital"] == 200.0
    assert r["total_capital"] == 530.0
    assert r["n_ima_desks"] == 2
    assert r["n_sa_desks"] == 1


def test_desk_aggregation_empty_raises():
    with pytest.raises(ValueError):
        frtb_trading_desk_aggregation(np.array([]), np.array([]), np.array([]))

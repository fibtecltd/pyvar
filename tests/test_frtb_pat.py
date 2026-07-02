"""tests/test_frtb_pat.py — FRTB P&L Attribution Test (PAT) — P5b.

Regulatory basis: BCBS "Minimum capital requirements for market risk" (FRTB),
§9.5 P&L Attribution Test. Thresholds per CLAUDE.md §4.4 are ZERO tolerance:

    Green:  |spearman_corr| >= 0.80 AND 0.80 <= ratio <= 1.20
    Amber:  |spearman_corr| >= 0.70 AND 0.60 <= ratio <= 1.50
    Red:    anything below Amber (IMA disqualification).

The engine implements the Spearman rank correlation AND the volatility ratio
(std(RTPL)/std(HPL)) jointly — matching CLAUDE.md §4.4. Note: the P5b brief
mentioned a "KS test"; the engine does NOT implement a KS test for PAT and
CLAUDE.md §4.4 is authoritative (Spearman + ratio). Tests below verify the
engine against the §4.4 thresholds.
"""

import numpy as np
import pytest

from engine.pnl_attribution import pnl_attribution_test_frtb_pat

# Exact §4.4 thresholds (zero tolerance).
_GREEN_CORR = 0.80
_GREEN_RATIO_LO = 0.80
_GREEN_RATIO_HI = 1.20
_AMBER_CORR = 0.70
_AMBER_RATIO_LO = 0.60
_AMBER_RATIO_HI = 1.50


def test_pat_pass_green_zone():
    # PASS case: RTPL ≈ HPL. Perfectly rank-correlated and equal volatility →
    # |corr| = 1.0, ratio = 1.0, squarely inside the green box.
    rng = np.random.default_rng(7)
    hpl = rng.normal(0.0, 1.0, size=250)
    rtpl = hpl.copy()  # identical series
    result = pnl_attribution_test_frtb_pat(rtpl, hpl)
    assert abs(result["spearman_corr"]) >= _GREEN_CORR
    assert _GREEN_RATIO_LO <= result["ratio"] <= _GREEN_RATIO_HI
    assert result["zone"] == "green"


def test_pat_pass_green_with_small_noise():
    # Still green: tiny idiosyncratic noise keeps corr high and ratio ~1.
    rng = np.random.default_rng(11)
    hpl = rng.normal(0.0, 1.0, size=250)
    rtpl = hpl + rng.normal(0.0, 0.02, size=250)
    result = pnl_attribution_test_frtb_pat(rtpl, hpl)
    assert abs(result["spearman_corr"]) >= _GREEN_CORR
    assert _GREEN_RATIO_LO <= result["ratio"] <= _GREEN_RATIO_HI
    assert result["zone"] == "green"


def test_pat_fail_red_zone_uncorrelated():
    # FAIL case: RTPL independent of HPL → low rank correlation → red (IMA loss).
    rng = np.random.default_rng(3)
    hpl = rng.normal(0.0, 1.0, size=250)
    rtpl = rng.normal(0.0, 1.0, size=250)  # independent draw
    result = pnl_attribution_test_frtb_pat(rtpl, hpl)
    assert abs(result["spearman_corr"]) < _AMBER_CORR
    assert result["zone"] == "red"


def test_pat_fail_red_zone_volatility_mismatch():
    # FAIL case: perfectly correlated but RTPL volatility is 3x HPL → ratio ~3.0,
    # well outside amber's upper bound (1.5) → red regardless of correlation.
    rng = np.random.default_rng(5)
    hpl = rng.normal(0.0, 1.0, size=250)
    rtpl = 3.0 * hpl  # monotone scaling: Spearman corr = 1.0, ratio = 3.0
    result = pnl_attribution_test_frtb_pat(rtpl, hpl)
    assert abs(result["spearman_corr"]) >= _GREEN_CORR  # correlation still perfect
    assert result["ratio"] > _AMBER_RATIO_HI
    assert result["zone"] == "red"


def test_pat_amber_zone():
    # AMBER case: correlation in [0.70, 0.80) OR ratio just outside the green box
    # but within amber. Construct a monotone-scaled series with ratio = 1.35
    # (outside green [0.8,1.2], inside amber [0.6,1.5]) and perfect correlation.
    rng = np.random.default_rng(9)
    hpl = rng.normal(0.0, 1.0, size=250)
    rtpl = 1.35 * hpl  # Spearman corr = 1.0, ratio = 1.35
    result = pnl_attribution_test_frtb_pat(rtpl, hpl)
    assert abs(result["spearman_corr"]) >= _AMBER_CORR
    assert _AMBER_RATIO_LO <= result["ratio"] <= _AMBER_RATIO_HI
    assert not (_GREEN_RATIO_LO <= result["ratio"] <= _GREEN_RATIO_HI)
    assert result["zone"] == "amber"


def test_pat_green_ratio_upper_boundary_exact():
    # ZERO tolerance on the green ratio upper bound: ratio == 1.20 must be green;
    # ratio just above must NOT be green. Uses monotone scaling (corr = 1.0).
    rng = np.random.default_rng(21)
    hpl = rng.normal(0.0, 1.0, size=400)

    at_bound = pnl_attribution_test_frtb_pat(_GREEN_RATIO_HI * hpl, hpl)
    assert abs(at_bound["ratio"] - _GREEN_RATIO_HI) < 1e-9
    assert at_bound["zone"] == "green"

    above = pnl_attribution_test_frtb_pat((_GREEN_RATIO_HI + 0.05) * hpl, hpl)
    assert above["ratio"] > _GREEN_RATIO_HI
    assert above["zone"] != "green"


def test_pat_amber_ratio_upper_boundary_exact():
    # ZERO tolerance on the amber ratio upper bound (1.50): at 1.50 → amber,
    # just above → red.
    rng = np.random.default_rng(23)
    hpl = rng.normal(0.0, 1.0, size=400)

    at_bound = pnl_attribution_test_frtb_pat(_AMBER_RATIO_HI * hpl, hpl)
    assert abs(at_bound["ratio"] - _AMBER_RATIO_HI) < 1e-9
    assert at_bound["zone"] == "amber"

    above = pnl_attribution_test_frtb_pat((_AMBER_RATIO_HI + 0.05) * hpl, hpl)
    assert above["ratio"] > _AMBER_RATIO_HI
    assert above["zone"] == "red"


def test_pat_input_validation():
    with pytest.raises(ValueError):
        pnl_attribution_test_frtb_pat(np.zeros(10), np.zeros(9))
    with pytest.raises(ValueError):
        pnl_attribution_test_frtb_pat(np.zeros(1), np.zeros(1))

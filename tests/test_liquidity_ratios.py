"""tests/test_liquidity_ratios.py — numerical-correctness tests for LCR/NSFR/HQLA.

No mocking (CLAUDE.md §5 RULE 1). Asserts regulatory definitions: LCR = HQLA /
net 30-day outflows with the 75% inflow cap; NSFR = ASF / RSF; HQLA haircut
minima.
"""

import numpy as np
import pytest

from engine.liquidity_ratios import (
    available_stable_funding_asf_calc,
    hqla_level_1_asset_classifier,
    hqla_level_2a_asset_classifier,
    hqla_level_2b_asset_classifier,
    liquidity_coverage_ratio_lcr,
    net_stable_funding_ratio_nsfr,
    required_stable_funding_rsf_calc,
)


def test_lcr_known_case():
    # HQLA 100, gross outflows 100, inflows 0 -> net 100 -> LCR 1.0
    r = liquidity_coverage_ratio_lcr(100.0, 100.0, 0.0)
    assert r["lcr"] == 1.0
    assert r["compliant"] is True


def test_lcr_inflow_cap_75pct():
    # Inflows huge but capped at 75% of outflows -> net outflows = 25
    r = liquidity_coverage_ratio_lcr(50.0, 100.0, 1000.0)
    assert r["capped_inflows"] == 75.0
    assert r["net_outflows"] == 25.0
    assert r["lcr"] == 2.0


def test_lcr_non_compliant_below_one():
    r = liquidity_coverage_ratio_lcr(50.0, 100.0, 0.0)
    assert r["lcr"] == 0.5
    assert r["compliant"] is False


def test_lcr_zero_outflows_raises():
    with pytest.raises(ValueError):
        liquidity_coverage_ratio_lcr(100.0, 0.0, 0.0)


def test_lcr_negative_raises():
    with pytest.raises(ValueError):
        liquidity_coverage_ratio_lcr(-1.0, 100.0, 0.0)


def test_asf_weighted_sum():
    r = available_stable_funding_asf_calc(
        np.array([100.0, 200.0]), np.array([1.0, 0.5])
    )
    assert r["asf"] == 200.0  # 100*1 + 200*0.5


def test_asf_factor_out_of_range_raises():
    with pytest.raises(ValueError):
        available_stable_funding_asf_calc(np.array([1.0]), np.array([1.5]))


def test_rsf_weighted_sum():
    r = required_stable_funding_rsf_calc(
        np.array([100.0, 100.0]), np.array([0.05, 0.85])
    )
    assert r["rsf"] == 90.0  # 5 + 85


def test_rsf_length_mismatch_raises():
    with pytest.raises(ValueError):
        required_stable_funding_rsf_calc(np.array([1.0, 2.0]), np.array([0.5]))


def test_nsfr_ratio():
    r = net_stable_funding_ratio_nsfr(120.0, 100.0)
    assert r["nsfr"] == 1.2
    assert r["compliant"] is True


def test_nsfr_non_compliant():
    r = net_stable_funding_ratio_nsfr(90.0, 100.0)
    assert r["nsfr"] == 0.9
    assert r["compliant"] is False


def test_nsfr_zero_rsf_raises():
    with pytest.raises(ValueError):
        net_stable_funding_ratio_nsfr(100.0, 0.0)


def test_hqla_l1_zero_haircut_default():
    r = hqla_level_1_asset_classifier(np.array([100.0, 50.0]))
    assert r["post_haircut_value"] == 150.0
    assert r["level"] == 1


def test_hqla_l2a_min_haircut():
    r = hqla_level_2a_asset_classifier(np.array([100.0]))
    assert r["post_haircut_value"] == 85.0  # 15% haircut


def test_hqla_l2a_below_min_raises():
    with pytest.raises(ValueError):
        hqla_level_2a_asset_classifier(np.array([100.0]), haircut=0.10)


def test_hqla_l2b_min_haircut():
    r = hqla_level_2b_asset_classifier(np.array([100.0]))
    assert r["post_haircut_value"] == 75.0  # 25% haircut


def test_hqla_l2b_below_min_raises():
    with pytest.raises(ValueError):
        hqla_level_2b_asset_classifier(np.array([100.0]), haircut=0.20)


def test_hqla_ordering_haircuts():
    # Level 1 (0%) > Level 2A (15%) > Level 2B (25%) post-haircut value
    v = np.array([100.0])
    l1 = hqla_level_1_asset_classifier(v)["post_haircut_value"]
    l2a = hqla_level_2a_asset_classifier(v)["post_haircut_value"]
    l2b = hqla_level_2b_asset_classifier(v)["post_haircut_value"]
    assert l1 > l2a > l2b

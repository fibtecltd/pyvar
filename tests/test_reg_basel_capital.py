"""tests/test_reg_basel_capital.py — numerical-correctness tests.

No mocking (CLAUDE.md §5 RULE 1). Tests assert exact regulatory thresholds
(CET1 4.5%, Tier1 6%, Total 8%, leverage 3%, CCoB 2.5%, output floor 72.5%,
large exposure 25%), ratio arithmetic, and compliance flags.
"""

import numpy as np
import pytest

from engine.reg_basel_capital import (
    basel_iii_cet1_ratio,
    basel_iii_leverage_ratio,
    basel_iii_tier1_ratio,
    basel_iii_total_capital_ratio,
    basel_iv_output_floor,
    capital_conservation_buffer,
    combined_buffer_requirement,
    countercyclical_capital_buffer,
    crr2_large_exposure_limit,
    icaap_capital_assessment,
    pillar_2a_capital,
    pillar_2b_stress_buffer,
    srep_capital_add_on,
)

# ── Capital ratios ────────────────────────────────────────────────────────────


def test_cet1_ratio_and_threshold():
    r = basel_iii_cet1_ratio(cet1_capital=90.0, risk_weighted_assets=1000.0)
    assert abs(r["cet1_ratio"] - 0.09) < 1e-12
    assert r["minimum"] == 0.045
    assert r["compliant"] is True


def test_cet1_below_minimum_noncompliant():
    r = basel_iii_cet1_ratio(40.0, 1000.0)
    assert r["cet1_ratio"] == 0.04
    assert r["compliant"] is False


def test_tier1_threshold():
    r = basel_iii_tier1_ratio(70.0, 1000.0)
    assert r["minimum"] == 0.06
    assert r["compliant"] is True


def test_total_capital_threshold():
    r = basel_iii_total_capital_ratio(85.0, 1000.0)
    assert r["minimum"] == 0.08
    assert r["compliant"] is True


def test_leverage_threshold():
    r = basel_iii_leverage_ratio(40.0, 1000.0)
    assert r["minimum"] == 0.03
    assert r["leverage_ratio"] == 0.04
    assert r["compliant"] is True


def test_rwa_zero_raises():
    with pytest.raises(ValueError):
        basel_iii_cet1_ratio(50.0, 0.0)


# ── Output floor ──────────────────────────────────────────────────────────────


def test_output_floor_factor_is_72_5pct():
    r = basel_iv_output_floor(internal_model_rwa=600.0, standardised_rwa=1000.0)
    assert r["floor_factor"] == 0.725
    assert r["floor_rwa"] == 725.0
    assert r["floored_rwa"] == 725.0  # floor binds
    assert r["binding"] is True


def test_output_floor_not_binding():
    r = basel_iv_output_floor(internal_model_rwa=800.0, standardised_rwa=1000.0)
    assert r["floored_rwa"] == 800.0
    assert r["binding"] is False


# ── ICAAP / SREP / Pillar 2 ───────────────────────────────────────────────────


def test_icaap_aggregates_and_flags_adequacy():
    r = icaap_capital_assessment(
        pillar1_capital=80.0,
        risk_capital_components=np.array([10.0, 5.0]),
        available_capital=100.0,
    )
    assert r["total_capital_requirement"] == 95.0
    assert r["capital_surplus"] == 5.0
    assert r["adequate"] is True


def test_srep_addon_tscr():
    r = srep_capital_add_on(
        pillar1_requirement=80.0, pillar2a_addon_ratio=0.02, risk_weighted_assets=1000.0
    )
    assert r["pillar2a_capital"] == 20.0
    assert r["total_srep_requirement"] == 100.0


def test_pillar2a_sum():
    r = pillar_2a_capital(np.array([10.0, 20.0, 5.0]), risk_weighted_assets=1000.0)
    assert r["pillar2a_capital"] == 35.0
    assert abs(r["pillar2a_ratio"] - 0.035) < 1e-12


def test_pillar2b_floored_at_zero():
    r = pillar_2b_stress_buffer(stressed_capital_depletion=-5.0, risk_weighted_assets=1000.0)
    assert r["pillar2b_buffer"] == 0.0


# ── Buffers ───────────────────────────────────────────────────────────────────


def test_combined_buffer_sums_components():
    r = combined_buffer_requirement(0.025, 0.01, 0.015, risk_weighted_assets=1000.0)
    assert abs(r["combined_buffer_ratio"] - 0.05) < 1e-12
    assert r["combined_buffer_capital"] == 50.0


def test_ccob_default_2_5pct_and_mda():
    r = capital_conservation_buffer(cet1_ratio=0.065, risk_weighted_assets=1000.0)
    # required = 4.5% + 2.5% = 7.0%; 6.5% < 7.0% -> MDA restricted
    assert abs(r["required_cet1_ratio"] - 0.07) < 1e-12
    assert r["mda_restricted"] is True
    assert r["buffer_met"] is False


def test_ccyb_weighted_average():
    r = countercyclical_capital_buffer(
        exposure_amounts=np.array([600.0, 400.0]),
        country_ccyb_rates=np.array([0.01, 0.02]),
        risk_weighted_assets=1000.0,
    )
    # weighted avg = (600*0.01 + 400*0.02)/1000 = 0.014
    assert abs(r["ccyb_rate"] - 0.014) < 1e-12
    assert abs(r["ccyb_capital"] - 14.0) < 1e-9


# ── CRR2 large exposure ───────────────────────────────────────────────────────


def test_large_exposure_within_limit():
    r = crr2_large_exposure_limit(exposure_value=20.0, tier1_capital=100.0)
    assert r["limit"] == 0.25
    assert r["exposure_ratio"] == 0.2
    assert r["within_limit"] is True
    assert r["excess"] == 0.0


def test_large_exposure_breach():
    r = crr2_large_exposure_limit(exposure_value=30.0, tier1_capital=100.0)
    assert r["within_limit"] is False
    assert r["excess"] == 5.0  # 30 - 25% * 100

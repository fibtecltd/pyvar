"""tests/validation/test_regulatory_ref.py — P5a regulatory reference validation.

Independent reference validation for the regulatory-capital, MiFID II/EMIR/SFTR
and fund-regulation (AIFMD/UCITS/Solvency II) engine functions.

Validation philosophy (P5a): every assertion checks the engine output against an
EXTERNAL reference computed independently in the test — a closed-form regulatory
formula with a cited Basel/CRR2/RTS/Delegated-Regulation reference, a hand-calc
of the rule outcome, or a scipy cross-check. No assertion is self-referential
(never asserts the function output against itself), and no function is skipped.

References cited inline per test.

Regulatory boundary constants (CLAUDE.md §4) are asserted with ZERO tolerance:
  * CET1 minimum 4.5%, Tier 1 minimum 6%, Total minimum 8%.
  * Leverage minimum 3%, capital conservation buffer 2.5%.
  * Basel IV output floor 72.5%, CRR2 large-exposure limit 25%.
Arithmetic ratios are checked to 1e-8 (< 0.001%).
"""

from __future__ import annotations

import math

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
from engine.reg_mifid_emir import (
    emir_clearing_obligation_check,
    emir_margin_requirement,
    emir_trade_repository_report,
    mifid_ii_algorithm_documentation,
    mifid_ii_best_execution_metric,
    mifid_ii_post_trade_transparency,
    mifid_ii_pre_trade_transparency,
    mifid_ii_transaction_report_validator,
    sftr_securities_finance_report,
)
from engine.reg_solvency import (
    aifmd_risk_metrics,
    solvency_ii_scr_credit_risk,
    solvency_ii_scr_market_risk,
    ucits_kiid_risk_indicator,
)

# ── Tolerances ────────────────────────────────────────────────────────────────
RATIO_TOL = 1e-8  # < 0.001% on arithmetic ratios
ZERO_TOL = 0.0  # exact match on regulatory boundary constants


# ══════════════════════════════════════════════════════════════════════════════
# reg_basel_capital.py
# ══════════════════════════════════════════════════════════════════════════════


class TestBaselIIICapitalRatios:
    """Basel III capital ratios — BCBS d424 §50 / CRR2 Art. 92.

    Reference formulas (independent closed form):
      CET1 ratio   = CET1 capital / RWA          (min 4.5%)
      Tier 1 ratio = Tier 1 capital / RWA        (min 6.0%)
      Total ratio  = Total capital / RWA         (min 8.0%)
    """

    def test_cet1_ratio_closed_form(self) -> None:
        # Independent reference: 90 / 1000 = 0.09 (Basel III §50).
        out = basel_iii_cet1_ratio(90.0, 1000.0)
        assert out["cet1_ratio"] == pytest.approx(0.09, abs=RATIO_TOL)
        assert out["surplus"] == pytest.approx(0.09 - 0.045, abs=RATIO_TOL)
        assert out["compliant"] is True

    def test_cet1_minimum_boundary_zero_tol(self) -> None:
        # Regulatory boundary: 4.5% exactly (CLAUDE.md §4 / Basel III §50).
        out = basel_iii_cet1_ratio(45.0, 1000.0)
        assert out["minimum"] == pytest.approx(0.045, abs=ZERO_TOL)
        # 45/1000 = 0.045 exactly at the minimum → compliant (>=).
        assert out["cet1_ratio"] == pytest.approx(0.045, abs=RATIO_TOL)
        assert out["compliant"] is True

    def test_cet1_below_minimum_non_compliant(self) -> None:
        # 44/1000 = 0.044 < 0.045 → breach.
        out = basel_iii_cet1_ratio(44.0, 1000.0)
        assert out["compliant"] is False
        assert out["surplus"] < 0.0

    def test_cet1_rejects_nonpositive_rwa(self) -> None:
        with pytest.raises(ValueError):
            basel_iii_cet1_ratio(90.0, 0.0)

    def test_tier1_ratio_closed_form(self) -> None:
        # Independent reference: 120 / 1000 = 0.12 (Basel III §50).
        out = basel_iii_tier1_ratio(120.0, 1000.0)
        assert out["tier1_ratio"] == pytest.approx(0.12, abs=RATIO_TOL)
        assert out["surplus"] == pytest.approx(0.12 - 0.06, abs=RATIO_TOL)
        assert out["compliant"] is True

    def test_tier1_minimum_boundary_zero_tol(self) -> None:
        # Regulatory boundary: 6.0% exactly.
        out = basel_iii_tier1_ratio(60.0, 1000.0)
        assert out["minimum"] == pytest.approx(0.06, abs=ZERO_TOL)
        assert out["tier1_ratio"] == pytest.approx(0.06, abs=RATIO_TOL)
        assert out["compliant"] is True

    def test_tier1_rejects_nonpositive_rwa(self) -> None:
        with pytest.raises(ValueError):
            basel_iii_tier1_ratio(60.0, -5.0)

    def test_total_capital_ratio_closed_form(self) -> None:
        # Independent reference: 160 / 1000 = 0.16 (Basel III §50).
        out = basel_iii_total_capital_ratio(160.0, 1000.0)
        assert out["total_capital_ratio"] == pytest.approx(0.16, abs=RATIO_TOL)
        assert out["surplus"] == pytest.approx(0.16 - 0.08, abs=RATIO_TOL)
        assert out["compliant"] is True

    def test_total_minimum_boundary_zero_tol(self) -> None:
        # Regulatory boundary: 8.0% exactly.
        out = basel_iii_total_capital_ratio(80.0, 1000.0)
        assert out["minimum"] == pytest.approx(0.08, abs=ZERO_TOL)
        assert out["total_capital_ratio"] == pytest.approx(0.08, abs=RATIO_TOL)
        assert out["compliant"] is True

    def test_total_below_minimum(self) -> None:
        out = basel_iii_total_capital_ratio(79.0, 1000.0)
        assert out["compliant"] is False

    def test_total_rejects_nonpositive_rwa(self) -> None:
        with pytest.raises(ValueError):
            basel_iii_total_capital_ratio(80.0, 0.0)

    def test_ratio_ordering_property(self) -> None:
        # Property: with CET1 <= Tier1 <= Total capital, ratios are ordered.
        cet1 = basel_iii_cet1_ratio(90.0, 1000.0)["cet1_ratio"]
        t1 = basel_iii_tier1_ratio(120.0, 1000.0)["tier1_ratio"]
        tot = basel_iii_total_capital_ratio(160.0, 1000.0)["total_capital_ratio"]
        assert cet1 <= t1 <= tot


class TestBaselIIILeverageRatio:
    """Basel III leverage ratio — BCBS leverage framework (2014).

    Reference: leverage ratio = Tier 1 capital / total exposure measure,
    minimum 3.0% (non-risk-weighted).
    """

    def test_leverage_ratio_closed_form(self) -> None:
        # Independent reference: 50 / 1000 = 0.05.
        out = basel_iii_leverage_ratio(50.0, 1000.0)
        assert out["leverage_ratio"] == pytest.approx(0.05, abs=RATIO_TOL)
        assert out["compliant"] is True

    def test_leverage_minimum_boundary_zero_tol(self) -> None:
        # Regulatory boundary: 3.0% exactly.
        out = basel_iii_leverage_ratio(30.0, 1000.0)
        assert out["minimum"] == pytest.approx(0.03, abs=ZERO_TOL)
        assert out["leverage_ratio"] == pytest.approx(0.03, abs=RATIO_TOL)
        assert out["compliant"] is True

    def test_leverage_below_minimum(self) -> None:
        # 29/1000 = 0.029 < 3% → breach.
        out = basel_iii_leverage_ratio(29.0, 1000.0)
        assert out["compliant"] is False
        assert out["surplus"] == pytest.approx(0.029 - 0.03, abs=RATIO_TOL)

    def test_leverage_rejects_nonpositive_exposure(self) -> None:
        with pytest.raises(ValueError):
            basel_iii_leverage_ratio(30.0, 0.0)


class TestBaselIVOutputFloor:
    """Basel IV output floor — Basel III finalisation (BCBS d424, Dec 2017) §46.

    Reference: floored RWA = max(internal_model_rwa, 72.5% * standardised_rwa).
    """

    def test_floor_binding(self) -> None:
        # standardised=1000 → floor = 0.725*1000 = 725; internal=600 < 725.
        out = basel_iv_output_floor(600.0, 1000.0)
        assert out["floor_rwa"] == pytest.approx(725.0, abs=1e-4)
        assert out["floored_rwa"] == pytest.approx(725.0, abs=1e-4)
        assert out["binding"] is True
        assert out["rwa_uplift"] == pytest.approx(125.0, abs=1e-4)

    def test_floor_not_binding(self) -> None:
        # internal=800 > floor(725) → floored stays at internal.
        out = basel_iv_output_floor(800.0, 1000.0)
        assert out["floored_rwa"] == pytest.approx(800.0, abs=1e-4)
        assert out["binding"] is False
        assert out["rwa_uplift"] == pytest.approx(0.0, abs=1e-4)

    def test_output_floor_factor_boundary_zero_tol(self) -> None:
        # Regulatory boundary: 72.5% exactly (default floor factor).
        out = basel_iv_output_floor(0.0, 1000.0)
        assert out["floor_factor"] == pytest.approx(0.725, abs=ZERO_TOL)
        # floor = 0.725 * 1000 = 725 exactly.
        assert out["floor_rwa"] == pytest.approx(725.0, abs=ZERO_TOL)

    def test_floor_rejects_negative_rwa(self) -> None:
        with pytest.raises(ValueError):
            basel_iv_output_floor(-1.0, 1000.0)

    def test_floor_rejects_bad_factor(self) -> None:
        with pytest.raises(ValueError):
            basel_iv_output_floor(600.0, 1000.0, floor_factor=1.5)


class TestICAAPCapitalAssessment:
    """ICAAP internal capital adequacy — Basel II Pillar 2 / CRD IV Art. 73.

    Reference: total requirement = Pillar 1 + sum(Pillar 2 components);
    surplus = available - requirement; adequate iff surplus >= 0.
    """

    def test_icaap_adequate(self) -> None:
        components = np.array([10.0, 5.0, 3.0], dtype=np.float64)
        # Independent: total = 80 + 18 = 98; surplus = 120 - 98 = 22.
        out = icaap_capital_assessment(80.0, components, 120.0)
        assert out["pillar2_capital"] == pytest.approx(18.0, abs=1e-6)
        assert out["total_capital_requirement"] == pytest.approx(98.0, abs=1e-6)
        assert out["capital_surplus"] == pytest.approx(22.0, abs=1e-6)
        assert out["adequate"] is True

    def test_icaap_inadequate(self) -> None:
        components = np.array([50.0, 20.0], dtype=np.float64)
        # total = 80 + 70 = 150; surplus = 120 - 150 = -30.
        out = icaap_capital_assessment(80.0, components, 120.0)
        assert out["capital_surplus"] == pytest.approx(-30.0, abs=1e-6)
        assert out["adequate"] is False

    def test_icaap_rejects_negative_pillar1(self) -> None:
        with pytest.raises(ValueError):
            icaap_capital_assessment(-1.0, np.array([1.0]), 10.0)


class TestSREPCapitalAddOn:
    """SREP capital add-on / TSCR — EBA SREP Guidelines (EBA/GL/2014/13).

    Reference: P2A capital = ratio * RWA; TSCR = Pillar 1 + P2A capital;
    TSCR ratio = TSCR / RWA.
    """

    def test_srep_addon_closed_form(self) -> None:
        # P2A = 0.02 * 1000 = 20; TSCR = 80 + 20 = 100; TSCR ratio = 0.10.
        out = srep_capital_add_on(80.0, 0.02, 1000.0)
        assert out["pillar2a_capital"] == pytest.approx(20.0, abs=1e-6)
        assert out["total_srep_requirement"] == pytest.approx(100.0, abs=1e-6)
        assert out["tscr_ratio"] == pytest.approx(0.10, abs=RATIO_TOL)

    def test_srep_rejects_nonpositive_rwa(self) -> None:
        with pytest.raises(ValueError):
            srep_capital_add_on(80.0, 0.02, 0.0)

    def test_srep_rejects_negative_addon(self) -> None:
        with pytest.raises(ValueError):
            srep_capital_add_on(80.0, -0.01, 1000.0)


class TestPillar2ACapital:
    """Pillar 2A capital — sum of individual risk add-ons (CRD IV Art. 104a)."""

    def test_pillar2a_sum(self) -> None:
        addons = np.array([12.0, 8.0, 5.0], dtype=np.float64)
        # Independent: total = 25; ratio = 25 / 1000 = 0.025.
        out = pillar_2a_capital(addons, 1000.0)
        assert out["pillar2a_capital"] == pytest.approx(25.0, abs=1e-6)
        assert out["pillar2a_ratio"] == pytest.approx(0.025, abs=RATIO_TOL)
        assert out["n_components"] == 3

    def test_pillar2a_rejects_nonpositive_rwa(self) -> None:
        with pytest.raises(ValueError):
            pillar_2a_capital(np.array([1.0]), -1.0)


class TestPillar2BStressBuffer:
    """Pillar 2B stress buffer (PRA buffer) — forward-looking CET1 depletion."""

    def test_pillar2b_positive_depletion(self) -> None:
        # buffer = max(30, 0) = 30; ratio = 30 / 1000 = 0.03.
        out = pillar_2b_stress_buffer(30.0, 1000.0)
        assert out["pillar2b_buffer"] == pytest.approx(30.0, abs=1e-6)
        assert out["buffer_ratio"] == pytest.approx(0.03, abs=RATIO_TOL)

    def test_pillar2b_floored_at_zero(self) -> None:
        # Negative depletion (capital accretion) floors the buffer at zero.
        out = pillar_2b_stress_buffer(-15.0, 1000.0)
        assert out["pillar2b_buffer"] == pytest.approx(0.0, abs=1e-6)
        assert out["buffer_ratio"] == pytest.approx(0.0, abs=RATIO_TOL)

    def test_pillar2b_rejects_nonpositive_rwa(self) -> None:
        with pytest.raises(ValueError):
            pillar_2b_stress_buffer(30.0, 0.0)


class TestCombinedBufferRequirement:
    """Combined Buffer Requirement — CRD IV Art. 128.

    Reference: CBR = CCoB + CCyB + systemic buffer.
    """

    def test_cbr_sum(self) -> None:
        # Independent: 0.025 + 0.01 + 0.015 = 0.05.
        out = combined_buffer_requirement(0.025, 0.01, 0.015, 1000.0)
        assert out["combined_buffer_ratio"] == pytest.approx(0.05, abs=RATIO_TOL)
        assert out["combined_buffer_capital"] == pytest.approx(50.0, abs=1e-4)

    def test_cbr_default_ccob_boundary_zero_tol(self) -> None:
        # Default CCoB is 2.5% exactly; with zero CCyB/systemic, CBR == 2.5%.
        out = combined_buffer_requirement()
        assert out["combined_buffer_ratio"] == pytest.approx(0.025, abs=ZERO_TOL)
        # No capital key when RWA == 0.
        assert "combined_buffer_capital" not in out

    def test_cbr_rejects_negative_ratio(self) -> None:
        with pytest.raises(ValueError):
            combined_buffer_requirement(0.025, -0.01, 0.0, 1000.0)


class TestCapitalConservationBuffer:
    """Capital Conservation Buffer — Basel III §122 / CRD IV Art. 129.

    Reference: 2.5% CET1 above the 4.5% minimum → required CET1 ratio = 7.0%;
    breach triggers MDA restrictions.
    """

    def test_ccob_required_ratio(self) -> None:
        # Independent: 4.5% + 2.5% = 7.0% required CET1 ratio.
        out = capital_conservation_buffer(0.08, 1000.0)
        assert out["required_cet1_ratio"] == pytest.approx(0.07, abs=RATIO_TOL)
        assert out["buffer_capital"] == pytest.approx(25.0, abs=1e-4)
        assert out["buffer_met"] is True
        assert out["mda_restricted"] is False

    def test_ccob_buffer_ratio_boundary_zero_tol(self) -> None:
        # Regulatory boundary: buffer capital = 2.5% * RWA exactly.
        out = capital_conservation_buffer(0.08, 1000.0)
        assert out["buffer_capital"] == pytest.approx(25.0, abs=ZERO_TOL)

    def test_ccob_mda_restricted_on_breach(self) -> None:
        # CET1 6.5% < required 7.0% → MDA restricted.
        out = capital_conservation_buffer(0.065, 1000.0)
        assert out["buffer_met"] is False
        assert out["mda_restricted"] is True

    def test_ccob_rejects_nonpositive_rwa(self) -> None:
        with pytest.raises(ValueError):
            capital_conservation_buffer(0.08, 0.0)


class TestCountercyclicalCapitalBuffer:
    """Institution-specific CCyB — CRD IV Art. 140.

    Reference: exposure-weighted average of national CCyB rates.
    """

    def test_ccyb_weighted_average(self) -> None:
        exposures = np.array([600.0, 400.0], dtype=np.float64)
        rates = np.array([0.01, 0.02], dtype=np.float64)
        # Independent: (600*0.01 + 400*0.02) / 1000 = (6 + 8)/1000 = 0.014.
        expected_rate = (600.0 * 0.01 + 400.0 * 0.02) / 1000.0
        out = countercyclical_capital_buffer(exposures, rates, 1000.0)
        assert out["ccyb_rate"] == pytest.approx(expected_rate, abs=RATIO_TOL)
        assert out["ccyb_rate"] == pytest.approx(0.014, abs=RATIO_TOL)
        assert out["ccyb_capital"] == pytest.approx(0.014 * 1000.0, abs=1e-4)

    def test_ccyb_uniform_rate(self) -> None:
        # Uniform 2.5% max rate → weighted average is 2.5% (CRD IV cap).
        exposures = np.array([100.0, 300.0, 600.0], dtype=np.float64)
        rates = np.array([0.025, 0.025, 0.025], dtype=np.float64)
        out = countercyclical_capital_buffer(exposures, rates, 2000.0)
        assert out["ccyb_rate"] == pytest.approx(0.025, abs=RATIO_TOL)

    def test_ccyb_rejects_mismatched_arrays(self) -> None:
        with pytest.raises(ValueError):
            countercyclical_capital_buffer(np.array([1.0, 2.0]), np.array([0.01]), 1000.0)

    def test_ccyb_rejects_nonpositive_rwa(self) -> None:
        with pytest.raises(ValueError):
            countercyclical_capital_buffer(np.array([1.0]), np.array([0.01]), 0.0)


class TestCRR2LargeExposureLimit:
    """CRR2 large exposure limit — Regulation (EU) 2019/876 Art. 395.

    Reference: exposure ratio = exposure / Tier 1; limit = 25% of Tier 1.
    """

    def test_within_limit(self) -> None:
        # 200 / 1000 = 0.20 <= 0.25 → within limit; excess 0.
        out = crr2_large_exposure_limit(200.0, 1000.0)
        assert out["exposure_ratio"] == pytest.approx(0.20, abs=RATIO_TOL)
        assert out["within_limit"] is True
        assert out["excess"] == pytest.approx(0.0, abs=1e-4)

    def test_limit_boundary_zero_tol(self) -> None:
        # Regulatory boundary: 25% exactly.
        out = crr2_large_exposure_limit(250.0, 1000.0)
        assert out["limit"] == pytest.approx(0.25, abs=ZERO_TOL)
        # Exactly at the limit → within_limit (<=).
        assert out["exposure_ratio"] == pytest.approx(0.25, abs=RATIO_TOL)
        assert out["within_limit"] is True

    def test_breach_excess_amount(self) -> None:
        # 300 / 1000 = 0.30 > 0.25; limit amount = 250; excess = 50.
        out = crr2_large_exposure_limit(300.0, 1000.0)
        assert out["within_limit"] is False
        assert out["excess"] == pytest.approx(50.0, abs=1e-4)

    def test_rejects_nonpositive_tier1(self) -> None:
        with pytest.raises(ValueError):
            crr2_large_exposure_limit(100.0, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# reg_mifid_emir.py  (validators/flags — independent hand-calc from RTS rule)
# ══════════════════════════════════════════════════════════════════════════════


class TestMiFIDTransactionReportValidator:
    """MiFID II / RTS 22 transaction report validator.

    Independent hand-calc from RTS 22 rule: all mandatory fields present, LEI
    length 20, ISIN length 12, positive price/quantity → valid.
    """

    def _valid_report(self) -> dict:
        return {
            "transaction_reference_number": "TXN0001",
            "executing_entity_lei": "5493001KJTIIGC8Y1R12",  # 20 chars
            "buyer_id": "B1",
            "seller_id": "S1",
            "instrument_isin": "GB0002634946",  # 12 chars
            "price": 101.5,
            "quantity": 100.0,
            "trading_datetime": "2026-07-01T09:00:00Z",
            "venue": "XLON",
        }

    def test_valid_report(self) -> None:
        out = mifid_ii_transaction_report_validator(self._valid_report())
        assert out["valid"] is True
        assert out["errors"] == []

    def test_missing_field_flagged(self) -> None:
        # Hand-calc: remove venue → exactly one missing_required_field error.
        rpt = self._valid_report()
        del rpt["venue"]
        out = mifid_ii_transaction_report_validator(rpt)
        assert out["valid"] is False
        assert "missing_required_field:venue" in out["errors"]

    def test_invalid_lei_length(self) -> None:
        # RTS 22: LEI must be 20 chars. 19-char LEI → invalid_lei_length.
        rpt = self._valid_report()
        rpt["executing_entity_lei"] = "5493001KJTIIGC8Y1R1"  # 19 chars
        out = mifid_ii_transaction_report_validator(rpt)
        assert "invalid_lei_length" in out["errors"]
        assert out["valid"] is False

    def test_invalid_isin_length(self) -> None:
        rpt = self._valid_report()
        rpt["instrument_isin"] = "GB000263494"  # 11 chars
        out = mifid_ii_transaction_report_validator(rpt)
        assert "invalid_isin_length" in out["errors"]

    def test_non_positive_price(self) -> None:
        rpt = self._valid_report()
        rpt["price"] = 0.0
        out = mifid_ii_transaction_report_validator(rpt)
        assert "non_positive_price" in out["errors"]

    def test_non_numeric_price_flagged(self) -> None:
        # RTS 22: price/quantity must be numeric; non-numeric → error flag.
        rpt = self._valid_report()
        rpt["price"] = "not_a_number"
        out = mifid_ii_transaction_report_validator(rpt)
        assert "non_numeric_price_or_quantity" in out["errors"]
        assert out["valid"] is False


class TestMiFIDPreTradeTransparency:
    """MiFID II pre-trade transparency / LIS waiver — RTS 1/2.

    Independent hand-calc: order >= LIS threshold → large_in_scale waiver;
    else illiquid → illiquid_instrument waiver; else transparency required.
    """

    def test_lis_waiver(self) -> None:
        out = mifid_ii_pre_trade_transparency("equity", 1_000_000.0, 500_000.0)
        assert out["waiver"] == "large_in_scale"
        assert out["transparency_required"] is False

    def test_illiquid_waiver(self) -> None:
        # Below LIS but illiquid → illiquid_instrument waiver.
        out = mifid_ii_pre_trade_transparency("bond", 100_000.0, 500_000.0, is_liquid=False)
        assert out["waiver"] == "illiquid_instrument"
        assert out["transparency_required"] is False

    def test_transparency_required(self) -> None:
        # Below LIS and liquid → no waiver, transparency required.
        out = mifid_ii_pre_trade_transparency("equity", 100_000.0, 500_000.0)
        assert out["waiver"] is None
        assert out["transparency_required"] is True

    def test_rejects_negative_size(self) -> None:
        with pytest.raises(ValueError):
            mifid_ii_pre_trade_transparency("equity", -1.0, 500_000.0)


class TestMiFIDPostTradeTransparency:
    """MiFID II post-trade transparency / deferred publication — RTS 1/2.

    Independent hand-calc: trade >= threshold OR illiquid → deferred;
    else real_time.
    """

    def test_deferred_by_size(self) -> None:
        out = mifid_ii_post_trade_transparency(2_000_000.0, 1_000_000.0)
        assert out["publication"] == "deferred"
        assert out["deferral_eligible"] is True

    def test_deferred_by_illiquidity(self) -> None:
        out = mifid_ii_post_trade_transparency(10_000.0, 1_000_000.0, is_liquid=False)
        assert out["publication"] == "deferred"

    def test_real_time(self) -> None:
        out = mifid_ii_post_trade_transparency(10_000.0, 1_000_000.0)
        assert out["publication"] == "real_time"
        assert out["deferral_eligible"] is False

    def test_rejects_negative_size(self) -> None:
        with pytest.raises(ValueError):
            mifid_ii_post_trade_transparency(-1.0, 1_000_000.0)


class TestMiFIDBestExecutionMetric:
    """MiFID II RTS 27/28 best-execution metric.

    Independent reference: quantity-weighted price improvement in bps.
    improvement_i = side * (benchmark_i - executed_i);
    bps = sum(improvement_i * q_i) / sum(benchmark_i * q_i) * 1e4.
    Cross-validated (numpy hand-calc).
    """

    def test_buy_price_improvement(self) -> None:
        executed = np.array([100.0, 101.0], dtype=np.float64)
        benchmark = np.array([100.5, 101.5], dtype=np.float64)
        qty = np.array([100.0, 200.0], dtype=np.float64)
        # side=+1 buy: improvement = bench - executed = [0.5, 0.5].
        # weighted num = 0.5*100 + 0.5*200 = 150.
        # weighted ref = 100.5*100 + 101.5*200 = 10050 + 20300 = 30350.
        # bps = 150 / 30350 * 1e4.
        expected_bps = 150.0 / 30350.0 * 1e4
        out = mifid_ii_best_execution_metric(executed, benchmark, qty, side=1)
        assert out["price_improvement_bps"] == pytest.approx(expected_bps, abs=1e-4)
        # Both fills improved → fill_rate 1.0.
        assert out["fill_rate"] == pytest.approx(1.0, abs=RATIO_TOL)
        assert out["n_fills"] == 2

    def test_sell_side_sign(self) -> None:
        executed = np.array([102.0], dtype=np.float64)
        benchmark = np.array([100.0], dtype=np.float64)
        qty = np.array([50.0], dtype=np.float64)
        # side=-1 sell: improvement = -1*(100 - 102) = +2 (sold above bench).
        # bps = (2*50) / (100*50) * 1e4 = 100/5000*1e4 = 200.
        out = mifid_ii_best_execution_metric(executed, benchmark, qty, side=-1)
        assert out["price_improvement_bps"] == pytest.approx(200.0, abs=1e-4)
        assert out["fill_rate"] == pytest.approx(1.0, abs=RATIO_TOL)

    def test_slippage_negative(self) -> None:
        executed = np.array([101.0], dtype=np.float64)
        benchmark = np.array([100.0], dtype=np.float64)
        qty = np.array([100.0], dtype=np.float64)
        # Buy above benchmark → negative improvement (slippage).
        out = mifid_ii_best_execution_metric(executed, benchmark, qty, side=1)
        assert out["price_improvement_bps"] < 0.0
        assert out["fill_rate"] == pytest.approx(0.0, abs=RATIO_TOL)

    def test_rejects_bad_side(self) -> None:
        with pytest.raises(ValueError):
            mifid_ii_best_execution_metric(
                np.array([1.0]), np.array([1.0]), np.array([1.0]), side=0
            )

    def test_rejects_mismatched_arrays(self) -> None:
        with pytest.raises(ValueError):
            mifid_ii_best_execution_metric(np.array([1.0, 2.0]), np.array([1.0]), np.array([1.0]))


class TestMiFIDAlgorithmDocumentation:
    """MiFID II RTS 6 algorithmic-trading documentation completeness.

    Independent hand-calc: 6 mandatory items. completeness = 1 - missing/6.
    """

    def _full_docs(self) -> dict:
        return {
            "strategy_description": True,
            "risk_controls": True,
            "kill_switch": True,
            "testing_evidence": True,
            "deployment_signoff": True,
            "monitoring_arrangements": True,
        }

    def test_complete(self) -> None:
        out = mifid_ii_algorithm_documentation(self._full_docs())
        assert out["valid"] is True
        assert out["errors"] == []
        assert out["report"]["completeness"] == pytest.approx(1.0, abs=RATIO_TOL)

    def test_missing_two_items(self) -> None:
        docs = self._full_docs()
        docs["kill_switch"] = False
        del docs["monitoring_arrangements"]
        # Hand-calc: 2 missing of 6 → completeness = 1 - 2/6 = 0.6667.
        out = mifid_ii_algorithm_documentation(docs)
        assert out["valid"] is False
        assert len(out["errors"]) == 2
        assert out["report"]["completeness"] == pytest.approx(1.0 - 2.0 / 6.0, abs=1e-4)


class TestEMIRTradeRepositoryReport:
    """EMIR trade repository report — Regulation (EU) 648/2012.

    Independent hand-calc: core fields present, LEIs length 20, positive
    notional → valid.
    """

    def _valid_trade(self) -> dict:
        return {
            "reporting_counterparty_lei": "5493001KJTIIGC8Y1R12",
            "other_counterparty_lei": "213800WAVVOPS85N2205",
            "uti": "UTI123456789",
            "asset_class": "interest_rate",
            "notional": 1_000_000.0,
            "execution_timestamp": "2026-07-01T10:00:00Z",
        }

    def test_valid_trade(self) -> None:
        out = emir_trade_repository_report(self._valid_trade())
        assert out["valid"] is True
        assert out["errors"] == []

    def test_missing_uti(self) -> None:
        trade = self._valid_trade()
        trade["uti"] = ""
        out = emir_trade_repository_report(trade)
        assert out["valid"] is False
        assert "missing:uti" in out["errors"]

    def test_invalid_lei(self) -> None:
        trade = self._valid_trade()
        trade["other_counterparty_lei"] = "SHORTLEI"  # not 20 chars
        out = emir_trade_repository_report(trade)
        assert "invalid_lei:other_counterparty_lei" in out["errors"]

    def test_non_positive_notional(self) -> None:
        trade = self._valid_trade()
        trade["notional"] = -5.0
        out = emir_trade_repository_report(trade)
        assert "non_positive_notional" in out["errors"]

    def test_non_numeric_notional(self) -> None:
        trade = self._valid_trade()
        trade["notional"] = "abc"
        out = emir_trade_repository_report(trade)
        assert "non_numeric_notional" in out["errors"]


class TestEMIRClearingObligation:
    """EMIR clearing obligation — Regulation (EU) 648/2012 Art. 4.

    Independent hand-calc: FC/NFC+ above the asset-class clearing threshold
    → clearing required; NFC- never subject to mandatory clearing.
    """

    THRESHOLDS = {"interest_rate": 3_000_000_000.0, "credit": 1_000_000_000.0}

    def test_fc_above_threshold(self) -> None:
        out = emir_clearing_obligation_check(
            "interest_rate", 5_000_000_000.0, "FC", self.THRESHOLDS
        )
        assert out["clearing_required"] is True
        assert out["threshold"] == pytest.approx(3_000_000_000.0, abs=1e-2)

    def test_nfc_plus_below_threshold(self) -> None:
        out = emir_clearing_obligation_check("credit", 500_000_000.0, "NFC+", self.THRESHOLDS)
        assert out["clearing_required"] is False

    def test_nfc_minus_exempt(self) -> None:
        # NFC- exempt even above the threshold.
        out = emir_clearing_obligation_check(
            "interest_rate", 9_000_000_000.0, "NFC-", self.THRESHOLDS
        )
        assert out["clearing_required"] is False

    def test_rejects_unknown_category(self) -> None:
        with pytest.raises(ValueError):
            emir_clearing_obligation_check("credit", 1.0, "XX", self.THRESHOLDS)

    def test_rejects_negative_notional(self) -> None:
        with pytest.raises(ValueError):
            emir_clearing_obligation_check("credit", -1.0, "FC", self.THRESHOLDS)


class TestEMIRMarginRequirement:
    """EMIR uncleared-derivatives margin — Regulation (EU) 648/2012 Art. 11.

    Independent reference: IM = rate * portfolio_value; VM call applied only
    if |VM| >= MTA; total = IM + VM call.
    """

    def test_margin_above_mta(self) -> None:
        # IM = 0.05 * 1_000_000 = 50_000; VM 20_000 >= MTA 10_000 → call 20_000.
        out = emir_margin_requirement(1_000_000.0, 0.05, 20_000.0, 10_000.0)
        assert out["initial_margin"] == pytest.approx(50_000.0, abs=1e-4)
        assert out["variation_margin_call"] == pytest.approx(20_000.0, abs=1e-4)
        assert out["total_margin"] == pytest.approx(70_000.0, abs=1e-4)

    def test_vm_below_mta_suppressed(self) -> None:
        # VM 5_000 < MTA 10_000 → no VM call.
        out = emir_margin_requirement(1_000_000.0, 0.05, 5_000.0, 10_000.0)
        assert out["variation_margin_call"] == pytest.approx(0.0, abs=1e-4)
        assert out["total_margin"] == pytest.approx(50_000.0, abs=1e-4)

    def test_rejects_negative_rate(self) -> None:
        with pytest.raises(ValueError):
            emir_margin_requirement(1_000_000.0, -0.01, 0.0)


class TestSFTRReport:
    """SFTR securities-financing report — Regulation (EU) 2015/2365.

    Independent hand-calc: core fields present, valid sft_type,
    non-negative collateral → valid.
    """

    def _valid_txn(self) -> dict:
        return {
            "reporting_counterparty_lei": "5493001KJTIIGC8Y1R12",
            "other_counterparty_lei": "213800WAVVOPS85N2205",
            "uti": "UTI987654321",
            "sft_type": "repo",
            "principal_amount": 1_000_000.0,
            "collateral_value": 1_050_000.0,
        }

    def test_valid_txn(self) -> None:
        out = sftr_securities_finance_report(self._valid_txn())
        assert out["valid"] is True
        assert out["errors"] == []

    def test_invalid_sft_type(self) -> None:
        txn = self._valid_txn()
        txn["sft_type"] = "swap"  # not an SFT type
        out = sftr_securities_finance_report(txn)
        assert "invalid_sft_type" in out["errors"]
        assert out["valid"] is False

    def test_negative_collateral(self) -> None:
        txn = self._valid_txn()
        txn["collateral_value"] = -1.0
        out = sftr_securities_finance_report(txn)
        assert "negative_collateral_value" in out["errors"]

    def test_missing_field(self) -> None:
        txn = self._valid_txn()
        txn["uti"] = None
        out = sftr_securities_finance_report(txn)
        assert "missing:uti" in out["errors"]

    def test_non_numeric_collateral(self) -> None:
        txn = self._valid_txn()
        txn["collateral_value"] = "xyz"
        out = sftr_securities_finance_report(txn)
        assert "non_numeric_collateral_value" in out["errors"]


# ══════════════════════════════════════════════════════════════════════════════
# reg_solvency.py  (AIFMD / UCITS / Solvency II)
# ══════════════════════════════════════════════════════════════════════════════


class TestAIFMDRiskMetrics:
    """AIFMD Annex IV leverage — Commission Delegated Reg (EU) 231/2013 Art. 7-8.

    Independent reference: gross leverage = gross exposure / NAV;
    commitment leverage = commitment exposure / NAV;
    substantially leveraged iff commitment leverage > 3x NAV.
    """

    def test_leverage_ratios(self) -> None:
        # gross = 250/100 = 2.5; commitment = 180/100 = 1.8.
        out = aifmd_risk_metrics(250.0, 180.0, 100.0)
        assert out["gross_leverage"] == pytest.approx(2.5, abs=1e-6)
        assert out["commitment_leverage"] == pytest.approx(1.8, abs=1e-6)
        assert out["substantially_leveraged"] is False

    def test_substantially_leveraged_boundary(self) -> None:
        # commitment = 350/100 = 3.5 > 3.0 → substantially leveraged.
        out = aifmd_risk_metrics(500.0, 350.0, 100.0)
        assert out["substantially_leveraged"] is True

    def test_var_pct_reported(self) -> None:
        out = aifmd_risk_metrics(250.0, 180.0, 100.0, var_pct=0.15)
        assert out["var_pct"] == pytest.approx(0.15, abs=RATIO_TOL)

    def test_rejects_nonpositive_nav(self) -> None:
        with pytest.raises(ValueError):
            aifmd_risk_metrics(250.0, 180.0, 0.0)


class TestUCITSKIIDRiskIndicator:
    """UCITS KIID SRRI — CESR 10-673 Box 1 / Regulation (EU) 583/2010.

    Independent reference: annualised vol = std(returns, ddof=1) * sqrt(ppy);
    SRRI band per CESR bands (0.5%, 2%, 5%, 10%, 15%, 25%).
    Cross-validated (scipy / numpy).
    """

    def test_srri_band_and_vol_cross_validated(self) -> None:
        rng = np.random.default_rng(42)
        # Weekly returns targeting ~8% annual vol → band 4 (5%<=vol<10%).
        weekly_sigma = 0.08 / math.sqrt(52.0)
        returns = rng.normal(0.0, weekly_sigma, size=520)
        # Independent reference computation of annualised vol.
        ref_vol = float(np.std(returns, ddof=1) * math.sqrt(52.0))
        out = ucits_kiid_risk_indicator(returns, periods_per_year=52)
        assert out["annualised_volatility"] == pytest.approx(ref_vol, abs=1e-8)
        # Independent band assignment from CESR bands.
        bands = (0.005, 0.02, 0.05, 0.10, 0.15, 0.25)
        expected_srri = 7
        for k, upper in enumerate(bands, start=1):
            if ref_vol < upper:
                expected_srri = k
                break
        assert out["srri"] == expected_srri

    def test_srri_low_vol_class1(self) -> None:
        # Near-constant returns → tiny vol → SRRI 1 (< 0.5%).
        returns = np.array([0.0001, 0.0002, 0.0001, 0.00015], dtype=np.float64)
        out = ucits_kiid_risk_indicator(returns, periods_per_year=52)
        assert out["srri"] == 1

    def test_srri_high_vol_class7(self) -> None:
        # Large swings → annualised vol >= 25% → SRRI 7.
        returns = np.array([0.10, -0.10, 0.12, -0.11, 0.09], dtype=np.float64)
        out = ucits_kiid_risk_indicator(returns, periods_per_year=52)
        # Independent check that reference vol >= 0.25.
        ref_vol = float(np.std(returns, ddof=1) * math.sqrt(52.0))
        assert ref_vol >= 0.25
        assert out["srri"] == 7

    def test_rejects_too_few_obs(self) -> None:
        with pytest.raises(ValueError):
            ucits_kiid_risk_indicator(np.array([0.01]))


class TestSolvencyIISCRMarketRisk:
    """Solvency II SCR Market — Delegated Regulation (EU) 2015/35 Art. 164.

    Independent reference: SCR = sqrt(s' Corr s) via the correlation-matrix
    square-root aggregation. Cross-validated (numpy quadratic form).
    """

    def test_scr_aggregation_closed_form(self) -> None:
        s = np.array([100.0, 50.0], dtype=np.float64)
        corr = np.array([[1.0, 0.5], [0.5, 1.0]], dtype=np.float64)
        # Independent: s'Cs = 100^2 + 50^2 + 2*0.5*100*50
        #                   = 10000 + 2500 + 5000 = 17500 → sqrt = 132.2876.
        ref_scr = math.sqrt(17500.0)
        out = solvency_ii_scr_market_risk(s, corr)
        assert out["scr_market"] == pytest.approx(ref_scr, abs=1e-4)
        assert out["sum_of_charges"] == pytest.approx(150.0, abs=1e-4)
        assert out["diversification_benefit"] == pytest.approx(150.0 - ref_scr, abs=1e-4)

    def test_scr_matches_numpy_quadratic_form(self) -> None:
        # Cross-validated (numpy): sqrt(s @ C @ s).
        s = np.array([80.0, 40.0, 25.0, 10.0], dtype=np.float64)
        corr = np.array(
            [
                [1.0, 0.25, 0.25, 0.25],
                [0.25, 1.0, 0.75, 0.25],
                [0.25, 0.75, 1.0, 0.5],
                [0.25, 0.25, 0.5, 1.0],
            ],
            dtype=np.float64,
        )
        ref_scr = float(np.sqrt(s @ corr @ s))
        out = solvency_ii_scr_market_risk(s, corr)
        assert out["scr_market"] == pytest.approx(ref_scr, abs=1e-4)

    def test_diversification_non_negative(self) -> None:
        # Property: with correlations <= 1, diversified SCR <= sum of charges.
        s = np.array([30.0, 20.0], dtype=np.float64)
        corr = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float64)
        out = solvency_ii_scr_market_risk(s, corr)
        assert out["diversification_benefit"] >= 0.0

    def test_rejects_bad_matrix_shape(self) -> None:
        with pytest.raises(ValueError):
            solvency_ii_scr_market_risk(np.array([1.0, 2.0]), np.array([[1.0]]))

    def test_rejects_bad_names_length(self) -> None:
        # Art. 164: sub_module labels must match the number of charges.
        s = np.array([100.0, 50.0], dtype=np.float64)
        corr = np.array([[1.0, 0.5], [0.5, 1.0]], dtype=np.float64)
        with pytest.raises(ValueError):
            solvency_ii_scr_market_risk(s, corr, sub_module_names=["only_one"])

    def test_accepts_matching_names(self) -> None:
        s = np.array([100.0, 50.0], dtype=np.float64)
        corr = np.array([[1.0, 0.5], [0.5, 1.0]], dtype=np.float64)
        out = solvency_ii_scr_market_risk(s, corr, sub_module_names=["interest_rate", "equity"])
        assert out["scr_market"] == pytest.approx(math.sqrt(17500.0), abs=1e-4)


class TestSolvencyIISCRCreditRisk:
    """Solvency II SCR credit — Delegated Regulation (EU) 2015/35 Art. 199-202.

    Independent reference (simplified type-1):
      lgd_i = ead_i * lgd_rate_i;  total_lgd = sum(lgd_i)
      expected_loss = sum(pd_i * lgd_i)
      variance = sum(lgd_i^2 * pd_i * (1-pd_i))
      scr = min(risk_factor * sqrt(variance), total_lgd)
    Cross-validated (numpy).
    """

    def test_scr_credit_closed_form(self) -> None:
        ead = np.array([1000.0, 2000.0], dtype=np.float64)
        lgd_rate = np.array([0.45, 0.60], dtype=np.float64)
        pd = np.array([0.02, 0.05], dtype=np.float64)
        # Independent reference:
        lgd = ead * lgd_rate  # [450, 1200]
        total_lgd = float(np.sum(lgd))  # 1650
        expected_loss = float(np.sum(pd * lgd))  # 0.02*450 + 0.05*1200 = 69
        variance = float(np.sum((lgd**2) * pd * (1.0 - pd)))
        ref_scr = min(3.0 * math.sqrt(variance), total_lgd)
        out = solvency_ii_scr_credit_risk(ead, lgd_rate, pd)
        assert out["total_lgd"] == pytest.approx(total_lgd, abs=1e-4)
        assert out["expected_loss"] == pytest.approx(expected_loss, abs=1e-4)
        assert out["scr_credit"] == pytest.approx(ref_scr, abs=1e-4)

    def test_scr_capped_at_total_lgd(self) -> None:
        # High risk factor forces the min() cap at total LGD.
        ead = np.array([1000.0], dtype=np.float64)
        lgd_rate = np.array([1.0], dtype=np.float64)
        pd = np.array([0.5], dtype=np.float64)
        out = solvency_ii_scr_credit_risk(ead, lgd_rate, pd, risk_factor=100.0)
        # total_lgd = 1000; uncapped scr huge → capped at 1000.
        assert out["scr_credit"] == pytest.approx(1000.0, abs=1e-4)

    def test_rejects_pd_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            solvency_ii_scr_credit_risk(np.array([1.0]), np.array([0.5]), np.array([1.5]))

    def test_rejects_mismatched_arrays(self) -> None:
        with pytest.raises(ValueError):
            solvency_ii_scr_credit_risk(np.array([1.0, 2.0]), np.array([0.5]), np.array([0.1]))

"""tests/validation/test_alm_ref.py — P5a external-reference validation for ALM.

Every ALM engine function (34 across 5 modules) is validated against an
INDEPENDENT reference, never against the function's own output:

* Closed-form arithmetic (duration/PV/gap/EVE/CPR/convexity) recomputed here
  by hand from the textbook formula.
* Regulatory (IRRBB / BCBS d368): the six standard shocks are checked for exact
  count, names, signs and shape and cross-validated against the d368 Annex 2
  construction; EVE deltas cross-checked against a hand-built shocked curve
  ("cross-validated" per BCBS d368).
* Where no published reference exists (behavioural NMD models, structural hedge
  optimisation, FTP curves, balance-sheet projection) an independent hand-calc
  from the documented formula is used and marked accordingly.

Tolerances: 1e-5 (0.001%) for pure duration/PV arithmetic; 1e-3 (0.1%) for
simulation; ZERO tolerance for the "exactly six shocks" IRRBB requirement.

Known limitations (Tier 3 #2 audit, documented rather than silently left):
  prepayment_model_mortgages computes WAL from TOTAL (interest+principal)
  cashflows rather than principal-only, which is the standard WAL
  definition in every published source checked (SIFMA "Standard Formulas
  for the Analysis of MBS") -- no published example can match by
  construction; a definition fix, not a citation, would be needed.
  behavioural_modelling_nmds, non_maturity_deposit_stability,
  funds_transfer_pricing_ftp (single-deal and curve construction),
  pipeline_risk_measurement, liquidity_adjusted_nii, nii_simulation_stress,
  dynamic_gap_analysis and balance_sheet_projection_model are all bespoke
  constructions with no published worked example -- checked against BCBS
  d368's standardised NMD treatment (a different methodology: slotting with
  maturity caps, not this file's exponential-decay blend), BIS WP47 and ECB
  WP 3140 (NMD stability literature reviews, no worked example), and
  Grant (2011, BIS FSI OP No. 10) / Bessis Ch. 10 (FTP, qualitative only).
  structural_hedge_optimisation_ref's single-instrument case is the exact
  analytic solution to a degenerate 1-instrument bounded least-squares
  problem -- correct, but doesn't exercise the general (multi-instrument)
  case.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from engine.alm_behavioural import (
    behavioural_modelling_nmds,
    core_deposit_duration,
    loan_prepayment_rate_cpr,
    non_maturity_deposit_stability,
    prepayment_model_mortgages,
)
from engine.alm_duration import (
    convexity_gap,
    duration_gap_analysis,
    effective_duration_alm,
    macaulay_duration_balance_sheet,
    modified_duration_balance_sheet,
    nii_sensitivity_rate_shock,
    nii_simulation_baseline,
)
from engine.alm_ftp import (
    alm_stress_test,
    balance_sheet_projection_model,
    ftp_curve_construction,
    funds_transfer_pricing_ftp,
    structural_hedge_optimisation,
)
from engine.alm_irrbb import (
    asset_liability_mismatch_index,
    basis_risk_irrbb,
    dynamic_gap_analysis,
    economic_value_helper,
    interest_rate_risk_capital_irrbb,
    irrbb_internal_model,
    irrbb_six_standard_rate_shocks,
    irrbb_standardised_framework,
    option_risk_irrbb,
    pipeline_risk_measurement,
    repricing_gap_analysis,
    repricing_maturity_profile,
    static_gap_analysis,
)
from engine.alm_nii_eve import (
    economic_value_of_equity_eve,
    eve_sensitivity_analysis,
    liquidity_adjusted_nii,
    nii_simulation_stress,
)

# Tolerances
TOL_ARITH = 1e-5  # 0.001% for closed-form duration/PV/gap arithmetic
TOL_SIM = 1e-3  # 0.1% for simulation / projection
SIX_SHOCK_NAMES = {
    "parallel_up",
    "parallel_down",
    "steepener",
    "flattener",
    "short_up",
    "short_down",
}


def _rel(a: float, b: float) -> float:
    """Relative deviation, robust to near-zero reference."""
    denom = max(abs(b), 1e-12)
    return abs(a - b) / denom


# ======================================================================
# MODULE 1 — engine/alm_duration.py
# ======================================================================


def test_macaulay_duration_balance_sheet_closed_form():
    """Macaulay D = sum(t*PV_t)/price, continuous discounting. Closed-form ref."""
    cf = np.array([5.0, 5.0, 105.0])
    t = np.array([1.0, 2.0, 3.0])
    r = 0.04
    # Independent reference
    df = np.exp(-r * t)
    pv = cf * df
    price_ref = float(np.sum(pv))
    dur_ref = float(np.sum(t * pv) / price_ref)
    out = macaulay_duration_balance_sheet(cf, t, r)
    assert _rel(out["present_value"], price_ref) < TOL_ARITH
    assert _rel(out["macaulay_duration"], dur_ref) < TOL_ARITH
    # Property: Macaulay duration < longest maturity for a coupon bond
    assert out["macaulay_duration"] < 3.0


def test_macaulay_duration_length_mismatch():
    with pytest.raises(ValueError):
        macaulay_duration_balance_sheet(np.array([1.0, 2.0]), np.array([1.0]), 0.05)


def test_modified_duration_less_than_macaulay():
    """Modified D = Macaulay/(1+y/m). Closed-form ref + property mod < mac."""
    cf = np.array([3.0, 3.0, 3.0, 103.0])
    t = np.array([1.0, 2.0, 3.0, 4.0])
    r = 0.05
    freq = 2
    mac = macaulay_duration_balance_sheet(cf, t, r)["macaulay_duration"]
    mod_ref = mac / (1.0 + r / freq)
    out = modified_duration_balance_sheet(cf, t, r, frequency=freq)
    assert _rel(out["modified_duration"], mod_ref) < TOL_ARITH
    # Property: modified duration strictly < Macaulay for positive rate
    assert out["modified_duration"] < out["macaulay_duration"]


def test_effective_duration_closed_form():
    """D_eff = (PV- - PV+)/(2*PV0*dy). Independent closed-form.

    Build PVs from a real bond so the effective duration matches its analytic
    modified duration as a cross-check.
    """
    cf = np.array([2.0, 2.0, 102.0])
    t = np.array([1.0, 2.0, 3.0])
    r = 0.03
    dy = 0.0001
    pv0 = float(np.sum(cf * np.exp(-r * t)))
    pv_up = float(np.sum(cf * np.exp(-(r + dy) * t)))
    pv_down = float(np.sum(cf * np.exp(-(r - dy) * t)))
    eff_ref = (pv_down - pv_up) / (2.0 * pv0 * dy)
    out = effective_duration_alm(pv0, pv_up, pv_down, dy)
    assert _rel(out["effective_duration"], eff_ref) < TOL_ARITH
    # Cross-check: for a continuously-discounted bond effective ~ Macaulay
    mac = macaulay_duration_balance_sheet(cf, t, r)["macaulay_duration"]
    assert _rel(out["effective_duration"], mac) < 1e-3


def test_effective_duration_invalid():
    with pytest.raises(ValueError):
        effective_duration_alm(0.0, 1.0, 1.0, 0.01)
    with pytest.raises(ValueError):
        effective_duration_alm(100.0, 99.0, 101.0, 0.0)


def test_duration_gap_analysis_closed_form():
    """DGAP = D_A - (L/A)*D_L; dEVE = -DGAP*A*dy. Independent closed-form."""
    d_a, d_l = 4.0, 2.0
    a, liab = 1000.0, 800.0
    dy = 0.01
    lev = liab / a
    dgap_ref = d_a - lev * d_l
    delta_eve_ref = -dgap_ref * a * dy
    out = duration_gap_analysis(d_a, d_l, a, liab, rate_shock=dy)
    assert _rel(out["duration_gap"], dgap_ref) < TOL_ARITH
    assert _rel(out["delta_eve"], delta_eve_ref) < TOL_ARITH
    assert _rel(out["equity"], a - liab) < TOL_ARITH
    # Property: positive duration gap => rates up (dy>0) => EVE falls
    assert out["duration_gap"] > 0
    assert out["delta_eve"] < 0


def test_duration_gap_invalid_assets():
    with pytest.raises(ValueError):
        duration_gap_analysis(4.0, 2.0, 0.0, 100.0)


def test_convexity_gap_closed_form():
    """CGAP = C_A - (L/A)*C_L. Independent closed-form."""
    c_a, c_l = 25.0, 10.0
    a, liab = 2000.0, 1500.0
    ref = c_a - (liab / a) * c_l
    out = convexity_gap(c_a, c_l, a, liab)
    assert _rel(out["convexity_gap"], ref) < TOL_ARITH


def test_convexity_gap_invalid():
    with pytest.raises(ValueError):
        convexity_gap(1.0, 1.0, 0.0, 1.0)


def test_nii_sensitivity_rate_shock_closed_form():
    """dNII = (RSA-RSL)*drate. Independent closed-form + sign property."""
    rsa, rsl, dy = 1200.0, 900.0, 0.02
    gap_ref = rsa - rsl
    dnii_ref = gap_ref * dy
    out = nii_sensitivity_rate_shock(rsa, rsl, dy)
    assert _rel(out["repricing_gap"], gap_ref) < TOL_ARITH
    assert _rel(out["delta_nii"], dnii_ref) < TOL_ARITH
    # Property: positive gap + rates up => NII rises
    assert out["delta_nii"] > 0


def test_nii_simulation_baseline_closed_form():
    """NII = sum(A*rA) - sum(L*rL). Independent closed-form."""
    ab = np.array([500.0, 300.0])
    ar = np.array([0.05, 0.04])
    lb = np.array([400.0, 200.0])
    lr = np.array([0.02, 0.015])
    income_ref = float(np.sum(ab * ar))
    expense_ref = float(np.sum(lb * lr))
    out = nii_simulation_baseline(ab, ar, lb, lr)
    assert _rel(out["interest_income"], income_ref) < TOL_ARITH
    assert _rel(out["interest_expense"], expense_ref) < TOL_ARITH
    assert _rel(out["nii"], income_ref - expense_ref) < TOL_ARITH


def test_nii_simulation_baseline_mismatch():
    with pytest.raises(ValueError):
        nii_simulation_baseline(
            np.array([1.0]), np.array([0.1, 0.2]), np.array([1.0]), np.array([0.1])
        )


# ======================================================================
# MODULE 2 — engine/alm_nii_eve.py
# ======================================================================


def test_nii_simulation_stress_closed_form():
    """Stressed NII with betas: A*(rA+bA*s) - L*(rL+bL*s). Independent ref."""
    ab = np.array([1000.0])
    ar = np.array([0.04])
    lb = np.array([800.0])
    lr = np.array([0.01])
    s = 0.02
    ba, bl = 1.0, 0.5
    baseline_ref = float(np.sum(ab * ar) - np.sum(lb * lr))
    stressed_ref = float(np.sum(ab * (ar + ba * s)) - np.sum(lb * (lr + bl * s)))
    out = nii_simulation_stress(ab, ar, lb, lr, s, asset_beta=ba, liability_beta=bl)
    assert _rel(out["baseline_nii"], baseline_ref) < TOL_ARITH
    assert _rel(out["stressed_nii"], stressed_ref) < TOL_ARITH
    assert _rel(out["delta_nii"], stressed_ref - baseline_ref) < TOL_ARITH
    # Property: assets reprice faster (beta 1 > 0.5) => rates up helps NII
    assert out["delta_nii"] > 0


def test_nii_simulation_stress_mismatch():
    with pytest.raises(ValueError):
        nii_simulation_stress(
            np.array([1.0, 2.0]), np.array([0.1]), np.array([1.0]), np.array([0.1]), 0.01
        )


def test_eve_closed_form():
    """EVE = PV(assets) - PV(liabilities), continuous discounting. Ref."""
    ac = np.array([100.0, 100.0])
    at = np.array([1.0, 2.0])
    ar = np.array([0.03, 0.035])
    lc = np.array([90.0, 90.0])
    lt = np.array([1.0, 2.0])
    lr = np.array([0.02, 0.025])
    pv_a_ref = float(np.sum(ac * np.exp(-ar * at)))
    pv_l_ref = float(np.sum(lc * np.exp(-lr * lt)))
    out = economic_value_of_equity_eve(ac, at, lc, lt, ar, lr)
    assert _rel(out["pv_assets"], pv_a_ref) < TOL_ARITH
    assert _rel(out["pv_liabilities"], pv_l_ref) < TOL_ARITH
    assert _rel(out["eve"], pv_a_ref - pv_l_ref) < TOL_ARITH


def test_eve_length_mismatch():
    with pytest.raises(ValueError):
        economic_value_of_equity_eve(
            np.array([1.0]),
            np.array([1.0, 2.0]),
            np.array([1.0]),
            np.array([1.0]),
            np.array([0.03]),
            np.array([0.03]),
        )
    with pytest.raises(ValueError):
        economic_value_of_equity_eve(
            np.array([1.0]),
            np.array([1.0]),
            np.array([1.0]),
            np.array([1.0, 2.0]),
            np.array([0.03]),
            np.array([0.03]),
        )


def test_eve_sensitivity_sign_and_ref():
    """dEVE under six shocks, cross-validated against hand-built shocked curve.

    Asset-heavy long-dated net cashflows => positive duration gap => parallel-up
    shock must reduce EVE (dEVE < 0). [REGULATORY] BCBS d368.

    This checks that eve_sensitivity_analysis composes correctly with
    irrbb_six_standard_rate_shocks's output -- it does NOT independently
    anchor the shock construction formula itself (calling that same
    function for the reference means a shared bug there would pass this
    test too). See test_irrbb_six_shocks_matches_bcbs_d368_annex2_worked_example
    for that anchor.
    """
    cf = np.array([50.0, 50.0, 1050.0])  # net long asset position
    t = np.array([1.0, 5.0, 10.0])
    r0 = np.array([0.02, 0.025, 0.03])
    par_bps, short_bps, long_bps = 200.0, 300.0, 150.0
    out = eve_sensitivity_analysis(
        cf, t, r0, parallel_bps=par_bps, short_bps=short_bps, long_bps=long_bps
    )
    base_ref = float(np.sum(cf * np.exp(-r0 * t)))
    assert _rel(out["base_eve"], base_ref) < TOL_ARITH
    # Independent reconstruction of the six shocks and dEVE
    shocks_ref = irrbb_six_standard_rate_shocks(t, par_bps, short_bps, long_bps)
    assert set(out["delta_eve"].keys()) == SIX_SHOCK_NAMES  # exactly six
    for name, shock in shocks_ref.items():
        shocked = r0 + np.asarray(shock)
        d_ref = float(np.sum(cf * np.exp(-shocked * t))) - base_ref
        assert _rel(out["delta_eve"][name], d_ref) < TOL_ARITH
    # Sign: parallel_up must lower EVE for a positive-duration book
    assert out["delta_eve"]["parallel_up"] < 0
    assert out["delta_eve"]["parallel_down"] > 0
    # worst_case is the minimum delta
    assert out["worst_case"] == pytest.approx(min(out["delta_eve"].values()))


def test_eve_sensitivity_mismatch():
    with pytest.raises(ValueError):
        eve_sensitivity_analysis(np.array([1.0, 2.0]), np.array([1.0]), np.array([0.03]))


def test_liquidity_adjusted_nii_closed_form():
    """adj = base + buffer*(yield - funding - premium). Independent hand-calc."""
    base, buf, y, fc, lp = 1000.0, 5000.0, 0.03, 0.04, 0.005
    carry_ref = buf * (y - fc - lp)
    out = liquidity_adjusted_nii(base, buf, y, fc, lp)
    assert _rel(out["buffer_carry"], carry_ref) < TOL_ARITH
    assert _rel(out["adjusted_nii"], base + carry_ref) < TOL_ARITH
    # Property: negative carry (funding > yield) => adjusted < base
    assert out["adjusted_nii"] < base


def test_liquidity_adjusted_nii_invalid():
    with pytest.raises(ValueError):
        liquidity_adjusted_nii(100.0, -1.0, 0.03, 0.02, 0.0)


# ======================================================================
# MODULE 3 — engine/alm_irrbb.py  [REGULATORY BCBS d368]
# ======================================================================


def test_irrbb_exactly_six_shocks_zero_tolerance():
    """[REGULATORY] BCBS d368 Annex 2: EXACTLY six scenarios, exact names. ZERO tol."""
    t = np.array([0.25, 1.0, 5.0, 10.0])
    shocks = irrbb_six_standard_rate_shocks(t, 200.0, 300.0, 150.0)
    assert len(shocks) == 6  # exactly six — zero tolerance
    assert set(shocks.keys()) == SIX_SHOCK_NAMES  # exact names — zero tolerance
    for name in SIX_SHOCK_NAMES:
        assert len(shocks[name]) == t.size  # per-tenor shape


def test_irrbb_six_shocks_construction_ref():
    """[REGULATORY] BCBS d368 Annex 2 construction, cross-validated by hand.

    parallel = +/- par (flat); short = short_bps*e^{-t/4}; long grows as
    (1-e^{-t/4}); steepener = -0.65*short + 0.90*long; flattener = 0.80*short
    - 0.60*long. Signs cross-checked against d368 worked structure.
    """
    t = np.array([0.5, 2.0, 7.0, 20.0])
    par_bps, short_bps, long_bps = 200.0, 300.0, 150.0
    shocks = irrbb_six_standard_rate_shocks(t, par_bps, short_bps, long_bps)
    par = par_bps / 1e4
    s_short = short_bps / 1e4 * np.exp(-t / 4.0)
    s_long = long_bps / 1e4 * (1.0 - np.exp(-t / 4.0))
    # parallel shocks are flat at +/- par
    np.testing.assert_allclose(shocks["parallel_up"], np.full(t.size, par), rtol=TOL_ARITH)
    np.testing.assert_allclose(shocks["parallel_down"], np.full(t.size, -par), rtol=TOL_ARITH)
    np.testing.assert_allclose(shocks["short_up"], s_short, rtol=TOL_ARITH)
    np.testing.assert_allclose(shocks["short_down"], -s_short, rtol=TOL_ARITH)
    np.testing.assert_allclose(shocks["steepener"], -0.65 * s_short + 0.90 * s_long, rtol=TOL_ARITH)
    np.testing.assert_allclose(shocks["flattener"], 0.80 * s_short - 0.60 * s_long, rtol=TOL_ARITH)
    # Sign property: steepener lowers short end, raises long end
    assert shocks["steepener"][0] < 0  # short tenor down
    assert shocks["steepener"][-1] > 0  # long tenor up
    # Flattener: raises short end, lowers long end
    assert shocks["flattener"][0] > 0
    assert shocks["flattener"][-1] < 0


def test_irrbb_six_shocks_matches_bcbs_d368_annex2_worked_example():
    """[REGULATORY] BCBS d368 Annex 2's own published worked example -- a
    genuine external anchor, not a re-derivation of the engine's formula.

    At t_k = 3.5 years with |short shock| = |long shock| = 100bp, Annex 2
    gives steepener = -0.65*100*e^(-3.5/4) + 0.90*100*(1-e^(-3.5/4)) =
    +25.4bp. Independently confirmed via a fresh web search (OSFI's
    Interest Rate Risk Management guideline reproduces the same example)
    and by hand (e^(-3.5/4) = 0.416862..., giving +25.386bp, consistent
    with the published "+25.4bp" at its stated rounding) before being
    written into this test -- found and researched during the Tier 3 #2
    audit, but re-verified independently here rather than taken on trust.

    test_irrbb_six_shocks_construction_ref above (and the three tests that
    build their reference by calling irrbb_six_standard_rate_shocks --
    test_eve_sensitivity_sign_and_ref, test_irrbb_standardised_framework_ref,
    test_alm_stress_test_ref) all check that OTHER functions compose
    correctly with this one's output, but none of them anchor the shock
    CONSTRUCTION formula itself against anything external -- every one of
    them would still pass if this formula's constants were subtly wrong,
    since they'd all agree with each other via the same shared bug. This
    test is that anchor.
    """
    t = np.array([3.5])
    shocks = irrbb_six_standard_rate_shocks(t, parallel_bps=0.0, short_bps=100.0, long_bps=100.0)
    steepener_bps = shocks["steepener"][0] * 1e4
    assert steepener_bps == pytest.approx(25.4, abs=0.05)


def test_irrbb_six_shocks_empty():
    with pytest.raises(ValueError):
        irrbb_six_standard_rate_shocks(np.array([]))


def test_economic_value_helper_closed_form():
    """Helper PV = sum(cf*exp(-r*t)). Independent closed-form."""
    cf = np.array([10.0, 110.0])
    t = np.array([1.0, 2.0])
    r = np.array([0.03, 0.04])
    ref = float(np.sum(cf * np.exp(-r * t)))
    assert _rel(economic_value_helper(cf, t, r), ref) < TOL_ARITH


def test_irrbb_standardised_framework_ref():
    """[REGULATORY] BCBS d368: worst dEVE across six shocks. Cross-validated.

    Composition check only -- see
    test_irrbb_six_shocks_matches_bcbs_d368_annex2_worked_example for the
    external anchor on the shock construction formula itself.
    """
    cf = np.array([100.0, 100.0, 1100.0])
    t = np.array([1.0, 3.0, 8.0])
    r0 = np.array([0.015, 0.02, 0.025])
    out = irrbb_standardised_framework(cf, t, r0, 200.0, 300.0, 150.0)
    base_ref = float(np.sum(cf * np.exp(-r0 * t)))
    assert _rel(out["base_eve"], base_ref) < TOL_ARITH
    assert set(out["delta_eve"].keys()) == SIX_SHOCK_NAMES  # exactly six
    # Independent dEVE reconstruction
    shocks = irrbb_six_standard_rate_shocks(t, 200.0, 300.0, 150.0)
    ref_deltas = {}
    for name, sh in shocks.items():
        ref_deltas[name] = float(np.sum(cf * np.exp(-(r0 + np.asarray(sh)) * t))) - base_ref
    for name in SIX_SHOCK_NAMES:
        assert _rel(out["delta_eve"][name], ref_deltas[name]) < TOL_ARITH
    # worst_case and worst_scenario consistent with reconstruction
    worst_ref = min(ref_deltas.values())
    worst_name_ref = min(ref_deltas, key=lambda k: ref_deltas[k])
    assert out["worst_case"] == pytest.approx(worst_ref, abs=1e-4)
    assert out["worst_scenario"] == worst_name_ref


def test_irrbb_standardised_mismatch():
    with pytest.raises(ValueError):
        irrbb_standardised_framework(np.array([1.0]), np.array([1.0, 2.0]), np.array([0.02]))


def test_irrbb_internal_model_ref():
    """Internal model EVE distribution over own scenarios. Independent ref + determinism."""
    cf = np.array([100.0, 1100.0])
    t = np.array([1.0, 5.0])
    r0 = np.array([0.02, 0.03])
    rng = np.random.default_rng(12345)
    scen = rng.normal(0.0, 0.005, size=(2000, 2))
    out = irrbb_internal_model(cf, t, r0, scen)
    base_ref = float(np.sum(cf * np.exp(-r0 * t)))
    deltas_ref = np.array(
        [float(np.sum(cf * np.exp(-(r0 + scen[i]) * t))) - base_ref for i in range(scen.shape[0])]
    )
    assert _rel(out["base_eve"], base_ref) < TOL_ARITH
    assert _rel(out["mean_delta_eve"], float(np.mean(deltas_ref))) < TOL_SIM
    assert out["worst_case_99"] == pytest.approx(
        float(np.percentile(deltas_ref, 1.0)), abs=abs(base_ref) * TOL_SIM
    )
    # Determinism: same seed => identical result
    scen2 = np.random.default_rng(12345).normal(0.0, 0.005, size=(2000, 2))
    out2 = irrbb_internal_model(cf, t, r0, scen2)
    assert out2["mean_delta_eve"] == out["mean_delta_eve"]


def test_irrbb_internal_model_bad_shape():
    with pytest.raises(ValueError):
        irrbb_internal_model(
            np.array([1.0, 2.0]),
            np.array([1.0, 2.0]),
            np.array([0.02, 0.03]),
            np.array([0.01, 0.02]),
        )  # 1D
    with pytest.raises(ValueError):
        # cf/t/r0 length mismatch branch
        irrbb_internal_model(
            np.array([1.0]), np.array([1.0, 2.0]), np.array([0.02, 0.03]), np.zeros((5, 1))
        )


def test_repricing_gap_analysis_closed_form():
    """gap_i = RSA_i - RSL_i; cumulative = cumsum. Independent closed-form."""
    a = np.array([300.0, 200.0, 500.0])
    liab = np.array([250.0, 300.0, 100.0])
    gap_ref = a - liab
    cum_ref = np.cumsum(gap_ref)
    out = repricing_gap_analysis(a, liab, bucket_labels=["m1", "m2", "m3"])
    assert _rel(out["gap"]["m1"], gap_ref[0]) < TOL_ARITH
    assert _rel(out["gap"]["m3"], gap_ref[2]) < TOL_ARITH
    for i in range(3):
        assert _rel(out["cumulative_gap"][i], cum_ref[i]) < TOL_ARITH
    assert _rel(out["total_gap"], float(np.sum(gap_ref))) < TOL_ARITH


def test_repricing_gap_default_labels_and_mismatch():
    out = repricing_gap_analysis(np.array([1.0, 2.0]), np.array([0.5, 0.5]))
    assert "bucket_0" in out["gap"]
    with pytest.raises(ValueError):
        repricing_gap_analysis(np.array([1.0]), np.array([1.0, 2.0]))


def test_repricing_maturity_profile_ref():
    """Balances allocated to buckets by digitize; wavg = sum(b*rt)/sum(b). Ref."""
    b = np.array([100.0, 200.0, 300.0, 400.0])
    rt = np.array([0.1, 0.6, 1.5, 4.0])
    edges = np.array([0.0, 0.5, 1.0, 2.0, 5.0])  # 4 buckets
    out = repricing_maturity_profile(b, rt, 4, edges)
    # Independent digitize onto interior edges
    idx = np.clip(np.digitize(rt, edges[1:-1]), 0, 3)
    profile_ref = np.zeros(4)
    for k in range(b.size):
        profile_ref[idx[k]] += b[k]
    for i in range(4):
        assert _rel(out["profile"][i], profile_ref[i]) < TOL_ARITH
    wavg_ref = float(np.sum(b * rt) / np.sum(b))
    assert _rel(out["weighted_avg_repricing"], wavg_ref) < TOL_ARITH
    # Conservation: total allocated == total balance
    assert _rel(sum(out["profile"]), float(np.sum(b))) < TOL_ARITH


def test_repricing_maturity_profile_invalid():
    with pytest.raises(ValueError):
        repricing_maturity_profile(
            np.array([1.0]), np.array([1.0, 2.0]), 2, np.array([0.0, 1.0, 2.0])
        )
    with pytest.raises(ValueError):
        repricing_maturity_profile(
            np.array([1.0]), np.array([1.0]), 2, np.array([0.0, 1.0])
        )  # wrong edges length


def test_static_gap_analysis_closed_form():
    """gap = A-L; gap_ratio = sum(A)/sum(L). Independent closed-form."""
    a = np.array([400.0, 600.0])
    liab = np.array([300.0, 500.0])
    gap_ref = a - liab
    ratio_ref = float(np.sum(a) / np.sum(liab))
    out = static_gap_analysis(a, liab)
    for i in range(2):
        assert _rel(out["gap"][i], gap_ref[i]) < TOL_ARITH
    assert _rel(out["gap_ratio"], ratio_ref) < TOL_ARITH


def test_static_gap_mismatch():
    with pytest.raises(ValueError):
        static_gap_analysis(np.array([1.0]), np.array([1.0, 2.0]))


def test_dynamic_gap_analysis_closed_form():
    """Projected gap_p = sum(A*(1+g)^p - L*(1+g)^p). Independent hand-calc."""
    a = np.array([1000.0])
    liab = np.array([800.0])
    ag = np.array([0.05])
    lg = np.array([0.03])
    n = 3
    ref = []
    for p in range(1, n + 1):
        ref.append(float(np.sum(a * (1 + ag) ** p - liab * (1 + lg) ** p)))
    out = dynamic_gap_analysis(a, liab, ag, lg, n)
    assert len(out["projected_total_gap"]) == n
    for i in range(n):
        assert _rel(out["projected_total_gap"][i], ref[i]) < TOL_ARITH


def test_dynamic_gap_mismatch():
    with pytest.raises(ValueError):
        dynamic_gap_analysis(
            np.array([1.0]), np.array([1.0]), np.array([0.1, 0.2]), np.array([0.1]), 2
        )


def test_basis_risk_irrbb_closed_form():
    """[REGULATORY] BCBS d368 basis risk: dNII = sum(A*di_A) - sum(L*di_L). Ref."""
    ab = np.array([1000.0, 500.0])
    ash = np.array([0.01, 0.008])
    lb = np.array([900.0, 400.0])
    lsh = np.array([0.006, 0.005])
    ref = float(np.sum(ab * ash) - np.sum(lb * lsh))
    out = basis_risk_irrbb(ab, ash, lb, lsh)
    assert _rel(out["basis_risk_nii"], ref) < TOL_ARITH


def test_basis_risk_mismatch():
    with pytest.raises(ValueError):
        basis_risk_irrbb(np.array([1.0, 2.0]), np.array([0.1]), np.array([1.0]), np.array([0.1]))


def test_option_risk_irrbb_closed_form():
    """[REGULATORY] BCBS d368: total = automatic + behavioural; ratio = total/notional."""
    auto, beh, notional = 12.0, 8.0, 1000.0
    out = option_risk_irrbb(auto, beh, notional)
    assert _rel(out["total_option_risk"], auto + beh) < TOL_ARITH
    assert _rel(out["option_risk_ratio"], (auto + beh) / notional) < TOL_ARITH


def test_option_risk_invalid():
    with pytest.raises(ValueError):
        option_risk_irrbb(1.0, 1.0, 0.0)


def test_pipeline_risk_closed_form():
    """exposure = notional*pull_through; rate_risk = exposure*vol*sqrt(T). Hand-calc."""
    notional, pull, lock, vol = 10_000_000.0, 0.75, 0.25, 0.15
    exp_ref = notional * pull
    rr_ref = exp_ref * vol * math.sqrt(lock)
    out = pipeline_risk_measurement(notional, pull, lock, vol)
    assert _rel(out["expected_exposure"], exp_ref) < TOL_ARITH
    assert _rel(out["rate_risk"], rr_ref) < TOL_ARITH


def test_pipeline_risk_invalid():
    with pytest.raises(ValueError):
        pipeline_risk_measurement(1.0, 1.5, 0.25, 0.1)  # pull-through > 1
    with pytest.raises(ValueError):
        pipeline_risk_measurement(1.0, 0.5, -0.1, 0.1)  # negative lock


def test_irrbb_capital_outlier_ref():
    """[REGULATORY] BCBS d368 Principle 12: outlier if EVE decline > 15% Tier1. Hand-calc."""
    tier1 = 1000.0
    # Case 1: breach
    worst = -200.0
    out = interest_rate_risk_capital_irrbb(worst, tier1, outlier_threshold=0.15)
    assert _rel(out["eve_decline"], 200.0) < TOL_ARITH
    assert _rel(out["threshold_amount"], 150.0) < TOL_ARITH
    assert out["is_outlier"] is True
    assert _rel(out["capital_add_on"], 50.0) < TOL_ARITH
    # Case 2: no breach (positive dEVE => zero decline)
    out2 = interest_rate_risk_capital_irrbb(50.0, tier1)
    assert out2["eve_decline"] == pytest.approx(0.0)
    assert out2["is_outlier"] is False
    assert out2["capital_add_on"] == pytest.approx(0.0)


def test_irrbb_capital_invalid():
    with pytest.raises(ValueError):
        interest_rate_risk_capital_irrbb(-10.0, 0.0)


def test_asset_liability_mismatch_index_ref():
    """Index = |D_A*A - D_L*L| / A. Independent closed-form."""
    ad = np.array([4.0, 2.0])
    aa = np.array([600.0, 400.0])
    ld = np.array([1.5, 1.0])
    la = np.array([500.0, 300.0])
    a_dollar_ref = float(np.sum(ad * aa))
    l_dollar_ref = float(np.sum(ld * la))
    idx_ref = abs(a_dollar_ref - l_dollar_ref) / float(np.sum(aa))
    out = asset_liability_mismatch_index(ad, aa, ld, la)
    assert _rel(out["asset_dollar_duration"], a_dollar_ref) < TOL_ARITH
    assert _rel(out["liability_dollar_duration"], l_dollar_ref) < TOL_ARITH
    assert _rel(out["mismatch_index"], idx_ref) < TOL_ARITH


def test_almmi_mismatch():
    with pytest.raises(ValueError):
        asset_liability_mismatch_index(
            np.array([1.0]), np.array([1.0, 2.0]), np.array([1.0]), np.array([1.0])
        )


# ======================================================================
# MODULE 4 — engine/alm_behavioural.py
# ======================================================================


def test_cpr_smm_conversion_closed_form():
    """CPR = 1-(1-SMM)^12; SMM = 1-(1-CPR)^{1/12}. Textbook closed-form both ways."""
    # SMM -> CPR
    smm = 0.005
    cpr_ref = 1.0 - (1.0 - smm) ** 12
    out = loan_prepayment_rate_cpr(smm=smm)
    assert _rel(out["cpr"], cpr_ref) < TOL_ARITH
    assert _rel(out["smm"], smm) < TOL_ARITH
    # CPR -> SMM
    cpr = 0.06
    smm_ref = 1.0 - (1.0 - cpr) ** (1.0 / 12.0)
    out2 = loan_prepayment_rate_cpr(cpr=cpr)
    assert _rel(out2["smm"], smm_ref) < TOL_ARITH
    assert _rel(out2["cpr"], cpr) < TOL_ARITH
    # Round-trip consistency (independent cross-check)
    assert _rel(loan_prepayment_rate_cpr(smm=out2["smm"])["cpr"], cpr) < TOL_ARITH


def test_cpr_smm_invalid():
    with pytest.raises(ValueError):
        loan_prepayment_rate_cpr()  # neither
    with pytest.raises(ValueError):
        loan_prepayment_rate_cpr(smm=0.1, cpr=0.1)  # both
    with pytest.raises(ValueError):
        loan_prepayment_rate_cpr(smm=1.0)  # smm out of range
    with pytest.raises(ValueError):
        loan_prepayment_rate_cpr(cpr=1.0)  # cpr out of range branch


def test_prepayment_model_mortgages_ref():
    """Independent hand-calc of amortisation+prepay (no published PSA reference).

    Reproduce the month-by-month level-payment schedule with constant SMM run-off
    in pure Python and compare total cashflow and WAL. Marked: independent
    hand-calc, no published reference.
    """
    principal, annual, term, cpr = 1_000_000.0, 0.06, 5, 0.10
    smm = 1.0 - (1.0 - cpr) ** (1.0 / 12.0)
    n = term * 12
    mr = annual / 12.0
    pmt = principal * mr / (1.0 - (1.0 + mr) ** (-n))
    bal = principal
    cfs = []
    for _ in range(n):
        interest = bal * mr
        sched = min(pmt - interest, bal)
        after = bal - sched
        prepay = after * smm
        cfs.append(interest + sched + prepay)
        bal = max(after - prepay, 0.0)
    cfs = np.array(cfs)
    months = np.arange(1, n + 1)
    total_ref = float(np.sum(cfs))
    wal_ref = float(np.sum(months / 12.0 * cfs) / total_ref)
    out = prepayment_model_mortgages(principal, annual, term, cpr)
    assert _rel(out["total_cashflow"], total_ref) < TOL_SIM
    assert _rel(out["weighted_average_life"], wal_ref) < TOL_SIM
    assert _rel(out["smm"], smm) < TOL_ARITH
    # Property: higher CPR shortens WAL
    out_hi = prepayment_model_mortgages(principal, annual, term, 0.30)
    assert out_hi["weighted_average_life"] < out["weighted_average_life"]


def test_prepayment_model_invalid():
    with pytest.raises(ValueError):
        prepayment_model_mortgages(0.0, 0.05, 5, 0.1)
    with pytest.raises(ValueError):
        prepayment_model_mortgages(1000.0, 0.05, 5, 1.0)


def test_prepayment_zero_rate_branch():
    """Zero-coupon amortisation branch: pmt = principal/n. Independent hand-calc."""
    principal, term = 120_000.0, 1
    smm = 1.0 - (1.0 - 0.0) ** (1.0 / 12.0)  # cpr=0 => smm=0
    out = prepayment_model_mortgages(principal, 0.0, term, 0.0)
    # No prepay, no interest => total cashflow == principal
    assert _rel(out["total_cashflow"], principal) < TOL_SIM
    assert out["smm"] == pytest.approx(smm)


def test_behavioural_nmd_ref():
    """Independent hand-calc (no published reference) of NMD run-off.

    core_surv = core*exp(-r_c*H); non_core_surv = nc*exp(-r_nc*H);
    eff_life = (core/ r_c + nc/ r_nc)/total. Marked: independent hand-calc.
    """
    total, cf_frac, rc, rnc, H = 1_000_000.0, 0.7, 0.05, 0.30, 5.0
    core = total * cf_frac
    nc = total * (1 - cf_frac)
    core_surv = core * math.exp(-rc * H)
    nc_surv = nc * math.exp(-rnc * H)
    surv_ref = core_surv + nc_surv
    eff_ref = (core * (1.0 / rc) + nc * (1.0 / rnc)) / total
    out = behavioural_modelling_nmds(total, cf_frac, rc, rnc, horizon_years=H)
    assert _rel(out["core_balance"], core) < TOL_ARITH
    assert _rel(out["non_core_balance"], nc) < TOL_ARITH
    assert _rel(out["surviving_balance"], surv_ref) < TOL_SIM
    assert _rel(out["effective_life"], eff_ref) < TOL_SIM
    # Property: core (slower run-off) survives at higher fraction than non-core
    assert core_surv / core > nc_surv / nc


def test_behavioural_nmd_invalid():
    with pytest.raises(ValueError):
        behavioural_modelling_nmds(1000.0, 1.5, 0.05, 0.3)


def test_nmd_stability_ref():
    """Independent hand-calc: stable = percentile(history, (1-cl)*100). No ref."""
    hist = np.array([100.0, 110.0, 95.0, 120.0, 105.0, 90.0, 130.0, 115.0])
    cl = 0.90
    stable_ref = float(np.percentile(hist, (1.0 - cl) * 100.0))
    current = float(hist[-1])
    volatile_ref = max(current - stable_ref, 0.0)
    frac_ref = stable_ref / current
    out = non_maturity_deposit_stability(hist, confidence_level=cl)
    assert _rel(out["stable_balance"], stable_ref) < TOL_ARITH
    assert _rel(out["volatile_balance"], volatile_ref) < TOL_ARITH
    assert _rel(out["stable_fraction"], frac_ref) < TOL_ARITH


def test_nmd_stability_invalid():
    with pytest.raises(ValueError):
        non_maturity_deposit_stability(np.array([100.0]))
    with pytest.raises(ValueError):
        non_maturity_deposit_stability(np.array([1.0, 2.0]), confidence_level=0.4)


def test_core_deposit_duration_ref():
    """Independent hand-calc of PV-weighted life of a decaying-annuity run-off. No ref.

    Reproduce the discretised monthly run-off and PV-weighted duration.
    """
    core, decay, disc, maxy = 1_000_000.0, 0.20, 0.03, 30.0
    times = np.arange(1.0 / 12.0, maxy + 1e-9, 1.0 / 12.0)
    runoff = core * decay * np.exp(-decay * times) / 12.0
    df = np.exp(-disc * times)
    pv = runoff * df
    total_pv = float(np.sum(pv))
    dur_ref = float(np.sum(times * pv) / total_pv)
    out = core_deposit_duration(core, decay, disc, max_years=maxy)
    assert _rel(out["core_deposit_duration"], dur_ref) < TOL_ARITH
    assert _rel(out["present_value"], total_pv) < TOL_ARITH
    # Property: slower decay => longer duration
    out_slow = core_deposit_duration(core, 0.05, disc, max_years=maxy)
    assert out_slow["core_deposit_duration"] > out["core_deposit_duration"]


def test_core_deposit_duration_invalid():
    with pytest.raises(ValueError):
        core_deposit_duration(1000.0, 0.0, 0.03)
    with pytest.raises(ValueError):
        core_deposit_duration(-1.0, 0.1, 0.03)


# ======================================================================
# MODULE 5 — engine/alm_ftp.py
# ======================================================================


def test_ftp_single_deal_asset_ref():
    """Independent hand-calc: asset commercial = (cust - (ftp+liq))*notional. No ref."""
    notional, cust, ftp, liq = 1_000_000.0, 0.06, 0.03, 0.005
    all_in = ftp + liq
    comm_ref = (cust - all_in) * notional
    fund_ref = all_in * notional
    spread_ref = abs(cust - all_in) * notional
    out = funds_transfer_pricing_ftp(notional, cust, ftp, liquidity_premium=liq, is_asset=True)
    assert _rel(out["commercial_margin"], comm_ref) < TOL_ARITH
    assert _rel(out["funding_value"], fund_ref) < TOL_ARITH
    assert _rel(out["total_spread"], spread_ref) < TOL_ARITH


def test_ftp_single_deal_liability_ref():
    """Liability: commercial = ((ftp+liq) - cust)*notional. Independent hand-calc."""
    notional, cust, ftp, liq = 500_000.0, 0.01, 0.025, 0.0
    all_in = ftp + liq
    comm_ref = (all_in - cust) * notional
    out = funds_transfer_pricing_ftp(notional, cust, ftp, liquidity_premium=liq, is_asset=False)
    assert _rel(out["commercial_margin"], comm_ref) < TOL_ARITH
    # Deposit at cost below FTP => positive contribution to the unit
    assert out["commercial_margin"] > 0


def test_ftp_invalid():
    with pytest.raises(ValueError):
        funds_transfer_pricing_ftp(0.0, 0.05, 0.03)


def test_ftp_curve_construction_ref():
    """Independent hand-calc: ftp = base + liquidity_spread per tenor. No ref."""
    tenors = np.array([1.0, 3.0, 5.0, 10.0])
    base = np.array([0.02, 0.025, 0.03, 0.035])
    liq = np.array([0.001, 0.002, 0.004, 0.007])
    ref = base + liq
    out = ftp_curve_construction(tenors, base, liq)
    for i in range(tenors.size):
        assert _rel(out["ftp_curve"][i], ref[i]) < TOL_ARITH
    assert out["tenors"] == tenors.tolist()


def test_ftp_curve_mismatch():
    with pytest.raises(ValueError):
        ftp_curve_construction(np.array([1.0, 2.0]), np.array([0.02]), np.array([0.001]))


def test_structural_hedge_optimisation_ref():
    """Independent hand-calc (no published reference) of bounded LSQ hedge.

    Target dollar-duration = equity*target_dur. With one instrument of
    duration d and a cap above the required notional, the solver should pick
    n* = target_dollar/d exactly (unconstrained interior solution).
    """
    equity, target_dur = 1_000_000.0, 3.0
    d = np.array([6.0])  # single 6y instrument
    cap = np.array([1_000_000.0])  # cap high enough
    target_dollar = equity * target_dur
    n_star_ref = target_dollar / d[0]
    out = structural_hedge_optimisation(target_dur, d, cap, equity)
    assert _rel(out["hedge_notionals"][0], n_star_ref) < TOL_SIM
    assert _rel(out["achieved_duration"], target_dur) < TOL_SIM
    assert abs(out["residual"]) < 1.0  # near-zero residual (unconstrained)
    # Constrained case: cap below required notional => residual < 0 (undershoot)
    cap_low = np.array([100_000.0])
    out2 = structural_hedge_optimisation(target_dur, d, cap_low, equity)
    assert out2["hedge_notionals"][0] == pytest.approx(100_000.0, rel=TOL_SIM)
    assert out2["residual"] < 0


def test_structural_hedge_invalid():
    with pytest.raises(ValueError):
        structural_hedge_optimisation(3.0, np.array([1.0, 2.0]), np.array([1.0]), 1e6)
    with pytest.raises(ValueError):
        structural_hedge_optimisation(3.0, np.array([1.0]), np.array([1.0]), 0.0)


def test_alm_stress_test_ref():
    """[REGULATORY] BCBS d368: worst dEVE / Tier1; breach if > 15%. Cross-validated.

    Independently compute worst-case dEVE via eve_sensitivity reconstruction and
    the capital ratio. Composition check only, same caveat as
    test_eve_sensitivity_sign_and_ref -- see
    test_irrbb_six_shocks_matches_bcbs_d368_annex2_worked_example for the
    external anchor on the shock construction formula itself.
    """
    cf = np.array([100.0, 100.0, 2000.0])
    t = np.array([1.0, 5.0, 12.0])
    r0 = np.array([0.02, 0.025, 0.03])
    tier1 = 500.0
    out = alm_stress_test(cf, t, r0, tier1, parallel_bps=200.0)
    # Independent worst-case via shock reconstruction
    base = float(np.sum(cf * np.exp(-r0 * t)))
    shocks = irrbb_six_standard_rate_shocks(t, 200.0, 300.0, 150.0)
    deltas = [
        float(np.sum(cf * np.exp(-(r0 + np.asarray(sh)) * t))) - base for sh in shocks.values()
    ]
    worst_ref = min(deltas)
    ratio_ref = abs(min(worst_ref, 0.0)) / tier1
    assert out["worst_case_eve"] == pytest.approx(worst_ref, abs=1e-3)
    assert _rel(out["eve_capital_ratio"], ratio_ref) < TOL_SIM
    assert out["breaches_15pct"] is bool(ratio_ref > 0.15)


def test_alm_stress_test_invalid():
    with pytest.raises(ValueError):
        alm_stress_test(np.array([1.0]), np.array([1.0]), np.array([0.02]), 0.0)


def test_balance_sheet_projection_ref():
    """Independent hand-calc (no published reference): geometric growth paths.

    A_y = A0*(1+g)^y; L_y = L0*(1+g)^y; equity = A-L; NII = A*yield - L*cost.
    """
    a0, l0 = 10_000.0, 8_000.0
    ag, lg = 0.05, 0.03
    ay, lc = 0.04, 0.015
    n = 3
    years = np.arange(1, n + 1)
    a_ref = a0 * (1 + ag) ** years
    l_ref = l0 * (1 + lg) ** years
    eq_ref = a_ref - l_ref
    nii_ref = a_ref * ay - l_ref * lc
    out = balance_sheet_projection_model(a0, l0, ag, lg, ay, lc, n)
    assert len(out["assets"]) == n
    for i in range(n):
        assert _rel(out["assets"][i], a_ref[i]) < TOL_ARITH
        assert _rel(out["liabilities"][i], l_ref[i]) < TOL_ARITH
        assert _rel(out["equity"][i], eq_ref[i]) < TOL_ARITH
        assert _rel(out["nii"][i], nii_ref[i]) < TOL_ARITH


def test_balance_sheet_projection_invalid():
    with pytest.raises(ValueError):
        balance_sheet_projection_model(1e4, 8e3, 0.05, 0.03, 0.04, 0.015, 0)

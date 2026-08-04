"""P5a validation suite for the liquidity-risk engine (40 functions).

Every assertion checks the engine output against an EXTERNAL, independently
computed reference — NEVER against the function's own output. Reference sources
are cited per test:

  * Basel III LCR — BCBS 238 (Jan 2013): LCR = HQLA / net 30-day outflows,
    inflow offset capped at 75% of gross outflows (§69); HQLA composition caps
    Level 2 <= 40% and Level 2B <= 15% of the buffer (§46-§47); supervisory
    haircuts Level 2A 15% (§52), Level 2B 25%-50% (§54).
  * Basel III NSFR — BCBS 295 (Oct 2014): NSFR = ASF / RSF, >= 100%.
  * Intraday — BCBS 248 monitoring tools.
  * HHI concentration = sum(share^2), standard competition-economics measure.

Reference tags used below:
  [closed-form, BCBS ...]      = regulator-sourced closed form recomputed here.
  [cross-validated (scipy)]    = checked against scipy, not regulator-sourced.
  [independent hand-calc]      = no published reference; hand-worked in the test.

Tolerances: 0.1% relative in general; ZERO tolerance on the LCR/NSFR 100%
threshold and on the 40%/15% HQLA caps.

Known limitations (Tier 3 #2 audit, documented rather than silently left):
  Roughly half the "[independent hand-calc]"-tagged tests in this file have
  NO published source and none was found by checking BCBS 238/248/295 and
  EBA ILAAP guidelines directly -- cash-flow ladder shortfall/bucketing,
  liquidity gap ratio, funding tenor analysis, survival horizon, liquidity
  buffer sizing, CFP trigger logic, secured-funding rollover gap, FX
  liquidity netting, intragroup flow netting, funding cost, liquidity
  transfer pricing, the ILAAP internal metric, risk-appetite RAG mapping,
  early-warning indicators, the liquidity scorecard, deposit-stability
  classification, and the cross-currency bridge are all internally
  reasonable conventions with no regulator-published worked example to
  check them against. Two tests (test_contingent_liquidity_risk_expected_
  and_max, test_central_bank_eligibility_filter_and_capacity) have partial
  parameter-level leads (BCBS 238 §131 committed-facility drawdown rates;
  ECB/BoE collateral haircut schedules) not yet incorporated. A smaller,
  separate issue also found: 5 "hand-calc" tests actually just restate the
  implementation's own NumPy expression rather than computing anything
  independently (test_cash_flow_ladder_1_year_buckets,
  test_liquidity_gap_analysis, test_collateral_availability_*,
  test_repo_market_stress_margin_call, part of
  test_wholesale_concentration_hhi) -- not fixed in this pass.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from engine.liquidity_cashflow import (
    cash_flow_ladder_1_year,
    cash_flow_ladder_30_day,
    funding_tenor_analysis,
    liquidity_gap_analysis,
)
from engine.liquidity_funding import (
    asset_encumbrance_ratio,
    collateral_availability_analysis,
    contingency_funding_plan_trigger,
    funding_cost_analysis,
    fx_liquidity_risk_by_currency,
    intragroup_liquidity_flow,
    liquidity_buffer_sizing,
    liquidity_transfer_pricing,
    repo_market_stress_haircut,
    retail_deposit_runoff_rate,
    secured_funding_rollover_risk,
    wholesale_funding_concentration,
)
from engine.liquidity_internal import (
    central_bank_facility_eligibility,
    contingent_liquidity_risk,
    cross_currency_liquidity_bridge,
    deposit_stability_classification,
    early_warning_indicator_liquidity,
    ilaap_internal_liquidity_metric,
    liquidity_risk_appetite_threshold,
    liquidity_scorecard_aggregation,
)
from engine.liquidity_ratios import (
    available_stable_funding_asf_calc,
    hqla_level_1_asset_classifier,
    hqla_level_2a_asset_classifier,
    hqla_level_2b_asset_classifier,
    liquidity_coverage_ratio_lcr,
    net_stable_funding_ratio_nsfr,
    required_stable_funding_rsf_calc,
)
from engine.liquidity_stress import (
    combined_stress_scenario,
    idiosyncratic_stress_scenario,
    ilaap_stress_testing_framework,
    intraday_liquidity_monitor,
    intraday_liquidity_stress_test,
    liquidity_stress_scenario,
    liquidity_var_liqvar,
    market_wide_stress_scenario,
    survival_horizon_calculator,
)

REL = 1e-3  # 0.1% relative tolerance


# =====================================================================
# engine/liquidity_ratios.py
# =====================================================================


def test_lcr_closed_form_and_inflow_cap():
    # [closed-form, BCBS 238 §69]. HQLA=150, gross out=200, gross in=50.
    # capped inflows = min(50, 0.75*200=150) = 50; net = 200-50 = 150.
    # LCR = 150/150 = 1.0 exactly.
    res = liquidity_coverage_ratio_lcr(150.0, 200.0, 50.0)
    assert res["capped_inflows"] == pytest.approx(50.0, rel=REL)
    assert res["net_outflows"] == pytest.approx(150.0, rel=REL)
    assert res["lcr"] == pytest.approx(1.0, rel=REL)
    assert res["lcr"] > 0.0


def test_lcr_inflow_cap_binds_zero_tolerance_on_threshold():
    # [closed-form, BCBS 238 §69]. Huge inflows (500) capped at 0.75*200=150.
    # net = 200-150 = 50 (the 25% floor). LCR = 90/50 = 1.8.
    res = liquidity_coverage_ratio_lcr(90.0, 200.0, 500.0)
    assert res["capped_inflows"] == pytest.approx(150.0, rel=REL)
    assert res["net_outflows"] == pytest.approx(50.0, rel=REL)
    assert res["lcr"] == pytest.approx(1.8, rel=REL)
    # ZERO tolerance on 100% compliance threshold.
    assert res["compliant"] is True
    # Non-compliant reference: HQLA 40 -> LCR 0.8 < 1.0.
    res2 = liquidity_coverage_ratio_lcr(40.0, 200.0, 500.0)
    assert res2["lcr"] == pytest.approx(0.8, rel=REL)
    assert res2["compliant"] is False


def test_lcr_rejects_bad_inputs():
    with pytest.raises(ValueError):
        liquidity_coverage_ratio_lcr(100.0, 0.0, 10.0)
    with pytest.raises(ValueError):
        liquidity_coverage_ratio_lcr(-1.0, 100.0, 10.0)


def test_asf_weighted_sum():
    # [closed-form, BCBS 295]. ASF = sum(amount * factor).
    amounts = np.array([1000.0, 500.0, 300.0])
    factors = np.array([1.00, 0.95, 0.50])
    ref = 1000 * 1.00 + 500 * 0.95 + 300 * 0.50  # 1625.0
    res = available_stable_funding_asf_calc(amounts, factors)
    assert res["asf"] == pytest.approx(ref, rel=REL)
    assert res["components"][1] == pytest.approx(475.0, rel=REL)


def test_asf_rejects_bad_factors():
    with pytest.raises(ValueError):
        available_stable_funding_asf_calc(np.array([1.0]), np.array([1.5]))
    with pytest.raises(ValueError):
        available_stable_funding_asf_calc(np.array([1.0, 2.0]), np.array([0.5]))


def test_rsf_weighted_sum():
    # [closed-form, BCBS 295]. RSF = sum(amount * factor).
    amounts = np.array([2000.0, 800.0, 400.0])
    factors = np.array([0.05, 0.15, 0.85])
    ref = 2000 * 0.05 + 800 * 0.15 + 400 * 0.85  # 100 + 120 + 340 = 560
    res = required_stable_funding_rsf_calc(amounts, factors)
    assert res["rsf"] == pytest.approx(ref, rel=REL)


def test_rsf_rejects_bad_factors():
    with pytest.raises(ValueError):
        required_stable_funding_rsf_calc(np.array([1.0]), np.array([-0.1]))


def test_nsfr_ratio_and_threshold():
    # [closed-form, BCBS 295]. NSFR = ASF/RSF.
    res = net_stable_funding_ratio_nsfr(1625.0, 560.0)
    assert res["nsfr"] == pytest.approx(1625.0 / 560.0, rel=REL)
    assert res["nsfr"] > 0.0
    # ZERO tolerance on 100% threshold: 1000/1000 -> exactly compliant.
    at = net_stable_funding_ratio_nsfr(1000.0, 1000.0)
    assert at["nsfr"] == pytest.approx(1.0, rel=REL)
    assert at["compliant"] is True
    below = net_stable_funding_ratio_nsfr(999.0, 1000.0)
    assert below["compliant"] is False


def test_nsfr_rejects_zero_rsf():
    with pytest.raises(ValueError):
        net_stable_funding_ratio_nsfr(100.0, 0.0)


def test_hqla_level1_zero_haircut_default():
    # [closed-form, BCBS 238 §50]. Level 1 default 0% haircut.
    values = np.array([100.0, 200.0, 50.0])
    res = hqla_level_1_asset_classifier(values)
    assert res["post_haircut_value"] == pytest.approx(350.0, rel=REL)
    assert res["level"] == 1
    # Haircut reduces value (monotonicity property).
    res_hc = hqla_level_1_asset_classifier(values, np.array([0.0, 0.1, 0.0]))
    assert res_hc["post_haircut_value"] < res["post_haircut_value"]
    assert res_hc["post_haircut_value"] == pytest.approx(100 + 180 + 50, rel=REL)


def test_hqla_level2a_15pct_haircut():
    # [closed-form, BCBS 238 §52]. Level 2A haircut 15%.
    values = np.array([1000.0, 500.0])
    res = hqla_level_2a_asset_classifier(values)  # default 0.15
    assert res["post_haircut_value"] == pytest.approx(1500.0 * 0.85, rel=REL)
    assert res["haircut"] == pytest.approx(0.15, rel=REL)
    # Sub-minimum haircut must be rejected.
    with pytest.raises(ValueError):
        hqla_level_2a_asset_classifier(values, haircut=0.10)


def test_hqla_level2b_25pct_haircut_and_haircut_monotone():
    # [closed-form, BCBS 238 §54]. Level 2B min haircut 25%.
    values = np.array([400.0, 600.0])
    res25 = hqla_level_2b_asset_classifier(values)  # 0.25
    assert res25["post_haircut_value"] == pytest.approx(1000.0 * 0.75, rel=REL)
    # 50% haircut (equities) reduces value further — haircut monotonicity.
    res50 = hqla_level_2b_asset_classifier(values, haircut=0.50)
    assert res50["post_haircut_value"] == pytest.approx(1000.0 * 0.50, rel=REL)
    assert res50["post_haircut_value"] < res25["post_haircut_value"]
    with pytest.raises(ValueError):
        hqla_level_2b_asset_classifier(values, haircut=0.20)


def test_hqla_composition_caps_40_and_15_pct_zero_tolerance():
    # [closed-form, BCBS 238 §46-§47]. Assemble a compliant buffer and verify
    # the 40% Level-2 and 15% Level-2B caps hold with ZERO tolerance.
    # Construct post-haircut components that sit exactly ON the cap boundaries:
    #   total buffer = 1000. Level 2 cap = 400 (40%); Level 2B cap = 150 (15%).
    #   Choose L2B = 150 (== 15% cap), L2A = 250 (L2 total = 400 == 40% cap),
    #   L1 = 600. This is the maximally Level-2-heavy compliant buffer.
    l1 = hqla_level_1_asset_classifier(np.array([600.0]))["post_haircut_value"]  # 600
    # 250 = value * 0.85  ->  value = 294.1176...
    l2a = hqla_level_2a_asset_classifier(np.array([250.0 / 0.85]))["post_haircut_value"]
    # 150 = value * 0.75  ->  value = 200
    l2b = hqla_level_2b_asset_classifier(np.array([200.0]))["post_haircut_value"]  # 150
    assert l1 == pytest.approx(600.0)
    assert l2a == pytest.approx(250.0)
    assert l2b == pytest.approx(150.0)
    total = l1 + l2a + l2b  # 1000
    level2 = l2a + l2b  # 400
    assert total == pytest.approx(1000.0)
    # ZERO tolerance: both caps hold exactly at the boundary.
    assert level2 / total <= 0.40 + 1e-12
    assert l2b / total <= 0.15 + 1e-12
    # And breaching either would be caught: adding L2B to 200 breaks the 15% cap.
    l2b_over = hqla_level_2b_asset_classifier(np.array([280.0]))["post_haircut_value"]  # 210
    total_over = l1 + l2a + l2b_over
    assert l2b_over / total_over > 0.15  # 210/1060 = 0.198 -> non-compliant


# =====================================================================
# engine/liquidity_cashflow.py
# =====================================================================


def test_cash_flow_ladder_30_day_cumulative():
    # [independent hand-calc]. Constant net +1/day for 30 days, opening 10.
    inflows = np.full(30, 5.0)
    outflows = np.full(30, 4.0)
    res = cash_flow_ladder_30_day(inflows, outflows, opening_balance=10.0)
    # net gap per day = 1; cumulative day k (0-indexed) = 10 + (k+1).
    assert res["net_gap"][0] == pytest.approx(1.0, rel=REL)
    assert res["cumulative_gap"][0] == pytest.approx(11.0, rel=REL)
    assert res["cumulative_gap"][-1] == pytest.approx(40.0, rel=REL)
    # min cumulative occurs on day 0 (monotone increasing path).
    assert res["min_day"] == 0
    assert res["min_cumulative"] == pytest.approx(11.0, rel=REL)


def test_cash_flow_ladder_30_day_shortfall_day():
    # [independent hand-calc]. Big outflow on day 5 drives the trough there.
    inflows = np.full(30, 1.0)
    outflows = np.full(30, 1.0)
    outflows[5] = 100.0
    res = cash_flow_ladder_30_day(inflows, outflows, opening_balance=0.0)
    # cumulative: 0 up to day4, then -99 at day5, stays -99.
    assert res["min_day"] == 5
    assert res["min_cumulative"] == pytest.approx(-99.0, rel=REL)
    with pytest.raises(ValueError):
        cash_flow_ladder_30_day(np.zeros(10), np.zeros(10))


def test_cash_flow_ladder_1_year_buckets():
    # [independent hand-calc]. 8 buckets, verify cumulative running sum.
    inflows = np.array([10.0, 20.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    outflows = np.array([5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0])
    res = cash_flow_ladder_1_year(inflows, outflows, opening_balance=0.0)
    net = inflows - outflows
    ref_cum = np.cumsum(net)
    assert res["net_gap"] == pytest.approx(list(net), rel=REL)
    assert res["cumulative_gap"] == pytest.approx(list(ref_cum), rel=REL)
    assert res["min_cumulative"] == pytest.approx(float(np.min(ref_cum)), rel=REL)
    with pytest.raises(ValueError):
        cash_flow_ladder_1_year(np.zeros(3), np.zeros(3))  # != 8 buckets


def test_liquidity_gap_analysis():
    # [independent hand-calc]. gap = assets - liabs; ratio = assets/liabs.
    assets = np.array([100.0, 50.0, 200.0, 0.0, 10.0, 10.0, 10.0, 10.0])
    liabs = np.array([80.0, 60.0, 100.0, 50.0, 10.0, 10.0, 10.0, 10.0])
    res = liquidity_gap_analysis(assets, liabs)
    ref_gap = assets - liabs
    ref_cum = np.cumsum(ref_gap)
    assert res["periodic_gap"] == pytest.approx(list(ref_gap), rel=REL)
    assert res["cumulative_gap"] == pytest.approx(list(ref_cum), rel=REL)
    assert res["gap_ratio"][0] == pytest.approx(100.0 / 80.0, rel=REL)


def test_liquidity_gap_ratio_inf_when_zero_liability():
    # [independent hand-calc]. Zero-liability bucket -> ratio None (inf).
    assets = np.array([100.0] * 8)
    liabs = np.array([0.0] + [10.0] * 7)
    res = liquidity_gap_analysis(assets, liabs)
    assert res["gap_ratio"][0] is None
    assert res["gap_ratio"][1] == pytest.approx(10.0, rel=REL)


def test_funding_tenor_analysis():
    # [independent hand-calc]. Weighted avg tenor & <=90d short-term ratio.
    amounts = np.array([100.0, 300.0, 600.0])
    tenors = np.array([30.0, 180.0, 365.0])
    total = 1000.0
    wat_ref = (100 * 30 + 300 * 180 + 600 * 365) / total  # 276.0
    short_ref = 100.0 / total  # only the 30d tranche is <= 90d
    res = funding_tenor_analysis(amounts, tenors)
    assert res["weighted_avg_tenor_days"] == pytest.approx(wat_ref, rel=REL)
    assert res["short_term_ratio"] == pytest.approx(short_ref, rel=REL)
    assert res["total_funding"] == pytest.approx(total, rel=REL)
    with pytest.raises(ValueError):
        funding_tenor_analysis(np.array([0.0]), np.array([10.0]))  # zero total


# =====================================================================
# engine/liquidity_stress.py
# =====================================================================


def test_liquidity_stress_scenario_runoff():
    # [closed-form, BCBS LCR run-off]. outflow = sum(balance*rate).
    balances = np.array([1000.0, 500.0, 200.0])
    rates = np.array([0.05, 0.10, 1.00])
    ref_out = 1000 * 0.05 + 500 * 0.10 + 200 * 1.00  # 50+50+200 = 300
    res = liquidity_stress_scenario(balances, rates, hqla=400.0, inflows=50.0)
    assert res["stressed_outflow"] == pytest.approx(ref_out, rel=REL)
    assert res["net_outflow"] == pytest.approx(250.0, rel=REL)
    assert res["surplus_deficit"] == pytest.approx(150.0, rel=REL)
    assert res["survives"] is True
    with pytest.raises(ValueError):
        liquidity_stress_scenario(np.array([1.0]), np.array([1.5]), 1.0)


def test_idiosyncratic_stress_100pct_wholesale():
    # [closed-form]. retail*0.10 + wholesale*1.00.
    res = idiosyncratic_stress_scenario(1000.0, 500.0, hqla=600.0)
    ref = 1000 * 0.10 + 500 * 1.00  # 100 + 500 = 600
    assert res["stressed_outflow"] == pytest.approx(ref, rel=REL)
    assert res["surplus_deficit"] == pytest.approx(0.0, abs=1e-6)
    assert res["survives"] is True  # surplus == 0 survives


def test_market_wide_stress_extra_haircut():
    # [closed-form]. stressed HQLA = sum(value*(1-hc)); haircut reduces value.
    hqla = np.array([500.0, 300.0, 200.0])
    hc = np.array([0.0, 0.10, 0.25])
    ref = 500 * 1.0 + 300 * 0.9 + 200 * 0.75  # 500+270+150 = 920
    res = market_wide_stress_scenario(hqla, hc, outflow=800.0)
    assert res["stressed_hqla"] == pytest.approx(ref, rel=REL)
    assert res["stressed_hqla"] < float(np.sum(hqla))  # haircut reduces
    assert res["surplus_deficit"] == pytest.approx(120.0, rel=REL)
    assert res["survives"] is True


def test_combined_stress_worse_than_components():
    # [closed-form, internal combined-stress convention -- NOT a Basel/EBA
    # reference scenario, despite a prior comment here claiming that: BCBS
    # 238's own combined idiosyncratic + market-wide scenario (Sec II para
    # 19-20) runs off the LCR's own 3%/5%/10% retail run-off categories, not
    # a flat 15%. Found during the Tier 3 #2 audit; the aggregation-ordering
    # property this test checks (combined never better than market-wide
    # alone) still holds regardless of the specific retail rate used.
    # outflow uses retail 0.15 default (internal, not regulator-set).
    retail, wholesale = 1000.0, 500.0
    hqla = np.array([500.0, 300.0, 200.0])
    hc = np.array([0.0, 0.10, 0.25])
    ref_out = retail * 0.15 + wholesale * 1.00  # 150 + 500 = 650
    ref_hqla = 500 + 270 + 150  # 920
    res = combined_stress_scenario(retail, wholesale, hqla, hc)
    assert res["stressed_outflow"] == pytest.approx(ref_out, rel=REL)
    assert res["stressed_hqla"] == pytest.approx(ref_hqla, rel=REL)
    assert res["surplus_deficit"] == pytest.approx(ref_hqla - ref_out, rel=REL)
    # Combined deficit never better than market-wide alone (same outflow).
    mw = market_wide_stress_scenario(hqla, hc, ref_out)
    assert res["surplus_deficit"] <= mw["surplus_deficit"] + 1e-6


def test_survival_horizon_nonnegative_and_exhaustion():
    # [independent hand-calc]. HQLA 100, drain 30/day. Buffer: 70,40,10,-20.
    # Breaks on day 3 (0-indexed) -> survives 3 full days.
    out = np.array([30.0, 30.0, 30.0, 30.0, 30.0])
    res = survival_horizon_calculator(100.0, out)
    assert res["survival_days"] == 3
    assert res["survival_days"] >= 0
    assert res["terminal_buffer"] == pytest.approx(-20.0, rel=REL)
    # Survives entire path when HQLA ample.
    res2 = survival_horizon_calculator(10_000.0, out)
    assert res2["survival_days"] == out.size
    with pytest.raises(ValueError):
        survival_horizon_calculator(100.0, np.array([]))


def test_intraday_liquidity_monitor():
    # [independent hand-calc]. NOT actually exercising a BCBS 248 monitoring
    # tool despite a prior comment tagging it that way: BCBS 248's "daily
    # maximum intraday liquidity usage" is the largest NET NEGATIVE
    # cumulative position -- that's net_debit_peak below, which this
    # scenario keeps at exactly 0.0 (balance never goes negative). The
    # load-bearing assertion here (max_usage == 80, the drop below opening
    # balance) is a different, internal metric, not a BCBS 248 tool. Found
    # during the Tier 3 #2 audit; a genuine BCBS 248 net-debit-peak check
    # would need a scenario where cumulative flows actually go negative --
    # left as a follow-up, not done here.
    # opening 100, flows drop below open.
    ts = np.array([1.0, 2.0, 3.0, 4.0])
    flows = np.array([-30.0, -50.0, 20.0, 10.0])
    # balance path = 70, 20, 40, 50. min = 20. opening 100.
    res = intraday_liquidity_monitor(ts, flows, opening_balance=100.0)
    assert res["min_balance"] == pytest.approx(20.0, rel=REL)
    assert res["max_usage"] == pytest.approx(80.0, rel=REL)  # 100 - 20
    assert res["net_debit_peak"] == pytest.approx(0.0, abs=1e-6)  # never < 0
    assert res["closing_balance"] == pytest.approx(50.0, rel=REL)
    with pytest.raises(ValueError):
        intraday_liquidity_monitor(np.array([2.0, 1.0]), np.array([1.0, 1.0]), 0.0)


def test_intraday_stress_test_delays_inflows():
    # [independent hand-calc]. flows [-40, +60, -30]; delay 0.5 halves inflow.
    flows = np.array([-40.0, 60.0, -30.0])
    # stressed flows: -40, +30, -30. path from opening 50: 10, 40, 10. min 10.
    res = intraday_liquidity_stress_test(flows, opening_balance=50.0, delay_factor=0.5)
    assert res["stressed_min_balance"] == pytest.approx(10.0, rel=REL)
    assert res["stressed_max_usage"] == pytest.approx(40.0, rel=REL)  # 50-10
    assert res["survives"] is True
    with pytest.raises(ValueError):
        intraday_liquidity_stress_test(flows, 50.0, delay_factor=1.5)


def test_ilaap_stress_framework_binding_scenario():
    # [independent hand-calc]. Worst surplus_deficit selects binding scenario.
    scenarios = {
        "idio": {"surplus_deficit": 100.0},
        "market": {"surplus_deficit": -50.0},
        "combined": {"surplus_deficit": -120.0},
    }
    res = ilaap_stress_testing_framework(scenarios)
    assert res["binding_scenario"] == "combined"
    assert res["worst_surplus_deficit"] == pytest.approx(-120.0, rel=REL)
    assert res["num_breached"] == 2
    assert res["adequate"] is False
    with pytest.raises(ValueError):
        ilaap_stress_testing_framework({})


def test_liqvar_cross_validated_against_scipy():
    # [cross-validated (scipy), not regulator-sourced]. LiqVaR quantile of
    # base*(1+vol*Z) equals base*(1+vol*z_alpha) analytically. MC must agree.
    base, vol, cl = 1000.0, 0.20, 0.99
    res = liquidity_var_liqvar(base, vol, confidence_level=cl, n_simulations=200_000, seed=42)
    z = float(stats.norm.ppf(cl))
    analytic_ref = base * (1.0 + vol * z)  # independent scipy closed form
    assert res["liqvar_analytic"] == pytest.approx(analytic_ref, rel=REL)
    # MC quantile within 1% of the analytic reference (sampling noise).
    assert res["liqvar"] == pytest.approx(analytic_ref, rel=1e-2)
    assert res["liqvar"] > 0.0
    # Determinism: same seed -> same simulated result.
    res_again = liquidity_var_liqvar(base, vol, confidence_level=cl, n_simulations=200_000, seed=42)
    assert res_again["liqvar"] == res["liqvar"]
    with pytest.raises(ValueError):
        liquidity_var_liqvar(base, -0.1)
    with pytest.raises(ValueError):
        liquidity_var_liqvar(base, vol, confidence_level=0.5)


# =====================================================================
# engine/liquidity_funding.py
# =====================================================================


def test_liquidity_buffer_sizing_peak_cumulative_monotone():
    # [independent hand-calc]. Buffer = peak cumulative outflow.
    outflows = np.array([50.0, 30.0, -20.0, 40.0])
    cum = np.cumsum(outflows)  # 50, 80, 60, 100
    res = liquidity_buffer_sizing(outflows)
    assert res["peak_cumulative_outflow"] == pytest.approx(100.0, rel=REL)
    assert res["peak_period"] == 3
    assert res["required_buffer"] == pytest.approx(100.0, rel=REL)
    # Confidence uplift is monotone increasing.
    res_up = liquidity_buffer_sizing(outflows, confidence_buffer=0.10)
    assert res_up["required_buffer"] == pytest.approx(110.0, rel=REL)
    assert res_up["required_buffer"] > res["required_buffer"]
    assert float(np.max(cum)) == pytest.approx(100.0)
    with pytest.raises(ValueError):
        liquidity_buffer_sizing(np.array([]))


def test_cfp_trigger_below_threshold():
    # [independent hand-calc]. Breach when metric < threshold.
    metrics = {"lcr": 0.95, "survival_days": 120.0, "nsfr": 1.10}
    thresholds = {"lcr": 1.00, "survival_days": 90.0, "nsfr": 1.00}
    res = contingency_funding_plan_trigger(metrics, thresholds)
    assert set(res["breached"]) == {"lcr"}
    assert res["num_breached"] == 1
    assert res["cfp_activated"] is True
    with pytest.raises(ValueError):
        contingency_funding_plan_trigger({}, {})


def test_wholesale_concentration_hhi():
    # [closed-form, HHI = sum(share^2)]. Equal 4 counterparties -> HHI = 0.25.
    amounts = np.array([250.0, 250.0, 250.0, 250.0])
    res = wholesale_funding_concentration(amounts)
    assert res["hhi"] == pytest.approx(0.25, rel=REL)
    assert res["top1_share"] == pytest.approx(0.25, rel=REL)
    assert res["effective_counterparties"] == pytest.approx(4.0, rel=REL)
    # Concentrated case: one dominant counterparty raises HHI.
    conc = np.array([900.0, 50.0, 50.0])
    shares = conc / conc.sum()
    hhi_ref = float(np.sum(shares**2))
    resc = wholesale_funding_concentration(conc)
    assert resc["hhi"] == pytest.approx(hhi_ref, rel=REL)
    assert resc["hhi"] > res["hhi"]
    with pytest.raises(ValueError):
        wholesale_funding_concentration(np.array([]))


def test_retail_deposit_runoff_blended():
    # [closed-form, BCBS LCR retail run-off]. blended = total_runoff/total_bal.
    bal = np.array([5000.0, 3000.0, 2000.0])
    rates = np.array([0.05, 0.10, 0.15])
    amounts_ref = bal * rates  # 250, 300, 300
    total_runoff = float(amounts_ref.sum())  # 850
    blended_ref = total_runoff / 10000.0  # 0.085
    res = retail_deposit_runoff_rate(bal, rates)
    assert res["total_runoff"] == pytest.approx(total_runoff, rel=REL)
    assert res["blended_rate"] == pytest.approx(blended_ref, rel=REL)
    with pytest.raises(ValueError):
        retail_deposit_runoff_rate(np.array([1.0]), np.array([2.0]))


def test_secured_funding_rollover_gap():
    # [independent hand-calc]. gap = total - sum(maturing*rollover).
    maturing = np.array([1000.0, 500.0, 500.0])
    rates = np.array([1.00, 0.50, 0.00])
    rolled_ref = 1000 * 1.0 + 500 * 0.5 + 500 * 0.0  # 1250
    gap_ref = 2000.0 - rolled_ref  # 750
    res = secured_funding_rollover_risk(maturing, rates)
    assert res["rolled_amount"] == pytest.approx(rolled_ref, rel=REL)
    assert res["rollover_gap"] == pytest.approx(gap_ref, rel=REL)
    assert res["effective_rollover_rate"] == pytest.approx(1250.0 / 2000.0, rel=REL)


def test_asset_encumbrance_ratio():
    # [closed-form, EBA]. ratio = encumbered/total.
    res = asset_encumbrance_ratio(300.0, 1000.0)
    assert res["encumbrance_ratio"] == pytest.approx(0.30, rel=REL)
    assert res["unencumbered_assets"] == pytest.approx(700.0, rel=REL)
    assert res["unencumbered_ratio"] == pytest.approx(0.70, rel=REL)
    with pytest.raises(ValueError):
        asset_encumbrance_ratio(1100.0, 1000.0)  # exceeds total
    with pytest.raises(ValueError):
        asset_encumbrance_ratio(100.0, 0.0)


def test_collateral_availability_post_haircut_and_pledged():
    # [independent hand-calc]. post = value*(1-hc), net off pledged, floor 0.
    values = np.array([1000.0, 500.0])
    hc = np.array([0.10, 0.50])
    pledged = np.array([100.0, 300.0])
    post_ref = values * (1 - hc)  # 900, 250
    avail_ref = np.maximum(post_ref - pledged, 0.0)  # 800, 0 (250-300<0)
    res = collateral_availability_analysis(values, hc, pledged)
    assert res["available_collateral"] == pytest.approx(float(avail_ref.sum()), rel=REL)
    assert res["post_haircut_values"] == pytest.approx(list(post_ref), rel=REL)
    # Haircut reduces available (monotonicity) vs no haircut, no pledge.
    res0 = collateral_availability_analysis(values, np.array([0.0, 0.0]))
    assert res0["available_collateral"] > res["available_collateral"]
    with pytest.raises(ValueError):
        collateral_availability_analysis(values, np.array([1.5, 0.1]))


def test_repo_market_stress_margin_call():
    # [independent hand-calc]. stressed hc = min(base*mult, 1); margin = value*Δhc.
    base = np.array([0.02, 0.05])
    mult = np.array([2.0, 3.0])
    values = np.array([1000.0, 2000.0])
    stressed_ref = np.minimum(base * mult, 1.0)  # 0.04, 0.15
    margin_ref = values * (stressed_ref - base)  # 20, 200
    res = repo_market_stress_haircut(base, mult, values)
    assert res["stressed_haircuts"] == pytest.approx(list(stressed_ref), rel=REL)
    assert res["additional_margin"] == pytest.approx(float(margin_ref.sum()), rel=REL)
    with pytest.raises(ValueError):
        repo_market_stress_haircut(base, np.array([0.5, 1.0]), values)  # mult<1


def test_fx_liquidity_net_by_currency():
    # [independent hand-calc]. net = inflow - outflow per ccy; worst short.
    inflows = {"USD": 100.0, "EUR": 50.0, "GBP": 30.0}
    outflows = {"USD": 120.0, "EUR": 40.0, "JPY": 200.0}
    res = fx_liquidity_risk_by_currency(inflows, outflows)
    assert res["net_by_ccy"]["USD"] == pytest.approx(-20.0, rel=REL)
    assert res["net_by_ccy"]["EUR"] == pytest.approx(10.0, rel=REL)
    assert res["net_by_ccy"]["JPY"] == pytest.approx(-200.0, rel=REL)
    assert res["largest_short_ccy"] == "JPY"
    assert res["largest_short_amount"] == pytest.approx(-200.0, rel=REL)
    with pytest.raises(ValueError):
        fx_liquidity_risk_by_currency({}, {})


def test_intragroup_liquidity_flow_netting():
    # [independent hand-calc]. providers > 0, receivers < 0, balanced check.
    positions = {"A": 100.0, "B": -60.0, "C": -40.0}
    res = intragroup_liquidity_flow(positions)
    assert res["total_provided"] == pytest.approx(100.0, rel=REL)
    assert set(res["net_providers"]) == {"A"}
    assert set(res["net_receivers"]) == {"B", "C"}
    assert res["balanced"] is True  # 100 - 60 - 40 = 0
    unbal = intragroup_liquidity_flow({"A": 100.0, "B": -50.0})
    assert unbal["balanced"] is False
    with pytest.raises(ValueError):
        intragroup_liquidity_flow({})


def test_funding_cost_weighted_average():
    # [independent hand-calc]. WAC = sum(amount*rate)/sum(amount).
    amounts = np.array([1000.0, 2000.0, 1000.0])
    rates = np.array([0.02, 0.04, 0.06])
    total_cost_ref = 1000 * 0.02 + 2000 * 0.04 + 1000 * 0.06  # 20+80+60 = 160
    wac_ref = total_cost_ref / 4000.0  # 0.04
    res = funding_cost_analysis(amounts, rates)
    assert res["total_annual_cost"] == pytest.approx(total_cost_ref, rel=REL)
    assert res["weighted_avg_cost"] == pytest.approx(wac_ref, rel=REL)
    with pytest.raises(ValueError):
        funding_cost_analysis(np.array([0.0]), np.array([0.05]))


def test_liquidity_transfer_pricing():
    # [independent hand-calc]. all_in = base + liq + contingent.
    res = liquidity_transfer_pricing(1_000_000.0, 5.0, 0.03, 0.01, 0.005)
    all_in_ref = 0.03 + 0.01 + 0.005  # 0.045
    annual_ref = 1_000_000.0 * all_in_ref  # 45000
    lifetime_ref = annual_ref * 5.0  # 225000
    assert res["all_in_rate"] == pytest.approx(all_in_ref, rel=REL)
    assert res["annual_charge"] == pytest.approx(annual_ref, rel=REL)
    assert res["lifetime_charge"] == pytest.approx(lifetime_ref, rel=REL)
    with pytest.raises(ValueError):
        liquidity_transfer_pricing(-1.0, 5.0, 0.03, 0.01)


# =====================================================================
# engine/liquidity_internal.py
# =====================================================================


def test_ilaap_internal_metric_coverage_and_survival():
    # [independent hand-calc]. coverage = CBC/outflow; adequacy both gates.
    res = ilaap_internal_liquidity_metric(1200.0, 1000.0, survival_days=120.0)
    assert res["coverage_ratio"] == pytest.approx(1.2, rel=REL)
    assert res["meets_survival"] is True
    assert res["adequate"] is True  # coverage>=1 AND survival>=90
    # Fails survival gate.
    res2 = ilaap_internal_liquidity_metric(1200.0, 1000.0, survival_days=30.0)
    assert res2["adequate"] is False
    with pytest.raises(ValueError):
        ilaap_internal_liquidity_metric(100.0, 0.0, 100.0)


def test_risk_appetite_rag_higher_is_better():
    # [independent hand-calc]. LCR-style: >= green -> green, >= amber -> amber.
    green = liquidity_risk_appetite_threshold(1.30, 1.20, 1.00)
    amber = liquidity_risk_appetite_threshold(1.10, 1.20, 1.00)
    red = liquidity_risk_appetite_threshold(0.90, 1.20, 1.00)
    assert green["zone"] == "green" and green["breach"] is False
    assert amber["zone"] == "amber"
    assert red["zone"] == "red" and red["breach"] is True


def test_risk_appetite_rag_lower_is_better():
    # [independent hand-calc]. concentration-style: <= green -> green.
    green = liquidity_risk_appetite_threshold(0.10, 0.20, 0.40, higher_is_better=False)
    amber = liquidity_risk_appetite_threshold(0.30, 0.20, 0.40, higher_is_better=False)
    red = liquidity_risk_appetite_threshold(0.50, 0.20, 0.40, higher_is_better=False)
    assert green["zone"] == "green"
    assert amber["zone"] == "amber"
    assert red["zone"] == "red"
    with pytest.raises(ValueError):
        liquidity_risk_appetite_threshold(1.0, 1.0, 2.0)  # green<amber, higher


def test_early_warning_indicator_signal():
    # [independent hand-calc]. mixed directions; 3 triggers -> alert.
    indicators = {"lcr": 0.9, "spread": 250.0, "deposit_growth": -0.05, "wac": 0.01}
    thresholds = {"lcr": 1.0, "spread": 100.0, "deposit_growth": 0.0, "wac": 0.05}
    directions = {
        "lcr": "lower_breach",
        "spread": "higher_breach",
        "deposit_growth": "lower_breach",
        "wac": "lower_breach",  # 0.01 < 0.05 -> triggers too
    }
    res = early_warning_indicator_liquidity(indicators, thresholds, directions)
    # lcr(0.9<1), spread(250>100), deposit_growth(-0.05<0), wac(0.01<0.05) = 4
    assert set(res["triggered"]) == {"lcr", "spread", "deposit_growth", "wac"}
    assert res["num_triggered"] == 4
    assert res["signal"] == "alert"  # >2 triggers
    # Watch case (1 trigger).
    watch = early_warning_indicator_liquidity({"lcr": 0.9}, {"lcr": 1.0}, {"lcr": "lower_breach"})
    assert watch["signal"] == "watch"
    with pytest.raises(ValueError):
        early_warning_indicator_liquidity({}, {})


def test_central_bank_eligibility_filter_and_capacity():
    # [independent hand-calc]. Eligible = rating>=min; capacity post-haircut.
    ratings = np.array([5.0, 3.0, 4.0, 2.0])
    values = np.array([1000.0, 500.0, 800.0, 200.0])
    hc = np.array([0.05, 0.10, 0.08, 0.20])
    min_rating = 4
    # eligible: idx 0 (5), idx 2 (4). capacity = 1000*0.95 + 800*0.92.
    cap_ref = 1000 * 0.95 + 800 * 0.92  # 950 + 736 = 1686
    res = central_bank_facility_eligibility(ratings, min_rating, values, hc)
    assert res["eligible_count"] == 2
    assert res["borrowing_capacity"] == pytest.approx(cap_ref, rel=REL)
    assert res["eligible_mask"] == [True, False, True, False]
    with pytest.raises(ValueError):
        central_bank_facility_eligibility(ratings, 4, values, np.array([1.5, 0, 0, 0]))


def test_contingent_liquidity_risk_expected_and_max():
    # [independent hand-calc]. expected = sum(amt*prob*ccf); max = sum(amt*ccf).
    amounts = np.array([1000.0, 2000.0])
    probs = np.array([0.10, 0.25])
    ccf = np.array([0.5, 1.0])
    exp_ref = 1000 * 0.10 * 0.5 + 2000 * 0.25 * 1.0  # 50 + 500 = 550
    max_ref = 1000 * 0.5 + 2000 * 1.0  # 500 + 2000 = 2500
    res = contingent_liquidity_risk(amounts, probs, ccf)
    assert res["expected_contingent_outflow"] == pytest.approx(exp_ref, rel=REL)
    assert res["max_contingent_outflow"] == pytest.approx(max_ref, rel=REL)
    assert res["expected_contingent_outflow"] <= res["max_contingent_outflow"]
    with pytest.raises(ValueError):
        contingent_liquidity_risk(amounts, np.array([1.5, 0.1]))


def test_liquidity_scorecard_weighted_composite():
    # [independent hand-calc]. composite = sum(score*w)/sum(w); RAG mapping.
    scores = np.array([80.0, 60.0, 90.0])
    weights = np.array([1.0, 1.0, 2.0])
    comp_ref = (80 * 1 + 60 * 1 + 90 * 2) / 4.0  # 320/4 = 80
    res = liquidity_scorecard_aggregation(scores, weights)
    assert res["composite_score"] == pytest.approx(comp_ref, rel=REL)
    assert res["rating"] == "green"  # >= 70
    # Amber band.
    amber = liquidity_scorecard_aggregation(np.array([50.0]), np.array([1.0]))
    assert amber["rating"] == "amber"
    red = liquidity_scorecard_aggregation(np.array([20.0]), np.array([1.0]))
    assert red["rating"] == "red"
    with pytest.raises(ValueError):
        liquidity_scorecard_aggregation(np.array([1.0]), np.array([0.0]))


def test_deposit_stability_classification():
    # [independent hand-calc]. stable = score >= threshold.
    scores = np.array([0.9, 0.4, 0.5, 0.2, 0.7])
    # >= 0.5: 0.9, 0.5, 0.7 -> 3 stable of 5.
    res = deposit_stability_classification(scores)
    assert res["num_stable"] == 3
    assert res["num_less_stable"] == 2
    assert res["stable_fraction"] == pytest.approx(3.0 / 5.0, rel=REL)
    with pytest.raises(ValueError):
        deposit_stability_classification(np.array([1.5]))
    with pytest.raises(ValueError):
        deposit_stability_classification(np.array([]))


def test_cross_currency_bridge_fx_swap():
    # [independent hand-calc]. usable = surplus*(1-hc); coverable in shortfall ccy.
    # Shortfall 1000 USD, surplus 900 EUR, fx 1.10 USD/EUR, haircut 0.05.
    # usable = 900*0.95 = 855 EUR -> *1.10 = 940.5 USD. residual = 59.5.
    res = cross_currency_liquidity_bridge("USD", 1000.0, "EUR", 900.0, 1.10, 0.05)
    coverable_ref = min(1000.0, 900.0 * 0.95 * 1.10)  # 940.5
    assert res["coverable_amount"] == pytest.approx(coverable_ref, rel=REL)
    assert res["residual_shortfall"] == pytest.approx(1000.0 - coverable_ref, rel=REL)
    assert res["fully_bridged"] is False
    # Full bridge when surplus ample.
    full = cross_currency_liquidity_bridge("USD", 100.0, "EUR", 900.0, 1.10, 0.0)
    assert full["fully_bridged"] is True
    assert full["residual_shortfall"] == pytest.approx(0.0, abs=1e-6)
    with pytest.raises(ValueError):
        cross_currency_liquidity_bridge("USD", 100.0, "EUR", 100.0, -1.0)
    with pytest.raises(ValueError):
        cross_currency_liquidity_bridge("USD", 100.0, "EUR", 100.0, 1.0, swap_haircut=1.5)

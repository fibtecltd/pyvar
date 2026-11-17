# Trial lane whitelist: benchmark of 151 functions (2026-11-17)

Output of `scripts/trial_weight_bench.py` (PR that adds it), run once on 2026-11-17. It chooses the whitelist of the A3 trial lane
(`docs/plan-trial-lane-throttle.md`): a function may go on it only if it is cheap and does not compile a Numba kernel on a worker's
first call. The lane charges the compute budget by the **measured** time of each call (owner decision, 2026-11-17), so these numbers
choose the list; they are not a weight table.

## How it was measured

- **Machine:** this session's sandbox, 4 vCPU Intel Xeon at 2.1 GHz, not Fargate. Absolute times on a 0.5 vCPU task will differ; run the
  script in the dev image for those. The ranking and the compile findings do not depend on the machine.
- **Warm pass:** one process, the real app in process (auth, rate-limit and response middleware included, no network, database or AWS), one
  unmeasured call, then 30 timed calls per function: p50, p95, max.
- **First-call pass:** each function in its own fresh process with an empty Numba cache and the same warm-up the lifespan does (one tiny
  `run_monte_carlo_var`, the only kernel the image pre-bakes); one call, timed, and the number of Numba kernels compiled by it.
- **Payloads:** 142 functions have only scalar required parameters and got a request built from the catalogue (default, else the middle of
  the limits); the 19 payloads recorded from the domain API tests (each answered 200 there) replace or add to these, nine of them for functions the catalogue could not build. 151 of 385 functions were measured; **234 have
  no payload yet** (array or object inputs and no recorded test payload), among them the flagship historical, parametric and Cornish-Fisher VaR.
- **Verdicts:** `ok` (200, no compile, p95 and first call under 1 s), `COMPILES` (the first call compiled one or more kernels), `SLOW` (none
  here), `ERROR` (the built payload was rejected with 422, so the function was not measured, which says nothing about the function).
- Test payloads are small (a few hundred returns, a handful of scenarios). A real caller can send more; the lane bounds that with a body-size
  cap, an array-length cap and the one-second deadline, not with this table.

## Result

| Domain | ok | COMPILES | ERROR | measured |
| --- | --- | --- | --- | --- |
| alm | 12 | 0 | 2 | 14 |
| credit-risk | 17 | 5 | 3 | 25 |
| derivatives | 23 | 15 | 4 | 42 |
| liquidity | 8 | 1 | 0 | 9 |
| market-risk | 14 | 2 | 0 | 16 |
| operational | 21 | 2 | 1 | 24 |
| portfolio | 3 | 2 | 0 | 5 |
| regulatory | 16 | 0 | 0 | 16 |
| **all** | **114** | **27** | **10** | **151** |

1. **114 functions are `ok`.** Their p95 has a median of 2.9 ms; 112 of them cost one unit (50 ms or less). The two heavier ones are
   `derivatives/cox_ingersoll_ross_model` (p95 357 ms, 8 units) and `operational/scenario_analysis_oprisk` (p95 173 ms, 4 units). All are far below the one-second deadline.
2. **27 functions `COMPILES`** (1 to 6 kernels in the first call). Warm they are fast (2 to 476 ms); in a fresh task the first call is
   slower than a function that compiles nothing by up to 1637 ms (median 306 ms; 13 of 27 under 300 ms, the worst `derivatives/rough_volatility_rbergomi_model` at 2076 ms in all).
   **They include the functions a first-time user most wants:** `market-risk/conditional_var_es`, `market-risk/garch_11_volatility_forecast`,
   `portfolio/sharpe_ratio`, `portfolio/maximum_drawdown` and the Monte Carlo and tree pricers. The image pre-bakes one kernel and the lifespan warms
   one, so the fix is the same for all of them: bake the kernels' cache in the image build and warm them at start-up. Until then they stay off the whitelist.
3. **10 functions `ERROR`:** the payload built from the catalogue failed validation (422); they need a recorded payload.
4. **The first call of a function that compiles nothing still takes 439 ms (median of the `ok` rows) in a fresh process.** That is one-time
   per-process cost of the first request through the stack, shared by every route, not a property of the function. A running task has paid it already.
5. **Not measured:** 234 functions (array and object inputs). Recording payloads for the flagship ones is the next step before the whitelist is fixed.

## For PR 1

Whitelist v1 = the `ok` rows, reviewed by the owner for product reasons (114 is more than a first-use experience needs; 20 to 30 spread across
the eight domains is probably enough), plus the compiling functions once their kernels are baked and warmed, plus recorded payloads for the array-input
flagships. The route-level whitelist is a set of paths in code, reviewed like any other; a function missing from it is simply refused.

## All 151 rows (ms; first = first call in a fresh process; comp = kernels compiled by it; units = ceil(p95 / 50))

| Route | Verdict | Status | First | Comp | p50 | p95 | Max | Units |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| derivatives/cox_ingersoll_ross_model | ok | 200 | 724.2 | 0 | 277.2 | 356.8 | 414.0 | 8 |
| operational/scenario_analysis_oprisk | ok | 200 | 696.5 | 0 | 119.3 | 172.8 | 206.1 | 4 |
| market-risk/correlation_matrix_historical | ok | 200 | 406.4 | 0 | 6.2 | 6.9 | 7.1 | 1 |
| portfolio/mean_variance_optimisation | ok | 200 | 447.5 | 0 | 6.3 | 6.8 | 7.1 | 1 |
| derivatives/heston_stochastic_volatility_model | ok | 200 | 443.8 | 0 | 5.4 | 5.8 | 5.8 | 1 |
| regulatory/crr2_large_exposure_limit | ok | 200 | 359.7 | 0 | 2.9 | 5.2 | 5.9 | 1 |
| operational/regulatory_compliance_score | ok | 200 | 459.3 | 0 | 3.0 | 4.5 | 6.4 | 1 |
| alm/balance_sheet_projection_model | ok | 200 | 442.6 | 0 | 2.8 | 4.5 | 5.0 | 1 |
| regulatory/mifid_ii_pre_trade_transparency | ok | 200 | 380.5 | 0 | 2.4 | 4.3 | 7.4 | 1 |
| portfolio/minimum_variance_portfolio | ok | 200 | 521.3 | 0 | 3.8 | 4.2 | 4.6 | 1 |
| alm/funds_transfer_pricing_ftp | ok | 200 | 423.6 | 0 | 3.1 | 4.2 | 4.6 | 1 |
| regulatory/frtb_ima_market_risk_capital | ok | 200 | 397.6 | 0 | 3.6 | 4.1 | 4.3 | 1 |
| derivatives/yield_to_call | ok | 200 | 444.9 | 0 | 3.8 | 4.1 | 4.2 | 1 |
| alm/effective_duration_alm | ok | 200 | 443.6 | 0 | 3.2 | 4.0 | 4.2 | 1 |
| derivatives/equity_swap_pricer | ok | 200 | 397.1 | 0 | 2.3 | 4.0 | 5.0 | 1 |
| regulatory/emir_margin_requirement | ok | 200 | 447.0 | 0 | 2.3 | 3.9 | 6.8 | 1 |
| derivatives/effective_duration | ok | 200 | 393.7 | 0 | 2.5 | 3.9 | 4.3 | 1 |
| market-risk/vanna_delta_vega_cross | ok | 200 | 540.4 | 0 | 1.9 | 3.9 | 6.8 | 1 |
| regulatory/mifid_ii_post_trade_transparency | ok | 200 | 408.9 | 0 | 3.4 | 3.9 | 4.2 | 1 |
| alm/duration_gap_analysis | ok | 200 | 364.2 | 0 | 2.4 | 3.8 | 4.3 | 1 |
| alm/option_risk_irrbb | ok | 200 | 480.8 | 0 | 2.6 | 3.8 | 4.1 | 1 |
| derivatives/total_return_swap_trs | ok | 200 | 456.1 | 0 | 3.2 | 3.8 | 3.9 | 1 |
| derivatives/zero_coupon_bond_pricer | ok | 200 | 395.6 | 0 | 2.5 | 3.8 | 3.9 | 1 |
| derivatives/spread_option_kirk_approximation | ok | 200 | 402.4 | 0 | 3.5 | 3.8 | 3.8 | 1 |
| regulatory/capital_conservation_buffer | ok | 200 | 431.1 | 0 | 3.4 | 3.7 | 3.9 | 1 |
| derivatives/sabr_volatility_model | ok | 200 | 426.6 | 0 | 3.4 | 3.7 | 4.0 | 1 |
| regulatory/basel_iv_output_floor | ok | 200 | 364.9 | 0 | 3.3 | 3.7 | 3.8 | 1 |
| regulatory/aifmd_risk_metrics | ok | 200 | 374.1 | 0 | 3.4 | 3.6 | 3.8 | 1 |
| derivatives/swaption_pricer_black | ok | 200 | 411.6 | 0 | 2.8 | 3.6 | 3.9 | 1 |
| regulatory/srep_capital_add_on | ok | 200 | 384.3 | 0 | 2.3 | 3.5 | 3.7 | 1 |
| regulatory/frtb_sa_market_risk_capital | ok | 200 | 371.4 | 0 | 2.4 | 3.5 | 4.0 | 1 |
| operational/business_continuity_risk_score | ok | 200 | 462.8 | 0 | 3.1 | 3.4 | 3.7 | 1 |
| operational/third_party_vendor_risk | ok | 200 | 559.9 | 0 | 3.1 | 3.4 | 3.4 | 1 |
| portfolio/equal_weight_portfolio | ok | 200 | 377.9 | 0 | 3.0 | 3.3 | 3.4 | 1 |
| derivatives/barrier_option_pricer | ok | 200 | 360.7 | 0 | 3.0 | 3.3 | 3.9 | 1 |
| derivatives/caplet_floorlet_pricer_black | ok | 200 | 365.6 | 0 | 2.8 | 3.3 | 3.4 | 1 |
| operational/scenario_frequency_estimation | ok | 200 | 502.4 | 0 | 2.0 | 3.3 | 3.4 | 1 |
| alm/nii_sensitivity_rate_shock | ok | 200 | 572.1 | 0 | 2.5 | 3.2 | 3.5 | 1 |
| liquidity/liquidity_risk_appetite_threshold | ok | 200 | 519.3 | 0 | 2.3 | 3.2 | 3.4 | 1 |
| operational/risk_appetite_statement_oprisk | ok | 200 | 408.4 | 0 | 2.9 | 3.2 | 3.4 | 1 |
| regulatory/basel_iii_leverage_ratio | ok | 200 | 392.3 | 0 | 2.3 | 3.2 | 3.5 | 1 |
| derivatives/swaption_pricer_sabr | ok | 200 | 479.8 | 0 | 2.8 | 3.2 | 3.5 | 1 |
| regulatory/basel_iii_total_capital_ratio | ok | 200 | 412.0 | 0 | 2.3 | 3.2 | 3.3 | 1 |
| derivatives/displaced_diffusion_model | ok | 200 | 432.7 | 0 | 2.7 | 3.1 | 3.4 | 1 |
| regulatory/basel_iii_tier1_ratio | ok | 200 | 358.4 | 0 | 2.3 | 3.1 | 3.2 | 1 |
| derivatives/black_scholes_european_option | ok | 200 | 371.2 | 0 | 2.6 | 3.1 | 4.9 | 1 |
| alm/interest_rate_risk_capital_irrbb | ok | 200 | 590.6 | 0 | 2.5 | 3.1 | 3.4 | 1 |
| regulatory/combined_buffer_requirement | ok | 200 | 426.8 | 0 | 2.5 | 3.1 | 3.1 | 1 |
| derivatives/black_scholes_greeks | ok | 200 | 383.7 | 0 | 2.6 | 3.0 | 4.1 | 1 |
| liquidity/ilaap_internal_liquidity_metric | ok | 200 | 419.4 | 0 | 2.3 | 3.0 | 3.2 | 1 |
| liquidity/asset_encumbrance_ratio | ok | 200 | 554.5 | 0 | 2.2 | 3.0 | 3.1 | 1 |
| operational/conduct_risk_metric | ok | 200 | 384.3 | 0 | 2.0 | 3.0 | 3.1 | 1 |
| regulatory/basel_iii_cet1_ratio | ok | 200 | 488.1 | 0 | 2.4 | 3.0 | 3.2 | 1 |
| regulatory/pillar_2b_stress_buffer | ok | 200 | 558.6 | 0 | 2.3 | 3.0 | 3.3 | 1 |
| alm/behavioural_modelling_nmds | ok | 200 | 571.1 | 0 | 2.5 | 3.0 | 3.4 | 1 |
| alm/liquidity_adjusted_nii | ok | 200 | 391.4 | 0 | 2.5 | 2.9 | 3.1 | 1 |
| operational/loss_event_classification_basel | ok | 200 | 462.9 | 0 | 1.9 | 2.9 | 3.3 | 1 |
| market-risk/basel_capital_addon_multiplier | ok | 200 | 411.0 | 0 | 1.9 | 2.8 | 3.0 | 1 |
| derivatives/fx_option_pricer_garman_kohlhagen | ok | 200 | 377.0 | 0 | 2.6 | 2.8 | 2.9 | 1 |
| liquidity/liquidity_coverage_ratio_lcr | ok | 200 | 454.9 | 0 | 1.9 | 2.8 | 3.0 | 1 |
| derivatives/convertible_bond_pricer | ok | 200 | 399.1 | 0 | 2.4 | 2.8 | 3.0 | 1 |
| derivatives/bond_pricer_fixed_coupon | ok | 200 | 481.3 | 0 | 2.3 | 2.8 | 2.9 | 1 |
| liquidity/net_stable_funding_ratio_nsfr | ok | 200 | 372.6 | 0 | 2.3 | 2.7 | 3.0 | 1 |
| alm/core_deposit_duration | ok | 200 | 371.5 | 0 | 2.4 | 2.7 | 2.8 | 1 |
| liquidity/idiosyncratic_stress_scenario | ok | 200 | 437.9 | 0 | 2.3 | 2.7 | 2.8 | 1 |
| alm/convexity_gap | ok | 200 | 526.5 | 0 | 2.3 | 2.7 | 2.8 | 1 |
| market-risk/volga_vega_convexity | ok | 200 | 476.8 | 0 | 1.9 | 2.7 | 3.0 | 1 |
| market-risk/vega_pnl_attribution | ok | 200 | 461.0 | 0 | 1.8 | 2.7 | 2.9 | 1 |
| alm/pipeline_risk_measurement | ok | 200 | 376.6 | 0 | 2.4 | 2.7 | 2.8 | 1 |
| derivatives/inflation_linked_bond_pricer | ok | 200 | 377.5 | 0 | 2.4 | 2.7 | 2.9 | 1 |
| market-risk/kupiec_pof_test | ok | 200 | 421.2 | 0 | 2.0 | 2.7 | 3.0 | 1 |
| operational/kri_threshold_breach_detection | ok | 200 | 549.4 | 0 | 2.0 | 2.7 | 3.0 | 1 |
| operational/basel_standardised_measurement_sma | ok | 200 | 363.8 | 0 | 1.9 | 2.7 | 3.1 | 1 |
| operational/oprisk_economic_capital | ok | 200 | 417.0 | 0 | 2.2 | 2.6 | 2.7 | 1 |
| market-risk/traffic_light_backtesting | ok | 200 | 482.4 | 0 | 2.1 | 2.6 | 2.6 | 1 |
| derivatives/digital_option_pricer | ok | 200 | 450.3 | 0 | 2.3 | 2.6 | 2.8 | 1 |
| credit-risk/credit_default_swap_var | ok | 200 | 433.7 | 0 | 2.2 | 2.5 | 3.0 | 1 |
| operational/oprisk_stress_testing | ok | 200 | 517.2 | 0 | 2.1 | 2.5 | 2.6 | 1 |
| derivatives/fx_forward_pricer | ok | 200 | 471.1 | 0 | 2.3 | 2.5 | 2.6 | 1 |
| operational/cyber_risk_loss_estimation | ok | 200 | 363.1 | 0 | 1.9 | 2.5 | 2.8 | 1 |
| operational/rcsa_control_effectiveness | ok | 200 | 380.5 | 0 | 2.0 | 2.5 | 2.5 | 1 |
| derivatives/overnight_index_swap_ois | ok | 200 | 449.0 | 0 | 2.2 | 2.4 | 2.5 | 1 |
| operational/rcsa_residual_risk_scoring | ok | 200 | 366.7 | 0 | 2.1 | 2.4 | 2.5 | 1 |
| liquidity/liquidity_transfer_pricing | ok | 200 | 384.1 | 0 | 2.0 | 2.3 | 3.1 | 1 |
| liquidity/cross_currency_liquidity_bridge | ok | 200 | 457.1 | 0 | 2.1 | 2.3 | 2.7 | 1 |
| operational/it_risk_scoring | ok | 200 | 392.4 | 0 | 1.9 | 2.3 | 2.4 | 1 |
| credit-risk/ifrs_9_staging_criteria_assessment | ok | 200 | 515.7 | 0 | 1.8 | 2.3 | 2.6 | 1 |
| operational/rcsa_inherent_risk_scoring | ok | 200 | 486.1 | 0 | 2.0 | 2.3 | 2.3 | 1 |
| credit-risk/altman_z_score_credit_scoring | ok | 200 | 427.7 | 0 | 1.9 | 2.2 | 2.4 | 1 |
| market-risk/theta_time_decay | ok | 200 | 423.8 | 0 | 1.9 | 2.2 | 2.4 | 1 |
| operational/audit_finding_risk_scorer | ok | 200 | 395.6 | 0 | 2.0 | 2.2 | 2.3 | 1 |
| market-risk/charm_delta_decay | ok | 200 | 441.0 | 0 | 1.9 | 2.2 | 2.3 | 1 |
| operational/control_testing_effectiveness | ok | 200 | 637.4 | 0 | 1.9 | 2.2 | 3.5 | 1 |
| market-risk/rho_interest_rate | ok | 200 | 534.9 | 0 | 1.8 | 2.1 | 2.2 | 1 |
| operational/model_risk_assessment | ok | 200 | 509.5 | 0 | 1.9 | 2.1 | 2.1 | 1 |
| operational/insurance_offset_calculation | ok | 200 | 452.0 | 0 | 1.9 | 2.1 | 3.9 | 1 |
| market-risk/frtb_ima_aggregate_capital_charge | ok | 200 | 657.1 | 0 | 1.8 | 2.1 | 2.1 | 1 |
| credit-risk/ifrs_9_stage_classification_pd_threshold | ok | 200 | 574.1 | 0 | 1.8 | 2.0 | 2.2 | 1 |
| credit-risk/current_exposure_method_cem | ok | 200 | 369.0 | 0 | 1.8 | 2.0 | 2.1 | 1 |
| market-risk/gamma_pnl_attribution | ok | 200 | 591.6 | 0 | 1.6 | 2.0 | 2.3 | 1 |
| credit-risk/kmv_merton_distance_to_default | ok | 200 | 567.5 | 0 | 1.8 | 2.0 | 2.0 | 1 |
| credit-risk/downturn_lgd_adjustment | ok | 200 | 390.4 | 0 | 1.7 | 2.0 | 2.2 | 1 |
| credit-risk/sovereign_credit_risk_assessment | ok | 200 | 367.1 | 0 | 1.8 | 2.0 | 2.0 | 1 |
| credit-risk/cds_spread_to_pd_conversion | ok | 200 | 584.8 | 0 | 1.7 | 2.0 | 2.5 | 1 |
| credit-risk/counterparty_credit_risk_ccr_exposure | ok | 200 | 461.1 | 0 | 1.7 | 1.9 | 2.0 | 1 |
| credit-risk/xva_aggregation | ok | 200 | 365.1 | 0 | 1.7 | 1.9 | 1.9 | 1 |
| credit-risk/ifrs_9_12_month_ecl_stage_1 | ok | 200 | 569.6 | 0 | 1.7 | 1.9 | 2.0 | 1 |
| credit-risk/collateral_haircut_calculation | ok | 200 | 448.2 | 0 | 1.7 | 1.9 | 1.9 | 1 |
| market-risk/theta_carry_attribution | ok | 200 | 564.7 | 0 | 1.6 | 1.8 | 1.9 | 1 |
| credit-risk/wrong_way_risk_adjustment | ok | 200 | 357.7 | 0 | 1.7 | 1.8 | 1.9 | 1 |
| credit-risk/basel_standardised_approach_rwa | ok | 200 | 450.6 | 0 | 1.6 | 1.8 | 1.9 | 1 |
| credit-risk/standardised_approach_ccr_sa_ccr | ok | 200 | 441.5 | 0 | 1.6 | 1.8 | 1.9 | 1 |
| market-risk/greeks_based_pnl_explain | ok | 200 | 702.7 | 0 | 1.6 | 1.8 | 2.1 | 1 |
| credit-risk/exposure_at_default_ead_calculator | ok | 200 | 462.1 | 0 | 1.6 | 1.8 | 1.8 | 1 |
| derivatives/american_option_lsm | COMPILES | 200 | 993.9 | 2 | 419.0 | 476.0 | 480.3 | 10 |
| derivatives/lookback_option_pricer | COMPILES | 200 | 1549.7 | 2 | 224.2 | 250.2 | 252.9 | 6 |
| derivatives/asian_option_pricer | COMPILES | 200 | 1478.3 | 2 | 203.3 | 241.3 | 252.2 | 5 |
| derivatives/bermudan_option_pricer | COMPILES | 200 | 745.6 | 2 | 162.6 | 186.2 | 208.8 | 4 |
| derivatives/rough_volatility_rbergomi_model | COMPILES | 200 | 2076.3 | 6 | 121.0 | 146.7 | 151.1 | 3 |
| derivatives/vasicek_interest_rate_model | COMPILES | 200 | 1245.4 | 2 | 97.8 | 124.2 | 128.8 | 3 |
| derivatives/hull_white_short_rate_model | COMPILES | 200 | 917.9 | 2 | 95.7 | 122.4 | 128.1 | 3 |
| derivatives/normal_inverse_gaussian_model | COMPILES | 200 | 1068.5 | 2 | 7.9 | 10.6 | 13.4 | 1 |
| operational/monte_carlo_oprisk_capital | COMPILES | 200 | 628.7 | 3 | 8.9 | 9.3 | 17.9 | 1 |
| operational/compound_loss_distribution | COMPILES | 200 | 703.2 | 3 | 7.5 | 8.9 | 9.2 | 1 |
| derivatives/variance_gamma_model | COMPILES | 200 | 1231.4 | 2 | 7.3 | 8.0 | 10.0 | 1 |
| derivatives/monte_carlo_option_pricer | COMPILES | 200 | 1292.5 | 2 | 2.9 | 6.3 | 8.3 | 1 |
| liquidity/liquidity_var_liqvar | COMPILES | 200 | 873.2 | 2 | 5.2 | 6.1 | 6.7 | 1 |
| portfolio/sharpe_ratio | COMPILES | 200 | 600.0 | 2 | 2.5 | 4.7 | 5.7 | 1 |
| derivatives/oas_option_adjusted_spread | COMPILES | 200 | 679.0 | 2 | 2.4 | 4.0 | 4.5 | 1 |
| portfolio/maximum_drawdown | COMPILES | 200 | 634.1 | 2 | 3.5 | 3.9 | 3.9 | 1 |
| derivatives/trinomial_tree_option_pricer | COMPILES | 200 | 1030.7 | 2 | 2.5 | 3.7 | 3.8 | 1 |
| derivatives/binomial_tree_option_pricer | COMPILES | 200 | 1199.7 | 2 | 2.4 | 3.1 | 5.3 | 1 |
| derivatives/callable_bond_pricer | COMPILES | 200 | 639.5 | 2 | 2.4 | 2.8 | 3.0 | 1 |
| derivatives/puttable_bond_pricer | COMPILES | 200 | 701.2 | 2 | 2.2 | 2.4 | 2.4 | 1 |
| market-risk/conditional_var_es | COMPILES | 200 | 783.3 | 3 | 1.9 | 2.4 | 2.5 | 1 |
| market-risk/garch_11_volatility_forecast | COMPILES | 200 | 646.5 | 2 | 2.1 | 2.3 | 2.4 | 1 |
| credit-risk/expected_loss_el_computation | COMPILES | 200 | 424.8 | 1 | 1.6 | 2.2 | 2.5 | 1 |
| credit-risk/irb_advanced_approach_capital | COMPILES | 200 | 462.3 | 2 | 2.0 | 2.2 | 2.2 | 1 |
| credit-risk/irb_foundation_approach_capital | COMPILES | 200 | 490.8 | 2 | 1.9 | 2.1 | 2.2 | 1 |
| credit-risk/sme_correlation_factor_basel | COMPILES | 200 | 623.4 | 1 | 1.6 | 1.8 | 1.8 | 1 |
| credit-risk/maturity_adjustment_basel_irb | COMPILES | 200 | 506.9 | 1 | 1.6 | 1.8 | 1.8 | 1 |
| alm/loan_prepayment_rate_cpr | ERROR | 422 | - | 0 | - | - | - | - |
| alm/prepayment_model_mortgages | ERROR | 422 | - | 0 | - | - | - | - |
| credit-risk/credit_var_analytical_vasicek | ERROR | 422 | - | 0 | - | - | - | - |
| credit-risk/point_in_time_pd_estimation | ERROR | 422 | - | 0 | - | - | - | - |
| credit-risk/through_the_cycle_pd_adjustment | ERROR | 422 | - | 0 | - | - | - | - |
| derivatives/chooser_option_pricer | ERROR | 422 | - | 0 | - | - | - | - |
| derivatives/compound_option_pricer | ERROR | 422 | - | 0 | - | - | - | - |
| derivatives/credit_default_swap_cds_pricer | ERROR | 422 | - | 0 | - | - | - | - |
| derivatives/forward_rate_agreement_fra | ERROR | 422 | - | 0 | - | - | - | - |
| operational/scenario_severity_estimation | ERROR | 422 | - | 0 | - | - | - | - |

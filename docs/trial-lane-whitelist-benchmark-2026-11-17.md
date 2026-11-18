# Trial lane whitelist: benchmark of all 385 functions (2026-11-18)

Output of `scripts/trial_weight_bench.py`, run on 2026-11-18 on **every function in the catalogue** (the 2026-11-17 runs measured 151, then 260). It chooses the whitelist of
the A3 trial lane (`docs/plan-trial-lane-throttle.md`): a function may go on it only if it is cheap and does not compile a Numba kernel on a worker's first call. The lane charges the compute
budget by the **measured** time of each call (owner decision, 2026-11-17), so these numbers choose the list; they are not a weight table.

## How it was measured

- **Machine:** this session's sandbox, 4 vCPU Intel Xeon at 2.1 GHz, not Fargate. Absolute times on a 0.5 vCPU task will differ; run the script in the dev image for those. The ranking and the
  compile findings do not depend on the machine.
- **Warm pass:** one process, the real app in process (auth, rate-limit and response middleware included, no network, database or AWS), one unmeasured call, then 30 timed calls per function:
  p50, p95, max.
- **First-call pass:** each function in its own fresh process with an empty Numba cache and the same warm-up the lifespan does (one tiny `run_monte_carlo_var`, the only kernel the image
  pre-bakes); one call, timed, and the number of Numba kernels compiled by it.
- **Payloads (385 of 385 functions, each answers 200):** the catalogue types every non-scalar parameter "object", so a request is built in layers, later ones winning:
  (1) scalar parameters from the catalogue (default, else the middle of the limits); (2) array and matrix parameters from **named fixtures** (`fixture_values()`: 252 daily returns on
  three assets, a 3 by 3 covariance matrix, a small curve and credit book); (3) **name-based guesses** for the remaining arrays (`guess_array()`: every array has length 3 so coupled arrays agree);
  (4) 19 request bodies recorded from the domain API tests; (5) **93 per-function overrides** for functions with rules the catalogue does not state (a probability of 1, an end
  before a start, mappings, lists of records, report fields, matrices of a stated shape), each needed to turn a 422 into a 200.
- **Verdicts:** `ok` (200, no compile, p95 and first call under 1 s), `COMPILES` (the first call compiled one or more kernels), `SLOW` (0 here: p95 or first call at or over one second) and
  `ERROR` (0 here).
- Payloads are test-size (a year of daily returns, a handful of scenarios, three-element arrays). A real caller can send more; the lane bounds that with a body-size cap, an array-length cap and the
  one-second deadline, not with this table. Small arrays also flatter the heavier numerical routines, so a function's weight in real use can be larger than its p95 here.

## Result

| Domain | ok | COMPILES | SLOW or ERROR | measured |
| --- | --- | --- | --- | --- |
| alm | 32 | 1 | 0 | 33 |
| credit-risk | 37 | 18 | 0 | 55 |
| derivatives | 44 | 18 | 0 | 62 |
| liquidity | 36 | 4 | 0 | 40 |
| market-risk | 62 | 9 | 0 | 71 |
| operational | 40 | 4 | 0 | 44 |
| portfolio | 35 | 15 | 0 | 50 |
| regulatory | 29 | 1 | 0 | 30 |
| **all** | **315** | **70** | **0** | **385** |

1. **315 functions are `ok`.** Their p95 has a median of 3.1 ms; 310 of them cost one unit (50 ms or less). The slowest are
   `derivatives/cox_ingersoll_ross_model` (389 ms, 8 units), `operational/scenario_analysis_oprisk` (194 ms, 4 units), `portfolio/resampled_efficient_frontier` (147 ms, 3 units), `derivatives/nelson_siegel_svensson_curve` (128 ms, 3 units). All are far below the one-second deadline.
2. **70 functions `COMPILES`** (1 to 13 kernels in the first call). Warm they are as fast as the others; in a fresh task the first call is slower than one that compiles nothing by up to
   1914 ms (median 286 ms; 36 of 70 under 300 ms). The image pre-bakes one kernel and the lifespan warms one, so the fix is
   the same for all of them: bake the kernels' cache in the image build and warm them at start-up. Until then they stay off the whitelist.
3. **The flagships** (14 of the 26 below are `ok` today, the rest compile): `parametric_delta_normal_var`, `cornish_fisher_var`, `marginal_var`, `component_var`, `monte_carlo_expected_shortfall`, `frtb_ima_expected_shortfall` and others are `ok`; historical-simulation VaR and expected shortfall,
   filtered historical simulation, the GARCH family, Sharpe, Sortino, maximum drawdown and risk parity compile kernels on the first call, which is what makes the baking worth doing.
4. **The first call of a function that compiles nothing still takes 423 ms (median of the `ok` rows) in a fresh process.** That is the one-time per-process cost of the first request
   through the stack, shared by every route, not a property of the function. A running task has paid it already.
5. **Coverage:** every function has a payload now. A payload that later stops answering 200 fails `tests/test_trial_weight_bench.py`, so a changed rule cannot silently drop a function.

## The flagships

| Route | Verdict | First (ms) | Comp | p95 (ms) |
| --- | --- | --- | --- | --- |
| market-risk/historical_simulation_var | COMPILES | 589.2 | 3 | 2.6 |
| market-risk/parametric_delta_normal_var | ok | 379.9 | 0 | 2.1 |
| market-risk/cornish_fisher_var | ok | 351.9 | 0 | 4.2 |
| market-risk/filtered_historical_simulation_var | COMPILES | 865.6 | 4 | 3.2 |
| market-risk/marginal_var | ok | 584.4 | 0 | 2.6 |
| market-risk/component_var | ok | 421.6 | 0 | 2.5 |
| market-risk/historical_expected_shortfall | COMPILES | 761.0 | 3 | 2.8 |
| market-risk/conditional_var_es | COMPILES | 515.0 | 3 | 2.9 |
| market-risk/monte_carlo_expected_shortfall | ok | 407.8 | 0 | 7.9 |
| market-risk/stressed_expected_shortfall | COMPILES | 605.5 | 3 | 3.2 |
| market-risk/frtb_ima_expected_shortfall | ok | 342.8 | 0 | 2.3 |
| market-risk/extreme_value_theory_var | ok | 404.9 | 0 | 29.5 |
| market-risk/compute_cvar | ok | 371.4 | 0 | 2.8 |
| market-risk/kupiec_pof_test | ok | 462.8 | 0 | 2.9 |
| market-risk/christoffersen_independence_test | ok | 376.4 | 0 | 3.3 |
| market-risk/traffic_light_backtesting | ok | 337.8 | 0 | 3.5 |
| market-risk/garch_11_volatility_forecast | COMPILES | 640.1 | 2 | 3.0 |
| market-risk/egarch_volatility_model | COMPILES | 905.9 | 2 | 3.4 |
| market-risk/gjr_garch_asymmetric_model | COMPILES | 604.4 | 2 | 3.2 |
| market-risk/dcc_garch_dynamic_correlation | ok | 498.6 | 0 | 6.7 |
| portfolio/sharpe_ratio | COMPILES | 502.4 | 2 | 2.7 |
| portfolio/sortino_ratio | COMPILES | 516.9 | 1 | 2.6 |
| portfolio/maximum_drawdown | COMPILES | 596.4 | 2 | 3.8 |
| portfolio/portfolio_beta | ok | 430.3 | 0 | 4.2 |
| portfolio/risk_parity_portfolio | COMPILES | 1131.2 | 7 | 6.4 |
| portfolio/maximum_sharpe_ratio_portfolio | ok | 350.9 | 0 | 8.3 |

## For PR 1

Whitelist v1 = a reviewed subset of the `ok` rows (315 is far more than a first-use experience needs; 20 to 30 spread across the eight domains and led by the flagships above is probably
enough), plus the compiling functions once their kernels are baked and warmed. The whitelist is a set of paths in code, reviewed like any other; a function missing from it is simply refused.

## All 385 rows (ms; first = first call in a fresh process; comp = kernels compiled by it; units = ceil(p95 / 50))

| Route | Verdict | First | Comp | p50 | p95 | Max | Units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| derivatives/cox_ingersoll_ross_model | ok | 796.2 | 0 | 349.9 | 388.6 | 388.9 | 8 |
| operational/scenario_analysis_oprisk | ok | 478.5 | 0 | 171.5 | 194.1 | 201.8 | 4 |
| portfolio/resampled_efficient_frontier | ok | 591.2 | 0 | 133.7 | 146.6 | 149.8 | 3 |
| derivatives/nelson_siegel_svensson_curve | ok | 482.6 | 0 | 102.0 | 128.2 | 129.1 | 3 |
| derivatives/nelson_siegel_curve_fit | ok | 380.0 | 0 | 56.3 | 61.2 | 62.6 | 2 |
| market-risk/extreme_value_theory_var | ok | 404.9 | 0 | 26.9 | 29.5 | 30.1 | 1 |
| market-risk/volatility_surface_implied_vol | ok | 427.5 | 0 | 17.7 | 19.1 | 19.3 | 1 |
| derivatives/heston_stochastic_volatility_model | ok | 485.5 | 0 | 9.2 | 9.9 | 10.0 | 1 |
| market-risk/correlation_matrix_historical | ok | 352.5 | 0 | 8.9 | 9.6 | 10.2 | 1 |
| portfolio/mean_variance_optimisation | ok | 372.5 | 0 | 6.7 | 8.8 | 10.7 | 1 |
| portfolio/cvar_constrained_optimisation | ok | 443.8 | 0 | 7.3 | 8.3 | 9.0 | 1 |
| portfolio/maximum_sharpe_ratio_portfolio | ok | 350.9 | 0 | 5.4 | 8.3 | 9.8 | 1 |
| market-risk/monte_carlo_expected_shortfall | ok | 407.8 | 0 | 6.9 | 7.9 | 8.4 | 1 |
| portfolio/minimum_variance_portfolio | ok | 419.2 | 0 | 5.5 | 7.5 | 8.3 | 1 |
| portfolio/robust_portfolio_optimisation | ok | 394.6 | 0 | 4.5 | 7.1 | 9.4 | 1 |
| market-risk/macro_scenario_generator | ok | 387.6 | 0 | 5.1 | 6.9 | 224.8 | 1 |
| market-risk/dcc_garch_dynamic_correlation | ok | 498.6 | 0 | 6.4 | 6.7 | 6.9 | 1 |
| portfolio/fama_french_5_factor_model | ok | 354.5 | 0 | 6.1 | 6.5 | 6.7 | 1 |
| liquidity/contingent_liquidity_risk | ok | 420.8 | 0 | 2.9 | 5.7 | 5.9 | 1 |
| portfolio/fama_french_3_factor_model | ok | 410.1 | 0 | 5.3 | 5.7 | 5.7 | 1 |
| operational/scenario_frequency_estimation | ok | 460.1 | 0 | 2.8 | 5.7 | 7.5 | 1 |
| derivatives/compound_option_pricer | ok | 425.8 | 0 | 4.2 | 5.6 | 5.9 | 1 |
| portfolio/factor_based_optimisation | ok | 400.9 | 0 | 4.5 | 5.3 | 6.0 | 1 |
| alm/economic_value_of_equity_eve | ok | 396.2 | 0 | 2.4 | 5.1 | 6.8 | 1 |
| regulatory/frtb_pl_attribution_test | ok | 344.7 | 0 | 4.6 | 4.9 | 5.1 | 1 |
| alm/modified_duration_balance_sheet | ok | 465.1 | 0 | 2.5 | 4.9 | 6.2 | 1 |
| derivatives/modified_duration | ok | 426.2 | 0 | 3.6 | 4.9 | 7.1 | 1 |
| portfolio/principal_component_analysis | ok | 448.8 | 0 | 4.7 | 4.9 | 5.0 | 1 |
| derivatives/sabr_volatility_model | ok | 453.6 | 0 | 3.3 | 4.9 | 5.4 | 1 |
| market-risk/risk_factor_pca_decomposition | ok | 345.4 | 0 | 4.5 | 4.9 | 5.0 | 1 |
| derivatives/fx_option_pricer_garman_kohlhagen | ok | 425.6 | 0 | 4.1 | 4.7 | 4.9 | 1 |
| portfolio/residual_risk | ok | 607.9 | 0 | 4.2 | 4.6 | 4.9 | 1 |
| alm/liquidity_adjusted_nii | ok | 486.5 | 0 | 2.5 | 4.6 | 8.5 | 1 |
| regulatory/ucits_kiid_risk_indicator | ok | 339.2 | 0 | 3.1 | 4.5 | 4.7 | 1 |
| portfolio/jensens_alpha | ok | 403.0 | 0 | 4.1 | 4.4 | 4.4 | 1 |
| portfolio/correlation_matrix_portfolio | ok | 366.1 | 0 | 3.4 | 4.4 | 193.8 | 1 |
| alm/duration_gap_analysis | ok | 504.8 | 0 | 2.3 | 4.4 | 5.6 | 1 |
| derivatives/equity_swap_pricer | ok | 388.2 | 0 | 3.7 | 4.4 | 4.6 | 1 |
| portfolio/treynor_ratio | ok | 411.8 | 0 | 4.0 | 4.3 | 4.4 | 1 |
| market-risk/pnl_attribution_test_frtb_pat | ok | 341.8 | 0 | 2.8 | 4.2 | 4.6 | 1 |
| portfolio/portfolio_beta | ok | 430.3 | 0 | 3.9 | 4.2 | 4.7 | 1 |
| market-risk/cornish_fisher_var | ok | 351.9 | 0 | 3.9 | 4.2 | 4.2 | 1 |
| derivatives/fx_forward_pricer | ok | 616.6 | 0 | 3.8 | 4.2 | 4.6 | 1 |
| market-risk/historical_scenario_replay | ok | 495.7 | 0 | 4.0 | 4.2 | 4.2 | 1 |
| credit-risk/default_correlation_matrix | ok | 394.0 | 0 | 3.7 | 4.1 | 4.3 | 1 |
| derivatives/z_spread_calculator | ok | 528.6 | 0 | 3.7 | 4.1 | 4.1 | 1 |
| derivatives/barrier_option_pricer | ok | 500.4 | 0 | 3.5 | 4.1 | 4.2 | 1 |
| derivatives/yield_to_maturity | ok | 345.7 | 0 | 3.7 | 4.0 | 4.1 | 1 |
| alm/alm_stress_test | ok | 476.6 | 0 | 3.4 | 4.0 | 4.5 | 1 |
| derivatives/forward_rate_agreement_fra | ok | 445.8 | 0 | 3.7 | 4.0 | 4.2 | 1 |
| portfolio/correlation_clustering | ok | 556.3 | 0 | 3.6 | 4.0 | 4.6 | 1 |
| market-risk/expected_shortfall_contribution | ok | 452.3 | 0 | 3.8 | 4.0 | 4.1 | 1 |
| derivatives/yield_to_call | ok | 431.4 | 0 | 3.7 | 4.0 | 4.6 | 1 |
| portfolio/liquidity_adjusted_portfolio_var | ok | 460.1 | 0 | 3.5 | 3.9 | 4.1 | 1 |
| market-risk/combined_backtesting | ok | 361.3 | 0 | 3.3 | 3.9 | 5.1 | 1 |
| regulatory/basel_iii_tier1_ratio | ok | 454.0 | 0 | 2.4 | 3.9 | 4.2 | 1 |
| regulatory/emir_margin_requirement | ok | 352.5 | 0 | 3.2 | 3.9 | 4.7 | 1 |
| portfolio/tracking_error | ok | 348.6 | 0 | 3.0 | 3.8 | 4.3 | 1 |
| portfolio/carbon_footprint_attribution | ok | 382.1 | 0 | 2.6 | 3.8 | 4.5 | 1 |
| portfolio/carhart_4_factor_model | ok | 351.4 | 0 | 3.6 | 3.8 | 3.9 | 1 |
| regulatory/solvency_ii_scr_credit_risk | ok | 484.5 | 0 | 3.4 | 3.8 | 4.1 | 1 |
| derivatives/convexity | ok | 422.7 | 0 | 2.3 | 3.8 | 8.8 | 1 |
| regulatory/countercyclical_capital_buffer | ok | 481.9 | 0 | 3.4 | 3.7 | 3.8 | 1 |
| derivatives/bond_pricer_floating_rate | ok | 414.9 | 0 | 2.9 | 3.7 | 4.4 | 1 |
| alm/eve_sensitivity_analysis | ok | 517.6 | 0 | 3.4 | 3.7 | 3.9 | 1 |
| market-risk/var_fan_chart | ok | 546.4 | 0 | 3.4 | 3.7 | 3.7 | 1 |
| derivatives/zero_coupon_bond_pricer | ok | 353.5 | 0 | 3.3 | 3.7 | 3.8 | 1 |
| regulatory/emir_trade_repository_report | ok | 579.4 | 0 | 3.1 | 3.7 | 4.4 | 1 |
| market-risk/var_breach_cluster_analysis | ok | 480.8 | 0 | 3.1 | 3.7 | 3.8 | 1 |
| market-risk/rolling_var_backtest | ok | 348.3 | 0 | 3.2 | 3.6 | 3.8 | 1 |
| regulatory/mifid_ii_best_execution_metric | ok | 352.7 | 0 | 3.3 | 3.6 | 3.8 | 1 |
| alm/core_deposit_duration | ok | 631.0 | 0 | 3.3 | 3.6 | 3.8 | 1 |
| market-risk/spectral_risk_measure | ok | 589.6 | 0 | 3.2 | 3.6 | 3.7 | 1 |
| liquidity/hqla_level_1_asset_classifier | ok | 565.8 | 0 | 2.4 | 3.6 | 3.9 | 1 |
| regulatory/combined_buffer_requirement | ok | 420.5 | 0 | 3.3 | 3.6 | 3.7 | 1 |
| regulatory/mifid_ii_algorithm_documentation | ok | 336.7 | 0 | 3.2 | 3.6 | 3.8 | 1 |
| derivatives/cap_floor_pricer | ok | 390.9 | 0 | 2.9 | 3.6 | 5.0 | 1 |
| portfolio/transaction_cost_analysis | ok | 415.4 | 0 | 3.2 | 3.5 | 3.6 | 1 |
| derivatives/local_volatility_dupire_model | ok | 480.3 | 0 | 2.4 | 3.5 | 5.8 | 1 |
| portfolio/gics_sector_exposure | ok | 613.5 | 0 | 3.2 | 3.5 | 3.6 | 1 |
| alm/funds_transfer_pricing_ftp | ok | 387.7 | 0 | 3.0 | 3.5 | 3.8 | 1 |
| regulatory/sftr_securities_finance_report | ok | 437.1 | 0 | 3.3 | 3.5 | 3.5 | 1 |
| operational/kri_trend_analysis | ok | 463.5 | 0 | 3.2 | 3.5 | 3.6 | 1 |
| derivatives/effective_duration | ok | 455.7 | 0 | 2.3 | 3.5 | 3.9 | 1 |
| regulatory/aifmd_risk_metrics | ok | 353.6 | 0 | 3.1 | 3.5 | 3.6 | 1 |
| regulatory/mifid_ii_post_trade_transparency | ok | 346.6 | 0 | 3.1 | 3.5 | 3.6 | 1 |
| alm/effective_duration_alm | ok | 546.3 | 0 | 3.1 | 3.5 | 9.9 | 1 |
| portfolio/omega_ratio | ok | 522.4 | 0 | 3.2 | 3.5 | 3.5 | 1 |
| regulatory/frtb_trading_desk_aggregation | ok | 592.9 | 0 | 3.1 | 3.5 | 3.5 | 1 |
| portfolio/esg_score_integration | ok | 351.4 | 0 | 2.7 | 3.5 | 3.6 | 1 |
| derivatives/digital_option_pricer | ok | 579.5 | 0 | 2.4 | 3.5 | 3.5 | 1 |
| credit-risk/through_the_cycle_pd_adjustment | ok | 480.2 | 0 | 2.1 | 3.5 | 4.3 | 1 |
| market-risk/traffic_light_backtesting | ok | 337.8 | 0 | 3.1 | 3.5 | 3.6 | 1 |
| operational/conduct_risk_metric | ok | 352.2 | 0 | 3.1 | 3.5 | 3.6 | 1 |
| alm/behavioural_modelling_nmds | ok | 505.1 | 0 | 2.7 | 3.5 | 3.8 | 1 |
| alm/ftp_curve_construction | ok | 483.8 | 0 | 2.6 | 3.4 | 3.6 | 1 |
| market-risk/compute_rolling_var | ok | 409.4 | 0 | 3.2 | 3.4 | 3.5 | 1 |
| alm/convexity_gap | ok | 516.1 | 0 | 3.1 | 3.4 | 3.5 | 1 |
| portfolio/factor_exposure_analysis_barra | ok | 606.8 | 0 | 2.4 | 3.4 | 3.5 | 1 |
| operational/control_testing_effectiveness | ok | 369.8 | 0 | 3.0 | 3.4 | 3.4 | 1 |
| regulatory/icaap_capital_assessment | ok | 418.2 | 0 | 3.1 | 3.4 | 3.5 | 1 |
| operational/internal_control_factor_icf | ok | 542.4 | 0 | 3.1 | 3.4 | 3.4 | 1 |
| derivatives/inflation_linked_bond_pricer | ok | 559.6 | 0 | 2.5 | 3.4 | 3.5 | 1 |
| derivatives/asset_swap_spread | ok | 625.9 | 0 | 2.4 | 3.4 | 5.5 | 1 |
| operational/escalation_threshold_calculation | ok | 463.9 | 0 | 3.1 | 3.4 | 3.5 | 1 |
| operational/business_environment_factor_bei | ok | 359.3 | 0 | 2.4 | 3.4 | 3.5 | 1 |
| operational/loss_data_collection_framework | ok | 357.3 | 0 | 3.0 | 3.4 | 3.5 | 1 |
| regulatory/pillar_2b_stress_buffer | ok | 504.4 | 0 | 3.0 | 3.4 | 3.4 | 1 |
| derivatives/caplet_floorlet_pricer_black | ok | 417.1 | 0 | 2.6 | 3.4 | 4.4 | 1 |
| portfolio/portfolio_turnover | ok | 472.3 | 0 | 3.0 | 3.4 | 3.4 | 1 |
| regulatory/mifid_ii_pre_trade_transparency | ok | 467.0 | 0 | 3.0 | 3.4 | 3.4 | 1 |
| operational/external_loss_data_integration | ok | 412.7 | 0 | 3.0 | 3.4 | 3.4 | 1 |
| operational/key_risk_indicator_kri_library | ok | 340.4 | 0 | 3.0 | 3.3 | 3.4 | 1 |
| regulatory/mifid_ii_transaction_report_validator | ok | 485.0 | 0 | 3.0 | 3.3 | 3.4 | 1 |
| regulatory/frtb_sa_market_risk_capital | ok | 427.7 | 0 | 3.0 | 3.3 | 3.4 | 1 |
| liquidity/central_bank_facility_eligibility | ok | 378.4 | 0 | 3.0 | 3.3 | 3.4 | 1 |
| operational/kri_threshold_breach_detection | ok | 388.0 | 0 | 3.0 | 3.3 | 3.4 | 1 |
| regulatory/crr2_large_exposure_limit | ok | 371.9 | 0 | 2.4 | 3.3 | 5.2 | 1 |
| alm/interest_rate_risk_capital_irrbb | ok | 425.8 | 0 | 2.2 | 3.3 | 3.7 | 1 |
| liquidity/wholesale_funding_concentration | ok | 341.8 | 0 | 2.9 | 3.3 | 4.0 | 1 |
| operational/diversification_benefit_oprisk | ok | 445.7 | 0 | 3.0 | 3.3 | 3.4 | 1 |
| liquidity/repo_market_stress_haircut | ok | 341.6 | 0 | 3.0 | 3.3 | 3.4 | 1 |
| portfolio/diversification_ratio | ok | 378.3 | 0 | 2.3 | 3.3 | 3.4 | 1 |
| liquidity/secured_funding_rollover_risk | ok | 352.0 | 0 | 2.7 | 3.3 | 3.4 | 1 |
| market-risk/dv01_pv01_bucketed | ok | 376.0 | 0 | 1.9 | 3.3 | 4.0 | 1 |
| portfolio/active_share | ok | 365.4 | 0 | 2.3 | 3.3 | 5.3 | 1 |
| derivatives/interest_rate_swap_irs_pricer | ok | 416.4 | 0 | 2.7 | 3.3 | 3.4 | 1 |
| regulatory/pillar_2a_capital | ok | 529.4 | 0 | 3.0 | 3.3 | 3.7 | 1 |
| portfolio/factor_return_attribution | ok | 540.6 | 0 | 2.5 | 3.3 | 3.3 | 1 |
| operational/frequency_distribution_fitting | ok | 439.0 | 0 | 3.0 | 3.3 | 3.3 | 1 |
| market-risk/christoffersen_independence_test | ok | 376.4 | 0 | 3.0 | 3.3 | 3.4 | 1 |
| operational/it_risk_scoring | ok | 549.9 | 0 | 3.0 | 3.3 | 3.3 | 1 |
| operational/cyber_risk_loss_estimation | ok | 507.4 | 0 | 3.0 | 3.2 | 3.3 | 1 |
| regulatory/basel_iii_cet1_ratio | ok | 519.4 | 0 | 3.0 | 3.2 | 3.3 | 1 |
| regulatory/frtb_ima_market_risk_capital | ok | 530.1 | 0 | 3.0 | 3.2 | 3.3 | 1 |
| liquidity/retail_deposit_runoff_rate | ok | 420.7 | 0 | 2.8 | 3.2 | 3.4 | 1 |
| market-risk/theta_time_decay | ok | 409.7 | 0 | 2.8 | 3.2 | 3.3 | 1 |
| liquidity/collateral_availability_analysis | ok | 412.7 | 0 | 2.9 | 3.2 | 3.3 | 1 |
| portfolio/tail_ratio | ok | 370.6 | 0 | 2.5 | 3.2 | 3.3 | 1 |
| operational/insurance_offset_calculation | ok | 354.4 | 0 | 2.9 | 3.2 | 3.3 | 1 |
| operational/model_risk_assessment | ok | 567.2 | 0 | 2.9 | 3.2 | 3.3 | 1 |
| regulatory/capital_conservation_buffer | ok | 544.4 | 0 | 2.3 | 3.2 | 3.6 | 1 |
| alm/basis_risk_irrbb | ok | 436.0 | 0 | 2.5 | 3.2 | 3.6 | 1 |
| liquidity/market_wide_stress_scenario | ok | 407.7 | 0 | 2.8 | 3.2 | 3.2 | 1 |
| alm/balance_sheet_projection_model | ok | 492.7 | 0 | 2.4 | 3.2 | 3.8 | 1 |
| liquidity/cross_currency_liquidity_bridge | ok | 446.0 | 0 | 2.8 | 3.2 | 3.3 | 1 |
| operational/scenario_expert_elicitation_model | ok | 368.3 | 0 | 2.9 | 3.2 | 3.3 | 1 |
| portfolio/currency_attribution | ok | 463.2 | 0 | 2.4 | 3.2 | 3.4 | 1 |
| derivatives/bootstrap_yield_curve | ok | 399.6 | 0 | 2.9 | 3.1 | 3.2 | 1 |
| liquidity/available_stable_funding_asf_calc | ok | 447.1 | 0 | 2.8 | 3.1 | 3.2 | 1 |
| operational/loss_event_classification_basel | ok | 411.6 | 0 | 2.8 | 3.1 | 3.1 | 1 |
| liquidity/combined_stress_scenario | ok | 493.8 | 0 | 2.8 | 3.1 | 3.2 | 1 |
| liquidity/deposit_stability_classification | ok | 409.0 | 0 | 2.3 | 3.1 | 4.1 | 1 |
| liquidity/asset_encumbrance_ratio | ok | 434.5 | 0 | 2.8 | 3.1 | 3.1 | 1 |
| market-risk/realised_volatility | ok | 350.0 | 0 | 2.3 | 3.1 | 3.4 | 1 |
| derivatives/chooser_option_pricer | ok | 403.5 | 0 | 2.8 | 3.1 | 3.1 | 1 |
| market-risk/frtb_ima_stressed_period_finder | ok | 501.8 | 0 | 2.8 | 3.1 | 3.2 | 1 |
| portfolio/equal_weight_portfolio | ok | 529.2 | 0 | 2.0 | 3.1 | 5.8 | 1 |
| operational/near_miss_capture_framework | ok | 590.3 | 0 | 2.2 | 3.0 | 3.2 | 1 |
| derivatives/credit_default_swap_cds_pricer | ok | 406.6 | 0 | 2.4 | 3.0 | 3.5 | 1 |
| market-risk/vanna_delta_vega_cross | ok | 342.8 | 0 | 2.7 | 3.0 | 3.5 | 1 |
| liquidity/required_stable_funding_rsf_calc | ok | 370.7 | 0 | 2.8 | 3.0 | 3.2 | 1 |
| operational/oprisk_capital_allocation | ok | 387.3 | 0 | 2.1 | 3.0 | 3.3 | 1 |
| derivatives/black_scholes_european_option | ok | 479.9 | 0 | 2.3 | 3.0 | 3.4 | 1 |
| credit-risk/credit_var_analytical_vasicek | ok | 580.5 | 0 | 2.4 | 3.0 | 3.4 | 1 |
| market-risk/var_by_risk_factor | ok | 385.4 | 0 | 2.6 | 3.0 | 3.3 | 1 |
| credit-risk/point_in_time_pd_estimation | ok | 381.8 | 0 | 2.2 | 3.0 | 3.1 | 1 |
| derivatives/black_scholes_greeks | ok | 395.9 | 0 | 2.6 | 2.9 | 3.0 | 1 |
| market-risk/theta_carry_attribution | ok | 500.4 | 0 | 2.5 | 2.9 | 3.0 | 1 |
| operational/oprisk_economic_capital | ok | 374.3 | 0 | 2.6 | 2.9 | 3.1 | 1 |
| liquidity/funding_tenor_analysis | ok | 472.8 | 0 | 2.0 | 2.9 | 3.2 | 1 |
| alm/repricing_gap_analysis | ok | 590.1 | 0 | 2.3 | 2.9 | 3.1 | 1 |
| operational/severity_distribution_fitting | ok | 746.7 | 0 | 2.3 | 2.9 | 3.4 | 1 |
| regulatory/srep_capital_add_on | ok | 390.4 | 0 | 2.3 | 2.9 | 3.3 | 1 |
| liquidity/contingency_funding_plan_trigger | ok | 364.7 | 0 | 2.7 | 2.9 | 3.0 | 1 |
| market-risk/kupiec_pof_test | ok | 462.8 | 0 | 2.5 | 2.9 | 4.5 | 1 |
| credit-risk/effective_epe_regulatory | ok | 385.7 | 0 | 2.6 | 2.9 | 3.0 | 1 |
| credit-risk/credit_stress_testing | ok | 528.6 | 0 | 2.5 | 2.9 | 2.9 | 1 |
| derivatives/displaced_diffusion_model | ok | 402.1 | 0 | 2.5 | 2.8 | 3.0 | 1 |
| market-risk/compute_cvar | ok | 371.4 | 0 | 2.6 | 2.8 | 2.9 | 1 |
| operational/basel_standardised_measurement_sma | ok | 505.0 | 0 | 2.0 | 2.8 | 4.6 | 1 |
| alm/non_maturity_deposit_stability | ok | 452.8 | 0 | 2.5 | 2.8 | 3.6 | 1 |
| regulatory/basel_iii_total_capital_ratio | ok | 431.6 | 0 | 2.4 | 2.8 | 2.9 | 1 |
| credit-risk/xva_aggregation | ok | 551.0 | 0 | 2.6 | 2.8 | 2.9 | 1 |
| derivatives/cross_currency_swap_pricer | ok | 463.7 | 0 | 2.3 | 2.8 | 4.6 | 1 |
| operational/scenario_severity_estimation | ok | 396.4 | 0 | 2.3 | 2.8 | 4.8 | 1 |
| market-risk/sector_stress_scenario | ok | 427.8 | 0 | 2.5 | 2.8 | 2.8 | 1 |
| operational/rcsa_inherent_risk_scoring | ok | 423.4 | 0 | 2.4 | 2.8 | 2.9 | 1 |
| market-risk/portfolio_delta_aggregated | ok | 367.7 | 0 | 2.5 | 2.8 | 2.8 | 1 |
| market-risk/vega_surface_bucketed | ok | 451.7 | 0 | 1.8 | 2.8 | 4.2 | 1 |
| market-risk/frtb_sa_sensitivity_based_method | ok | 353.3 | 0 | 2.5 | 2.8 | 2.8 | 1 |
| market-risk/compute_breaches | ok | 406.0 | 0 | 2.5 | 2.8 | 2.8 | 1 |
| market-risk/rho_interest_rate | ok | 361.3 | 0 | 2.5 | 2.8 | 3.0 | 1 |
| market-risk/rates_pnl_attribution | ok | 353.4 | 0 | 2.6 | 2.8 | 2.9 | 1 |
| liquidity/liquidity_scorecard_aggregation | ok | 431.8 | 0 | 2.5 | 2.8 | 2.8 | 1 |
| alm/pipeline_risk_measurement | ok | 362.0 | 0 | 2.3 | 2.8 | 2.9 | 1 |
| liquidity/net_stable_funding_ratio_nsfr | ok | 354.8 | 0 | 2.5 | 2.8 | 2.9 | 1 |
| liquidity/fx_liquidity_risk_by_currency | ok | 398.3 | 0 | 2.5 | 2.8 | 2.8 | 1 |
| market-risk/compute_loss_percentiles | ok | 386.0 | 0 | 2.5 | 2.8 | 2.9 | 1 |
| liquidity/hqla_level_2a_asset_classifier | ok | 508.3 | 0 | 2.5 | 2.8 | 2.8 | 1 |
| market-risk/sensitivity_stress_profile | ok | 423.2 | 0 | 2.5 | 2.8 | 2.8 | 1 |
| regulatory/emir_clearing_obligation_check | ok | 378.2 | 0 | 2.3 | 2.8 | 3.9 | 1 |
| operational/audit_finding_risk_scorer | ok | 417.1 | 0 | 2.4 | 2.8 | 2.8 | 1 |
| operational/operational_var_opvar | ok | 452.3 | 0 | 2.1 | 2.7 | 4.8 | 1 |
| derivatives/bond_pricer_fixed_coupon | ok | 561.6 | 0 | 2.3 | 2.7 | 2.9 | 1 |
| credit-risk/capital_valuation_adjustment_kva | ok | 567.0 | 0 | 1.8 | 2.7 | 2.9 | 1 |
| liquidity/idiosyncratic_stress_scenario | ok | 410.8 | 0 | 2.4 | 2.7 | 2.8 | 1 |
| derivatives/ois_curve_sonia_sofr | ok | 448.8 | 0 | 2.3 | 2.7 | 2.8 | 1 |
| credit-risk/kmv_merton_distance_to_default | ok | 466.9 | 0 | 2.5 | 2.7 | 2.8 | 1 |
| alm/irrbb_six_standard_rate_shocks | ok | 501.9 | 0 | 2.2 | 2.7 | 3.2 | 1 |
| alm/structural_hedge_optimisation | ok | 595.6 | 0 | 2.5 | 2.7 | 2.8 | 1 |
| credit-risk/loss_given_default_lgd_model | ok | 509.2 | 0 | 2.5 | 2.7 | 2.7 | 1 |
| market-risk/frtb_ima_aggregate_capital_charge | ok | 379.9 | 0 | 1.8 | 2.7 | 2.9 | 1 |
| credit-risk/funding_valuation_adjustment_fva | ok | 389.5 | 0 | 2.4 | 2.7 | 2.7 | 1 |
| portfolio/calmar_ratio | ok | 350.3 | 0 | 2.3 | 2.7 | 3.2 | 1 |
| alm/repricing_maturity_profile | ok | 409.7 | 0 | 2.3 | 2.7 | 3.0 | 1 |
| liquidity/hqla_level_2b_asset_classifier | ok | 350.9 | 0 | 2.4 | 2.7 | 2.8 | 1 |
| liquidity/liquidity_risk_appetite_threshold | ok | 341.6 | 0 | 2.5 | 2.7 | 2.8 | 1 |
| regulatory/basel_iv_output_floor | ok | 404.2 | 0 | 2.2 | 2.7 | 3.7 | 1 |
| market-risk/cvar_decomposition_euler | ok | 385.2 | 0 | 2.4 | 2.7 | 2.7 | 1 |
| market-risk/frtb_ima_non_modellable_risk_factors | ok | 527.2 | 0 | 2.4 | 2.7 | 2.9 | 1 |
| alm/dynamic_gap_analysis | ok | 449.4 | 0 | 2.3 | 2.7 | 2.7 | 1 |
| regulatory/basel_iii_leverage_ratio | ok | 398.1 | 0 | 2.0 | 2.7 | 2.9 | 1 |
| market-risk/frtb_sa_default_risk_charge | ok | 406.8 | 0 | 2.4 | 2.7 | 2.7 | 1 |
| market-risk/basel_capital_addon_multiplier | ok | 403.7 | 0 | 1.7 | 2.7 | 2.8 | 1 |
| alm/asset_liability_mismatch_index | ok | 366.7 | 0 | 2.4 | 2.7 | 2.8 | 1 |
| liquidity/liquidity_stress_scenario | ok | 392.9 | 0 | 2.4 | 2.7 | 2.7 | 1 |
| market-risk/volga_vega_convexity | ok | 484.5 | 0 | 2.3 | 2.6 | 2.7 | 1 |
| alm/nii_simulation_baseline | ok | 435.3 | 0 | 2.2 | 2.6 | 3.6 | 1 |
| market-risk/vega_pnl_attribution | ok | 437.0 | 0 | 1.7 | 2.6 | 2.7 | 1 |
| derivatives/duration_macaulay | ok | 509.1 | 0 | 2.3 | 2.6 | 2.8 | 1 |
| credit-risk/downturn_lgd_adjustment | ok | 478.1 | 0 | 2.3 | 2.6 | 2.8 | 1 |
| derivatives/swaption_pricer_sabr | ok | 408.4 | 0 | 2.4 | 2.6 | 2.8 | 1 |
| liquidity/liquidity_transfer_pricing | ok | 397.9 | 0 | 2.4 | 2.6 | 2.7 | 1 |
| liquidity/liquidity_coverage_ratio_lcr | ok | 427.3 | 0 | 1.8 | 2.6 | 2.8 | 1 |
| alm/static_gap_analysis | ok | 526.9 | 0 | 2.3 | 2.6 | 2.6 | 1 |
| market-risk/frtb_sa_residual_risk_addon | ok | 392.5 | 0 | 2.4 | 2.6 | 2.7 | 1 |
| alm/irrbb_internal_model | ok | 395.2 | 0 | 2.4 | 2.6 | 2.6 | 1 |
| market-risk/charm_delta_decay | ok | 478.6 | 0 | 2.3 | 2.6 | 2.7 | 1 |
| derivatives/swaption_pricer_black | ok | 345.4 | 0 | 2.3 | 2.6 | 2.7 | 1 |
| alm/option_risk_irrbb | ok | 499.8 | 0 | 2.2 | 2.6 | 2.6 | 1 |
| alm/nii_simulation_stress | ok | 499.5 | 0 | 2.3 | 2.6 | 2.6 | 1 |
| market-risk/fx_pnl_attribution | ok | 346.9 | 0 | 2.3 | 2.6 | 2.6 | 1 |
| credit-risk/ifrs_9_stage_classification_pd_threshold | ok | 501.6 | 0 | 2.2 | 2.6 | 2.8 | 1 |
| portfolio/black_litterman_model | ok | 532.6 | 0 | 2.3 | 2.6 | 2.7 | 1 |
| market-risk/marginal_var | ok | 584.4 | 0 | 1.7 | 2.6 | 2.7 | 1 |
| credit-risk/wrong_way_risk_adjustment | ok | 407.9 | 0 | 1.9 | 2.6 | 2.6 | 1 |
| liquidity/ilaap_internal_liquidity_metric | ok | 452.5 | 0 | 1.7 | 2.6 | 2.9 | 1 |
| credit-risk/sector_default_rate_analysis | ok | 386.6 | 0 | 1.8 | 2.6 | 3.4 | 1 |
| alm/loan_prepayment_rate_cpr | ok | 544.2 | 0 | 2.3 | 2.6 | 2.8 | 1 |
| market-risk/contagion_stress_scenario | ok | 368.2 | 0 | 2.2 | 2.6 | 2.6 | 1 |
| credit-risk/current_exposure_method_cem | ok | 366.4 | 0 | 2.2 | 2.5 | 2.6 | 1 |
| alm/macaulay_duration_balance_sheet | ok | 539.3 | 0 | 2.3 | 2.5 | 2.9 | 1 |
| credit-risk/recovery_rate_estimation | ok | 386.3 | 0 | 1.9 | 2.5 | 2.6 | 1 |
| market-risk/gamma_cross_gamma_matrix | ok | 409.1 | 0 | 2.2 | 2.5 | 2.6 | 1 |
| market-risk/residual_pnl_unexplained | ok | 486.5 | 0 | 1.9 | 2.5 | 2.6 | 1 |
| credit-risk/credit_portfolio_optimisation | ok | 554.0 | 0 | 1.9 | 2.5 | 2.9 | 1 |
| derivatives/dv01_pvbp | ok | 506.9 | 0 | 2.3 | 2.5 | 2.6 | 1 |
| credit-risk/ifrs_9_12_month_ecl_stage_1 | ok | 470.5 | 0 | 2.3 | 2.5 | 2.5 | 1 |
| derivatives/spread_option_kirk_approximation | ok | 399.0 | 0 | 2.3 | 2.5 | 2.5 | 1 |
| operational/business_continuity_risk_score | ok | 464.1 | 0 | 2.1 | 2.5 | 2.5 | 1 |
| portfolio/concentration_risk_hhi | ok | 417.0 | 0 | 2.2 | 2.5 | 2.7 | 1 |
| market-risk/credit_pnl_attribution | ok | 376.0 | 0 | 2.2 | 2.5 | 2.6 | 1 |
| market-risk/incremental_var | ok | 399.2 | 0 | 2.2 | 2.5 | 2.5 | 1 |
| market-risk/component_var | ok | 421.6 | 0 | 2.2 | 2.5 | 3.6 | 1 |
| operational/risk_appetite_statement_oprisk | ok | 359.3 | 0 | 2.0 | 2.5 | 4.6 | 1 |
| liquidity/early_warning_indicator_liquidity | ok | 510.4 | 0 | 1.9 | 2.5 | 2.8 | 1 |
| derivatives/overnight_index_swap_ois | ok | 379.0 | 0 | 2.2 | 2.5 | 2.6 | 1 |
| credit-risk/margin_valuation_adjustment_mva | ok | 516.9 | 0 | 1.7 | 2.5 | 2.6 | 1 |
| derivatives/convertible_bond_pricer | ok | 443.1 | 0 | 2.1 | 2.4 | 2.5 | 1 |
| alm/irrbb_standardised_framework | ok | 378.4 | 0 | 2.3 | 2.4 | 2.5 | 1 |
| alm/nii_sensitivity_rate_shock | ok | 439.6 | 0 | 2.2 | 2.4 | 2.5 | 1 |
| operational/oprisk_heat_map_generator | ok | 447.0 | 0 | 2.2 | 2.4 | 2.5 | 1 |
| credit-risk/ifrs_9_scenario_weighted_ecl | ok | 436.4 | 0 | 1.9 | 2.4 | 2.7 | 1 |
| credit-risk/exposure_at_default_ead_calculator | ok | 526.3 | 0 | 2.2 | 2.4 | 2.7 | 1 |
| market-risk/greeks_based_pnl_explain | ok | 410.0 | 0 | 2.2 | 2.4 | 2.5 | 1 |
| credit-risk/ifrs_9_staging_criteria_assessment | ok | 475.9 | 0 | 1.8 | 2.4 | 2.5 | 1 |
| market-risk/gamma_pnl_attribution | ok | 401.5 | 0 | 2.1 | 2.4 | 2.5 | 1 |
| market-risk/cs01_credit_spread | ok | 343.2 | 0 | 2.1 | 2.4 | 2.4 | 1 |
| operational/tail_risk_scenario_oprisk | ok | 421.1 | 0 | 2.0 | 2.4 | 2.5 | 1 |
| market-risk/liquidity_adjusted_es | ok | 365.4 | 0 | 2.1 | 2.3 | 2.4 | 1 |
| derivatives/swap_rate_curve | ok | 755.4 | 0 | 2.1 | 2.3 | 2.4 | 1 |
| market-risk/hypothetical_multi_factor_scenario | ok | 403.1 | 0 | 2.1 | 2.3 | 2.4 | 1 |
| operational/root_cause_analysis_template | ok | 372.7 | 0 | 2.0 | 2.3 | 2.8 | 1 |
| credit-risk/macroeconomic_overlays_ecl | ok | 502.5 | 0 | 1.8 | 2.3 | 2.4 | 1 |
| market-risk/frtb_ima_expected_shortfall | ok | 342.8 | 0 | 2.0 | 2.3 | 2.9 | 1 |
| credit-risk/credit_concentration_risk_hhi | ok | 414.9 | 0 | 1.9 | 2.3 | 2.4 | 1 |
| credit-risk/expected_positive_exposure_epe | ok | 423.6 | 0 | 1.8 | 2.3 | 2.6 | 1 |
| operational/rcsa_control_effectiveness | ok | 461.8 | 0 | 1.9 | 2.3 | 2.5 | 1 |
| operational/rcsa_risk_identification | ok | 475.4 | 0 | 1.8 | 2.3 | 2.4 | 1 |
| derivatives/total_return_swap_trs | ok | 379.3 | 0 | 2.0 | 2.2 | 2.3 | 1 |
| operational/third_party_vendor_risk | ok | 412.5 | 0 | 1.9 | 2.2 | 2.3 | 1 |
| credit-risk/corporate_credit_scoring_model | ok | 413.4 | 0 | 1.9 | 2.2 | 2.5 | 1 |
| operational/rcsa_residual_risk_scoring | ok | 488.4 | 0 | 1.9 | 2.2 | 2.5 | 1 |
| operational/regulatory_compliance_score | ok | 347.1 | 0 | 2.0 | 2.2 | 2.3 | 1 |
| liquidity/liquidity_buffer_sizing | ok | 595.5 | 0 | 1.8 | 2.2 | 2.4 | 1 |
| credit-risk/credit_default_swap_var | ok | 485.7 | 0 | 2.0 | 2.2 | 2.3 | 1 |
| liquidity/funding_cost_analysis | ok | 388.6 | 0 | 1.9 | 2.2 | 2.4 | 1 |
| credit-risk/credit_spread_curve_bootstrap | ok | 372.9 | 0 | 1.9 | 2.2 | 2.6 | 1 |
| operational/oprisk_stress_testing | ok | 510.3 | 0 | 1.9 | 2.1 | 2.2 | 1 |
| market-risk/parametric_delta_normal_var | ok | 379.9 | 0 | 1.7 | 2.1 | 2.2 | 1 |
| liquidity/survival_horizon_calculator | ok | 374.4 | 0 | 1.8 | 2.1 | 2.7 | 1 |
| credit-risk/cds_spread_to_pd_conversion | ok | 522.8 | 0 | 1.7 | 2.1 | 2.1 | 1 |
| liquidity/intragroup_liquidity_flow | ok | 357.1 | 0 | 1.8 | 2.0 | 2.5 | 1 |
| liquidity/intraday_liquidity_monitor | ok | 358.3 | 0 | 1.8 | 2.0 | 2.3 | 1 |
| liquidity/intraday_liquidity_stress_test | ok | 424.7 | 0 | 1.8 | 2.0 | 2.1 | 1 |
| credit-risk/retail_scorecard_pd_model | ok | 499.1 | 0 | 1.8 | 2.0 | 2.0 | 1 |
| credit-risk/counterparty_credit_risk_ccr_exposure | ok | 470.4 | 0 | 1.7 | 2.0 | 2.1 | 1 |
| credit-risk/altman_z_score_credit_scoring | ok | 504.5 | 0 | 1.6 | 2.0 | 2.0 | 1 |
| credit-risk/collateral_haircut_calculation | ok | 568.7 | 0 | 1.7 | 1.9 | 2.0 | 1 |
| credit-risk/sovereign_credit_risk_assessment | ok | 475.1 | 0 | 1.8 | 1.9 | 2.0 | 1 |
| liquidity/ilaap_stress_testing_framework | ok | 364.2 | 0 | 1.7 | 1.9 | 2.0 | 1 |
| market-risk/reverse_stress_testing | ok | 365.0 | 0 | 1.5 | 1.9 | 4.7 | 1 |
| credit-risk/basel_standardised_approach_rwa | ok | 615.0 | 0 | 1.5 | 1.9 | 2.3 | 1 |
| credit-risk/standardised_approach_ccr_sa_ccr | ok | 414.1 | 0 | 1.7 | 1.9 | 2.0 | 1 |
| derivatives/american_option_lsm | COMPILES | 1139.8 | 2 | 468.3 | 509.9 | 515.0 | 11 |
| derivatives/asian_option_pricer | COMPILES | 1259.3 | 2 | 246.2 | 261.5 | 269.9 | 6 |
| derivatives/lookback_option_pricer | COMPILES | 1409.7 | 2 | 230.7 | 255.0 | 279.4 | 6 |
| derivatives/bermudan_option_pricer | COMPILES | 1002.7 | 2 | 162.8 | 202.3 | 213.1 | 5 |
| derivatives/rough_volatility_rbergomi_model | COMPILES | 2337.1 | 6 | 127.1 | 136.4 | 146.9 | 3 |
| derivatives/vasicek_interest_rate_model | COMPILES | 906.1 | 2 | 109.1 | 123.1 | 128.0 | 3 |
| derivatives/hull_white_short_rate_model | COMPILES | 1106.8 | 2 | 93.7 | 116.8 | 119.0 | 3 |
| derivatives/lmm_bgm_rate_model | COMPILES | 2078.8 | 4 | 36.3 | 42.8 | 68.3 | 1 |
| operational/advanced_measurement_approach_ama | COMPILES | 643.1 | 3 | 21.2 | 23.4 | 23.6 | 1 |
| operational/loss_distribution_approach_lda | COMPILES | 923.3 | 3 | 22.2 | 22.9 | 23.0 | 1 |
| derivatives/basket_option_pricer | COMPILES | 1398.0 | 2 | 15.2 | 16.3 | 20.1 | 1 |
| derivatives/rainbow_option_pricer | COMPILES | 1303.3 | 2 | 13.0 | 16.2 | 20.7 | 1 |
| portfolio/monte_carlo_portfolio_simulation | COMPILES | 725.5 | 2 | 14.2 | 15.4 | 15.5 | 1 |
| liquidity/liquidity_var_liqvar | COMPILES | 861.1 | 2 | 8.0 | 15.2 | 18.0 | 1 |
| derivatives/normal_inverse_gaussian_model | COMPILES | 1064.9 | 2 | 8.7 | 13.0 | 14.2 | 1 |
| credit-risk/credit_var_monte_carlo | COMPILES | 1470.0 | 6 | 6.5 | 12.3 | 26.3 | 1 |
| operational/monte_carlo_oprisk_capital | COMPILES | 837.5 | 3 | 11.6 | 12.0 | 12.3 | 1 |
| derivatives/monte_carlo_option_pricer | COMPILES | 1431.8 | 2 | 7.6 | 10.4 | 14.6 | 1 |
| operational/compound_loss_distribution | COMPILES | 668.3 | 3 | 8.7 | 9.8 | 10.1 | 1 |
| credit-risk/potential_future_exposure_pfe | COMPILES | 2202.4 | 13 | 8.9 | 9.4 | 9.7 | 1 |
| derivatives/variance_gamma_model | COMPILES | 1403.6 | 2 | 6.6 | 7.0 | 7.8 | 1 |
| credit-risk/logistic_regression_pd_model | COMPILES | 558.2 | 2 | 6.4 | 6.8 | 6.8 | 1 |
| credit-risk/machine_learning_pd_calibration | COMPILES | 553.1 | 2 | 4.5 | 6.5 | 6.9 | 1 |
| portfolio/risk_parity_portfolio | COMPILES | 1131.2 | 7 | 6.1 | 6.4 | 6.7 | 1 |
| credit-risk/unexpected_loss_ul_computation | COMPILES | 796.3 | 2 | 1.8 | 4.8 | 8.8 | 1 |
| credit-risk/creditmetrics_portfolio_model | COMPILES | 1324.1 | 6 | 4.3 | 4.7 | 6.8 | 1 |
| portfolio/regime_detection_hmm | COMPILES | 1255.9 | 2 | 4.1 | 4.4 | 4.6 | 1 |
| alm/prepayment_model_mortgages | COMPILES | 895.2 | 2 | 2.5 | 4.4 | 5.1 | 1 |
| derivatives/callable_bond_pricer | COMPILES | 726.1 | 2 | 2.5 | 4.2 | 6.2 | 1 |
| portfolio/information_ratio | COMPILES | 678.8 | 2 | 3.8 | 4.1 | 4.2 | 1 |
| regulatory/solvency_ii_scr_market_risk | COMPILES | 463.7 | 1 | 3.4 | 3.9 | 5.4 | 1 |
| portfolio/maximum_drawdown | COMPILES | 596.4 | 2 | 3.4 | 3.8 | 3.8 | 1 |
| portfolio/ulcer_index | COMPILES | 561.4 | 1 | 3.4 | 3.6 | 4.0 | 1 |
| portfolio/return_attribution_brinson | COMPILES | 672.3 | 2 | 3.3 | 3.6 | 3.7 | 1 |
| portfolio/marginal_contribution_to_risk | COMPILES | 1123.2 | 7 | 3.3 | 3.6 | 3.6 | 1 |
| portfolio/conditional_drawdown_at_risk | COMPILES | 699.4 | 2 | 2.4 | 3.4 | 3.5 | 1 |
| market-risk/egarch_volatility_model | COMPILES | 905.9 | 2 | 2.6 | 3.4 | 5.9 | 1 |
| derivatives/puttable_bond_pricer | COMPILES | 647.1 | 2 | 2.2 | 3.3 | 4.3 | 1 |
| portfolio/rebalancing_optimiser | COMPILES | 526.9 | 2 | 3.0 | 3.3 | 3.4 | 1 |
| liquidity/liquidity_gap_analysis | COMPILES | 586.2 | 2 | 2.3 | 3.2 | 4.2 | 1 |
| market-risk/filtered_historical_simulation_var | COMPILES | 865.6 | 4 | 2.5 | 3.2 | 3.5 | 1 |
| market-risk/stressed_expected_shortfall | COMPILES | 605.5 | 3 | 2.8 | 3.2 | 3.3 | 1 |
| market-risk/gjr_garch_asymmetric_model | COMPILES | 604.4 | 2 | 2.8 | 3.2 | 3.3 | 1 |
| liquidity/cash_flow_ladder_1_year | COMPILES | 572.8 | 2 | 2.4 | 3.0 | 3.1 | 1 |
| credit-risk/irb_foundation_approach_capital | COMPILES | 674.3 | 2 | 2.3 | 3.0 | 3.1 | 1 |
| liquidity/cash_flow_ladder_30_day | COMPILES | 494.0 | 2 | 2.4 | 3.0 | 3.1 | 1 |
| market-risk/garch_11_volatility_forecast | COMPILES | 640.1 | 2 | 2.8 | 3.0 | 3.1 | 1 |
| market-risk/conditional_var_es | COMPILES | 515.0 | 3 | 2.5 | 2.9 | 2.9 | 1 |
| credit-risk/cds_pricing_isda_standard | COMPILES | 715.3 | 2 | 2.3 | 2.9 | 3.6 | 1 |
| credit-risk/ratings_migration_matrix | COMPILES | 579.6 | 4 | 2.2 | 2.9 | 3.0 | 1 |
| credit-risk/irb_advanced_approach_capital | COMPILES | 704.1 | 2 | 2.5 | 2.8 | 2.9 | 1 |
| portfolio/sector_attribution | COMPILES | 751.2 | 2 | 2.2 | 2.8 | 3.0 | 1 |
| credit-risk/credit_valuation_adjustment_cva | COMPILES | 526.0 | 1 | 2.2 | 2.8 | 3.1 | 1 |
| market-risk/historical_expected_shortfall | COMPILES | 761.0 | 3 | 2.5 | 2.8 | 2.9 | 1 |
| portfolio/average_drawdown | COMPILES | 566.7 | 2 | 2.3 | 2.8 | 3.4 | 1 |
| portfolio/sharpe_ratio | COMPILES | 502.4 | 2 | 2.3 | 2.7 | 2.9 | 1 |
| credit-risk/ifrs_9_lifetime_ecl_stage_2_3 | COMPILES | 647.5 | 1 | 2.0 | 2.7 | 2.8 | 1 |
| portfolio/drawdown_duration | COMPILES | 724.7 | 2 | 2.3 | 2.7 | 3.1 | 1 |
| credit-risk/cva_sensitivity_cva_greeks | COMPILES | 670.7 | 1 | 2.2 | 2.6 | 2.8 | 1 |
| market-risk/historical_simulation_var | COMPILES | 589.2 | 3 | 2.4 | 2.6 | 2.7 | 1 |
| derivatives/oas_option_adjusted_spread | COMPILES | 604.2 | 2 | 2.3 | 2.6 | 3.2 | 1 |
| derivatives/binomial_tree_option_pricer | COMPILES | 1125.4 | 2 | 2.1 | 2.6 | 2.6 | 1 |
| portfolio/sortino_ratio | COMPILES | 516.9 | 1 | 2.3 | 2.6 | 2.9 | 1 |
| credit-risk/probability_of_default_pd_estimation | COMPILES | 754.0 | 2 | 2.3 | 2.5 | 2.6 | 1 |
| credit-risk/debt_valuation_adjustment_dva | COMPILES | 619.7 | 1 | 1.9 | 2.5 | 2.7 | 1 |
| derivatives/trinomial_tree_option_pricer | COMPILES | 1235.3 | 2 | 2.1 | 2.4 | 2.4 | 1 |
| credit-risk/expected_loss_el_computation | COMPILES | 522.3 | 1 | 1.7 | 2.3 | 184.4 | 1 |
| market-risk/es_at_multiple_confidence_levels | COMPILES | 546.4 | 3 | 1.8 | 2.3 | 2.3 | 1 |
| credit-risk/maturity_adjustment_basel_irb | COMPILES | 542.8 | 1 | 1.7 | 2.3 | 2.3 | 1 |
| credit-risk/sme_correlation_factor_basel | COMPILES | 587.8 | 1 | 1.5 | 1.8 | 1.8 | 1 |

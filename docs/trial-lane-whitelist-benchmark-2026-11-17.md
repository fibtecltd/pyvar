# Trial lane whitelist: benchmark of 260 functions (2026-11-17)

Output of `scripts/trial_weight_bench.py` (PR #436), run twice on 2026-11-17: first on 151 functions, then on 260 after the array payloads below were added. It chooses the whitelist of
the A3 trial lane (`docs/plan-trial-lane-throttle.md`): a function may go on it only if it is cheap and does not compile a Numba kernel on a worker's first call. The lane charges the compute
budget by the **measured** time of each call (owner decision, 2026-11-17), so these numbers choose the list; they are not a weight table.

## How it was measured

- **Machine:** this session's sandbox, 4 vCPU Intel Xeon at 2.1 GHz, not Fargate. Absolute times on a 0.5 vCPU task will differ; run the script in the dev image for those. The ranking and the
  compile findings do not depend on the machine.
- **Warm pass:** one process, the real app in process (auth, rate-limit and response middleware included, no network, database or AWS), one unmeasured call, then 30 timed calls per function:
  p50, p95, max.
- **First-call pass:** each function in its own fresh process with an empty Numba cache and the same warm-up the lifespan does (one tiny `run_monte_carlo_var`, the only kernel the image
  pre-bakes); one call, timed, and the number of Numba kernels compiled by it.
- **Payloads (260 of 385 functions):** (1) scalar parameters from the catalogue (default, else the middle of the limits); (2) **array and matrix parameters from named fixtures**
  (`fixture_values()` in the script: 252 daily returns on three assets, a 3 by 3 covariance matrix, a three-bucket curve, a three-name credit book; the catalogue types every non-scalar
  parameter "object", so the name is the only guide); (3) 19 recorded request bodies from the domain API tests, which win over the built ones; (4) per-function overrides for 19 functions
  whose own rules the catalogue does not state (a probability of 1, an end before a start, a stress window that does not exist), each needed to turn a 422 into a 200. **125 functions
  have no payload yet:** their array or object parameters have names no fixture covers (185 distinct names, 165 of them used by a single function).
- **Verdicts:** `ok` (200, no compile, p95 and first call under 1 s), `COMPILES` (the first call compiled one or more kernels), `SLOW` and `ERROR` (none this time: every built payload
  answered 200 and none reached the one-second deadline).
- Payloads are test-size (a year of daily returns, a handful of scenarios). A real caller can send more; the lane bounds that with a body-size cap, an array-length cap and the one-second deadline,
  not with this table.

## Result

| Domain | ok | COMPILES | measured |
| --- | --- | --- | --- |
| alm | 24 | 1 | 25 |
| credit-risk | 27 | 11 | 38 |
| derivatives | 36 | 15 | 51 |
| liquidity | 11 | 1 | 12 |
| market-risk | 40 | 9 | 49 |
| operational | 26 | 4 | 30 |
| portfolio | 23 | 14 | 37 |
| regulatory | 18 | 0 | 18 |
| **all** | **205** | **55** | **260** |

1. **205 functions are `ok`.** Their p95 has a median of 2.5 ms; 201 of them cost one unit (50 ms or less). The slowest are
   `derivatives/cox_ingersoll_ross_model` (350 ms, 7 units), `portfolio/resampled_efficient_frontier` (131 ms, 3 units), `derivatives/nelson_siegel_svensson_curve` (108 ms, 3 units), `operational/scenario_analysis_oprisk` (99 ms, 2 units). All are far below the one-second deadline.
2. **55 functions `COMPILES`** (1 to 13 kernels in the first call). Warm they are as fast as the others; in a fresh task the first call is slower than one that compiles nothing by up to
   2219 ms (median 218 ms; 35 of 55 under 300 ms). The image pre-bakes one kernel and the lifespan warms one, so the fix is
   the same for all of them: bake the kernels' cache in the image build and warm them at start-up. Until then they stay off the whitelist.
3. **The flagships** (14 of the 26 below are `ok` today, the rest compile): parametric, Cornish-Fisher, marginal and component VaR, Monte Carlo and FRTB expected shortfall, extreme-value VaR,
   Kupiec, Christoffersen and the traffic-light backtest are `ok`. Historical-simulation VaR and expected shortfall, filtered historical simulation, the GARCH family, Sharpe, Sortino,
   maximum drawdown and risk parity compile kernels on the first call (about 55 to 725 ms more than a function that compiles nothing), which is what makes the baking worth doing.
4. **The first call of a function that compiles nothing still takes 357 ms (median of the `ok` rows) in a fresh process.** That is the one-time per-process cost of the first request
   through the stack, shared by every route, not a property of the function. A running task has paid it already.
5. **Not measured:** 125 functions. Their parameter names are not in the fixtures; adding a name to `fixture_values()` or an entry to `body_overrides()` brings a function in.

## The flagships

| Route | Verdict | First (ms) | Comp | p95 (ms) |
| --- | --- | --- | --- | --- |
| market-risk/historical_simulation_var | COMPILES | 518.6 | 3 | 2.5 |
| market-risk/parametric_delta_normal_var | ok | 447.0 | 0 | 2.1 |
| market-risk/cornish_fisher_var | ok | 357.8 | 0 | 5.9 |
| market-risk/filtered_historical_simulation_var | COMPILES | 756.4 | 4 | 2.0 |
| market-risk/marginal_var | ok | 333.0 | 0 | 4.3 |
| market-risk/component_var | ok | 349.8 | 0 | 2.0 |
| market-risk/historical_expected_shortfall | COMPILES | 606.8 | 3 | 2.1 |
| market-risk/conditional_var_es | COMPILES | 542.9 | 3 | 2.0 |
| market-risk/monte_carlo_expected_shortfall | ok | 454.6 | 0 | 6.3 |
| market-risk/stressed_expected_shortfall | COMPILES | 486.2 | 3 | 2.1 |
| market-risk/frtb_ima_expected_shortfall | ok | 373.5 | 0 | 2.7 |
| market-risk/extreme_value_theory_var | ok | 376.8 | 0 | 24.3 |
| market-risk/compute_cvar | ok | 322.8 | 0 | 2.1 |
| market-risk/kupiec_pof_test | ok | 366.5 | 0 | 2.3 |
| market-risk/christoffersen_independence_test | ok | 353.4 | 0 | 2.5 |
| market-risk/traffic_light_backtesting | ok | 447.0 | 0 | 2.3 |
| market-risk/garch_11_volatility_forecast | COMPILES | 466.7 | 2 | 2.8 |
| market-risk/egarch_volatility_model | COMPILES | 563.9 | 2 | 2.2 |
| market-risk/gjr_garch_asymmetric_model | COMPILES | 462.6 | 2 | 2.3 |
| market-risk/dcc_garch_dynamic_correlation | ok | 313.3 | 0 | 4.0 |
| portfolio/sharpe_ratio | COMPILES | 471.9 | 2 | 2.5 |
| portfolio/sortino_ratio | COMPILES | 412.7 | 1 | 3.2 |
| portfolio/maximum_drawdown | COMPILES | 608.0 | 2 | 2.4 |
| portfolio/portfolio_beta | ok | 388.6 | 0 | 3.0 |
| portfolio/risk_parity_portfolio | COMPILES | 1081.7 | 7 | 5.0 |
| portfolio/maximum_sharpe_ratio_portfolio | ok | 315.8 | 0 | 4.0 |

## For PR 1

Whitelist v1 = the `ok` rows, reviewed by the owner for product reasons (205 is more than a first-use experience needs; 20 to 30 spread across the eight domains and led by the flagships above
is probably enough), plus the compiling functions once their kernels are baked and warmed. The whitelist is a set of paths in code, reviewed like any other; a function missing from it is simply refused.

## All 260 rows (ms; first = first call in a fresh process; comp = kernels compiled by it; units = ceil(p95 / 50))

| Route | Verdict | First | Comp | p50 | p95 | Max | Units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| derivatives/cox_ingersoll_ross_model | ok | 661.3 | 0 | 292.4 | 349.8 | 553.0 | 7 |
| portfolio/resampled_efficient_frontier | ok | 397.7 | 0 | 87.9 | 131.3 | 147.4 | 3 |
| derivatives/nelson_siegel_svensson_curve | ok | 453.4 | 0 | 67.3 | 107.7 | 131.4 | 3 |
| operational/scenario_analysis_oprisk | ok | 403.7 | 0 | 92.9 | 98.7 | 126.3 | 2 |
| derivatives/nelson_siegel_curve_fit | ok | 440.4 | 0 | 32.1 | 43.1 | 43.2 | 1 |
| market-risk/extreme_value_theory_var | ok | 376.8 | 0 | 18.5 | 24.3 | 25.1 | 1 |
| market-risk/monte_carlo_expected_shortfall | ok | 454.6 | 0 | 5.8 | 6.3 | 6.4 | 1 |
| market-risk/correlation_matrix_historical | ok | 326.8 | 0 | 5.5 | 6.3 | 6.9 | 1 |
| market-risk/cornish_fisher_var | ok | 357.8 | 0 | 3.0 | 5.9 | 10.9 | 1 |
| market-risk/macro_scenario_generator | ok | 408.4 | 0 | 4.9 | 5.8 | 181.1 | 1 |
| derivatives/heston_stochastic_volatility_model | ok | 331.1 | 0 | 5.2 | 5.5 | 5.9 | 1 |
| portfolio/carhart_4_factor_model | ok | 339.0 | 0 | 4.9 | 5.0 | 5.1 | 1 |
| portfolio/correlation_matrix_portfolio | ok | 360.2 | 0 | 3.9 | 4.9 | 5.8 | 1 |
| derivatives/convertible_bond_pricer | ok | 318.9 | 0 | 2.5 | 4.9 | 5.0 | 1 |
| alm/nii_sensitivity_rate_shock | ok | 505.0 | 0 | 2.3 | 4.8 | 6.3 | 1 |
| regulatory/frtb_pl_attribution_test | ok | 347.7 | 0 | 4.5 | 4.8 | 4.8 | 1 |
| portfolio/robust_portfolio_optimisation | ok | 360.8 | 0 | 4.1 | 4.5 | 4.9 | 1 |
| derivatives/black_scholes_greeks | ok | 358.1 | 0 | 2.5 | 4.3 | 9.8 | 1 |
| portfolio/mean_variance_optimisation | ok | 315.5 | 0 | 3.9 | 4.3 | 4.4 | 1 |
| market-risk/marginal_var | ok | 333.0 | 0 | 1.8 | 4.3 | 9.2 | 1 |
| alm/eve_sensitivity_analysis | ok | 334.2 | 0 | 3.6 | 4.0 | 4.1 | 1 |
| market-risk/dcc_garch_dynamic_correlation | ok | 313.3 | 0 | 3.9 | 4.0 | 4.4 | 1 |
| alm/alm_stress_test | ok | 469.6 | 0 | 2.6 | 4.0 | 4.0 | 1 |
| portfolio/maximum_sharpe_ratio_portfolio | ok | 315.8 | 0 | 3.4 | 4.0 | 4.1 | 1 |
| alm/ftp_curve_construction | ok | 363.8 | 0 | 3.6 | 4.0 | 4.1 | 1 |
| derivatives/compound_option_pricer | ok | 366.0 | 0 | 3.7 | 4.0 | 4.0 | 1 |
| alm/funds_transfer_pricing_ftp | ok | 375.7 | 0 | 3.7 | 3.9 | 4.0 | 1 |
| derivatives/inflation_linked_bond_pricer | ok | 357.5 | 0 | 3.6 | 3.9 | 4.0 | 1 |
| market-risk/pnl_attribution_test_frtb_pat | ok | 506.4 | 0 | 3.6 | 3.9 | 4.0 | 1 |
| portfolio/correlation_clustering | ok | 333.4 | 0 | 3.6 | 3.9 | 4.1 | 1 |
| alm/irrbb_standardised_framework | ok | 323.7 | 0 | 3.4 | 3.9 | 3.9 | 1 |
| derivatives/interest_rate_swap_irs_pricer | ok | 336.0 | 0 | 3.4 | 3.8 | 3.9 | 1 |
| portfolio/minimum_variance_portfolio | ok | 337.3 | 0 | 3.5 | 3.8 | 3.9 | 1 |
| portfolio/fama_french_5_factor_model | ok | 385.8 | 0 | 3.7 | 3.8 | 3.9 | 1 |
| portfolio/principal_component_analysis | ok | 340.2 | 0 | 3.3 | 3.8 | 4.2 | 1 |
| derivatives/credit_default_swap_cds_pricer | ok | 362.3 | 0 | 3.4 | 3.7 | 3.7 | 1 |
| portfolio/fama_french_3_factor_model | ok | 318.5 | 0 | 3.4 | 3.6 | 3.9 | 1 |
| alm/interest_rate_risk_capital_irrbb | ok | 394.9 | 0 | 3.2 | 3.6 | 3.8 | 1 |
| derivatives/digital_option_pricer | ok | 341.5 | 0 | 3.3 | 3.6 | 3.7 | 1 |
| portfolio/tail_ratio | ok | 415.8 | 0 | 3.3 | 3.6 | 3.7 | 1 |
| alm/macaulay_duration_balance_sheet | ok | 322.5 | 0 | 3.3 | 3.6 | 3.7 | 1 |
| alm/loan_prepayment_rate_cpr | ok | 318.1 | 0 | 3.3 | 3.6 | 3.7 | 1 |
| derivatives/spread_option_kirk_approximation | ok | 403.1 | 0 | 2.5 | 3.6 | 5.4 | 1 |
| derivatives/black_scholes_european_option | ok | 334.3 | 0 | 2.5 | 3.6 | 4.4 | 1 |
| alm/duration_gap_analysis | ok | 328.4 | 0 | 2.7 | 3.5 | 3.9 | 1 |
| alm/liquidity_adjusted_nii | ok | 316.1 | 0 | 3.2 | 3.5 | 3.6 | 1 |
| alm/effective_duration_alm | ok | 517.5 | 0 | 3.2 | 3.5 | 3.7 | 1 |
| alm/nii_simulation_baseline | ok | 473.0 | 0 | 3.1 | 3.5 | 5.2 | 1 |
| regulatory/mifid_ii_post_trade_transparency | ok | 433.2 | 0 | 3.1 | 3.4 | 3.5 | 1 |
| alm/pipeline_risk_measurement | ok | 403.1 | 0 | 3.2 | 3.4 | 3.5 | 1 |
| credit-risk/expected_positive_exposure_epe | ok | 342.7 | 0 | 2.4 | 3.4 | 4.8 | 1 |
| alm/option_risk_irrbb | ok | 411.1 | 0 | 3.1 | 3.4 | 3.5 | 1 |
| regulatory/frtb_sa_market_risk_capital | ok | 411.1 | 0 | 3.1 | 3.4 | 3.5 | 1 |
| alm/nii_simulation_stress | ok | 353.5 | 0 | 3.2 | 3.4 | 3.5 | 1 |
| derivatives/overnight_index_swap_ois | ok | 353.5 | 0 | 3.2 | 3.4 | 3.5 | 1 |
| derivatives/total_return_swap_trs | ok | 373.0 | 0 | 2.3 | 3.4 | 3.6 | 1 |
| alm/static_gap_analysis | ok | 581.5 | 0 | 2.6 | 3.4 | 3.8 | 1 |
| portfolio/omega_ratio | ok | 372.0 | 0 | 2.3 | 3.3 | 7.1 | 1 |
| credit-risk/altman_z_score_credit_scoring | ok | 449.2 | 0 | 2.0 | 3.3 | 4.2 | 1 |
| regulatory/mifid_ii_pre_trade_transparency | ok | 335.4 | 0 | 3.0 | 3.3 | 3.4 | 1 |
| market-risk/var_fan_chart | ok | 336.2 | 0 | 2.4 | 3.3 | 4.3 | 1 |
| portfolio/residual_risk | ok | 330.0 | 0 | 2.7 | 3.2 | 3.5 | 1 |
| portfolio/calmar_ratio | ok | 315.6 | 0 | 3.0 | 3.2 | 3.3 | 1 |
| regulatory/pillar_2b_stress_buffer | ok | 378.8 | 0 | 2.9 | 3.2 | 3.3 | 1 |
| derivatives/barrier_option_pricer | ok | 365.3 | 0 | 2.8 | 3.2 | 3.3 | 1 |
| alm/core_deposit_duration | ok | 335.6 | 0 | 2.4 | 3.2 | 4.1 | 1 |
| regulatory/basel_iii_tier1_ratio | ok | 327.0 | 0 | 2.8 | 3.1 | 3.4 | 1 |
| credit-risk/credit_var_analytical_vasicek | ok | 406.5 | 0 | 2.8 | 3.1 | 3.2 | 1 |
| alm/repricing_gap_analysis | ok | 395.3 | 0 | 2.5 | 3.1 | 3.2 | 1 |
| derivatives/convexity | ok | 342.7 | 0 | 2.3 | 3.1 | 3.2 | 1 |
| portfolio/portfolio_beta | ok | 388.6 | 0 | 2.7 | 3.0 | 8.0 | 1 |
| operational/regulatory_compliance_score | ok | 324.2 | 0 | 2.7 | 3.0 | 4.1 | 1 |
| regulatory/basel_iii_leverage_ratio | ok | 339.0 | 0 | 2.7 | 3.0 | 3.1 | 1 |
| market-risk/risk_factor_pca_decomposition | ok | 311.8 | 0 | 2.9 | 3.0 | 3.0 | 1 |
| operational/risk_appetite_statement_oprisk | ok | 340.0 | 0 | 2.6 | 2.9 | 2.9 | 1 |
| regulatory/basel_iii_cet1_ratio | ok | 356.5 | 0 | 2.7 | 2.9 | 3.0 | 1 |
| derivatives/swaption_pricer_sabr | ok | 327.4 | 0 | 2.6 | 2.9 | 3.4 | 1 |
| regulatory/ucits_kiid_risk_indicator | ok | 397.6 | 0 | 2.5 | 2.9 | 3.2 | 1 |
| derivatives/swaption_pricer_black | ok | 318.8 | 0 | 2.6 | 2.9 | 2.9 | 1 |
| credit-risk/credit_stress_testing | ok | 489.6 | 0 | 1.9 | 2.9 | 5.8 | 1 |
| derivatives/chooser_option_pricer | ok | 404.3 | 0 | 2.6 | 2.9 | 2.9 | 1 |
| derivatives/caplet_floorlet_pricer_black | ok | 355.4 | 0 | 2.5 | 2.8 | 2.9 | 1 |
| derivatives/fx_option_pricer_garman_kohlhagen | ok | 484.6 | 0 | 2.6 | 2.8 | 2.8 | 1 |
| portfolio/tracking_error | ok | 394.8 | 0 | 2.6 | 2.8 | 2.9 | 1 |
| portfolio/treynor_ratio | ok | 325.0 | 0 | 2.6 | 2.8 | 2.9 | 1 |
| derivatives/displaced_diffusion_model | ok | 419.1 | 0 | 2.5 | 2.7 | 2.8 | 1 |
| credit-risk/effective_epe_regulatory | ok | 341.1 | 0 | 2.4 | 2.7 | 2.9 | 1 |
| derivatives/yield_to_maturity | ok | 350.2 | 0 | 2.4 | 2.7 | 3.3 | 1 |
| regulatory/frtb_ima_market_risk_capital | ok | 351.5 | 0 | 2.1 | 2.7 | 2.8 | 1 |
| market-risk/combined_backtesting | ok | 347.3 | 0 | 2.4 | 2.7 | 2.8 | 1 |
| derivatives/sabr_volatility_model | ok | 351.8 | 0 | 2.3 | 2.7 | 2.8 | 1 |
| alm/behavioural_modelling_nmds | ok | 436.2 | 0 | 2.3 | 2.7 | 2.9 | 1 |
| portfolio/jensens_alpha | ok | 354.7 | 0 | 2.5 | 2.7 | 2.8 | 1 |
| market-risk/frtb_ima_expected_shortfall | ok | 373.5 | 0 | 2.5 | 2.7 | 2.8 | 1 |
| alm/modified_duration_balance_sheet | ok | 403.9 | 0 | 2.3 | 2.7 | 3.5 | 1 |
| alm/irrbb_six_standard_rate_shocks | ok | 413.6 | 0 | 2.4 | 2.7 | 2.8 | 1 |
| market-risk/frtb_ima_stressed_period_finder | ok | 360.2 | 0 | 2.3 | 2.7 | 2.8 | 1 |
| derivatives/yield_to_call | ok | 378.9 | 0 | 2.3 | 2.6 | 2.9 | 1 |
| credit-risk/current_exposure_method_cem | ok | 333.0 | 0 | 2.3 | 2.6 | 2.6 | 1 |
| derivatives/swap_rate_curve | ok | 361.6 | 0 | 2.3 | 2.5 | 2.6 | 1 |
| alm/balance_sheet_projection_model | ok | 379.2 | 0 | 2.3 | 2.5 | 2.6 | 1 |
| market-risk/compute_rolling_var | ok | 334.8 | 0 | 2.3 | 2.5 | 2.6 | 1 |
| regulatory/srep_capital_add_on | ok | 442.5 | 0 | 2.2 | 2.5 | 2.6 | 1 |
| market-risk/volga_vega_convexity | ok | 347.8 | 0 | 1.9 | 2.5 | 2.8 | 1 |
| derivatives/duration_macaulay | ok | 524.3 | 0 | 2.2 | 2.5 | 2.9 | 1 |
| alm/convexity_gap | ok | 323.8 | 0 | 2.2 | 2.5 | 2.6 | 1 |
| derivatives/dv01_pvbp | ok | 318.4 | 0 | 2.3 | 2.5 | 2.8 | 1 |
| derivatives/modified_duration | ok | 371.2 | 0 | 2.2 | 2.5 | 2.6 | 1 |
| derivatives/fx_forward_pricer | ok | 505.1 | 0 | 2.2 | 2.5 | 2.5 | 1 |
| derivatives/bond_pricer_fixed_coupon | ok | 489.8 | 0 | 2.1 | 2.5 | 3.0 | 1 |
| credit-risk/downturn_lgd_adjustment | ok | 495.2 | 0 | 2.2 | 2.5 | 2.6 | 1 |
| market-risk/christoffersen_independence_test | ok | 353.4 | 0 | 2.2 | 2.5 | 2.5 | 1 |
| credit-risk/point_in_time_pd_estimation | ok | 597.7 | 0 | 2.1 | 2.4 | 2.6 | 1 |
| market-risk/rolling_var_backtest | ok | 349.0 | 0 | 2.2 | 2.4 | 2.9 | 1 |
| derivatives/forward_rate_agreement_fra | ok | 344.2 | 0 | 2.2 | 2.4 | 2.6 | 1 |
| derivatives/equity_swap_pricer | ok | 543.2 | 0 | 2.2 | 2.4 | 2.4 | 1 |
| derivatives/zero_coupon_bond_pricer | ok | 329.3 | 0 | 2.2 | 2.4 | 2.4 | 1 |
| market-risk/frtb_ima_aggregate_capital_charge | ok | 376.1 | 0 | 2.1 | 2.4 | 2.4 | 1 |
| credit-risk/sovereign_credit_risk_assessment | ok | 328.5 | 0 | 1.8 | 2.4 | 3.0 | 1 |
| regulatory/capital_conservation_buffer | ok | 328.6 | 0 | 2.1 | 2.4 | 2.5 | 1 |
| market-risk/vega_pnl_attribution | ok | 349.9 | 0 | 1.6 | 2.4 | 2.6 | 1 |
| credit-risk/cds_spread_to_pd_conversion | ok | 434.2 | 0 | 1.8 | 2.4 | 2.5 | 1 |
| market-risk/kupiec_pof_test | ok | 366.5 | 0 | 2.0 | 2.3 | 2.4 | 1 |
| derivatives/effective_duration | ok | 343.6 | 0 | 2.2 | 2.3 | 2.4 | 1 |
| credit-risk/through_the_cycle_pd_adjustment | ok | 400.1 | 0 | 2.1 | 2.3 | 2.4 | 1 |
| operational/severity_distribution_fitting | ok | 328.3 | 0 | 2.0 | 2.3 | 2.7 | 1 |
| regulatory/basel_iv_output_floor | ok | 336.5 | 0 | 2.0 | 2.3 | 2.5 | 1 |
| market-risk/spectral_risk_measure | ok | 418.7 | 0 | 2.1 | 2.3 | 2.6 | 1 |
| regulatory/basel_iii_total_capital_ratio | ok | 439.8 | 0 | 2.0 | 2.3 | 2.4 | 1 |
| regulatory/aifmd_risk_metrics | ok | 340.5 | 0 | 2.1 | 2.3 | 2.6 | 1 |
| portfolio/active_share | ok | 336.8 | 0 | 2.0 | 2.3 | 2.3 | 1 |
| portfolio/diversification_ratio | ok | 319.0 | 0 | 2.1 | 2.3 | 2.3 | 1 |
| regulatory/crr2_large_exposure_limit | ok | 328.9 | 0 | 2.0 | 2.3 | 2.4 | 1 |
| portfolio/concentration_risk_hhi | ok | 372.0 | 0 | 2.1 | 2.3 | 2.4 | 1 |
| credit-risk/exposure_at_default_ead_calculator | ok | 425.9 | 0 | 2.1 | 2.3 | 2.4 | 1 |
| market-risk/traffic_light_backtesting | ok | 447.0 | 0 | 2.0 | 2.3 | 2.3 | 1 |
| regulatory/emir_margin_requirement | ok | 453.2 | 0 | 2.0 | 2.2 | 2.4 | 1 |
| market-risk/theta_time_decay | ok | 338.1 | 0 | 1.9 | 2.2 | 2.2 | 1 |
| market-risk/var_breach_cluster_analysis | ok | 314.6 | 0 | 2.0 | 2.2 | 2.2 | 1 |
| regulatory/combined_buffer_requirement | ok | 327.6 | 0 | 2.0 | 2.2 | 2.4 | 1 |
| operational/scenario_severity_estimation | ok | 332.7 | 0 | 2.0 | 2.2 | 2.2 | 1 |
| credit-risk/kmv_merton_distance_to_default | ok | 535.5 | 0 | 1.9 | 2.2 | 2.2 | 1 |
| market-risk/realised_volatility | ok | 447.9 | 0 | 1.9 | 2.1 | 2.2 | 1 |
| credit-risk/credit_default_swap_var | ok | 388.7 | 0 | 1.9 | 2.1 | 2.3 | 1 |
| market-risk/cvar_decomposition_euler | ok | 342.5 | 0 | 1.9 | 2.1 | 2.2 | 1 |
| liquidity/hqla_level_2a_asset_classifier | ok | 344.2 | 0 | 1.8 | 2.1 | 2.2 | 1 |
| market-risk/charm_delta_decay | ok | 347.0 | 0 | 1.9 | 2.1 | 2.2 | 1 |
| liquidity/hqla_level_2b_asset_classifier | ok | 328.9 | 0 | 1.9 | 2.1 | 2.1 | 1 |
| liquidity/cross_currency_liquidity_bridge | ok | 345.1 | 0 | 1.9 | 2.1 | 2.1 | 1 |
| liquidity/hqla_level_1_asset_classifier | ok | 385.3 | 0 | 1.9 | 2.1 | 2.2 | 1 |
| operational/rcsa_residual_risk_scoring | ok | 318.7 | 0 | 1.7 | 2.1 | 2.7 | 1 |
| liquidity/ilaap_internal_liquidity_metric | ok | 329.3 | 0 | 1.9 | 2.1 | 2.1 | 1 |
| operational/business_continuity_risk_score | ok | 392.2 | 0 | 1.8 | 2.1 | 2.5 | 1 |
| credit-risk/funding_valuation_adjustment_fva | ok | 456.2 | 0 | 1.9 | 2.1 | 2.5 | 1 |
| operational/frequency_distribution_fitting | ok | 328.8 | 0 | 1.9 | 2.1 | 2.1 | 1 |
| operational/cyber_risk_loss_estimation | ok | 331.5 | 0 | 1.8 | 2.1 | 2.3 | 1 |
| operational/tail_risk_scenario_oprisk | ok | 349.3 | 0 | 1.9 | 2.1 | 2.2 | 1 |
| liquidity/liquidity_transfer_pricing | ok | 315.5 | 0 | 1.8 | 2.1 | 2.2 | 1 |
| operational/audit_finding_risk_scorer | ok | 432.2 | 0 | 1.8 | 2.1 | 2.1 | 1 |
| liquidity/asset_encumbrance_ratio | ok | 381.6 | 0 | 1.8 | 2.1 | 2.1 | 1 |
| market-risk/parametric_delta_normal_var | ok | 447.0 | 0 | 1.8 | 2.1 | 2.1 | 1 |
| credit-risk/credit_concentration_risk_hhi | ok | 584.1 | 0 | 1.8 | 2.1 | 2.2 | 1 |
| operational/operational_var_opvar | ok | 354.4 | 0 | 1.9 | 2.1 | 2.3 | 1 |
| market-risk/compute_cvar | ok | 322.8 | 0 | 1.9 | 2.1 | 2.1 | 1 |
| operational/conduct_risk_metric | ok | 318.0 | 0 | 1.8 | 2.1 | 2.1 | 1 |
| liquidity/liquidity_risk_appetite_threshold | ok | 313.6 | 0 | 1.9 | 2.0 | 2.1 | 1 |
| market-risk/incremental_var | ok | 365.6 | 0 | 1.9 | 2.0 | 2.1 | 1 |
| market-risk/component_var | ok | 349.8 | 0 | 1.8 | 2.0 | 2.2 | 1 |
| portfolio/equal_weight_portfolio | ok | 314.7 | 0 | 1.8 | 2.0 | 2.1 | 1 |
| operational/third_party_vendor_risk | ok | 310.8 | 0 | 1.8 | 2.0 | 2.5 | 1 |
| market-risk/compute_loss_percentiles | ok | 337.0 | 0 | 1.8 | 2.0 | 2.1 | 1 |
| operational/scenario_frequency_estimation | ok | 464.1 | 0 | 1.8 | 2.0 | 2.1 | 1 |
| market-risk/vanna_delta_vega_cross | ok | 391.8 | 0 | 1.8 | 2.0 | 2.0 | 1 |
| operational/model_risk_assessment | ok | 345.4 | 0 | 1.8 | 2.0 | 2.1 | 1 |
| credit-risk/recovery_rate_estimation | ok | 615.2 | 0 | 1.8 | 2.0 | 2.0 | 1 |
| operational/it_risk_scoring | ok | 316.1 | 0 | 1.8 | 2.0 | 2.0 | 1 |
| operational/kri_threshold_breach_detection | ok | 393.8 | 0 | 1.7 | 2.0 | 2.0 | 1 |
| credit-risk/loss_given_default_lgd_model | ok | 644.0 | 0 | 1.8 | 2.0 | 2.1 | 1 |
| operational/oprisk_stress_testing | ok | 362.5 | 0 | 1.7 | 2.0 | 2.0 | 1 |
| liquidity/idiosyncratic_stress_scenario | ok | 337.9 | 0 | 1.8 | 2.0 | 2.0 | 1 |
| credit-risk/basel_standardised_approach_rwa | ok | 318.1 | 0 | 1.6 | 2.0 | 2.2 | 1 |
| operational/loss_event_classification_basel | ok | 353.2 | 0 | 1.8 | 2.0 | 2.1 | 1 |
| liquidity/liquidity_coverage_ratio_lcr | ok | 346.3 | 0 | 1.8 | 2.0 | 2.0 | 1 |
| market-risk/greeks_based_pnl_explain | ok | 420.9 | 0 | 1.7 | 2.0 | 2.1 | 1 |
| market-risk/rho_interest_rate | ok | 454.1 | 0 | 1.7 | 2.0 | 2.0 | 1 |
| credit-risk/ifrs_9_12_month_ecl_stage_1 | ok | 358.4 | 0 | 1.7 | 2.0 | 2.0 | 1 |
| liquidity/net_stable_funding_ratio_nsfr | ok | 346.0 | 0 | 1.8 | 2.0 | 2.0 | 1 |
| operational/control_testing_effectiveness | ok | 368.2 | 0 | 1.8 | 2.0 | 2.0 | 1 |
| operational/basel_standardised_measurement_sma | ok | 343.6 | 0 | 1.7 | 1.9 | 2.1 | 1 |
| market-risk/theta_carry_attribution | ok | 396.1 | 0 | 1.6 | 1.9 | 2.1 | 1 |
| operational/insurance_offset_calculation | ok | 336.1 | 0 | 1.7 | 1.9 | 2.0 | 1 |
| operational/rcsa_control_effectiveness | ok | 389.7 | 0 | 1.8 | 1.9 | 2.0 | 1 |
| credit-risk/ifrs_9_staging_criteria_assessment | ok | 445.5 | 0 | 1.7 | 1.9 | 2.0 | 1 |
| operational/oprisk_economic_capital | ok | 311.8 | 0 | 1.7 | 1.9 | 2.0 | 1 |
| operational/rcsa_inherent_risk_scoring | ok | 401.7 | 0 | 1.7 | 1.9 | 1.9 | 1 |
| credit-risk/ifrs_9_stage_classification_pd_threshold | ok | 430.1 | 0 | 1.7 | 1.9 | 1.9 | 1 |
| market-risk/cs01_credit_spread | ok | 351.0 | 0 | 1.7 | 1.9 | 1.9 | 1 |
| credit-risk/xva_aggregation | ok | 376.6 | 0 | 1.7 | 1.9 | 1.9 | 1 |
| credit-risk/wrong_way_risk_adjustment | ok | 372.4 | 0 | 1.7 | 1.9 | 1.9 | 1 |
| market-risk/gamma_pnl_attribution | ok | 335.5 | 0 | 1.5 | 1.9 | 2.1 | 1 |
| market-risk/basel_capital_addon_multiplier | ok | 362.6 | 0 | 1.6 | 1.9 | 1.9 | 1 |
| credit-risk/standardised_approach_ccr_sa_ccr | ok | 314.7 | 0 | 1.6 | 1.8 | 1.9 | 1 |
| credit-risk/counterparty_credit_risk_ccr_exposure | ok | 391.0 | 0 | 1.6 | 1.8 | 2.0 | 1 |
| market-risk/reverse_stress_testing | ok | 415.3 | 0 | 1.6 | 1.8 | 1.8 | 1 |
| credit-risk/collateral_haircut_calculation | ok | 423.9 | 0 | 1.6 | 1.8 | 1.9 | 1 |
| derivatives/american_option_lsm | COMPILES | 1068.1 | 2 | 429.2 | 484.9 | 576.6 | 10 |
| derivatives/asian_option_pricer | COMPILES | 1473.7 | 2 | 210.8 | 236.4 | 262.7 | 5 |
| derivatives/lookback_option_pricer | COMPILES | 1264.3 | 2 | 185.8 | 231.5 | 238.2 | 5 |
| derivatives/bermudan_option_pricer | COMPILES | 685.6 | 2 | 150.0 | 179.6 | 185.5 | 4 |
| derivatives/rough_volatility_rbergomi_model | COMPILES | 1799.6 | 6 | 98.1 | 108.0 | 116.1 | 3 |
| derivatives/vasicek_interest_rate_model | COMPILES | 849.3 | 2 | 89.1 | 107.9 | 111.2 | 3 |
| derivatives/hull_white_short_rate_model | COMPILES | 887.4 | 2 | 87.1 | 106.7 | 113.4 | 3 |
| portfolio/monte_carlo_portfolio_simulation | COMPILES | 538.3 | 2 | 8.6 | 20.3 | 27.3 | 1 |
| operational/advanced_measurement_approach_ama | COMPILES | 521.0 | 3 | 15.4 | 19.1 | 19.6 | 1 |
| operational/loss_distribution_approach_lda | COMPILES | 518.2 | 3 | 14.8 | 15.7 | 16.0 | 1 |
| derivatives/normal_inverse_gaussian_model | COMPILES | 1031.4 | 2 | 8.0 | 9.2 | 12.5 | 1 |
| credit-risk/credit_var_monte_carlo | COMPILES | 1448.4 | 6 | 6.7 | 8.5 | 13.2 | 1 |
| operational/monte_carlo_oprisk_capital | COMPILES | 560.6 | 3 | 8.1 | 8.4 | 8.4 | 1 |
| derivatives/variance_gamma_model | COMPILES | 912.1 | 2 | 6.7 | 7.4 | 7.7 | 1 |
| credit-risk/potential_future_exposure_pfe | COMPILES | 2576.6 | 13 | 6.9 | 7.2 | 7.2 | 1 |
| operational/compound_loss_distribution | COMPILES | 600.2 | 3 | 5.8 | 6.0 | 6.0 | 1 |
| portfolio/risk_parity_portfolio | COMPILES | 1081.7 | 7 | 4.0 | 5.0 | 5.1 | 1 |
| credit-risk/creditmetrics_portfolio_model | COMPILES | 1575.1 | 6 | 4.3 | 4.9 | 8.6 | 1 |
| liquidity/liquidity_var_liqvar | COMPILES | 646.2 | 2 | 4.4 | 4.7 | 4.7 | 1 |
| derivatives/monte_carlo_option_pricer | COMPILES | 1022.5 | 2 | 3.4 | 4.2 | 4.4 | 1 |
| portfolio/average_drawdown | COMPILES | 456.4 | 2 | 3.1 | 3.5 | 5.2 | 1 |
| derivatives/puttable_bond_pricer | COMPILES | 535.9 | 2 | 2.9 | 3.3 | 3.6 | 1 |
| derivatives/binomial_tree_option_pricer | COMPILES | 1163.3 | 2 | 2.9 | 3.3 | 3.7 | 1 |
| portfolio/sortino_ratio | COMPILES | 412.7 | 1 | 2.5 | 3.2 | 3.3 | 1 |
| portfolio/regime_detection_hmm | COMPILES | 915.6 | 2 | 2.7 | 3.2 | 4.1 | 1 |
| derivatives/oas_option_adjusted_spread | COMPILES | 525.2 | 2 | 2.9 | 3.1 | 3.2 | 1 |
| credit-risk/credit_valuation_adjustment_cva | COMPILES | 425.1 | 1 | 1.8 | 3.1 | 4.5 | 1 |
| credit-risk/expected_loss_el_computation | COMPILES | 575.4 | 1 | 2.1 | 3.0 | 3.3 | 1 |
| alm/prepayment_model_mortgages | COMPILES | 875.0 | 2 | 2.5 | 2.8 | 4.0 | 1 |
| market-risk/garch_11_volatility_forecast | COMPILES | 466.7 | 2 | 2.2 | 2.8 | 3.6 | 1 |
| credit-risk/cva_sensitivity_cva_greeks | COMPILES | 473.5 | 1 | 2.5 | 2.8 | 2.9 | 1 |
| derivatives/trinomial_tree_option_pricer | COMPILES | 839.7 | 2 | 2.4 | 2.7 | 3.1 | 1 |
| portfolio/information_ratio | COMPILES | 572.2 | 2 | 2.3 | 2.6 | 2.6 | 1 |
| portfolio/conditional_drawdown_at_risk | COMPILES | 553.9 | 2 | 2.3 | 2.6 | 2.6 | 1 |
| market-risk/historical_simulation_var | COMPILES | 518.6 | 3 | 2.2 | 2.5 | 2.6 | 1 |
| portfolio/sharpe_ratio | COMPILES | 471.9 | 2 | 2.3 | 2.5 | 2.5 | 1 |
| derivatives/callable_bond_pricer | COMPILES | 548.3 | 2 | 2.1 | 2.5 | 2.8 | 1 |
| portfolio/ulcer_index | COMPILES | 439.0 | 1 | 2.2 | 2.4 | 2.5 | 1 |
| portfolio/sector_attribution | COMPILES | 505.6 | 2 | 2.1 | 2.4 | 2.4 | 1 |
| portfolio/maximum_drawdown | COMPILES | 608.0 | 2 | 2.2 | 2.4 | 2.4 | 1 |
| portfolio/drawdown_duration | COMPILES | 499.1 | 2 | 2.1 | 2.4 | 2.4 | 1 |
| portfolio/marginal_contribution_to_risk | COMPILES | 1130.6 | 7 | 2.1 | 2.4 | 2.5 | 1 |
| portfolio/return_attribution_brinson | COMPILES | 525.6 | 2 | 2.1 | 2.3 | 2.4 | 1 |
| market-risk/gjr_garch_asymmetric_model | COMPILES | 462.6 | 2 | 2.0 | 2.3 | 2.5 | 1 |
| credit-risk/irb_foundation_approach_capital | COMPILES | 587.0 | 2 | 2.0 | 2.3 | 2.4 | 1 |
| credit-risk/irb_advanced_approach_capital | COMPILES | 638.4 | 2 | 2.0 | 2.2 | 2.2 | 1 |
| market-risk/egarch_volatility_model | COMPILES | 563.9 | 2 | 2.0 | 2.2 | 2.2 | 1 |
| market-risk/historical_expected_shortfall | COMPILES | 606.8 | 3 | 1.9 | 2.1 | 2.2 | 1 |
| market-risk/stressed_expected_shortfall | COMPILES | 486.2 | 3 | 1.8 | 2.1 | 2.1 | 1 |
| market-risk/filtered_historical_simulation_var | COMPILES | 756.4 | 4 | 1.8 | 2.0 | 2.2 | 1 |
| market-risk/conditional_var_es | COMPILES | 542.9 | 3 | 1.8 | 2.0 | 2.0 | 1 |
| market-risk/es_at_multiple_confidence_levels | COMPILES | 642.1 | 3 | 1.8 | 2.0 | 2.1 | 1 |
| credit-risk/unexpected_loss_ul_computation | COMPILES | 556.5 | 2 | 1.8 | 2.0 | 2.0 | 1 |
| credit-risk/sme_correlation_factor_basel | COMPILES | 481.8 | 1 | 1.7 | 1.9 | 2.0 | 1 |
| credit-risk/maturity_adjustment_basel_irb | COMPILES | 529.2 | 1 | 1.6 | 1.8 | 1.9 | 1 |

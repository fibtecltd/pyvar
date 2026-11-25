# Domain endpoint index

Every endpoint below is `POST /api/v1/<prefix>/<name>` and sits behind the compute rate limit (`main.py:217-234`). Names are the path strings declared on each router; a few of them are modelled on a regulatory framework or a textbook model, and the README warns that roughly a quarter of functions carry a `caveat` in `portal/functions.json` that should be read before relying on them (`README.md:259-264`). The general conventions, authentication and quotas are in [api-reference.md](api-reference.md).

Counts come from `docugen-src grep` over each router module and total 385: 71 + 55 + 62 + 40 + 44 + 50 + 30 + 33.

## market-risk (71)

Router `api/routes/market_risk.py:252`; declarations from line 268 to line 1912.

historical_simulation_var, filtered_historical_simulation_var, parametric_delta_normal_var, cornish_fisher_var, marginal_var, component_var, incremental_var, var_by_risk_factor, var_fan_chart, conditional_var_es, historical_expected_shortfall, monte_carlo_expected_shortfall, cvar_decomposition_euler, stressed_expected_shortfall, liquidity_adjusted_es, es_at_multiple_confidence_levels, expected_shortfall_contribution, historical_scenario_replay, hypothetical_multi_factor_scenario, reverse_stress_testing, sensitivity_stress_profile, sector_stress_scenario, macro_scenario_generator, contagion_stress_scenario, portfolio_delta_aggregated, gamma_cross_gamma_matrix, vega_surface_bucketed, dv01_pv01_bucketed, cs01_credit_spread, rho_interest_rate, theta_time_decay, charm_delta_decay, volga_vega_convexity, vanna_delta_vega_cross, greeks_based_pnl_explain, pnl_attribution_test_frtb_pat, theta_carry_attribution, gamma_pnl_attribution, vega_pnl_attribution, fx_pnl_attribution, rates_pnl_attribution, credit_pnl_attribution, residual_pnl_unexplained, traffic_light_backtesting, kupiec_pof_test, christoffersen_independence_test, combined_backtesting, basel_capital_addon_multiplier, rolling_var_backtest, var_breach_cluster_analysis, volatility_surface_implied_vol, garch_11_volatility_forecast, egarch_volatility_model, gjr_garch_asymmetric_model, realised_volatility, correlation_matrix_historical, dcc_garch_dynamic_correlation, risk_factor_pca_decomposition, frtb_sa_sensitivity_based_method, frtb_sa_default_risk_charge, frtb_sa_residual_risk_addon, frtb_ima_expected_shortfall, frtb_ima_stressed_period_finder, frtb_ima_non_modellable_risk_factors, frtb_ima_aggregate_capital_charge, extreme_value_theory_var, spectral_risk_measure, compute_cvar, compute_loss_percentiles, compute_rolling_var, compute_breaches.

## credit-risk (55)

Router `api/routes/credit_risk.py:216`; declarations from line 232 to line 1519.

probability_of_default_pd_estimation, loss_given_default_lgd_model, exposure_at_default_ead_calculator, expected_loss_el_computation, unexpected_loss_ul_computation, recovery_rate_estimation, downturn_lgd_adjustment, irb_foundation_approach_capital, irb_advanced_approach_capital, basel_standardised_approach_rwa, maturity_adjustment_basel_irb, sme_correlation_factor_basel, credit_var_monte_carlo, credit_var_analytical_vasicek, creditmetrics_portfolio_model, kmv_merton_distance_to_default, default_correlation_matrix, credit_concentration_risk_hhi, counterparty_credit_risk_ccr_exposure, current_exposure_method_cem, standardised_approach_ccr_sa_ccr, potential_future_exposure_pfe, expected_positive_exposure_epe, effective_epe_regulatory, collateral_haircut_calculation, credit_valuation_adjustment_cva, debt_valuation_adjustment_dva, funding_valuation_adjustment_fva, capital_valuation_adjustment_kva, margin_valuation_adjustment_mva, xva_aggregation, cva_sensitivity_cva_greeks, wrong_way_risk_adjustment, credit_spread_curve_bootstrap, cds_pricing_isda_standard, cds_spread_to_pd_conversion, credit_default_swap_var, ifrs_9_stage_classification_pd_threshold, ifrs_9_12_month_ecl_stage_1, ifrs_9_lifetime_ecl_stage_2_3, ifrs_9_scenario_weighted_ecl, macroeconomic_overlays_ecl, ifrs_9_staging_criteria_assessment, credit_portfolio_optimisation, credit_stress_testing, altman_z_score_credit_scoring, logistic_regression_pd_model, machine_learning_pd_calibration, through_the_cycle_pd_adjustment, point_in_time_pd_estimation, ratings_migration_matrix, retail_scorecard_pd_model, corporate_credit_scoring_model, sovereign_credit_risk_assessment, sector_default_rate_analysis.

## derivatives (62)

Router `api/routes/derivatives.py:223`; declarations from line 239 to line 1767.

black_scholes_european_option, black_scholes_greeks, binomial_tree_option_pricer, trinomial_tree_option_pricer, monte_carlo_option_pricer, digital_option_pricer, barrier_option_pricer, asian_option_pricer, lookback_option_pricer, american_option_lsm, bermudan_option_pricer, rainbow_option_pricer, basket_option_pricer, spread_option_kirk_approximation, compound_option_pricer, chooser_option_pricer, bond_pricer_fixed_coupon, bond_pricer_floating_rate, zero_coupon_bond_pricer, inflation_linked_bond_pricer, callable_bond_pricer, puttable_bond_pricer, convertible_bond_pricer, duration_macaulay, modified_duration, effective_duration, convexity, dv01_pvbp, yield_to_maturity, yield_to_call, z_spread_calculator, asset_swap_spread, oas_option_adjusted_spread, nelson_siegel_curve_fit, nelson_siegel_svensson_curve, bootstrap_yield_curve, swap_rate_curve, ois_curve_sonia_sofr, forward_rate_agreement_fra, interest_rate_swap_irs_pricer, cross_currency_swap_pricer, overnight_index_swap_ois, total_return_swap_trs, credit_default_swap_cds_pricer, equity_swap_pricer, caplet_floorlet_pricer_black, cap_floor_pricer, swaption_pricer_black, swaption_pricer_sabr, vasicek_interest_rate_model, cox_ingersoll_ross_model, hull_white_short_rate_model, lmm_bgm_rate_model, heston_stochastic_volatility_model, sabr_volatility_model, local_volatility_dupire_model, rough_volatility_rbergomi_model, variance_gamma_model, normal_inverse_gaussian_model, displaced_diffusion_model, fx_forward_pricer, fx_option_pricer_garman_kohlhagen.

## liquidity (40)

Router `api/routes/liquidity.py:185`; declarations from line 201 to line 1120.

liquidity_coverage_ratio_lcr, available_stable_funding_asf_calc, required_stable_funding_rsf_calc, net_stable_funding_ratio_nsfr, hqla_level_1_asset_classifier, hqla_level_2a_asset_classifier, hqla_level_2b_asset_classifier, cash_flow_ladder_30_day, cash_flow_ladder_1_year, liquidity_gap_analysis, funding_tenor_analysis, liquidity_stress_scenario, idiosyncratic_stress_scenario, market_wide_stress_scenario, combined_stress_scenario, survival_horizon_calculator, intraday_liquidity_monitor, intraday_liquidity_stress_test, ilaap_stress_testing_framework, liquidity_var_liqvar, liquidity_buffer_sizing, contingency_funding_plan_trigger, wholesale_funding_concentration, retail_deposit_runoff_rate, secured_funding_rollover_risk, asset_encumbrance_ratio, collateral_availability_analysis, repo_market_stress_haircut, fx_liquidity_risk_by_currency, intragroup_liquidity_flow, funding_cost_analysis, liquidity_transfer_pricing, ilaap_internal_liquidity_metric, liquidity_risk_appetite_threshold, early_warning_indicator_liquidity, central_bank_facility_eligibility, contingent_liquidity_risk, liquidity_scorecard_aggregation, deposit_stability_classification, cross_currency_liquidity_bridge.

## operational (44)

Router `api/routes/operational.py:169`; declarations from line 185 to line 1154.

frequency_distribution_fitting, severity_distribution_fitting, compound_loss_distribution, monte_carlo_oprisk_capital, operational_var_opvar, loss_distribution_approach_lda, advanced_measurement_approach_ama, basel_standardised_measurement_sma, oprisk_capital_allocation, diversification_benefit_oprisk, oprisk_economic_capital, insurance_offset_calculation, tail_risk_scenario_oprisk, oprisk_stress_testing, rcsa_risk_identification, rcsa_inherent_risk_scoring, rcsa_residual_risk_scoring, rcsa_control_effectiveness, control_testing_effectiveness, business_environment_factor_bei, internal_control_factor_icf, loss_event_classification_basel, loss_data_collection_framework, external_loss_data_integration, key_risk_indicator_kri_library, kri_threshold_breach_detection, kri_trend_analysis, scenario_frequency_estimation, scenario_severity_estimation, scenario_expert_elicitation_model, scenario_analysis_oprisk, cyber_risk_loss_estimation, conduct_risk_metric, model_risk_assessment, it_risk_scoring, third_party_vendor_risk, business_continuity_risk_score, near_miss_capture_framework, root_cause_analysis_template, risk_appetite_statement_oprisk, escalation_threshold_calculation, oprisk_heat_map_generator, regulatory_compliance_score, audit_finding_risk_scorer.

## portfolio (50)

Router `api/routes/portfolio.py:193`; declarations from line 209 to line 1407.

mean_variance_optimisation, minimum_variance_portfolio, maximum_sharpe_ratio_portfolio, risk_parity_portfolio, equal_weight_portfolio, black_litterman_model, resampled_efficient_frontier, robust_portfolio_optimisation, cvar_constrained_optimisation, factor_based_optimisation, sharpe_ratio, sortino_ratio, calmar_ratio, information_ratio, treynor_ratio, jensens_alpha, omega_ratio, tail_ratio, ulcer_index, maximum_drawdown, average_drawdown, drawdown_duration, conditional_drawdown_at_risk, return_attribution_brinson, factor_return_attribution, sector_attribution, currency_attribution, gics_sector_exposure, factor_exposure_analysis_barra, fama_french_3_factor_model, carhart_4_factor_model, fama_french_5_factor_model, principal_component_analysis, correlation_clustering, regime_detection_hmm, portfolio_beta, active_share, tracking_error, residual_risk, portfolio_turnover, transaction_cost_analysis, marginal_contribution_to_risk, diversification_ratio, correlation_matrix_portfolio, concentration_risk_hhi, liquidity_adjusted_portfolio_var, monte_carlo_portfolio_simulation, rebalancing_optimiser, esg_score_integration, carbon_footprint_attribution.

## regulatory (30)

Router `api/routes/regulatory.py:131`; declarations from line 147 to line 802.

basel_iii_cet1_ratio, basel_iii_tier1_ratio, basel_iii_total_capital_ratio, basel_iii_leverage_ratio, basel_iv_output_floor, icaap_capital_assessment, srep_capital_add_on, pillar_2a_capital, pillar_2b_stress_buffer, combined_buffer_requirement, capital_conservation_buffer, countercyclical_capital_buffer, crr2_large_exposure_limit, frtb_sa_market_risk_capital, frtb_ima_market_risk_capital, frtb_pl_attribution_test, frtb_trading_desk_aggregation, mifid_ii_transaction_report_validator, mifid_ii_pre_trade_transparency, mifid_ii_post_trade_transparency, mifid_ii_best_execution_metric, mifid_ii_algorithm_documentation, emir_trade_repository_report, emir_clearing_obligation_check, emir_margin_requirement, sftr_securities_finance_report, aifmd_risk_metrics, ucits_kiid_risk_indicator, solvency_ii_scr_market_risk, solvency_ii_scr_credit_risk.

## alm (33)

Router `api/routes/alm.py:128`; declarations from line 144 to line 909.

macaulay_duration_balance_sheet, modified_duration_balance_sheet, effective_duration_alm, duration_gap_analysis, convexity_gap, nii_sensitivity_rate_shock, nii_simulation_baseline, nii_simulation_stress, economic_value_of_equity_eve, eve_sensitivity_analysis, liquidity_adjusted_nii, irrbb_six_standard_rate_shocks, irrbb_standardised_framework, irrbb_internal_model, repricing_gap_analysis, repricing_maturity_profile, static_gap_analysis, dynamic_gap_analysis, basis_risk_irrbb, option_risk_irrbb, pipeline_risk_measurement, interest_rate_risk_capital_irrbb, asset_liability_mismatch_index, loan_prepayment_rate_cpr, prepayment_model_mortgages, behavioural_modelling_nmds, non_maturity_deposit_stability, core_deposit_duration, funds_transfer_pricing_ftp, ftp_curve_construction, structural_hedge_optimisation, alm_stress_test, balance_sheet_projection_model.

## Related endpoint outside these routers

`POST /api/v1/var/compute` is served by the separate VaR router and runs as a queued job rather than inline (`api/routes/var.py:179-331`). Counting it with the 385 domain endpoints gives the 386 that `api/middleware/rate_limit.py:14-18` mentions.

## Sources

main.py
README.md
api/routes/market_risk.py
api/routes/credit_risk.py
api/routes/derivatives.py
api/routes/liquidity.py
api/routes/operational.py
api/routes/portfolio.py
api/routes/regulatory.py
api/routes/alm.py
api/routes/var.py
api/middleware/rate_limit.py

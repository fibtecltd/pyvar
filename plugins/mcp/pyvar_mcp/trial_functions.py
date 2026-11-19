"""plugins/mcp/pyvar_mcp/trial_functions.py — the functions the no-sign-up trial can run.

Reasoning:
- pyvar.com's trial lane (api/trial_whitelist.py in the pyvar repository) runs only a short list of
  functions for a caller with no API key. The server answers 404 for any other name, so this copy exists
  to tell the model BEFORE a call which functions work without a key, and to refuse the rest without a
  network round trip. It is a copy, not a generated file: tests/test_mcp_trial_contract.py in the main
  repository fails if it differs from the server's list, so the two cannot drift unnoticed.
"""

from __future__ import annotations

TRIAL_FUNCTIONS: frozenset[str] = frozenset(
    {
        "altman_z_score_credit_scoring",
        "basel_iii_cet1_ratio",
        "basel_iii_leverage_ratio",
        "basel_iv_output_floor",
        "basel_standardised_measurement_sma",
        "black_scholes_european_option",
        "black_scholes_greeks",
        "bond_pricer_fixed_coupon",
        "calmar_ratio",
        "cds_spread_to_pd_conversion",
        "component_var",
        "cornish_fisher_var",
        "credit_var_analytical_vasicek",
        "duration_gap_analysis",
        "frtb_ima_expected_shortfall",
        "ifrs_9_12_month_ecl_stage_1",
        "interest_rate_swap_irs_pricer",
        "irrbb_six_standard_rate_shocks",
        "kri_threshold_breach_detection",
        "kupiec_pof_test",
        "liquidity_buffer_sizing",
        "mean_variance_optimisation",
        "parametric_delta_normal_var",
        "rcsa_inherent_risk_scoring",
        "reverse_stress_testing",
        "survival_horizon_calculator",
        "tracking_error",
        "traffic_light_backtesting",
        "wholesale_funding_concentration",
        "yield_to_maturity",
    }
)

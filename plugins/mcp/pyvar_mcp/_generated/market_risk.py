"""plugins/mcp/pyvar_mcp/_generated/market_risk.py — GENERATED, do not edit by hand.

The market-risk tools. Regenerate with: python3 scripts/generate_mcp_tools.py (from the
repo root). Source: portal/functions.json -- see that script for the mapping.
"""

from __future__ import annotations

from typing import Any

# Each entry: domain, function_name (== the API's function name), tool_name (the
# MCP tool name -- currently identical to function_name; kept as a separate field
# in case a future disambiguation strategy needs to diverge the two), path (the
# real POST endpoint, relative to the API base URL), summary, description, and
# input_schema (JSON Schema, mapped directly from functions.json's params list).
FUNCTIONS: list[dict[str, Any]] = [
    {
        "description": "Green zone (< 5 breaches) → 3.0; yellow zone (5-9) → the BCBS graduated\n"
        "schedule (3.40 .. 3.85); red zone (>= 10) → 4.0. These values are set by "
        "the\n"
        "Basel Committee (CLAUDE.md §4.3).",
        "domain": "market-risk",
        "function_name": "basel_capital_addon_multiplier",
        "input_schema": {
            "properties": {"n_breaches": {"type": "integer"}},
            "required": ["n_breaches"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/basel_capital_addon_multiplier",
        "summary": "Basel capital add-on multiplier from the backtest breach count.",
        "tool_name": "basel_capital_addon_multiplier",
    },
    {
        "description": "Computed in the time-to-maturity convention so that a finite-difference "
        "of\n"
        "delta with respect to τ reproduces this value. Note the sign: this is\n"
        "+∂Δ/∂τ (time-to-maturity), the opposite sign from the calendar-time charm\n"
        "convention −∂Δ/∂t (decay per day of calendar time elapsed) more commonly\n"
        "quoted on trading desks and in textbooks — do not assume the "
        "calendar-time\n"
        "sign without checking which convention a comparison source uses.",
        "domain": "market-risk",
        "function_name": "charm_delta_decay",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/charm_delta_decay",
        "summary": "Charm — sensitivity of delta to time to maturity (∂Δ/∂τ).",
        "tool_name": "charm_delta_decay",
    },
    {
        "description": "Likelihood-ratio test that breaches are serially independent (no\n"
        "clustering), via a first-order Markov transition model. Chi-squared with\n"
        "1 dof at the 95% critical value.\n"
        "\n"
        "The four transition counts (n00, n01, n10, n11) that drive the likelihood\n"
        "ratio are derived internally from the ``breaches`` sequence itself, not\n"
        "supplied as separate arguments.",
        "domain": "market-risk",
        "function_name": "christoffersen_independence_test",
        "input_schema": {
            "properties": {"breaches": {"type": "object"}},
            "required": ["breaches"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/christoffersen_independence_test",
        "summary": "Christoffersen independence (clustering) test.",
        "tool_name": "christoffersen_independence_test",
    },
    {
        "description": "The Christoffersen conditional-coverage statistic ``LR_cc = LR_POF + "
        "LR_ind``\n"
        "is chi-squared with 2 dof, tested at the 95% critical value. It rejects a\n"
        "model that either mis-counts or clusters its breaches.",
        "domain": "market-risk",
        "function_name": "combined_backtesting",
        "input_schema": {
            "properties": {
                "breaches": {"type": "object"},
                "confidence_level": {"default": 0.99, "type": "number"},
            },
            "required": ["breaches"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/combined_backtesting",
        "summary": "Combined (conditional coverage) backtest: Kupiec + Christoffersen.",
        "tool_name": "combined_backtesting",
    },
    {
        "description": "Allocates total VaR to each position as ``w_i * marginal_i``. Because VaR "
        "is\n"
        "homogeneous of degree 1 in the weights, the components sum exactly to the\n"
        "total VaR (Euler's theorem) — the property regulators require for a\n"
        "coherent risk decomposition.",
        "domain": "market-risk",
        "function_name": "component_var",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "cov_matrix": {"type": "object"},
                "portfolio_value": {"type": "number"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "cov_matrix", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/component_var",
        "summary": "Component VaR via Euler allocation.",
        "tool_name": "component_var",
    },
    {
        "description": "Basel traffic-light zones:\n"
        "  Green  < 5 breaches / 250 days\n"
        "  Yellow 5-9 breaches\n"
        "  Red    >= 10 breaches",
        "domain": "market-risk",
        "function_name": "compute_breaches",
        "input_schema": {
            "properties": {
                "actual_returns": {"type": "object"},
                "var_estimates": {"type": "object"},
            },
            "required": ["actual_returns", "var_estimates"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/compute_breaches",
        "summary": "Backtesting: count days where actual loss exceeded VaR estimate.",
        "tool_name": "compute_breaches",
    },
    {
        "description": "Regulatory standard under Basel III / FRTB for market risk capital.",
        "domain": "market-risk",
        "function_name": "compute_cvar",
        "input_schema": {
            "properties": {
                "confidence_level": {"type": "number"},
                "sorted_losses": {"type": "object"},
            },
            "required": ["sorted_losses", "confidence_level"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/compute_cvar",
        "summary": "Conditional VaR (Expected Shortfall) — mean of losses beyond VaR threshold.",
        "tool_name": "compute_cvar",
    },
    {
        "description": "Default percentiles cover the standard regulatory range.",
        "domain": "market-risk",
        "function_name": "compute_loss_percentiles",
        "input_schema": {
            "properties": {"percentiles": {"type": "object"}, "sorted_losses": {"type": "object"}},
            "required": ["sorted_losses"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/compute_loss_percentiles",
        "summary": "Returns a dict of {percentile_label: loss_value} for fan chart display.",
        "tool_name": "compute_loss_percentiles",
    },
    {
        "description": "At each point, mean and volatility are estimated from only the most "
        "recent\n"
        "`window` observations (returns[i - window : i]), not an expanding window\n"
        "that grows from the start of the series.\n"
        "Fast approximation for backtesting — not the full Monte Carlo.\n"
        "Uses scipy.stats.norm for the quantile function.\n"
        "\n"
        "Returns array of VaR estimates, same length as returns (NaN for first "
        "window obs).",
        "domain": "market-risk",
        "function_name": "compute_rolling_var",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "returns": {"type": "object"},
                "window": {"default": 250, "type": "integer"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/compute_rolling_var",
        "summary": "Parametric (Gaussian) rolling VaR using a fixed-length trailing window.",
        "tool_name": "compute_rolling_var",
    },
    {
        "description": "The FRTB IMA capital metric is ES at 97.5% (hence the default). ES is the\n"
        "mean loss conditional on exceeding the VaR threshold and is always >= VaR.",
        "domain": "market-risk",
        "function_name": "conditional_var_es",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.975, "type": "number"},
                "portfolio_value": {"type": "number"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/conditional_var_es",
        "summary": "Conditional VaR (Expected Shortfall) from a return series.",
        "tool_name": "conditional_var_es",
    },
    {
        "description": "Each round, the current shock spills to connected nodes via the contagion\n"
        "matrix C; the cumulative shock is ``shock + C·shock + C²·shock + ...`` "
        "over\n"
        "the requested rounds — a truncated Neumann series of the spillover "
        "operator.",
        "domain": "market-risk",
        "function_name": "contagion_stress_scenario",
        "input_schema": {
            "properties": {
                "contagion_matrix": {"type": "object"},
                "initial_shock": {"type": "object"},
                "rounds": {"default": 3, "type": "integer"},
            },
            "required": ["initial_shock", "contagion_matrix"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/contagion_stress_scenario",
        "summary": "Propagate an initial shock through a contagion (spillover) network.",
        "tool_name": "contagion_stress_scenario",
    },
    {
        "description": "Expands the Gaussian quantile with the third and fourth moments so the "
        "VaR\n"
        "reflects skewness and fat tails. When skewness and excess kurtosis are "
        "both\n"
        "zero it collapses exactly to the parametric delta-normal VaR.",
        "domain": "market-risk",
        "function_name": "cornish_fisher_var",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "excess_kurtosis": {"type": "object"},
                "portfolio_value": {"type": "number"},
                "returns": {"type": "object"},
                "skewness": {"type": "object"},
            },
            "required": ["returns", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/cornish_fisher_var",
        "summary": "Cornish-Fisher (modified) VaR.",
        "tool_name": "cornish_fisher_var",
    },
    {
        "description": "",
        "domain": "market-risk",
        "function_name": "correlation_matrix_historical",
        "input_schema": {
            "properties": {"returns_matrix": {"type": "object"}},
            "required": ["returns_matrix"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/correlation_matrix_historical",
        "summary": "Historical (Pearson) correlation matrix of asset returns.",
        "tool_name": "correlation_matrix_historical",
    },
    {
        "description": "Total credit P&L = Σ cs01_i · dspread_bp_i, additive across credit names.",
        "domain": "market-risk",
        "function_name": "credit_pnl_attribution",
        "input_schema": {
            "properties": {
                "cs01_sensitivities": {"type": "object"},
                "name_labels": {"type": "object"},
                "spread_moves_bp": {"type": "object"},
            },
            "required": ["cs01_sensitivities", "spread_moves_bp"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/credit_pnl_attribution",
        "summary": "Credit P&L attribution by issuer / curve.",
        "tool_name": "credit_pnl_attribution",
    },
    {
        "description": "Cashflows are discounted at ``r + s``; CS01 is\n"
        "``Σ cf_k · t_k · e^{-(r+s) t_k} · 1e-4`` — the price drop for a 1bp "
        "widening\n"
        "of the credit spread.",
        "domain": "market-risk",
        "function_name": "cs01_credit_spread",
        "input_schema": {
            "properties": {
                "cashflows": {"type": "object"},
                "credit_spread": {"type": "number"},
                "risk_free_rate": {"type": "number"},
                "times": {"type": "object"},
            },
            "required": ["cashflows", "times", "risk_free_rate", "credit_spread"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/cs01_credit_spread",
        "summary": "CS01 — sensitivity of a risky cashflow stream to a +1bp credit spread move.",
        "tool_name": "cs01_credit_spread",
    },
    {
        "description": "Under the normal model ES = sigma_p * φ(z) / (1 − α). ES is homogeneous "
        "of\n"
        "degree 1 in the weights, so component ES_i = w_i * (Σ w)_i / sigma_p *\n"
        "φ(z)/(1 − α) and the components sum exactly to total ES (Euler's theorem).",
        "domain": "market-risk",
        "function_name": "cvar_decomposition_euler",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.975, "type": "number"},
                "cov_matrix": {"type": "object"},
                "portfolio_value": {"type": "number"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "cov_matrix", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/cvar_decomposition_euler",
        "summary": "Euler decomposition of Gaussian Expected Shortfall.",
        "tool_name": "cvar_decomposition_euler",
    },
    {
        "description": "Standardises each series, then evolves the quasi-correlation\n"
        "``Q_t = (1−a−b) Q̄ + a z_{t-1} z_{t-1}' + b Q_{t-1}`` and normalises to a\n"
        "correlation matrix. With ``a = b = 0`` it collapses to the constant\n"
        "unconditional correlation Q̄.",
        "domain": "market-risk",
        "function_name": "dcc_garch_dynamic_correlation",
        "input_schema": {
            "properties": {
                "a": {"default": 0.02, "type": "number"},
                "b": {"default": 0.95, "type": "number"},
                "returns_matrix": {"type": "object"},
            },
            "required": ["returns_matrix"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/dcc_garch_dynamic_correlation",
        "summary": "DCC-GARCH dynamic conditional correlation (Engle 2002), terminal R_T.",
        "tool_name": "dcc_garch_dynamic_correlation",
    },
    {
        "description": "For continuously-discounted cashflows ``PV = Σ cf_k e^{-y t_k}`` the DV01 "
        "of\n"
        "each cashflow (price change for a +1bp yield move) is\n"
        "``cf_k · t_k · e^{-y t_k} · 1e-4``. Cashflows are summed into tenor "
        "buckets;\n"
        "the bucket DV01s sum exactly to the total.",
        "domain": "market-risk",
        "function_name": "dv01_pv01_bucketed",
        "input_schema": {
            "properties": {
                "bucket_indices": {"type": "object"},
                "cashflows": {"type": "object"},
                "flat_yield": {"type": "number"},
                "n_buckets": {"type": "integer"},
                "times": {"type": "object"},
            },
            "required": ["cashflows", "times", "flat_yield", "bucket_indices", "n_buckets"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/dv01_pv01_bucketed",
        "summary": "Tenor-bucketed DV01 / PV01 of a fixed cashflow stream.",
        "tool_name": "dv01_pv01_bucketed",
    },
    {
        "description": "Models log-variance, so conditional variance is positive for any "
        "parameters.\n"
        "The leverage term ``gamma`` makes negative shocks raise volatility more "
        "than\n"
        "positive shocks of equal size (when ``gamma < 0``).",
        "domain": "market-risk",
        "function_name": "egarch_volatility_model",
        "input_schema": {
            "properties": {
                "alpha": {"default": 0.1, "type": "number"},
                "beta": {"default": 0.95, "type": "number"},
                "gamma": {"default": -0.05, "type": "number"},
                "omega": {"default": -0.1, "type": "number"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/egarch_volatility_model",
        "summary": "EGARCH(1,1) asymmetric volatility model (Nelson 1991).",
        "tool_name": "egarch_volatility_model",
    },
    {
        "description": "Useful for limit dashboards that report internal (95%), FRTB (97.5%) and\n"
        "Basel (99%) ES side by side. ES is monotone non-decreasing in confidence.",
        "domain": "market-risk",
        "function_name": "es_at_multiple_confidence_levels",
        "input_schema": {
            "properties": {
                "confidence_levels": {"default": [0.95, 0.975, 0.99], "type": "array"},
                "portfolio_value": {"type": "number"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/es_at_multiple_confidence_levels",
        "summary": "Expected Shortfall evaluated at several confidence levels at once.",
        "tool_name": "es_at_multiple_confidence_levels",
    },
    {
        "description": "Each asset's ES contribution is its average loss across exactly the\n"
        "scenarios where the *portfolio* breaches VaR. By construction the\n"
        "contributions sum to total ES (the additive allocation FRTB expects).",
        "domain": "market-risk",
        "function_name": "expected_shortfall_contribution",
        "input_schema": {
            "properties": {
                "asset_returns": {"type": "object"},
                "confidence_level": {"default": 0.975, "type": "number"},
                "portfolio_value": {"type": "number"},
                "weights": {"type": "object"},
            },
            "required": ["asset_returns", "weights", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/expected_shortfall_contribution",
        "summary": "Per-asset ES contribution by conditional expectation in the tail.",
        "tool_name": "expected_shortfall_contribution",
    },
    {
        "description": "Fits a Generalised Pareto Distribution to losses exceeding a high "
        "threshold\n"
        "u and reads the tail quantile::\n"
        "\n"
        "    VaR_p = u + (β/ξ) · [ ((n/N_u)(1−p))^{−ξ} − 1 ]\n"
        "\n"
        "capturing tail behaviour beyond the empirical sample range.",
        "domain": "market-risk",
        "function_name": "extreme_value_theory_var",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "returns": {"type": "object"},
                "threshold_quantile": {"default": 0.95, "type": "number"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/extreme_value_theory_var",
        "summary": "Extreme Value Theory VaR via Peaks-Over-Threshold (Generalised Pareto).",
        "tool_name": "extreme_value_theory_var",
    },
    {
        "description": "Standardises returns by their EWMA conditional volatility, then re-scales\n"
        "the standardised residuals by the *current* volatility forecast before\n"
        "taking the empirical quantile. This captures volatility clustering that\n"
        "plain historical simulation ignores.",
        "domain": "market-risk",
        "function_name": "filtered_historical_simulation_var",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "lambda_decay": {"default": 0.94, "type": "number"},
                "portfolio_value": {"type": "number"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/filtered_historical_simulation_var",
        "summary": "Filtered Historical Simulation VaR (Barone-Adesi & Giannopoulos).",
        "tool_name": "filtered_historical_simulation_var",
    },
    {
        "description": "Combines the internally-modelled capital charge (IMCC, from ES), the\n"
        "non-modellable SES add-on, and the default risk charge (MAR33.43):\n"
        "``ACC = IMCC + SES + DRC``.",
        "domain": "market-risk",
        "function_name": "frtb_ima_aggregate_capital_charge",
        "input_schema": {
            "properties": {
                "default_risk_charge": {"default": 0.0, "type": "number"},
                "imcc": {"type": "number"},
                "ses": {"type": "number"},
            },
            "required": ["imcc", "ses"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/frtb_ima_aggregate_capital_charge",
        "summary": "FRTB IMA aggregate capital charge.",
        "tool_name": "frtb_ima_aggregate_capital_charge",
    },
    {
        "description": "ES is the mean loss beyond the VaR threshold at the FRTB confidence of\n"
        "97.5% (CLAUDE.md §4.2) and is always >= VaR.",
        "domain": "market-risk",
        "function_name": "frtb_ima_expected_shortfall",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.975, "type": "number"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/frtb_ima_expected_shortfall",
        "summary": "FRTB IMA Expected Shortfall (the regulatory ES at 97.5%).",
        "tool_name": "frtb_ima_expected_shortfall",
    },
    {
        "description": "Aggregates per-factor stressed capital add-ons (ISES) as\n"
        "``SES = sqrt( (ρ·Σ ISES)² + (1−ρ²)·Σ ISES² )`` (MAR33.16). With ρ = 0 this "
        "is\n"
        "the Euclidean sum; with ρ = 1 it is the linear (fully correlated) sum.",
        "domain": "market-risk",
        "function_name": "frtb_ima_non_modellable_risk_factors",
        "input_schema": {
            "properties": {
                "individual_ses": {"type": "object"},
                "rho": {"default": 0.0, "type": "number"},
            },
            "required": ["individual_ses"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/frtb_ima_non_modellable_risk_factors",
        "summary": "FRTB IMA non-modellable risk factor (NMRF) capital — aggregate SES.",
        "tool_name": "frtb_ima_non_modellable_risk_factors",
    },
    {
        "description": "FRTB calibrates the stressed ES to the historical window of greatest "
        "stress.\n"
        "This slides a 250-day window and returns the start index whose Expected\n"
        "Shortfall is largest.",
        "domain": "market-risk",
        "function_name": "frtb_ima_stressed_period_finder",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.975, "type": "number"},
                "returns": {"type": "object"},
                "window": {"default": 250, "type": "integer"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/frtb_ima_stressed_period_finder",
        "summary": "Locate the FRTB IMA stressed period — the worst 250-day ES window.",
        "tool_name": "frtb_ima_stressed_period_finder",
    },
    {
        "description": "Net jump-to-default per issuer is risk-weighted; the gross short charge "
        "is\n"
        "scaled by the Weighted-to-Short (hedge benefit) ratio\n"
        "``WtS = Σ netLong / (Σ netLong + Σ|netShort|)`` (MAR22). DRC is floored at "
        "0.",
        "domain": "market-risk",
        "function_name": "frtb_sa_default_risk_charge",
        "input_schema": {
            "properties": {
                "jtd_long": {"type": "object"},
                "jtd_short": {"type": "object"},
                "risk_weights": {"type": "object"},
            },
            "required": ["jtd_long", "jtd_short", "risk_weights"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/frtb_sa_default_risk_charge",
        "summary": "FRTB SA Default Risk Charge (DRC) with the hedge-benefit ratio.",
        "tool_name": "frtb_sa_default_risk_charge",
    },
    {
        "description": "A simple notional-based add-on for instruments with residual risks not\n"
        "captured by the SBM: ``RRAO = Σ notional_i · weight_i`` (MAR23, e.g. 1.0% "
        "on\n"
        "exotic underlyings, 0.1% otherwise).",
        "domain": "market-risk",
        "function_name": "frtb_sa_residual_risk_addon",
        "input_schema": {
            "properties": {"notionals": {"type": "object"}, "rrao_weights": {"type": "object"}},
            "required": ["notionals", "rrao_weights"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/frtb_sa_residual_risk_addon",
        "summary": "FRTB SA Residual Risk Add-On (RRAO).",
        "tool_name": "frtb_sa_residual_risk_addon",
    },
    {
        "description": "Within each bucket the risk position is\n"
        "``Kb = sqrt(Σ WS_i² + Σ_{i≠j} ρ·WS_i·WS_j)``; the charge aggregates "
        "buckets\n"
        "as ``sqrt(Σ Kb² + Σ_{b≠c} γ·S_b·S_c)`` with ``S_b = Σ_i WS_i`` (MAR21).\n"
        "\n"
        "Both the per-bucket ``Kb²`` term and the aggregate sum under the final\n"
        "square root are floored at 0 before the square root is taken, guarding\n"
        "against a negative value under extreme correlation inputs — a safeguard\n"
        "not shown in the MAR21 formula above.",
        "domain": "market-risk",
        "function_name": "frtb_sa_sensitivity_based_method",
        "input_schema": {
            "properties": {
                "bucket_weighted_sensitivities": {"type": "array"},
                "inter_bucket_corr": {"type": "number"},
                "intra_bucket_corr": {"type": "number"},
            },
            "required": ["bucket_weighted_sensitivities", "intra_bucket_corr", "inter_bucket_corr"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/frtb_sa_sensitivity_based_method",
        "summary": "FRTB SA Sensitivities-Based Method (delta) risk charge.",
        "tool_name": "frtb_sa_sensitivity_based_method",
    },
    {
        "description": "Total FX P&L = Σ fx_delta_i · dFX_i, additive across currencies.",
        "domain": "market-risk",
        "function_name": "fx_pnl_attribution",
        "input_schema": {
            "properties": {
                "currency_names": {"type": "object"},
                "fx_deltas": {"type": "object"},
                "fx_moves": {"type": "object"},
            },
            "required": ["fx_deltas", "fx_moves"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/fx_pnl_attribution",
        "summary": "FX P&L attribution across currency pairs.",
        "tool_name": "fx_pnl_attribution",
    },
    {
        "description": "The diagonal holds each underlying's net gamma (∂²V/∂S_i²); off-diagonals\n"
        "hold cross-gammas (∂²V/∂S_i∂S_j). The matrix is symmetric (Schwarz's\n"
        "theorem) — gamma P&L for a shock vector ds is ``0.5 · ds' G ds``.",
        "domain": "market-risk",
        "function_name": "gamma_cross_gamma_matrix",
        "input_schema": {
            "properties": {"cross_gammas": {"type": "object"}, "own_gammas": {"type": "object"}},
            "required": ["own_gammas"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/gamma_cross_gamma_matrix",
        "summary": "Assemble the portfolio gamma / cross-gamma matrix.",
        "tool_name": "gamma_cross_gamma_matrix",
    },
    {
        "description": "",
        "domain": "market-risk",
        "function_name": "gamma_pnl_attribution",
        "input_schema": {
            "properties": {"gamma": {"type": "number"}, "spot_move": {"type": "number"}},
            "required": ["gamma", "spot_move"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/gamma_pnl_attribution",
        "summary": "Gamma (convexity) P&L component: ``½ · Γ · dS²``.",
        "tool_name": "gamma_pnl_attribution",
    },
    {
        "description": "Filters the conditional variance and projects it forward. The h-step\n"
        "forecast mean-reverts to the long-run variance ``ω/(1−α−β)`` at rate\n"
        "``(α+β)`` — the defining property of a stationary GARCH(1,1). If ``omega`` "
        "is\n"
        "not supplied it is set by variance targeting, ``ω = "
        "(1−α−β)·Var(returns)``.",
        "domain": "market-risk",
        "function_name": "garch_11_volatility_forecast",
        "input_schema": {
            "properties": {
                "alpha": {"default": 0.1, "type": "number"},
                "beta": {"default": 0.85, "type": "number"},
                "horizon": {"default": 10, "type": "integer"},
                "omega": {"type": "object"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/garch_11_volatility_forecast",
        "summary": "GARCH(1,1) conditional-volatility filter and multi-step forecast.",
        "tool_name": "garch_11_volatility_forecast",
    },
    {
        "description": "A leverage indicator adds ``gamma`` to the ARCH coefficient when the "
        "prior\n"
        "shock was negative, so (for ``gamma > 0``) downside shocks raise "
        "volatility\n"
        "more. The long-run variance is ``ω/(1 − α − β − γ/2)``.",
        "domain": "market-risk",
        "function_name": "gjr_garch_asymmetric_model",
        "input_schema": {
            "properties": {
                "alpha": {"default": 0.03, "type": "number"},
                "beta": {"default": 0.88, "type": "number"},
                "gamma": {"default": 0.08, "type": "number"},
                "omega": {"type": "object"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/gjr_garch_asymmetric_model",
        "summary": "GJR-GARCH(1,1) asymmetric volatility model (Glosten-Jagannathan-Runkle).",
        "tool_name": "gjr_garch_asymmetric_model",
    },
    {
        "description": "Predicted P&L = Δ·dS + ½Γ·dS² + ν·dσ + Θ·dt + ρ·dr. The unexplained "
        "residual\n"
        "is ``actual_pnl − predicted`` — the quantity the FRTB PAT scrutinises.",
        "domain": "market-risk",
        "function_name": "greeks_based_pnl_explain",
        "input_schema": {
            "properties": {
                "actual_pnl": {"type": "number"},
                "delta": {"type": "number"},
                "gamma": {"type": "number"},
                "rate_move": {"type": "number"},
                "rho": {"type": "number"},
                "spot_move": {"type": "number"},
                "theta": {"type": "number"},
                "time_step": {"type": "number"},
                "vega": {"type": "number"},
                "vol_move": {"type": "number"},
            },
            "required": [
                "delta",
                "gamma",
                "vega",
                "theta",
                "rho",
                "spot_move",
                "vol_move",
                "time_step",
                "rate_move",
                "actual_pnl",
            ],
            "type": "object",
        },
        "path": "/api/v1/market-risk/greeks_based_pnl_explain",
        "summary": "Second-order Greeks P&L explain.",
        "tool_name": "greeks_based_pnl_explain",
    },
    {
        "description": "Identical tail-mean definition as :func:`conditional_var_es` but framed "
        "as\n"
        "the historical-simulation ES: no distributional assumption, the empirical\n"
        "tail is averaged directly.",
        "domain": "market-risk",
        "function_name": "historical_expected_shortfall",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.975, "type": "number"},
                "portfolio_value": {"type": "number"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/historical_expected_shortfall",
        "summary": "Non-parametric historical Expected Shortfall.",
        "tool_name": "historical_expected_shortfall",
    },
    {
        "description": "Applies each historical day's factor returns to the current exposures and\n"
        "reports the resulting P&L path, identifying the single worst day.",
        "domain": "market-risk",
        "function_name": "historical_scenario_replay",
        "input_schema": {
            "properties": {
                "exposures": {"type": "object"},
                "historical_factor_returns": {"type": "object"},
            },
            "required": ["exposures", "historical_factor_returns"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/historical_scenario_replay",
        "summary": "Replay historical factor moves against the current portfolio.",
        "tool_name": "historical_scenario_replay",
    },
    {
        "description": "Re-prices the portfolio under each observed historical return and reads "
        "the\n"
        "empirical loss quantile — making no distributional assumption.",
        "domain": "market-risk",
        "function_name": "historical_simulation_var",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "portfolio_value": {"type": "number"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/historical_simulation_var",
        "summary": "Non-parametric Historical Simulation VaR.",
        "tool_name": "historical_simulation_var",
    },
    {
        "description": 'First-order P&L = Σ exposure_i * shock_i. Used for ad-hoc "what if" '
        "scenarios\n"
        "such as a simultaneous equity sell-off and rates spike.",
        "domain": "market-risk",
        "function_name": "hypothetical_multi_factor_scenario",
        "input_schema": {
            "properties": {"exposures": {"type": "object"}, "shocks": {"type": "object"}},
            "required": ["exposures", "shocks"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/hypothetical_multi_factor_scenario",
        "summary": "P&L under a single hypothetical multi-factor shock.",
        "tool_name": "hypothetical_multi_factor_scenario",
    },
    {
        "description": "The exact (non-marginal) effect of a position on portfolio VaR:\n"
        "``VaR(full) − VaR(portfolio with position i removed)``.",
        "domain": "market-risk",
        "function_name": "incremental_var",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "cov_matrix": {"type": "object"},
                "portfolio_value": {"type": "number"},
                "position_index": {"type": "integer"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "cov_matrix", "position_index", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/incremental_var",
        "summary": "Incremental VaR of a single position.",
        "tool_name": "incremental_var",
    },
    {
        "description": "Likelihood-ratio test that the observed breach rate matches the expected\n"
        "``p = 1 − confidence_level``. The statistic is chi-squared with 1 dof;\n"
        "rejection uses the 95% critical value.\n"
        "\n"
        "At the boundary cases ``x = 0`` or ``x = n`` (zero or 100% observed "
        "breach\n"
        "rate) the likelihood ratio is computed with a simplified one-sided form "
        "to\n"
        "avoid ``ln(0)``; the general two-sided expression applies for ``0 < x < "
        "n``.",
        "domain": "market-risk",
        "function_name": "kupiec_pof_test",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "n_breaches": {"type": "integer"},
                "n_observations": {"type": "integer"},
            },
            "required": ["n_breaches", "n_observations"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/kupiec_pof_test",
        "summary": "Kupiec Proportion-of-Failures (POF) unconditional coverage test.",
        "tool_name": "kupiec_pof_test",
    },
    {
        "description": "Scales the base-horizon ES up for risk factors that take longer than the\n"
        "base liquidity horizon T to unwind::\n"
        "\n"
        "    ES = sqrt( ES_base^2 + Σ_{j>=2} ( ES_j * sqrt((LH_j − LH_{j-1}) / T) "
        ")^2 )\n"
        "\n"
        "where ``ES_base`` is the whole-portfolio ES at horizon T, and ``ES_j`` is "
        "the\n"
        "ES with respect to factors in liquidity bucket j and longer.",
        "domain": "market-risk",
        "function_name": "liquidity_adjusted_es",
        "input_schema": {
            "properties": {
                "base_horizon": {"default": 10.0, "type": "number"},
                "es_base": {"type": "number"},
                "liquidity_horizons": {"type": "array"},
                "partial_es": {"type": "array"},
            },
            "required": ["es_base", "partial_es", "liquidity_horizons"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/liquidity_adjusted_es",
        "summary": "Liquidity-adjusted Expected Shortfall (FRTB IMA, MAR33.12).",
        "tool_name": "liquidity_adjusted_es",
    },
    {
        "description": "Draws standard-normal innovations in pure Python (CLAUDE.md §3.1 RULE 3) "
        "and\n"
        "colours them with the Cholesky factor of the supplied covariance so the\n"
        "generated scenarios reproduce the target factor correlation structure.",
        "domain": "market-risk",
        "function_name": "macro_scenario_generator",
        "input_schema": {
            "properties": {
                "factor_cov": {"type": "object"},
                "n_scenarios": {"default": 10000, "type": "integer"},
                "seed": {"default": 42, "type": "object"},
            },
            "required": ["factor_cov"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/macro_scenario_generator",
        "summary": "Generate correlated macro factor scenarios via the Cholesky factor.",
        "tool_name": "macro_scenario_generator",
    },
    {
        "description": "For the delta-normal model VaR = z * sqrt(w' Σ w), the marginal VaR is "
        "the\n"
        "gradient ``∂VaR/∂w_i = z * (Σ w)_i / sigma_p``.",
        "domain": "market-risk",
        "function_name": "marginal_var",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "cov_matrix": {"type": "object"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/marginal_var",
        "summary": "Marginal VaR — sensitivity of portfolio VaR to each position weight.",
        "tool_name": "marginal_var",
    },
    {
        "description": "Runs the parametric-normal Monte Carlo engine and reads the ES (CVaR) "
        "from\n"
        "the simulated loss distribution. Deterministic for a fixed seed.\n"
        "\n"
        "Internally this delegates to ``engine.montecarlo.run_monte_carlo_var`` "
        "and\n"
        "returns its ``cvar_pct``/``cvar_abs`` fields; the simulation's mean and\n"
        "volatility (mu, sigma) are fitted directly from the ``returns`` argument,\n"
        "not supplied as separate distribution parameters.",
        "domain": "market-risk",
        "function_name": "monte_carlo_expected_shortfall",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.975, "type": "number"},
                "horizon_days": {"default": 1, "type": "integer"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "portfolio_value": {"type": "number"},
                "returns": {"type": "object"},
                "seed": {"default": 42, "type": "object"},
            },
            "required": ["returns", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/monte_carlo_expected_shortfall",
        "summary": "Monte Carlo Expected Shortfall.",
        "tool_name": "monte_carlo_expected_shortfall",
    },
    {
        "description": "Assumes asset returns are jointly normal so portfolio loss is normal with\n"
        "standard deviation ``sqrt(w' Σ w)``. VaR is the scaled normal quantile.",
        "domain": "market-risk",
        "function_name": "parametric_delta_normal_var",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "cov_matrix": {"type": "object"},
                "horizon_days": {"default": 1, "type": "integer"},
                "portfolio_value": {"type": "number"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "cov_matrix", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/parametric_delta_normal_var",
        "summary": "Variance-covariance (delta-normal) VaR.",
        "tool_name": "parametric_delta_normal_var",
    },
    {
        "description": "Jointly evaluates the Spearman rank correlation between risk-theoretical "
        "P&L\n"
        "(RTPL) and hypothetical P&L (HPL) and the volatility ratio\n"
        "``std(RTPL)/std(HPL)``, assigning the Basel traffic-light zone. These\n"
        "thresholds are set by the Basel Committee and are not parameterised.",
        "domain": "market-risk",
        "function_name": "pnl_attribution_test_frtb_pat",
        "input_schema": {
            "properties": {
                "hypothetical_pnl": {"type": "object"},
                "risk_theoretical_pnl": {"type": "object"},
            },
            "required": ["risk_theoretical_pnl", "hypothetical_pnl"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/pnl_attribution_test_frtb_pat",
        "summary": "FRTB P&L Attribution Test (PAT) — Spearman correlation and ratio test.",
        "tool_name": "pnl_attribution_test_frtb_pat",
    },
    {
        "description": "Net delta = Σ delta_i * quantity_i. When spot prices are supplied the\n"
        "cash (dollar) delta Σ delta_i * quantity_i * spot_i is also returned.",
        "domain": "market-risk",
        "function_name": "portfolio_delta_aggregated",
        "input_schema": {
            "properties": {
                "deltas": {"type": "object"},
                "quantities": {"type": "object"},
                "spot_prices": {"type": "object"},
            },
            "required": ["deltas", "quantities"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/portfolio_delta_aggregated",
        "summary": "Aggregate per-position deltas into a net portfolio delta.",
        "tool_name": "portfolio_delta_aggregated",
    },
    {
        "description": "Total rates P&L = Σ sensitivity_t · dyield_bp_t, where each sensitivity "
        "is\n"
        "P&L per +1bp move at that tenor. Additive across the key-rate ladder.",
        "domain": "market-risk",
        "function_name": "rates_pnl_attribution",
        "input_schema": {
            "properties": {
                "key_rate_sensitivities": {"type": "object"},
                "tenor_names": {"type": "object"},
                "yield_moves_bp": {"type": "object"},
            },
            "required": ["key_rate_sensitivities", "yield_moves_bp"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/rates_pnl_attribution",
        "summary": "Interest-rate P&L attribution by key-rate tenor.",
        "tool_name": "rates_pnl_attribution",
    },
    {
        "description": "Realised variance is the sum of squared returns; realised volatility is "
        "its\n"
        "square root, and the annualised figure scales by "
        "``sqrt(annualisation_factor)``.",
        "domain": "market-risk",
        "function_name": "realised_volatility",
        "input_schema": {
            "properties": {
                "annualisation_factor": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/realised_volatility",
        "summary": "Realised volatility from a block of (typically high-frequency) returns.",
        "tool_name": "realised_volatility",
    },
    {
        "description": "Residual = actual P&L − Σ explained components. The residual plus the sum "
        "of\n"
        "explained components reconstructs the actual P&L exactly; a large "
        "residual\n"
        "relative to actual P&L flags model incompleteness (an FRTB PAT concern).",
        "domain": "market-risk",
        "function_name": "residual_pnl_unexplained",
        "input_schema": {
            "properties": {
                "actual_pnl": {"type": "number"},
                "explained_components": {"type": "object"},
            },
            "required": ["actual_pnl", "explained_components"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/residual_pnl_unexplained",
        "summary": "Unexplained (residual) P&L.",
        "tool_name": "residual_pnl_unexplained",
    },
    {
        "description": "Among all factor shocks producing the given loss, the most plausible "
        "(lowest\n"
        "Mahalanobis magnitude under the factor covariance) lies along ``-Σ e``. "
        "The\n"
        "closed-form solution for loss L is ``s* = -(L / e'Σe) · Σ e`` with "
        "magnitude\n"
        "``m = L / sqrt(e'Σe)``.",
        "domain": "market-risk",
        "function_name": "reverse_stress_testing",
        "input_schema": {
            "properties": {
                "exposures": {"type": "object"},
                "factor_cov": {"type": "object"},
                "target_loss": {"type": "number"},
            },
            "required": ["exposures", "factor_cov", "target_loss"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/reverse_stress_testing",
        "summary": "Reverse stress test — find the most plausible scenario causing a target loss.",
        "tool_name": "reverse_stress_testing",
    },
    {
        "description": "``Rho_call = K τ e^{-rτ} N(d2)``; ``Rho_put = -K τ e^{-rτ} N(-d2)``.",
        "domain": "market-risk",
        "function_name": "rho_interest_rate",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/rho_interest_rate",
        "summary": "Black-Scholes Rho — option value sensitivity to the interest rate.",
        "tool_name": "rho_interest_rate",
    },
    {
        "description": "Eigen-decomposes the factor covariance matrix and orders components by\n"
        "descending variance. The explained-variance ratios sum to 1 (over all\n"
        "components) and the eigenvalues are non-negative (covariance is PSD).",
        "domain": "market-risk",
        "function_name": "risk_factor_pca_decomposition",
        "input_schema": {
            "properties": {
                "n_components": {"type": "object"},
                "returns_matrix": {"type": "object"},
            },
            "required": ["returns_matrix"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/risk_factor_pca_decomposition",
        "summary": "Principal-component decomposition of the risk-factor covariance.",
        "tool_name": "risk_factor_pca_decomposition",
    },
    {
        "description": "Estimates parametric VaR on each trailing window and counts breaches of "
        "the\n"
        "realised next-day return, returning the Basel traffic-light zone.",
        "domain": "market-risk",
        "function_name": "rolling_var_backtest",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "returns": {"type": "object"},
                "window": {"default": 250, "type": "integer"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/rolling_var_backtest",
        "summary": "Rolling-window VaR backtest over the Basel 250-day window.",
        "tool_name": "rolling_var_backtest",
    },
    {
        "description": "Applies a shock to each sector's net exposure and aggregates. Total P&L "
        "is\n"
        "the exact sum of per-sector P&L (additivity by construction).",
        "domain": "market-risk",
        "function_name": "sector_stress_scenario",
        "input_schema": {
            "properties": {
                "sector_exposures": {"type": "object"},
                "sector_names": {"type": "object"},
                "sector_shocks": {"type": "object"},
            },
            "required": ["sector_exposures", "sector_shocks"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/sector_stress_scenario",
        "summary": "Sector-level stress scenario.",
        "tool_name": "sector_stress_scenario",
    },
    {
        "description": "Sweeps a single risk factor across a grid of shocks (holding others flat)\n"
        'and returns the P&L profile — the building block of a stress "ladder".',
        "domain": "market-risk",
        "function_name": "sensitivity_stress_profile",
        "input_schema": {
            "properties": {
                "exposures": {"type": "object"},
                "factor_index": {"type": "integer"},
                "shock_grid": {"type": "object"},
            },
            "required": ["exposures", "factor_index", "shock_grid"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/sensitivity_stress_profile",
        "summary": "One-factor sensitivity stress profile.",
        "tool_name": "sensitivity_stress_profile",
    },
    {
        "description": "A coherent risk measure that integrates the loss quantile against a\n"
        "decreasing risk-spectrum ``φ(p) = k·e^{−k(1−p)} / (1−e^{−k})``, placing "
        "more\n"
        "weight on the tail as the risk aversion k rises. SRM >= the mean loss and "
        "is\n"
        "increasing in k.",
        "domain": "market-risk",
        "function_name": "spectral_risk_measure",
        "input_schema": {
            "properties": {
                "returns": {"type": "object"},
                "risk_aversion": {"default": 25.0, "type": "number"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/spectral_risk_measure",
        "summary": "Spectral risk measure with an exponential risk-aversion spectrum.",
        "tool_name": "spectral_risk_measure",
    },
    {
        "description": "FRTB requires ES to be calibrated to a historical period of significant\n"
        "financial stress. This computes ES over the supplied stressed window\n"
        "``returns[stress_start:stress_end]`` only.",
        "domain": "market-risk",
        "function_name": "stressed_expected_shortfall",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.975, "type": "number"},
                "portfolio_value": {"type": "number"},
                "returns": {"type": "object"},
                "stress_end": {"type": "integer"},
                "stress_start": {"type": "integer"},
            },
            "required": ["returns", "stress_start", "stress_end", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/stressed_expected_shortfall",
        "summary": "Stressed Expected Shortfall (FRTB IMA).",
        "tool_name": "stressed_expected_shortfall",
    },
    {
        "description": "Isolates the deterministic time-decay (carry) component of P&L,\n"
        "``theta · dt``, optionally net of a funding cost over the same period.",
        "domain": "market-risk",
        "function_name": "theta_carry_attribution",
        "input_schema": {
            "properties": {
                "funding_cost": {"default": 0.0, "type": "number"},
                "theta": {"type": "number"},
                "time_step": {"type": "number"},
            },
            "required": ["theta", "time_step"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/theta_carry_attribution",
        "summary": "Theta / carry attribution.",
        "tool_name": "theta_carry_attribution",
    },
    {
        "description": "",
        "domain": "market-risk",
        "function_name": "theta_time_decay",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/theta_time_decay",
        "summary": "Black-Scholes Theta — calendar time decay (∂V/∂calendar = −∂V/∂τ), per year.",
        "tool_name": "theta_time_decay",
    },
    {
        "description": "Counts VaR breaches and assigns the Basel zone: green (< 5 breaches), "
        "yellow\n"
        "(5-9), red (>= 10). These boundaries are set by the Basel Committee.",
        "domain": "market-risk",
        "function_name": "traffic_light_backtesting",
        "input_schema": {
            "properties": {
                "actual_returns": {"type": "object"},
                "var_estimates": {"type": "object"},
            },
            "required": ["actual_returns", "var_estimates"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/traffic_light_backtesting",
        "summary": "Basel traffic-light backtest over the 250-day window.",
        "tool_name": "traffic_light_backtesting",
    },
    {
        "description": "``Vanna = −e^{-qτ} · φ(d1) · d2 / σ``. Identical for calls and puts. It\n"
        "measures how delta drifts as volatility moves (and vice versa).",
        "domain": "market-risk",
        "function_name": "vanna_delta_vega_cross",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/vanna_delta_vega_cross",
        "summary": "Vanna — cross sensitivity ∂vega/∂S = ∂Δ/∂σ.",
        "tool_name": "vanna_delta_vega_cross",
    },
    {
        "description": "Reports the number of breach clusters (maximal runs of consecutive\n"
        "breaches), the longest run, and the mean run length — diagnostics for the\n"
        "independence assumption that the Christoffersen test formalises.\n"
        "\n"
        "This is an algorithmic run-length computation over the breach sequence,\n"
        "not a closed-form statistic.",
        "domain": "market-risk",
        "function_name": "var_breach_cluster_analysis",
        "input_schema": {
            "properties": {"breaches": {"type": "object"}},
            "required": ["breaches"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/var_breach_cluster_analysis",
        "summary": "Analyse the clustering of VaR breaches.",
        "tool_name": "var_breach_cluster_analysis",
    },
    {
        "description": "Identical Euler decomposition to :func:`component_var` but expressed in\n"
        "risk-factor space: given portfolio factor exposures ``b`` and factor\n"
        "covariance ``F``, the factor contribution is\n"
        "``z * b_i * (F b)_i / sigma_p`` and contributions sum to the total VaR.",
        "domain": "market-risk",
        "function_name": "var_by_risk_factor",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "factor_cov": {"type": "object"},
                "factor_exposures": {"type": "object"},
                "factor_names": {"type": "object"},
                "portfolio_value": {"type": "number"},
            },
            "required": ["factor_exposures", "factor_cov", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/var_by_risk_factor",
        "summary": "Decompose VaR across systematic risk factors (Euler allocation).",
        "tool_name": "var_by_risk_factor",
    },
    {
        "description": "Produces, for each confidence level, the VaR projected over 1..H days "
        "using\n"
        "square-root-of-time volatility scaling — the standard visualisation of "
        "how\n"
        "the loss envelope widens with the holding period.",
        "domain": "market-risk",
        "function_name": "var_fan_chart",
        "input_schema": {
            "properties": {
                "confidence_levels": {"default": [0.9, 0.95, 0.99], "type": "array"},
                "horizon_days": {"default": 10, "type": "integer"},
                "portfolio_value": {"type": "number"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/var_fan_chart",
        "summary": "VaR fan chart — parametric VaR bands across confidence levels and horizons.",
        "tool_name": "var_fan_chart",
    },
    {
        "description": "",
        "domain": "market-risk",
        "function_name": "vega_pnl_attribution",
        "input_schema": {
            "properties": {"vega": {"type": "number"}, "vol_move": {"type": "number"}},
            "required": ["vega", "vol_move"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/vega_pnl_attribution",
        "summary": "Vega P&L component: ``ν · dσ``.",
        "tool_name": "vega_pnl_attribution",
    },
    {
        "description": "Each option's vega is summed into its (expiry, strike) bucket. Total vega "
        "is\n"
        "conserved — the surface sum equals the input vega sum.",
        "domain": "market-risk",
        "function_name": "vega_surface_bucketed",
        "input_schema": {
            "properties": {
                "expiry_buckets": {"type": "object"},
                "n_expiry": {"type": "integer"},
                "n_strike": {"type": "integer"},
                "strike_buckets": {"type": "object"},
                "vegas": {"type": "object"},
            },
            "required": ["vegas", "expiry_buckets", "strike_buckets", "n_expiry", "n_strike"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/vega_surface_bucketed",
        "summary": "Aggregate option vegas onto a bucketed (expiry × strike) surface.",
        "tool_name": "vega_surface_bucketed",
    },
    {
        "description": "For each quoted option the Black-Scholes equation is inverted for implied\n"
        "volatility by bisection. Round-tripping (pricing at the recovered IV)\n"
        "reproduces the input price.",
        "domain": "market-risk",
        "function_name": "volatility_surface_implied_vol",
        "input_schema": {
            "properties": {
                "expiries": {"type": "object"},
                "market_prices": {"type": "object"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "spot": {"type": "number"},
                "strikes": {"type": "object"},
            },
            "required": ["market_prices", "strikes", "expiries", "spot", "rate"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/volatility_surface_implied_vol",
        "summary": "Back out the implied-volatility surface from market option prices.",
        "tool_name": "volatility_surface_implied_vol",
    },
    {
        "description": "``Volga = vega · d1 · d2 / σ``. Identical for calls and puts. Positive "
        "volga\n"
        "means the position is long volatility-of-volatility.",
        "domain": "market-risk",
        "function_name": "volga_vega_convexity",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/market-risk/volga_vega_convexity",
        "summary": "Volga (vomma) — convexity of value in volatility (∂²V/∂σ² = ∂vega/∂σ).",
        "tool_name": "volga_vega_convexity",
    },
]

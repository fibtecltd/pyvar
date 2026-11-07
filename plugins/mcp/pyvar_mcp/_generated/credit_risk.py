"""plugins/mcp/pyvar_mcp/_generated/credit_risk.py — GENERATED, do not edit by hand.

The credit-risk tools. Regenerate with: python3 scripts/generate_mcp_tools.py (from the
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
        "description": "``Z = 1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4 + 1.0 X5`` with X1 = WC/TA,\n"
        "X2 = RE/TA, X3 = EBIT/TA, X4 = MV equity / total liabilities, X5 = "
        "sales/TA.\n"
        "Zones: ``Z > 2.99`` safe, ``1.81 <= Z <= 2.99`` grey, ``Z < 1.81`` "
        "distress.",
        "domain": "credit-risk",
        "function_name": "altman_z_score_credit_scoring",
        "input_schema": {
            "properties": {
                "ebit": {"description": "Earnings before interest " "and tax.", "type": "number"},
                "market_value_equity": {
                    "description": "Market " "value of " "equity.",
                    "type": "number",
                },
                "retained_earnings": {"description": "Retained " "earnings.", "type": "number"},
                "sales": {"description": "Net sales.", "type": "number"},
                "total_assets": {"description": "Total assets (> " "0).", "type": "number"},
                "total_liabilities": {
                    "description": "Total " "liabilities " "(> 0).",
                    "type": "number",
                },
                "working_capital": {"description": "Working " "capital.", "type": "number"},
            },
            "required": [
                "working_capital",
                "retained_earnings",
                "ebit",
                "market_value_equity",
                "sales",
                "total_assets",
                "total_liabilities",
            ],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/altman_z_score_credit_scoring",
        "summary": "Altman (1968) Z-score for public manufacturers.",
        "tool_name": "altman_z_score_credit_scoring",
    },
    {
        "description": "``RWA = (EAD - CRM) * risk_weight``, where the supervisory risk weight is\n"
        "set by the external rating / exposure class (e.g. 0% sovereign AAA, 20%\n"
        "bank, 100% corporate unrated, 150% sub-investment grade). The minimum\n"
        "capital is 8% of RWA.",
        "domain": "credit-risk",
        "function_name": "basel_standardised_approach_rwa",
        "input_schema": {
            "properties": {
                "credit_risk_mitigation": {
                    "default": 0.0,
                    "description": "Eligible "
                    "collateral "
                    "/ "
                    "guarantee "
                    "value "
                    "netted "
                    "from "
                    "EAD "
                    "before "
                    "weighting "
                    "(>= "
                    "0).",
                    "type": "number",
                },
                "ead": {
                    "description": "Exposure at default " "(currency amount, >= 0).",
                    "type": "number",
                },
                "risk_weight": {
                    "description": "Supervisory risk "
                    "weight as a "
                    "fraction (e.g. "
                    "1.0 for 100%).",
                    "type": "number",
                },
            },
            "required": ["ead", "risk_weight"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/basel_standardised_approach_rwa",
        "summary": "Basel Standardised-Approach RWA (CRE20).",
        "tool_name": "basel_standardised_approach_rwa",
    },
    {
        "description": "``KVA = cost_of_capital * sum_k K_k * DF_k * dt_k`` — the present value "
        "of\n"
        "the shareholders' required return on the regulatory capital held against "
        "the\n"
        "trade over its life.",
        "domain": "credit-risk",
        "function_name": "capital_valuation_adjustment_kva",
        "input_schema": {
            "properties": {
                "capital_profile": {
                    "description": "``(n,)`` "
                    "regulatory "
                    "capital held "
                    "per bucket "
                    "(>= 0).",
                    "type": "object",
                },
                "cost_of_capital": {
                    "default": 0.1,
                    "description": "Hurdle rate / "
                    "cost of "
                    "capital "
                    "(decimal, "
                    "e.g. 0.10).",
                    "type": "number",
                },
                "discount_factors": {
                    "description": "``(n,)`` " "discount " "factors in " "``(0, 1]``.",
                    "type": "object",
                },
                "time_steps": {
                    "description": "``(n,)`` strictly " "increasing bucket " "end-times (years).",
                    "type": "object",
                },
            },
            "required": ["capital_profile", "time_steps", "discount_factors"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/capital_valuation_adjustment_kva",
        "summary": "Capital Valuation Adjustment — lifetime cost of regulatory capital.",
        "tool_name": "capital_valuation_adjustment_kva",
    },
    {
        "description": "PV(buyer) = protection leg - premium leg, where:\n"
        "  * premium leg = spread * notional * risky annuity\n"
        "    (``sum_k accrual_k DF_k S_k``),\n"
        "  * protection leg = LGD * notional * ``sum_k DF_k (S_{k-1} - S_k)``.\n"
        "The par spread that zeroes the PV is also returned.",
        "domain": "credit-risk",
        "function_name": "cds_pricing_isda_standard",
        "input_schema": {
            "properties": {
                "accrual_factors": {
                    "description": "``(n,)`` "
                    "day-count "
                    "accrual "
                    "fractions per "
                    "period (>= "
                    "0).",
                    "type": "object",
                },
                "contract_spread": {
                    "description": "Contractual " "(running) CDS " "spread " "(decimal).",
                    "type": "number",
                },
                "discount_factors": {
                    "description": "``(n,)`` " "risk-free " "discount " "factors in " "``(0, 1]``.",
                    "type": "object",
                },
                "hazard_rate": {
                    "description": "Flat hazard rate " "lambda (>= 0).",
                    "type": "number",
                },
                "notional": {"default": 1.0, "description": "Contract notional.", "type": "number"},
                "payment_times": {
                    "description": "``(n,)`` "
                    "strictly "
                    "increasing "
                    "premium-payment "
                    "times.",
                    "type": "object",
                },
                "recovery_rate": {
                    "default": 0.4,
                    "description": "Recovery rate " "in ``[0, 1)``.",
                    "type": "number",
                },
            },
            "required": [
                "payment_times",
                "accrual_factors",
                "discount_factors",
                "hazard_rate",
                "contract_spread",
            ],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/cds_pricing_isda_standard",
        "summary": "ISDA-standard CDS present value (protection-buyer perspective).",
        "tool_name": "cds_pricing_isda_standard",
    },
    {
        "description": "Hazard ``lambda = spread / (1 - R)``; cumulative default probability to\n"
        "maturity is ``PD = 1 - exp(-lambda * T)``. The annualised marginal "
        "default\n"
        "rate is also returned.",
        "domain": "credit-risk",
        "function_name": "cds_spread_to_pd_conversion",
        "input_schema": {
            "properties": {
                "cds_spread": {
                    "description": "CDS par spread " "(decimal, e.g. " "0.015 = 150 bps, " ">= 0).",
                    "type": "number",
                },
                "maturity": {"description": "Horizon T in years " "(> 0).", "type": "number"},
                "recovery_rate": {
                    "default": 0.4,
                    "description": "Recovery rate " "in ``[0, 1)``.",
                    "type": "number",
                },
            },
            "required": ["cds_spread", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/cds_spread_to_pd_conversion",
        "summary": "Credit-triangle conversion of a CDS spread to PD.",
        "tool_name": "cds_spread_to_pd_conversion",
    },
    {
        "description": "The adjusted collateral value is\n"
        "``C_adj = C * (1 - H_c - H_fx)`` where ``H_c`` is the "
        "market-price-volatility\n"
        "haircut and ``H_fx`` the currency-mismatch haircut (8% standard). The\n"
        "adjusted value is floored at zero.",
        "domain": "credit-risk",
        "function_name": "collateral_haircut_calculation",
        "input_schema": {
            "properties": {
                "collateral_value": {
                    "description": "Nominal " "collateral " "market value " "(>= 0).",
                    "type": "number",
                },
                "haircut_collateral": {
                    "description": "Collateral " "volatility " "haircut in " "``[0, " "1]``.",
                    "type": "number",
                },
                "haircut_fx": {
                    "default": 0.0,
                    "description": "Currency-mismatch " "haircut in ``[0, " "1]``.",
                    "type": "number",
                },
            },
            "required": ["collateral_value", "haircut_collateral"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/collateral_haircut_calculation",
        "summary": "Supervisory collateral haircut under the comprehensive approach (CRE22).",
        "tool_name": "collateral_haircut_calculation",
    },
    {
        "description": "Combines normalised factor scores (e.g. leverage, coverage, "
        "profitability,\n"
        "each in ``[0, 1]`` with 1 = strongest) into a composite ``[0, 1]`` rating\n"
        "strength, then maps to PD via ``PD = pd_anchor * (1 - strength)`` floored "
        "at\n"
        "``pd_floor``. A perfectly strong borrower hits the floor.\n"
        "\n"
        "This is a bespoke internal weighted-factor model, confirmed against\n"
        "BIS/EBA sources not to match any specific published or regulatory\n"
        "scoring formula, so treat it as a reasonable internal model rather than\n"
        "a reproduction of one.",
        "domain": "credit-risk",
        "function_name": "corporate_credit_scoring_model",
        "input_schema": {
            "properties": {
                "factor_scores": {
                    "description": "``(k,)`` factor " "strengths in " "``[0, 1]`` (1 = " "best).",
                    "type": "object",
                },
                "factor_weights": {
                    "description": "``(k,)`` "
                    "non-negative "
                    "weights "
                    "(normalised "
                    "internally).",
                    "type": "object",
                },
                "pd_anchor": {
                    "default": 0.5,
                    "description": "PD assigned to the " "weakest borrower " "(strength 0).",
                    "type": "number",
                },
                "pd_floor": {
                    "default": 0.0003,
                    "description": "Regulatory PD floor.",
                    "type": "number",
                },
            },
            "required": ["factor_scores", "factor_weights"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/corporate_credit_scoring_model",
        "summary": "Weighted-factor corporate credit score mapped to a PD.",
        "tool_name": "corporate_credit_scoring_model",
    },
    {
        "description": "``Exposure = max(MtM - collateral, 0) + add_on``. The current exposure is\n"
        "floored at zero (a counterparty owing you nothing has no replacement "
        "cost).",
        "domain": "credit-risk",
        "function_name": "counterparty_credit_risk_ccr_exposure",
        "input_schema": {
            "properties": {
                "add_on": {
                    "description": "Potential-future-exposure " "add-on (>= 0).",
                    "type": "number",
                },
                "collateral": {
                    "default": 0.0,
                    "description": "Collateral held " "against the " "exposure (>= 0).",
                    "type": "number",
                },
                "mark_to_market": {
                    "description": "Current MtM of "
                    "the netting "
                    "set (positive "
                    "= in-the-money "
                    "to the "
                    "reporting "
                    "bank).",
                    "type": "number",
                },
            },
            "required": ["mark_to_market", "add_on"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/counterparty_credit_risk_ccr_exposure",
        "summary": "Generic CCR exposure = current exposure + add-on, net of collateral.",
        "tool_name": "counterparty_credit_risk_ccr_exposure",
    },
    {
        "description": "``HHI = sum_i (w_i)^2`` on exposure shares. HHI = 1 means a single-name\n"
        "portfolio; HHI = 1/n means perfectly granular. The effective number of\n"
        "independent exposures is ``1/HHI`` (the diversification score).",
        "domain": "credit-risk",
        "function_name": "credit_concentration_risk_hhi",
        "input_schema": {
            "properties": {
                "exposures": {
                    "description": "Per-name exposure "
                    "amounts (>= 0, at "
                    "least one "
                    "positive).",
                    "type": "object",
                }
            },
            "required": ["exposures"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/credit_concentration_risk_hhi",
        "summary": "Herfindahl-Hirschman concentration index of a credit portfolio.",
        "tool_name": "credit_concentration_risk_hhi",
    },
    {
        "description": "The first-order MtM sensitivity to the credit spread is the spread DV01\n"
        "``= notional * risky_annuity`` (per unit spread). With a normal daily "
        "spread\n"
        "move of volatility ``sigma_s``, the VaR is\n"
        "``z * sigma_s * sqrt(horizon) * spread_DV01``.",
        "domain": "credit-risk",
        "function_name": "credit_default_swap_var",
        "input_schema": {
            "properties": {
                "confidence_level": {
                    "default": 0.99,
                    "description": "VaR " "confidence " "in ``[0.90, " "0.9999]``.",
                    "type": "number",
                },
                "horizon_days": {
                    "default": 1,
                    "description": "Risk horizon in " "trading days " "(sqrt-time " "scaling).",
                    "type": "integer",
                },
                "notional": {"description": "CDS notional.", "type": "number"},
                "position": {
                    "default": "long_protection",
                    "description": '``"long_protection"`` '
                    "or "
                    '``"short_protection"`` '
                    "(affects only the "
                    "sign of "
                    "``pnl_sensitivity``; "
                    "VaR magnitude is "
                    "identical).",
                    "type": "string",
                },
                "risky_annuity": {
                    "description": "Risky annuity " "(RPV01) of the " "contract (>= " "0).",
                    "type": "number",
                },
                "spread_volatility": {
                    "description": "Daily "
                    "absolute "
                    "spread "
                    "volatility "
                    "(decimal, "
                    "e.g. 0.0005 "
                    "= 5 "
                    "bps/day).",
                    "type": "number",
                },
            },
            "required": ["notional", "risky_annuity", "spread_volatility"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/credit_default_swap_var",
        "summary": "Parametric VaR of a single-name CDS position from spread risk.",
        "tool_name": "credit_default_swap_var",
    },
    {
        "description": "Maximises a mean-EL utility ``sum_i w_i (r_i - risk_aversion * EL_i)`` "
        "subject\n"
        "to ``sum w = 1`` and ``0 <= w_i <= max_weight``. With these box + simplex\n"
        "constraints the solution is a greedy water-filling onto the highest\n"
        "risk-adjusted scores, which is the exact optimum for a linear objective.\n"
        "\n"
        "No generic LP/QP solver is called anywhere in this function — the\n"
        "closed-form greedy allocation coded here is exact for this specific\n"
        "linear-objective, box-plus-simplex problem shape only.",
        "domain": "credit-risk",
        "function_name": "credit_portfolio_optimisation",
        "input_schema": {
            "properties": {
                "expected_losses": {
                    "description": "``(n,)`` " "per-asset " "expected loss " "rates (>= 0).",
                    "type": "object",
                },
                "expected_returns": {
                    "description": "``(n,)`` " "per-asset " "expected " "returns.",
                    "type": "object",
                },
                "max_weight": {
                    "default": 1.0,
                    "description": "Per-name " "concentration cap " "in ``(0, 1]``.",
                    "type": "number",
                },
                "risk_aversion": {
                    "default": 1.0,
                    "description": "Penalty applied " "to expected " "loss (>= 0).",
                    "type": "number",
                },
            },
            "required": ["expected_returns", "expected_losses"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/credit_portfolio_optimisation",
        "summary": "Single-period credit-portfolio weight optimisation (return vs expected loss).",
        "tool_name": "credit_portfolio_optimisation",
    },
    {
        "description": "Uses the credit-triangle approximation hazard ``lambda(t) = spread(t) / "
        "LGD``\n"
        "on each tenor, giving survival ``S(t) = exp(-lambda * t)`` with a "
        "piecewise\n"
        "hazard between consecutive tenors. This is the standard quick bootstrap;\n"
        "the full ISDA bootstrap solves leg-PV = 0 per tenor (handled by\n"
        ":func:`cds_pricing_isda_standard` when validating).",
        "domain": "credit-risk",
        "function_name": "credit_spread_curve_bootstrap",
        "input_schema": {
            "properties": {
                "par_spreads": {
                    "description": "Par CDS spreads " "per tenor " "(decimal, >= 0).",
                    "type": "object",
                },
                "recovery_rate": {
                    "default": 0.4,
                    "description": "Recovery rate " "in ``[0, 1)``.",
                    "type": "number",
                },
                "tenors": {
                    "description": "Strictly increasing " "CDS tenors in years (> " "0).",
                    "type": "object",
                },
            },
            "required": ["tenors", "par_spreads"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/credit_spread_curve_bootstrap",
        "summary": "Bootstrap a piecewise-constant hazard / survival curve from CDS spreads.",
        "tool_name": "credit_spread_curve_bootstrap",
    },
    {
        "description": "Applies a supervisory-style stress (e.g. EBA adverse scenario) by scaling\n"
        "PD and LGD, clipping to ``[0, 1]``, and reports the baseline vs stressed\n"
        "expected loss and the incremental impairment.\n"
        "\n"
        "The baseline EL leg is the definitional ``PD*LGD*EAD``, but the\n"
        "multiplicative PD/LGD shock structure itself is a bespoke internal\n"
        "stress design, confirmed against BIS/EBA sources not to reproduce any\n"
        "specific published adverse-scenario formula.",
        "domain": "credit-risk",
        "function_name": "credit_stress_testing",
        "input_schema": {
            "properties": {
                "ead": {"description": "``(n,)`` EAD per exposure " "(>= 0).", "type": "object"},
                "lgd": {
                    "description": "``(n,)`` baseline LGD per " "exposure in ``[0, 1]``.",
                    "type": "object",
                },
                "lgd_shock_multiplier": {
                    "default": 1.2,
                    "description": "Multiplier " "applied " "to LGD " "under " "stress " "(>= 1).",
                    "type": "number",
                },
                "pd": {
                    "description": "``(n,)`` baseline PD per " "exposure in ``[0, 1]``.",
                    "type": "object",
                },
                "pd_shock_multiplier": {
                    "default": 1.5,
                    "description": "Multiplier " "applied " "to PD " "under " "stress " "(>= 1).",
                    "type": "number",
                },
            },
            "required": ["pd", "lgd", "ead"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/credit_stress_testing",
        "summary": "Credit stress test: multiplicative PD/LGD shocks on the loss profile.",
        "tool_name": "credit_stress_testing",
    },
    {
        "description": "The market price of counterparty default risk:\n"
        "``CVA = LGD * sum_k EPE_k * DF_k * (S_{k-1} - S_k)`` with LGD = 1 - R and "
        "a\n"
        "flat hazard ``lambda = spread / LGD`` (credit-triangle approximation).",
        "domain": "credit-risk",
        "function_name": "credit_valuation_adjustment_cva",
        "input_schema": {
            "properties": {
                "credit_spread": {
                    "description": "Counterparty "
                    "CDS spread "
                    "(decimal, e.g. "
                    "0.01 = 100 "
                    "bps).",
                    "type": "number",
                },
                "discount_factors": {
                    "description": "``(n,)`` " "risk-free " "discount " "factors in " "``(0, 1]``.",
                    "type": "object",
                },
                "expected_exposure": {
                    "description": "``(n,)`` " "discounted-or-not " "EPE per " "bucket (>= " "0).",
                    "type": "object",
                },
                "recovery_rate": {
                    "default": 0.4,
                    "description": "Counterparty " "recovery rate " "in ``[0, 1)``.",
                    "type": "number",
                },
                "time_steps": {
                    "description": "``(n,)`` strictly " "increasing bucket " "end-times (years).",
                    "type": "object",
                },
            },
            "required": ["expected_exposure", "time_steps", "discount_factors", "credit_spread"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/credit_valuation_adjustment_cva",
        "summary": "Unilateral Credit Valuation Adjustment.",
        "tool_name": "credit_valuation_adjustment_cva",
    },
    {
        "description": "The Vasicek (2002) asymptotic single-risk-factor loss rate at confidence q "
        "is\n"
        "``L(q) = LGD * N( (N^{-1}(PD) + sqrt(rho) N^{-1}(q)) / sqrt(1-rho) )`` — "
        "the\n"
        "same conditional-default formula underlying the Basel IRB charge. VaR is "
        "the\n"
        "loss rate times total EAD; UL is the VaR in excess of EL.",
        "domain": "credit-risk",
        "function_name": "credit_var_analytical_vasicek",
        "input_schema": {
            "properties": {
                "asset_correlation": {
                    "default": 0.15,
                    "description": "Asset " "correlation " "rho in " "``[0, 1)``.",
                    "type": "number",
                },
                "confidence_level": {
                    "default": 0.999,
                    "description": "VaR " "confidence " "in ``[0.90, " "0.9999]``.",
                    "type": "number",
                },
                "ead_total": {
                    "description": "Total portfolio " "exposure at default " "(>= 0).",
                    "type": "number",
                },
                "lgd": {"description": "Loss given default in " "``[0, 1]``.", "type": "number"},
                "pd": {
                    "description": "Portfolio probability of " "default in ``(0, 1)``.",
                    "type": "number",
                },
            },
            "required": ["pd", "lgd", "ead_total"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/credit_var_analytical_vasicek",
        "summary": "Analytical Vasicek large-homogeneous-portfolio Credit VaR.",
        "tool_name": "credit_var_analytical_vasicek",
    },
    {
        "description": "Simulates correlated defaults, aggregates ``LGD * EAD`` losses, and reads\n"
        "the loss quantile (VaR) and the mean tail loss (ES / CVaR). Expected Loss "
        "is\n"
        "the simulation mean; Unexpected Loss is ``VaR - EL`` (economic-capital\n"
        "convention).",
        "domain": "credit-risk",
        "function_name": "credit_var_monte_carlo",
        "input_schema": {
            "properties": {
                "asset_correlation": {
                    "default": 0.15,
                    "description": "Scalar or "
                    "per-obligor "
                    "asset "
                    "correlation "
                    "rho in "
                    "``[0, 1)``.",
                    "type": "object",
                },
                "confidence_level": {
                    "default": 0.999,
                    "description": "VaR "
                    "confidence "
                    "in ``[0.90, "
                    "0.9999]`` "
                    "(Basel "
                    "99.9%).",
                    "type": "number",
                },
                "ead": {
                    "description": "Per-obligor exposure at " "default (>= 0).",
                    "type": "object",
                },
                "lgd": {
                    "description": "Per-obligor loss given " "default in ``[0, 1]``.",
                    "type": "object",
                },
                "n_simulations": {
                    "default": 50000,
                    "description": "Number of " "Monte-Carlo " "paths.",
                    "type": "integer",
                },
                "pd": {
                    "description": "Per-obligor probability of " "default in ``(0, 1)``.",
                    "type": "object",
                },
                "seed": {
                    "default": 12345,
                    "description": "RNG seed for " "reproducibility.",
                    "type": "integer",
                },
            },
            "required": ["pd", "lgd", "ead"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/credit_var_monte_carlo",
        "summary": "Monte-Carlo Credit VaR under a one-factor Gaussian copula.",
        "tool_name": "credit_var_monte_carlo",
    },
    {
        "description": "By default (the three transition-matrix arguments omitted) this is a\n"
        "default/no-default reduction of J.P. Morgan's CreditMetrics: latent asset\n"
        "returns are driven by a single common factor; an obligor defaults when "
        "its\n"
        "return breaches ``N^{-1}(PD)``, incurring ``LGD * exposure``. In this "
        "mode\n"
        "it is a direct pass-through to the same one-factor Gaussian-copula Monte\n"
        "Carlo engine used by :func:`credit_var_monte_carlo` (identical formula,\n"
        "identical code path) — unchanged from before this function supported the\n"
        "multi-state mode below.\n"
        "\n"
        "Pass ``transition_matrix``, ``current_rating`` and ``state_loss_pct``\n"
        "together to switch to the genuine multi-state CreditMetrics model: each\n"
        "obligor's simulated asset return is mapped through *its own*\n"
        "transition-matrix row (Gupton, Finger & Bhatia 1997, the CreditMetrics\n"
        "Technical Document's asset-return discretisation) to a migrated rating\n"
        "state — not just default/survive — and the loss for that path is that\n"
        "state's ``state_loss_pct`` of exposure (or ``LGD * exposure`` if the\n"
        "migration lands in default). ``pd``/``lgd`` still drive the default\n"
        "boundary and loss in multi-state mode: the caller's per-obligor ``pd``\n"
        "OVERRIDES ``transition_matrix``'s own default column for that obligor's\n"
        "row, rather than the two being independently averaged or the matrix's\n"
        "figure silently winning. To preserve the matrix's migration *shape* under\n"
        "that override, the non-default cumulative transition probabilities are\n"
        "affinely rescaled from ``[matrix's own default prob, 1]`` onto\n"
        "``[pd, 1]`` — so relative proportions between non-default states are\n"
        "unchanged, only the total probability mass assigned to default moves to\n"
        "match ``pd`` exactly.\n"
        "\n"
        "Rating-state convention (matches\n"
        ":func:`engine.credit_scoring.ratings_migration_matrix`'s own \"n_states,\n"
        'including default as the last"): index 0 is the best rating, index\n'
        "``n_states - 2`` the worst non-default rating, and index ``n_states - 1``\n"
        "is always default.",
        "domain": "credit-risk",
        "function_name": "creditmetrics_portfolio_model",
        "input_schema": {
            "properties": {
                "asset_correlation": {
                    "default": 0.2,
                    "description": "Common-factor " "asset " "correlation " "in ``[0, " "1)``.",
                    "type": "number",
                },
                "confidence_level": {
                    "default": 0.99,
                    "description": "VaR " "confidence " "in ``[0.90, " "0.9999]``.",
                    "type": "number",
                },
                "current_rating": {
                    "description": "Multi-state "
                    "only. "
                    "Per-obligor "
                    "starting "
                    "rating index "
                    "in ``[0, "
                    "n_states - "
                    "1)`` (an "
                    "obligor cannot "
                    "start already "
                    "in default).",
                    "type": "object",
                },
                "exposures": {"description": "Per-obligor " "exposure (>= 0).", "type": "object"},
                "lgd": {
                    "description": "Per-obligor LGD in ``[0, "
                    "1]`` — always used for "
                    "the default-state loss, "
                    "in both modes.",
                    "type": "object",
                },
                "n_simulations": {
                    "default": 20000,
                    "description": "Number of " "Monte-Carlo " "paths.",
                    "type": "integer",
                },
                "pd": {
                    "description": "Per-obligor PD in ``(0, "
                    "1)`` — always used for the "
                    "default threshold, in both "
                    "modes. In multi-state mode "
                    "this OVERRIDES "
                    "``transition_matrix``'s "
                    "own default probability "
                    "for that obligor (see "
                    "above), it is not blended "
                    "or ignored.",
                    "type": "object",
                },
                "seed": {"default": 2024, "description": "RNG seed.", "type": "integer"},
                "state_loss_pct": {
                    "description": "Multi-state "
                    "only. "
                    "``(n_states - "
                    "1,)`` loss "
                    "percentage of "
                    "exposure if "
                    "migrated to "
                    "each "
                    "non-default "
                    "state (index 0 "
                    "= best "
                    "rating). The "
                    "default "
                    "state's loss "
                    "always comes "
                    "from that "
                    "obligor's own "
                    "``lgd``, not "
                    "from this "
                    "array.",
                    "type": "object",
                },
                "transition_matrix": {
                    "description": "Multi-state "
                    "only. "
                    "Row-stochastic "
                    "``(n_states, "
                    "n_states)`` "
                    "rating "
                    "transition "
                    "matrix "
                    "(rows sum "
                    "to 1).",
                    "type": "object",
                },
            },
            "required": ["exposures", "pd", "lgd"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/creditmetrics_portfolio_model",
        "summary": "CreditMetrics portfolio loss distribution — two-state or genuine multi-state.",
        "tool_name": "creditmetrics_portfolio_model",
    },
    {
        "description": "``EAD = max(MtM, 0) + notional * add_on_factor``. The add-on factor is "
        "the\n"
        "supervisory percentage by asset class and residual maturity (e.g. 0.5% IR\n"
        "< 1y, 1.5% IR 1-5y, 6% equity). CEM is superseded by SA-CCR but retained "
        "for\n"
        "legacy reporting.",
        "domain": "credit-risk",
        "function_name": "current_exposure_method_cem",
        "input_schema": {
            "properties": {
                "add_on_factor": {
                    "description": "Supervisory " "add-on factor " "in ``[0, 1]``.",
                    "type": "number",
                },
                "mark_to_market": {
                    "description": "Current MtM " "(replacement " "cost " "component).",
                    "type": "number",
                },
                "notional": {
                    "description": "Trade / netting-set " "notional (>= 0).",
                    "type": "number",
                },
            },
            "required": ["mark_to_market", "notional", "add_on_factor"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/current_exposure_method_cem",
        "summary": "Basel I/II Current Exposure Method (CEM) EAD.",
        "tool_name": "current_exposure_method_cem",
    },
    {
        "description": "Computes the base CVA and:\n"
        "  * ``cs01``: the change in CVA for a +1 bp parallel shift in the credit\n"
        "    spread (finite-difference), the dominant CVA Greek for capital and\n"
        "    hedging.\n"
        "  * ``exposure_delta``: sensitivity to a 1% uniform scaling of the EPE\n"
        "    profile (linear, so exact = CVA * 0.01).",
        "domain": "credit-risk",
        "function_name": "cva_sensitivity_cva_greeks",
        "input_schema": {
            "properties": {
                "credit_spread": {
                    "description": "Counterparty " "CDS spread " "(decimal).",
                    "type": "number",
                },
                "discount_factors": {
                    "description": "``(n,)`` " "discount " "factors in " "``(0, 1]``.",
                    "type": "object",
                },
                "expected_exposure": {
                    "description": "``(n,)`` " "EPE per " "bucket (>= " "0).",
                    "type": "object",
                },
                "recovery_rate": {
                    "default": 0.4,
                    "description": "Counterparty " "recovery rate " "in ``[0, 1)``.",
                    "type": "number",
                },
                "spread_bump": {
                    "default": 0.0001,
                    "description": "Spread shift for " "the CS01 bump " "(default 1 bp).",
                    "type": "number",
                },
                "time_steps": {
                    "description": "``(n,)`` strictly " "increasing bucket " "end-times (years).",
                    "type": "object",
                },
            },
            "required": ["expected_exposure", "time_steps", "discount_factors", "credit_spread"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/cva_sensitivity_cva_greeks",
        "summary": "CVA sensitivities — CS01 (credit delta) and exposure delta.",
        "tool_name": "cva_sensitivity_cva_greeks",
    },
    {
        "description": "DVA mirrors CVA using the *negative* expected exposure (the amount the "
        "bank\n"
        "owes) and the bank's *own* credit spread. It is a gain to the reporting\n"
        "entity (own default extinguishes a liability).\n"
        "\n"
        "Under the hood this simply calls :func:`credit_valuation_adjustment_cva`\n"
        "on the negative-exposure profile with the bank's own spread and recovery\n"
        "substituted in, rather than a separately derived formula.",
        "domain": "credit-risk",
        "function_name": "debt_valuation_adjustment_dva",
        "input_schema": {
            "properties": {
                "discount_factors": {
                    "description": "``(n,)`` " "discount " "factors in " "``(0, 1]``.",
                    "type": "object",
                },
                "expected_negative_exposure": {
                    "description": "``(n,)`` " "ENE " "per " "bucket " "(>= " "0, " "magnitude).",
                    "type": "object",
                },
                "own_credit_spread": {
                    "description": "The bank's " "own CDS " "spread " "(decimal).",
                    "type": "number",
                },
                "own_recovery_rate": {
                    "default": 0.4,
                    "description": "The bank's " "own " "recovery " "rate in " "``[0, 1)``.",
                    "type": "number",
                },
                "time_steps": {
                    "description": "``(n,)`` strictly " "increasing bucket " "end-times.",
                    "type": "object",
                },
            },
            "required": [
                "expected_negative_exposure",
                "time_steps",
                "discount_factors",
                "own_credit_spread",
            ],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/debt_valuation_adjustment_dva",
        "summary": "Debit Valuation Adjustment — the symmetric own-default benefit.",
        "tool_name": "debt_valuation_adjustment_dva",
    },
    {
        "description": "The default correlation between two obligors is\n"
        "``rho_D = (P(both default) - PD_i PD_j) / sqrt(PD_i(1-PD_i) "
        "PD_j(1-PD_j))``\n"
        "where the joint default probability is the bivariate normal CDF\n"
        "``Phi_2(N^{-1}(PD_i), N^{-1}(PD_j); rho_A)`` with asset correlation rho_A.",
        "domain": "credit-risk",
        "function_name": "default_correlation_matrix",
        "input_schema": {
            "properties": {
                "asset_correlation": {
                    "description": "Symmetric "
                    "``(n, n)`` "
                    "asset-correlation "
                    "matrix with "
                    "unit "
                    "diagonal, "
                    "entries in "
                    "``[-1, "
                    "1]``.",
                    "type": "object",
                },
                "pd": {"description": "Per-obligor PD in ``(0, " "1)``.", "type": "object"},
            },
            "required": ["pd", "asset_correlation"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/default_correlation_matrix",
        "summary": "Pairwise default correlation from asset correlations (Gaussian copula).",
        "tool_name": "default_correlation_matrix",
    },
    {
        "description": "CRR Art. 181 requires LGD to reflect economic-downturn conditions when\n"
        "these are more conservative than the long-run average. Two scaling\n"
        "methods are available:\n"
        "\n"
        '- ``"multiplicative"`` (default, backward-compatible): a transparent\n'
        "  multiplicative scaling, ``LGD_LR * multiplier``, clipped to\n"
        "  ``[floor, 1]`` so the result never under-states the long-run LGD.\n"
        "  Calibrate ``downturn_multiplier`` to your own downturn analysis —\n"
        "  this is not itself a formula prescribed by CRR Art. 181 or EBA GL.\n"
        '- ``"additive"``: the EBA/GL/2019/03 supervisory-style fallback add-on,\n'
        "  ``LGD_downturn = LGD_LR + max(0, multiplier - 1) * (1 - LGD_LR) * 0.5``\n"
        '  — here ``downturn_multiplier`` plays the same "how severe" role as in\n'
        "  the multiplicative method, scaling how much of the remaining\n"
        "  loss-given-default headroom (``1 - LGD_LR``) the downturn add-on\n"
        "  consumes, rather than scaling ``LGD_LR`` itself directly.",
        "domain": "credit-risk",
        "function_name": "downturn_lgd_adjustment",
        "input_schema": {
            "properties": {
                "downturn_multiplier": {
                    "default": 1.0,
                    "description": "Multiplier " "(>= 1) " "reflecting " "downturn " "severity.",
                    "type": "number",
                },
                "floor": {
                    "default": 0.0,
                    "description": "Regulatory LGD floor "
                    "(e.g. 0.05 for retail "
                    "mortgages, CRR Art. "
                    "164).",
                    "type": "number",
                },
                "lgd_long_run": {
                    "description": "Long-run average " "LGD in ``[0, " "1]``.",
                    "type": "number",
                },
                "method": {
                    "default": "multiplicative",
                    "description": '``"multiplicative"`` ' "(default) or " '``"additive"``.',
                    "type": "string",
                },
            },
            "required": ["lgd_long_run"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/downturn_lgd_adjustment",
        "summary": "Basel downturn-LGD adjustment of a long-run average LGD.",
        "tool_name": "downturn_lgd_adjustment",
    },
    {
        "description": "The Effective Expected Exposure is the running maximum of EE\n"
        "``EEE(t) = max(EEE(t-1), EE(t))`` (it never decreases, capturing "
        "roll-over\n"
        "risk). EEPE is the time-weighted average of EEE over the first year "
        "(CRE53).\n"
        "EAD = alpha * EEPE downstream.",
        "domain": "credit-risk",
        "function_name": "effective_epe_regulatory",
        "input_schema": {
            "properties": {
                "expected_exposure": {
                    "description": "``(n,)`` " "expected-exposure " "profile (>= " "0).",
                    "type": "object",
                },
                "time_steps": {
                    "description": "``(n,)`` strictly " "increasing time " "points (years).",
                    "type": "object",
                },
            },
            "required": ["expected_exposure", "time_steps"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/effective_epe_regulatory",
        "summary": "Basel Effective EPE (EEPE) with the non-decreasing Effective EE profile.",
        "tool_name": "effective_epe_regulatory",
    },
    {
        "description": "",
        "domain": "credit-risk",
        "function_name": "expected_loss_el_computation",
        "input_schema": {
            "properties": {
                "ead": {
                    "description": "Exposure at default " "(currency amount, >= 0).",
                    "type": "number",
                },
                "lgd": {"description": "Loss given default in " "``[0, 1]``.", "type": "number"},
                "pd": {"description": "Probability of default in " "``[0, 1]``.", "type": "number"},
            },
            "required": ["pd", "lgd", "ead"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/expected_loss_el_computation",
        "summary": "Expected Loss ``EL = PD * LGD * EAD``.",
        "tool_name": "expected_loss_el_computation",
    },
    {
        "description": "EPE is the time-average of the expected-exposure profile over the horizon\n"
        "(CRE53): ``EPE = (1/T) * integral_0^T EE(t) dt`` approximated by the\n"
        "trapezoidal rule on the supplied grid.",
        "domain": "credit-risk",
        "function_name": "expected_positive_exposure_epe",
        "input_schema": {
            "properties": {
                "expected_exposure": {
                    "description": "``(n,)`` " "expected-exposure " "profile " "EE(t) (>= " "0).",
                    "type": "object",
                },
                "time_steps": {
                    "description": "``(n,)`` strictly "
                    "increasing time "
                    "points (years), "
                    "starting at or "
                    "after 0.",
                    "type": "object",
                },
            },
            "required": ["expected_exposure", "time_steps"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/expected_positive_exposure_epe",
        "summary": "Expected Positive Exposure — time-weighted average expected exposure.",
        "tool_name": "expected_positive_exposure_epe",
    },
    {
        "description": "``EAD = drawn + CCF * undrawn``. The CCF (a.k.a. credit-conversion "
        "factor)\n"
        "captures the share of the currently undrawn commitment expected to be "
        "drawn\n"
        "by the time of default. Basel F-IRB uses 0.75 for unconditionally\n"
        "cancellable commitments unless otherwise specified.",
        "domain": "credit-risk",
        "function_name": "exposure_at_default_ead_calculator",
        "input_schema": {
            "properties": {
                "credit_conversion_factor": {
                    "default": 0.75,
                    "description": "CCF "
                    "in "
                    "``[0, "
                    "1]`` "
                    "applied "
                    "to "
                    "the "
                    "undrawn "
                    "part.",
                    "type": "number",
                },
                "drawn": {
                    "description": "Currently drawn " "(on-balance-sheet) " "amount.",
                    "type": "number",
                },
                "undrawn": {
                    "description": "Undrawn committed " "(off-balance-sheet) " "amount.",
                    "type": "number",
                },
            },
            "required": ["drawn", "undrawn"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/exposure_at_default_ead_calculator",
        "summary": "EAD for a revolving / committed facility via the CCF method.",
        "tool_name": "exposure_at_default_ead_calculator",
    },
    {
        "description": "Note: when ``survival_probability`` is omitted it defaults to 1 at every\n"
        "bucket, i.e. the FVA is computed with no counterparty-default\n"
        "conditioning applied.\n"
        "\n"
        "``FVA = funding_spread * sum_k EPE_k * DF_k * S_k * dt_k`` — the present\n"
        "value of the funding-spread carry on the expected exposure over each\n"
        "interval, conditional on counterparty survival.",
        "domain": "credit-risk",
        "function_name": "funding_valuation_adjustment_fva",
        "input_schema": {
            "properties": {
                "discount_factors": {
                    "description": "``(n,)`` " "discount " "factors in " "``(0, 1]``.",
                    "type": "object",
                },
                "expected_exposure": {
                    "description": "``(n,)`` " "EPE per " "bucket (>= " "0).",
                    "type": "object",
                },
                "funding_spread": {
                    "description": "Bank funding " "spread over " "risk-free " "(decimal).",
                    "type": "number",
                },
                "survival_probability": {
                    "description": "Optional "
                    "``(n,)`` "
                    "counterparty "
                    "survival "
                    "at each "
                    "bucket "
                    "end; "
                    "defaults "
                    "to "
                    "all-ones "
                    "(no "
                    "default "
                    "conditioning).",
                    "type": "object",
                },
                "time_steps": {
                    "description": "``(n,)`` strictly " "increasing bucket " "end-times (years).",
                    "type": "object",
                },
            },
            "required": ["expected_exposure", "time_steps", "discount_factors", "funding_spread"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/funding_valuation_adjustment_fva",
        "summary": "Funding Valuation Adjustment — cost of funding uncollateralised exposure.",
        "tool_name": "funding_valuation_adjustment_fva",
    },
    {
        "description": "For Stage 1 exposures ECL uses the 12-month PD:\n"
        "``ECL = PD_12m * LGD * EAD * DF``.",
        "domain": "credit-risk",
        "function_name": "ifrs_9_12_month_ecl_stage_1",
        "input_schema": {
            "properties": {
                "discount_factor": {
                    "default": 1.0,
                    "description": "Discount "
                    "factor to the "
                    "reporting "
                    "date in ``(0, "
                    "1]``.",
                    "type": "number",
                },
                "ead": {"description": "Exposure at default (>= " "0).", "type": "number"},
                "lgd": {"description": "Loss given default in " "``[0, 1]``.", "type": "number"},
                "pd_12m": {
                    "description": "12-month probability " "of default in ``[0, " "1]``.",
                    "type": "number",
                },
            },
            "required": ["pd_12m", "lgd", "ead"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/ifrs_9_12_month_ecl_stage_1",
        "summary": "IFRS 9 Stage 1 (12-month) Expected Credit Loss.",
        "tool_name": "ifrs_9_12_month_ecl_stage_1",
    },
    {
        "description": "Lifetime ECL sums discounted expected loss across all future periods "
        "using\n"
        "the *marginal* (per-period) PD term structure:\n"
        "``ECL = sum_t marginal_PD_t * LGD_t * EAD_t * DF_t``. For Stage 3 the PD "
        "is\n"
        "effectively 1 in the first period (already defaulted); callers pass the\n"
        "appropriate marginal-PD vector.",
        "domain": "credit-risk",
        "function_name": "ifrs_9_lifetime_ecl_stage_2_3",
        "input_schema": {
            "properties": {
                "discount_factors": {
                    "description": "``(n,)`` " "discount " "factors in " "``(0, 1]``.",
                    "type": "object",
                },
                "ead": {"description": "``(n,)`` per-period EAD " "(>= 0).", "type": "object"},
                "lgd": {
                    "description": "``(n,)`` per-period LGD " "in ``[0, 1]``.",
                    "type": "object",
                },
                "marginal_pd": {
                    "description": "``(n,)`` "
                    "per-period "
                    "marginal default "
                    "probabilities in "
                    "``[0, 1]`` "
                    "(should sum to <= "
                    "1).",
                    "type": "object",
                },
                "stage": {
                    "default": 2,
                    "description": "Reported stage (2 or 3) " "for metadata.",
                    "type": "integer",
                },
            },
            "required": ["marginal_pd", "lgd", "ead", "discount_factors"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/ifrs_9_lifetime_ecl_stage_2_3",
        "summary": "IFRS 9 Stage 2/3 lifetime Expected Credit Loss.",
        "tool_name": "ifrs_9_lifetime_ecl_stage_2_3",
    },
    {
        "description": "IFRS 9 requires ECL to reflect an unbiased probability-weighted amount "
        "over\n"
        "multiple scenarios (base / upside / downside):\n"
        "``ECL = sum_s weight_s * ECL_s`` with weights summing to 1.",
        "domain": "credit-risk",
        "function_name": "ifrs_9_scenario_weighted_ecl",
        "input_schema": {
            "properties": {
                "scenario_ecls": {
                    "description": "``(s,)`` ECL " "per scenario " "(>= 0).",
                    "type": "object",
                },
                "scenario_weights": {
                    "description": "``(s,)`` " "scenario " "probabilities " "(>= 0, sum " "to ~1).",
                    "type": "object",
                },
            },
            "required": ["scenario_ecls", "scenario_weights"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/ifrs_9_scenario_weighted_ecl",
        "summary": "Probability-weighted ECL across forward-looking macro scenarios.",
        "tool_name": "ifrs_9_scenario_weighted_ecl",
    },
    {
        "description": "Stage 3 if credit-impaired (90+ days past due, the IFRS 9 rebuttable "
        "default\n"
        "presumption). Otherwise Stage 2 if a significant increase in credit risk "
        "has\n"
        "occurred — either the lifetime PD has risen by at least\n"
        "``sicr_relative_threshold`` times origination, OR the absolute PD "
        "increase\n"
        "exceeds ``sicr_absolute_threshold``. Else Stage 1.",
        "domain": "credit-risk",
        "function_name": "ifrs_9_stage_classification_pd_threshold",
        "input_schema": {
            "properties": {
                "days_past_due": {
                    "default": 0,
                    "description": "Days the " "exposure is " "past due (>= " "0).",
                    "type": "integer",
                },
                "pd_current": {
                    "description": "Current " "(reporting-date) " "lifetime PD in " "``[0, 1]``.",
                    "type": "number",
                },
                "pd_origination": {
                    "description": "Lifetime PD at " "initial " "recognition in " "``[0, 1]``.",
                    "type": "number",
                },
                "sicr_absolute_threshold": {
                    "default": 0.02,
                    "description": "Absolute " "PD " "increase " "triggering " "SICR.",
                    "type": "number",
                },
                "sicr_relative_threshold": {
                    "default": 2.0,
                    "description": "Relative " "PD " "multiple " "triggering " "SICR " "(>= " "1).",
                    "type": "number",
                },
            },
            "required": ["pd_current", "pd_origination"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/ifrs_9_stage_classification_pd_threshold",
        "summary": "IFRS 9 stage classification by the PD-threshold SICR rule.",
        "tool_name": "ifrs_9_stage_classification_pd_threshold",
    },
    {
        "description": "Extends the PD-threshold rule with qualitative backstops required by IFRS "
        "9:\n"
        "forbearance and internal watchlist status force at least Stage 2, while\n"
        "90+ days past due forces Stage 3. The final stage is the most severe of "
        "all\n"
        "triggered criteria.\n"
        "\n"
        "The quantitative leg reuses\n"
        ":func:`ifrs_9_stage_classification_pd_threshold`'s PD-threshold rule\n"
        "directly (including its ``sicr_relative_threshold`` parameter) rather\n"
        "than an independently coded SICR test.",
        "domain": "credit-risk",
        "function_name": "ifrs_9_staging_criteria_assessment",
        "input_schema": {
            "properties": {
                "days_past_due": {
                    "default": 0,
                    "description": "Days past due " "(>= 0).",
                    "type": "integer",
                },
                "forbearance": {
                    "default": False,
                    "description": "Whether the " "exposure is under " "forbearance " "measures.",
                    "type": "boolean",
                },
                "pd_current": {
                    "description": "Current lifetime " "PD in ``[0, 1]``.",
                    "type": "number",
                },
                "pd_origination": {
                    "description": "Origination " "lifetime PD in " "``[0, 1]``.",
                    "type": "number",
                },
                "sicr_relative_threshold": {
                    "default": 2.0,
                    "description": "Relative-PD " "SICR " "multiple " "(>= " "1).",
                    "type": "number",
                },
                "watchlist": {
                    "default": False,
                    "description": "Whether the " "exposure is on the " "internal watchlist.",
                    "type": "boolean",
                },
            },
            "required": ["pd_current", "pd_origination"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/ifrs_9_staging_criteria_assessment",
        "summary": "Full IFRS 9 staging assessment combining quantitative and qualitative SICR.",
        "tool_name": "ifrs_9_staging_criteria_assessment",
    },
    {
        "description": "Note: when ``correlation`` is not supplied it defaults to the Basel\n"
        "corporate correlation function of PD, the same formula F-IRB always uses.\n"
        "\n"
        "Under A-IRB the bank supplies its own PD, LGD, EAD and effective "
        "maturity.\n"
        "The risk-weight function is identical to F-IRB; only the parameter "
        "sources\n"
        "differ.",
        "domain": "credit-risk",
        "function_name": "irb_advanced_approach_capital",
        "input_schema": {
            "properties": {
                "correlation": {
                    "description": "Optional override "
                    "of the asset "
                    "correlation R "
                    "(e.g. for an SME "
                    "or "
                    "specialised-lending "
                    "adjustment); "
                    "``None`` uses the "
                    "Basel corporate "
                    "formula.",
                    "type": "object",
                },
                "ead": {
                    "description": "Own-estimate exposure at " "default (>= 0).",
                    "type": "number",
                },
                "lgd": {
                    "description": "Own-estimate loss given " "default in ``[0, 1]``.",
                    "type": "number",
                },
                "maturity": {
                    "default": 2.5,
                    "description": "Own-estimate " "effective maturity M " "in years.",
                    "type": "number",
                },
                "pd": {
                    "description": "Own-estimate probability " "of default in ``(0, 1]``.",
                    "type": "number",
                },
            },
            "required": ["pd", "lgd", "ead"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/irb_advanced_approach_capital",
        "summary": "Basel IRB Advanced-Approach capital (CRE31).",
        "tool_name": "irb_advanced_approach_capital",
    },
    {
        "description": "Note: unlike :func:`irb_advanced_approach_capital`, F-IRB exposes no\n"
        "override at all for the asset correlation R — it is always the Basel\n"
        "corporate correlation function of PD.\n"
        "\n"
        "Under F-IRB the bank supplies its own PD but uses *supervisory* LGD: 45% "
        "for\n"
        "senior unsecured and 75% for subordinated claims (CRE32). EAD and "
        "maturity\n"
        "are also supervisory (M defaults to 2.5 years).",
        "domain": "credit-risk",
        "function_name": "irb_foundation_approach_capital",
        "input_schema": {
            "properties": {
                "ead": {
                    "description": "Exposure at default " "(currency amount, >= 0).",
                    "type": "number",
                },
                "lgd": {
                    "default": 0.45,
                    "description": "Override supervisory LGD; "
                    "ignored unless "
                    "``seniority`` is custom.",
                    "type": "number",
                },
                "maturity": {
                    "default": 2.5,
                    "description": "Effective maturity M "
                    "in years "
                    "(supervisory default "
                    "2.5).",
                    "type": "number",
                },
                "pd": {
                    "description": "Own-estimate probability " "of default in ``(0, 1]``.",
                    "type": "number",
                },
                "seniority": {
                    "default": "senior_unsecured",
                    "description": '``"senior_unsecured"`` '
                    "(45%) or "
                    '``"subordinated"`` '
                    "(75%).",
                    "type": "string",
                },
            },
            "required": ["pd", "ead"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/irb_foundation_approach_capital",
        "summary": "Basel IRB Foundation-Approach capital (CRE31).",
        "tool_name": "irb_foundation_approach_capital",
    },
    {
        "description": "Note: when ``asset_drift`` is omitted, the asset drift mu used in the\n"
        "distance-to-default formula defaults to ``risk_free_rate`` (a\n"
        "risk-neutral assumption), not an estimate of the firm's actual expected\n"
        "asset return.\n"
        "\n"
        "In the structural Merton model the firm defaults at horizon T if asset "
        "value\n"
        "falls below the debt face value. The distance-to-default is\n"
        "``DD = (ln(V/D) + (mu - 0.5 sigma^2) T) / (sigma sqrt(T))`` and the model "
        "PD\n"
        "(expected default frequency) is ``N(-DD)``.",
        "domain": "credit-risk",
        "function_name": "kmv_merton_distance_to_default",
        "input_schema": {
            "properties": {
                "asset_drift": {
                    "description": "Expected asset "
                    "return mu; "
                    "defaults to "
                    "``risk_free_rate``.",
                    "type": "object",
                },
                "asset_value": {
                    "description": "Current market " "value of firm " "assets V (> 0).",
                    "type": "number",
                },
                "asset_volatility": {
                    "description": "Annualised " "asset return " "volatility " "sigma (> 0).",
                    "type": "number",
                },
                "debt_face_value": {
                    "description": "Default " "boundary / " "debt face " "value D (> " "0).",
                    "type": "number",
                },
                "horizon": {
                    "default": 1.0,
                    "description": "Horizon T in years (> " "0).",
                    "type": "number",
                },
                "risk_free_rate": {
                    "default": 0.0,
                    "description": "Risk-free rate " "(used when " "``asset_drift`` " "is None).",
                    "type": "number",
                },
            },
            "required": ["asset_value", "debt_face_value", "asset_volatility"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/kmv_merton_distance_to_default",
        "summary": "Merton / KMV distance-to-default and implied PD.",
        "tool_name": "kmv_merton_distance_to_default",
    },
    {
        "description": "Estimates ``PD = sigmoid(b0 + x·b)`` from a default indicator. A small "
        "ridge\n"
        "term stabilises the Hessian on separable / collinear data. An intercept "
        "is\n"
        "added automatically.\n"
        "\n"
        "Coefficients are found by iterative Newton-Raphson (IRLS) convergence to\n"
        "the maximum-likelihood estimate, not a closed-form solution.",
        "domain": "credit-risk",
        "function_name": "logistic_regression_pd_model",
        "input_schema": {
            "properties": {
                "defaults": {
                    "description": "``(n_samples,)`` "
                    "binary default "
                    "indicator in ``{0, "
                    "1}``.",
                    "type": "object",
                },
                "features": {
                    "description": "``(n_samples, "
                    "n_features)`` design "
                    "matrix (no intercept "
                    "col).",
                    "type": "object",
                },
                "max_iter": {
                    "default": 100,
                    "description": "Maximum Newton " "iterations.",
                    "type": "integer",
                },
                "ridge": {
                    "default": 1e-06,
                    "description": "L2 ridge added to the " "Hessian diagonal for " "stability.",
                    "type": "number",
                },
                "tol": {
                    "default": 1e-08,
                    "description": "Convergence tolerance on " "the coefficient update " "norm.",
                    "type": "number",
                },
            },
            "required": ["features", "defaults"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/logistic_regression_pd_model",
        "summary": "Fit a logistic-regression PD model by Newton-Raphson (IRLS) MLE.",
        "tool_name": "logistic_regression_pd_model",
    },
    {
        "description": "``LGD = 1 - (recoveries - costs) / EAD``, exposure-weighted across the\n"
        "facility sample and clipped to ``[0, 1]``.",
        "domain": "credit-risk",
        "function_name": "loss_given_default_lgd_model",
        "input_schema": {
            "properties": {
                "exposure_amounts": {
                    "description": "Exposure at " "default per " "facility (> " "0).",
                    "type": "object",
                },
                "recovery_amounts": {
                    "description": "Recovered " "amounts per " "defaulted " "facility.",
                    "type": "object",
                },
                "workout_cost_rate": {
                    "default": 0.0,
                    "description": "Workout "
                    "cost as a "
                    "fraction of "
                    "EAD "
                    "(subtracted "
                    "from "
                    "recoveries).",
                    "type": "number",
                },
            },
            "required": ["recovery_amounts", "exposure_amounts"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/loss_given_default_lgd_model",
        "summary": "Workout LGD as one minus the recovery rate, net of workout costs.",
        "tool_name": "loss_given_default_lgd_model",
    },
    {
        "description": "Many ML classifiers (gradient boosting, random forests) emit uncalibrated\n"
        "scores. Platt scaling fits a one-dimensional logistic map\n"
        "``PD = sigmoid(a * score + b)`` so the output is a true probability. The "
        "fit\n"
        "reuses the Newton-Raphson logistic solver on the single score feature.\n"
        "\n"
        "No scikit-learn or other ML library is involved anywhere in this module —\n"
        "the calibration is a hand-rolled fit on top of this file's own solver.",
        "domain": "credit-risk",
        "function_name": "machine_learning_pd_calibration",
        "input_schema": {
            "properties": {
                "defaults": {
                    "description": "``(n_samples,)`` " "binary default " "indicator.",
                    "type": "object",
                },
                "max_iter": {
                    "default": 100,
                    "description": "Maximum Newton " "iterations.",
                    "type": "integer",
                },
                "raw_scores": {
                    "description": "``(n_samples,)`` " "uncalibrated model " "scores.",
                    "type": "object",
                },
                "tol": {
                    "default": 1e-08,
                    "description": "Convergence tolerance.",
                    "type": "number",
                },
            },
            "required": ["raw_scores", "defaults"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/machine_learning_pd_calibration",
        "summary": "Platt-scaling calibration of raw ML scores into well-calibrated PDs.",
        "tool_name": "machine_learning_pd_calibration",
    },
    {
        "description": "Adjusts ECL for projected macro deviations via a multiplicative factor\n"
        "``adj = 1 + sum_j sensitivity_j * factor_j`` (clamped at 0), then adds a\n"
        "discretionary management overlay. Captures the IFRS 9 requirement to\n"
        "incorporate forward-looking information not in the through-the-cycle "
        "model.\n"
        "\n"
        "This multiplicative overlay structure is a bespoke internal design\n"
        "choice, confirmed against BIS/EBA sources not to reproduce a specific\n"
        "published or regulatory ECL-overlay formula.",
        "domain": "credit-risk",
        "function_name": "macroeconomic_overlays_ecl",
        "input_schema": {
            "properties": {
                "base_ecl": {"description": "Model base-case ECL " "(>= 0).", "type": "number"},
                "macro_factors": {
                    "description": "``(k,)`` "
                    "standardised "
                    "macro "
                    "deviations "
                    "(e.g. GDP, "
                    "unemp).",
                    "type": "object",
                },
                "management_overlay": {
                    "default": 0.0,
                    "description": "Additive " "post-model " "adjustment " "(can be " "negative).",
                    "type": "number",
                },
                "sensitivities": {
                    "description": "``(k,)`` ECL " "sensitivity " "(elasticity) to " "each factor.",
                    "type": "object",
                },
            },
            "required": ["base_ecl", "macro_factors", "sensitivities"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/macroeconomic_overlays_ecl",
        "summary": "Apply forward-looking macroeconomic overlays to a base ECL.",
        "tool_name": "macroeconomic_overlays_ecl",
    },
    {
        "description": "``MVA = spread * sum_k IM_k * DF_k * dt_k`` — present value of the carry "
        "on\n"
        "posting (and funding) initial margin that earns less than the bank's "
        "funding\n"
        "cost over the trade's life.",
        "domain": "credit-risk",
        "function_name": "margin_valuation_adjustment_mva",
        "input_schema": {
            "properties": {
                "discount_factors": {
                    "description": "``(n,)`` " "discount " "factors in " "``(0, 1]``.",
                    "type": "object",
                },
                "initial_margin_profile": {
                    "description": "``(n,)`` "
                    "expected "
                    "initial "
                    "margin "
                    "posted "
                    "per "
                    "bucket "
                    "(>= "
                    "0).",
                    "type": "object",
                },
                "margin_funding_spread": {
                    "description": "Spread "
                    "between "
                    "funding "
                    "cost "
                    "and "
                    "margin "
                    "remuneration.",
                    "type": "number",
                },
                "time_steps": {
                    "description": "``(n,)`` strictly " "increasing bucket " "end-times (years).",
                    "type": "object",
                },
            },
            "required": [
                "initial_margin_profile",
                "time_steps",
                "discount_factors",
                "margin_funding_spread",
            ],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/margin_valuation_adjustment_mva",
        "summary": "Margin Valuation Adjustment — funding cost of posted initial margin.",
        "tool_name": "margin_valuation_adjustment_mva",
    },
    {
        "description": "``b(PD) = (0.11852 - 0.05478 ln PD)^2`` and\n"
        "``MA = (1 + (M - 2.5) b) / (1 - 1.5 b)``. At M = 2.5 the adjustment is\n"
        "exactly 1.0 by construction.",
        "domain": "credit-risk",
        "function_name": "maturity_adjustment_basel_irb",
        "input_schema": {
            "properties": {
                "maturity": {
                    "description": "Effective maturity M "
                    "in years (Basel caps "
                    "M at 5, floors at 1 "
                    "for most exposures; "
                    "not enforced here so "
                    "the raw factor is "
                    "exposed).",
                    "type": "number",
                },
                "pd": {"description": "Probability of default in " "``(0, 1]``.", "type": "number"},
            },
            "required": ["pd", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/maturity_adjustment_basel_irb",
        "summary": "Basel IRB maturity adjustment (CRE31.6).",
        "tool_name": "maturity_adjustment_basel_irb",
    },
    {
        "description": "Inverse of the TTC transform: shifts the probit-domain TTC score by a\n"
        "sensitivity-scaled standardised macro index ``z`` (negative ``z`` = "
        "adverse\n"
        "conditions raise the PD): ``score_PIT = N^{-1}(PD_TTC) - sensitivity * "
        "z``.",
        "domain": "credit-risk",
        "function_name": "point_in_time_pd_estimation",
        "input_schema": {
            "properties": {
                "macro_index": {
                    "description": "Standardised "
                    "macroeconomic "
                    "index (z-score; "
                    "positive = good "
                    "conditions).",
                    "type": "number",
                },
                "sensitivity": {
                    "default": 1.0,
                    "description": "Loading of the " "score on the " "macro factor (>= " "0).",
                    "type": "number",
                },
                "ttc_pd": {
                    "description": "Through-the-cycle PD " "in ``(0, 1)``.",
                    "type": "number",
                },
            },
            "required": ["ttc_pd", "macro_index"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/point_in_time_pd_estimation",
        "summary": "Derive a point-in-time PD from a TTC PD and a macro factor.",
        "tool_name": "point_in_time_pd_estimation",
    },
    {
        "description": "Simulates the netting-set value as ``V_t = V_0 + drift*t + "
        "sigma*sqrt(t)*Z``\n"
        "and reports the per-step PFE (high quantile of positive exposure) and the\n"
        "peak PFE. Randomness is pre-drawn in pure Python (RULE 3).\n"
        "\n"
        "PFE at each time step is the empirical quantile of the simulated exposure\n"
        "distribution rather than a closed-form expression, so results carry\n"
        "Monte Carlo sampling noise that varies with ``n_paths`` and ``seed``.",
        "domain": "credit-risk",
        "function_name": "potential_future_exposure_pfe",
        "input_schema": {
            "properties": {
                "drift": {
                    "default": 0.0,
                    "description": "Per-unit-time drift of " "the value process.",
                    "type": "number",
                },
                "initial_value": {
                    "description": "Current " "netting-set " "value V_0.",
                    "type": "number",
                },
                "n_paths": {
                    "default": 20000,
                    "description": "Number of Monte-Carlo " "paths.",
                    "type": "integer",
                },
                "quantile": {
                    "default": 0.95,
                    "description": "PFE confidence in " "``(0, 1)`` (default " "95%).",
                    "type": "number",
                },
                "seed": {"default": 909, "description": "RNG seed.", "type": "integer"},
                "time_steps": {
                    "description": "Strictly positive "
                    "time points "
                    "(years) at which "
                    "to profile.",
                    "type": "object",
                },
                "volatility": {
                    "description": "Per-sqrt-time " "value volatility " "sigma (>= 0).",
                    "type": "number",
                },
            },
            "required": ["initial_value", "volatility", "time_steps"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/potential_future_exposure_pfe",
        "summary": "Potential Future Exposure profile via Monte-Carlo (arithmetic BM proxy).",
        "tool_name": "potential_future_exposure_pfe",
    },
    {
        "description": "Computes the per-cohort default frequency and the obligor-weighted pooled\n"
        "PD, then applies the Basel regulatory floor (3 bps for non-defaulted\n"
        "exposures under CRR Art. 160/163).",
        "domain": "credit-risk",
        "function_name": "probability_of_default_pd_estimation",
        "input_schema": {
            "properties": {
                "floor": {
                    "default": 0.0003,
                    "description": "Regulatory PD floor " "applied to the pooled " "estimate.",
                    "type": "number",
                },
                "n_defaults": {
                    "description": "Defaults observed " "in each rating " "cohort.",
                    "type": "object",
                },
                "n_obligors": {
                    "description": "Obligors at risk " "at the start of " "each cohort.",
                    "type": "object",
                },
            },
            "required": ["n_defaults", "n_obligors"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/probability_of_default_pd_estimation",
        "summary": "Estimate PD from observed default cohorts (cohort / frequency method).",
        "tool_name": "probability_of_default_pd_estimation",
    },
    {
        "description": "Counts observed transitions and normalises each row to a probability\n"
        "distribution. Empty rows (no obligors observed in that state) are set to "
        "the\n"
        "identity (a self-transition), keeping the matrix row-stochastic.\n"
        "\n"
        "This identity substitution for empty rows is a modelling convention, not "
        "an\n"
        "observed transition — it exists purely so the returned matrix stays\n"
        "row-stochastic and is safe to chain into further calculations.",
        "domain": "credit-risk",
        "function_name": "ratings_migration_matrix",
        "input_schema": {
            "properties": {
                "from_rating": {
                    "description": "Integer "
                    "start-of-period "
                    "rating index per "
                    "obligor in ``[0, "
                    "n_states)``.",
                    "type": "object",
                },
                "n_states": {
                    "description": "Number of rating "
                    "states (including "
                    "default as the "
                    "last).",
                    "type": "integer",
                },
                "to_rating": {
                    "description": "Integer " "end-of-period " "rating index per " "obligor.",
                    "type": "object",
                },
            },
            "required": ["from_rating", "to_rating", "n_states"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/ratings_migration_matrix",
        "summary": "Estimate a row-stochastic ratings-migration matrix (cohort method).",
        "tool_name": "ratings_migration_matrix",
    },
    {
        "description": "Supports optional present-valuing of recoveries via per-facility discount\n"
        "factors (workout recoveries are received some time after default).",
        "domain": "credit-risk",
        "function_name": "recovery_rate_estimation",
        "input_schema": {
            "properties": {
                "discount_factors": {
                    "description": "Optional "
                    "per-facility "
                    "discount "
                    "factors in "
                    "``(0, 1]`` "
                    "applied to "
                    "recoveries; "
                    "``None`` "
                    "means no "
                    "discounting.",
                    "type": "object",
                },
                "exposure_amounts": {
                    "description": "Exposure at " "default per " "facility (> " "0).",
                    "type": "object",
                },
                "recovery_amounts": {
                    "description": "Nominal " "recovered " "amounts per " "facility.",
                    "type": "object",
                },
            },
            "required": ["recovery_amounts", "exposure_amounts"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/recovery_rate_estimation",
        "summary": "Estimate the recovery rate (1 - LGD) from a defaulted-facility sample.",
        "tool_name": "recovery_rate_estimation",
    },
    {
        "description": "A scorecard sums attribute points into a score; the score relates to odds "
        "by\n"
        "``odds = base_odds * 2^{(score - base_score)/pdo}`` (PDO = points to "
        "double\n"
        "the odds). PD = ``1 / (1 + odds)``.",
        "domain": "credit-risk",
        "function_name": "retail_scorecard_pd_model",
        "input_schema": {
            "properties": {
                "base_odds": {
                    "default": 50.0,
                    "description": "Good:bad odds at " "``base_score`` " "(e.g. 50:1).",
                    "type": "number",
                },
                "base_points": {
                    "description": "Intercept points " "added to the " "total.",
                    "type": "number",
                },
                "base_score": {
                    "default": 600.0,
                    "description": "Reference score at " "which odds equal " "``base_odds``.",
                    "type": "number",
                },
                "feature_values": {
                    "description": "``(n_features,)`` "
                    "per-attribute "
                    "binary/scaled "
                    "indicator.",
                    "type": "object",
                },
                "pdo": {
                    "default": 50.0,
                    "description": "Points to double the odds " "(industry default 50).",
                    "type": "number",
                },
                "points_per_feature": {
                    "description": "``(n_features,)`` " "points " "assigned " "per " "attribute.",
                    "type": "object",
                },
            },
            "required": ["feature_values", "points_per_feature", "base_points"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/retail_scorecard_pd_model",
        "summary": "Retail scorecard: additive points to a PD via the points-to-double-odds map.",
        "tool_name": "retail_scorecard_pd_model",
    },
    {
        "description": "Computes each sector's default rate, the obligor-weighted overall rate "
        "and\n"
        "each sector's relative risk versus the portfolio average (lift > 1 means "
        "the\n"
        "sector defaults more than average).",
        "domain": "credit-risk",
        "function_name": "sector_default_rate_analysis",
        "input_schema": {
            "properties": {
                "sector_defaults": {
                    "description": "Defaults " "observed per " "sector.",
                    "type": "object",
                },
                "sector_names": {
                    "description": "Optional labels; " "defaults to " "``sector_0, " "...``.",
                    "type": "object",
                },
                "sector_obligors": {
                    "description": "Obligors per " "sector (>= " "defaults).",
                    "type": "object",
                },
            },
            "required": ["sector_defaults", "sector_obligors"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/sector_default_rate_analysis",
        "summary": "Per-sector default-rate analysis with a concentration of distress.",
        "tool_name": "sector_default_rate_analysis",
    },
    {
        "description": "For SME corporate exposures (sales €5m-€50m) the asset correlation is\n"
        "reduced by a size term:\n"
        "``R_SME = R_corp - 0.04 * (1 - (S - 5)/45)`` with S clamped to ``[5, "
        "50]``.\n"
        "This lowers the capital charge for smaller, more idiosyncratic borrowers.",
        "domain": "credit-risk",
        "function_name": "sme_correlation_factor_basel",
        "input_schema": {
            "properties": {
                "annual_sales_millions": {
                    "description": "Total " "annual " "sales S " "in € " "millions.",
                    "type": "number",
                },
                "pd": {"description": "Probability of default in " "``(0, 1]``.", "type": "number"},
            },
            "required": ["pd", "annual_sales_millions"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/sme_correlation_factor_basel",
        "summary": "Basel SME firm-size correlation adjustment (CRE31.10).",
        "tool_name": "sme_correlation_factor_basel",
    },
    {
        "description": "Maps standard sovereign indicators into a ``[0, 100]`` creditworthiness\n"
        "score (higher = stronger): high debt/GDP and twin deficits reduce the "
        "score;\n"
        "larger FX reserves and stronger governance raise it. The score is mapped "
        "to\n"
        "an indicative PD via a logistic transform.\n"
        "\n"
        "This is a bespoke internal composite-indicator model, confirmed against\n"
        "BIS/EBA sources not to match any specific published sovereign-risk\n"
        "methodology (e.g. a rating-agency or IMF framework).",
        "domain": "credit-risk",
        "function_name": "sovereign_credit_risk_assessment",
        "input_schema": {
            "properties": {
                "current_account_pct": {
                    "description": "Current-account " "balance / " "GDP.",
                    "type": "number",
                },
                "debt_to_gdp": {
                    "description": "General-government " "debt / GDP (e.g. " "0.6 = 60%).",
                    "type": "number",
                },
                "fiscal_balance_pct": {
                    "description": "Fiscal " "balance / " "GDP " "(deficit " "negative).",
                    "type": "number",
                },
                "fx_reserves_months": {
                    "description": "FX " "reserves " "in months " "of imports " "(>= 0).",
                    "type": "number",
                },
                "governance_score": {
                    "description": "World-Bank-style " "governance " "index in " "``[0, 1]``.",
                    "type": "number",
                },
            },
            "required": [
                "debt_to_gdp",
                "fiscal_balance_pct",
                "current_account_pct",
                "fx_reserves_months",
                "governance_score",
            ],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/sovereign_credit_risk_assessment",
        "summary": "Composite sovereign credit-risk score from macro-fiscal indicators.",
        "tool_name": "sovereign_credit_risk_assessment",
    },
    {
        "description": "``EAD = alpha * (RC + PFE)`` where the replacement cost is\n"
        "``RC = max(MtM - collateral, 0)`` (unmargined) and ``PFE = multiplier *\n"
        "AddOn_aggregate`` with the regulatory recognition-of-excess-collateral\n"
        "multiplier ``multiplier = min(1, 0.05 + 0.95 * exp((MtM - C)/(1.9 * "
        "AddOn)))``.\n"
        "The supervisory ``alpha`` is 1.4.",
        "domain": "credit-risk",
        "function_name": "standardised_approach_ccr_sa_ccr",
        "input_schema": {
            "properties": {
                "add_on_aggregate": {
                    "description": "Aggregate " "asset-class " "add-on (>= " "0).",
                    "type": "number",
                },
                "alpha": {
                    "default": 1.4,
                    "description": "Supervisory scaling " "factor (default 1.4).",
                    "type": "number",
                },
                "collateral": {"description": "Net collateral " "held (>= 0).", "type": "number"},
                "mark_to_market": {
                    "description": "Current " "netting-set " "MtM.",
                    "type": "number",
                },
            },
            "required": ["mark_to_market", "collateral", "add_on_aggregate"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/standardised_approach_ccr_sa_ccr",
        "summary": "Basel SA-CCR EAD (CRE52).",
        "tool_name": "standardised_approach_ccr_sa_ccr",
    },
    {
        "description": "TTC PDs dampen the macro cycle for stable regulatory capital. A convex "
        "blend\n"
        "in the Gaussian-score (probit) domain is used so the result stays a valid\n"
        "probability: ``score_TTC = (1-w) score_PIT + w score_LRA`` with\n"
        "``w = cyclicality`` and ``score = N^{-1}(PD)``.",
        "domain": "credit-risk",
        "function_name": "through_the_cycle_pd_adjustment",
        "input_schema": {
            "properties": {
                "cyclicality": {
                    "default": 0.5,
                    "description": "Blend weight in "
                    "``[0, 1]`` toward "
                    "the long-run "
                    "anchor (0 = pure "
                    "PIT, 1 = pure "
                    "TTC).",
                    "type": "number",
                },
                "long_run_average_pd": {
                    "description": "Long-run " "central-tendency " "PD in " "``(0, " "1)``.",
                    "type": "number",
                },
                "pit_pd": {"description": "Point-in-time PD in " "``(0, 1)``.", "type": "number"},
            },
            "required": ["pit_pd", "long_run_average_pd"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/through_the_cycle_pd_adjustment",
        "summary": "Convert a point-in-time PD to a through-the-cycle PD.",
        "tool_name": "through_the_cycle_pd_adjustment",
    },
    {
        "description": "For a Bernoulli default with deterministic LGD, the stand-alone UL of one\n"
        "exposure is ``EAD * LGD * sqrt(PD(1-PD))`` — the loss standard deviation.\n"
        "The portfolio UL reported here is the *sum* of stand-alone ULs (i.e. the\n"
        "fully-correlated upper bound); correlation-aware UL is handled by the\n"
        "Vasicek / CreditMetrics models in :mod:`engine.credit_var`.",
        "domain": "credit-risk",
        "function_name": "unexpected_loss_ul_computation",
        "input_schema": {
            "properties": {
                "ead": {"description": "Per-exposure EAD array " "(>= 0).", "type": "object"},
                "lgd": {
                    "description": "Per-exposure LGD array in " "``[0, 1]``.",
                    "type": "object",
                },
                "pd": {"description": "Per-exposure PD array in " "``[0, 1]``.", "type": "object"},
            },
            "required": ["pd", "lgd", "ead"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/unexpected_loss_ul_computation",
        "summary": "Stand-alone Unexpected Loss per exposure and the un-diversified sum.",
        "tool_name": "unexpected_loss_ul_computation",
    },
    {
        "description": "When exposure rises as the counterparty's credit deteriorates (positive\n"
        "correlation), CVA is understated. A first-order alpha multiplier\n"
        "``alpha = 1 + correlation * exposure_volatility`` (clamped >= 0) scales "
        "the\n"
        "base CVA; negative correlation gives right-way risk (alpha < 1).\n"
        "\n"
        "This is a first-order proxy multiplier, confirmed against the WWR\n"
        "literature (Hull & White 2012; Gregory, *The xVA Challenge*) not to\n"
        "reproduce a specific published WWR model — treat it as a reasonable\n"
        "internal approximation.",
        "domain": "credit-risk",
        "function_name": "wrong_way_risk_adjustment",
        "input_schema": {
            "properties": {
                "base_cva": {
                    "description": "Independence-assumption " "CVA (>= 0).",
                    "type": "number",
                },
                "correlation": {
                    "description": "Exposure/credit " "correlation in " "``[-1, 1]``.",
                    "type": "number",
                },
                "exposure_volatility": {
                    "default": 0.3,
                    "description": "Relative "
                    "exposure "
                    "volatility "
                    "(>= 0) "
                    "controlling "
                    "the "
                    "adjustment "
                    "magnitude.",
                    "type": "number",
                },
            },
            "required": ["base_cva", "correlation"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/wrong_way_risk_adjustment",
        "summary": "Wrong-way-risk (WWR) multiplicative adjustment to CVA.",
        "tool_name": "wrong_way_risk_adjustment",
    },
    {
        "description": "Sign convention (cost to the bank is positive, reducing the trade value):\n"
        "``total_xva = CVA - DVA + FVA + KVA + MVA``. DVA is a benefit and so "
        "enters\n"
        "negatively. The adjusted price is ``risk_free_price - total_xva`` "
        "downstream.",
        "domain": "credit-risk",
        "function_name": "xva_aggregation",
        "input_schema": {
            "properties": {
                "cva": {
                    "description": "Credit valuation " "adjustment (cost, >= 0).",
                    "type": "number",
                },
                "dva": {
                    "default": 0.0,
                    "description": "Debit valuation " "adjustment (benefit, >= " "0).",
                    "type": "number",
                },
                "fva": {
                    "default": 0.0,
                    "description": "Funding valuation " "adjustment (cost).",
                    "type": "number",
                },
                "kva": {
                    "default": 0.0,
                    "description": "Capital valuation " "adjustment (cost).",
                    "type": "number",
                },
                "mva": {
                    "default": 0.0,
                    "description": "Margin valuation " "adjustment (cost).",
                    "type": "number",
                },
            },
            "required": ["cva"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/xva_aggregation",
        "summary": "Aggregate the XVA components into a total valuation adjustment.",
        "tool_name": "xva_aggregation",
    },
]

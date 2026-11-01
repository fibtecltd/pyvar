"""plugins/mcp/pyvar_mcp/_generated/regulatory.py — GENERATED, do not edit by hand.

The regulatory tools. Regenerate with: python3 scripts/generate_mcp_tools.py (from the
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
        "description": '"Substantially leveraged" here is a simple threshold flag (commitment\n'
        "leverage > 3x NAV), not AIFMD's full leverage-calculation methodology.\n"
        "\n"
        "Computes leverage under the gross method and the commitment method (each "
        "as\n"
        "a multiple of NAV) per Delegated Regulation 231/2013 Art. 7-8. A fund is\n"
        '"substantially leveraged" when commitment leverage exceeds 3x NAV.',
        "domain": "regulatory",
        "function_name": "aifmd_risk_metrics",
        "input_schema": {
            "properties": {
                "commitment_exposure": {"type": "number"},
                "gross_exposure": {"type": "number"},
                "net_asset_value": {"type": "number"},
                "var_pct": {"type": "object"},
            },
            "required": ["gross_exposure", "commitment_exposure", "net_asset_value"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/aifmd_risk_metrics",
        "summary": "AIFMD Annex IV risk metrics — leverage and (optional) VaR.",
        "tool_name": "aifmd_risk_metrics",
    },
    {
        "description": "``CET1 ratio = CET1 capital / RWA``; minimum 4.5% (Basel III §50).",
        "domain": "regulatory",
        "function_name": "basel_iii_cet1_ratio",
        "input_schema": {
            "properties": {
                "cet1_capital": {"type": "number"},
                "risk_weighted_assets": {"type": "number"},
            },
            "required": ["cet1_capital", "risk_weighted_assets"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/basel_iii_cet1_ratio",
        "summary": "Basel III Common Equity Tier 1 (CET1) ratio.",
        "tool_name": "basel_iii_cet1_ratio",
    },
    {
        "description": "``Leverage ratio = Tier 1 capital / total exposure measure``; minimum "
        "3.0%.\n"
        "The exposure measure is non-risk-weighted (on + off balance sheet).",
        "domain": "regulatory",
        "function_name": "basel_iii_leverage_ratio",
        "input_schema": {
            "properties": {
                "tier1_capital": {"type": "number"},
                "total_exposure": {"type": "number"},
            },
            "required": ["tier1_capital", "total_exposure"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/basel_iii_leverage_ratio",
        "summary": "Basel III leverage ratio.",
        "tool_name": "basel_iii_leverage_ratio",
    },
    {
        "description": "``Tier 1 ratio = Tier 1 capital / RWA``; minimum 6.0% (Basel III §50).",
        "domain": "regulatory",
        "function_name": "basel_iii_tier1_ratio",
        "input_schema": {
            "properties": {
                "risk_weighted_assets": {"type": "number"},
                "tier1_capital": {"type": "number"},
            },
            "required": ["tier1_capital", "risk_weighted_assets"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/basel_iii_tier1_ratio",
        "summary": "Basel III Tier 1 capital ratio.",
        "tool_name": "basel_iii_tier1_ratio",
    },
    {
        "description": "``Total ratio = (Tier 1 + Tier 2) / RWA``; minimum 8.0% (Basel III §50).",
        "domain": "regulatory",
        "function_name": "basel_iii_total_capital_ratio",
        "input_schema": {
            "properties": {
                "risk_weighted_assets": {"type": "number"},
                "total_capital": {"type": "number"},
            },
            "required": ["total_capital", "risk_weighted_assets"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/basel_iii_total_capital_ratio",
        "summary": "Basel III Total capital ratio.",
        "tool_name": "basel_iii_total_capital_ratio",
    },
    {
        "description": "Floored RWA = ``max(internal_model_rwa, floor_factor * "
        "standardised_rwa)``.\n"
        "The floor factor is 72.5% (Basel III finalisation) — do not relax.",
        "domain": "regulatory",
        "function_name": "basel_iv_output_floor",
        "input_schema": {
            "properties": {
                "floor_factor": {"default": 0.725, "type": "number"},
                "internal_model_rwa": {"type": "number"},
                "standardised_rwa": {"type": "number"},
            },
            "required": ["internal_model_rwa", "standardised_rwa"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/basel_iv_output_floor",
        "summary": "Basel IV output floor.",
        "tool_name": "basel_iv_output_floor",
    },
    {
        "description": "The 2.5% CET1 buffer above the 4.5% minimum. Breaching the buffer "
        "triggers\n"
        "Maximum Distributable Amount (MDA) restrictions on dividends/bonuses.",
        "domain": "regulatory",
        "function_name": "capital_conservation_buffer",
        "input_schema": {
            "properties": {
                "buffer_ratio": {"default": 0.025, "type": "number"},
                "cet1_ratio": {"type": "number"},
                "risk_weighted_assets": {"type": "number"},
            },
            "required": ["cet1_ratio", "risk_weighted_assets"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/capital_conservation_buffer",
        "summary": "Capital Conservation Buffer (CCoB) and distribution constraint.",
        "tool_name": "capital_conservation_buffer",
    },
    {
        "description": "The max(G-SII, O-SII, SyRB) selection is expected to already be resolved\n"
        "by the caller into ``systemic_buffer_ratio``; this function itself\n"
        "performs only a straight sum of the three supplied buffer ratios.\n"
        "\n"
        "``CBR = CCoB + CCyB + max(G-SII, O-SII, SyRB)`` per CRD IV. Sums the "
        "buffer\n"
        "ratios and (optionally) the capital amount on the supplied RWA.",
        "domain": "regulatory",
        "function_name": "combined_buffer_requirement",
        "input_schema": {
            "properties": {
                "capital_conservation_buffer_ratio": {"default": 0.025, "type": "number"},
                "countercyclical_buffer_ratio": {"default": 0.0, "type": "number"},
                "risk_weighted_assets": {"default": 0.0, "type": "number"},
                "systemic_buffer_ratio": {"default": 0.0, "type": "number"},
            },
            "type": "object",
        },
        "path": "/api/v1/regulatory/combined_buffer_requirement",
        "summary": "Combined Buffer Requirement (CBR).",
        "tool_name": "combined_buffer_requirement",
    },
    {
        "description": "The CCyB rate is the exposure-weighted average of the national CCyB rates\n"
        "applied to the bank's private-sector credit exposures (CRD IV Art. 140).",
        "domain": "regulatory",
        "function_name": "countercyclical_capital_buffer",
        "input_schema": {
            "properties": {
                "country_ccyb_rates": {"type": "object"},
                "exposure_amounts": {"type": "object"},
                "risk_weighted_assets": {"type": "number"},
            },
            "required": ["exposure_amounts", "country_ccyb_rates", "risk_weighted_assets"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/countercyclical_capital_buffer",
        "summary": "Institution-specific Countercyclical Capital Buffer (CCyB).",
        "tool_name": "countercyclical_capital_buffer",
    },
    {
        "description": "A single client / group exposure must not exceed 25% of Tier 1 capital,\n"
        "or — where the counterparty is an institution (or a group of connected\n"
        "clients including one) — the HIGHER of 25% of Tier 1 capital or EUR 150m\n"
        "(``CRR2_INSTITUTION_ABSOLUTE_LIMIT_EUR``), per Art. 395(1)'s institution\n"
        "alternative. ``exposure_value``/``tier1_capital`` are assumed\n"
        "EUR-denominated, matching Art. 395(1)'s own absolute figure — this\n"
        "function does not itself perform currency conversion.\n"
        "\n"
        "Note: Art. 395(1)'s EUR 150m alternative additionally requires that the\n"
        "institution's total exposure to non-institution clients connected to\n"
        "this counterparty stays within the plain 25% limit — a condition that\n"
        "spans a connected-client group, not a single exposure, so it is out of\n"
        "scope for this single-exposure function and not checked here.",
        "domain": "regulatory",
        "function_name": "crr2_large_exposure_limit",
        "input_schema": {
            "properties": {
                "exposure_value": {"type": "number"},
                "is_institution": {"default": False, "type": "boolean"},
                "tier1_capital": {"type": "number"},
            },
            "required": ["exposure_value", "tier1_capital"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/crr2_large_exposure_limit",
        "summary": "CRR2 large exposure limit (Art. 395).",
        "tool_name": "crr2_large_exposure_limit",
    },
    {
        "description": "[REGULATORY] EMIR REFIT (Regulation (EU) 2019/834) Art. 4a(1): a "
        "Financial\n"
        "Counterparty (FC) that breaches its clearing threshold in ANY ONE OTC\n"
        "derivative asset class becomes subject to the clearing obligation for ALL\n"
        "asset classes it has positions in, not just the one that breached. Art.\n"
        "10(1) evaluates a Non-Financial Counterparty above threshold (NFC+)\n"
        "per-asset-class instead -- only the classes where ITS OWN threshold is\n"
        "breached become subject to clearing.\n"
        "\n"
        "A prior version of this function applied FC's per-class-only logic to\n"
        "BOTH categories (took a single ``asset_class``/``notional`` pair,\n"
        "identical branching for FC and NFC+ beyond the NFC- exemption). It\n"
        "understated an FC's clearing scope whenever the breaching class differed\n"
        "from the queried class -- masked in the original test, which happened to\n"
        "query the same class that breached. Found during the Tier 3 #2 audit.",
        "domain": "regulatory",
        "function_name": "emir_clearing_obligation_check",
        "input_schema": {
            "properties": {
                "clearing_thresholds": {"type": "object"},
                "counterparty_category": {"type": "string"},
                "notionals": {"type": "object"},
            },
            "required": ["notionals", "counterparty_category", "clearing_thresholds"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/emir_clearing_obligation_check",
        "summary": "EMIR clearing obligation check (Art. 4 / Art. 4a / Art. 10 / clearing "
        "thresholds).",
        "tool_name": "emir_clearing_obligation_check",
    },
    {
        "description": "Computes the Initial Margin (IM) from the rate and the net margin call "
        "after\n"
        "applying the Minimum Transfer Amount (MTA) to the variation margin.",
        "domain": "regulatory",
        "function_name": "emir_margin_requirement",
        "input_schema": {
            "properties": {
                "initial_margin_rate": {"type": "number"},
                "minimum_transfer_amount": {"default": 0.0, "type": "number"},
                "portfolio_value": {"type": "number"},
                "variation_margin": {"type": "number"},
            },
            "required": ["portfolio_value", "initial_margin_rate", "variation_margin"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/emir_margin_requirement",
        "summary": "EMIR (Art. 11) uncleared-derivatives margin requirement.",
        "tool_name": "emir_margin_requirement",
    },
    {
        "description": "This validates a representative core subset of 6 fields, not full-schema\n"
        "coverage of EMIR REFIT's roughly 200 reportable fields.\n"
        "\n"
        "Validates the core EMIR reporting fields (counterparty LEIs, UTI, "
        "notional,\n"
        "asset class) and echoes a normalised report.",
        "domain": "regulatory",
        "function_name": "emir_trade_repository_report",
        "input_schema": {
            "properties": {"trade": {"type": "object"}},
            "required": ["trade"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/emir_trade_repository_report",
        "summary": "EMIR trade repository report builder/validator.",
        "tool_name": "emir_trade_repository_report",
    },
    {
        "description": "The IMA charge combines the multiplier-scaled, stressed-scaled Expected\n"
        'Shortfall (the "IMCC" proxy) with the non-modellable risk factor capital\n'
        "(SES) and the Default Risk Charge (BCBS d457 §189). The multiplier is\n"
        "floored at 1.5.",
        "domain": "regulatory",
        "function_name": "frtb_ima_market_risk_capital",
        "input_schema": {
            "properties": {
                "default_risk_charge": {"default": 0.0, "type": "number"},
                "expected_shortfall": {"type": "number"},
                "multiplier": {"type": "number"},
                "non_modellable_ses": {"default": 0.0, "type": "number"},
                "stressed_es_ratio": {"type": "number"},
            },
            "required": ["expected_shortfall", "stressed_es_ratio", "multiplier"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/frtb_ima_market_risk_capital",
        "summary": "FRTB Internal Models Approach total market-risk capital.",
        "tool_name": "frtb_ima_market_risk_capital",
    },
    {
        "description": "The green/amber/red zone is assigned by a fixed-threshold lookup on the\n"
        "correlation and ratio values below, not a single closed-form equation.\n"
        "\n"
        "Jointly evaluates the Spearman rank correlation between risk-theoretical "
        "P&L\n"
        "(RTPL) and hypothetical P&L (HPL) and the volatility ratio\n"
        "``std(RTPL)/std(HPL)``, assigning the Basel traffic-light zone. The\n"
        "thresholds are mandated by BCBS d457 and CLAUDE.md §4.4:\n"
        "green ``|corr|>=0.80 AND 0.8<=ratio<=1.2``;\n"
        "amber ``|corr|>=0.70 AND 0.6<=ratio<=1.5``; otherwise red (IMA loss).",
        "domain": "regulatory",
        "function_name": "frtb_pl_attribution_test",
        "input_schema": {
            "properties": {
                "hypothetical_pnl": {"type": "object"},
                "risk_theoretical_pnl": {"type": "object"},
            },
            "required": ["risk_theoretical_pnl", "hypothetical_pnl"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/frtb_pl_attribution_test",
        "summary": "FRTB P&L Attribution Test (PAT) — Spearman correlation + variance ratio.",
        "tool_name": "frtb_pl_attribution_test",
    },
    {
        "description": "The SA capital is the simple sum of the Sensitivities-Based Method charge\n"
        "(already aggregated across delta/vega/curvature and the three correlation\n"
        "scenarios), the Default Risk Charge (DRC) and the Residual Risk Add-On\n"
        "(RRAO) (BCBS d457 §2).",
        "domain": "regulatory",
        "function_name": "frtb_sa_market_risk_capital",
        "input_schema": {
            "properties": {
                "default_risk_charge": {"type": "number"},
                "residual_risk_addon": {"type": "number"},
                "sensitivities_charge": {"type": "number"},
            },
            "required": ["sensitivities_charge", "default_risk_charge", "residual_risk_addon"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/frtb_sa_market_risk_capital",
        "summary": "FRTB Standardised Approach total market-risk capital.",
        "tool_name": "frtb_sa_market_risk_capital",
    },
    {
        "description": "Aggregates per-desk capital: IMA-eligible desks contribute their IMA "
        "charge,\n"
        "non-eligible (PAT-red / backtest-failed) desks fall back to the SA "
        "charge.\n"
        "The total firm-wide market-risk capital is the sum across desks (BCBS "
        "d457\n"
        "treats the firm charge as the sum of approved-desk IMA plus SA for the "
        "rest).",
        "domain": "regulatory",
        "function_name": "frtb_trading_desk_aggregation",
        "input_schema": {
            "properties": {
                "desk_ima_charges": {"type": "object"},
                "desk_ima_eligible": {"type": "object"},
                "desk_sa_charges": {"type": "object"},
            },
            "required": ["desk_sa_charges", "desk_ima_charges", "desk_ima_eligible"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/frtb_trading_desk_aggregation",
        "summary": "FRTB trading-desk capital aggregation.",
        "tool_name": "frtb_trading_desk_aggregation",
    },
    {
        "description": "Aggregates Pillar 1 capital with internally-assessed risk components\n"
        "(credit concentration, IRRBB, etc.) and compares to available capital.",
        "domain": "regulatory",
        "function_name": "icaap_capital_assessment",
        "input_schema": {
            "properties": {
                "available_capital": {"type": "number"},
                "pillar1_capital": {"type": "number"},
                "risk_capital_components": {"type": "object"},
            },
            "required": ["pillar1_capital", "risk_capital_components", "available_capital"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/icaap_capital_assessment",
        "summary": "ICAAP internal capital adequacy assessment.",
        "tool_name": "icaap_capital_assessment",
    },
    {
        "description": "The 6-item checklist below is this codebase's own internal choice, not a\n"
        "checklist published by RTS 6 itself.\n"
        "\n"
        "Verifies that the mandatory governance and control documentation items "
        "for\n"
        "an algorithmic trading strategy are present.",
        "domain": "regulatory",
        "function_name": "mifid_ii_algorithm_documentation",
        "input_schema": {
            "properties": {"documentation": {"type": "object"}},
            "required": ["documentation"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/mifid_ii_algorithm_documentation",
        "summary": "MiFID II RTS 6 algorithmic-trading documentation completeness check.",
        "tool_name": "mifid_ii_algorithm_documentation",
    },
    {
        "description": "This is an internal TCA (transaction cost analysis) metric only; neither\n"
        "RTS 27 nor RTS 28 defines a prescribed quantitative figure that this\n"
        "function reproduces.\n"
        "\n"
        "Computes the quantity-weighted price improvement (or slippage) of "
        "executions\n"
        "versus a reference (e.g. EBBO) price, in basis points. Positive means "
        "price\n"
        "improvement for the client.\n"
        "\n"
        "This does not correspond to any specific RTS 27/28 field: RTS 27\n"
        "(Commission Delegated Regulation (EU) 2017/575) requires simple-average\n"
        "and volume-weighted transaction prices/spreads/best-bid-offer (Annex\n"
        "Tables 1-9), and RTS 28 (DR (EU) 2017/576) requires execution-venue\n"
        "rankings -- neither defines a quantity-weighted price-improvement-in-bps\n"
        "metric like this one. RTS 27 was also repealed by the 2024 MiFIR review.\n"
        'A prior version of this docstring cited "RTS 27/28" directly; corrected\n'
        "during the Tier 3 #2 audit. This remains a reasonable internal TCA\n"
        "metric, just not a regulatory-prescribed one.",
        "domain": "regulatory",
        "function_name": "mifid_ii_best_execution_metric",
        "input_schema": {
            "properties": {
                "benchmark_prices": {"type": "object"},
                "executed_prices": {"type": "object"},
                "quantities": {"type": "object"},
                "side": {"default": 1, "type": "integer"},
            },
            "required": ["executed_prices", "benchmark_prices", "quantities"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/mifid_ii_best_execution_metric",
        "summary": "MiFID II best-execution TCA metric -- internal, NOT an RTS 27/28 figure.",
        "tool_name": "mifid_ii_best_execution_metric",
    },
    {
        "description": "Trades above the size threshold (or in illiquid instruments) may benefit\n"
        "from deferred publication; otherwise publication is near real-time.",
        "domain": "regulatory",
        "function_name": "mifid_ii_post_trade_transparency",
        "input_schema": {
            "properties": {
                "delayed_publication_threshold": {"type": "number"},
                "is_liquid": {"default": True, "type": "boolean"},
                "trade_size": {"type": "number"},
            },
            "required": ["trade_size", "delayed_publication_threshold"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/mifid_ii_post_trade_transparency",
        "summary": "MiFID II post-trade transparency / deferred-publication assessment.",
        "tool_name": "mifid_ii_post_trade_transparency",
    },
    {
        "description": "Determines whether an order qualifies for the Large-in-Scale (LIS) waiver\n"
        "from pre-trade transparency (illiquid instruments and orders above the "
        "LIS\n"
        "threshold may be waived).",
        "domain": "regulatory",
        "function_name": "mifid_ii_pre_trade_transparency",
        "input_schema": {
            "properties": {
                "instrument_type": {"type": "string"},
                "is_liquid": {"default": True, "type": "boolean"},
                "large_in_scale_threshold": {"type": "number"},
                "order_size": {"type": "number"},
            },
            "required": ["instrument_type", "order_size", "large_in_scale_threshold"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/mifid_ii_pre_trade_transparency",
        "summary": "MiFID II pre-trade transparency / LIS waiver assessment.",
        "tool_name": "mifid_ii_pre_trade_transparency",
    },
    {
        "description": "This checks a representative core subset of 9 fields, not full-schema\n"
        "coverage of RTS 22's roughly 65 mandatory transaction-report fields.\n"
        "\n"
        "Checks the presence and basic validity of the mandatory "
        "transaction-report\n"
        "fields (LEI length, ISIN length, positive price/quantity).",
        "domain": "regulatory",
        "function_name": "mifid_ii_transaction_report_validator",
        "input_schema": {
            "properties": {"report": {"type": "object"}},
            "required": ["report"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/mifid_ii_transaction_report_validator",
        "summary": "MiFID II / RTS 22 transaction report field validator.",
        "tool_name": "mifid_ii_transaction_report_validator",
    },
    {
        "description": "Pillar 2A covers risks not (fully) captured in Pillar 1: e.g. credit\n"
        "concentration, IRRBB, pension, operational. Sums the component charges.",
        "domain": "regulatory",
        "function_name": "pillar_2a_capital",
        "input_schema": {
            "properties": {
                "risk_addons": {"type": "object"},
                "risk_weighted_assets": {"type": "number"},
            },
            "required": ["risk_addons", "risk_weighted_assets"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/pillar_2a_capital",
        "summary": "Pillar 2A capital — sum of individual risk add-ons.",
        "tool_name": "pillar_2a_capital",
    },
    {
        "description": "The forward-looking buffer to absorb the peak capital depletion projected\n"
        "under the supervisory stress scenario.",
        "domain": "regulatory",
        "function_name": "pillar_2b_stress_buffer",
        "input_schema": {
            "properties": {
                "risk_weighted_assets": {"type": "number"},
                "stressed_capital_depletion": {"type": "number"},
            },
            "required": ["stressed_capital_depletion", "risk_weighted_assets"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/pillar_2b_stress_buffer",
        "summary": "Pillar 2B stress buffer (PRA buffer / capital guidance).",
        "tool_name": "pillar_2b_stress_buffer",
    },
    {
        "description": "This validates a representative core subset of 6 fields, not full-schema\n"
        "coverage of SFTR's complete field set.\n"
        "\n"
        "Validates the core SFTR fields for an SFT (repo, securities lending, buy-\n"
        "sell back, margin lending): counterparties, UTI, collateral and the SFT\n"
        "type.",
        "domain": "regulatory",
        "function_name": "sftr_securities_finance_report",
        "input_schema": {
            "properties": {"transaction": {"type": "object"}},
            "required": ["transaction"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/sftr_securities_finance_report",
        "summary": "SFTR securities-financing transaction report builder/validator.",
        "tool_name": "sftr_securities_finance_report",
    },
    {
        "description": "The sigma used here is the intra-counterparty (independent-Bernoulli)\n"
        "variance term only; Delegated Regulation (EU) 2015/35 Art. 201's\n"
        "inter-counterparty correlation term is not implemented, so the true\n"
        "Art. 201 variance (and SCR) is at least as large as what this function\n"
        "returns.\n"
        "\n"
        "[REGULATORY] Delegated Regulation (EU) 2015/35 Art. 200(1)-(3) fixes the\n"
        "capital charge as a TIERED multiplier on the standard deviation (sigma) "
        "of\n"
        "the loss distribution, not a flat 3x: SCR = 3*sigma while\n"
        "sigma <= 7% of total LGD; SCR = 5*sigma while 7% < sigma/TLGD <= 20%; SCR "
        "=\n"
        "total LGD (fully capped) once sigma/TLGD exceeds 20%. An earlier version "
        "of\n"
        "this function exposed a caller-configurable ``risk_factor`` defaulting to "
        "a\n"
        "flat 3.0 — that understated capital by ~79% on a representative "
        "2-exposure\n"
        "case (807 vs. the correct ~1449, entirely from missing the 5x/TLGD "
        "tiers).\n"
        "The multiplier is fixed by the Delegated Regulation, so it is "
        "intentionally\n"
        "not a parameter here (same reasoning as CLAUDE.md §4.3/§4.4's Basel\n"
        "thresholds: never parameterise regulator-set constants).\n"
        "\n"
        "[LIMITATION] The variance (sigma^2) computed here is the "
        "intra-counterparty\n"
        "term only — an independent-Bernoulli approximation summing each\n"
        "counterparty's own default-loss variance. Art. 201's full formula also "
        "adds\n"
        "an inter-counterparty correlation term (V_inter) between exposures "
        "carrying\n"
        "different default probabilities, which this implementation does NOT\n"
        "compute — that term is generally positive, so the true Art. 201 variance\n"
        "(and therefore the true SCR) is at least as large as what this function\n"
        "returns. Do not rely on this for statutory Solvency II reporting without "
        "an\n"
        "actuarial review of that gap.",
        "domain": "regulatory",
        "function_name": "solvency_ii_scr_credit_risk",
        "input_schema": {
            "properties": {
                "default_probabilities": {"type": "object"},
                "exposures": {"type": "object"},
                "loss_given_default": {"type": "object"},
            },
            "required": ["exposures", "loss_given_default", "default_probabilities"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/solvency_ii_scr_credit_risk",
        "summary": "Solvency II SCR counterparty default (credit) risk — Type 1 exposures.",
        "tool_name": "solvency_ii_scr_credit_risk",
    },
    {
        "description": "Aggregates the market sub-module capital charges (interest rate, equity,\n"
        "property, spread, currency, concentration) using the prescribed "
        "correlation\n"
        "matrix and the square-root formula ``SCR = sqrt(s' Corr s)`` (Delegated\n"
        "Regulation 2015/35 Art. 164).",
        "domain": "regulatory",
        "function_name": "solvency_ii_scr_market_risk",
        "input_schema": {
            "properties": {
                "correlation_matrix": {"type": "object"},
                "sub_module_charges": {"type": "object"},
                "sub_module_names": {"type": "object"},
            },
            "required": ["sub_module_charges", "correlation_matrix"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/solvency_ii_scr_market_risk",
        "summary": "Solvency II SCR Market risk — standard-formula modular aggregation.",
        "tool_name": "solvency_ii_scr_market_risk",
    },
    {
        "description": "Translates the supervisory Pillar 2A add-on ratio into a capital amount "
        "and\n"
        "the Total SREP Capital Requirement (TSCR).",
        "domain": "regulatory",
        "function_name": "srep_capital_add_on",
        "input_schema": {
            "properties": {
                "pillar1_requirement": {"type": "number"},
                "pillar2a_addon_ratio": {"type": "number"},
                "risk_weighted_assets": {"type": "number"},
            },
            "required": ["pillar1_requirement", "pillar2a_addon_ratio", "risk_weighted_assets"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/srep_capital_add_on",
        "summary": "SREP (Supervisory Review and Evaluation Process) capital add-on.",
        "tool_name": "srep_capital_add_on",
    },
    {
        "description": "The SRRI class itself is a bucket lookup of the annualised volatility\n"
        "against fixed CESR volatility bands, not a closed-form equation.\n"
        "\n"
        "Maps the annualised volatility of (weekly by default) returns to the SRRI\n"
        "bucket per CESR 10-673: class 1 (< 0.5%) up to class 7 (>= 25%).",
        "domain": "regulatory",
        "function_name": "ucits_kiid_risk_indicator",
        "input_schema": {
            "properties": {
                "periods_per_year": {"default": 52, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/regulatory/ucits_kiid_risk_indicator",
        "summary": "UCITS KIID Synthetic Risk and Reward Indicator (SRRI), 1-7.",
        "tool_name": "ucits_kiid_risk_indicator",
    },
]

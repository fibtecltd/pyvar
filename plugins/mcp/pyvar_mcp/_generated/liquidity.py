"""plugins/mcp/pyvar_mcp/_generated/liquidity.py — GENERATED, do not edit by hand.

The liquidity tools. Regenerate with: python3 scripts/generate_mcp_tools.py (from the
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
        "description": "``encumbrance = encumbered assets / total assets``. High encumbrance "
        "reduces\n"
        "the unencumbered asset pool available to monetise in stress.",
        "domain": "liquidity",
        "function_name": "asset_encumbrance_ratio",
        "input_schema": {
            "properties": {
                "encumbered_assets": {
                    "description": "Carrying " "value of " "encumbered " "assets.",
                    "type": "number",
                },
                "total_assets": {
                    "description": "Total assets " "(encumbered + " "unencumbered).",
                    "type": "number",
                },
            },
            "required": ["encumbered_assets", "total_assets"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/asset_encumbrance_ratio",
        "summary": "Asset encumbrance ratio (EBA reporting).",
        "tool_name": "asset_encumbrance_ratio",
    },
    {
        "description": "ASF is the weighted sum of funding sources by their ASF factor. Basel III\n"
        "assigns higher factors to more stable funding (e.g. capital and >1y "
        "funding\n"
        "= 100%, stable retail deposits = 95%, less-stable = 90%, wholesale <1y\n"
        "typically 50% or 0%).",
        "domain": "liquidity",
        "function_name": "available_stable_funding_asf_calc",
        "input_schema": {
            "properties": {
                "asf_factors": {
                    "description": "ASF factor for " "each source, each " "in [0, 1].",
                    "type": "object",
                },
                "funding_amounts": {
                    "description": "Carrying " "amounts of " "each funding " "source.",
                    "type": "object",
                },
            },
            "required": ["funding_amounts", "asf_factors"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/available_stable_funding_asf_calc",
        "summary": "Available Stable Funding for the NSFR numerator.",
        "tool_name": "available_stable_funding_asf_calc",
    },
    {
        "description": "Aggregates inflows and outflows into the standard maturity buckets and\n"
        "computes the per-bucket and cumulative liquidity gap.",
        "domain": "liquidity",
        "function_name": "cash_flow_ladder_1_year",
        "input_schema": {
            "properties": {
                "bucket_inflows": {
                    "description": "Inflow per " "maturity " "bucket (one " "entry per " "bucket).",
                    "type": "object",
                },
                "bucket_outflows": {
                    "description": "Outflow per " "maturity " "bucket.",
                    "type": "object",
                },
                "buckets": {
                    "description": "Optional bucket "
                    "labels; defaults to "
                    "the standard 8-bucket "
                    "set.",
                    "type": "object",
                },
                "opening_balance": {
                    "default": 0.0,
                    "description": "Starting " "balance " "carried into " "the first " "bucket.",
                    "type": "number",
                },
            },
            "required": ["bucket_inflows", "bucket_outflows"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/cash_flow_ladder_1_year",
        "summary": "One-year bucketed contractual cash-flow ladder.",
        "tool_name": "cash_flow_ladder_1_year",
    },
    {
        "description": "Projects the daily net and cumulative liquidity position over a 30-day\n"
        "horizon. The minimum cumulative balance (including the opening balance) "
        "is\n"
        "the tightest liquidity point — if negative the institution faces a "
        "funding\n"
        "shortfall on that day.",
        "domain": "liquidity",
        "function_name": "cash_flow_ladder_30_day",
        "input_schema": {
            "properties": {
                "daily_inflows": {
                    "description": "Length-30 array " "of daily " "contractual " "inflows.",
                    "type": "object",
                },
                "daily_outflows": {
                    "description": "Length-30 " "array of daily " "contractual " "outflows.",
                    "type": "object",
                },
                "opening_balance": {
                    "default": 0.0,
                    "description": "Starting cash " "/ HQLA " "balance at " "day 0.",
                    "type": "number",
                },
            },
            "required": ["daily_inflows", "daily_outflows"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/cash_flow_ladder_30_day",
        "summary": "30-day daily contractual cash-flow ladder.",
        "tool_name": "cash_flow_ladder_30_day",
    },
    {
        "description": "Filters assets meeting the central bank's minimum credit rating (encoded "
        "as\n"
        "an ordinal where higher = better) and computes the "
        "post-central-bank-haircut\n"
        "borrowing capacity from eligible assets.",
        "domain": "liquidity",
        "function_name": "central_bank_facility_eligibility",
        "input_schema": {
            "properties": {
                "asset_ratings": {
                    "description": "Ordinal credit " "rating per " "asset (higher = " "better).",
                    "type": "object",
                },
                "asset_values": {"description": "Market value per " "asset.", "type": "object"},
                "cb_haircuts": {
                    "description": "Central-bank " "haircut per " "asset, each in " "[0, 1].",
                    "type": "object",
                },
                "min_rating": {
                    "description": "Minimum ordinal " "rating accepted by " "the facility.",
                    "type": "integer",
                },
            },
            "required": ["asset_ratings", "min_rating", "asset_values", "cb_haircuts"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/central_bank_facility_eligibility",
        "summary": "Central-bank facility collateral eligibility and borrowing capacity.",
        "tool_name": "central_bank_facility_eligibility",
    },
    {
        "description": "Computes the net realisable collateral value after haircuts and netting "
        "off\n"
        "already-pledged amounts — the counterbalancing capacity available to "
        "raise\n"
        "secured funding.",
        "domain": "liquidity",
        "function_name": "collateral_availability_analysis",
        "input_schema": {
            "properties": {
                "already_pledged": {
                    "description": "Optional " "pledged " "amount per " "asset to net " "off.",
                    "type": "object",
                },
                "collateral_values": {
                    "description": "Market " "value of " "each " "collateral " "asset.",
                    "type": "object",
                },
                "haircuts": {
                    "description": "Haircut per asset, " "each in [0, 1].",
                    "type": "object",
                },
            },
            "required": ["collateral_values", "haircuts"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/collateral_availability_analysis",
        "summary": "Collateral availability — post-haircut monetisable value.",
        "tool_name": "collateral_availability_analysis",
    },
    {
        "description": "By default (the two retail-category arguments omitted) this is NOT the\n"
        "BCBS 238 reference combined scenario: BCBS 238's own combined\n"
        "idiosyncratic + market-wide scenario (§II paras 19-20) runs off the\n"
        "LCR's own regulator-set retail run-off categories (stable/less-stable\n"
        "deposit stability buckets, each with its own national-discretion\n"
        "minimum rate), whereas this function's default applies a single flat\n"
        "15% retail / 100% wholesale run-off convention instead -- a structural\n"
        "gap a single scalar ``retail_runoff`` rate cannot close, since BCBS\n"
        "238's categorisation requires segmenting retail deposits into multiple\n"
        "stability buckets with different rates, not one blended rate.\n"
        "\n"
        "Pass ``retail_deposits_by_category`` and ``retail_runoff_rates``\n"
        "together (equal-length arrays: each category's deposit balance and its\n"
        "own regulator-set run-off rate) to switch to a BCBS-238-shaped\n"
        "categorised retail outflow -- ``sum(retail_deposits_by_category *\n"
        "retail_runoff_rates)`` -- instead of the single-rate\n"
        "``retail_deposits * retail_runoff`` convention. This function does not\n"
        "hardcode specific category rates itself (BCBS 238 leaves the exact\n"
        "stable/less-stable thresholds and rates to national supervisory\n"
        "discretion); the caller supplies their own jurisdiction's categorised\n"
        "balances and rates. ``retail_deposits_by_category`` must sum to\n"
        "``retail_deposits`` -- enforced as a consistency check, not silently\n"
        "ignored.\n"
        "\n"
        "Models a firm-specific shock occurring inside a market-wide crisis:\n"
        "liability run-off is aggravated (default 15% retail, 100% wholesale)\n"
        "*and* HQLA value is reduced by stressed market haircuts, simultaneously.\n"
        "(Found during the Tier 3 #2 audit — a prior version of this docstring\n"
        "incorrectly claimed this was the Basel/EBA reference scenario.)",
        "domain": "liquidity",
        "function_name": "combined_stress_scenario",
        "input_schema": {
            "properties": {
                "hqla_by_level": {
                    "description": "HQLA market " "value per " "level.",
                    "type": "object",
                },
                "inflows": {
                    "default": 0.0,
                    "description": "Stressed contractual " "inflows.",
                    "type": "number",
                },
                "market_haircuts": {
                    "description": "Additional "
                    "stressed "
                    "haircut per "
                    "level, each "
                    "in [0, 1].",
                    "type": "object",
                },
                "retail_deposits": {
                    "description": "Retail "
                    "deposit "
                    "balance. Used "
                    "directly "
                    "(times "
                    "``retail_runoff``) "
                    "unless the "
                    "categorised "
                    "arguments are "
                    "supplied, in "
                    "which case it "
                    "must equal "
                    "``sum(retail_deposits_by_category)``.",
                    "type": "number",
                },
                "retail_deposits_by_category": {
                    "description": "Optional "
                    "per-category "
                    "retail "
                    "deposit "
                    "balances "
                    "(e.g. "
                    "stable "
                    "/ "
                    "less-stable "
                    "buckets). "
                    "Must "
                    "be "
                    "supplied "
                    "together "
                    "with "
                    "``retail_runoff_rates`` "
                    "and "
                    "must "
                    "sum "
                    "to "
                    "``retail_deposits``.",
                    "type": "object",
                },
                "retail_runoff": {
                    "default": 0.15,
                    "description": "Retail run-off "
                    "rate (default "
                    "15%). Ignored "
                    "when the "
                    "categorised "
                    "retail "
                    "arguments are "
                    "supplied.",
                    "type": "number",
                },
                "retail_runoff_rates": {
                    "description": "Optional "
                    "per-category "
                    "run-off "
                    "rates in "
                    "[0, 1], "
                    "matching "
                    "``retail_deposits_by_category`` "
                    "in "
                    "length.",
                    "type": "object",
                },
                "wholesale_funding": {
                    "description": "Wholesale " "funding " "balance.",
                    "type": "number",
                },
                "wholesale_runoff": {
                    "default": 1.0,
                    "description": "Wholesale " "run-off rate " "(default " "100%).",
                    "type": "number",
                },
            },
            "required": [
                "retail_deposits",
                "wholesale_funding",
                "hqla_by_level",
                "market_haircuts",
            ],
            "type": "object",
        },
        "path": "/api/v1/liquidity/combined_stress_scenario",
        "summary": "Combined idiosyncratic + market-wide stress scenario.",
        "tool_name": "combined_stress_scenario",
    },
    {
        "description": "Compares current early-warning metrics against their activation "
        "thresholds.\n"
        "A metric breaches when its value falls *below* the threshold (lower = "
        "worse;\n"
        "e.g. LCR, survival days). Returns the list of breached triggers and the "
        "CFP\n"
        "activation decision.\n"
        "\n"
        "This is a logical breach test, not an arithmetic formula, so it is shown "
        "on\n"
        "the Try-it panel as an indicator function of the comparison rather than a\n"
        "computed expression.",
        "domain": "liquidity",
        "function_name": "contingency_funding_plan_trigger",
        "input_schema": {
            "properties": {
                "metrics": {
                    "description": "Mapping ``name -> " "current value``.",
                    "type": "object",
                },
                "thresholds": {
                    "description": "Mapping ``name -> " "minimum acceptable " "value``.",
                    "type": "object",
                },
            },
            "required": ["metrics", "thresholds"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/contingency_funding_plan_trigger",
        "summary": "Evaluate Contingency Funding Plan (CFP) activation triggers.",
        "tool_name": "contingency_funding_plan_trigger",
    },
    {
        "description": "When ``ccf`` is not supplied it defaults to 1.0 for every commitment,\n"
        "i.e. full drawdown of each commitment is assumed in the expected-outflow\n"
        "calculation unless a lower conversion factor is explicitly passed.\n"
        "\n"
        "Estimates the expected contingent outflow as ``commitment * "
        "draw_probability\n"
        "* credit-conversion-factor`` — the liquidity that off-balance-sheet\n"
        "commitments (undrawn lines, guarantees) could absorb in stress.",
        "domain": "liquidity",
        "function_name": "contingent_liquidity_risk",
        "input_schema": {
            "properties": {
                "ccf": {
                    "description": "Optional credit "
                    "conversion factor per "
                    "commitment (default all "
                    "1.0).",
                    "type": "object",
                },
                "commitment_amounts": {
                    "description": "Notional "
                    "of each "
                    "undrawn "
                    "commitment "
                    "/ "
                    "guarantee.",
                    "type": "object",
                },
                "draw_probabilities": {
                    "description": "Probability "
                    "of "
                    "drawdown "
                    "per "
                    "commitment, "
                    "in [0, 1].",
                    "type": "object",
                },
            },
            "required": ["commitment_amounts", "draw_probabilities"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/contingent_liquidity_risk",
        "summary": "Contingent liquidity risk from undrawn commitments and guarantees.",
        "tool_name": "contingent_liquidity_risk",
    },
    {
        "description": "Sizes the FX swap needed to fund a shortfall in one currency using "
        "surplus\n"
        "in another. ``fx_rate`` converts one unit of the surplus currency into "
        "the\n"
        "shortfall currency; a ``swap_haircut`` reduces the usable surplus to "
        "reflect\n"
        "swap-market stress.",
        "domain": "liquidity",
        "function_name": "cross_currency_liquidity_bridge",
        "input_schema": {
            "properties": {
                "fx_rate": {
                    "description": "Units of " "shortfall_ccy per " "unit of surplus_ccy.",
                    "type": "number",
                },
                "shortfall_amount": {
                    "description": "Amount of " "the deficit " "(in " "shortfall_ccy).",
                    "type": "number",
                },
                "shortfall_ccy": {"description": "Currency in " "deficit.", "type": "string"},
                "surplus_amount": {
                    "description": "Available " "surplus (in " "surplus_ccy).",
                    "type": "number",
                },
                "surplus_ccy": {
                    "description": "Currency with " "surplus to swap.",
                    "type": "string",
                },
                "swap_haircut": {
                    "default": 0.0,
                    "description": "Haircut on " "usable surplus, " "in [0, 1].",
                    "type": "number",
                },
            },
            "required": [
                "shortfall_ccy",
                "shortfall_amount",
                "surplus_ccy",
                "surplus_amount",
                "fx_rate",
            ],
            "type": "object",
        },
        "path": "/api/v1/liquidity/cross_currency_liquidity_bridge",
        "summary": "Cross-currency liquidity bridge via FX swap.",
        "tool_name": "cross_currency_liquidity_bridge",
    },
    {
        "description": "Each deposit carries a stability score in [0, 1] (e.g. derived from\n"
        "insurance coverage, transactional relationship, tenor). Deposits at or "
        "above\n"
        "``stable_threshold`` are classified stable (lower LCR run-off), the rest\n"
        "less-stable.",
        "domain": "liquidity",
        "function_name": "deposit_stability_classification",
        "input_schema": {
            "properties": {
                "deposit_features": {
                    "description": "Stability " "score per " "deposit, " "each in [0, " "1].",
                    "type": "object",
                },
                "stable_threshold": {
                    "default": 0.5,
                    "description": "Cut-off for " "the stable " "classification.",
                    "type": "number",
                },
            },
            "required": ["deposit_features"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/deposit_stability_classification",
        "summary": "Classify deposits as stable vs less-stable from a stability score.",
        "tool_name": "deposit_stability_classification",
    },
    {
        "description": "Evaluates each EWI against its threshold and a per-indicator direction\n"
        '(``"higher_breach"`` means a value above threshold is a warning, e.g. '
        "funding\n"
        'spread; ``"lower_breach"`` means below threshold is a warning, e.g. LCR). '
        "The\n"
        "aggregate signal escalates with the number of triggered indicators.\n"
        "\n"
        "This is a direction-dependent logical breach test per indicator, not a\n"
        "single arithmetic formula, and the aggregate signal buckets are exact:\n"
        "normal (0 triggers), watch (1-2) and alert (3 or more).",
        "domain": "liquidity",
        "function_name": "early_warning_indicator_liquidity",
        "input_schema": {
            "properties": {
                "directions": {
                    "description": "Optional mapping "
                    "``name -> "
                    '"higher_breach"|"lower_breach"``; '
                    "defaults to "
                    '``"lower_breach"`` '
                    "for all.",
                    "type": "object",
                },
                "indicators": {
                    "description": "Mapping ``name -> " "current value``.",
                    "type": "object",
                },
                "thresholds": {
                    "description": "Mapping ``name -> " "threshold``.",
                    "type": "object",
                },
            },
            "required": ["indicators", "thresholds"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/early_warning_indicator_liquidity",
        "summary": "Liquidity early-warning indicator (EWI) dashboard.",
        "tool_name": "early_warning_indicator_liquidity",
    },
    {
        "description": "Computes the amount-weighted average cost of the funding base and the "
        "total\n"
        "annual funding cost in currency terms.",
        "domain": "liquidity",
        "function_name": "funding_cost_analysis",
        "input_schema": {
            "properties": {
                "funding_amounts": {
                    "description": "Outstanding " "amount of " "each funding " "source.",
                    "type": "object",
                },
                "funding_rates": {
                    "description": "Annual rate "
                    "(decimal) per "
                    "source, e.g. "
                    "0.035 for 3.5%.",
                    "type": "object",
                },
            },
            "required": ["funding_amounts", "funding_rates"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/funding_cost_analysis",
        "summary": "Weighted-average funding cost.",
        "tool_name": "funding_cost_analysis",
    },
    {
        "description": "Computes the amount-weighted average tenor of the funding base and the\n"
        "proportion of funding maturing within 90 days — a core ILAAP structural\n"
        "metric (longer WAL == more stable funding).",
        "domain": "liquidity",
        "function_name": "funding_tenor_analysis",
        "input_schema": {
            "properties": {
                "funding_amounts": {
                    "description": "Outstanding " "amount of " "each funding " "tranche.",
                    "type": "object",
                },
                "tenors_days": {
                    "description": "Residual tenor in " "days for each " "tranche.",
                    "type": "object",
                },
            },
            "required": ["funding_amounts", "tenors_days"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/funding_tenor_analysis",
        "summary": "Weighted-average funding tenor and short-term reliance.",
        "tool_name": "funding_tenor_analysis",
    },
    {
        "description": "Computes the net liquidity gap in each currency (inflows - outflows). A\n"
        "significant negative position signals reliance on FX swap markets to fund\n"
        "the shortfall — a key vulnerability if swap markets seize.",
        "domain": "liquidity",
        "function_name": "fx_liquidity_risk_by_currency",
        "input_schema": {
            "properties": {
                "inflows_by_ccy": {
                    "description": "Mapping " "``currency -> " "inflow " "amount``.",
                    "type": "object",
                },
                "outflows_by_ccy": {
                    "description": "Mapping " "``currency -> " "outflow " "amount``.",
                    "type": "object",
                },
            },
            "required": ["inflows_by_ccy", "outflows_by_ccy"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/fx_liquidity_risk_by_currency",
        "summary": "FX liquidity risk — net position per significant currency.",
        "tool_name": "fx_liquidity_risk_by_currency",
    },
    {
        "description": "When ``haircuts`` is not supplied it defaults to all zeros, i.e. no\n"
        "haircut is applied and every asset is valued at full market value.\n"
        "\n"
        "Level 1 assets (cash, central-bank reserves, 0%-risk-weight sovereign "
        "debt)\n"
        "receive a 0% haircut by default and have no composition cap (BCBS 238 "
        "§50).",
        "domain": "liquidity",
        "function_name": "hqla_level_1_asset_classifier",
        "input_schema": {
            "properties": {
                "asset_values": {
                    "description": "Market values of " "candidate Level " "1 assets.",
                    "type": "object",
                },
                "haircuts": {
                    "description": "Optional per-asset "
                    "haircuts in [0, 1]; "
                    "defaults to all "
                    "zeros.",
                    "type": "object",
                },
            },
            "required": ["asset_values"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/hqla_level_1_asset_classifier",
        "summary": "Classify and value Level 1 HQLA.",
        "tool_name": "hqla_level_1_asset_classifier",
    },
    {
        "description": "Unlike Level 1's zero-by-default haircut array, ``haircut`` here is a\n"
        "single scalar applied uniformly to every asset in ``asset_values``, and\n"
        "the function enforces a minimum of 15%.\n"
        "\n"
        "Level 2A assets (20%-risk-weight sovereigns, certain covered bonds, high-\n"
        "grade corporates) carry a minimum 15% haircut (BCBS 238 §52).",
        "domain": "liquidity",
        "function_name": "hqla_level_2a_asset_classifier",
        "input_schema": {
            "properties": {
                "asset_values": {
                    "description": "Market values of " "candidate Level " "2A assets.",
                    "type": "object",
                },
                "haircut": {
                    "default": 0.15,
                    "description": "Supervisory haircut " "(minimum 15%).",
                    "type": "number",
                },
            },
            "required": ["asset_values"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/hqla_level_2a_asset_classifier",
        "summary": "Classify and value Level 2A HQLA.",
        "tool_name": "hqla_level_2a_asset_classifier",
    },
    {
        "description": "As with Level 2A, ``haircut`` is a single scalar applied uniformly to\n"
        "every asset in ``asset_values`` rather than a per-asset array; the\n"
        "function enforces a minimum of 25% (pass 0.50 for the lower-grade\n"
        "corporate/equity sub-bucket).\n"
        "\n"
        "Level 2B assets (RMBS 25% haircut, lower-grade corporates and qualifying\n"
        "equities 50% haircut) carry a minimum 25% haircut (BCBS 238 §54).",
        "domain": "liquidity",
        "function_name": "hqla_level_2b_asset_classifier",
        "input_schema": {
            "properties": {
                "asset_values": {
                    "description": "Market values of " "candidate Level " "2B assets.",
                    "type": "object",
                },
                "haircut": {
                    "default": 0.25,
                    "description": "Supervisory haircut " "(minimum 25%).",
                    "type": "number",
                },
            },
            "required": ["asset_values"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/hqla_level_2b_asset_classifier",
        "summary": "Classify and value Level 2B HQLA.",
        "tool_name": "hqla_level_2b_asset_classifier",
    },
    {
        "description": "Models a firm-specific crisis (e.g. rating downgrade): partial retail\n"
        "deposit flight and complete loss of wholesale funding rollover. Wholesale\n"
        "run-off defaults to 100% — the hallmark of a name-specific shock.",
        "domain": "liquidity",
        "function_name": "idiosyncratic_stress_scenario",
        "input_schema": {
            "properties": {
                "hqla": {"description": "Available HQLA.", "type": "number"},
                "retail_deposits": {
                    "description": "Retail " "deposit " "balance.",
                    "type": "number",
                },
                "retail_runoff": {
                    "default": 0.1,
                    "description": "Retail run-off " "rate (default " "10%).",
                    "type": "number",
                },
                "wholesale_funding": {
                    "description": "Wholesale " "funding " "balance.",
                    "type": "number",
                },
                "wholesale_runoff": {
                    "default": 1.0,
                    "description": "Wholesale " "run-off rate " "(default " "100%).",
                    "type": "number",
                },
            },
            "required": ["retail_deposits", "wholesale_funding", "hqla"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/idiosyncratic_stress_scenario",
        "summary": "Idiosyncratic (name-specific) stress scenario.",
        "tool_name": "idiosyncratic_stress_scenario",
    },
    {
        "description": "Combines the institution's own counterbalancing-capacity coverage ratio\n"
        "(CBC / stressed outflow) with the survival-horizon adequacy versus the\n"
        "internal minimum (commonly 90 days). Both must hold for internal adequacy.",
        "domain": "liquidity",
        "function_name": "ilaap_internal_liquidity_metric",
        "input_schema": {
            "properties": {
                "counterbalancing_capacity": {
                    "description": "Total " "monetisable " "liquidity " "(CBC).",
                    "type": "number",
                },
                "minimum_survival_days": {
                    "default": 90.0,
                    "description": "Internal " "minimum " "survival " "target.",
                    "type": "number",
                },
                "stressed_net_outflow": {
                    "description": "Stressed " "net " "outflow " "over the " "horizon.",
                    "type": "number",
                },
                "survival_days": {
                    "description": "Modelled " "survival " "horizon in " "days.",
                    "type": "number",
                },
            },
            "required": ["counterbalancing_capacity", "stressed_net_outflow", "survival_days"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/ilaap_internal_liquidity_metric",
        "summary": "ILAAP internal liquidity adequacy metric.",
        "tool_name": "ilaap_internal_liquidity_metric",
    },
    {
        "description": "Aggregates the outcomes of multiple named liquidity stress scenarios into "
        "an\n"
        "ILAAP-style summary: the binding (worst) scenario, the count of scenarios\n"
        "breached, and overall adequacy. Each scenario value must expose a\n"
        "``surplus_deficit`` figure (as produced by the scenario functions above).\n"
        "\n"
        "SD_k in the rendered formula denotes the ``surplus_deficit`` field each\n"
        "named scenario dict must already carry — this function only aggregates\n"
        "pre-computed values and performs no cash-flow arithmetic itself.",
        "domain": "liquidity",
        "function_name": "ilaap_stress_testing_framework",
        "input_schema": {
            "properties": {
                "scenarios": {
                    "description": "Mapping ``name -> " '{"surplus_deficit": ' "float, ...}``.",
                    "type": "object",
                }
            },
            "required": ["scenarios"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/ilaap_stress_testing_framework",
        "summary": "ILAAP stress-testing framework aggregator.",
        "tool_name": "ilaap_stress_testing_framework",
    },
    {
        "description": "Of the two figures reported, only ``net_debit_peak`` (the largest "
        "negative\n"
        'cumulative position) is the genuine BCBS 248 "largest net debit position"\n'
        "monitoring tool — ``max_usage`` is this codebase's own additional metric,\n"
        "not one of BCBS 248's own monitoring tools.\n"
        "\n"
        "Tracks the intraday liquidity position from time-stamped net payment "
        "flows\n"
        "and reports the peak usage (largest negative intraday position relative "
        "to\n"
        "the opening balance) and the largest net debit position.",
        "domain": "liquidity",
        "function_name": "intraday_liquidity_monitor",
        "input_schema": {
            "properties": {
                "net_flows": {
                    "description": "Net payment flow at "
                    "each timestamp "
                    "(credit +, debit "
                    "-).",
                    "type": "object",
                },
                "opening_balance": {
                    "description": "Available " "intraday " "liquidity at " "start of day.",
                    "type": "number",
                },
                "timestamps": {
                    "description": "Monotonic intraday "
                    "timestamps "
                    "(seconds/minutes "
                    "from open).",
                    "type": "object",
                },
            },
            "required": ["timestamps", "net_flows", "opening_balance"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/intraday_liquidity_monitor",
        "summary": "Intraday liquidity monitor (BCBS 248).",
        "tool_name": "intraday_liquidity_monitor",
    },
    {
        "description": "This is this codebase's own internal stress design — delaying a fraction\n"
        "of positive intraday inflows — set in the context of BCBS 248's intraday-\n"
        "liquidity monitoring framework; it is not BCBS 248's own prescribed "
        "stress\n"
        "design.\n"
        "\n"
        "Stresses the intraday profile by delaying a fraction of *inflows* "
        "(positive\n"
        "flows): a ``delay_factor`` of expected inflows is removed from the "
        "intraday\n"
        "path, sharpening the peak liquidity requirement. Reports the stressed "
        "peak\n"
        "usage and whether the opening buffer plus any additional shock survives.",
        "domain": "liquidity",
        "function_name": "intraday_liquidity_stress_test",
        "input_schema": {
            "properties": {
                "delay_factor": {
                    "default": 0.5,
                    "description": "Fraction of "
                    "positive inflows "
                    "delayed beyond "
                    "the horizon, in "
                    "[0, 1].",
                    "type": "number",
                },
                "inflow_delay_shock": {
                    "default": 0.0,
                    "description": "Extra "
                    "absolute "
                    "liquidity "
                    "reserved "
                    "against "
                    "the shock.",
                    "type": "number",
                },
                "net_flows": {
                    "description": "Net payment flow at "
                    "each intraday step "
                    "(credit +, debit "
                    "-).",
                    "type": "object",
                },
                "opening_balance": {
                    "description": "Available " "intraday " "liquidity at " "start of day.",
                    "type": "number",
                },
            },
            "required": ["net_flows", "opening_balance"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/intraday_liquidity_stress_test",
        "summary": "Intraday liquidity stress test (BCBS 248 stress scenarios).",
        "tool_name": "intraday_liquidity_stress_test",
    },
    {
        "description": "Nets bilateral liquidity positions across group entities to derive each\n"
        "entity's net provider/receiver status and the total internal liquidity\n"
        "transferred. Positive = net provider of liquidity to the group.",
        "domain": "liquidity",
        "function_name": "intragroup_liquidity_flow",
        "input_schema": {
            "properties": {
                "entity_positions": {
                    "description": "Mapping "
                    "``entity -> "
                    "net "
                    "position`` "
                    "(provided "
                    "minus "
                    "received).",
                    "type": "object",
                }
            },
            "required": ["entity_positions"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/intragroup_liquidity_flow",
        "summary": "Intragroup liquidity flow netting.",
        "tool_name": "intragroup_liquidity_flow",
    },
    {
        "description": "The required buffer equals the maximum cumulative net outflow over the\n"
        "stress horizon (the deepest point of the cash-flow trough), optionally\n"
        "uplifted by a management ``confidence_buffer`` margin.",
        "domain": "liquidity",
        "function_name": "liquidity_buffer_sizing",
        "input_schema": {
            "properties": {
                "confidence_buffer": {
                    "default": 0.0,
                    "description": "Fractional " "management " "uplift " "(e.g. 0.10 " "for +10%).",
                    "type": "number",
                },
                "stressed_net_outflows": {
                    "description": "Per-period "
                    "stressed "
                    "net "
                    "outflows "
                    "(positive "
                    "= "
                    "drain).",
                    "type": "object",
                },
            },
            "required": ["stressed_net_outflows"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/liquidity_buffer_sizing",
        "summary": "Size the liquidity buffer to the peak cumulative stressed outflow.",
        "tool_name": "liquidity_buffer_sizing",
    },
    {
        "description": "``LCR = HQLA / net 30-day outflows`` where net outflows are gross "
        "outflows\n"
        "minus *capped* inflows. Recognised inflows are floored at ``inflow_cap`` "
        "of\n"
        "gross outflows (default 75%), guaranteeing net outflows never fall below\n"
        "25% of gross — the BCBS 238 §69 cap.",
        "domain": "liquidity",
        "function_name": "liquidity_coverage_ratio_lcr",
        "input_schema": {
            "properties": {
                "gross_inflows": {
                    "description": "Total expected " "30-day " "contractual " "cash inflows.",
                    "type": "number",
                },
                "gross_outflows": {
                    "description": "Total expected " "30-day " "stressed cash " "outflows.",
                    "type": "number",
                },
                "hqla": {
                    "description": "Stock of high-quality " "liquid assets " "(post-haircut).",
                    "type": "number",
                },
                "inflow_cap": {
                    "default": 0.75,
                    "description": "Maximum fraction "
                    "of gross outflows "
                    "that inflows may "
                    "offset.",
                    "type": "number",
                },
            },
            "required": ["hqla", "gross_outflows", "gross_inflows"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/liquidity_coverage_ratio_lcr",
        "summary": "Basel III Liquidity Coverage Ratio.",
        "tool_name": "liquidity_coverage_ratio_lcr",
    },
    {
        "description": "Computes the structural maturity mismatch: ``gap_i = assets_i -\n"
        "liabilities_i`` per bucket, plus the cumulative gap. A positive "
        "cumulative\n"
        "gap means more assets than liabilities mature by that point (a funding\n"
        "surplus); a negative gap signals a refinancing need.\n"
        "\n"
        "Like the two cash-flow-ladder functions above, an optional opening "
        "balance\n"
        "is added to every cumulative-gap entry — the starting cash / HQLA "
        "position\n"
        "carried into the first bucket. It defaults to 0.0, so existing callers "
        "see\n"
        "no change in behaviour.",
        "domain": "liquidity",
        "function_name": "liquidity_gap_analysis",
        "input_schema": {
            "properties": {
                "asset_maturities": {
                    "description": "Asset cash " "inflows " "maturing in " "each bucket.",
                    "type": "object",
                },
                "buckets": {
                    "description": "Optional bucket "
                    "labels; defaults to "
                    "the standard 8-bucket "
                    "set.",
                    "type": "object",
                },
                "liability_maturities": {
                    "description": "Liability "
                    "cash "
                    "outflows "
                    "maturing "
                    "in each "
                    "bucket.",
                    "type": "object",
                },
            },
            "required": ["asset_maturities", "liability_maturities"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/liquidity_gap_analysis",
        "summary": "Maturity-bucket liquidity gap (assets vs liabilities).",
        "tool_name": "liquidity_gap_analysis",
    },
    {
        "description": "For ``higher_is_better`` metrics (LCR, NSFR, survival days) green is at "
        "or\n"
        "above ``green_threshold`` and red below ``amber_threshold``. For\n"
        "lower-is-better metrics (e.g. funding concentration) the comparison "
        "inverts.\n"
        "\n"
        "This is a piecewise categorical rule rather than a continuous formula, "
        "and\n"
        "the Try-it panel's rendered formula shows only the higher-is-better\n"
        "direction; the comparison flips (green <= amber <= metric) when\n"
        "``higher_is_better`` is False.",
        "domain": "liquidity",
        "function_name": "liquidity_risk_appetite_threshold",
        "input_schema": {
            "properties": {
                "amber_threshold": {
                    "description": "Boundary for " "the amber " "zone.",
                    "type": "number",
                },
                "green_threshold": {
                    "description": "Boundary for " "the green " "zone.",
                    "type": "number",
                },
                "higher_is_better": {
                    "default": True,
                    "description": "Direction of " "the metric.",
                    "type": "boolean",
                },
                "metric_value": {"description": "Current metric " "value.", "type": "number"},
            },
            "required": ["metric_value", "green_threshold", "amber_threshold"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/liquidity_risk_appetite_threshold",
        "summary": "Map a liquidity metric to a RAG (red/amber/green) risk-appetite zone.",
        "tool_name": "liquidity_risk_appetite_threshold",
    },
    {
        "description": "Combines individual liquidity metric scores (each typically 0-100) into a\n"
        "single weighted composite score and maps it to a RAG rating.",
        "domain": "liquidity",
        "function_name": "liquidity_scorecard_aggregation",
        "input_schema": {
            "properties": {
                "scores": {"description": "Individual component " "scores.", "type": "object"},
                "weights": {
                    "description": "Weight per component " "(need not sum to 1; " "normalised).",
                    "type": "object",
                },
            },
            "required": ["scores", "weights"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/liquidity_scorecard_aggregation",
        "summary": "Weighted liquidity scorecard aggregation.",
        "tool_name": "liquidity_scorecard_aggregation",
    },
    {
        "description": "Applies category-specific run-off rates to funding balances to derive\n"
        "stressed outflows, nets inflows, and tests whether HQLA covers the net\n"
        "stressed outflow.",
        "domain": "liquidity",
        "function_name": "liquidity_stress_scenario",
        "input_schema": {
            "properties": {
                "balances": {
                    "description": "Outstanding balance " "of each funding " "category.",
                    "type": "object",
                },
                "hqla": {
                    "description": "Available high-quality " "liquid assets " "(post-haircut).",
                    "type": "number",
                },
                "inflows": {
                    "default": 0.0,
                    "description": "Stressed contractual " "inflows over the " "horizon.",
                    "type": "number",
                },
                "runoff_rates": {
                    "description": "Stressed run-off " "rate per " "category, each " "in [0, 1].",
                    "type": "object",
                },
            },
            "required": ["balances", "runoff_rates", "hqla"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/liquidity_stress_scenario",
        "summary": "Generic single liquidity stress scenario.",
        "tool_name": "liquidity_stress_scenario",
    },
    {
        "description": "The FTP charge passes the cost of liquidity to business lines: the all-in\n"
        "transfer rate is ``base_rate + term liquidity premium + contingent "
        "liquidity\n"
        "premium``. The annual charge is that rate applied to notional; the "
        "lifetime\n"
        "charge multiplies by tenor.",
        "domain": "liquidity",
        "function_name": "liquidity_transfer_pricing",
        "input_schema": {
            "properties": {
                "base_rate": {
                    "description": "Reference/base " "funding rate " "(decimal).",
                    "type": "number",
                },
                "contingent_spread": {
                    "default": 0.0,
                    "description": "Contingent "
                    "liquidity "
                    "premium for "
                    "undrawn/optional "
                    "commitments "
                    "(decimal).",
                    "type": "number",
                },
                "liquidity_spread": {
                    "description": "Term " "liquidity " "premium " "(decimal).",
                    "type": "number",
                },
                "notional": {"description": "Position notional " "being funded.", "type": "number"},
                "tenor_years": {
                    "description": "Funding tenor in " "years (>= 0).",
                    "type": "number",
                },
            },
            "required": ["notional", "tenor_years", "base_rate", "liquidity_spread"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/liquidity_transfer_pricing",
        "summary": "Liquidity Transfer Pricing (LTP) charge for a funding position.",
        "tool_name": "liquidity_transfer_pricing",
    },
    {
        "description": "Simulates the distribution of stressed net cash outflows as\n"
        "``base_outflow * (1 + vol * Z)`` and reads the loss quantile at the\n"
        "confidence level. LiqVaR is the outflow level not exceeded with the given\n"
        "confidence — the liquidity analogue of market VaR.\n"
        "\n"
        "Per CLAUDE.md §3.1 RULE 3 the N(0,1) shocks are pre-drawn in pure Python "
        "and\n"
        "passed to the JIT kernel; an analytic normal quantile is also returned "
        "for\n"
        "validation.\n"
        "\n"
        "``liqvar`` is a simulated order statistic of this floored-at-zero\n"
        "normal-shock model, cross-validated only against its own analytic\n"
        "counterpart ``liqvar_analytic`` rather than a regulatory reference, using\n"
        "index ``floor(confidence_level * n_simulations)`` capped at\n"
        "``n_simulations - 1``.",
        "domain": "liquidity",
        "function_name": "liquidity_var_liqvar",
        "input_schema": {
            "properties": {
                "base_outflow": {"description": "Expected net " "cash outflow.", "type": "number"},
                "confidence_level": {
                    "default": 0.99,
                    "description": "Confidence " "in [0.90, " "0.9999].",
                    "type": "number",
                },
                "n_simulations": {
                    "default": 100000,
                    "description": "Number of Monte " "Carlo draws.",
                    "type": "integer",
                },
                "outflow_vol": {
                    "description": "Relative " "volatility of net " "outflow (>= 0).",
                    "type": "number",
                },
                "seed": {
                    "default": 42,
                    "description": "RNG seed for " "reproducibility.",
                    "type": "object",
                },
            },
            "required": ["base_outflow", "outflow_vol"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/liquidity_var_liqvar",
        "summary": "Liquidity VaR (LiqVaR) by Monte Carlo simulation of stressed net outflows.",
        "tool_name": "liquidity_var_liqvar",
    },
    {
        "description": "Models a system-wide crisis where HQLA monetisation value falls due to\n"
        "widened market haircuts (flight to quality, fire-sale discounts). "
        "Outflows\n"
        "are met from the haircut-reduced HQLA value.",
        "domain": "liquidity",
        "function_name": "market_wide_stress_scenario",
        "input_schema": {
            "properties": {
                "hqla_by_level": {
                    "description": "HQLA market " "value per level " "(e.g. [L1, L2A, " "L2B]).",
                    "type": "object",
                },
                "market_haircuts": {
                    "description": "Additional "
                    "stressed "
                    "haircut per "
                    "level, each "
                    "in [0, 1].",
                    "type": "object",
                },
                "outflow": {
                    "description": "Stressed net cash " "outflow over the " "horizon.",
                    "type": "number",
                },
            },
            "required": ["hqla_by_level", "market_haircuts", "outflow"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/market_wide_stress_scenario",
        "summary": "Market-wide stress scenario.",
        "tool_name": "market_wide_stress_scenario",
    },
    {
        "description": "``NSFR = ASF / RSF`` and must be >= 100% (BCBS 295). Measures the "
        "proportion\n"
        "of long-term assets funded by stable funding sources over a one-year "
        "horizon.",
        "domain": "liquidity",
        "function_name": "net_stable_funding_ratio_nsfr",
        "input_schema": {
            "properties": {
                "available_stable_funding": {
                    "description": "Total "
                    "ASF "
                    "(see "
                    ":func:`available_stable_funding_asf_calc`).",
                    "type": "number",
                },
                "required_stable_funding": {
                    "description": "Total "
                    "RSF "
                    "(see "
                    ":func:`required_stable_funding_rsf_calc`).",
                    "type": "number",
                },
            },
            "required": ["available_stable_funding", "required_stable_funding"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/net_stable_funding_ratio_nsfr",
        "summary": "Basel III Net Stable Funding Ratio.",
        "tool_name": "net_stable_funding_ratio_nsfr",
    },
    {
        "description": "Under stress, repo haircuts widen by a multiplier. The incremental margin\n"
        "requirement is the extra collateral (or cash) the institution must post "
        "to\n"
        "maintain the same secured borrowing.",
        "domain": "liquidity",
        "function_name": "repo_market_stress_haircut",
        "input_schema": {
            "properties": {
                "base_haircuts": {
                    "description": "Current repo "
                    "haircut per "
                    "collateral "
                    "type, in [0, "
                    "1].",
                    "type": "object",
                },
                "collateral_values": {
                    "description": "Market " "value of " "pledged " "collateral " "per type.",
                    "type": "object",
                },
                "stress_multipliers": {
                    "description": "Multiplier "
                    "applied to "
                    "each "
                    "haircut "
                    "under "
                    "stress (>= "
                    "1.0).",
                    "type": "object",
                },
            },
            "required": ["base_haircuts", "stress_multipliers", "collateral_values"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/repo_market_stress_haircut",
        "summary": "Repo market stress — incremental margin call from widened haircuts.",
        "tool_name": "repo_market_stress_haircut",
    },
    {
        "description": "RSF is the weighted sum of assets by their RSF factor. More liquid / "
        "shorter\n"
        "assets attract lower factors (Level 1 HQLA = 5%, Level 2A = 15%, loans = "
        "50-\n"
        "85%, illiquid assets = 100%).",
        "domain": "liquidity",
        "function_name": "required_stable_funding_rsf_calc",
        "input_schema": {
            "properties": {
                "asset_amounts": {
                    "description": "Carrying " "amounts of each " "asset / " "off-balance " "item.",
                    "type": "object",
                },
                "rsf_factors": {
                    "description": "RSF factor for " "each asset, each " "in [0, 1].",
                    "type": "object",
                },
            },
            "required": ["asset_amounts", "rsf_factors"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/required_stable_funding_rsf_calc",
        "summary": "Required Stable Funding for the NSFR denominator.",
        "tool_name": "required_stable_funding_rsf_calc",
    },
    {
        "description": "Computes the blended run-off rate across retail deposit categories (e.g.\n"
        "stable 5%, less-stable 10%, non-operational higher) and the total "
        "expected\n"
        "30-day run-off amount.",
        "domain": "liquidity",
        "function_name": "retail_deposit_runoff_rate",
        "input_schema": {
            "properties": {
                "deposit_balances": {
                    "description": "Balance per " "retail " "deposit " "category.",
                    "type": "object",
                },
                "runoff_rates": {
                    "description": "Run-off rate per " "category, each " "in [0, 1].",
                    "type": "object",
                },
            },
            "required": ["deposit_balances", "runoff_rates"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/retail_deposit_runoff_rate",
        "summary": "Aggregate retail deposit run-off (Basel LCR categories).",
        "tool_name": "retail_deposit_runoff_rate",
    },
    {
        "description": "Estimates the funding gap from secured transactions that fail to roll: "
        "the\n"
        "non-rolled portion of each maturing tranche must be replaced or repaid.",
        "domain": "liquidity",
        "function_name": "secured_funding_rollover_risk",
        "input_schema": {
            "properties": {
                "maturing_amounts": {
                    "description": "Amount of " "secured " "funding " "maturing per " "tranche.",
                    "type": "object",
                },
                "rollover_rates": {
                    "description": "Assumed "
                    "rollover "
                    "(renewal) rate "
                    "per tranche, "
                    "in [0, 1].",
                    "type": "object",
                },
            },
            "required": ["maturing_amounts", "rollover_rates"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/secured_funding_rollover_risk",
        "summary": "Secured funding (repo) rollover risk.",
        "tool_name": "secured_funding_rollover_risk",
    },
    {
        "description": "Walks forward through the daily net-outflow path subtracting from the "
        "HQLA\n"
        "counterbalancing capacity. The survival horizon is the last day on which "
        "the\n"
        "remaining buffer is still non-negative.\n"
        "\n"
        "``survival_days`` is the 0-indexed day on which cumulative outflow first\n"
        "drives the buffer negative, so it equals the count of full days survived\n"
        "before breach (0 if the very first day breaches).",
        "domain": "liquidity",
        "function_name": "survival_horizon_calculator",
        "input_schema": {
            "properties": {
                "daily_net_outflows": {
                    "description": "Array of "
                    "daily net "
                    "cash "
                    "outflows "
                    "(positive "
                    "= drain).",
                    "type": "object",
                },
                "hqla": {
                    "description": "Opening counterbalancing " "capacity (HQLA).",
                    "type": "number",
                },
            },
            "required": ["hqla", "daily_net_outflows"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/survival_horizon_calculator",
        "summary": "Survival horizon — days until cumulative net outflow exhausts HQLA.",
        "tool_name": "survival_horizon_calculator",
    },
    {
        "description": "Computes the HHI of funding shares across counterparties (sum of squared\n"
        "shares, in [1/n, 1]) plus the largest single-counterparty share. Higher "
        "HHI\n"
        "means more concentrated, less diversified funding.",
        "domain": "liquidity",
        "function_name": "wholesale_funding_concentration",
        "input_schema": {
            "properties": {
                "counterparty_amounts": {
                    "description": "Funding "
                    "amount "
                    "from "
                    "each "
                    "wholesale "
                    "counterparty.",
                    "type": "object",
                }
            },
            "required": ["counterparty_amounts"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/wholesale_funding_concentration",
        "summary": "Wholesale funding concentration via the Herfindahl-Hirschman Index.",
        "tool_name": "wholesale_funding_concentration",
    },
]

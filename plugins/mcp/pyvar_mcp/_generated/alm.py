"""plugins/mcp/pyvar_mcp/_generated/alm.py — GENERATED, do not edit by hand.

The alm tools. Regenerate with: python3 scripts/generate_mcp_tools.py (from the
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
        "description": "Note: the per-scenario ΔEVE values are computed entirely inside\n"
        ":func:`~engine.alm_nii_eve.eve_sensitivity_analysis` (the same PV formula\n"
        "used by ``economic_value_of_equity_eve``); this function only adds the\n"
        "Tier-1 capital ratio and the 15% outlier-test check on top.\n"
        "\n"
        "[REGULATORY] BCBS d368. Computes ΔEVE across the six standard shocks and\n"
        "expresses the worst-case loss as a fraction of Tier-1 capital (the\n"
        "supervisory outlier ratio).",
        "domain": "alm",
        "function_name": "alm_stress_test",
        "input_schema": {
            "properties": {
                "base_rates": {
                    "description": "Base zero rate per " "bucket (decimal).",
                    "type": "object",
                },
                "net_cashflows": {
                    "description": "Net " "banking-book " "cashflow per " "bucket.",
                    "type": "object",
                },
                "parallel_bps": {
                    "default": 200.0,
                    "description": "Parallel shock " "magnitude (bps).",
                    "type": "number",
                },
                "tier1_capital": {
                    "description": "Tier-1 capital " "(currency, > " "0).",
                    "type": "number",
                },
                "times": {"description": "Bucket times in years.", "type": "object"},
            },
            "required": ["net_cashflows", "times", "base_rates", "tier1_capital"],
            "type": "object",
        },
        "path": "/api/v1/alm/alm_stress_test",
        "summary": "Run an ALM stress test: worst-case EVE decline vs Tier-1 capital.",
        "tool_name": "alm_stress_test",
    },
    {
        "description": "Index = normalised absolute duration gap\n"
        "``|D_A·A − D_L·L| / A`` — zero when the book is perfectly immunised.",
        "domain": "alm",
        "function_name": "asset_liability_mismatch_index",
        "input_schema": {
            "properties": {
                "asset_amounts": {
                    "description": "Amount per " "asset bucket " "(currency).",
                    "type": "object",
                },
                "asset_durations": {
                    "description": "Duration per " "asset bucket " "(years).",
                    "type": "object",
                },
                "liability_amounts": {
                    "description": "Amount per " "liability " "bucket.",
                    "type": "object",
                },
                "liability_durations": {
                    "description": "Duration " "per " "liability " "bucket.",
                    "type": "object",
                },
            },
            "required": [
                "asset_durations",
                "asset_amounts",
                "liability_durations",
                "liability_amounts",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/asset_liability_mismatch_index",
        "summary": "Asset-liability mismatch index from duration-weighted exposures.",
        "tool_name": "asset_liability_mismatch_index",
    },
    {
        "description": "Assets and liabilities grow geometrically; equity is the residual; NII "
        "each\n"
        "year is ``assets·yield − liabilities·cost``. Returns the projected paths.",
        "domain": "alm",
        "function_name": "balance_sheet_projection_model",
        "input_schema": {
            "properties": {
                "asset_growth_rate": {
                    "description": "Annual " "asset " "growth " "(decimal).",
                    "type": "number",
                },
                "asset_yield": {
                    "description": "Average asset " "yield (decimal).",
                    "type": "number",
                },
                "initial_assets": {
                    "description": "Opening total " "assets " "(currency).",
                    "type": "number",
                },
                "initial_liabilities": {
                    "description": "Opening " "total " "liabilities " "(currency).",
                    "type": "number",
                },
                "liability_cost": {
                    "description": "Average " "liability cost " "(decimal).",
                    "type": "number",
                },
                "liability_growth_rate": {
                    "description": "Annual " "liability " "growth " "(decimal).",
                    "type": "number",
                },
                "n_years": {
                    "description": "Projection horizon " "(years, >= 1).",
                    "type": "integer",
                },
            },
            "required": [
                "initial_assets",
                "initial_liabilities",
                "asset_growth_rate",
                "liability_growth_rate",
                "asset_yield",
                "liability_cost",
                "n_years",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/balance_sheet_projection_model",
        "summary": "Project the balance sheet and NII forward over ``n_years``.",
        "tool_name": "balance_sheet_projection_model",
    },
    {
        "description": "[REGULATORY] BCBS d368 — basis risk arises when assets and liabilities\n"
        "reprice off different indices. ΔNII = Σ A·Δi_A − Σ L·Δi_L.",
        "domain": "alm",
        "function_name": "basis_risk_irrbb",
        "input_schema": {
            "properties": {
                "asset_balances": {
                    "description": "Balance per " "asset index " "bucket.",
                    "type": "object",
                },
                "asset_index_shifts": {
                    "description": "Index move " "per asset " "bucket " "(decimal).",
                    "type": "object",
                },
                "liability_balances": {
                    "description": "Balance " "per " "liability " "index " "bucket.",
                    "type": "object",
                },
                "liability_index_shifts": {
                    "description": "Index " "move " "per " "liability " "bucket " "(decimal).",
                    "type": "object",
                },
            },
            "required": [
                "asset_balances",
                "asset_index_shifts",
                "liability_balances",
                "liability_index_shifts",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/basis_risk_irrbb",
        "summary": "Basis risk: NII impact of imperfectly-correlated index repricing.",
        "tool_name": "basis_risk_irrbb",
    },
    {
        "description": "[LIMITATION] This is a bespoke core/non-core exponential-decay run-off\n"
        "model, not an implementation of BCBS d368's standardised NMD slotting\n"
        "methodology -- the BCBS d368 reference below names the regulatory context\n"
        "this model addresses, not the calculation performed here.\n"
        "\n"
        "[REGULATORY] BCBS d368 NMD treatment. Core deposits are stable and decay\n"
        "slowly; non-core (volatile) deposits run off quickly. Returns the "
        "projected\n"
        "surviving balance and the effective average life.",
        "domain": "alm",
        "function_name": "behavioural_modelling_nmds",
        "input_schema": {
            "properties": {
                "core_fraction": {
                    "description": "Fraction deemed " "core in [0, 1].",
                    "type": "number",
                },
                "core_runoff_rate": {
                    "description": "Annual " "run-off rate " "of core " "deposits " "(decimal).",
                    "type": "number",
                },
                "horizon_years": {
                    "default": 5.0,
                    "description": "Projection " "horizon " "(years).",
                    "type": "number",
                },
                "non_core_runoff_rate": {
                    "description": "Annual " "run-off " "rate of " "non-core " "(decimal).",
                    "type": "number",
                },
                "total_balance": {
                    "description": "Total NMD " "balance " "(currency).",
                    "type": "number",
                },
            },
            "required": [
                "total_balance",
                "core_fraction",
                "core_runoff_rate",
                "non_core_runoff_rate",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/behavioural_modelling_nmds",
        "summary": "Model non-maturity-deposit (NMD) run-off splitting core / non-core.",
        "tool_name": "behavioural_modelling_nmds",
    },
    {
        "description": "``CGAP = C_A − (L/A)·C_L`` — the second-order term refining the\n"
        "duration-gap EVE estimate ``ΔEVE ≈ A(−DGAP·Δy + ½·CGAP·Δy²)``.",
        "domain": "alm",
        "function_name": "convexity_gap",
        "input_schema": {
            "properties": {
                "asset_convexity": {
                    "description": "Weighted " "asset " "convexity.",
                    "type": "number",
                },
                "liability_convexity": {
                    "description": "Weighted " "liability " "convexity.",
                    "type": "number",
                },
                "total_assets": {"description": "Total assets " "(currency).", "type": "number"},
                "total_liabilities": {
                    "description": "Total " "liabilities " "(currency).",
                    "type": "number",
                },
            },
            "required": [
                "asset_convexity",
                "liability_convexity",
                "total_assets",
                "total_liabilities",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/convexity_gap",
        "summary": "Convexity gap of the banking book.",
        "tool_name": "convexity_gap",
    },
    {
        "description": "``core_deposit_duration`` (the primary, default figure) is a discrete\n"
        "monthly Riemann sum over the exponential run-off schedule, truncated at\n"
        "``max_years``:\n"
        "``D = sum_t[t*B*decay_rate*e^{-(decay_rate+discount_rate)t}]\n"
        "      / sum_t[B*decay_rate*e^{-(decay_rate+discount_rate)t}]``\n"
        "for ``t = 1/12, 2/12, ..., max_years``.\n"
        "\n"
        "A genuine closed form exists for the *untruncated* (``max_years`` ->\n"
        "infinity) continuous-time version of the same model: the run-off density\n"
        "``core_balance*decay_rate*e^{-decay_rate*t}`` is the density of an\n"
        "Exponential(``decay_rate``) survival distribution, and PV-weighting it by\n"
        "``e^{-discount_rate*t}`` is equivalent to re-weighting by\n"
        "Exponential(``decay_rate + discount_rate``) — whose mean is exactly\n"
        "``1 / (decay_rate + discount_rate)``. That value, plus its closed-form PV\n"
        "``core_balance*decay_rate / (decay_rate + discount_rate)``, is returned "
        "as\n"
        "``closed_form_duration`` / ``closed_form_present_value`` for reference,\n"
        "but is NOT used for the primary ``core_deposit_duration`` figure.\n"
        "\n"
        "Why the truncated discrete sum stays the default instead of switching to\n"
        "the closed form (validated numerically — see\n"
        "``tests/test_alm_behavioural.py::test_core_deposit_duration_closed_form``):\n"
        "the two diverge materially whenever ``max_years`` is not several "
        "multiples\n"
        "of the implied continuous duration ``1/(decay_rate+discount_rate)``. For\n"
        'the slow-decaying "sticky" core books this function exists to model, that\n'
        "ratio is often well under 3x at the ``max_years=30`` default — e.g.\n"
        "``decay_rate=0.05, discount_rate=0.02`` implies a 14.3y continuous\n"
        "duration against a 30y truncation, and the discrete figure understates\n"
        "the closed form by ~29%. So ``max_years`` is a real, user-set truncation\n"
        "of the run-off horizon here, not just a numerical implementation detail,\n"
        "and silently dropping it would change the model's economics, not just its\n"
        "numerics. Even where truncation is immaterial\n"
        "(``max_years >> 1/(decay_rate+discount_rate)``), the monthly\n"
        "right-Riemann-sum quadrature itself carries a systematic +dt/2 (~0.042y)\n"
        "bias relative to the continuous integral, which is non-negligible against\n"
        "a 0.1-0.5% tolerance for short-duration books (e.g. ``decay_rate=0.30,\n"
        "discount_rate=0.10`` -> ~1.7% bias even with a generous horizon).\n"
        "\n"
        "Core deposits run off at ``decay_rate`` (exponential). The duration is "
        "the\n"
        "PV-weighted average life of the run-off cashflows discounted at\n"
        "``discount_rate`` — typically multi-year, which is why NMDs anchor the\n"
        "liability side of the duration gap.",
        "domain": "alm",
        "function_name": "core_deposit_duration",
        "input_schema": {
            "properties": {
                "core_balance": {
                    "description": "Core deposit " "balance " "(currency).",
                    "type": "number",
                },
                "decay_rate": {
                    "description": "Annual exponential " "decay rate " "(decimal, > 0).",
                    "type": "number",
                },
                "discount_rate": {
                    "description": "Discount rate " "(decimal, >= " "0).",
                    "type": "number",
                },
                "max_years": {
                    "default": 30.0,
                    "description": "Truncation horizon " "for the run-off " "integral.",
                    "type": "number",
                },
            },
            "required": ["core_balance", "decay_rate", "discount_rate"],
            "type": "object",
        },
        "path": "/api/v1/alm/core_deposit_duration",
        "summary": "Effective duration of core deposits modelled as a decaying annuity.",
        "tool_name": "core_deposit_duration",
    },
    {
        "description": "Duration gap ``DGAP = D_A − (L/A)·D_L``. The change in economic value of\n"
        "equity for a rate shock is approximately ``ΔEVE ≈ −DGAP · A · Δy``.",
        "domain": "alm",
        "function_name": "duration_gap_analysis",
        "input_schema": {
            "properties": {
                "asset_duration": {
                    "description": "Weighted asset " "duration " "(years).",
                    "type": "number",
                },
                "liability_duration": {
                    "description": "Weighted " "liability " "duration " "(years).",
                    "type": "number",
                },
                "rate_shock": {
                    "default": 0.01,
                    "description": "Parallel rate " "shock (decimal).",
                    "type": "number",
                },
                "total_assets": {"description": "Total assets " "(currency).", "type": "number"},
                "total_liabilities": {
                    "description": "Total " "liabilities " "(currency).",
                    "type": "number",
                },
            },
            "required": [
                "asset_duration",
                "liability_duration",
                "total_assets",
                "total_liabilities",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/duration_gap_analysis",
        "summary": "Duration-gap analysis of the banking book.",
        "tool_name": "duration_gap_analysis",
    },
    {
        "description": "Applies per-bucket growth rates compounding over ``n_periods`` and "
        "returns\n"
        "the projected gap path — capturing new business unlike a static gap.",
        "domain": "alm",
        "function_name": "dynamic_gap_analysis",
        "input_schema": {
            "properties": {
                "asset_growth": {
                    "description": "Per-period asset " "growth rate per " "bucket " "(decimal).",
                    "type": "object",
                },
                "bucket_assets": {
                    "description": "Initial " "rate-sensitive " "assets per " "bucket.",
                    "type": "object",
                },
                "bucket_liabilities": {
                    "description": "Initial " "rate-sensitive " "liabilities " "per " "bucket.",
                    "type": "object",
                },
                "liability_growth": {
                    "description": "Per-period " "liability " "growth rate " "per bucket.",
                    "type": "object",
                },
                "n_periods": {"description": "Number of " "projection periods.", "type": "integer"},
            },
            "required": [
                "bucket_assets",
                "bucket_liabilities",
                "asset_growth",
                "liability_growth",
                "n_periods",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/dynamic_gap_analysis",
        "summary": "Dynamic gap projecting balance growth over future periods.",
        "tool_name": "dynamic_gap_analysis",
    },
    {
        "description": "[REGULATORY] BCBS d368. EVE is the residual economic value accruing to\n"
        "equity holders after discounting all banking-book cashflows.",
        "domain": "alm",
        "function_name": "economic_value_of_equity_eve",
        "input_schema": {
            "properties": {
                "asset_cashflows": {
                    "description": "Asset " "cashflow per " "bucket.",
                    "type": "object",
                },
                "asset_rates": {
                    "description": "Discount zero " "rate per asset " "bucket (decimal).",
                    "type": "object",
                },
                "asset_times": {
                    "description": "Asset cashflow " "time per bucket " "(years).",
                    "type": "object",
                },
                "liability_cashflows": {
                    "description": "Liability " "cashflow " "per " "bucket.",
                    "type": "object",
                },
                "liability_rates": {
                    "description": "Discount zero " "rate per " "liability " "bucket " "(decimal).",
                    "type": "object",
                },
                "liability_times": {
                    "description": "Liability " "cashflow time " "per bucket " "(years).",
                    "type": "object",
                },
            },
            "required": [
                "asset_cashflows",
                "asset_times",
                "liability_cashflows",
                "liability_times",
                "asset_rates",
                "liability_rates",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/economic_value_of_equity_eve",
        "summary": "Economic Value of Equity: PV(assets) − PV(liabilities).",
        "tool_name": "economic_value_of_equity_eve",
    },
    {
        "description": "``D_eff = (PV− − PV+) / (2 · PV0 · Δy)`` — captures optionality in "
        "deposits,\n"
        "prepayments and caps/floors that analytic duration misses.",
        "domain": "alm",
        "function_name": "effective_duration_alm",
        "input_schema": {
            "properties": {
                "pv_base": {"description": "Present value at base " "rates.", "type": "number"},
                "pv_down": {
                    "description": "Present value after " "−``rate_shock``.",
                    "type": "number",
                },
                "pv_up": {
                    "description": "Present value after " "+``rate_shock``.",
                    "type": "number",
                },
                "rate_shock": {
                    "description": "Parallel rate " "shock (decimal).",
                    "type": "number",
                },
            },
            "required": ["pv_base", "pv_up", "pv_down", "rate_shock"],
            "type": "object",
        },
        "path": "/api/v1/alm/effective_duration_alm",
        "summary": "Effective duration of an ALM position from re-valued PVs under a shock.",
        "tool_name": "effective_duration_alm",
    },
    {
        "description": "[REGULATORY] BCBS d368. Reports ΔEVE for every prescribed scenario and "
        "the\n"
        "worst case — the headline supervisory metric.",
        "domain": "alm",
        "function_name": "eve_sensitivity_analysis",
        "input_schema": {
            "properties": {
                "base_rates": {
                    "description": "Base zero rate per " "bucket (decimal).",
                    "type": "object",
                },
                "long_bps": {
                    "default": 150.0,
                    "description": "Long shock (bps).",
                    "type": "number",
                },
                "net_cashflows": {
                    "description": "Net (asset − " "liability) " "cashflow per " "bucket.",
                    "type": "object",
                },
                "parallel_bps": {
                    "default": 200.0,
                    "description": "Parallel shock " "(bps).",
                    "type": "number",
                },
                "short_bps": {
                    "default": 300.0,
                    "description": "Short shock (bps).",
                    "type": "number",
                },
                "times": {"description": "Bucket times in years.", "type": "object"},
            },
            "required": ["net_cashflows", "times", "base_rates"],
            "type": "object",
        },
        "path": "/api/v1/alm/eve_sensitivity_analysis",
        "summary": "EVE sensitivity (ΔEVE) under each of the six IRRBB rate shocks.",
        "tool_name": "eve_sensitivity_analysis",
    },
    {
        "description": "Each tenor's transfer rate adds a term-liquidity spread to the base "
        "funding\n"
        "curve. The curve is non-decreasing in the spread component by "
        "construction.",
        "domain": "alm",
        "function_name": "ftp_curve_construction",
        "input_schema": {
            "properties": {
                "base_curve": {
                    "description": "Base funding rate " "per tenor " "(decimal).",
                    "type": "object",
                },
                "liquidity_spreads": {
                    "description": "Term-liquidity " "spread per " "tenor " "(decimal).",
                    "type": "object",
                },
                "tenors": {
                    "description": "Tenor points in years " "(ascending).",
                    "type": "object",
                },
            },
            "required": ["tenors", "base_curve", "liquidity_spreads"],
            "type": "object",
        },
        "path": "/api/v1/alm/ftp_curve_construction",
        "summary": "Construct a matched-maturity FTP curve = base curve + liquidity spread.",
        "tool_name": "ftp_curve_construction",
    },
    {
        "description": "For an asset, the lending unit earns ``customer_rate − ftp_rate`` (credit "
        "/\n"
        "commercial margin) while the central treasury earns the FTP minus its "
        "cost.\n"
        "A liquidity premium is charged on the FTP. Margins sum to the total "
        "spread.",
        "domain": "alm",
        "function_name": "funds_transfer_pricing_ftp",
        "input_schema": {
            "properties": {
                "customer_rate": {
                    "description": "Rate charged to " "/ paid to the " "customer " "(decimal).",
                    "type": "number",
                },
                "ftp_rate": {
                    "description": "Matched-maturity " "transfer rate " "(decimal).",
                    "type": "number",
                },
                "is_asset": {
                    "default": True,
                    "description": "True for an asset "
                    "(loan), False for a "
                    "liability (deposit).",
                    "type": "boolean",
                },
                "liquidity_premium": {
                    "default": 0.0,
                    "description": "Liquidity " "charge " "added to " "the FTP " "(decimal).",
                    "type": "number",
                },
                "notional": {"description": "Deal notional " "(currency).", "type": "number"},
            },
            "required": ["notional", "customer_rate", "ftp_rate"],
            "type": "object",
        },
        "path": "/api/v1/alm/funds_transfer_pricing_ftp",
        "summary": "Funds-transfer-price a single deal into margin components.",
        "tool_name": "funds_transfer_pricing_ftp",
    },
    {
        "description": "[REGULATORY] BCBS d368 Principle 12 (not §118 -- a prior citation here\n"
        "named the wrong section; the 15%-of-Tier-1 supervisory outlier test is "
        "set\n"
        "out under Principle 12): a bank is an outlier if the worst-case EVE\n"
        "decline exceeds 15% of Tier-1 capital. Capital implied is the breach "
        "amount.",
        "domain": "alm",
        "function_name": "interest_rate_risk_capital_irrbb",
        "input_schema": {
            "properties": {
                "outlier_threshold": {
                    "default": 0.15,
                    "description": "Supervisory " "threshold " "(default " "0.15 = " "15%).",
                    "type": "number",
                },
                "tier1_capital": {"description": "Tier-1 capital " "(currency).", "type": "number"},
                "worst_delta_eve": {
                    "description": "Worst-case " "ΔEVE " "(negative for " "a loss).",
                    "type": "number",
                },
            },
            "required": ["worst_delta_eve", "tier1_capital"],
            "type": "object",
        },
        "path": "/api/v1/alm/interest_rate_risk_capital_irrbb",
        "summary": "IRRBB supervisory outlier test against Tier-1 capital.",
        "tool_name": "interest_rate_risk_capital_irrbb",
    },
    {
        "description": "Unlike the standardised framework this accepts an arbitrary matrix of\n"
        "rate-shock scenarios (e.g. historical or Monte Carlo simulated) and "
        "reports\n"
        "the EVE distribution and a 99% worst-case.",
        "domain": "alm",
        "function_name": "irrbb_internal_model",
        "input_schema": {
            "properties": {
                "base_rates": {
                    "description": "Base zero rate per " "bucket (decimal).",
                    "type": "object",
                },
                "net_cashflows": {"description": "Net cashflow " "per bucket.", "type": "object"},
                "rate_scenarios": {
                    "description": "``(n_scenarios, " "n_buckets)`` " "additive rate " "shocks.",
                    "type": "object",
                },
                "times": {"description": "Bucket times in years.", "type": "object"},
            },
            "required": ["net_cashflows", "times", "base_rates", "rate_scenarios"],
            "type": "object",
        },
        "path": "/api/v1/alm/irrbb_internal_model",
        "summary": "Internal-model IRRBB EVE using a bank's own rate scenarios.",
        "tool_name": "irrbb_internal_model",
    },
    {
        "description": "[REGULATORY] BCBS d368 Annex 2 (not §115 -- a prior citation here named\n"
        "the wrong section; Annex 2 is where the shock-construction formulas\n"
        "actually live). The steepener/flattener combine scaled short and long\n"
        "shocks: ``steepener = −0.65·short + 0.90·long`` and\n"
        "``flattener = +0.80·short − 0.60·long`` (per-tenor short/long scalars "
        "decay\n"
        "as ``e^{−t/4}``). See the module docstring for a [LIMITATION] on the\n"
        "default shock magnitudes (``parallel_bps``/``short_bps``/``long_bps``) --\n"
        "BCBS d578 recalibrated these in 2024, effective 2026.",
        "domain": "alm",
        "function_name": "irrbb_six_standard_rate_shocks",
        "input_schema": {
            "properties": {
                "long_bps": {
                    "default": 150.0,
                    "description": "Long-rate shock " "magnitude (basis " "points).",
                    "type": "number",
                },
                "parallel_bps": {
                    "default": 200.0,
                    "description": "Parallel shock " "magnitude (basis " "points).",
                    "type": "number",
                },
                "short_bps": {
                    "default": 300.0,
                    "description": "Short-rate shock " "magnitude (basis " "points).",
                    "type": "number",
                },
                "tenors": {"description": "Tenor points in years " "(> 0).", "type": "object"},
            },
            "required": ["tenors"],
            "type": "object",
        },
        "path": "/api/v1/alm/irrbb_six_standard_rate_shocks",
        "summary": "Construct the six BCBS d368 standard interest-rate shock curves.",
        "tool_name": "irrbb_six_standard_rate_shocks",
    },
    {
        "description": "[REGULATORY] BCBS d368. ΔEVE per scenario is the change in the present "
        "value\n"
        "of net banking-book cashflows under the shocked curve; the regulatory "
        "metric\n"
        "is the maximum loss (most negative ΔEVE).",
        "domain": "alm",
        "function_name": "irrbb_standardised_framework",
        "input_schema": {
            "properties": {
                "base_rates": {
                    "description": "Base zero rate per " "bucket (decimal).",
                    "type": "object",
                },
                "long_bps": {
                    "default": 150.0,
                    "description": "Long shock magnitude " "(bps).",
                    "type": "number",
                },
                "net_cashflows": {
                    "description": "Net (asset − " "liability) " "cashflow per " "time bucket.",
                    "type": "object",
                },
                "parallel_bps": {
                    "default": 200.0,
                    "description": "Parallel shock " "magnitude (bps).",
                    "type": "number",
                },
                "short_bps": {
                    "default": 300.0,
                    "description": "Short shock " "magnitude (bps).",
                    "type": "number",
                },
                "times": {"description": "Bucket midpoint times " "in years.", "type": "object"},
            },
            "required": ["net_cashflows", "times", "base_rates"],
            "type": "object",
        },
        "path": "/api/v1/alm/irrbb_standardised_framework",
        "summary": "Standardised IRRBB EVE measure: worst ΔEVE across the six shocks.",
        "tool_name": "irrbb_standardised_framework",
    },
    {
        "description": "Holding a high-quality liquid-asset buffer earns ``buffer_yield`` but is\n"
        "funded at ``funding_cost`` plus a ``liquidity_premium`` — usually a net\n"
        "drag. Adjusted NII = base + buffer·(yield − funding − premium).",
        "domain": "alm",
        "function_name": "liquidity_adjusted_nii",
        "input_schema": {
            "properties": {
                "base_nii": {
                    "description": "Baseline net " "interest income " "(currency).",
                    "type": "number",
                },
                "buffer_yield": {
                    "description": "Yield on the " "buffer " "(decimal).",
                    "type": "number",
                },
                "funding_cost": {
                    "description": "Funding cost of " "the buffer " "(decimal).",
                    "type": "number",
                },
                "liquidity_buffer": {
                    "description": "Size of the " "liquidity " "buffer " "(currency).",
                    "type": "number",
                },
                "liquidity_premium": {
                    "description": "Additional " "liquidity " "premium " "charged " "(decimal).",
                    "type": "number",
                },
            },
            "required": [
                "base_nii",
                "liquidity_buffer",
                "buffer_yield",
                "funding_cost",
                "liquidity_premium",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/liquidity_adjusted_nii",
        "summary": "Liquidity-adjusted NII: base NII net of the liquidity-buffer carry cost.",
        "tool_name": "liquidity_adjusted_nii",
    },
    {
        "description": "``CPR = 1 − (1 − SMM)^12`` and ``SMM = 1 − (1 − CPR)^{1/12}``. Provide "
        "exactly\n"
        "one of the two.",
        "domain": "alm",
        "function_name": "loan_prepayment_rate_cpr",
        "input_schema": {
            "properties": {
                "cpr": {
                    "description": "Constant prepayment rate "
                    "(decimal), if converting "
                    "CPR→SMM.",
                    "type": "object",
                },
                "smm": {
                    "description": "Single monthly mortality "
                    "(decimal), if converting "
                    "SMM→CPR.",
                    "type": "object",
                },
            },
            "type": "object",
        },
        "path": "/api/v1/alm/loan_prepayment_rate_cpr",
        "summary": "Convert between single-monthly mortality (SMM) and CPR.",
        "tool_name": "loan_prepayment_rate_cpr",
    },
    {
        "description": "",
        "domain": "alm",
        "function_name": "macaulay_duration_balance_sheet",
        "input_schema": {
            "properties": {
                "cashflows": {"description": "Cashflow amounts.", "type": "object"},
                "discount_rate": {
                    "description": "Continuous " "discount rate " "(decimal).",
                    "type": "number",
                },
                "times": {"description": "Cashflow times in " "years.", "type": "object"},
            },
            "required": ["cashflows", "times", "discount_rate"],
            "type": "object",
        },
        "path": "/api/v1/alm/macaulay_duration_balance_sheet",
        "summary": "Macaulay duration of a balance-sheet cashflow stream (years).",
        "tool_name": "macaulay_duration_balance_sheet",
    },
    {
        "description": "``D_mod = D_mac / (1 + y/m)``; with continuous discounting (frequency "
        "large)\n"
        "modified ≈ Macaulay.",
        "domain": "alm",
        "function_name": "modified_duration_balance_sheet",
        "input_schema": {
            "properties": {
                "cashflows": {"description": "Cashflow amounts.", "type": "object"},
                "discount_rate": {"description": "Discount rate " "(decimal).", "type": "number"},
                "frequency": {
                    "default": 1,
                    "description": "Compounding " "frequency per year.",
                    "type": "integer",
                },
                "times": {"description": "Cashflow times in " "years.", "type": "object"},
            },
            "required": ["cashflows", "times", "discount_rate"],
            "type": "object",
        },
        "path": "/api/v1/alm/modified_duration_balance_sheet",
        "summary": "Modified duration of a balance-sheet position.",
        "tool_name": "modified_duration_balance_sheet",
    },
    {
        "description": "``ΔNII ≈ (RSA − RSL) · Δrate`` where ``RSA − RSL`` is the cumulative\n"
        "one-year repricing gap. A positive gap gains NII when rates rise.",
        "domain": "alm",
        "function_name": "nii_sensitivity_rate_shock",
        "input_schema": {
            "properties": {
                "rate_sensitive_assets": {
                    "description": "Assets " "repricing " "within " "the " "horizon " "(currency).",
                    "type": "number",
                },
                "rate_sensitive_liabilities": {
                    "description": "Liabilities " "repricing " "within " "the " "horizon.",
                    "type": "number",
                },
                "rate_shock": {
                    "description": "Parallel rate " "shock (decimal).",
                    "type": "number",
                },
            },
            "required": ["rate_sensitive_assets", "rate_sensitive_liabilities", "rate_shock"],
            "type": "object",
        },
        "path": "/api/v1/alm/nii_sensitivity_rate_shock",
        "summary": "Net interest income sensitivity to a parallel rate shock.",
        "tool_name": "nii_sensitivity_rate_shock",
    },
    {
        "description": "``NII = Σ A_i·r^A_i − Σ L_j·r^L_j`` over the projection horizon.",
        "domain": "alm",
        "function_name": "nii_simulation_baseline",
        "input_schema": {
            "properties": {
                "asset_balances": {
                    "description": "Balance per " "interest-earning " "asset bucket.",
                    "type": "object",
                },
                "asset_rates": {
                    "description": "Yield per asset " "bucket (decimal).",
                    "type": "object",
                },
                "liability_balances": {
                    "description": "Balance " "per " "interest-bearing " "liability " "bucket.",
                    "type": "object",
                },
                "liability_rates": {
                    "description": "Cost per " "liability " "bucket " "(decimal).",
                    "type": "object",
                },
            },
            "required": ["asset_balances", "asset_rates", "liability_balances", "liability_rates"],
            "type": "object",
        },
        "path": "/api/v1/alm/nii_simulation_baseline",
        "summary": "Baseline (current-rate) net-interest-income projection.",
        "tool_name": "nii_simulation_baseline",
    },
    {
        "description": "Asset and liability rates reprice by ``beta · shock`` (betas capture\n"
        "incomplete pass-through, especially on deposits). Returns the stressed "
        "NII\n"
        "and the change versus baseline.",
        "domain": "alm",
        "function_name": "nii_simulation_stress",
        "input_schema": {
            "properties": {
                "asset_balances": {
                    "description": "Balance per " "asset bucket " "(currency).",
                    "type": "object",
                },
                "asset_beta": {
                    "default": 1.0,
                    "description": "Asset repricing " "beta in [0, 1+].",
                    "type": "number",
                },
                "asset_rates": {
                    "description": "Base yield per " "asset bucket " "(decimal).",
                    "type": "object",
                },
                "liability_balances": {
                    "description": "Balance " "per " "liability " "bucket.",
                    "type": "object",
                },
                "liability_beta": {
                    "default": 0.5,
                    "description": "Liability " "(deposit) " "repricing beta " "in [0, 1+].",
                    "type": "number",
                },
                "liability_rates": {
                    "description": "Base cost per " "liability " "bucket " "(decimal).",
                    "type": "object",
                },
                "rate_shock": {
                    "description": "Parallel rate " "shock (decimal).",
                    "type": "number",
                },
            },
            "required": [
                "asset_balances",
                "asset_rates",
                "liability_balances",
                "liability_rates",
                "rate_shock",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/nii_simulation_stress",
        "summary": "Stressed NII under a parallel rate shock with repricing betas.",
        "tool_name": "nii_simulation_stress",
    },
    {
        "description": "Stable balance = the low percentile of the historical balance series (the\n"
        "level retained with ``confidence_level`` probability); the volatile "
        "portion\n"
        "is the remainder versus the current balance.",
        "domain": "alm",
        "function_name": "non_maturity_deposit_stability",
        "input_schema": {
            "properties": {
                "balance_history": {
                    "description": "Historical " "deposit " "balances (>= " "2 " "observations).",
                    "type": "object",
                },
                "confidence_level": {
                    "default": 0.99,
                    "description": "Confidence " "for the " "stable floor " "in [0.5, 1).",
                    "type": "number",
                },
            },
            "required": ["balance_history"],
            "type": "object",
        },
        "path": "/api/v1/alm/non_maturity_deposit_stability",
        "summary": "Estimate the stable (core) portion of NMDs from a balance history.",
        "tool_name": "non_maturity_deposit_stability",
    },
    {
        "description": "[REGULATORY] BCBS d368 distinguishes automatic options (caps/floors,\n"
        "prepayment options exercised optimally) from behavioural options (early\n"
        "redemption, deposit withdrawal). Total option risk = sum of both.",
        "domain": "alm",
        "function_name": "option_risk_irrbb",
        "input_schema": {
            "properties": {
                "automatic_option_value": {
                    "description": "PV of " "automatic " "interest-rate " "options.",
                    "type": "number",
                },
                "behavioural_option_value": {
                    "description": "PV " "of " "behavioural " "options.",
                    "type": "number",
                },
                "notional": {
                    "description": "Reference notional " "for the option-risk " "ratio.",
                    "type": "number",
                },
            },
            "required": ["automatic_option_value", "behavioural_option_value", "notional"],
            "type": "object",
        },
        "path": "/api/v1/alm/option_risk_irrbb",
        "summary": "Option risk: value of automatic and behavioural embedded options.",
        "tool_name": "option_risk_irrbb",
    },
    {
        "description": "Note: ``rate_risk`` is a heuristic √time-scaled volatility exposure\n"
        "proxy, not a rigorous option-pricing valuation of the rate-lock\n"
        "optionality.\n"
        "\n"
        "Exposure = ``notional · pull_through``; the rate risk scales with the\n"
        "rate-lock period and rate volatility (a √time vol exposure proxy).",
        "domain": "alm",
        "function_name": "pipeline_risk_measurement",
        "input_schema": {
            "properties": {
                "pipeline_notional": {
                    "description": "Committed " "pipeline " "notional.",
                    "type": "number",
                },
                "pull_through_rate": {
                    "description": "Expected " "fraction " "that " "completes " "in [0, 1].",
                    "type": "number",
                },
                "rate_lock_period": {
                    "description": "Rate-lock " "horizon in " "years.",
                    "type": "number",
                },
                "rate_volatility": {
                    "description": "Annualised " "rate " "volatility " "(decimal).",
                    "type": "number",
                },
            },
            "required": [
                "pipeline_notional",
                "pull_through_rate",
                "rate_lock_period",
                "rate_volatility",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/pipeline_risk_measurement",
        "summary": "Pipeline risk of rate-locked mortgage commitments not yet on balance.",
        "tool_name": "pipeline_risk_measurement",
    },
    {
        "description": "Note: cashflows come from a month-by-month recursive amortisation loop\n"
        "(interest, then scheduled principal, then prepayment on the remaining\n"
        "balance each month), not a single closed-form cashflow expression.\n"
        "\n"
        "Higher CPR shortens the weighted-average life (WAL) of the pool.",
        "domain": "alm",
        "function_name": "prepayment_model_mortgages",
        "input_schema": {
            "properties": {
                "annual_rate": {
                    "description": "Annual mortgage " "coupon (decimal).",
                    "type": "number",
                },
                "cpr": {"description": "Constant prepayment rate " "(decimal).", "type": "number"},
                "principal": {"description": "Initial pool " "balance.", "type": "number"},
                "term_years": {"description": "Original term in " "years.", "type": "integer"},
            },
            "required": ["principal", "annual_rate", "term_years", "cpr"],
            "type": "object",
        },
        "path": "/api/v1/alm/prepayment_model_mortgages",
        "summary": "Project mortgage cashflows under a constant CPR prepayment assumption.",
        "tool_name": "prepayment_model_mortgages",
    },
    {
        "description": "``gap_i = RSA_i − RSL_i``; the cumulative gap drives NII sensitivity.",
        "domain": "alm",
        "function_name": "repricing_gap_analysis",
        "input_schema": {
            "properties": {
                "bucket_assets": {
                    "description": "Rate-sensitive " "assets " "repricing in " "each bucket.",
                    "type": "object",
                },
                "bucket_labels": {"description": "Optional bucket " "names.", "type": "object"},
                "bucket_liabilities": {
                    "description": "Rate-sensitive "
                    "liabilities "
                    "repricing "
                    "in each "
                    "bucket.",
                    "type": "object",
                },
            },
            "required": ["bucket_assets", "bucket_liabilities"],
            "type": "object",
        },
        "path": "/api/v1/alm/repricing_gap_analysis",
        "summary": "Repricing gap per time bucket and the cumulative gap.",
        "tool_name": "repricing_gap_analysis",
    },
    {
        "description": "Note: bucket allocation is a discrete binning operation (``np.digitize``\n"
        "against ``bucket_edges``), not a closed-form sum in the usual sense.",
        "domain": "alm",
        "function_name": "repricing_maturity_profile",
        "input_schema": {
            "properties": {
                "balances": {"description": "Balance per " "instrument.", "type": "object"},
                "bucket_edges": {
                    "description": "Length " "``n_buckets+1`` " "ascending bucket " "boundaries.",
                    "type": "object",
                },
                "n_buckets": {"description": "Number of buckets.", "type": "integer"},
                "repricing_times": {
                    "description": "Next " "repricing " "time per " "instrument " "(years).",
                    "type": "object",
                },
            },
            "required": ["balances", "repricing_times", "n_buckets", "bucket_edges"],
            "type": "object",
        },
        "path": "/api/v1/alm/repricing_maturity_profile",
        "summary": "Allocate balances into repricing-time buckets.",
        "tool_name": "repricing_maturity_profile",
    },
    {
        "description": "",
        "domain": "alm",
        "function_name": "static_gap_analysis",
        "input_schema": {
            "properties": {
                "bucket_assets": {
                    "description": "Rate-sensitive " "assets per " "bucket.",
                    "type": "object",
                },
                "bucket_liabilities": {
                    "description": "Rate-sensitive " "liabilities " "per " "bucket.",
                    "type": "object",
                },
            },
            "required": ["bucket_assets", "bucket_liabilities"],
            "type": "object",
        },
        "path": "/api/v1/alm/static_gap_analysis",
        "summary": "Static (point-in-time) repricing gap assuming a frozen balance sheet.",
        "tool_name": "static_gap_analysis",
    },
    {
        "description": "Note: hedge notionals are solved numerically via SciPy bounded\n"
        "least-squares (``scipy.optimize.lsq_linear``), not a closed-form\n"
        "allocation formula.\n"
        "\n"
        "Solves for non-negative hedge notionals (bounded by per-instrument caps)\n"
        "that bring the dollar-duration of the hedge as close as possible to the\n"
        "target ``equity_notional · target_duration``.",
        "domain": "alm",
        "function_name": "structural_hedge_optimisation",
        "input_schema": {
            "properties": {
                "equity_notional": {
                    "description": "Equity " "notional to " "hedge " "(currency).",
                    "type": "number",
                },
                "instrument_durations": {
                    "description": "Duration " "of each " "hedge " "instrument " "(years).",
                    "type": "object",
                },
                "instrument_max_notional": {
                    "description": "Max " "notional " "per " "instrument " "(currency).",
                    "type": "object",
                },
                "target_duration": {
                    "description": "Desired " "equity " "duration " "(years).",
                    "type": "number",
                },
            },
            "required": [
                "target_duration",
                "instrument_durations",
                "instrument_max_notional",
                "equity_notional",
            ],
            "type": "object",
        },
        "path": "/api/v1/alm/structural_hedge_optimisation",
        "summary": "Optimise a structural hedge to a target equity duration.",
        "tool_name": "structural_hedge_optimisation",
    },
]

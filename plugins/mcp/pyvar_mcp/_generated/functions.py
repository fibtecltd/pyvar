"""plugins/mcp/pyvar_mcp/_generated/functions.py — GENERATED, do not edit by hand.

Regenerate with: python3 scripts/generate_mcp_tools.py (from the repo root)
Source: portal/functions.json -- see scripts/generate_mcp_tools.py for the mapping.
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
                "base_rates": {"type": "object"},
                "net_cashflows": {"type": "object"},
                "parallel_bps": {"default": 200.0, "type": "number"},
                "tier1_capital": {"type": "number"},
                "times": {"type": "object"},
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
                "asset_amounts": {"type": "object"},
                "asset_durations": {"type": "object"},
                "liability_amounts": {"type": "object"},
                "liability_durations": {"type": "object"},
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
                "asset_growth_rate": {"type": "number"},
                "asset_yield": {"type": "number"},
                "initial_assets": {"type": "number"},
                "initial_liabilities": {"type": "number"},
                "liability_cost": {"type": "number"},
                "liability_growth_rate": {"type": "number"},
                "n_years": {"type": "integer"},
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
                "asset_balances": {"type": "object"},
                "asset_index_shifts": {"type": "object"},
                "liability_balances": {"type": "object"},
                "liability_index_shifts": {"type": "object"},
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
                "core_fraction": {"type": "number"},
                "core_runoff_rate": {"type": "number"},
                "horizon_years": {"default": 5.0, "type": "number"},
                "non_core_runoff_rate": {"type": "number"},
                "total_balance": {"type": "number"},
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
                "asset_convexity": {"type": "number"},
                "liability_convexity": {"type": "number"},
                "total_assets": {"type": "number"},
                "total_liabilities": {"type": "number"},
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
                "core_balance": {"type": "number"},
                "decay_rate": {"type": "number"},
                "discount_rate": {"type": "number"},
                "max_years": {"default": 30.0, "type": "number"},
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
                "asset_duration": {"type": "number"},
                "liability_duration": {"type": "number"},
                "rate_shock": {"default": 0.01, "type": "number"},
                "total_assets": {"type": "number"},
                "total_liabilities": {"type": "number"},
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
                "asset_growth": {"type": "object"},
                "bucket_assets": {"type": "object"},
                "bucket_liabilities": {"type": "object"},
                "liability_growth": {"type": "object"},
                "n_periods": {"type": "integer"},
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
                "asset_cashflows": {"type": "object"},
                "asset_rates": {"type": "object"},
                "asset_times": {"type": "object"},
                "liability_cashflows": {"type": "object"},
                "liability_rates": {"type": "object"},
                "liability_times": {"type": "object"},
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
                "pv_base": {"type": "number"},
                "pv_down": {"type": "number"},
                "pv_up": {"type": "number"},
                "rate_shock": {"type": "number"},
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
                "base_rates": {"type": "object"},
                "long_bps": {"default": 150.0, "type": "number"},
                "net_cashflows": {"type": "object"},
                "parallel_bps": {"default": 200.0, "type": "number"},
                "short_bps": {"default": 300.0, "type": "number"},
                "times": {"type": "object"},
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
                "base_curve": {"type": "object"},
                "liquidity_spreads": {"type": "object"},
                "tenors": {"type": "object"},
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
                "customer_rate": {"type": "number"},
                "ftp_rate": {"type": "number"},
                "is_asset": {"default": True, "type": "boolean"},
                "liquidity_premium": {"default": 0.0, "type": "number"},
                "notional": {"type": "number"},
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
                "outlier_threshold": {"default": 0.15, "type": "number"},
                "tier1_capital": {"type": "number"},
                "worst_delta_eve": {"type": "number"},
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
                "base_rates": {"type": "object"},
                "net_cashflows": {"type": "object"},
                "rate_scenarios": {"type": "object"},
                "times": {"type": "object"},
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
                "long_bps": {"default": 150.0, "type": "number"},
                "parallel_bps": {"default": 200.0, "type": "number"},
                "short_bps": {"default": 300.0, "type": "number"},
                "tenors": {"type": "object"},
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
                "base_rates": {"type": "object"},
                "long_bps": {"default": 150.0, "type": "number"},
                "net_cashflows": {"type": "object"},
                "parallel_bps": {"default": 200.0, "type": "number"},
                "short_bps": {"default": 300.0, "type": "number"},
                "times": {"type": "object"},
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
                "base_nii": {"type": "number"},
                "buffer_yield": {"type": "number"},
                "funding_cost": {"type": "number"},
                "liquidity_buffer": {"type": "number"},
                "liquidity_premium": {"type": "number"},
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
            "properties": {"cpr": {"type": "object"}, "smm": {"type": "object"}},
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
                "cashflows": {"type": "object"},
                "discount_rate": {"type": "number"},
                "times": {"type": "object"},
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
                "cashflows": {"type": "object"},
                "discount_rate": {"type": "number"},
                "frequency": {"default": 1, "type": "integer"},
                "times": {"type": "object"},
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
                "rate_sensitive_assets": {"type": "number"},
                "rate_sensitive_liabilities": {"type": "number"},
                "rate_shock": {"type": "number"},
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
                "asset_balances": {"type": "object"},
                "asset_rates": {"type": "object"},
                "liability_balances": {"type": "object"},
                "liability_rates": {"type": "object"},
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
                "asset_balances": {"type": "object"},
                "asset_beta": {"default": 1.0, "type": "number"},
                "asset_rates": {"type": "object"},
                "liability_balances": {"type": "object"},
                "liability_beta": {"default": 0.5, "type": "number"},
                "liability_rates": {"type": "object"},
                "rate_shock": {"type": "number"},
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
                "balance_history": {"type": "object"},
                "confidence_level": {"default": 0.99, "type": "number"},
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
                "automatic_option_value": {"type": "number"},
                "behavioural_option_value": {"type": "number"},
                "notional": {"type": "number"},
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
                "pipeline_notional": {"type": "number"},
                "pull_through_rate": {"type": "number"},
                "rate_lock_period": {"type": "number"},
                "rate_volatility": {"type": "number"},
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
                "annual_rate": {"type": "number"},
                "cpr": {"type": "number"},
                "principal": {"type": "number"},
                "term_years": {"type": "integer"},
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
                "bucket_assets": {"type": "object"},
                "bucket_labels": {"type": "object"},
                "bucket_liabilities": {"type": "object"},
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
                "balances": {"type": "object"},
                "bucket_edges": {"type": "object"},
                "n_buckets": {"type": "integer"},
                "repricing_times": {"type": "object"},
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
                "bucket_assets": {"type": "object"},
                "bucket_liabilities": {"type": "object"},
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
                "equity_notional": {"type": "number"},
                "instrument_durations": {"type": "object"},
                "instrument_max_notional": {"type": "object"},
                "target_duration": {"type": "number"},
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
                "ebit": {"type": "number"},
                "market_value_equity": {"type": "number"},
                "retained_earnings": {"type": "number"},
                "sales": {"type": "number"},
                "total_assets": {"type": "number"},
                "total_liabilities": {"type": "number"},
                "working_capital": {"type": "number"},
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
                "credit_risk_mitigation": {"default": 0.0, "type": "number"},
                "ead": {"type": "number"},
                "risk_weight": {"type": "number"},
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
                "capital_profile": {"type": "object"},
                "cost_of_capital": {"default": 0.1, "type": "number"},
                "discount_factors": {"type": "object"},
                "time_steps": {"type": "object"},
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
                "accrual_factors": {"type": "object"},
                "contract_spread": {"type": "number"},
                "discount_factors": {"type": "object"},
                "hazard_rate": {"type": "number"},
                "notional": {"default": 1.0, "type": "number"},
                "payment_times": {"type": "object"},
                "recovery_rate": {"default": 0.4, "type": "number"},
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
                "cds_spread": {"type": "number"},
                "maturity": {"type": "number"},
                "recovery_rate": {"default": 0.4, "type": "number"},
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
                "collateral_value": {"type": "number"},
                "haircut_collateral": {"type": "number"},
                "haircut_fx": {"default": 0.0, "type": "number"},
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
                "factor_scores": {"type": "object"},
                "factor_weights": {"type": "object"},
                "pd_anchor": {"default": 0.5, "type": "number"},
                "pd_floor": {"default": 0.0003, "type": "number"},
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
                "add_on": {"type": "number"},
                "collateral": {"default": 0.0, "type": "number"},
                "mark_to_market": {"type": "number"},
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
            "properties": {"exposures": {"type": "object"}},
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
                "confidence_level": {"default": 0.99, "type": "number"},
                "horizon_days": {"default": 1, "type": "integer"},
                "notional": {"type": "number"},
                "position": {"default": "long_protection", "type": "string"},
                "risky_annuity": {"type": "number"},
                "spread_volatility": {"type": "number"},
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
                "expected_losses": {"type": "object"},
                "expected_returns": {"type": "object"},
                "max_weight": {"default": 1.0, "type": "number"},
                "risk_aversion": {"default": 1.0, "type": "number"},
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
                "par_spreads": {"type": "object"},
                "recovery_rate": {"default": 0.4, "type": "number"},
                "tenors": {"type": "object"},
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
                "ead": {"type": "object"},
                "lgd": {"type": "object"},
                "lgd_shock_multiplier": {"default": 1.2, "type": "number"},
                "pd": {"type": "object"},
                "pd_shock_multiplier": {"default": 1.5, "type": "number"},
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
                "credit_spread": {"type": "number"},
                "discount_factors": {"type": "object"},
                "expected_exposure": {"type": "object"},
                "recovery_rate": {"default": 0.4, "type": "number"},
                "time_steps": {"type": "object"},
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
                "asset_correlation": {"default": 0.15, "type": "number"},
                "confidence_level": {"default": 0.999, "type": "number"},
                "ead_total": {"type": "number"},
                "lgd": {"type": "number"},
                "pd": {"type": "number"},
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
                "asset_correlation": {"default": 0.15, "type": "object"},
                "confidence_level": {"default": 0.999, "type": "number"},
                "ead": {"type": "object"},
                "lgd": {"type": "object"},
                "n_simulations": {"default": 50000, "type": "integer"},
                "pd": {"type": "object"},
                "seed": {"default": 12345, "type": "integer"},
            },
            "required": ["pd", "lgd", "ead"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/credit_var_monte_carlo",
        "summary": "Monte-Carlo Credit VaR under a one-factor Gaussian copula.",
        "tool_name": "credit_var_monte_carlo",
    },
    {
        "description": "A default/no-default reduction of J.P. Morgan's CreditMetrics: latent "
        "asset\n"
        "returns are driven by a single common factor; an obligor defaults when "
        "its\n"
        "return breaches ``N^{-1}(PD)``, incurring ``LGD * exposure``. The full "
        "model\n"
        "uses a multi-state rating-migration matrix — handled separately by\n"
        ":func:`engine.credit_scoring.ratings_migration_matrix` — but the loss tail "
        "is\n"
        "dominated by the default state captured here.\n"
        "\n"
        "In implementation this is a direct pass-through to the same one-factor\n"
        "Gaussian-copula Monte Carlo engine used by\n"
        ":func:`credit_var_monte_carlo` (identical formula, identical code path),\n"
        "not a separately coded multi-state model.",
        "domain": "credit-risk",
        "function_name": "creditmetrics_portfolio_model",
        "input_schema": {
            "properties": {
                "asset_correlation": {"default": 0.2, "type": "number"},
                "confidence_level": {"default": 0.99, "type": "number"},
                "exposures": {"type": "object"},
                "lgd": {"type": "object"},
                "n_simulations": {"default": 20000, "type": "integer"},
                "pd": {"type": "object"},
                "seed": {"default": 2024, "type": "integer"},
            },
            "required": ["exposures", "pd", "lgd"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/creditmetrics_portfolio_model",
        "summary": "Simplified CreditMetrics (two-state) portfolio loss distribution.",
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
                "add_on_factor": {"type": "number"},
                "mark_to_market": {"type": "number"},
                "notional": {"type": "number"},
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
                "credit_spread": {"type": "number"},
                "discount_factors": {"type": "object"},
                "expected_exposure": {"type": "object"},
                "recovery_rate": {"default": 0.4, "type": "number"},
                "spread_bump": {"default": 0.0001, "type": "number"},
                "time_steps": {"type": "object"},
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
                "discount_factors": {"type": "object"},
                "expected_negative_exposure": {"type": "object"},
                "own_credit_spread": {"type": "number"},
                "own_recovery_rate": {"default": 0.4, "type": "number"},
                "time_steps": {"type": "object"},
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
            "properties": {"asset_correlation": {"type": "object"}, "pd": {"type": "object"}},
            "required": ["pd", "asset_correlation"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/default_correlation_matrix",
        "summary": "Pairwise default correlation from asset correlations (Gaussian copula).",
        "tool_name": "default_correlation_matrix",
    },
    {
        "description": "Note: uses a multiplicative downturn scaling, a deliberate departure from\n"
        "EBA/GL/2019/03's additive fallback approach — see CRR Art. 181 for the\n"
        "underlying requirement.\n"
        "\n"
        "CRR Art. 181 requires LGD to reflect economic-downturn conditions when "
        "these\n"
        "are more conservative than the long-run average. The supervisory-style\n"
        "additive add-on (EBA GL) is applied as\n"
        "``LGD_downturn = LGD_LR + max(0, multiplier - 1) * (1 - LGD_LR) * 0.5`` "
        "is\n"
        "*not* used here; instead a transparent multiplicative scaling is applied "
        "and\n"
        "clipped to ``[floor, 1]`` so the result never under-states the long-run "
        "LGD.",
        "domain": "credit-risk",
        "function_name": "downturn_lgd_adjustment",
        "input_schema": {
            "properties": {
                "downturn_multiplier": {"default": 1.0, "type": "number"},
                "floor": {"default": 0.0, "type": "number"},
                "lgd_long_run": {"type": "number"},
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
                "expected_exposure": {"type": "object"},
                "time_steps": {"type": "object"},
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
                "ead": {"type": "number"},
                "lgd": {"type": "number"},
                "pd": {"type": "number"},
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
                "expected_exposure": {"type": "object"},
                "time_steps": {"type": "object"},
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
                "credit_conversion_factor": {"default": 0.75, "type": "number"},
                "drawn": {"type": "number"},
                "undrawn": {"type": "number"},
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
                "discount_factors": {"type": "object"},
                "expected_exposure": {"type": "object"},
                "funding_spread": {"type": "number"},
                "survival_probability": {"type": "object"},
                "time_steps": {"type": "object"},
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
                "discount_factor": {"default": 1.0, "type": "number"},
                "ead": {"type": "number"},
                "lgd": {"type": "number"},
                "pd_12m": {"type": "number"},
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
                "discount_factors": {"type": "object"},
                "ead": {"type": "object"},
                "lgd": {"type": "object"},
                "marginal_pd": {"type": "object"},
                "stage": {"default": 2, "type": "integer"},
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
                "scenario_ecls": {"type": "object"},
                "scenario_weights": {"type": "object"},
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
                "days_past_due": {"default": 0, "type": "integer"},
                "pd_current": {"type": "number"},
                "pd_origination": {"type": "number"},
                "sicr_absolute_threshold": {"default": 0.02, "type": "number"},
                "sicr_relative_threshold": {"default": 2.0, "type": "number"},
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
                "days_past_due": {"default": 0, "type": "integer"},
                "forbearance": {"default": False, "type": "boolean"},
                "pd_current": {"type": "number"},
                "pd_origination": {"type": "number"},
                "sicr_relative_threshold": {"default": 2.0, "type": "number"},
                "watchlist": {"default": False, "type": "boolean"},
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
                "correlation": {"type": "object"},
                "ead": {"type": "number"},
                "lgd": {"type": "number"},
                "maturity": {"default": 2.5, "type": "number"},
                "pd": {"type": "number"},
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
                "ead": {"type": "number"},
                "lgd": {"default": 0.45, "type": "number"},
                "maturity": {"default": 2.5, "type": "number"},
                "pd": {"type": "number"},
                "seniority": {"default": "senior_unsecured", "type": "string"},
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
                "asset_drift": {"type": "object"},
                "asset_value": {"type": "number"},
                "asset_volatility": {"type": "number"},
                "debt_face_value": {"type": "number"},
                "horizon": {"default": 1.0, "type": "number"},
                "risk_free_rate": {"default": 0.0, "type": "number"},
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
                "defaults": {"type": "object"},
                "features": {"type": "object"},
                "max_iter": {"default": 100, "type": "integer"},
                "ridge": {"default": 1e-06, "type": "number"},
                "tol": {"default": 1e-08, "type": "number"},
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
                "exposure_amounts": {"type": "object"},
                "recovery_amounts": {"type": "object"},
                "workout_cost_rate": {"default": 0.0, "type": "number"},
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
                "defaults": {"type": "object"},
                "max_iter": {"default": 100, "type": "integer"},
                "raw_scores": {"type": "object"},
                "tol": {"default": 1e-08, "type": "number"},
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
                "base_ecl": {"type": "number"},
                "macro_factors": {"type": "object"},
                "management_overlay": {"default": 0.0, "type": "number"},
                "sensitivities": {"type": "object"},
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
                "discount_factors": {"type": "object"},
                "initial_margin_profile": {"type": "object"},
                "margin_funding_spread": {"type": "number"},
                "time_steps": {"type": "object"},
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
            "properties": {"maturity": {"type": "number"}, "pd": {"type": "number"}},
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
                "macro_index": {"type": "number"},
                "sensitivity": {"default": 1.0, "type": "number"},
                "ttc_pd": {"type": "number"},
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
                "drift": {"default": 0.0, "type": "number"},
                "initial_value": {"type": "number"},
                "n_paths": {"default": 20000, "type": "integer"},
                "quantile": {"default": 0.95, "type": "number"},
                "seed": {"default": 909, "type": "integer"},
                "time_steps": {"type": "object"},
                "volatility": {"type": "number"},
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
                "floor": {"default": 0.0003, "type": "number"},
                "n_defaults": {"type": "object"},
                "n_obligors": {"type": "object"},
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
                "from_rating": {"type": "object"},
                "n_states": {"type": "integer"},
                "to_rating": {"type": "object"},
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
                "discount_factors": {"type": "object"},
                "exposure_amounts": {"type": "object"},
                "recovery_amounts": {"type": "object"},
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
                "base_odds": {"default": 50.0, "type": "number"},
                "base_points": {"type": "number"},
                "base_score": {"default": 600.0, "type": "number"},
                "feature_values": {"type": "object"},
                "pdo": {"default": 50.0, "type": "number"},
                "points_per_feature": {"type": "object"},
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
                "sector_defaults": {"type": "object"},
                "sector_names": {"type": "object"},
                "sector_obligors": {"type": "object"},
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
            "properties": {"annual_sales_millions": {"type": "number"}, "pd": {"type": "number"}},
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
                "current_account_pct": {"type": "number"},
                "debt_to_gdp": {"type": "number"},
                "fiscal_balance_pct": {"type": "number"},
                "fx_reserves_months": {"type": "number"},
                "governance_score": {"type": "number"},
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
                "add_on_aggregate": {"type": "number"},
                "alpha": {"default": 1.4, "type": "number"},
                "collateral": {"type": "number"},
                "mark_to_market": {"type": "number"},
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
                "cyclicality": {"default": 0.5, "type": "number"},
                "long_run_average_pd": {"type": "number"},
                "pit_pd": {"type": "number"},
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
                "ead": {"type": "object"},
                "lgd": {"type": "object"},
                "pd": {"type": "object"},
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
                "base_cva": {"type": "number"},
                "correlation": {"type": "number"},
                "exposure_volatility": {"default": 0.3, "type": "number"},
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
                "cva": {"type": "number"},
                "dva": {"default": 0.0, "type": "number"},
                "fva": {"default": 0.0, "type": "number"},
                "kva": {"default": 0.0, "type": "number"},
                "mva": {"default": 0.0, "type": "number"},
            },
            "required": ["cva"],
            "type": "object",
        },
        "path": "/api/v1/credit-risk/xva_aggregation",
        "summary": "Aggregate the XVA components into a total valuation adjustment.",
        "tool_name": "xva_aggregation",
    },
    {
        "description": "Allows early exercise at every time step. The price must be >= the "
        "European\n"
        "price of the same option.\n"
        "\n"
        "Note: the continuation value at each exercise date is fit by quadratic "
        "OLS\n"
        "regression on in-the-money paths rather than evaluated from a closed-form\n"
        "formula, and the opt-in Greeks use a spot bump roughly 30x larger than\n"
        "this module's smooth-payoff pricers because that regression-based\n"
        "exercise decision is discontinuous in spot.\n"
        "\n"
        "Deliberately has no qmc option (task #15 Phase 2 evaluated and rejected\n"
        "it for this function specifically -- see _price_by_qmc_replicates'\n"
        "docstring). Randomized-QMC replicates work cleanly for "
        "asian_option_pricer\n"
        "and lookback_option_pricer (simple path-average / path-extremum\n"
        "estimators) but introduce a real, non-vanishing pricing bias here: LSM's\n"
        "backward-induction step fits a cross-sectional OLS regression of\n"
        "continuation value against in-the-money paths at each exercise date, and\n"
        "that regression implicitly assumes the sampled points are independent.\n"
        "Scrambled Sobol paths are deliberately correlated (that correlation is\n"
        "exactly what gives QMC its variance reduction elsewhere), which biases\n"
        "the regression fit and, through it, the exercise decision. Measured at\n"
        "S=K=100, r=5%, sigma=20%, tau=1, n_steps=50 against a 200k-path plain-MC\n"
        "reference (~6.024): plain MC at n_simulations=6,000/20,000 is biased by\n"
        "only +0.03-0.04 (LSM's well-known small-sample low bias), while QMC\n"
        "replicates at the same total budget were biased by +0.08 to +0.31\n"
        "depending on replicate count/size -- shrinking as per-replicate path\n"
        "count grows into the thousands, but not vanishing by n_simulations=20k\n"
        "the way it does for Asian/lookback. Revisit only with a fix for the\n"
        "underlying regression-bias interaction (e.g. an in-sample/out-of-sample\n"
        "split for the regression fit), not by retuning replicate count alone.",
        "domain": "derivatives",
        "function_name": "american_option_lsm",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "n_steps": {"default": 50, "type": "integer"},
                "option_type": {"default": "put", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 41, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/american_option_lsm",
        "summary": "American option price via Longstaff-Schwartz Monte Carlo (LSM).",
        "tool_name": "american_option_lsm",
    },
    {
        "description": "The averaging reduces volatility, so an Asian option is worth less than "
        "the\n"
        "corresponding vanilla European option.",
        "domain": "derivatives",
        "function_name": "asian_option_pricer",
        "input_schema": {
            "properties": {
                "average_type": {"default": "arithmetic", "type": "string"},
                "div_yield": {"default": 0.0, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "n_steps": {"default": 100, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "qmc": {"default": False, "type": "boolean"},
                "rate": {"type": "number"},
                "seed": {"default": 21, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/asian_option_pricer",
        "summary": "Arithmetic-average Asian option price via Monte Carlo.",
        "tool_name": "asian_option_pricer",
    },
    {
        "description": "The spread equating the bond's net present value (relative to par) to an\n"
        "annuity of the swap's fixed-leg PV01:\n"
        "``ASW = (PV_bond − par) / annuity``, expressed in basis points.\n"
        "\n"
        "Note: ``bond_price`` is accepted for API-compatibility but does not\n"
        "affect the result — ``PV_bond`` in the formula above is derived\n"
        "internally by discounting ``cashflows``/``times`` at ``swap_rates``,\n"
        "not from the observed ``bond_price`` passed in.",
        "domain": "derivatives",
        "function_name": "asset_swap_spread",
        "input_schema": {
            "properties": {
                "bond_price": {"type": "number"},
                "cashflows": {"type": "object"},
                "face_value": {"default": 100.0, "type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "swap_rates": {"type": "object"},
                "times": {"type": "object"},
            },
            "required": ["bond_price", "cashflows", "times", "swap_rates"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/asset_swap_spread",
        "summary": "Par-par asset-swap spread.",
        "tool_name": "asset_swap_spread",
    },
    {
        "description": "modelled rebate leg.\n"
        "\n"
        "Uses the in-out parity ``knock-in + knock-out = vanilla`` for the *pure*\n"
        "(no-rebate) option legs, so any of the four standard combinations is\n"
        "supported. A nonzero ``rebate`` adds the standard Reiner-Rubinstein cash\n"
        "rebate term on top of that pure leg: for a knock-in, the rebate is paid\n"
        'at expiry if the barrier is never touched (the "E" term below); for a\n'
        "knock-out, the rebate is paid at the moment the barrier is touched (the\n"
        '"F" term below) -- the standard two rebate conventions (Haug, *The\n'
        'Complete Guide to Option Pricing Formulas*, "Standard Barrier Options").\n'
        "\n"
        "Note: only the general Reiner-Rubinstein building blocks (A/B/C/D) are\n"
        "shown here — which combination prices the knock-in leg depends on\n"
        "``option_type``, ``barrier_type``, and whether strike exceeds barrier.",
        "domain": "derivatives",
        "function_name": "barrier_option_pricer",
        "input_schema": {
            "properties": {
                "barrier": {"type": "number"},
                "barrier_type": {"default": "down-and-out", "type": "string"},
                "div_yield": {"default": 0.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "rebate": {"default": 0.0, "type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "barrier", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/barrier_option_pricer",
        "summary": "Single-barrier option price (Reiner-Rubinstein closed form), with a",
        "tool_name": "barrier_option_pricer",
    },
    {
        "description": "Diversification means the basket option is worth no more than the "
        "weighted\n"
        "sum of single-asset options.",
        "domain": "derivatives",
        "function_name": "basket_option_pricer",
        "input_schema": {
            "properties": {
                "correlation": {"type": "object"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 71, "type": "integer"},
                "sigmas": {"type": "object"},
                "spots": {"type": "object"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
                "weights": {"type": "object"},
            },
            "required": ["spots", "weights", "strike", "rate", "sigmas", "tau", "correlation"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/basket_option_pricer",
        "summary": "Basket option price via Monte Carlo on a weighted sum of assets.",
        "tool_name": "basket_option_pricer",
    },
    {
        "description": "Early exercise is allowed only on an evenly-spaced subset of the time "
        "grid.\n"
        "Price lies between the European and American values.\n"
        "\n"
        "Note: uses the same Longstaff-Schwartz regression-based exercise decision\n"
        "as ``american_option_lsm`` (no closed form), restricted to an\n"
        "evenly-spaced subset of roughly ``n_steps / exercise_dates`` grid points.",
        "domain": "derivatives",
        "function_name": "bermudan_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "exercise_dates": {"default": 4, "type": "integer"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "n_steps": {"default": 48, "type": "integer"},
                "option_type": {"default": "put", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 51, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/bermudan_option_pricer",
        "summary": "Bermudan option price via LSM with discrete exercise dates.",
        "tool_name": "bermudan_option_pricer",
    },
    {
        "description": "Handles European and American exercise. European prices converge to\n"
        "Black-Scholes as ``n_steps`` grows.",
        "domain": "derivatives",
        "function_name": "binomial_tree_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "n_steps": {"default": 500, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "style": {"default": "european", "type": "string"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/binomial_tree_option_pricer",
        "summary": "Cox-Ross-Rubinstein binomial tree option price.",
        "tool_name": "binomial_tree_option_pricer",
    },
    {
        "description": "``Call = S e^{-qτ} N(d1) − K e^{-rτ} N(d2)``; the put follows by parity.\n"
        "When ``tau == 0`` the intrinsic value is returned (zero-time limit) and "
        "when\n"
        "``sigma == 0`` the discounted-forward intrinsic value is returned.",
        "domain": "derivatives",
        "function_name": "black_scholes_european_option",
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
        "path": "/api/v1/derivatives/black_scholes_european_option",
        "summary": "Black-Scholes-Merton price of a European option.",
        "tool_name": "black_scholes_european_option",
    },
    {
        "description": "Returns delta, gamma, vega, theta (per year) and rho. Gamma and vega are\n"
        "identical for calls and puts.",
        "domain": "derivatives",
        "function_name": "black_scholes_greeks",
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
        "path": "/api/v1/derivatives/black_scholes_greeks",
        "summary": "Closed-form Black-Scholes first-order Greeks.",
        "tool_name": "black_scholes_greeks",
    },
    {
        "description": "Price falls as yield rises (inverse relationship), and equals par when "
        "the\n"
        "coupon rate equals the yield.",
        "domain": "derivatives",
        "function_name": "bond_pricer_fixed_coupon",
        "input_schema": {
            "properties": {
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "maturity": {"type": "number"},
                "yield_rate": {"type": "number"},
            },
            "required": ["face_value", "coupon_rate", "yield_rate", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/bond_pricer_fixed_coupon",
        "summary": "Price a fixed-coupon bond by discounting its cashflows at a flat yield.",
        "tool_name": "bond_pricer_fixed_coupon",
    },
    {
        "description": "Each coupon is ``(reference_rate + spread) / frequency · face``. On a "
        "reset\n"
        "date with discount rates equal to the reference rates, an FRN prices near\n"
        "par plus the PV of the spread.\n"
        "\n"
        "Note: the number of coupon periods actually priced is\n"
        "``len(reference_rates)`` (and ``discount_rates`` must match that length).\n"
        "``maturity`` is only used for input validation (``maturity > 0``) here —\n"
        "it does not determine the coupon schedule, so a caller-supplied\n"
        "``maturity`` inconsistent with ``len(reference_rates) / frequency`` is\n"
        "not detected or reconciled.",
        "domain": "derivatives",
        "function_name": "bond_pricer_floating_rate",
        "input_schema": {
            "properties": {
                "discount_rates": {"type": "object"},
                "face_value": {"type": "number"},
                "frequency": {"default": 4, "type": "integer"},
                "maturity": {"type": "number"},
                "reference_rates": {"type": "object"},
                "spread": {"type": "number"},
            },
            "required": ["face_value", "reference_rates", "spread", "discount_rates", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/bond_pricer_floating_rate",
        "summary": "Price a floating-rate note (FRN) from projected forward rates.",
        "tool_name": "bond_pricer_floating_rate",
    },
    {
        "description": "Sequentially solves for each discount factor so each par bond prices to "
        "par,\n"
        "then converts discount factors to continuously-compounded zero rates.",
        "domain": "derivatives",
        "function_name": "bootstrap_yield_curve",
        "input_schema": {
            "properties": {
                "face_value": {"default": 1.0, "type": "number"},
                "frequency": {"default": 1, "type": "integer"},
                "maturities": {"type": "object"},
                "par_rates": {"type": "object"},
            },
            "required": ["par_rates", "maturities"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/bootstrap_yield_curve",
        "summary": "Bootstrap zero (spot) rates from par-coupon bond rates.",
        "tool_name": "bootstrap_yield_curve",
    },
    {
        "description": "A callable bond is worth no more than the equivalent straight bond — the\n"
        "embedded call belongs to the issuer.\n"
        "\n"
        "Note: the short-rate tree is a simplified multiplicative lattice with\n"
        "fixed 0.5/0.5 branch probabilities, not a Black-Derman-Toy tree "
        "calibrated\n"
        "to an initial term structure, and the coupon is added at every node on\n"
        "every step.",
        "domain": "derivatives",
        "function_name": "callable_bond_pricer",
        "input_schema": {
            "properties": {
                "call_price": {"type": "number"},
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 1, "type": "integer"},
                "maturity": {"type": "number"},
                "rate_vol": {"type": "number"},
                "short_rate": {"type": "number"},
            },
            "required": [
                "face_value",
                "coupon_rate",
                "short_rate",
                "rate_vol",
                "maturity",
                "call_price",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/callable_bond_pricer",
        "summary": "Price a callable bond (issuer's option) on a short-rate binomial tree.",
        "tool_name": "callable_bond_pricer",
    },
    {
        "description": "",
        "domain": "derivatives",
        "function_name": "cap_floor_pricer",
        "input_schema": {
            "properties": {
                "accruals": {"type": "object"},
                "discount_factors": {"type": "object"},
                "expiries": {"type": "object"},
                "forward_rates": {"type": "object"},
                "notional": {"type": "number"},
                "option_type": {"default": "cap", "type": "string"},
                "strike": {"type": "number"},
                "vols": {"type": "object"},
            },
            "required": [
                "notional",
                "forward_rates",
                "strike",
                "vols",
                "expiries",
                "accruals",
                "discount_factors",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/cap_floor_pricer",
        "summary": "Price an interest-rate cap/floor as a strip of caplets/floorlets.",
        "tool_name": "cap_floor_pricer",
    },
    {
        "description": "A caplet is a call on the forward rate; a floorlet is a put. Caplet +\n"
        "floorlet (same strike) replicate a payer FRA (put-call parity).",
        "domain": "derivatives",
        "function_name": "caplet_floorlet_pricer_black",
        "input_schema": {
            "properties": {
                "accrual": {"type": "number"},
                "discount_factor": {"type": "number"},
                "expiry": {"type": "number"},
                "forward_rate": {"type": "number"},
                "notional": {"type": "number"},
                "option_type": {"default": "caplet", "type": "string"},
                "strike": {"type": "number"},
                "vol": {"type": "number"},
            },
            "required": [
                "notional",
                "forward_rate",
                "strike",
                "vol",
                "expiry",
                "accrual",
                "discount_factor",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/caplet_floorlet_pricer_black",
        "summary": "Price a single caplet/floorlet under the Black (lognormal) model.",
        "tool_name": "caplet_floorlet_pricer_black",
    },
    {
        "description": "At ``tau_choose`` the holder picks call or put (same strike/expiry). By\n"
        "put-call parity the value is a call plus a put on a reduced-maturity\n"
        "underlying: ``C(S,K,T) + P(S, K e^{-r(T-t)}·..., t)``. Worth at least the\n"
        "more valuable of the embedded call and put.",
        "domain": "derivatives",
        "function_name": "chooser_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau_choose": {"type": "number"},
                "tau_expiry": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau_choose", "tau_expiry"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/chooser_option_pricer",
        "summary": "Simple chooser option price (closed form).",
        "tool_name": "chooser_option_pricer",
    },
    {
        "description": "Supports the four standard compound types (call/put on call/put). See\n"
        "``_geske_compound_price`` for the exact d-term algebra and its citation.",
        "domain": "derivatives",
        "function_name": "compound_option_pricer",
        "input_schema": {
            "properties": {
                "compound_type": {"default": "call-on-call", "type": "string"},
                "div_yield": {"default": 0.0, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 200000, "type": "integer"},
                "rate": {"type": "number"},
                "seed": {"default": 81, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike_compound": {"type": "number"},
                "strike_underlying": {"type": "number"},
                "tau_compound": {"type": "number"},
                "tau_underlying": {"type": "number"},
            },
            "required": [
                "spot",
                "strike_underlying",
                "strike_compound",
                "rate",
                "sigma",
                "tau_compound",
                "tau_underlying",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/compound_option_pricer",
        "summary": "Compound option (option-on-option) price via the Geske (1979) closed form.",
        "tool_name": "compound_option_pricer",
    },
    {
        "description": "Value = max(straight bond floor, conversion value), a simple but standard\n"
        "lower-bound decomposition. The convertible is always worth at least its\n"
        "conversion value and at least its bond floor.\n"
        "\n"
        "Note: this lower-bound decomposition does not model conversion\n"
        "optionality, equity volatility, or embedded call/put features of a real\n"
        "convertible bond.",
        "domain": "derivatives",
        "function_name": "convertible_bond_pricer",
        "input_schema": {
            "properties": {
                "conversion_ratio": {"type": "number"},
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "maturity": {"type": "number"},
                "stock_price": {"type": "number"},
                "yield_rate": {"type": "number"},
            },
            "required": [
                "face_value",
                "coupon_rate",
                "yield_rate",
                "maturity",
                "conversion_ratio",
                "stock_price",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/convertible_bond_pricer",
        "summary": "Price a convertible bond via the bond-floor + conversion-value maximum.",
        "tool_name": "convertible_bond_pricer",
    },
    {
        "description": "option-free bonds).\n"
        "\n"
        "``C = Σ cf_k · t_k(t_k + 1/m) · (1+y/m)^{-(m t_k + 2)} / P``.",
        "domain": "derivatives",
        "function_name": "convexity",
        "input_schema": {
            "properties": {
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "times": {"type": "object"},
                "yield_rate": {"type": "number"},
            },
            "required": ["cashflows", "times", "yield_rate"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/convexity",
        "summary": "Bond convexity — the second-order yield sensitivity (always >= 0 for",
        "tool_name": "convexity",
    },
    {
        "description": "``dr = κ(θ−r)dt + σ√r dW``. The square-root diffusion keeps ``r >= 0``. "
        "The\n"
        "Feller condition ``2κθ ≥ σ²`` guarantees strict positivity.\n"
        "\n"
        "The Monte Carlo path uses the exact non-central chi-squared CIR\n"
        "transition distribution (Broadie-Kaya / Glasserman §3.4;\n"
        "``_cir_paths_exact_terminal``), not an Euler discretisation -- there is\n"
        "no discretisation bias here at any ``n_steps``, unlike the (retained,\n"
        "non-production) full-truncation Euler scheme in ``_cir_paths_euler``.",
        "domain": "derivatives",
        "function_name": "cox_ingersoll_ross_model",
        "input_schema": {
            "properties": {
                "kappa": {"type": "number"},
                "maturity": {"type": "number"},
                "n_simulations": {"default": 50000, "type": "integer"},
                "n_steps": {"default": 100, "type": "integer"},
                "r0": {"type": "number"},
                "seed": {"default": 102, "type": "integer"},
                "sigma": {"type": "number"},
                "theta": {"type": "number"},
            },
            "required": ["r0", "kappa", "theta", "sigma", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/cox_ingersoll_ross_model",
        "summary": "CIR model: closed-form ZCB price + simulated (non-negative) short rate.",
        "tool_name": "cox_ingersoll_ross_model",
    },
    {
        "description": "accrual-midpoint default settlement.\n"
        "\n"
        "Survival ``Q(t)=e^{−λt}``. Default losses -- and the accrued premium a\n"
        "protection buyer owes if default falls inside a coupon period -- are\n"
        "both settled at each period's ACCRUAL MIDPOINT\n"
        "``t_mid,i = (t_{i−1}+t_i)/2``, discounted at ``DF(t_mid,i)``, following\n"
        "the standard ISDA/JPMorgan reduced-form CDS convention also implemented\n"
        "by QuantLib's ``MidPointCdsEngine`` (which settles the same way by\n"
        "default: ``settlesAccrual=True``, ``paysAtDefaultTime=True`` --\n"
        "confirmed by inspecting its NPV decomposition directly, since this is\n"
        "exactly what ``tests/validation/test_derivatives_ref.py`` cross-checks\n"
        "against). The regular coupon cashflow -- paid only while the name has\n"
        "survived to the period end -- is unaffected: ``spread · τ · Σ DF(t_i) ·\n"
        "Q(t_i)``.\n"
        "\n"
        "Protection leg = ``(1−R) · Σ DF(t_mid,i) · (Q_{i−1} − Q_i)``.\n"
        "Accrual-on-default rebate = ``spread · Σ (t_mid,i − t_{i−1}) ·\n"
        "DF(t_mid,i) · (Q_{i−1} − Q_i)``, added to the premium leg. The par\n"
        "spread zeroes the swap value.",
        "domain": "derivatives",
        "function_name": "credit_default_swap_cds_pricer",
        "input_schema": {
            "properties": {
                "discount_rate": {"type": "number"},
                "frequency": {"default": 4, "type": "integer"},
                "hazard_rate": {"type": "number"},
                "maturity": {"type": "number"},
                "notional": {"type": "number"},
                "recovery_rate": {"type": "number"},
                "spread": {"type": "number"},
            },
            "required": [
                "notional",
                "spread",
                "hazard_rate",
                "recovery_rate",
                "maturity",
                "discount_rate",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/credit_default_swap_cds_pricer",
        "summary": "Price a CDS via a flat-hazard-rate reduced-form model with",
        "tool_name": "credit_default_swap_cds_pricer",
    },
    {
        "description": "Values each leg in its own currency (coupons + final notional), converts "
        "the\n"
        "foreign leg at the FX spot, and nets. Pay-domestic = pay the domestic "
        "leg,\n"
        "receive the foreign leg.",
        "domain": "derivatives",
        "function_name": "cross_currency_swap_pricer",
        "input_schema": {
            "properties": {
                "accruals": {"type": "object"},
                "df_dom": {"type": "object"},
                "df_for": {"type": "object"},
                "fixed_rate_dom": {"type": "number"},
                "fixed_rate_for": {"type": "number"},
                "fx_spot": {"type": "number"},
                "notional_dom": {"type": "number"},
                "notional_for": {"type": "number"},
                "pay_domestic": {"default": True, "type": "boolean"},
            },
            "required": [
                "notional_dom",
                "notional_for",
                "fixed_rate_dom",
                "fixed_rate_for",
                "df_dom",
                "df_for",
                "accruals",
                "fx_spot",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/cross_currency_swap_pricer",
        "summary": "Price a fixed-fixed cross-currency swap (with notional exchange).",
        "tool_name": "cross_currency_swap_pricer",
    },
    {
        "description": "``Call = payout · e^{-rτ} N(d2)``, ``Put = payout · e^{-rτ} N(-d2)``.",
        "domain": "derivatives",
        "function_name": "digital_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "payout": {"default": 1.0, "type": "number"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/digital_option_pricer",
        "summary": "Cash-or-nothing digital (binary) option price.",
        "tool_name": "digital_option_pricer",
    },
    {
        "description": "Prices ``(S + a)`` as a lognormal with vol scaled by ``S/(S+a)`` — a "
        "simple\n"
        "way to interpolate between lognormal (a=0) and normal-like dynamics. "
        "Reduces\n"
        "exactly to Black-Scholes when ``displacement == 0``.",
        "domain": "derivatives",
        "function_name": "displaced_diffusion_model",
        "input_schema": {
            "properties": {
                "displacement": {"type": "number"},
                "div_yield": {"default": 0.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau", "displacement"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/displaced_diffusion_model",
        "summary": "Displaced-diffusion (shifted lognormal) European option price.",
        "tool_name": "displaced_diffusion_model",
    },
    {
        "description": "",
        "domain": "derivatives",
        "function_name": "duration_macaulay",
        "input_schema": {
            "properties": {
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "times": {"type": "object"},
                "yield_rate": {"type": "number"},
            },
            "required": ["cashflows", "times", "yield_rate"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/duration_macaulay",
        "summary": "Macaulay duration — PV-weighted average time to cashflows (in years).",
        "tool_name": "duration_macaulay",
    },
    {
        "description": "Computed by central difference of the price function at ±0.5bp.",
        "domain": "derivatives",
        "function_name": "dv01_pvbp",
        "input_schema": {
            "properties": {
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "times": {"type": "object"},
                "yield_rate": {"type": "number"},
            },
            "required": ["cashflows", "times", "yield_rate"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/dv01_pvbp",
        "summary": "DV01 / PVBP — price change for a 1 basis-point yield move.",
        "tool_name": "dv01_pvbp",
    },
    {
        "description": "``D_eff = (P− − P+) / (2 · P0 · Δy)`` — model-agnostic, so it captures\n"
        "embedded optionality (callable/puttable) that analytic duration misses.",
        "domain": "derivatives",
        "function_name": "effective_duration",
        "input_schema": {
            "properties": {
                "price_base": {"type": "number"},
                "price_down": {"type": "number"},
                "price_up": {"type": "number"},
                "yield_shock": {"type": "number"},
            },
            "required": ["price_base", "price_up", "price_down", "yield_shock"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/effective_duration",
        "summary": "Effective duration from re-priced bond values under a parallel shock.",
        "tool_name": "effective_duration",
    },
    {
        "description": "``notional · (equity_return − funding·τ) · DF`` to the equity receiver.",
        "domain": "derivatives",
        "function_name": "equity_swap_pricer",
        "input_schema": {
            "properties": {
                "accrual": {"type": "number"},
                "discount_factor": {"type": "number"},
                "equity_return": {"type": "number"},
                "funding_rate": {"type": "number"},
                "notional": {"type": "number"},
                "receive_equity": {"default": True, "type": "boolean"},
            },
            "required": ["notional", "equity_return", "funding_rate", "accrual", "discount_factor"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/equity_swap_pricer",
        "summary": "Value an equity swap leg (equity return vs funding).",
        "tool_name": "equity_swap_pricer",
    },
    {
        "description": "``Value = notional · (forward − fra_rate) · accrual · DF(end)``. Zero "
        "value\n"
        "when the contracted FRA rate equals the projected forward.",
        "domain": "derivatives",
        "function_name": "forward_rate_agreement_fra",
        "input_schema": {
            "properties": {
                "discount_factor": {"type": "number"},
                "end": {"type": "number"},
                "forward_rate": {"type": "number"},
                "fra_rate": {"type": "number"},
                "notional": {"type": "number"},
                "start": {"type": "number"},
            },
            "required": ["notional", "fra_rate", "forward_rate", "start", "end", "discount_factor"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/forward_rate_agreement_fra",
        "summary": "Mark-to-market value of a forward rate agreement (long = pay fixed).",
        "tool_name": "forward_rate_agreement_fra",
    },
    {
        "description": "``F = S · e^{(r_dom − r_for)·τ}``. If a contracted forward is supplied, "
        "the\n"
        "MtM value (domestic ccy) of a long-foreign position is\n"
        "``notional · (F − contracted) · e^{−r_dom·τ}``.",
        "domain": "derivatives",
        "function_name": "fx_forward_pricer",
        "input_schema": {
            "properties": {
                "contracted_forward": {"type": "object"},
                "notional": {"default": 1.0, "type": "number"},
                "rate_domestic": {"type": "number"},
                "rate_foreign": {"type": "number"},
                "spot": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "rate_domestic", "rate_foreign", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/fx_forward_pricer",
        "summary": "FX forward rate and mark-to-market via covered interest-rate parity.",
        "tool_name": "fx_forward_pricer",
    },
    {
        "description": "Black-Scholes with the foreign rate acting as a continuous dividend "
        "yield:\n"
        "``Call = S e^{−r_for τ} N(d1) − K e^{−r_dom τ} N(d2)``. Satisfies FX\n"
        "put-call parity ``C − P = S e^{−r_for τ} − K e^{−r_dom τ}``.",
        "domain": "derivatives",
        "function_name": "fx_option_pricer_garman_kohlhagen",
        "input_schema": {
            "properties": {
                "notional": {"default": 1.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate_domestic": {"type": "number"},
                "rate_foreign": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate_domestic", "rate_foreign", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/fx_option_pricer_garman_kohlhagen",
        "summary": "Garman-Kohlhagen FX option price.",
        "tool_name": "fx_option_pricer_garman_kohlhagen",
    },
    {
        "description": "Prices via the single-integral representation using the characteristic\n"
        "function. As ``sigma`` (vol-of-vol) → 0 with ``v0 = theta`` the price "
        "tends\n"
        "to Black-Scholes with constant vol ``sqrt(theta)``.",
        "domain": "derivatives",
        "function_name": "heston_stochastic_volatility_model",
        "input_schema": {
            "properties": {
                "kappa": {"type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "rho": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
                "theta": {"type": "number"},
                "v0": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "tau", "v0", "kappa", "theta", "sigma", "rho"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/heston_stochastic_volatility_model",
        "summary": "Heston stochastic-volatility European option price (semi-analytic).",
        "tool_name": "heston_stochastic_volatility_model",
    },
    {
        "description": "``dr = κ(θ−r)dt + σ dW`` — the extended-Vasicek form; with a constant θ "
        "the\n"
        "closed-form ZCB price coincides with Vasicek. Returns the analytic bond\n"
        "price and a Monte Carlo cross-check.\n"
        "\n"
        "Note: with ``theta_const`` held constant this function literally "
        "delegates\n"
        "to ``vasicek_interest_rate_model`` — it is not a genuine time-dependent\n"
        "Hull-White model calibrated to fit an observed market forward curve.",
        "domain": "derivatives",
        "function_name": "hull_white_short_rate_model",
        "input_schema": {
            "properties": {
                "kappa": {"type": "number"},
                "maturity": {"type": "number"},
                "n_simulations": {"default": 50000, "type": "integer"},
                "n_steps": {"default": 100, "type": "integer"},
                "r0": {"type": "number"},
                "seed": {"default": 103, "type": "integer"},
                "sigma": {"type": "number"},
                "theta_const": {"default": 0.03, "type": "number"},
            },
            "required": ["r0", "kappa", "sigma", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/hull_white_short_rate_model",
        "summary": "Hull-White one-factor model with a constant mean-reversion level.",
        "tool_name": "hull_white_short_rate_model",
    },
    {
        "description": "Coupons and principal accrete with cumulative inflation; the resulting\n"
        "nominal cashflows are discounted at the real yield (the standard\n"
        "real-cashflow / real-yield convention).",
        "domain": "derivatives",
        "function_name": "inflation_linked_bond_pricer",
        "input_schema": {
            "properties": {
                "face_value": {"type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "inflation_rate": {"type": "number"},
                "maturity": {"type": "number"},
                "real_coupon_rate": {"type": "number"},
                "real_yield": {"type": "number"},
            },
            "required": [
                "face_value",
                "real_coupon_rate",
                "real_yield",
                "maturity",
                "inflation_rate",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/inflation_linked_bond_pricer",
        "summary": "Price an inflation-linked (real) bond with index-uplifted principal.",
        "tool_name": "inflation_linked_bond_pricer",
    },
    {
        "description": "Float leg PV = ``notional · Σ fwd_i · τ_i · DF_i``; fixed leg PV =\n"
        "``notional · fixed · Σ τ_i · DF_i``. Swap value to the payer is\n"
        "``float − fixed``. The par (break-even) fixed rate is also returned.",
        "domain": "derivatives",
        "function_name": "interest_rate_swap_irs_pricer",
        "input_schema": {
            "properties": {
                "accruals": {"type": "object"},
                "discount_factors": {"type": "object"},
                "fixed_rate": {"type": "number"},
                "forward_rates": {"type": "object"},
                "notional": {"type": "number"},
                "pay_fixed": {"default": True, "type": "boolean"},
            },
            "required": ["notional", "fixed_rate", "forward_rates", "discount_factors", "accruals"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/interest_rate_swap_irs_pricer",
        "summary": "Price a vanilla fixed-vs-float interest-rate swap.",
        "tool_name": "interest_rate_swap_irs_pricer",
    },
    {
        "description": "Evolves a vector of forward LIBOR rates under the spot measure with the\n"
        "standard log-normal BGM drift, discretised via the Glasserman-Zhao\n"
        "predictor-corrector Euler scheme (see\n"
        "``_lmm_terminal_rates_predictor_corrector``). Returns the mean terminal\n"
        "forward curve; rates stay positive (log-normal dynamics).\n"
        "\n"
        "The drift for rate ``i`` sums over ``j = 0..i`` inclusive (including rate\n"
        "``i`` itself), evaluated from a single consistent rate vector at each of\n"
        "the predictor and corrector stages -- not a sequential same-step\n"
        "overwrite (see ``_lmm_terminal_rates_sequential_euler`` for the retained,\n"
        "non-production former scheme).",
        "domain": "derivatives",
        "function_name": "lmm_bgm_rate_model",
        "input_schema": {
            "properties": {
                "forward_rates": {"type": "object"},
                "horizon": {"type": "number"},
                "n_simulations": {"default": 20000, "type": "integer"},
                "n_steps": {"default": 20, "type": "integer"},
                "seed": {"default": 104, "type": "integer"},
                "tenor": {"type": "number"},
                "vols": {"type": "object"},
            },
            "required": ["forward_rates", "vols", "tenor", "horizon"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/lmm_bgm_rate_model",
        "summary": "LIBOR Market Model (BGM) forward-rate Monte Carlo simulation.",
        "tool_name": "lmm_bgm_rate_model",
    },
    {
        "description": "Uses finite differences of the Dupire equation\n"
        "``σ_loc² = (∂C/∂T + r K ∂C/∂K) / (½ K² ∂²C/∂K²)`` on the supplied grid,\n"
        "covering the FULL grid: central differences in strike at interior\n"
        "points, one-sided (forward/backward) 2nd-order-accurate differences at\n"
        "the two strike boundaries (exact non-uniform-grid Fornberg-style 3-point\n"
        "stencils -- exact for any quadratic, verified against hand-differentiated\n"
        "polynomials), and a forward/backward difference in maturity at the\n"
        "first/last maturity respectively (interior maturities also use the\n"
        "forward difference toward the next maturity).",
        "domain": "derivatives",
        "function_name": "local_volatility_dupire_model",
        "input_schema": {
            "properties": {
                "call_surface": {"type": "object"},
                "maturities": {"type": "object"},
                "rate": {"type": "number"},
                "spot": {"type": "number"},
                "strikes": {"type": "object"},
            },
            "required": ["strikes", "maturities", "call_surface", "rate", "spot"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/local_volatility_dupire_model",
        "summary": "Dupire local volatility surface from a call-price surface.",
        "tool_name": "local_volatility_dupire_model",
    },
    {
        "description": "Floating-strike: call pays ``S_T − min`` (>= 0), put pays ``max − S_T``.\n"
        "Fixed-strike: call pays ``max − K``, put pays ``K − min``. Always >= the\n"
        "corresponding vanilla payoff.",
        "domain": "derivatives",
        "function_name": "lookback_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "n_steps": {"default": 100, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "qmc": {"default": False, "type": "boolean"},
                "rate": {"type": "number"},
                "seed": {"default": 31, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "strike_type": {"default": "floating", "type": "string"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/lookback_option_pricer",
        "summary": "Lookback option price via Monte Carlo.",
        "tool_name": "lookback_option_pricer",
    },
    {
        "description": "Approximates the percentage price change for a 1-unit yield move:\n"
        "``ΔP/P ≈ −D_mod · Δy``.",
        "domain": "derivatives",
        "function_name": "modified_duration",
        "input_schema": {
            "properties": {
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "times": {"type": "object"},
                "yield_rate": {"type": "number"},
            },
            "required": ["cashflows", "times", "yield_rate"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/modified_duration",
        "summary": "Modified duration = Macaulay duration / (1 + y/m).",
        "tool_name": "modified_duration",
    },
    {
        "description": "Randoms are pre-drawn in pure Python (CLAUDE.md §3.1 RULE 3); the JIT "
        "kernel\n"
        "only consumes the pre-drawn standard-normal array.",
        "domain": "derivatives",
        "function_name": "monte_carlo_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 12345, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/monte_carlo_option_pricer",
        "summary": "Monte Carlo price of a European option (terminal GBM payoff).",
        "tool_name": "monte_carlo_option_pricer",
    },
    {
        "description": "Parameters: ``beta0`` (level), ``beta1`` (slope), ``beta2`` (curvature),\n"
        "``tau`` (decay). ``beta0 + beta1`` is the instantaneous short rate and\n"
        "``beta0`` is the asymptotic long rate.",
        "domain": "derivatives",
        "function_name": "nelson_siegel_curve_fit",
        "input_schema": {
            "properties": {
                "maturities": {"type": "object"},
                "tau_init": {"default": 1.5, "type": "number"},
                "yields": {"type": "object"},
            },
            "required": ["maturities", "yields"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/nelson_siegel_curve_fit",
        "summary": "Fit a Nelson-Siegel curve to observed yields.",
        "tool_name": "nelson_siegel_curve_fit",
    },
    {
        "description": "Adds a second curvature hump (``beta3``, ``tau2``) to Nelson-Siegel, "
        "giving\n"
        "a closer fit to longer/more complex term structures.",
        "domain": "derivatives",
        "function_name": "nelson_siegel_svensson_curve",
        "input_schema": {
            "properties": {
                "maturities": {"type": "object"},
                "tau1_init": {"default": 1.5, "type": "number"},
                "tau2_init": {"default": 8.0, "type": "number"},
                "yields": {"type": "object"},
            },
            "required": ["maturities", "yields"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/nelson_siegel_svensson_curve",
        "summary": "Fit the Nelson-Siegel-Svensson (six-parameter) curve.",
        "tool_name": "nelson_siegel_svensson_curve",
    },
    {
        "description": "NIG is Brownian motion subordinated by an inverse-Gaussian process. The\n"
        "drift is corrected so the discounted spot is a martingale.",
        "domain": "derivatives",
        "function_name": "normal_inverse_gaussian_model",
        "input_schema": {
            "properties": {
                "alpha": {"default": 15.0, "type": "number"},
                "beta": {"default": -5.0, "type": "number"},
                "delta": {"default": 0.5, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 11, "type": "integer"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/normal_inverse_gaussian_model",
        "summary": "Normal Inverse Gaussian European option price via Monte Carlo.",
        "tool_name": "normal_inverse_gaussian_model",
    },
    {
        "description": "Finds the constant spread added to the short rate on the pricing tree "
        "that\n"
        "reprices the callable bond to its market price — stripping out the "
        "embedded\n"
        "option so spreads are comparable across bonds.\n"
        "\n"
        "Note: the spread is root-found (Brent's method) against\n"
        "``callable_bond_pricer``'s tree price rather than expressed in closed\n"
        "form — the equation above is the condition the solver satisfies, not an\n"
        "explicit OAS formula.",
        "domain": "derivatives",
        "function_name": "oas_option_adjusted_spread",
        "input_schema": {
            "properties": {
                "call_price": {"type": "number"},
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 1, "type": "integer"},
                "market_price": {"type": "number"},
                "maturity": {"type": "number"},
                "rate_vol": {"type": "number"},
                "short_rate": {"type": "number"},
            },
            "required": [
                "market_price",
                "face_value",
                "coupon_rate",
                "short_rate",
                "rate_vol",
                "maturity",
                "call_price",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/oas_option_adjusted_spread",
        "summary": "Option-adjusted spread of a callable bond.",
        "tool_name": "oas_option_adjusted_spread",
    },
    {
        "description": "OIS swaps pay annually against compounded overnight; the discount curve "
        "is\n"
        "bootstrapped exactly as for par swaps (single-curve OIS-discounting).",
        "domain": "derivatives",
        "function_name": "ois_curve_sonia_sofr",
        "input_schema": {
            "properties": {
                "frequency": {"default": 1, "type": "integer"},
                "maturities": {"type": "object"},
                "ois_rates": {"type": "object"},
            },
            "required": ["ois_rates", "maturities"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/ois_curve_sonia_sofr",
        "summary": "Build an OIS (SONIA/SOFR) discount curve from quoted OIS swap rates.",
        "tool_name": "ois_curve_sonia_sofr",
    },
    {
        "description": "Net cashflow = ``notional · (compounded_overnight − fixed) · accrual``,\n"
        "discounted. Zero value when the compounded rate equals the fixed rate.",
        "domain": "derivatives",
        "function_name": "overnight_index_swap_ois",
        "input_schema": {
            "properties": {
                "accrual": {"type": "number"},
                "compounded_rate": {"type": "number"},
                "discount_factor": {"type": "number"},
                "fixed_rate": {"type": "number"},
                "notional": {"type": "number"},
                "pay_fixed": {"default": True, "type": "boolean"},
            },
            "required": ["notional", "fixed_rate", "compounded_rate", "accrual", "discount_factor"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/overnight_index_swap_ois",
        "summary": "Value a single-period overnight index swap.",
        "tool_name": "overnight_index_swap_ois",
    },
    {
        "description": "A puttable bond is worth at least the equivalent straight bond — the\n"
        "embedded put belongs to the holder.\n"
        "\n"
        "Note: uses the same simplified multiplicative short-rate lattice as\n"
        "``callable_bond_pricer`` — fixed 0.5/0.5 branch probabilities, not\n"
        "calibrated to a market curve.",
        "domain": "derivatives",
        "function_name": "puttable_bond_pricer",
        "input_schema": {
            "properties": {
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 1, "type": "integer"},
                "maturity": {"type": "number"},
                "put_price": {"type": "number"},
                "rate_vol": {"type": "number"},
                "short_rate": {"type": "number"},
            },
            "required": [
                "face_value",
                "coupon_rate",
                "short_rate",
                "rate_vol",
                "maturity",
                "put_price",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/puttable_bond_pricer",
        "summary": "Price a puttable bond (holder's option) on a short-rate binomial tree.",
        "tool_name": "puttable_bond_pricer",
    },
    {
        "description": "Payoff references the max (best-of) or min (worst-of) of the terminal "
        "asset\n"
        "prices against the strike.",
        "domain": "derivatives",
        "function_name": "rainbow_option_pricer",
        "input_schema": {
            "properties": {
                "correlation": {"type": "object"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rainbow_type": {"default": "best-of", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 61, "type": "integer"},
                "sigmas": {"type": "object"},
                "spots": {"type": "object"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spots", "strike", "rate", "sigmas", "tau", "correlation"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/rainbow_option_pricer",
        "summary": "Rainbow (best-of / worst-of) option price via Monte Carlo.",
        "tool_name": "rainbow_option_pricer",
    },
    {
        "description": "A rough-volatility model with Hurst exponent ``H < 0.5``. Randoms are\n"
        "pre-drawn in pure Python (CLAUDE.md §3.1 RULE 3).\n"
        "\n"
        "Three independent numerical-correctness bugs were fixed here (task #18,\n"
        "found via the Tier 3 #2 test-reference audit and its follow-up\n"
        "verification -- see _rbergomi_volterra_driver, "
        "_rbergomi_discrete_variance\n"
        "and _rbergomi_paths' docstrings/comments for each in detail):\n"
        "\n"
        "1. The fractional driver froze each increment's weight at the moment it\n"
        "   was drawn instead of recomputing it (as a gap to the current time) at\n"
        "   every later step -- right marginal variance, wrong autocovariance,\n"
        "   invisible to any test that only checks a single time point.\n"
        "2. The martingale correction used the CONTINUUM-limit variance\n"
        "   (``t^(2H)``), which the naive discrete Riemann sum undershoots\n"
        "   substantially at this model's default ``n_steps`` -- pulling\n"
        "   ``E[var_t]`` well below ``xi``.\n"
        "3. The variance applied to a given step's price shock was computed using\n"
        "   that SAME step's own Brownian draw rather than a value predictable\n"
        '   from strictly prior information -- correlating "random" volatility\n'
        "   with the shock it should be independent of and breaking the\n"
        "   risk-neutral drift (``E[S_T] != S0*exp(rT)``; put-call parity was off\n"
        "   by more than 15, not a rounding-level miss).\n"
        "\n"
        "Verified (not merely believed) via three checks the code lacked before:\n"
        "an exact hand-computable impulse-response test on the fractional driver\n"
        "(bug 1), an ``eta -> 0`` reduction to flat-vol Black-Scholes (bugs 2 & 3\n"
        "together -- degenerate case has no vol-of-vol to expose either), and\n"
        "put-call parity at the model's actual default parameters (bug 3\n"
        "specifically, since parity holds regardless of how the volatility itself\n"
        "is modelled).",
        "domain": "derivatives",
        "function_name": "rough_volatility_rbergomi_model",
        "input_schema": {
            "properties": {
                "control_variate": {"default": False, "type": "boolean"},
                "eta": {"default": 1.5, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "hurst": {"default": 0.1, "type": "number"},
                "n_simulations": {"default": 50000, "type": "integer"},
                "n_steps": {"default": 50, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "rho": {"default": -0.7, "type": "number"},
                "seed": {"default": 2024, "type": "integer"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
                "xi": {"default": 0.04, "type": "number"},
            },
            "required": ["spot", "strike", "rate", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/rough_volatility_rbergomi_model",
        "summary": "Rough Bergomi (rBergomi) European option price via Monte Carlo.",
        "tool_name": "rough_volatility_rbergomi_model",
    },
    {
        "description": "Returns the Black implied volatility for the given strike under the SABR\n"
        "dynamics. At-the-money it reduces to the well-known ATM SABR vol.",
        "domain": "derivatives",
        "function_name": "sabr_volatility_model",
        "input_schema": {
            "properties": {
                "alpha": {"type": "number"},
                "beta": {"type": "number"},
                "forward": {"type": "number"},
                "nu": {"type": "number"},
                "rho": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["forward", "strike", "tau", "alpha", "beta", "rho", "nu"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/sabr_volatility_model",
        "summary": "SABR implied (lognormal/Black) volatility via Hagan's expansion.",
        "tool_name": "sabr_volatility_model",
    },
    {
        "description": "Prices an option on ``S1 − S2`` by reducing it to a Black-76 option on "
        "the\n"
        "ratio with an effective volatility. Exact when ``strike == 0`` "
        "(Margrabe).\n"
        "Inputs are treated as forwards (Black-76); the value is discounted once.",
        "domain": "derivatives",
        "function_name": "spread_option_kirk_approximation",
        "input_schema": {
            "properties": {
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "rho": {"type": "number"},
                "sigma1": {"type": "number"},
                "sigma2": {"type": "number"},
                "spot1": {"type": "number"},
                "spot2": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
            },
            "required": ["spot1", "spot2", "strike", "rate", "sigma1", "sigma2", "rho", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/spread_option_kirk_approximation",
        "summary": "Spread option price via Kirk's approximation.",
        "tool_name": "spread_option_kirk_approximation",
    },
    {
        "description": "For each tenor, ``swap_rate = (1 − DF(T)) / (Σ τ · DF)`` — the fixed rate\n"
        "that makes a par swap have zero value.",
        "domain": "derivatives",
        "function_name": "swap_rate_curve",
        "input_schema": {
            "properties": {
                "discount_factors": {"type": "object"},
                "frequency": {"default": 1, "type": "integer"},
                "maturities": {"type": "object"},
            },
            "required": ["discount_factors", "maturities"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/swap_rate_curve",
        "summary": "Par swap rates implied by a discount-factor curve.",
        "tool_name": "swap_rate_curve",
    },
    {
        "description": "``Price = annuity · Black(forward_swap_rate, strike, vol, expiry)``. A "
        "payer\n"
        "swaption is a call on the swap rate; a receiver swaption is a put.",
        "domain": "derivatives",
        "function_name": "swaption_pricer_black",
        "input_schema": {
            "properties": {
                "annuity": {"type": "number"},
                "expiry": {"type": "number"},
                "forward_swap_rate": {"type": "number"},
                "notional": {"type": "number"},
                "option_type": {"default": "payer", "type": "string"},
                "strike": {"type": "number"},
                "vol": {"type": "number"},
            },
            "required": ["notional", "forward_swap_rate", "strike", "vol", "expiry", "annuity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/swaption_pricer_black",
        "summary": "Price a European swaption under the Black model.",
        "tool_name": "swaption_pricer_black",
    },
    {
        "description": "Computes the SABR lognormal vol for the (forward, strike, expiry) point "
        "via\n"
        "Hagan's expansion, then plugs it into the Black swaption formula.",
        "domain": "derivatives",
        "function_name": "swaption_pricer_sabr",
        "input_schema": {
            "properties": {
                "alpha": {"type": "number"},
                "annuity": {"type": "number"},
                "beta": {"type": "number"},
                "expiry": {"type": "number"},
                "forward_swap_rate": {"type": "number"},
                "notional": {"type": "number"},
                "nu": {"type": "number"},
                "option_type": {"default": "payer", "type": "string"},
                "rho": {"type": "number"},
                "strike": {"type": "number"},
            },
            "required": [
                "notional",
                "forward_swap_rate",
                "strike",
                "expiry",
                "annuity",
                "alpha",
                "beta",
                "rho",
                "nu",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/swaption_pricer_sabr",
        "summary": "Price a swaption using a SABR-implied Black volatility.",
        "tool_name": "swaption_pricer_sabr",
    },
    {
        "description": "The total-return receiver gets the asset's total return and pays a "
        "financing\n"
        "rate (e.g. SOFR + spread): ``notional · (asset_return − financing·τ) · "
        "DF``.",
        "domain": "derivatives",
        "function_name": "total_return_swap_trs",
        "input_schema": {
            "properties": {
                "accrual": {"type": "number"},
                "asset_return": {"type": "number"},
                "discount_factor": {"type": "number"},
                "financing_rate": {"type": "number"},
                "notional": {"type": "number"},
                "receive_total_return": {"default": True, "type": "boolean"},
            },
            "required": [
                "notional",
                "asset_return",
                "financing_rate",
                "accrual",
                "discount_factor",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/total_return_swap_trs",
        "summary": "Value a total-return swap leg.",
        "tool_name": "total_return_swap_trs",
    },
    {
        "description": "Up/middle/down branching converges to Black-Scholes for European options.\n"
        "Handles American exercise.",
        "domain": "derivatives",
        "function_name": "trinomial_tree_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {"default": 0.0, "type": "number"},
                "n_steps": {"default": 300, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "style": {"default": "european", "type": "string"},
                "tau": {"type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/trinomial_tree_option_pricer",
        "summary": "Boyle trinomial tree option price.",
        "tool_name": "trinomial_tree_option_pricer",
    },
    {
        "description": "Note: the ``theta`` parameter here is the VG skew parameter\n"
        "(subordinated-drift), unrelated to the Greek theta (time decay)\n"
        "optionally returned when ``greeks=True``.\n"
        "\n"
        "Time-changes Brownian motion by a Gamma subordinator (mean 1, variance\n"
        "``nu``). The martingale drift correction ``omega`` is computed in closed\n"
        "form so the discounted spot is a martingale.",
        "domain": "derivatives",
        "function_name": "variance_gamma_model",
        "input_schema": {
            "properties": {
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "nu": {"default": 0.2, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 7, "type": "integer"},
                "sigma": {"default": 0.2, "type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
                "theta": {"default": -0.1, "type": "number"},
            },
            "required": ["spot", "strike", "rate", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/variance_gamma_model",
        "summary": "Variance Gamma European option price via Monte Carlo.",
        "tool_name": "variance_gamma_model",
    },
    {
        "description": "``dr = κ(θ−r)dt + σ dW``. The affine ZCB price is ``P = A·e^{−B·r0}``. "
        "The\n"
        "short rate is Gaussian (can go negative).",
        "domain": "derivatives",
        "function_name": "vasicek_interest_rate_model",
        "input_schema": {
            "properties": {
                "kappa": {"type": "number"},
                "maturity": {"type": "number"},
                "n_simulations": {"default": 50000, "type": "integer"},
                "n_steps": {"default": 100, "type": "integer"},
                "r0": {"type": "number"},
                "seed": {"default": 101, "type": "integer"},
                "sigma": {"type": "number"},
                "theta": {"type": "number"},
            },
            "required": ["r0", "kappa", "theta", "sigma", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/vasicek_interest_rate_model",
        "summary": "Vasicek model: closed-form zero-coupon bond price + simulated short rate.",
        "tool_name": "vasicek_interest_rate_model",
    },
    {
        "description": "Builds the cashflow stream truncated at ``call_date`` with redemption at\n"
        "``call_price`` and solves for the yield.",
        "domain": "derivatives",
        "function_name": "yield_to_call",
        "input_schema": {
            "properties": {
                "call_date": {"type": "number"},
                "call_price": {"type": "number"},
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "price": {"type": "number"},
            },
            "required": ["price", "face_value", "coupon_rate", "call_price", "call_date"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/yield_to_call",
        "summary": "Yield to call — yield assuming redemption at the first call date.",
        "tool_name": "yield_to_call",
    },
    {
        "description": "Solved by Brent root-finding. Recovers the input yield exactly when "
        "``price``\n"
        "was produced by :func:`engine.deriv_bonds.bond_pricer_fixed_coupon`.",
        "domain": "derivatives",
        "function_name": "yield_to_maturity",
        "input_schema": {
            "properties": {
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "price": {"type": "number"},
                "times": {"type": "object"},
            },
            "required": ["price", "cashflows", "times"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/yield_to_maturity",
        "summary": "Yield to maturity — the flat rate that discounts cashflows to ``price``.",
        "tool_name": "yield_to_maturity",
    },
    {
        "description": "Solves for ``z`` such that ``Σ cf_k (1 + (zero_k + z)/m)^{-m t_k} = "
        "price``.",
        "domain": "derivatives",
        "function_name": "z_spread_calculator",
        "input_schema": {
            "properties": {
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "price": {"type": "number"},
                "times": {"type": "object"},
                "zero_rates": {"type": "object"},
            },
            "required": ["price", "cashflows", "times", "zero_rates"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/z_spread_calculator",
        "summary": "Z-spread — constant spread over the zero curve that reprices the bond.",
        "tool_name": "z_spread_calculator",
    },
    {
        "description": "",
        "domain": "derivatives",
        "function_name": "zero_coupon_bond_pricer",
        "input_schema": {
            "properties": {
                "face_value": {"type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "maturity": {"type": "number"},
                "yield_rate": {"type": "number"},
            },
            "required": ["face_value", "yield_rate", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/zero_coupon_bond_pricer",
        "summary": "Price a zero-coupon bond: ``face / (1 + y/m)^{m·T}``.",
        "tool_name": "zero_coupon_bond_pricer",
    },
    {
        "description": "``encumbrance = encumbered assets / total assets``. High encumbrance "
        "reduces\n"
        "the unencumbered asset pool available to monetise in stress.",
        "domain": "liquidity",
        "function_name": "asset_encumbrance_ratio",
        "input_schema": {
            "properties": {
                "encumbered_assets": {"type": "number"},
                "total_assets": {"type": "number"},
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
                "asf_factors": {"type": "object"},
                "funding_amounts": {"type": "object"},
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
                "bucket_inflows": {"type": "object"},
                "bucket_outflows": {"type": "object"},
                "buckets": {"type": "object"},
                "opening_balance": {"default": 0.0, "type": "number"},
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
                "daily_inflows": {"type": "object"},
                "daily_outflows": {"type": "object"},
                "opening_balance": {"default": 0.0, "type": "number"},
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
                "asset_ratings": {"type": "object"},
                "asset_values": {"type": "object"},
                "cb_haircuts": {"type": "object"},
                "min_rating": {"type": "integer"},
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
                "already_pledged": {"type": "object"},
                "collateral_values": {"type": "object"},
                "haircuts": {"type": "object"},
            },
            "required": ["collateral_values", "haircuts"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/collateral_availability_analysis",
        "summary": "Collateral availability — post-haircut monetisable value.",
        "tool_name": "collateral_availability_analysis",
    },
    {
        "description": "This is NOT the BCBS 238 reference combined scenario: BCBS 238's own\n"
        "combined idiosyncratic + market-wide scenario (§II paras 19-20) runs off\n"
        "the LCR's own regulator-set retail run-off categories (3%/5%/10%\n"
        "depending on deposit stability), whereas this function applies its own\n"
        "flat 15% retail / 100% wholesale run-off convention instead.\n"
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
                "hqla_by_level": {"type": "object"},
                "inflows": {"default": 0.0, "type": "number"},
                "market_haircuts": {"type": "object"},
                "retail_deposits": {"type": "number"},
                "retail_runoff": {"default": 0.15, "type": "number"},
                "wholesale_funding": {"type": "number"},
                "wholesale_runoff": {"default": 1.0, "type": "number"},
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
            "properties": {"metrics": {"type": "object"}, "thresholds": {"type": "object"}},
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
                "ccf": {"type": "object"},
                "commitment_amounts": {"type": "object"},
                "draw_probabilities": {"type": "object"},
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
                "fx_rate": {"type": "number"},
                "shortfall_amount": {"type": "number"},
                "shortfall_ccy": {"type": "string"},
                "surplus_amount": {"type": "number"},
                "surplus_ccy": {"type": "string"},
                "swap_haircut": {"default": 0.0, "type": "number"},
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
                "deposit_features": {"type": "object"},
                "stable_threshold": {"default": 0.5, "type": "number"},
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
                "directions": {"type": "object"},
                "indicators": {"type": "object"},
                "thresholds": {"type": "object"},
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
                "funding_amounts": {"type": "object"},
                "funding_rates": {"type": "object"},
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
                "funding_amounts": {"type": "object"},
                "tenors_days": {"type": "object"},
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
                "inflows_by_ccy": {"type": "object"},
                "outflows_by_ccy": {"type": "object"},
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
            "properties": {"asset_values": {"type": "object"}, "haircuts": {"type": "object"}},
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
                "asset_values": {"type": "object"},
                "haircut": {"default": 0.15, "type": "number"},
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
                "asset_values": {"type": "object"},
                "haircut": {"default": 0.25, "type": "number"},
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
                "hqla": {"type": "number"},
                "retail_deposits": {"type": "number"},
                "retail_runoff": {"default": 0.1, "type": "number"},
                "wholesale_funding": {"type": "number"},
                "wholesale_runoff": {"default": 1.0, "type": "number"},
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
                "counterbalancing_capacity": {"type": "number"},
                "minimum_survival_days": {"default": 90.0, "type": "number"},
                "stressed_net_outflow": {"type": "number"},
                "survival_days": {"type": "number"},
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
            "properties": {"scenarios": {"type": "object"}},
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
                "net_flows": {"type": "object"},
                "opening_balance": {"type": "number"},
                "timestamps": {"type": "object"},
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
                "delay_factor": {"default": 0.5, "type": "number"},
                "inflow_delay_shock": {"default": 0.0, "type": "number"},
                "net_flows": {"type": "object"},
                "opening_balance": {"type": "number"},
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
            "properties": {"entity_positions": {"type": "object"}},
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
                "confidence_buffer": {"default": 0.0, "type": "number"},
                "stressed_net_outflows": {"type": "object"},
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
                "gross_inflows": {"type": "number"},
                "gross_outflows": {"type": "number"},
                "hqla": {"type": "number"},
                "inflow_cap": {"default": 0.75, "type": "number"},
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
                "asset_maturities": {"type": "object"},
                "buckets": {"type": "object"},
                "liability_maturities": {"type": "object"},
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
                "amber_threshold": {"type": "number"},
                "green_threshold": {"type": "number"},
                "higher_is_better": {"default": True, "type": "boolean"},
                "metric_value": {"type": "number"},
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
            "properties": {"scores": {"type": "object"}, "weights": {"type": "object"}},
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
                "balances": {"type": "object"},
                "hqla": {"type": "number"},
                "inflows": {"default": 0.0, "type": "number"},
                "runoff_rates": {"type": "object"},
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
                "base_rate": {"type": "number"},
                "contingent_spread": {"default": 0.0, "type": "number"},
                "liquidity_spread": {"type": "number"},
                "notional": {"type": "number"},
                "tenor_years": {"type": "number"},
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
                "base_outflow": {"type": "number"},
                "confidence_level": {"default": 0.99, "type": "number"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "outflow_vol": {"type": "number"},
                "seed": {"default": 42, "type": "object"},
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
                "hqla_by_level": {"type": "object"},
                "market_haircuts": {"type": "object"},
                "outflow": {"type": "number"},
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
                "available_stable_funding": {"type": "number"},
                "required_stable_funding": {"type": "number"},
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
                "base_haircuts": {"type": "object"},
                "collateral_values": {"type": "object"},
                "stress_multipliers": {"type": "object"},
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
            "properties": {"asset_amounts": {"type": "object"}, "rsf_factors": {"type": "object"}},
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
                "deposit_balances": {"type": "object"},
                "runoff_rates": {"type": "object"},
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
                "maturing_amounts": {"type": "object"},
                "rollover_rates": {"type": "object"},
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
            "properties": {"daily_net_outflows": {"type": "object"}, "hqla": {"type": "number"}},
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
            "properties": {"counterparty_amounts": {"type": "object"}},
            "required": ["counterparty_amounts"],
            "type": "object",
        },
        "path": "/api/v1/liquidity/wholesale_funding_concentration",
        "summary": "Wholesale funding concentration via the Herfindahl-Hirschman Index.",
        "tool_name": "wholesale_funding_concentration",
    },
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
    {
        "description": "Superseded by the Standardised Measurement Approach for Basel III/IV\n"
        "regulatory capital (see ``basel_standardised_measurement_sma``); retained\n"
        "here for economic-capital, internal scenario analysis, and jurisdictions\n"
        "still on earlier timelines only.\n"
        "\n"
        "The AMA permits the LDA internal model. Under Basel II §669(b), if a bank "
        "can\n"
        "demonstrate that expected loss (EL) is already captured in its "
        "provisioning /\n"
        "pricing, capital may be set to unexpected loss only (OpVaR − EL); "
        "otherwise\n"
        "capital equals the full OpVaR.\n"
        "\n"
        "OpVaR and EL are not supplied by the caller — both are computed internally "
        "by\n"
        "running the full LDA pipeline (frequency/severity MLE fit, then a Monte "
        "Carlo\n"
        "quantile) over ``annual_event_counts`` and ``loss_amounts``.",
        "domain": "operational",
        "function_name": "advanced_measurement_approach_ama",
        "input_schema": {
            "properties": {
                "annual_event_counts": {"type": "object"},
                "confidence_level": {"default": 0.999, "type": "number"},
                "expected_loss_covered": {"default": True, "type": "boolean"},
                "loss_amounts": {"type": "object"},
                "n_years": {"default": 100000, "type": "integer"},
                "seed": {"default": 42, "type": "object"},
            },
            "required": ["annual_event_counts", "loss_amounts"],
            "type": "object",
        },
        "path": "/api/v1/operational/advanced_measurement_approach_ama",
        "summary": "Advanced Measurement Approach (AMA) capital charge — retired under Basel "
        "III/IV.",
        "tool_name": "advanced_measurement_approach_ama",
    },
    {
        "description": "Base score is severity × likelihood on the 5×5 scale; overdue remediation\n"
        "escalates the score (each 30-day block adds an uplift), capped at 25.",
        "domain": "operational",
        "function_name": "audit_finding_risk_scorer",
        "input_schema": {
            "properties": {
                "likelihood": {"type": "integer"},
                "overdue_days": {"type": "number"},
                "severity": {"type": "integer"},
            },
            "required": ["severity", "likelihood", "overdue_days"],
            "type": "object",
        },
        "path": "/api/v1/operational/audit_finding_risk_scorer",
        "summary": "Score an outstanding audit finding by severity, likelihood and ageing.",
        "tool_name": "audit_finding_risk_scorer",
    },
    {
        "description": "SMA capital = BIC × ILM, where the Business Indicator Component (BIC) is "
        "a\n"
        "piecewise-linear function of the Business Indicator (12%/15%/18% marginal\n"
        "coefficients across the three buckets) and the Internal Loss Multiplier\n"
        "(ILM) scales by the bank's historical loss experience:\n"
        "``ILM = ln(e − 1 + (LC / BIC)^0.8)``. Bucket-1 banks may set ILM = 1.\n"
        "\n"
        "The ILM = 1.0 case (``use_ilm=False``, bucket-1 BI, or non-positive BIC) "
        "is\n"
        "an explicit override in code rather than a value the log formula itself\n"
        "produces.",
        "domain": "operational",
        "function_name": "basel_standardised_measurement_sma",
        "input_schema": {
            "properties": {
                "business_indicator": {"type": "number"},
                "loss_component": {"default": 0.0, "type": "number"},
                "use_ilm": {"default": True, "type": "boolean"},
            },
            "required": ["business_indicator"],
            "type": "object",
        },
        "path": "/api/v1/operational/basel_standardised_measurement_sma",
        "summary": "Basel III Standardised Measurement Approach (SMA) capital.",
        "tool_name": "basel_standardised_measurement_sma",
    },
    {
        "description": "Flags where the recovery time objective (RTO) exceeds the maximum "
        "tolerable\n"
        "downtime (MTD) and discounts the residual risk by BCP maturity. A breach "
        "of\n"
        "MTD is the dominant driver.\n"
        "\n"
        "Note:\n"
        "    ``rpo_hours`` is accepted as an input (and range-validated) but does\n"
        "    not currently affect the computed score — only ``rto_hours`` versus\n"
        "    ``max_tolerable_downtime`` and ``bcp_maturity`` drive\n"
        "    ``bc_risk_score``. See ``docs/p11-caveat-triage-plan.md`` (Tier 1)\n"
        "    for the triage of this dead parameter.",
        "domain": "operational",
        "function_name": "business_continuity_risk_score",
        "input_schema": {
            "properties": {
                "bcp_maturity": {"type": "number"},
                "max_tolerable_downtime": {"type": "number"},
                "rpo_hours": {"type": "number"},
                "rto_hours": {"type": "number"},
            },
            "required": ["rto_hours", "rpo_hours", "max_tolerable_downtime", "bcp_maturity"],
            "type": "object",
        },
        "path": "/api/v1/operational/business_continuity_risk_score",
        "summary": "Business-continuity risk from RTO versus tolerance and BCP maturity.",
        "tool_name": "business_continuity_risk_score",
    },
    {
        "description": "Translates forward-looking business-environment factor scores (e.g. on a "
        "1-5\n"
        "scale where higher = riskier) into a capital multiplier around 1.0: "
        "scores\n"
        "above the baseline increase capital, below decrease it. Part of the BEICF\n"
        "overlay permitted under the AMA.",
        "domain": "operational",
        "function_name": "business_environment_factor_bei",
        "input_schema": {
            "properties": {
                "baseline": {"default": 3.0, "type": "number"},
                "factor_scores": {"type": "object"},
                "sensitivity": {"default": 0.05, "type": "number"},
            },
            "required": ["factor_scores"],
            "type": "object",
        },
        "path": "/api/v1/operational/business_environment_factor_bei",
        "summary": "Business Environment Indicator (BEI) capital adjustment multiplier.",
        "tool_name": "business_environment_factor_bei",
    },
    {
        "description": "The classic frequency ⊗ severity convolution: for each simulated year draw "
        "a\n"
        "Poisson(lambda) number of events, then that many lognormal(mu, sigma)\n"
        "severities, and sum. Per RULE 3 all randomness is pre-drawn in pure "
        "Python;\n"
        "the per-year aggregation runs in the JIT kernel.",
        "domain": "operational",
        "function_name": "compound_loss_distribution",
        "input_schema": {
            "properties": {
                "frequency_lambda": {"type": "number"},
                "n_years": {"default": 50000, "type": "integer"},
                "seed": {"default": 42, "type": "object"},
                "severity_mu": {"type": "number"},
                "severity_sigma": {"type": "number"},
            },
            "required": ["frequency_lambda", "severity_mu", "severity_sigma"],
            "type": "object",
        },
        "path": "/api/v1/operational/compound_loss_distribution",
        "summary": "Simulate the compound (aggregate) annual loss distribution.",
        "tool_name": "compound_loss_distribution",
    },
    {
        "description": "Combines the complaints-per-1000-customers rate and the "
        "redress-to-revenue\n"
        "ratio into a normalised 0-100 conduct-risk index (higher = worse) with a "
        "RAG\n"
        "band.",
        "domain": "operational",
        "function_name": "conduct_risk_metric",
        "input_schema": {
            "properties": {
                "complaints": {"type": "number"},
                "customers": {"type": "number"},
                "redress_paid": {"type": "number"},
                "revenue": {"type": "number"},
            },
            "required": ["complaints", "customers", "redress_paid", "revenue"],
            "type": "object",
        },
        "path": "/api/v1/operational/conduct_risk_metric",
        "summary": "Composite conduct-risk metric from complaints and redress intensity.",
        "tool_name": "conduct_risk_metric",
    },
    {
        "description": "The empirical pass rate from control testing samples; an exception rate "
        "above\n"
        "a supervisory tolerance (default >5% failures) downgrades the conclusion.",
        "domain": "operational",
        "function_name": "control_testing_effectiveness",
        "input_schema": {
            "properties": {"tests_passed": {"type": "integer"}, "tests_total": {"type": "integer"}},
            "required": ["tests_passed", "tests_total"],
            "type": "object",
        },
        "path": "/api/v1/operational/control_testing_effectiveness",
        "summary": "Control testing pass rate and effectiveness conclusion.",
        "tool_name": "control_testing_effectiveness",
    },
    {
        "description": "Worst-case (given a breach) = ``records_exposed × cost_per_record +\n"
        "business_interruption_cost``; expected loss multiplies by the annual "
        "breach\n"
        "probability — a FAIR-style single-loss-expectancy estimate.",
        "domain": "operational",
        "function_name": "cyber_risk_loss_estimation",
        "input_schema": {
            "properties": {
                "breach_probability": {"type": "number"},
                "business_interruption_cost": {"default": 0.0, "type": "number"},
                "cost_per_record": {"type": "number"},
                "records_exposed": {"type": "number"},
            },
            "required": ["records_exposed", "cost_per_record", "breach_probability"],
            "type": "object",
        },
        "path": "/api/v1/operational/cyber_risk_loss_estimation",
        "summary": "Estimate expected and worst-case cyber loss.",
        "tool_name": "cyber_risk_loss_estimation",
    },
    {
        "description": "Compares the simple sum of standalone capitals (perfect-correlation, no\n"
        "diversification) with the correlated aggregate\n"
        "``sqrt(sum_i sum_j rho_ij K_i K_j)`` using a uniform pairwise "
        "correlation.\n"
        "The benefit is the reduction from imperfect correlation.",
        "domain": "operational",
        "function_name": "diversification_benefit_oprisk",
        "input_schema": {
            "properties": {
                "correlation": {"default": 0.0, "type": "number"},
                "standalone_capitals": {"type": "object"},
            },
            "required": ["standalone_capitals"],
            "type": "object",
        },
        "path": "/api/v1/operational/diversification_benefit_oprisk",
        "summary": "Diversification benefit across OpRisk cells under a single correlation.",
        "tool_name": "diversification_benefit_oprisk",
    },
    {
        "description": "Maps a loss amount to the highest governance tier whose threshold it meets "
        "or\n"
        'exceeds (e.g. ``{"team": 1e3, "head": 1e4, "exco": 1e5, "board": 1e6}``).\n'
        "\n"
        "This is a rule-based lookup: it selects the triggered tier with the\n"
        "numerically largest threshold value, not necessarily the dict's declared\n"
        '"highest" tier by name or insertion order, so it relies on ``thresholds``\n'
        "being ordered monotonically with severity.",
        "domain": "operational",
        "function_name": "escalation_threshold_calculation",
        "input_schema": {
            "properties": {"loss_amount": {"type": "number"}, "thresholds": {"type": "object"}},
            "required": ["loss_amount", "thresholds"],
            "type": "object",
        },
        "path": "/api/v1/operational/escalation_threshold_calculation",
        "summary": "Determine the escalation level for a loss against tiered thresholds.",
        "tool_name": "escalation_threshold_calculation",
    },
    {
        "description": "External (consortium / public) losses are scaled to the firm's size by a\n"
        "``scaling_factor`` (e.g. ratio of revenues) before being pooled with "
        "internal\n"
        "losses — the standard approach for enriching a sparse internal tail.",
        "domain": "operational",
        "function_name": "external_loss_data_integration",
        "input_schema": {
            "properties": {
                "external_losses": {"type": "object"},
                "internal_losses": {"type": "object"},
                "scaling_factor": {"type": "number"},
            },
            "required": ["internal_losses", "external_losses", "scaling_factor"],
            "type": "object",
        },
        "path": "/api/v1/operational/external_loss_data_integration",
        "summary": "Integrate scaled external loss data with internal data.",
        "tool_name": "external_loss_data_integration",
    },
    {
        "description": "The Poisson MLE for lambda is the sample mean of annual counts. Also "
        "reports\n"
        "the variance-to-mean ratio (dispersion) — a value far above 1 signals\n"
        "over-dispersion and a possible negative-binomial alternative.",
        "domain": "operational",
        "function_name": "frequency_distribution_fitting",
        "input_schema": {
            "properties": {"annual_event_counts": {"type": "object"}},
            "required": ["annual_event_counts"],
            "type": "object",
        },
        "path": "/api/v1/operational/frequency_distribution_fitting",
        "summary": "Fit a Poisson frequency distribution to annual loss-event counts.",
        "tool_name": "frequency_distribution_fitting",
    },
    {
        "description": "Recoverable amount = ``min(max(gross_loss − deductible, 0), "
        "policy_limit)``\n"
        "reduced by a supervisory haircut (Basel caps total insurance recognition "
        "at\n"
        "20% of capital and applies haircuts for residual term and payment\n"
        "uncertainty; the cap is applied by the caller).",
        "domain": "operational",
        "function_name": "insurance_offset_calculation",
        "input_schema": {
            "properties": {
                "deductible": {"type": "number"},
                "gross_loss": {"type": "number"},
                "haircut": {"default": 0.0, "type": "number"},
                "policy_limit": {"type": "number"},
            },
            "required": ["gross_loss", "policy_limit", "deductible"],
            "type": "object",
        },
        "path": "/api/v1/operational/insurance_offset_calculation",
        "summary": "Insurance mitigation offset for an operational loss.",
        "tool_name": "insurance_offset_calculation",
    },
    {
        "description": "Stronger internal controls (higher average effectiveness in [0, 1]) "
        "reduce\n"
        "the capital multiplier below 1.0; weaker controls increase it. The BEICF\n"
        "counterpart to :func:`business_environment_factor_bei`.",
        "domain": "operational",
        "function_name": "internal_control_factor_icf",
        "input_schema": {
            "properties": {
                "baseline": {"default": 0.8, "type": "number"},
                "control_scores": {"type": "object"},
                "sensitivity": {"default": 0.25, "type": "number"},
            },
            "required": ["control_scores"],
            "type": "object",
        },
        "path": "/api/v1/operational/internal_control_factor_icf",
        "summary": "Internal Control Factor (ICF) capital adjustment multiplier.",
        "tool_name": "internal_control_factor_icf",
    },
    {
        "description": "Blends system availability (fraction), incident frequency and patch\n"
        "compliance (fraction) into a 0-100 IT-risk score (higher = worse) with a "
        "RAG\n"
        "band.",
        "domain": "operational",
        "function_name": "it_risk_scoring",
        "input_schema": {
            "properties": {
                "availability": {"type": "number"},
                "incident_count": {"type": "number"},
                "patch_compliance": {"type": "number"},
            },
            "required": ["availability", "incident_count", "patch_compliance"],
            "type": "object",
        },
        "path": "/api/v1/operational/it_risk_scoring",
        "summary": "IT operational-risk score from availability, incidents and patching.",
        "tool_name": "it_risk_scoring",
    },
    {
        "description": "Each KRI definition must carry a ``name``, a numeric ``amber_threshold`` "
        "and\n"
        '``red_threshold``, and a ``direction`` (``"higher_breach"`` or\n'
        '``"lower_breach"``). Returns a validated registry keyed by name.\n'
        "\n"
        "This is a pure validation/indexing pass — it checks required keys and "
        "builds\n"
        "the keyed registry, with no numeric computation involved.",
        "domain": "operational",
        "function_name": "key_risk_indicator_kri_library",
        "input_schema": {
            "properties": {"kri_definitions": {"type": "array"}},
            "required": ["kri_definitions"],
            "type": "object",
        },
        "path": "/api/v1/operational/key_risk_indicator_kri_library",
        "summary": "Validate and index a KRI library.",
        "tool_name": "key_risk_indicator_kri_library",
    },
    {
        "description": "For ``higher_breach`` KRIs (higher = worse, e.g. failed trades) the value\n"
        "crosses amber then red as it rises; for ``lower_breach`` KRIs (lower = "
        "worse,\n"
        "e.g. staffing level) it crosses as it falls.\n"
        "\n"
        "For ``lower_breach`` every inequality above is reversed (red at or below "
        "the\n"
        "red threshold, amber between red and amber, green above amber).",
        "domain": "operational",
        "function_name": "kri_threshold_breach_detection",
        "input_schema": {
            "properties": {
                "amber_threshold": {"type": "number"},
                "direction": {"default": "higher_breach", "type": "string"},
                "red_threshold": {"type": "number"},
                "value": {"type": "number"},
            },
            "required": ["value", "amber_threshold", "red_threshold"],
            "type": "object",
        },
        "path": "/api/v1/operational/kri_threshold_breach_detection",
        "summary": "Classify a KRI value into a green/amber/red status.",
        "tool_name": "kri_threshold_breach_detection",
    },
    {
        "description": "Fits an OLS slope to the observation series and classifies the trend as\n"
        '``"deteriorating"``, ``"improving"`` or ``"stable"`` based on the slope '
        "sign\n"
        "and the metric direction.\n"
        "\n"
        '"Stable" is a scale-relative rule (``|slope| < 1e-4 * '
        "mean(|observations|)``),\n"
        "not a fixed absolute tolerance, and the deteriorating/improving call "
        "flips\n"
        "with ``higher_is_worse``.",
        "domain": "operational",
        "function_name": "kri_trend_analysis",
        "input_schema": {
            "properties": {
                "higher_is_worse": {"default": True, "type": "boolean"},
                "observations": {"type": "object"},
            },
            "required": ["observations"],
            "type": "object",
        },
        "path": "/api/v1/operational/kri_trend_analysis",
        "summary": "Linear-trend analysis of a KRI time series.",
        "tool_name": "kri_trend_analysis",
    },
    {
        "description": "Filters loss events at or above the firm's de-minimis reporting threshold "
        "and\n"
        "summarises count and total — the internal loss dataset feeding the LDA.",
        "domain": "operational",
        "function_name": "loss_data_collection_framework",
        "input_schema": {
            "properties": {
                "loss_events": {"type": "array"},
                "reporting_threshold": {"type": "number"},
            },
            "required": ["loss_events", "reporting_threshold"],
            "type": "object",
        },
        "path": "/api/v1/operational/loss_data_collection_framework",
        "summary": "Internal loss-data collection above a reporting threshold.",
        "tool_name": "loss_data_collection_framework",
    },
    {
        "description": "Fits the frequency (Poisson) and severity (lognormal) distributions from\n"
        "historical data, simulates the compound distribution and reads OpVaR /\n"
        "capital at the regulatory confidence — the full LDA pipeline in one call.\n"
        "\n"
        "This is a composed pipeline, not a single closed-form equation; "
        "``n_years``\n"
        "and ``seed`` only control the internal Monte Carlo simulation, not the\n"
        "capital figure itself.",
        "domain": "operational",
        "function_name": "loss_distribution_approach_lda",
        "input_schema": {
            "properties": {
                "annual_event_counts": {"type": "object"},
                "confidence_level": {"default": 0.999, "type": "number"},
                "loss_amounts": {"type": "object"},
                "n_years": {"default": 100000, "type": "integer"},
                "seed": {"default": 42, "type": "object"},
            },
            "required": ["annual_event_counts", "loss_amounts"],
            "type": "object",
        },
        "path": "/api/v1/operational/loss_distribution_approach_lda",
        "summary": "End-to-end Loss Distribution Approach capital estimate.",
        "tool_name": "loss_distribution_approach_lda",
    },
    {
        "description": "Validates the event type against the seven Basel II Level-1 categories\n"
        "(BCBS 128, Annex 9) and returns its ordinal index for downstream "
        "bucketing.\n"
        "\n"
        "This is a membership lookup against the fixed seven Basel II categories, "
        "not\n"
        "a numeric equation.",
        "domain": "operational",
        "function_name": "loss_event_classification_basel",
        "input_schema": {
            "properties": {"event_type": {"type": "string"}},
            "required": ["event_type"],
            "type": "object",
        },
        "path": "/api/v1/operational/loss_event_classification_basel",
        "summary": "Classify a loss event into a Basel II Level-1 event-type category.",
        "tool_name": "loss_event_classification_basel",
    },
    {
        "description": "Combines model materiality and complexity (1-5 each) into an inherent "
        "score,\n"
        "then discounts by validation quality (in [0, 1]) to a residual model-risk\n"
        "tier (SR 11-7 / PRA SS1/23 style).\n"
        "\n"
        "SR 11-7 / PRA SS1/23 are named only for the general materiality x "
        "complexity\n"
        "tiering style this follows; the specific 1-5 scale, multiplication, and "
        "RAG\n"
        "thresholds are pyvar's own, not values prescribed by either document.",
        "domain": "operational",
        "function_name": "model_risk_assessment",
        "input_schema": {
            "properties": {
                "complexity": {"type": "integer"},
                "materiality": {"type": "integer"},
                "validation_score": {"type": "number"},
            },
            "required": ["materiality", "complexity", "validation_score"],
            "type": "object",
        },
        "path": "/api/v1/operational/model_risk_assessment",
        "summary": "Model risk tier from materiality, complexity, and validation quality.",
        "tool_name": "model_risk_assessment",
    },
    {
        "description": "Builds the compound loss distribution and reads the loss quantile at the\n"
        "regulatory confidence (Basel AMA uses 99.9% over a one-year horizon). "
        "Capital\n"
        "is the unexpected loss = OpVaR minus expected loss.",
        "domain": "operational",
        "function_name": "monte_carlo_oprisk_capital",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.999, "type": "number"},
                "frequency_lambda": {"type": "number"},
                "n_years": {"default": 100000, "type": "integer"},
                "seed": {"default": 42, "type": "object"},
                "severity_mu": {"type": "number"},
                "severity_sigma": {"type": "number"},
            },
            "required": ["frequency_lambda", "severity_mu", "severity_sigma"],
            "type": "object",
        },
        "path": "/api/v1/operational/monte_carlo_oprisk_capital",
        "summary": "Monte Carlo OpRisk regulatory capital (OpVaR + expected shortfall).",
        "tool_name": "monte_carlo_oprisk_capital",
    },
    {
        "description": "A near-miss is an event with zero actual loss but a non-zero potential "
        "loss.\n"
        "Validates events and summarises the count and aggregate potential loss — "
        "a\n"
        "leading indicator of control weakness.\n"
        "\n"
        "This is a rule-based filter/count over ``events``; ``actual_loss`` and\n"
        "``potential_loss`` are per-event dict keys rather than top-level function\n"
        "parameters.",
        "domain": "operational",
        "function_name": "near_miss_capture_framework",
        "input_schema": {
            "properties": {"events": {"type": "array"}},
            "required": ["events"],
            "type": "object",
        },
        "path": "/api/v1/operational/near_miss_capture_framework",
        "summary": "Summarise captured near-miss events.",
        "tool_name": "near_miss_capture_framework",
    },
    {
        "description": "Reads the loss quantile at the confidence level directly from a supplied\n"
        "(e.g. simulated or historical) annual-loss array — the generic OpVaR "
        "reader.",
        "domain": "operational",
        "function_name": "operational_var_opvar",
        "input_schema": {
            "properties": {
                "annual_losses": {"type": "object"},
                "confidence_level": {"default": 0.999, "type": "number"},
            },
            "required": ["annual_losses"],
            "type": "object",
        },
        "path": "/api/v1/operational/operational_var_opvar",
        "summary": "Operational VaR from an empirical aggregate-loss sample.",
        "tool_name": "operational_var_opvar",
    },
    {
        "description": "Distributes the firm-wide capital to business lines in proportion to "
        "their\n"
        "standalone risk contributions, so the allocations sum exactly to the total "
        "—\n"
        "a coherent (additive) allocation.",
        "domain": "operational",
        "function_name": "oprisk_capital_allocation",
        "input_schema": {
            "properties": {
                "business_line_risks": {"type": "object"},
                "total_capital": {"type": "number"},
            },
            "required": ["total_capital", "business_line_risks"],
            "type": "object",
        },
        "path": "/api/v1/operational/oprisk_capital_allocation",
        "summary": "Allocate total OpRisk capital across business lines (pro-rata by risk).",
        "tool_name": "oprisk_capital_allocation",
    },
    {
        "description": "Economic capital is the unexpected loss (OpVaR − expected loss) reduced "
        "by\n"
        "recognised risk mitigants (insurance recoveries and diversification), "
        "floored\n"
        "at zero.",
        "domain": "operational",
        "function_name": "oprisk_economic_capital",
        "input_schema": {
            "properties": {
                "diversification_benefit": {"default": 0.0, "type": "number"},
                "expected_loss": {"type": "number"},
                "insurance_offset": {"default": 0.0, "type": "number"},
                "opvar": {"type": "number"},
            },
            "required": ["opvar", "expected_loss"],
            "type": "object",
        },
        "path": "/api/v1/operational/oprisk_economic_capital",
        "summary": "OpRisk economic capital (unexpected loss net of mitigants).",
        "tool_name": "oprisk_economic_capital",
    },
    {
        "description": "Buckets each (likelihood, impact) risk into the 5×5 grid and computes the\n"
        "score (likelihood × impact) and RAG band for each, plus a count matrix of\n"
        "risks per cell.",
        "domain": "operational",
        "function_name": "oprisk_heat_map_generator",
        "input_schema": {
            "properties": {"impacts": {"type": "object"}, "likelihoods": {"type": "object"}},
            "required": ["likelihoods", "impacts"],
            "type": "object",
        },
        "path": "/api/v1/operational/oprisk_heat_map_generator",
        "summary": "Generate a 5×5 OpRisk heat-map distribution.",
        "tool_name": "oprisk_heat_map_generator",
    },
    {
        "description": "Projects stressed capital by scaling the base capital for shocks to event\n"
        "frequency and severity. Because aggregate loss scales (approximately)\n"
        "multiplicatively in both drivers, stressed capital =\n"
        "``base × (1 + freq_shock) × (1 + sev_shock)``.",
        "domain": "operational",
        "function_name": "oprisk_stress_testing",
        "input_schema": {
            "properties": {
                "base_capital": {"type": "number"},
                "frequency_shock": {"type": "number"},
                "severity_shock": {"type": "number"},
            },
            "required": ["base_capital", "frequency_shock", "severity_shock"],
            "type": "object",
        },
        "path": "/api/v1/operational/oprisk_stress_testing",
        "summary": "OpRisk stress-testing capital projection.",
        "tool_name": "oprisk_stress_testing",
    },
    {
        "description": "Combines design effectiveness (is the control well-designed?) and "
        "operating\n"
        "effectiveness (does it operate as intended?) into a single [0, 1] score "
        "via a\n"
        "weighted average.",
        "domain": "operational",
        "function_name": "rcsa_control_effectiveness",
        "input_schema": {
            "properties": {
                "design_score": {"type": "number"},
                "design_weight": {"default": 0.4, "type": "number"},
                "operating_score": {"type": "number"},
            },
            "required": ["design_score", "operating_score"],
            "type": "object",
        },
        "path": "/api/v1/operational/rcsa_control_effectiveness",
        "summary": "Composite control effectiveness from design and operating effectiveness.",
        "tool_name": "rcsa_control_effectiveness",
    },
    {
        "description": "Inherent risk is the gross exposure before controls: ``likelihood × "
        "impact``\n"
        "on the 1-5 scale, giving a 1-25 score mapped to a RAG band.",
        "domain": "operational",
        "function_name": "rcsa_inherent_risk_scoring",
        "input_schema": {
            "properties": {"impact": {"type": "integer"}, "likelihood": {"type": "integer"}},
            "required": ["likelihood", "impact"],
            "type": "object",
        },
        "path": "/api/v1/operational/rcsa_inherent_risk_scoring",
        "summary": "Inherent risk score on the 5×5 RCSA heat map.",
        "tool_name": "rcsa_inherent_risk_scoring",
    },
    {
        "description": "Residual = ``inherent × (1 − control_effectiveness)``: effective controls\n"
        "reduce the inherent score toward zero. The residual is mapped to a RAG "
        "band.",
        "domain": "operational",
        "function_name": "rcsa_residual_risk_scoring",
        "input_schema": {
            "properties": {
                "control_effectiveness": {"type": "number"},
                "inherent_score": {"type": "number"},
            },
            "required": ["inherent_score", "control_effectiveness"],
            "type": "object",
        },
        "path": "/api/v1/operational/rcsa_residual_risk_scoring",
        "summary": "Residual risk after control mitigation.",
        "tool_name": "rcsa_residual_risk_scoring",
    },
    {
        "description": "Checks each risk entry exposes a ``risk_id`` and a Basel ``category`` and\n"
        "summarises counts by category — the identification step of the RCSA "
        "cycle.\n"
        "\n"
        "This is validation plus a count-by-category aggregation, not a numeric\n"
        "formula; ``category`` is a per-entry dict key rather than a top-level\n"
        "function parameter.",
        "domain": "operational",
        "function_name": "rcsa_risk_identification",
        "input_schema": {
            "properties": {"risk_register": {"type": "array"}},
            "required": ["risk_register"],
            "type": "object",
        },
        "path": "/api/v1/operational/rcsa_risk_identification",
        "summary": "Validate and summarise an RCSA risk register.",
        "tool_name": "rcsa_risk_identification",
    },
    {
        "description": "Computes the weighted fraction of regulatory requirements met (each 0 = "
        "not\n"
        "met, 1 = met, or a partial value in between) as a 0-100 compliance score "
        "with\n"
        "a RAG band.",
        "domain": "operational",
        "function_name": "regulatory_compliance_score",
        "input_schema": {
            "properties": {"requirements_met": {"type": "object"}, "weights": {"type": "object"}},
            "required": ["requirements_met"],
            "type": "object",
        },
        "path": "/api/v1/operational/regulatory_compliance_score",
        "summary": "Weighted regulatory-compliance score.",
        "tool_name": "regulatory_compliance_score",
    },
    {
        "description": "Maps a metric to ``within_appetite`` / ``within_tolerance`` / ``breach``\n"
        "against a two-tier limit structure: appetite (the desired ceiling) and\n"
        "tolerance (the absolute maximum before escalation).\n"
        "\n"
        "When ``higher_is_worse=False`` every inequality is reversed and "
        "utilisation\n"
        "is computed as ``tolerance_limit / current_metric`` rather than the\n"
        "``current_metric / tolerance_limit`` used in the higher-is-worse case.",
        "domain": "operational",
        "function_name": "risk_appetite_statement_oprisk",
        "input_schema": {
            "properties": {
                "appetite_limit": {"type": "number"},
                "current_metric": {"type": "number"},
                "higher_is_worse": {"default": True, "type": "boolean"},
                "tolerance_limit": {"type": "number"},
            },
            "required": ["current_metric", "appetite_limit", "tolerance_limit"],
            "type": "object",
        },
        "path": "/api/v1/operational/risk_appetite_statement_oprisk",
        "summary": "Assess an OpRisk metric against appetite and tolerance limits.",
        "tool_name": "risk_appetite_statement_oprisk",
    },
    {
        "description": "Normalises the supplied causal-factor weights (e.g. people, process,\n"
        "systems, external) to sum to 1 and identifies the dominant root cause — "
        "the\n"
        "quantitative backbone of an RCA template.",
        "domain": "operational",
        "function_name": "root_cause_analysis_template",
        "input_schema": {
            "properties": {"causal_factors": {"type": "object"}},
            "required": ["causal_factors"],
            "type": "object",
        },
        "path": "/api/v1/operational/root_cause_analysis_template",
        "summary": "Aggregate root-cause contributions into a normalised attribution.",
        "tool_name": "root_cause_analysis_template",
    },
    {
        "description": "Builds a single scenario's aggregate annual loss distribution from its\n"
        "calibrated frequency and lognormal severity and reads the loss quantile —\n"
        "the scenario's contribution to capital. Per RULE 3 randomness is "
        "pre-drawn\n"
        "in pure Python.",
        "domain": "operational",
        "function_name": "scenario_analysis_oprisk",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.999, "type": "number"},
                "frequency_lambda": {"type": "number"},
                "n_years": {"default": 50000, "type": "integer"},
                "seed": {"default": 42, "type": "object"},
                "severity_mu": {"type": "number"},
                "severity_sigma": {"type": "number"},
            },
            "required": ["frequency_lambda", "severity_mu", "severity_sigma"],
            "type": "object",
        },
        "path": "/api/v1/operational/scenario_analysis_oprisk",
        "summary": "Scenario-based OpRisk capital via a compound Monte Carlo.",
        "tool_name": "scenario_analysis_oprisk",
    },
    {
        "description": "Combines multiple experts' point estimates into a weighted consensus and\n"
        "reports the dispersion (weighted standard deviation) as a confidence proxy "
        "—\n"
        "wide disagreement signals an unreliable scenario.",
        "domain": "operational",
        "function_name": "scenario_expert_elicitation_model",
        "input_schema": {
            "properties": {
                "expert_estimates": {"type": "object"},
                "expert_weights": {"type": "object"},
            },
            "required": ["expert_estimates"],
            "type": "object",
        },
        "path": "/api/v1/operational/scenario_expert_elicitation_model",
        "summary": "Aggregate expert loss estimates into a consensus with dispersion.",
        "tool_name": "scenario_expert_elicitation_model",
    },
    {
        "description": "Uses the expert's expected events per year directly, or — if historical\n"
        "occurrence data is supplied — the empirical rate ``occurrences /\n"
        "observation_years``. The result is the Poisson lambda feeding the "
        "scenario's\n"
        "compound loss.",
        "domain": "operational",
        "function_name": "scenario_frequency_estimation",
        "input_schema": {
            "properties": {
                "expected_events_per_year": {"type": "number"},
                "observation_years": {"type": "object"},
                "occurrences": {"type": "object"},
            },
            "required": ["expected_events_per_year"],
            "type": "object",
        },
        "path": "/api/v1/operational/scenario_frequency_estimation",
        "summary": "Estimate a scenario's annual frequency (Poisson lambda).",
        "tool_name": "scenario_frequency_estimation",
    },
    {
        "description": "Treats ``typical_loss`` as the lognormal median (so ``mu = ln(typical)``) "
        "and\n"
        "solves for ``sigma`` from the worst-case percentile:\n"
        "``sigma = (ln(worst) − mu) / z_p``. This is the standard two-point expert\n"
        "calibration for scenario severities.",
        "domain": "operational",
        "function_name": "scenario_severity_estimation",
        "input_schema": {
            "properties": {
                "typical_loss": {"type": "number"},
                "worst_case_loss": {"type": "number"},
                "worst_case_percentile": {"default": 0.99, "type": "number"},
            },
            "required": ["typical_loss", "worst_case_loss"],
            "type": "object",
        },
        "path": "/api/v1/operational/scenario_severity_estimation",
        "summary": "Calibrate a lognormal severity from expert typical / worst-case losses.",
        "tool_name": "scenario_severity_estimation",
    },
    {
        "description": "Supports four standard OpRisk severity families, all fit by maximum\n"
        "likelihood with the location parameter pinned at zero (severities are\n"
        "strictly positive, so a free location would let the MLE drift away from\n"
        "the actual support):\n"
        "\n"
        '- ``"lognormal"`` (default, the OpRisk industry standard): closed-form '
        "MLE\n"
        "  of the log-loss mean/sigma, i.e. ``scipy.stats.lognorm.fit(x, floc=0)``\n"
        "  reparameterised as ``mu = log(scale)``, ``sigma = shape``.\n"
        '- ``"gamma"``: ``scipy.stats.gamma.fit(x, floc=0)`` — shape ``a`` and\n'
        "  ``scale``; commonly used for moderate, right-skewed severities.\n"
        '- ``"weibull"``: ``scipy.stats.weibull_min.fit(x, floc=0)`` — shape ``c``\n'
        "  and ``scale``; flexible hazard shape, another standard severity choice.\n"
        '- ``"gpd"`` (Generalized Pareto Distribution): '
        "``scipy.stats.genpareto.fit(\n"
        "  x, floc=0)`` — shape ``xi`` and ``scale``; the standard EVT/POT model "
        "for\n"
        "  the tail of large losses (threshold-exceedance modelling). The mean is\n"
        "  only finite for ``xi < 1``; when ``xi >= 1`` ``mean_severity`` is\n"
        "  ``None`` rather than a misleading infinite/negative value.\n"
        "\n"
        "Any other ``distribution`` value raises ``ValueError`` rather than "
        "falling\n"
        "back or approximating.",
        "domain": "operational",
        "function_name": "severity_distribution_fitting",
        "input_schema": {
            "properties": {
                "distribution": {"default": "lognormal", "type": "string"},
                "loss_amounts": {"type": "object"},
            },
            "required": ["loss_amounts"],
            "type": "object",
        },
        "path": "/api/v1/operational/severity_distribution_fitting",
        "summary": "Fit a severity distribution to individual loss amounts.",
        "tool_name": "severity_distribution_fitting",
    },
    {
        "description": "Stresses the extreme tail by scaling losses beyond the tail quantile by a\n"
        '``severity_multiplier`` (e.g. a "perfect-storm" amplification) and '
        "re-reading\n"
        "the stressed tail expectation. Reports the uplift over the unstressed "
        "tail.",
        "domain": "operational",
        "function_name": "tail_risk_scenario_oprisk",
        "input_schema": {
            "properties": {
                "annual_losses": {"type": "object"},
                "severity_multiplier": {"default": 1.0, "type": "number"},
                "tail_confidence": {"default": 0.999, "type": "number"},
            },
            "required": ["annual_losses"],
            "type": "object",
        },
        "path": "/api/v1/operational/tail_risk_scenario_oprisk",
        "summary": "Tail-risk scenario capital uplift for OpRisk.",
        "tool_name": "tail_risk_scenario_oprisk",
    },
    {
        "description": "Weighted index of vendor criticality (1-5), inverse financial health,\n"
        "concentration and inverse substitutability — all normalised to a 0-100 "
        "score\n"
        "(higher = worse).",
        "domain": "operational",
        "function_name": "third_party_vendor_risk",
        "input_schema": {
            "properties": {
                "concentration": {"type": "number"},
                "criticality": {"type": "integer"},
                "financial_health": {"type": "number"},
                "substitutability": {"type": "number"},
            },
            "required": ["criticality", "financial_health", "concentration", "substitutability"],
            "type": "object",
        },
        "path": "/api/v1/operational/third_party_vendor_risk",
        "summary": "Third-party / vendor risk score.",
        "tool_name": "third_party_vendor_risk",
    },
    {
        "description": "``0.5 * sum(|w_i - b_i|)``; 0 means identical to benchmark, 1 means fully\n"
        "differentiated (Cremers & Petajisto).",
        "domain": "portfolio",
        "function_name": "active_share",
        "input_schema": {
            "properties": {"benchmark_weights": {"type": "object"}, "weights": {"type": "object"}},
            "required": ["weights", "benchmark_weights"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/active_share",
        "summary": "Active share — fraction of holdings differing from the benchmark.",
        "tool_name": "active_share",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "average_drawdown",
        "input_schema": {
            "properties": {
                "is_equity_curve": {"default": False, "type": "boolean"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/average_drawdown",
        "summary": "Average drawdown — mean of the drawdown series magnitude.",
        "tool_name": "average_drawdown",
    },
    {
        "description": "Combines the CAPM-implied equilibrium returns ``Π = λ Σ w_mkt`` with\n"
        "investor views ``P E[r] = Q`` to produce posterior expected returns and "
        "the\n"
        "corresponding mean-variance weights.",
        "domain": "portfolio",
        "function_name": "black_litterman_model",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "market_weights": {"type": "object"},
                "omega": {"type": "object"},
                "p_matrix": {"type": "object"},
                "q_views": {"type": "object"},
                "risk_aversion": {"default": 2.5, "type": "number"},
                "tau": {"default": 0.05, "type": "number"},
            },
            "required": ["market_weights", "cov_matrix", "p_matrix", "q_views"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/black_litterman_model",
        "summary": "Black-Litterman posterior expected returns and weights.",
        "tool_name": "black_litterman_model",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "calmar_ratio",
        "input_schema": {
            "properties": {
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/calmar_ratio",
        "summary": "Calmar ratio — annualised return over maximum drawdown.",
        "tool_name": "calmar_ratio",
    },
    {
        "description": "Computes the Weighted Average Carbon Intensity (WACI) -- this leg matches\n"
        "TCFD's WACI definition regardless of mode.\n"
        "\n"
        "By default (``company_total_emissions``/``company_value`` omitted,\n"
        "unchanged prior behaviour) ``total_financed_emissions`` scales\n"
        "revenue-intensity by invested value per holding, which does NOT match\n"
        "the ownership-share method used by the TCFD/PCAF financed-emissions\n"
        "standards.\n"
        "\n"
        "Supplying BOTH ``company_total_emissions`` (each holding's investee\n"
        "company's total absolute Scope 1+2 emissions, tCO2e) and\n"
        "``company_value`` (each company's total enterprise value -- PCAF's EVIC,\n"
        "enterprise value including cash, or market cap -- same currency unit as\n"
        "``portfolio_value``) switches to the PCAF ownership-share method\n"
        '(Partnership for Carbon Accounting Financials, "The Global GHG\n'
        'Accounting and Reporting Standard for the Financial Industry", Part A,\n'
        "2020; the same method TCFD's 2017 recommendations point to for financed\n"
        "emissions):\n"
        "\n"
        "    ownership_share_i = invested_i / company_value_i\n"
        "    financed_emissions_i = ownership_share_i * company_total_emissions_i\n"
        "\n"
        "where ``invested_i = weights_i * portfolio_value`` is the investor's\n"
        "outstanding amount in company i. Unlike the default (revenue-intensity\n"
        "x invested-value) leg, this correctly represents \"the investor's\n"
        "proportional share of the company's own total emissions\" rather than an\n"
        "intensity-scaled quantity with no ownership interpretation -- an\n"
        "investor's ownership share can never legitimately attribute more than\n"
        "the company's own total emissions (verified in tests).",
        "domain": "portfolio",
        "function_name": "carbon_footprint_attribution",
        "input_schema": {
            "properties": {
                "asset_names": {"type": "object"},
                "carbon_intensities": {"type": "object"},
                "company_total_emissions": {"type": "object"},
                "company_value": {"type": "object"},
                "portfolio_value": {"type": "number"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "carbon_intensities", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/carbon_footprint_attribution",
        "summary": "Carbon footprint attribution (WACI and financed emissions).",
        "tool_name": "carbon_footprint_attribution",
    },
    {
        "description": "Extends Fama-French 3-factor with the momentum (WML/MOM) factor.",
        "domain": "portfolio",
        "function_name": "carhart_4_factor_model",
        "input_schema": {
            "properties": {"excess_returns": {"type": "object"}, "factors": {"type": "object"}},
            "required": ["excess_returns", "factors"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/carhart_4_factor_model",
        "summary": "Carhart 4-factor regression (MKT, SMB, HML, MOM).",
        "tool_name": "carhart_4_factor_model",
    },
    {
        "description": "``HHI = sum(w_i^2)`` on absolute weights normalised to sum to 1. Ranges "
        "from\n"
        "``1/n`` (equal weight) to 1 (single holding). The effective number of\n"
        "holdings is ``1/HHI``.",
        "domain": "portfolio",
        "function_name": "concentration_risk_hhi",
        "input_schema": {
            "properties": {"weights": {"type": "object"}},
            "required": ["weights"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/concentration_risk_hhi",
        "summary": "Concentration risk via the Herfindahl-Hirschman Index (HHI).",
        "tool_name": "concentration_risk_hhi",
    },
    {
        "description": "The mean of the worst ``(1 - confidence_level)`` fraction of drawdowns —\n"
        "the drawdown analogue of Expected Shortfall (Chekhlov, Uryasev, "
        "Zabarankin).",
        "domain": "portfolio",
        "function_name": "conditional_drawdown_at_risk",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.95, "type": "number"},
                "is_equity_curve": {"default": False, "type": "boolean"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/conditional_drawdown_at_risk",
        "summary": "Conditional Drawdown at Risk (CDaR).",
        "tool_name": "conditional_drawdown_at_risk",
    },
    {
        "description": "Builds the correlation distance ``sqrt(2(1 - rho))`` and performs\n"
        "single-linkage agglomerative clustering down to ``n_clusters`` groups —\n"
        "grouping assets that co-move.\n"
        "\n"
        "The merge itself is delegated to ``scipy.cluster.hierarchy.linkage``\n"
        "(``method='single'``) followed by ``fcluster(..., criterion='maxclust')``\n"
        "rather than a hand-rolled merge loop; this is the same single-linkage\n"
        "algorithm (repeatedly merge the two clusters whose minimum pairwise\n"
        "distance is smallest), just computed by SciPy's tested implementation.\n"
        "Cluster *membership* is therefore identical to the earlier hand-rolled\n"
        "version — only the arbitrary integer cluster-id labelling can differ.",
        "domain": "portfolio",
        "function_name": "correlation_clustering",
        "input_schema": {
            "properties": {
                "n_clusters": {"default": 2, "type": "integer"},
                "returns_matrix": {"type": "object"},
            },
            "required": ["returns_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/correlation_clustering",
        "summary": "Correlation-based clustering of assets.",
        "tool_name": "correlation_clustering",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "correlation_matrix_portfolio",
        "input_schema": {
            "properties": {"returns_matrix": {"type": "object"}},
            "required": ["returns_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/correlation_matrix_portfolio",
        "summary": "Correlation matrix and average pairwise correlation of asset returns.",
        "tool_name": "correlation_matrix_portfolio",
    },
    {
        "description": "By default (``local_risk_free``/``base_risk_free`` omitted, unchanged\n"
        "prior behaviour) this splits the base-currency return into a\n"
        "local-market component and a currency (FX) component per holding,\n"
        "weighted by exposure, via the geometric identity\n"
        "``base = (1+local)(1+fx)-1`` with currency as the residual. This naive\n"
        'split is NOT Karnosky-Singer -- see Bacon, C. (2008), "Practical\n'
        'Portfolio Performance Measurement and Attribution", 2nd ed., Ch. 6,\n'
        "which presents it as the baseline before introducing Karnosky-Singer.\n"
        "\n"
        "Supplying BOTH ``local_risk_free`` (per-holding local-currency\n"
        "risk-free/cash rate) and ``base_risk_free`` (the reporting/base\n"
        "currency's own risk-free rate) switches to Karnosky & Singer's (1994)\n"
        'genuine decomposition ("The Currency Dimension of Global Asset\n'
        'Management and Performance Attribution", CFA Institute Research\n'
        "Foundation): local returns are first netted against the *local*\n"
        "risk-free rate into a local return PREMIUM (the market-selection\n"
        "component the currency side must not re-capture), and the currency\n"
        "side is split into the base cash return and a currency SURPRISE --\n"
        "the currency return net of the covered-interest-parity forward\n"
        "premium implied by the two risk-free rates -- rather than absorbing\n"
        "the interest-rate differential as an unexplained residual:\n"
        "\n"
        "    premium_i = (1+local_i)/(1+local_rf_i) - 1\n"
        "    forward_premium_i = (1+base_rf)/(1+local_rf_i) - 1   (covered interest "
        "parity)\n"
        "    surprise_i = (1+fx_i)/(1+forward_premium_i) - 1\n"
        "\n"
        "These combine via the exact geometric identity\n"
        "``(1+base_rf)(1+premium_i)(1+surprise_i) = (1+local_i)(1+fx_i)`` -- i.e.\n"
        "Karnosky-Singer re-partitions the *same* total base-currency return\n"
        "used by the naive split, it does not change it (verified in tests).\n"
        "The ``currency_effect`` bucket is further broken into\n"
        "``base_cash_effect`` (``base_rf``, common to every holding),\n"
        "``currency_surprise_effect`` (``surprise_i``) and a small\n"
        "``currency_interaction_effect`` residual capturing the compounding\n"
        "cross-terms between the three multiplicative legs -- the same\n"
        "reconciling-residual pattern :func:`return_attribution_brinson` uses\n"
        "for its own interaction effect, so the three currency sub-effects sum\n"
        "exactly to ``currency_effect`` (which itself sums with ``local_effect``\n"
        "to ``total_return``, as before).",
        "domain": "portfolio",
        "function_name": "currency_attribution",
        "input_schema": {
            "properties": {
                "base_risk_free": {"type": "object"},
                "currency_names": {"type": "object"},
                "fx_returns": {"type": "object"},
                "local_returns": {"type": "object"},
                "local_risk_free": {"type": "object"},
                "weights": {"type": "object"},
            },
            "required": ["local_returns", "fx_returns", "weights"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/currency_attribution",
        "summary": "Currency attribution -- naive geometric split, or genuine Karnosky-Singer.",
        "tool_name": "currency_attribution",
    },
    {
        "description": "Maximises expected return subject to the portfolio CVaR (at\n"
        "``confidence_level``) not exceeding ``cvar_limit``, long-only and fully\n"
        "invested. CVaR is computed empirically over the supplied scenarios.\n"
        "\n"
        "Solved via Rockafellar & Uryasev's (2000) original auxiliary-variable\n"
        "linear-programming reformulation, not a direct nonlinear CVaR\n"
        "constraint. Introduce an auxiliary VaR estimate ``zeta`` and one\n"
        "non-negative excess-loss variable ``u_s`` per scenario, then solve the\n"
        "convex LP\n"
        "\n"
        "    minimize    -mu^T w\n"
        "    subject to  sum(w) = 1,  0 <= w_i <= 1\n"
        "                zeta + (1/(S(1-alpha))) * sum_s u_s <= cvar_limit\n"
        "                u_s >= -(scenario_s . w) - zeta,   u_s >= 0   (s=1..S)\n"
        "\n"
        "via ``scipy.optimize.linprog`` (HiGHS). CVaR is a convex function of\n"
        "``w`` and both this LP and the retired SLSQP-on-empirical-CVaR\n"
        "formulation share the same feasible region and the same (convex)\n"
        "objective, so they solve to the same global optimum — the LP just gets\n"
        "there via Rockafellar-Uryasev's exact reformulation instead of SLSQP\n"
        "re-evaluating the empirical quantile/tail-mean at every iterate.",
        "domain": "portfolio",
        "function_name": "cvar_constrained_optimisation",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.95, "type": "number"},
                "cvar_limit": {"default": 0.05, "type": "number"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "scenario_returns": {"type": "object"},
            },
            "required": ["scenario_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/cvar_constrained_optimisation",
        "summary": "CVaR-constrained portfolio optimisation (Rockafellar-Uryasev).",
        "tool_name": "cvar_constrained_optimisation",
    },
    {
        "description": "``(w' σ) / sqrt(w' Σ w)`` where ``σ`` is the vector of asset "
        "volatilities.\n"
        "Always >= 1; higher means more diversification benefit (Choueifaty).",
        "domain": "portfolio",
        "function_name": "diversification_ratio",
        "input_schema": {
            "properties": {"cov_matrix": {"type": "object"}, "weights": {"type": "object"}},
            "required": ["weights", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/diversification_ratio",
        "summary": "Diversification ratio — weighted average vol over portfolio vol.",
        "tool_name": "diversification_ratio",
    },
    {
        "description": "Counts consecutive periods spent below the prior peak.",
        "domain": "portfolio",
        "function_name": "drawdown_duration",
        "input_schema": {
            "properties": {
                "is_equity_curve": {"default": False, "type": "boolean"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/drawdown_duration",
        "summary": "Drawdown duration — longest and current underwater run lengths.",
        "tool_name": "drawdown_duration",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "equal_weight_portfolio",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "n_assets": {"type": "integer"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["n_assets"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/equal_weight_portfolio",
        "summary": "Equal-weight (1/N) portfolio.",
        "tool_name": "equal_weight_portfolio",
    },
    {
        "description": "Computes the weighted-average portfolio ESG score. If ``min_esg_score`` "
        "and\n"
        "a covariance matrix are supplied, solves a minimum-variance long-only\n"
        "portfolio subject to the weighted ESG score meeting the floor.",
        "domain": "portfolio",
        "function_name": "esg_score_integration",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "esg_scores": {"type": "object"},
                "min_esg_score": {"type": "object"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "esg_scores"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/esg_score_integration",
        "summary": "ESG score integration — weighted score and optional ESG-constrained tilt.",
        "tool_name": "esg_score_integration",
    },
    {
        "description": "Builds the asset covariance from a factor model\n"
        "``Σ = B F Bᵀ + diag(specific_var)`` and finds the long-only "
        "fully-invested\n"
        "minimum-variance portfolio, optionally matching ``target_exposures`` to "
        "the\n"
        "factors via an equality constraint.",
        "domain": "portfolio",
        "function_name": "factor_based_optimisation",
        "input_schema": {
            "properties": {
                "factor_cov": {"type": "object"},
                "factor_exposures": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "specific_var": {"type": "object"},
                "target_exposures": {"type": "object"},
            },
            "required": ["factor_exposures", "factor_cov", "specific_var"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/factor_based_optimisation",
        "summary": "Factor-based minimum-risk optimisation.",
        "tool_name": "factor_based_optimisation",
    },
    {
        "description": "Aggregates per-asset factor loadings into portfolio-level exposures\n"
        "``Bᵀ w`` — the active/absolute factor tilts of the portfolio.",
        "domain": "portfolio",
        "function_name": "factor_exposure_analysis_barra",
        "input_schema": {
            "properties": {
                "asset_exposures": {"type": "object"},
                "factor_names": {"type": "object"},
                "weights": {"type": "object"},
            },
            "required": ["asset_exposures", "weights"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/factor_exposure_analysis_barra",
        "summary": "Barra-style portfolio factor exposure.",
        "tool_name": "factor_exposure_analysis_barra",
    },
    {
        "description": "Decomposes the realised portfolio return into per-factor contributions\n"
        "``exposure_i * factor_return_i`` plus a specific (idiosyncratic) "
        "component.",
        "domain": "portfolio",
        "function_name": "factor_return_attribution",
        "input_schema": {
            "properties": {
                "factor_exposures": {"type": "object"},
                "factor_names": {"type": "object"},
                "factor_returns": {"type": "object"},
                "specific_return": {"type": "number"},
            },
            "required": ["factor_exposures", "factor_returns", "specific_return"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/factor_return_attribution",
        "summary": "Factor return attribution.",
        "tool_name": "factor_return_attribution",
    },
    {
        "description": "Regresses portfolio excess returns on the market, size (SMB) and value\n"
        "(HML) factors. The intercept is the factor alpha.",
        "domain": "portfolio",
        "function_name": "fama_french_3_factor_model",
        "input_schema": {
            "properties": {"excess_returns": {"type": "object"}, "factors": {"type": "object"}},
            "required": ["excess_returns", "factors"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/fama_french_3_factor_model",
        "summary": "Fama-French 3-factor regression (MKT, SMB, HML).",
        "tool_name": "fama_french_3_factor_model",
    },
    {
        "description": "Adds profitability (RMW) and investment (CMA) factors to the 3-factor "
        "model.",
        "domain": "portfolio",
        "function_name": "fama_french_5_factor_model",
        "input_schema": {
            "properties": {"excess_returns": {"type": "object"}, "factors": {"type": "object"}},
            "required": ["excess_returns", "factors"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/fama_french_5_factor_model",
        "summary": "Fama-French 5-factor regression (MKT, SMB, HML, RMW, CMA).",
        "tool_name": "fama_french_5_factor_model",
    },
    {
        "description": "Aggregates position weights into GICS sector buckets and reports each\n"
        "sector's share of the portfolio. Shares sum to the total invested weight.",
        "domain": "portfolio",
        "function_name": "gics_sector_exposure",
        "input_schema": {
            "properties": {"sector_codes": {"type": "array"}, "weights": {"type": "object"}},
            "required": ["weights", "sector_codes"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/gics_sector_exposure",
        "summary": "GICS sector exposure aggregation.",
        "tool_name": "gics_sector_exposure",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "information_ratio",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/information_ratio",
        "summary": "Information ratio — active return over tracking error.",
        "tool_name": "information_ratio",
    },
    {
        "description": "``alpha = mean(r - rf) - beta * mean(b - rf)`` per period; annualised by\n"
        "multiplication by ``periods_per_year``.",
        "domain": "portfolio",
        "function_name": "jensens_alpha",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/jensens_alpha",
        "summary": "Jensen's alpha from the CAPM single-factor regression.",
        "tool_name": "jensens_alpha",
    },
    {
        "description": "Adds a liquidity cost term equal to half the weighted bid-ask spread to "
        "the\n"
        "parametric delta-normal VaR (Bangia-Diebold-Schuermann simplified "
        "add-on),\n"
        "capturing the cost of unwinding positions.",
        "domain": "portfolio",
        "function_name": "liquidity_adjusted_portfolio_var",
        "input_schema": {
            "properties": {
                "bid_ask_spreads": {"type": "object"},
                "confidence_level": {"default": 0.99, "type": "number"},
                "cov_matrix": {"type": "object"},
                "horizon_days": {"default": 1, "type": "integer"},
                "portfolio_value": {"type": "number"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "cov_matrix", "bid_ask_spreads", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/liquidity_adjusted_portfolio_var",
        "summary": "Liquidity-adjusted parametric VaR (LVaR).",
        "tool_name": "liquidity_adjusted_portfolio_var",
    },
    {
        "description": "Marginal contribution ``(Σw)_i / sigma_p``; component ``w_i * "
        "marginal_i``.\n"
        "Component contributions sum exactly to the portfolio volatility (Euler).",
        "domain": "portfolio",
        "function_name": "marginal_contribution_to_risk",
        "input_schema": {
            "properties": {"cov_matrix": {"type": "object"}, "weights": {"type": "object"}},
            "required": ["weights", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/marginal_contribution_to_risk",
        "summary": "Marginal and component contribution to portfolio volatility risk.",
        "tool_name": "marginal_contribution_to_risk",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "maximum_drawdown",
        "input_schema": {
            "properties": {
                "is_equity_curve": {"default": False, "type": "boolean"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/maximum_drawdown",
        "summary": "Maximum drawdown — largest peak-to-trough decline.",
        "tool_name": "maximum_drawdown",
    },
    {
        "description": "Maximises the annualised Sharpe ratio subject to weights summing to 1.",
        "domain": "portfolio",
        "function_name": "maximum_sharpe_ratio_portfolio",
        "input_schema": {
            "properties": {
                "allow_short": {"default": False, "type": "boolean"},
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["mean_returns", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/maximum_sharpe_ratio_portfolio",
        "summary": "Maximum Sharpe ratio (tangency) portfolio.",
        "tool_name": "maximum_sharpe_ratio_portfolio",
    },
    {
        "description": "Maximises ``w'μ - 0.5 * λ * w'Σw`` subject to weights summing to 1, with "
        "an\n"
        "optional long-only constraint.",
        "domain": "portfolio",
        "function_name": "mean_variance_optimisation",
        "input_schema": {
            "properties": {
                "allow_short": {"default": False, "type": "boolean"},
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_aversion": {"default": 1.0, "type": "number"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["mean_returns", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/mean_variance_optimisation",
        "summary": "Mean-variance (Markowitz) optimisation.",
        "tool_name": "mean_variance_optimisation",
    },
    {
        "description": "Minimises ``w'Σw`` subject to weights summing to 1. With shorting allowed\n"
        "the closed-form solution ``Σ⁻¹1 / (1'Σ⁻¹1)`` is used; long-only uses "
        "SLSQP.",
        "domain": "portfolio",
        "function_name": "minimum_variance_portfolio",
        "input_schema": {
            "properties": {
                "allow_short": {"default": False, "type": "boolean"},
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/minimum_variance_portfolio",
        "summary": "Global minimum-variance portfolio.",
        "tool_name": "minimum_variance_portfolio",
    },
    {
        "description": "Draws correlated multivariate-normal asset returns (RULE 3: pre-drawn in\n"
        "pure Python via Cholesky), compounds them over the horizon in a JIT "
        "kernel,\n"
        "and reports the simulated VaR / ES of terminal P&L.",
        "domain": "portfolio",
        "function_name": "monte_carlo_portfolio_simulation",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "cov_matrix": {"type": "object"},
                "horizon": {"default": 10, "type": "integer"},
                "mean_returns": {"type": "object"},
                "n_simulations": {"default": 10000, "type": "integer"},
                "portfolio_value": {"default": 1000000.0, "type": "number"},
                "seed": {"default": 12345, "type": "integer"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "mean_returns", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/monte_carlo_portfolio_simulation",
        "summary": "Monte Carlo portfolio simulation of terminal P&L.",
        "tool_name": "monte_carlo_portfolio_simulation",
    },
    {
        "description": "``Omega = sum(max(r - threshold, 0)) / sum(max(threshold - r, 0))``.",
        "domain": "portfolio",
        "function_name": "omega_ratio",
        "input_schema": {
            "properties": {
                "returns": {"type": "object"},
                "threshold": {"default": 0.0, "type": "number"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/omega_ratio",
        "summary": "Omega ratio — probability-weighted gains over losses about a threshold.",
        "tool_name": "omega_ratio",
    },
    {
        "description": "``beta = cov(r, b) / var(b)``.",
        "domain": "portfolio",
        "function_name": "portfolio_beta",
        "input_schema": {
            "properties": {"benchmark_returns": {"type": "object"}, "returns": {"type": "object"}},
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/portfolio_beta",
        "summary": "Portfolio beta — sensitivity of portfolio returns to the benchmark.",
        "tool_name": "portfolio_beta",
    },
    {
        "description": "``0.5 * sum(|w_after - w_before|)`` (one-way convention).",
        "domain": "portfolio",
        "function_name": "portfolio_turnover",
        "input_schema": {
            "properties": {
                "weights_after": {"type": "object"},
                "weights_before": {"type": "object"},
            },
            "required": ["weights_before", "weights_after"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/portfolio_turnover",
        "summary": "Portfolio turnover — one-way traded fraction between two weight vectors.",
        "tool_name": "portfolio_turnover",
    },
    {
        "description": "Eigendecomposes the covariance matrix to extract orthogonal principal\n"
        "components ordered by explained variance.",
        "domain": "portfolio",
        "function_name": "principal_component_analysis",
        "input_schema": {
            "properties": {
                "n_components": {"type": "object"},
                "returns_matrix": {"type": "object"},
            },
            "required": ["returns_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/principal_component_analysis",
        "summary": "Principal Component Analysis of an asset return matrix.",
        "tool_name": "principal_component_analysis",
    },
    {
        "description": "Computes the trades to move from current to target weights, suppressing\n"
        "trades within a no-trade band to avoid churn, and reports turnover and\n"
        "total transaction cost.\n"
        "\n"
        "By default ``no_trade_band`` is a single user-supplied absolute weight\n"
        "threshold applied uniformly to every asset (unchanged prior behaviour).\n"
        "Supplying both ``asset_volatility`` and ``risk_aversion`` instead\n"
        "*derives* a per-asset band from the classic Constantinides (1986) /\n"
        "Davis & Norman (1990) asymptotic no-trade-region half-width — the\n"
        "closed-form cube-root result that Leland's (1999) mean-variance\n"
        "tracking-error approximation and Donohue & Yip's (2003) practitioner\n"
        "rebalancing-band heuristic both build on:\n"
        "\n"
        "    h_i = ( (3/4) * c_i * sigma_i^2 * w_i^tgt * (1 - w_i^tgt)^2 / gamma "
        ")^(1/3)\n"
        "\n"
        "where ``c_i`` is the proportional transaction cost (``cost_bps_i /\n"
        "1e4``), ``sigma_i`` is asset i's return volatility, ``w_i^tgt`` is asset\n"
        "i's target weight (the frictionless-optimal allocation the band is\n"
        "centred on) and ``gamma`` is the investor's (CRRA) risk-aversion\n"
        "coefficient. The half-width widens with cost and volatility (cube-root\n"
        "scaling) and narrows as risk aversion rises — more risk-averse investors\n"
        "tolerate less drift before trading. This is the classic single-risky-\n"
        "asset asymptotic result applied per-asset; it is not a reproduction of\n"
        "Leland's or Donohue & Yip's own published numerical examples (no\n"
        "published table was available to cross-check exact figures against).\n"
        "\n"
        "When the derived-band mode is used, it *replaces* the scalar\n"
        "``no_trade_band`` for that call rather than combining with it; when\n"
        "either ``asset_volatility`` or ``risk_aversion`` is omitted, behaviour\n"
        "is unchanged — the scalar ``no_trade_band`` is used exactly as before.",
        "domain": "portfolio",
        "function_name": "rebalancing_optimiser",
        "input_schema": {
            "properties": {
                "asset_volatility": {"type": "object"},
                "cost_bps": {"type": "object"},
                "current_weights": {"type": "object"},
                "no_trade_band": {"default": 0.0, "type": "number"},
                "risk_aversion": {"type": "object"},
                "target_weights": {"type": "object"},
            },
            "required": ["current_weights", "target_weights", "cost_bps"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/rebalancing_optimiser",
        "summary": "Rebalancing optimiser with a no-trade band.",
        "tool_name": "rebalancing_optimiser",
    },
    {
        "description": "Note: despite the name, this fits a stationary 2-component Gaussian\n"
        "mixture (EM, i.i.d. weights) — there is no transition matrix, so it does\n"
        "not model true HMM regime persistence/switching dynamics.\n"
        "\n"
        "Fits a two-component Gaussian mixture by EM and labels each observation "
        "by\n"
        "its most likely regime. The higher-variance component is reported as the\n"
        '"stress" regime — the standard calm/turbulent market characterisation.',
        "domain": "portfolio",
        "function_name": "regime_detection_hmm",
        "input_schema": {
            "properties": {
                "n_iter": {"default": 50, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/regime_detection_hmm",
        "summary": "Two-state Gaussian regime detection via EM.",
        "tool_name": "regime_detection_hmm",
    },
    {
        "description": "Bootstraps return samples from the estimated multivariate-normal, solves "
        "the\n"
        "minimum-variance long-only portfolio on each resample, and averages the\n"
        "weights — reducing estimation-error sensitivity. All randomness is "
        "pre-drawn\n"
        "in pure Python (RULE 3).",
        "domain": "portfolio",
        "function_name": "resampled_efficient_frontier",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "n_obs": {"default": 250, "type": "integer"},
                "n_resamples": {"default": 50, "type": "integer"},
                "seed": {"default": 2024, "type": "integer"},
            },
            "required": ["mean_returns", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/resampled_efficient_frontier",
        "summary": "Resampled efficient frontier (Michaud) minimum-variance point.",
        "tool_name": "resampled_efficient_frontier",
    },
    {
        "description": "Regresses portfolio returns on the benchmark (CAPM) and reports the\n"
        "standard deviation of the residuals — the risk not explained by beta.",
        "domain": "portfolio",
        "function_name": "residual_risk",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/residual_risk",
        "summary": "Residual (idiosyncratic) risk — volatility of single-factor regression "
        "residuals.",
        "tool_name": "residual_risk",
    },
    {
        "description": "Decomposes the active return into allocation, selection and interaction\n"
        "effects per segment. The three effects sum exactly to the total active\n"
        "return — the reconciliation property required for performance reporting.",
        "domain": "portfolio",
        "function_name": "return_attribution_brinson",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "benchmark_weights": {"type": "object"},
                "portfolio_returns": {"type": "object"},
                "portfolio_weights": {"type": "object"},
                "segment_names": {"type": "object"},
            },
            "required": [
                "portfolio_weights",
                "benchmark_weights",
                "portfolio_returns",
                "benchmark_returns",
            ],
            "type": "object",
        },
        "path": "/api/v1/portfolio/return_attribution_brinson",
        "summary": "Brinson-Hood-Beebower return attribution.",
        "tool_name": "return_attribution_brinson",
    },
    {
        "description": "Finds long-only weights so each asset contributes equally to portfolio\n"
        "variance, by minimising the dispersion of risk contributions.\n"
        "\n"
        "Dispersion is measured as the sum of squared pairwise differences\n"
        "between all assets' risk contributions rather than each asset's\n"
        "deviation from the mean contribution -- a stronger gradient signal for\n"
        "SLSQP that converges to the same equal-risk-contribution solution.",
        "domain": "portfolio",
        "function_name": "risk_parity_portfolio",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/risk_parity_portfolio",
        "summary": "Equal risk contribution (risk parity) portfolio.",
        "tool_name": "risk_parity_portfolio",
    },
    {
        "description": "Uses the worst-case expected return ``μ - κ·diag(Σ)^{1/2}`` within an\n"
        "ellipsoidal/box uncertainty set (Tütüncü-Koenig style), then solves the\n"
        "standard mean-variance problem — producing more conservative weights.",
        "domain": "portfolio",
        "function_name": "robust_portfolio_optimisation",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_aversion": {"default": 1.0, "type": "number"},
                "uncertainty": {"default": 0.05, "type": "number"},
            },
            "required": ["mean_returns", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/robust_portfolio_optimisation",
        "summary": "Robust mean-variance optimisation with a box uncertainty set on means.",
        "tool_name": "robust_portfolio_optimisation",
    },
    {
        "description": "A thin specialisation of :func:`return_attribution_brinson` where "
        "segments\n"
        "are GICS sectors. Allocation+selection+interaction reconcile to the "
        "active\n"
        "return.",
        "domain": "portfolio",
        "function_name": "sector_attribution",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "benchmark_weights": {"type": "object"},
                "portfolio_returns": {"type": "object"},
                "portfolio_weights": {"type": "object"},
                "sector_names": {"type": "object"},
            },
            "required": [
                "portfolio_weights",
                "benchmark_weights",
                "portfolio_returns",
                "benchmark_returns",
            ],
            "type": "object",
        },
        "path": "/api/v1/portfolio/sector_attribution",
        "summary": "Sector attribution — Brinson allocation/selection grouped by sector.",
        "tool_name": "sector_attribution",
    },
    {
        "description": "Mean excess return divided by return volatility, annualised by\n"
        "``sqrt(periods_per_year)``.\n"
        "\n"
        "By default (``ddof=0``, unchanged from prior behaviour) volatility is the\n"
        "*population* standard deviation (divide by n) of per-period excess\n"
        "returns. Pass ``ddof=1`` to use the *sample* standard deviation (divide\n"
        "by n-1) instead — the usual unbiased-estimator convention when\n"
        "``returns`` is treated as a sample drawn from a larger population. The\n"
        "``n``-vs-``n-1`` divisor only matters materially for small samples; for\n"
        "the sample sizes typical of return series (hundreds+ of observations)\n"
        "the two converge.",
        "domain": "portfolio",
        "function_name": "sharpe_ratio",
        "input_schema": {
            "properties": {
                "ddof": {"default": 0, "type": "integer"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/sharpe_ratio",
        "summary": "Annualised Sharpe ratio.",
        "tool_name": "sharpe_ratio",
    },
    {
        "description": "Like Sharpe but penalises only downside deviation below ``target``, so\n"
        "upside volatility is not treated as risk.\n"
        "\n"
        "The numerator's excess return is measured against ``risk_free`` while\n"
        "the downside-deviation denominator measures shortfalls of the raw (not\n"
        "risk-free-adjusted) returns below the separate ``target``, so when\n"
        "``target != risk_free`` the two are distinct reference rates by\n"
        "construction.",
        "domain": "portfolio",
        "function_name": "sortino_ratio",
        "input_schema": {
            "properties": {
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
                "risk_free": {"default": 0.0, "type": "number"},
                "target": {"default": 0.0, "type": "number"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/sortino_ratio",
        "summary": "Annualised Sortino ratio.",
        "tool_name": "sortino_ratio",
    },
    {
        "description": "``|quantile(1 - tail)| / |quantile(tail)|``. A value above 1 indicates "
        "the\n"
        "right (gain) tail is larger than the left (loss) tail.",
        "domain": "portfolio",
        "function_name": "tail_ratio",
        "input_schema": {
            "properties": {
                "returns": {"type": "object"},
                "tail": {"default": 0.05, "type": "number"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/tail_ratio",
        "summary": "Tail ratio — magnitude of the right tail relative to the left tail.",
        "tool_name": "tail_ratio",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "tracking_error",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/tracking_error",
        "summary": "Tracking error — volatility of active (portfolio minus benchmark) return.",
        "tool_name": "tracking_error",
    },
    {
        "description": "Computes per-trade slippage against an arrival/VWAP benchmark and the\n"
        "quantity-weighted average slippage in basis points. ``side`` is +1 for\n"
        "buys (paying above benchmark is a cost) and -1 for sells.\n"
        "\n"
        "By default (``decision_price`` omitted, unchanged prior behaviour) this\n"
        "is narrower than Perold's (1988) full implementation-shortfall\n"
        "decomposition -- it measures only execution slippage against the\n"
        "``benchmark_prices`` (arrival/VWAP), with no delay-cost leg.\n"
        "\n"
        "Passing ``decision_price`` -- the price at the instant the investment\n"
        'decision was made, Perold\'s "paper" price, distinct from the\n'
        "arrival/VWAP ``benchmark_prices`` used for execution slippage -- adds\n"
        "the delay-cost leg: the cost incurred between the decision and the\n"
        "order reaching the market (``benchmark_prices``), *before* any\n"
        "execution slippage is measured. Delay cost and execution slippage sum\n"
        "exactly to the executed-quantity implementation shortfall measured\n"
        "directly against the decision price:\n"
        "``delay_cost + total_cost == sum(side * (trade_prices - decision_price)\n"
        "* trade_quantities)``. This still omits Perold's unexecuted-share\n"
        "opportunity-cost leg (no cancellation price/quantity is modelled here),\n"
        "so even with ``decision_price`` supplied the result is a delay+\n"
        "execution partial IS, not the complete four-component decomposition.",
        "domain": "portfolio",
        "function_name": "transaction_cost_analysis",
        "input_schema": {
            "properties": {
                "benchmark_prices": {"type": "object"},
                "decision_price": {"type": "object"},
                "side": {"default": 1, "type": "integer"},
                "trade_prices": {"type": "object"},
                "trade_quantities": {"type": "object"},
            },
            "required": ["trade_prices", "benchmark_prices", "trade_quantities"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/transaction_cost_analysis",
        "summary": "Transaction Cost Analysis (TCA) — implementation shortfall vs benchmark.",
        "tool_name": "transaction_cost_analysis",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "treynor_ratio",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/treynor_ratio",
        "summary": "Treynor ratio — annualised excess return per unit of systematic risk (beta).",
        "tool_name": "treynor_ratio",
    },
    {
        "description": "A depth-and-duration-sensitive risk measure: deeper, longer drawdowns are\n"
        "penalised quadratically.",
        "domain": "portfolio",
        "function_name": "ulcer_index",
        "input_schema": {
            "properties": {
                "is_equity_curve": {"default": False, "type": "boolean"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/ulcer_index",
        "summary": "Ulcer Index — root-mean-square of percentage drawdowns from peak.",
        "tool_name": "ulcer_index",
    },
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

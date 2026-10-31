---
name: pyvar-liquidity-risk
description: >
  Run pyvar's 40 liquidity-risk functions on the live pyvar.com API: LCR and NSFR, HQLA
  classification, cash-flow ladders, stress scenarios, survival horizon, intraday liquidity,
  funding concentration and liquidity VaR. Use when the user wants liquidity ratios or stress
  results computed rather than only explained. Needs a free pyvar API key; the skill explains
  how to get one.
version: "1.2.0"
author: "Fibtec Limited — pyvar.com"
tags: [liquidity-risk, LCR, NSFR, HQLA, cash-flow, ILAAP, survival-horizon, funding-risk, intraday, stress-test]
---

# pyvar — Liquidity Risk  (40 functions)

Liquidity-risk calculations: regulatory ratios (LCR/NSFR), HQLA, cash-flow ladders, stress scenarios, survival horizon, intraday and funding metrics. Pick the function in **Functions** below; the **Worked examples** show the request shape.

## Before you call anything

This skill is a guide to the **live pyvar.com API**. It computes nothing by itself, and every
function needs the user's pyvar API key. Don't substitute your own numpy/scipy code and present
the result as pyvar output: these are regulatory-grade functions and the user wants pyvar's own
numbers.

The key is the user's to hold. Never look for it on their machine (environment variables, files,
shell history, other tools' settings), and don't ask them to paste it into the chat.

1. **Call through the pyvar MCP server.** The `pyvar-mcp` plugin asks the user for the key once,
   when they enable it, and keeps it in the system's secure credential store; its tools attach it
   to every call, so you never handle it. Use
   `call_pyvar_function(domain="liquidity", function_name="<function>", params=body)` with the
   request body below (every example in this skill is a real, tested request), and
   `list_pyvar_functions` to browse.
2. **No pyvar tools available? Say so, and walk the user through setting them up** (free, about
   a minute). First, get a key: open https://www.pyvar.com#get-api-key, then either click "Sign in with Google" (when
   it is shown) or enter an email and click the link we send (single use; the same form signs
   returning users in). The dashboard opens with a first API key already created: a string
   starting `pyvar_`, shown once. A key lasts a year and can be revoked or replaced on the
   dashboard at any time. Then install the `pyvar-mcp` plugin (the `/plugin` Discover tab, or
   `/plugin install pyvar-mcp@pyvar-marketplace`); Claude Code asks for the key when it is
   enabled. On a `401 Invalid, revoked or expired API key`, send the user back to the dashboard to
   create a new one.
3. **Cannot use MCP, or cannot run code or reach the network** (for example a sandbox with no
   internet)? Give the user the exact request to run themselves, with their own key where the
   placeholder is, instead of guessing a result:
   - Python: `pip install pyvar-client`, then
     `Client(api_key="<your pyvar key>").liquidity_risk.<function>(**body)`.
   - REST: `POST https://www.pyvar.com/api/v1/liquidity/<function>` with header
     `Authorization: Bearer <your pyvar key>` and the body as JSON.
4. **Read the response.** Every function returns one JSON object. Quote the key numbers together
   with the inputs you used (and units: rates and returns are decimals, so 0.02 means 2%).

Errors: `401` bad or expired key; `422` a parameter is wrong (the `detail` field names it: fix it
and retry, never resend the same body); `429` the daily quota is used up (free tier: 10 calls per
day across all pyvar functions; the `Retry-After` header is in seconds): tell the user instead of
retrying in a loop.

## Worked examples

Each request body below is the same set of keyword arguments for the Python client, the REST body and the MCP `params`. They were run against the real API.

### 1. LCR and NSFR against the 100% minimum

Any one currency unit throughout. LCR is HQLA over net outflows over 30 days (inflows capped at 75% of outflows); NSFR is available over required stable funding. Both are compliant at 1.0 or above.

`POST /api/v1/liquidity/liquidity_coverage_ratio_lcr`

```json
{
  "hqla": 1200000000,
  "gross_outflows": 1000000000,
  "gross_inflows": 300000000
}
```

Returns: `lcr`, `net_outflows`, `capped_inflows`, `hqla`, `compliant`.

`POST /api/v1/liquidity/net_stable_funding_ratio_nsfr`

```json
{
  "available_stable_funding": 9500000000,
  "required_stable_funding": 9000000000
}
```

Returns: `nsfr`, `asf`, `rsf`, `compliant`.

### 2. Survival horizon under a stressed outflow path

How many full days the liquidity buffer lasts when net outflows accelerate. The horizon is the last day on which the cumulative net outflow is still covered.

`POST /api/v1/liquidity/survival_horizon_calculator`

```json
{
  "hqla": 500,
  "daily_net_outflows": [40, 60, 80, 100, 100, 90, 80, 70, 60, 50]
}
```

Returns: `survival_days`, `terminal_buffer`, `hqla`.

## Functions (40)

Every function is `POST /api/v1/liquidity/<name>`. Required parameters are listed bare, optional ones with their defaults (`name=default`). Types, bounds and formulas are in `references/functions.md`, in this plugin's folder: read the entry before calling a function you have not used yet.

### Regulatory Ratios (LCR/NSFR)

- `liquidity_coverage_ratio_lcr(hqla, gross_outflows, gross_inflows, inflow_cap=0.75)`: Basel III Liquidity Coverage Ratio.
  Note: Outflows are floored so recognised inflows can offset at most 75% of gross outflows (BCBS 238 §69, the default `inflow_cap`). compliant = (LCR >= 1.0).
- `net_stable_funding_ratio_nsfr(available_stable_funding, required_stable_funding)`: Basel III Net Stable Funding Ratio.
- `available_stable_funding_asf_calc(funding_amounts, asf_factors)`: Available Stable Funding for the NSFR numerator.
- `required_stable_funding_rsf_calc(asset_amounts, rsf_factors)`: Required Stable Funding for the NSFR denominator.

### Intraday Liquidity

(Moved out of the LCR/NSFR group above — these are BCBS 248 intraday
monitoring functions, not LCR/NSFR calculations.)

- `intraday_liquidity_monitor(timestamps, net_flows, opening_balance)`: Intraday liquidity monitor (BCBS 248).
  Note: Negative cumulative position — BCBS 248's actual "daily maximum intraday liquidity usage" tool) AND `max_usage` (drop below opening balance). Only `net_debit_peak` is the genuine BCBS 248 figure — `max_usage` is an internal metric and the two diverge whenever the balance path never actually goes negative.
- `intraday_liquidity_stress_test(net_flows, opening_balance, delay_factor=0.5, inflow_delay_shock=0.0)`: Intraday liquidity stress test (BCBS 248 stress scenarios).
  Note: Delays a fraction of inflows (`delay_factor`); an internal stress design, not a specific BCBS 248 prescribed scenario.

### HQLA Classification

- `hqla_level_1_asset_classifier(asset_values, haircuts=None)`: Classify and value Level 1 HQLA.
- `hqla_level_2a_asset_classifier(asset_values, haircut=0.15)`: Classify and value Level 2A HQLA.
  Note: Regulatory minimum haircut (BCBS 238 §52)
- `hqla_level_2b_asset_classifier(asset_values, haircut=0.25)`: Classify and value Level 2B HQLA.
  regulatory minimum haircut (BCBS 238 §54); pass haircut=0.50 for the lower-grade-corporate/equity sub-bucket

  **Composition caps are not enforced by any function.** BCBS 238 §46-§47 caps
  Level 2 assets at <= 40% of total HQLA and Level 2B at <= 15% of total HQLA.
  These thresholds exist as constants in `engine/liquidity_ratios.py` but no
  function combines the three classifiers' output and checks them — callers
  must sum the three `post_haircut_value` results themselves and apply the
  40%/15% checks.

### Cash Flow Ladder

- `cash_flow_ladder_30_day(daily_inflows, daily_outflows, opening_balance=0.0)`: 30-day daily contractual cash-flow ladder.
- `cash_flow_ladder_1_year(bucket_inflows, bucket_outflows, opening_balance=0.0, buckets=None)`: One-year bucketed contractual cash-flow ladder.
- `liquidity_gap_analysis(asset_maturities, liability_maturities, buckets=None)`: Maturity-bucket liquidity gap (assets vs liabilities).

### Stress Scenarios

- `liquidity_stress_scenario(balances, runoff_rates, hqla, inflows=0.0)`: Generic single liquidity stress scenario.
- `idiosyncratic_stress_scenario(retail_deposits, wholesale_funding, hqla, retail_runoff=0.1, wholesale_runoff=1.0)`: Idiosyncratic (name-specific) stress scenario.
- `market_wide_stress_scenario(hqla_by_level, market_haircuts, outflow)`: Market-wide stress scenario.
- `combined_stress_scenario(retail_deposits, wholesale_funding, hqla_by_level, market_haircuts, retail_runoff=0.15, wholesale_runoff=1.0, inflows=0.0, retail_deposits_by_category=None, retail_runoff_rates=None)`: Combined idiosyncratic + market-wide stress scenario.
  Note: Combined Stress Scenario. NOT the Basel/EBA reference combined scenario: BCBS 238's own version runs off the LCR's regulator-set 3%/5%/10% retail run-off categories, not this function's flat 15% default (`retail_runoff`), which is an internal convention. The "combined deficit never better than market-wide alone" ordering property still holds regardless.

### Buffer & Survival

- `liquidity_buffer_sizing(stressed_net_outflows, confidence_buffer=0.0)`: Size the liquidity buffer to the peak cumulative stressed outflow.
- `contingency_funding_plan_trigger(metrics, thresholds)`: Evaluate Contingency Funding Plan (CFP) activation triggers.
- `wholesale_funding_concentration(counterparty_amounts)`: Wholesale funding concentration via the Herfindahl-Hirschman Index.
- `survival_horizon_calculator(hqla, daily_net_outflows)`: Survival horizon — days until cumulative net outflow exhausts HQLA.

### Funding Risk

- `retail_deposit_runoff_rate(deposit_balances, runoff_rates)`: Aggregate retail deposit run-off (Basel LCR categories).
- `secured_funding_rollover_risk(maturing_amounts, rollover_rates)`: Secured funding (repo) rollover risk.
- `asset_encumbrance_ratio(encumbered_assets, total_assets)`: Asset encumbrance ratio (EBA reporting).
- `collateral_availability_analysis(collateral_values, haircuts, already_pledged=None)`: Collateral availability — post-haircut monetisable value.
- `repo_market_stress_haircut(base_haircuts, stress_multipliers, collateral_values)`: Repo market stress — incremental margin call from widened haircuts.
- `fx_liquidity_risk_by_currency(inflows_by_ccy, outflows_by_ccy)`: FX liquidity risk — net position per significant currency.
- `intragroup_liquidity_flow(entity_positions)`: Intragroup liquidity flow netting.
- `funding_cost_analysis(funding_amounts, funding_rates)`: Weighted-average funding cost.
- `deposit_stability_classification(deposit_features, stable_threshold=0.5)`: Classify deposits as stable vs less-stable from a stability score.

### Internal Liquidity Metrics

- `liquidity_transfer_pricing(notional, tenor_years, base_rate, liquidity_spread, contingent_spread=0.0)`: Liquidity Transfer Pricing (LTP) charge for a funding position.
- `ilaap_internal_liquidity_metric(counterbalancing_capacity, stressed_net_outflow, survival_days, minimum_survival_days=90.0)`: ILAAP internal liquidity adequacy metric.
- `ilaap_stress_testing_framework(scenarios)`: ILAAP stress-testing framework aggregator.
- `liquidity_risk_appetite_threshold(metric_value, green_threshold, amber_threshold, higher_is_better=True)`: Map a liquidity metric to a RAG (red/amber/green) risk-appetite zone.
- `early_warning_indicator_liquidity(indicators, thresholds, directions=None)`: Liquidity early-warning indicator (EWI) dashboard.
- `central_bank_facility_eligibility(asset_ratings, min_rating, asset_values, cb_haircuts)`: Central-bank facility collateral eligibility and borrowing capacity.
- `contingent_liquidity_risk(commitment_amounts, draw_probabilities, ccf=None)`: Contingent liquidity risk from undrawn commitments and guarantees.

### Advanced Liquidity Analytics

- `liquidity_var_liqvar(base_outflow, outflow_vol, confidence_level=0.99, n_simulations=100000, seed=42)`: Liquidity VaR (LiqVaR) by Monte Carlo simulation of stressed net outflows.
- `funding_tenor_analysis(funding_amounts, tenors_days)`: Weighted-average funding tenor and short-term reliance.
- `liquidity_scorecard_aggregation(scores, weights)`: Weighted liquidity scorecard aggregation.
- `cross_currency_liquidity_bridge(shortfall_ccy, shortfall_amount, surplus_ccy, surplus_amount, fx_rate, swap_haircut=0.0)`: Cross-currency liquidity bridge via FX swap.

## Regulatory basis

Only a subset of these 40 functions implement a published, checkable Basel/EBA
formula; the rest are internally reasonable conventions with no regulator
worked example to validate against. This split is documented and enforced
(with `[closed-form, BCBS ...]` / `[independent hand-calc]` tags per test) in
`tests/validation/test_liquidity_ref.py`. Summary:

- **Regulator-sourced closed forms**: `liquidity_coverage_ratio_lcr`,
  `net_stable_funding_ratio_nsfr`, `available_stable_funding_asf_calc`,
  `required_stable_funding_rsf_calc`, the three `hqla_level_*_asset_classifier`
  functions (BCBS 238 §46-§54), `retail_deposit_runoff_rate`,
  `asset_encumbrance_ratio` (EBA), `wholesale_funding_concentration` (HHI —
  a standard competition-economics measure, not a Basel-specific one), and
  `intraday_liquidity_monitor`'s `net_debit_peak` field only (BCBS 248).
- **Internal conventions, tagged `[independent hand-calc]` in the validation
  suite** (BCBS 238/248/295 and EBA ILAAP guidelines checked directly, no
  source found): the cash-flow ladder and gap/tenor functions,
  `survival_horizon_calculator`, `liquidity_buffer_sizing`,
  `contingency_funding_plan_trigger`, `secured_funding_rollover_risk`,
  `collateral_availability_analysis`, `repo_market_stress_haircut`,
  `fx_liquidity_risk_by_currency`, `intragroup_liquidity_flow`,
  `funding_cost_analysis`, `liquidity_transfer_pricing`, and everything under
  Internal Liquidity Metrics / Advanced Liquidity Analytics above except
  `liquidity_var_liqvar`, plus `combined_stress_scenario` and
  `intraday_liquidity_monitor`'s `max_usage` field (see callouts above).
  `contingent_liquidity_risk` and `central_bank_facility_eligibility` have
  partial parameter-level leads (BCBS 238 §131 committed-facility drawdown
  rates; ECB/BoE collateral haircut schedules) not yet incorporated.
- **Cross-validated, not regulator-sourced**: `liquidity_var_liqvar` — its
  `liqvar` (Monte Carlo) is checked against `liqvar_analytic` (closed-form
  normal quantile via scipy), not against a regulatory reference.
## Naming convention
- Ratios returned as decimal (1.15 = 115%)
- Time buckets: overnight, 1w, 2w, 1m, 3m, 6m, 1y, >1y
- Stress scenarios: "idiosyncratic" | "market_wide" | "combined"
## For contributors: dependencies
numpy >= 1.24 · pandas >= 2.0 · polars >= 0.19

## For contributors: architecture context
- **Compute**: NumPy (cash flow aggregation), Polars (large ladder datasets)
- **Queue**: Celery (daily LCR/NSFR batch)
- **Storage**: Redis (intraday monitor), PostgreSQL (regulatory ratios)
- **API**: FastAPI endpoint `/api/v1/liquidity-risk/{function}`

---

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

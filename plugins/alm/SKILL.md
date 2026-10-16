---
name: pyvar-alm
description: >
  Run pyvar's 33 ALM and balance-sheet functions on the live pyvar.com API: duration gap, NII
  and EVE simulation, the six BCBS IRRBB shocks, repricing gap, non-maturity deposit and
  prepayment models, funds transfer pricing. Use when the user wants
  interest-rate-risk-in-the-banking-book numbers computed rather than only explained. Needs a
  free pyvar API key; the skill explains how to get one.
version: "1.1.0"
author: "Fibtec Limited — pyvar.com"
tags: [ALM, NII, EVE, IRRBB, duration, repricing-gap, NMD, prepayment, FTP, convexity, basis-risk, pipeline-risk, balance-sheet, ICAAP]
---

# pyvar — ALM and Balance Sheet  (33 functions)

ALM calculations: duration and repricing gaps, NII and EVE sensitivity, the IRRBB standardised framework, behavioural models and funds transfer pricing. Pick the function in **Functions** below; the **Worked examples** show the request shape.

## Before you call anything

This skill is a guide to the **live pyvar.com API**. It computes nothing by itself, and every
function needs a pyvar API key. Don't substitute your own numpy/scipy code and present the result
as pyvar output: these are regulatory-grade functions and the user wants pyvar's own numbers.

1. **Find the key.** Look for `PYVAR_API_KEY` in the environment. If the pyvar MCP server is
   connected, its tools (`call_pyvar_function`, `list_pyvar_functions`) already carry the key.
2. **No key? Say so, and walk the user through getting one** (free, about a minute): open
   https://www.pyvar.com#get-api-key, then either click "Sign in with Google" (when it is shown) or enter an email and
   click the link we send (single use; the same form signs returning users in). The dashboard
   opens with a first API key already created: a string starting `pyvar_`, shown once. Ask the
   user to copy it and set `PYVAR_API_KEY`. A key lasts a year and can be revoked or replaced on
   the dashboard at any time. On a `401 Invalid, revoked or expired API key`, send the user back
   to the dashboard to create a new one.
3. **Call the function** with the request body below (every example in this skill is a real,
   tested request). Use whichever of these is available:
   - Python: `pip install pyvar-client`, then
     `Client(api_key=os.environ["PYVAR_API_KEY"]).alm.<function>(**body)`.
   - REST: `POST https://www.pyvar.com/api/v1/alm/<function>` with header
     `Authorization: Bearer $PYVAR_API_KEY` and the body as JSON.
   - MCP: `call_pyvar_function(domain="alm", function_name="<function>", params=body)`.
   If you cannot run code or reach the network (for example a sandbox with no internet), give the
   user the exact `curl` command or Python snippet to run themselves instead of guessing a result.
4. **Read the response.** Every function returns one JSON object. Quote the key numbers together
   with the inputs you used (and units: rates and returns are decimals, so 0.02 means 2%).

Errors: `401` bad or expired key; `422` a parameter is wrong (the `detail` field names it: fix it
and retry, never resend the same body); `429` the daily quota is used up (free tier: 10 calls per
day across all pyvar functions; the `Retry-After` header is in seconds): tell the user instead of
retrying in a loop.

## Worked examples

Each request body below is the same set of keyword arguments for the Python client, the REST body and the MCP `params`. They were run against the real API.

### 1. Duration gap and repricing gap on one balance sheet

The duration gap converts a parallel rate shock into an equity impact; the repricing gap shows the per-bucket asset and liability mismatch that drives NII.

`POST /api/v1/alm/duration_gap_analysis`

```json
{
  "asset_duration": 4.2,
  "liability_duration": 2.1,
  "total_assets": 1000000000,
  "total_liabilities": 920000000,
  "rate_shock": 0.01
}
```

Returns: `duration_gap`, `leverage_adjusted_gap`, `delta_eve`, `equity`.

`POST /api/v1/alm/repricing_gap_analysis`

```json
{
  "bucket_assets": [120, 200, 260, 220, 200],
  "bucket_liabilities": [300, 220, 180, 150, 150],
  "bucket_labels": ["0-3m", "3-12m", "1-3y", "3-5y", "5y+"]
}
```

Returns: `gap`, `cumulative_gap`, `total_gap`.

### 2. The six BCBS IRRBB rate shocks

The standardised shock vectors for a tenor grid: parallel up/down, short up/down, steepener and flattener. Feed them to the EVE and NII functions.

`POST /api/v1/alm/irrbb_six_standard_rate_shocks`

```json
{
  "tenors": [0.25, 1, 2, 5, 10, 20],
  "parallel_bps": 200,
  "short_bps": 300,
  "long_bps": 150
}
```

Returns: `parallel_up`, `parallel_down`, `steepener`, `flattener`, `short_up`, `short_down`.

## Functions (33)

Every function is `POST /api/v1/alm/<name>`. Required parameters are listed bare, optional ones with their defaults (`name=default`). Types, bounds and formulas are in [references/functions.md](references/functions.md): read the entry before calling a function you have not used yet.

### Duration & Gap Analysis

- `duration_gap_analysis(asset_duration, liability_duration, total_assets, total_liabilities, rate_shock=0.01)`: Duration-gap analysis of the banking book.
- `macaulay_duration_balance_sheet(cashflows, times, discount_rate)`: Macaulay duration of a balance-sheet cashflow stream (years).
- `modified_duration_balance_sheet(cashflows, times, discount_rate, frequency=1)`: Modified duration of a balance-sheet position.
- `effective_duration_alm(pv_base, pv_up, pv_down, rate_shock)`: Effective duration of an ALM position from re-valued PVs under a shock.
- `convexity_gap(asset_convexity, liability_convexity, total_assets, total_liabilities)`: Convexity gap of the banking book.

### NII & EVE Simulation

- `nii_simulation_stress(asset_balances, asset_rates, liability_balances, liability_rates, rate_shock, asset_beta=1.0, liability_beta=0.5)`: Stressed NII under a parallel rate shock with repricing betas.
- `economic_value_of_equity_eve(asset_cashflows, asset_times, liability_cashflows, liability_times, asset_rates, liability_rates)`: Economic Value of Equity: PV(assets) − PV(liabilities).
- `eve_sensitivity_analysis(net_cashflows, times, base_rates, parallel_bps=200.0, short_bps=300.0, long_bps=150.0)`: EVE sensitivity (ΔEVE) under each of the six IRRBB rate shocks.
- `nii_sensitivity_rate_shock(rate_sensitive_assets, rate_sensitive_liabilities, rate_shock)`: Net interest income sensitivity to a parallel rate shock.
- `nii_simulation_baseline(asset_balances, asset_rates, liability_balances, liability_rates)`: Baseline (current-rate) net-interest-income projection.
- `liquidity_adjusted_nii(base_nii, liquidity_buffer, buffer_yield, funding_cost, liquidity_premium)`: Liquidity-adjusted NII: base NII net of the liquidity-buffer carry cost.

### IRRBB Framework

[REGULATORY] BCBS d368 ("Interest rate risk in the banking book", April
2016) Annex 2 defines the six prescribed shock scenarios constructed by
`irrbb_six_standard_rate_shocks` (`engine/alm_irrbb.py`): parallel up/down
are flat across tenor; short_up/short_down decay with tenor as
`short_bps · e^(−t/4)`; steepener = `−0.65·short + 0.90·long` and
flattener = `0.80·short − 0.60·long`, where `long` grows with tenor as
`long_bps · (1 − e^(−t/4))`. These scalars and the tenor-decay shape match
Annex 2 exactly — `tests/validation/test_alm_ref.py` checks them against
Annex 2's own published worked example (t = 3.5y, |short| = |long| = 100bp
→ steepener = +25.4bp), independently cross-confirmed against OSFI's
Interest Rate Risk Management guideline, which reproduces the same
example. `interest_rate_risk_capital_irrbb` implements d368 Principle 12's
supervisory outlier test: a bank is an outlier if the worst-case ΔEVE
decline exceeds 15% of Tier-1 capital (`outlier_threshold=0.15` default).
Two citations in this module previously pointed at the wrong section
(§115/§118, which don't exist in d368 in the cited sense) — fixed to
Annex 2 / Principle 12 in commit `364f961`.

[LIMITATION — STALE SHOCK MAGNITUDES] `irrbb_six_standard_rate_shocks`'s
defaults (`parallel_bps=200`, `short_bps=300`, `long_bps=150`) are d368
(2016)'s USD row, not current. BCBS d578 ("Recalibration of shocks for
interest rate risk in the banking book", July 2024,
bis.org/bcbs/publ/d578.htm) recalibrated the per-currency shock sizes —
widening the calibration window to Dec 2015–Dec 2023, moving from a 99th
to a 99.9th percentile, and rounding to the nearest 25bp instead of 50bp —
effective 1 January 2026, already in effect as of this writing (2026-08).
Neither this codebase's engine docstring nor this skill file could verify
the exact new per-currency figures against the primary BIS document or any
secondary summary: bis.org, forvismazars.com, kpmg.com and banking.vision
are all blocked by this environment's network egress proxy, reproducing
the same 403s the original audit hit. The 200/300/150 defaults have
deliberately NOT been changed to a plausible-but-unverified number —
committing an unverified figure here would repeat the exact failure mode
already found and fixed once in this codebase (a false "QuantLib
cross-validated" claim, see `fix/iron-triangle-quantlib-claim`). Callers
needing d578-compliant shocks must pass `parallel_bps`/`short_bps`/
`long_bps` explicitly, sourced from the primary document.

[SCOPE NOTE] `behavioural_modelling_nmds`'s docstring cites "BCBS d368 NMD
treatment", but the function implements a bespoke core/non-core
exponential-decay blend, not d368's actual standardised NMD methodology
(maturity-capped slotting into tenor buckets). Treat it as an independent,
unvalidated behavioural model, not a compliant implementation of the
standardised approach — `tests/validation/test_alm_ref.py` checks it only
against its own documented formula, not against d368's slotting output.

- `irrbb_standardised_framework(net_cashflows, times, base_rates, parallel_bps=200.0, short_bps=300.0, long_bps=150.0)`: Standardised IRRBB EVE measure: worst ΔEVE across the six shocks.
- `irrbb_internal_model(net_cashflows, times, base_rates, rate_scenarios)`: Internal-model IRRBB EVE using a bank's own rate scenarios.
- `irrbb_six_standard_rate_shocks(tenors, parallel_bps=200.0, short_bps=300.0, long_bps=150.0)`: Construct the six BCBS d368 standard interest-rate shock curves.
- `basis_risk_irrbb(asset_balances, asset_index_shifts, liability_balances, liability_index_shifts)`: Basis risk: NII impact of imperfectly-correlated index repricing.
- `option_risk_irrbb(automatic_option_value, behavioural_option_value, notional)`: Option risk: value of automatic and behavioural embedded options.
- `pipeline_risk_measurement(pipeline_notional, pull_through_rate, rate_lock_period, rate_volatility)`: Pipeline risk of rate-locked mortgage commitments not yet on balance.
- `interest_rate_risk_capital_irrbb(worst_delta_eve, tier1_capital, outlier_threshold=0.15)`: IRRBB supervisory outlier test against Tier-1 capital.

### Repricing & Gap

- `static_gap_analysis(bucket_assets, bucket_liabilities)`: Static (point-in-time) repricing gap assuming a frozen balance sheet.
- `dynamic_gap_analysis(bucket_assets, bucket_liabilities, asset_growth, liability_growth, n_periods)`: Dynamic gap projecting balance growth over future periods.
- `repricing_gap_analysis(bucket_assets, bucket_liabilities, bucket_labels=None)`: Repricing gap per time bucket and the cumulative gap.
- `repricing_maturity_profile(balances, repricing_times, n_buckets, bucket_edges)`: Allocate balances into repricing-time buckets.

### Behavioural & Prepayment Models

- `prepayment_model_mortgages(principal, annual_rate, term_years, cpr)`: Project mortgage cashflows under a constant CPR prepayment assumption.
- `behavioural_modelling_nmds(total_balance, core_fraction, core_runoff_rate, non_core_runoff_rate, horizon_years=5.0)`: Model non-maturity-deposit (NMD) run-off splitting core / non-core.
- `non_maturity_deposit_stability(balance_history, confidence_level=0.99)`: Estimate the stable (core) portion of NMDs from a balance history.
- `core_deposit_duration(core_balance, decay_rate, discount_rate, max_years=30.0)`: Effective duration of core deposits modelled as a decaying annuity.
- `loan_prepayment_rate_cpr(smm=None, cpr=None)`: Convert between single-monthly mortality (SMM) and CPR.

### Funds Transfer Pricing (FTP)

- `funds_transfer_pricing_ftp(notional, customer_rate, ftp_rate, liquidity_premium=0.0, is_asset=True)`: Funds-transfer-price a single deal into margin components.
- `ftp_curve_construction(tenors, base_curve, liquidity_spreads)`: Construct a matched-maturity FTP curve = base curve + liquidity spread.

### ALM Strategic Analytics

- `asset_liability_mismatch_index(asset_durations, asset_amounts, liability_durations, liability_amounts)`: Asset-liability mismatch index from duration-weighted exposures.
- `structural_hedge_optimisation(target_duration, instrument_durations, instrument_max_notional, equity_notional)`: Optimise a structural hedge to a target equity duration.
- `alm_stress_test(net_cashflows, times, base_rates, tier1_capital, parallel_bps=200.0)`: Run an ALM stress test: worst-case EVE decline vs Tier-1 capital.
- `balance_sheet_projection_model(initial_assets, initial_liabilities, asset_growth_rate, liability_growth_rate, asset_yield, liability_cost, n_years)`: Project the balance sheet and NII forward over ``n_years``.

## Naming convention
- The public API surface is exactly 33
  (matches every module's `__all__` and the 33 registered `/api/v1/alm/*`
  routes). `tests/validation/test_alm_ref.py` says "34 across 5 modules" —
  that count additionally includes `economic_value_helper`, an internal
  `alm_irrbb.py` helper (not in `__all__`, not routed) reused by
  `alm_nii_eve.py`; it is not part of the public API this file describes.
- NII/EVE: currency amounts
- Duration: years (decimal)
- Rate shocks: basis points (int) or decimal
- IRRBB shocks: "parallel_up" | "parallel_down" | "steepener" |
                "flattener" | "short_up" | "short_down"
## For contributors: dependencies
numpy >= 1.24 · scipy >= 1.10 (`optimize.lsq_linear`, used only by
`structural_hedge_optimisation`) · numba (one kernel, `alm_behavioural.py`)

Note: earlier revisions of this file also listed pandas and QuantLib as ALM
dependencies. Neither is imported anywhere in `engine/alm_*.py`,
`schemas/alm.py` or `api/routes/alm.py` (verified by repo-wide grep) —
every function returns a plain `dict`, never a DataFrame, hence the return
type above. QuantLib appears only in `requirements-heavy.txt` and the AMI
worker install list, and is not used by any ALM test or, in fact, any test
in the repo (`tests/validation/`) — a false "QuantLib cross-validated"
claim was already found and removed once elsewhere in this codebase
(`docs/p8-iron-triangle-data.md`, `fix/iron-triangle-quantlib-claim`);
listing it here as a dependency without an actual import would repeat that
mistake.

## For contributors: architecture context
- **Compute**: NumPy (cash-flow NPV, duration, EVE), SciPy
  `optimize.lsq_linear` (`structural_hedge_optimisation`'s bounded
  least-squares hedge solve). One `@njit(cache=True)` kernel exists in the
  whole ALM engine — `_amortise_with_prepay` in `alm_behavioural.py`, the
  month-by-month prepayment cashflow projection behind
  `prepayment_model_mortgages` — every other function is plain,
  non-JIT-compiled NumPy (CLAUDE.md §3.1 is satisfied trivially for those).
- **Execution**: synchronous request/response, not a Celery job. Every
  `/api/v1/alm/*` route (`api/routes/alm.py`, auto-generated by
  `scripts/gen_p3.py`) calls its engine function directly and returns the
  result dict in the same HTTP response (200, or 422 on bad input) — unlike
  the VaR domain's async submit-then-poll job pattern (CLAUDE.md §2/§3.2),
  there is no ALM Celery task and no queue involved.
- **Storage**: none dedicated to ALM. `storage/models.py` defines only
  `ApiUsage`, `User` and `VaRJob` — there is no balance-sheet-snapshot or
  EVE-history table; callers must persist results themselves if needed.
- **API**: FastAPI endpoint `/api/v1/alm/{function}`, 33 routes, JWT bearer
  auth required on every route (`tests/test_alm_api.py`).

---

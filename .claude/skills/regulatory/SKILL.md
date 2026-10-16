---
name: pyvar-regulatory
description: >
  Run pyvar's 30 regulatory-capital functions on the live pyvar.com API: Basel III/IV ratios
  and output floor, ICAAP/SREP Pillar 2, FRTB, MiFID II, EMIR/SFTR, AIFMD/UCITS/Solvency II
  and CRR2 buffers. Use when the user wants a capital ratio, buffer or regulatory test
  computed rather than only explained. Needs a free pyvar API key; the skill explains how to
  get one.
version: "1.2.0"
author: "Fibtec Limited — pyvar.com"
tags: [regulatory, Basel-III, Basel-IV, FRTB, MiFID-II, EMIR, SFTR, ICAAP, SREP, CET1, Solvency-II, CRR2]
---

# pyvar — Regulatory Capital  (30 functions)

Regulatory calculations: capital ratios and buffers, Pillar 2, FRTB, MiFID II, EMIR, fund regulations. The thresholds are the published Basel/EU values and are fixed, not parameters. Pick the function in **Functions** below.

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
     `Client(api_key=os.environ["PYVAR_API_KEY"]).regulatory.<function>(**body)`.
   - REST: `POST https://www.pyvar.com/api/v1/regulatory/<function>` with header
     `Authorization: Bearer $PYVAR_API_KEY` and the body as JSON.
   - MCP: `call_pyvar_function(domain="regulatory", function_name="<function>", params=body)`.
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

### 1. CET1 ratio, combined buffer and leverage ratio for one bank

Three independent calls on the same balance sheet (any one currency unit). Each returns the ratio and whether it meets the regulatory minimum.

`POST /api/v1/regulatory/basel_iii_cet1_ratio`

```json
{
  "cet1_capital": 12000000000,
  "risk_weighted_assets": 100000000000
}
```

Returns: `cet1_ratio`, `minimum`, `surplus`, `compliant`.

`POST /api/v1/regulatory/combined_buffer_requirement`

```json
{
  "capital_conservation_buffer_ratio": 0.025,
  "countercyclical_buffer_ratio": 0.01,
  "systemic_buffer_ratio": 0.01,
  "risk_weighted_assets": 100000000000
}
```

Returns: `combined_buffer_ratio`, `combined_buffer_capital`.

`POST /api/v1/regulatory/basel_iii_leverage_ratio`

```json
{
  "tier1_capital": 13000000000,
  "total_exposure": 380000000000
}
```

Returns: `leverage_ratio`, `minimum`, `surplus`, `compliant`.

### 2. Basel IV output floor

Internal-model RWA cannot fall below 72.5% of the standardised RWA. Here the floor binds.

`POST /api/v1/regulatory/basel_iv_output_floor`

```json
{
  "internal_model_rwa": 60000000000,
  "standardised_rwa": 100000000000
}
```

Returns: `floored_rwa`, `floor_rwa`, `binding`, `rwa_uplift`, `floor_factor`.

## Functions (30)

Every function is `POST /api/v1/regulatory/<name>`. Required parameters are listed bare, optional ones with their defaults (`name=default`). Types, bounds and formulas are in [references/functions.md](references/functions.md): read the entry before calling a function you have not used yet.

### Basel III/IV Capital Ratios

- `basel_iii_cet1_ratio(cet1_capital, risk_weighted_assets)`: Basel III Common Equity Tier 1 (CET1) ratio.
  Note: Basel III Common Equity Tier 1 (CET1) ratio; minimum 4.5% (Basel III §50)
- `basel_iii_tier1_ratio(tier1_capital, risk_weighted_assets)`: Basel III Tier 1 capital ratio.
  Note: Basel III Tier 1 Capital Ratio; minimum 6.0% (Basel III §50)
- `basel_iii_total_capital_ratio(total_capital, risk_weighted_assets)`: Basel III Total capital ratio.
- `basel_iii_leverage_ratio(tier1_capital, total_exposure)`: Basel III leverage ratio.
- `basel_iv_output_floor(internal_model_rwa, standardised_rwa, floor_factor=0.725)`: Basel IV output floor.

### ICAAP / SREP / Pillar 2

- `srep_capital_add_on(pillar1_requirement, pillar2a_addon_ratio, risk_weighted_assets)`: SREP (Supervisory Review and Evaluation Process) capital add-on.
- `pillar_2a_capital(risk_addons, risk_weighted_assets)`: Pillar 2A capital — sum of individual risk add-ons.
  Note: Sum of individual risk add-ons
- `pillar_2b_stress_buffer(stressed_capital_depletion, risk_weighted_assets)`: Pillar 2B stress buffer (PRA buffer / capital guidance).
- `icaap_capital_assessment(pillar1_capital, risk_capital_components, available_capital)`: ICAAP internal capital adequacy assessment.

### FRTB Capital (SA & IMA)

- `frtb_sa_market_risk_capital(sensitivities_charge, default_risk_charge, residual_risk_addon)`: FRTB Standardised Approach total market-risk capital.
- `frtb_ima_market_risk_capital(expected_shortfall, stressed_es_ratio, multiplier, non_modellable_ses=0.0, default_risk_charge=0.0)`: FRTB Internal Models Approach total market-risk capital.
- `frtb_pl_attribution_test(risk_theoretical_pnl, hypothetical_pnl)`: FRTB P&L Attribution Test (PAT) — Spearman correlation + variance ratio.
  Note: Spearman rank correlation + variance ratio, jointly evaluated (CLAUDE.md §4.4 / BCBS d457)
- `frtb_trading_desk_aggregation(desk_sa_charges, desk_ima_charges, desk_ima_eligible)`: FRTB trading-desk capital aggregation.

### MiFID II

- `mifid_ii_transaction_report_validator(report)`: MiFID II / RTS 22 transaction report field validator.
- `mifid_ii_pre_trade_transparency(instrument_type, order_size, large_in_scale_threshold, is_liquid=True)`: MiFID II pre-trade transparency / LIS waiver assessment.
- `mifid_ii_post_trade_transparency(trade_size, delayed_publication_threshold, is_liquid=True)`: MiFID II post-trade transparency / deferred-publication assessment.
- `mifid_ii_best_execution_metric(executed_prices, benchmark_prices, quantities, side=1)`: MiFID II best-execution TCA metric -- internal, NOT an RTS 27/28 figure.
  Note: Quantity-weighted price improvement vs. a reference price, in bps. NOT an RTS 27/28 figure: RTS 27 (DR (EU) 2017/575) and RTS 28 (DR (EU) 2017/576) define different fields (simple/volume-weighted prices & spreads; execution-venue rankings), not this metric, and RTS 27 was repealed by the 2024 MiFIR review. A prior docstring cited "RTS 27/28" directly for this function; corrected in the citation cleanup pass (see "Citation cleanup" below). Useful internal TCA metric, just not a regulator-prescribed one.
- `mifid_ii_algorithm_documentation(documentation)`: MiFID II RTS 6 algorithmic-trading documentation completeness check.

### EMIR & SFTR

- `emir_trade_repository_report(trade)`: EMIR trade repository report builder/validator.
- `emir_clearing_obligation_check(notionals, counterparty_category, clearing_thresholds)`: EMIR clearing obligation check (Art. 4 / Art. 4a / Art. 10 / clearing thresholds).
  Note: EMIR REFIT (Reg. (EU) 2019/834) Art. 4a(1) / Art. 10(1). Takes `notionals: dict[str, float]` (gross notional per asset class the counterparty holds — NOT a single asset_class/notional pair) plus counterparty_category ("FC"/"NFC+"/ "NFC-") and clearing_thresholds. For an FC, breaching the threshold in ANY ONE asset class puts ALL of that counterparty's asset classes in scope (Art. 4a(1)) — this is why `notionals` must cover every class, not just the one being queried. For an NFC+, each asset class is evaluated independently (Art. 10(1)); NFC- is always exempt. Returns clearing_required as a dict keyed by asset class, plus an any_class_breached flag. See "EMIR clearing scope" below.
- `emir_margin_requirement(portfolio_value, initial_margin_rate, variation_margin, minimum_transfer_amount=0.0)`: EMIR (Art. 11) uncleared-derivatives margin requirement.
- `sftr_securities_finance_report(transaction)`: SFTR securities-financing transaction report builder/validator.

### Fund Regulations (AIFMD/UCITS/Solvency II)

- `aifmd_risk_metrics(gross_exposure, commitment_exposure, net_asset_value, var_pct=None)`: AIFMD Annex IV risk metrics — leverage and (optional) VaR.
- `ucits_kiid_risk_indicator(returns, periods_per_year=52)`: UCITS KIID Synthetic Risk and Reward Indicator (SRRI), 1-7.
- `solvency_ii_scr_market_risk(sub_module_charges, correlation_matrix, sub_module_names=None)`: Solvency II SCR Market risk — standard-formula modular aggregation.
- `solvency_ii_scr_credit_risk(exposures, loss_given_default, default_probabilities)`: Solvency II SCR counterparty default (credit) risk — Type 1 exposures.
  Note: Delegated Regulation (EU) 2015/35 Art. 200(1)-(3). Capital is a TIERED multiplier on sigma (the loss std. dev.), not a flat 3x: 3*sigma while sigma/total_LGD <= 7%; 5*sigma while 7%-20%; capped at total_LGD above 20%. No risk_factor parameter — the tiers are fixed by the Delegated Regulation. [LIMITATION] the variance computed is the intra-counterparty term only (independent-Bernoulli); Art. 201's inter-counterparty correlation term (V_inter) is not computed, so the true SCR is at least as large as what this returns — see "Solvency II SCR credit-risk fix" below.

### CRR2 & Capital Buffers

- `crr2_large_exposure_limit(exposure_value, tier1_capital, is_institution=False)`: CRR2 large exposure limit (Art. 395).
- `capital_conservation_buffer(cet1_ratio, risk_weighted_assets, buffer_ratio=0.025)`: Capital Conservation Buffer (CCoB) and distribution constraint.
- `countercyclical_capital_buffer(exposure_amounts, country_ccyb_rates, risk_weighted_assets)`: Institution-specific Countercyclical Capital Buffer (CCyB).
- `combined_buffer_requirement(capital_conservation_buffer_ratio=0.025, countercyclical_buffer_ratio=0.0, systemic_buffer_ratio=0.0, risk_weighted_assets=0.0)`: Combined Buffer Requirement (CBR).

## Naming convention
- Capital ratios: decimal (0.15 = 15%)
- RWA: currency amount
- Field validators return `{"valid": bool, "errors": list, "report": dict}` —
  this covers `mifid_ii_transaction_report_validator`,
  `mifid_ii_algorithm_documentation`, `emir_trade_repository_report` and
  `sftr_securities_finance_report`, not just the MiFID II ones.
## For contributors: dependencies
numpy >= 1.26.0 · scipy >= 1.13.0 (only `reg_frtb.py`, for
`scipy.stats.spearmanr` in the P&L Attribution Test)

pandas, lxml and openpyxl are NOT dependencies of this domain's engine code —
every `engine/reg_*.py` function returns a plain `dict`, and there is no
XBRL/COREP export anywhere in the codebase (see Architecture context above).
Versions above match `requirements.txt`/`requirements-ci.txt`, the actual
pinned versions — not aspirational ones.

---
## Two regulatory-logic fixes from this project's history

Both were found during an internal "Tier 3 #2" test-reference audit — an
independent-reference pass that recomputes each function's expected output by
hand or in closed form from the cited regulation, rather than asserting a
function's output against itself. Both shipped before the codebase's first
public release, in `engine/reg_solvency.py` and `engine/reg_mifid_emir.py`.

### Solvency II SCR credit-risk formula (Delegated Regulation (EU) 2015/35 Art. 200-201)
`solvency_ii_scr_credit_risk` used to take a caller-configurable
`risk_factor` parameter defaulting to a flat `3.0`, applied as
`SCR = risk_factor * sigma`. Art. 200(1)-(3) instead fixes a TIERED
multiplier on sigma (the loss standard deviation) relative to total LGD:
`3*sigma` while `sigma/total_LGD <= 7%`, `5*sigma` while `7%-20%`, and capped
at `total_LGD` above 20%. On the representative 2-exposure case used to catch
this, the flat-3x version understated capital by roughly 79% (807 vs. the
correct ~1449) — entirely from missing the 5x and capped tiers, since that
case's `sigma/total_LGD` ratio (~16.3%) falls in the 5x band, not the 3x one.
The fix removed `risk_factor` from the function signature and the
`SolvencyIiScrCreditRiskRequest` schema entirely — Art. 200's multiplier
tiers are not a free parameter, same principle CLAUDE.md §4.3/§4.4 already
applies to the Basel backtesting/PAT thresholds. The fix also added an
explicit `[LIMITATION]` docstring note (not previously present): the
variance term computed is intra-counterparty only (independent-Bernoulli
approximation); Art. 201's full formula adds a positive inter-counterparty
correlation term (V_inter) this function still does not compute, so its
SCR output is a lower bound, not the full Art. 201 figure.

### EMIR clearing obligation scope (EMIR REFIT, Regulation (EU) 2019/834, Art. 4a(1) / Art. 10(1))
`emir_clearing_obligation_check` used to take a single
`(asset_class, notional)` pair and apply the same per-asset-class breach
logic to both Financial Counterparties (FC) and NFC+ counterparties (beyond
the NFC- exemption, which was always correct). That is right for NFC+
(Art. 10(1) genuinely is per-class) but wrong for FC: Art. 4a(1) says an FC
that breaches its clearing threshold in ANY ONE OTC derivative asset class
becomes subject to the clearing obligation for ALL asset classes it holds
positions in. The bug was masked by the original test, which happened to
always query the same asset class that had breached. The fix changed the
signature to take `notionals: dict[str, float]` covering every asset class
the counterparty holds (a single class's notional cannot answer the FC
any-class-breach question) and changed the return shape from a single bool
to `clearing_required: dict[str, bool]` (one entry per class) plus a new
`any_class_breached` flag — an intentionally API-breaking change, justified
the same way as the Solvency II fix: the old shape was wrong, not just
differently designed.
## Citation cleanup pass
Alongside the two fixes above, engine docstrings across this domain (and
`CLAUDE.md`) went through a pass that removed citations that didn't actually
support the implementation and replaced them with either a real published
source or an explicit `[LIMITATION]` note where none exists. Two concrete
outcomes worth knowing before citing a regulation in new code here:
- `mifid_ii_best_execution_metric` previously cited "RTS 27/28" directly.
  RTS 27 (Commission DR (EU) 2017/575) and RTS 28 (DR (EU) 2017/576) define
  specific, different fields (simple/volume-weighted transaction
  prices/spreads; execution-venue rankings) — neither defines the
  quantity-weighted price-improvement-in-bps metric this function computes,
  and RTS 27 was repealed outright by the 2024 MiFIR review. The function is
  still a reasonable internal TCA metric; it just isn't a
  regulator-prescribed one, and the docstring says so now.
- Several functions have a genuine no-published-source gap, documented
  in-place rather than papered over with an invented citation:
  `icaap_capital_assessment` and `pillar_2b_stress_buffer` implement
  assessments that CRD IV Art. 73 / PRA SS31/15 / EBA/GL/2018/04 require to
  happen, but none of those sources publish a specific formula or worked
  example to match against. `mifid_ii_pre_trade_transparency`,
  `mifid_ii_post_trade_transparency` and `mifid_ii_algorithm_documentation`
  cite real rules (MiFIR Art. 4(1)(c)/9(1)(c) LIS/illiquidity waivers; RTS
  1/2 deferred-publication mechanics; RTS 6 Art. 5-12 governance
  requirements) but the specific numeric thresholds passed in and the
  6-item documentation checklist are this codebase's internal choices, not
  regulator-set values — ESMA only publishes LIS/deferral thresholds as
  per-instrument values in the FITRS register, with no general worked
  example to cite instead.
- The three field validators (`mifid_ii_transaction_report_validator`,
  `emir_trade_repository_report`, `sftr_securities_finance_report`) check a
  representative CORE SUBSET of their full regulatory field schema — 9 of
  RTS 22's ~65 fields, 6 of EMIR REFIT's ~200, 6 of SFTR's field set — not
  full schema coverage. The individual format rules they do check are
  genuinely regulator-sourced (LEI = 20 characters per ISO 17442; ISIN = 12
  characters per ISO 6166), so a `valid: True` result should be read as
  "core fields well-formed," not "filing-ready."

## For contributors: architecture context
- **Compute**: NumPy (capital/ratio formulas); SciPy (`scipy.stats.spearmanr` for
  the FRTB P&L Attribution Test). No pandas, no Numba — these are reporting/
  aggregation functions over scalars and small arrays, not array hot loops, so
  none of them are `@njit` (contrast with `engine/montecarlo.py`).
- **Output**: a plain `dict` per function, returned as JSON via `OrjsonResponse`.
  There is no XBRL/COREP export in this codebase today (no `lxml`/`openpyxl`
  usage anywhere under `engine/`, `api/`, or `schemas/` for this domain) —
  reporting field validators (`mifid_ii_transaction_report_validator`,
  `emir_trade_repository_report`, `sftr_securities_finance_report`) check field
  presence/format only, they do not produce a submittable regulatory filing.
- **Storage**: none dedicated to this domain. Calls are synchronous
  request/response (no Celery dispatch, no job polling — unlike `/var/compute`).
  Only generic `ApiUsage` telemetry (`storage/models.py`) records that the call
  happened (domain, function name, tier, latency); there is no
  `VaRJob`-style audit table for regulatory submissions.
- **API**: FastAPI endpoint `/api/v1/regulatory/{function}` (auto-generated
  routes in `api/routes/regulatory.py`; the engine function in `engine/reg_*.py`
  is the single source of truth, the route is a thin validate/call/serialize
  wrapper)
- **Security**: Bandit runs in CI (`bandit -r . -ll -x tests/ --exit-zero`) but
  is not currently merge-blocking — findings surface in CI logs, they don't
  fail the build (a deliberate interim state per the workflow's own comment,
  not an oversight — see `arch-observability/SKILL.md`). All inputs validated
  via Pydantic.

---

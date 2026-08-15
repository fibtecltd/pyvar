---
name: pyvar-regulatory
description: >
  Activate for regulatory capital, prudential reporting, MiFID II, EMIR,
  Basel III/IV, FRTB, ICAAP/SREP, Solvency II, or CRR2 calculations. Covers
  30 functions across 7 regulatory frameworks.
version: "1.1.0"
author: "Fibtec Limited — pyvar.com"
tags: [regulatory, Basel-III, Basel-IV, FRTB, MiFID-II, EMIR, SFTR,
       ICAAP, SREP, CET1, Solvency-II, CRR2]
---

# pyvar — Regulatory & Compliance  (30 functions)

## Architecture context
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

## Basel III/IV Capital Ratios

```python
pyvar.regulatory.basel_iii_cet1_ratio(
    # Basel III Common Equity Tier 1 (CET1) ratio; minimum 4.5% (Basel III §50)
    **params
) -> dict
```

```python
pyvar.regulatory.basel_iii_tier1_ratio(
    # Basel III Tier 1 Capital Ratio; minimum 6.0% (Basel III §50)
    **params
) -> dict
```

```python
pyvar.regulatory.basel_iii_total_capital_ratio(
    # Basel III Total Capital Ratio; minimum 8.0% (Basel III §50)
    **params
) -> dict
```

```python
pyvar.regulatory.basel_iii_leverage_ratio(
    # Basel III Leverage Ratio; minimum 3.0%
    **params
) -> dict
```

```python
pyvar.regulatory.basel_iv_output_floor(
    # Basel IV Output Floor (72.5%, Basel III finalisation)
    **params
) -> dict
```

```python
pyvar.regulatory.icaap_capital_assessment(
    # ICAAP Capital Assessment
    **params
) -> dict
```


## ICAAP / SREP / Pillar 2

```python
pyvar.regulatory.srep_capital_add_on(
    # SREP Capital Add-On
    **params
) -> dict
```

```python
pyvar.regulatory.pillar_2a_capital(
    # Pillar 2A Capital (CRD IV Art. 104a) — sum of individual risk add-ons
    **params
) -> dict
```

```python
pyvar.regulatory.pillar_2b_stress_buffer(
    # Pillar 2B Stress Buffer
    **params
) -> dict
```

```python
pyvar.regulatory.combined_buffer_requirement(
    # Combined Buffer Requirement
    **params
) -> dict
```


## FRTB Capital (SA & IMA)

```python
pyvar.regulatory.frtb_sa_market_risk_capital(
    # FRTB SA Market Risk Capital
    **params
) -> dict
```

```python
pyvar.regulatory.frtb_ima_market_risk_capital(
    # FRTB IMA Market Risk Capital
    **params
) -> dict
```

```python
pyvar.regulatory.frtb_pl_attribution_test(
    # FRTB P&L Attribution Test — Spearman rank correlation + variance ratio,
    # jointly evaluated (CLAUDE.md §4.4 / BCBS d457)
    **params
) -> dict
```

```python
pyvar.regulatory.frtb_trading_desk_aggregation(
    # FRTB Trading Desk Aggregation
    **params
) -> dict
```


## MiFID II

```python
pyvar.regulatory.mifid_ii_transaction_report_validator(
    # MiFID II Transaction Report Validator
    **params
) -> dict
```

```python
pyvar.regulatory.mifid_ii_pre_trade_transparency(
    # MiFID II Pre-Trade Transparency
    **params
) -> dict
```

```python
pyvar.regulatory.mifid_ii_post_trade_transparency(
    # MiFID II Post-Trade Transparency
    **params
) -> dict
```

```python
pyvar.regulatory.mifid_ii_best_execution_metric(
    # MiFID II best-execution TCA metric — quantity-weighted price
    # improvement vs. a reference price, in bps. NOT an RTS 27/28 figure:
    # RTS 27 (DR (EU) 2017/575) and RTS 28 (DR (EU) 2017/576) define
    # different fields (simple/volume-weighted prices & spreads;
    # execution-venue rankings), not this metric, and RTS 27 was repealed
    # by the 2024 MiFIR review. A prior docstring cited "RTS 27/28"
    # directly for this function; corrected in the citation cleanup pass
    # (see "Citation cleanup" below). Useful internal TCA metric, just not
    # a regulator-prescribed one.
    **params
) -> dict
```

```python
pyvar.regulatory.mifid_ii_algorithm_documentation(
    # MiFID II Algorithm Documentation
    **params
) -> dict
```


## EMIR & SFTR

```python
pyvar.regulatory.emir_trade_repository_report(
    # EMIR Trade Repository Report
    **params
) -> dict
```

```python
pyvar.regulatory.emir_clearing_obligation_check(
    # EMIR Clearing Obligation Check — EMIR REFIT (Reg. (EU) 2019/834)
    # Art. 4a(1) / Art. 10(1). Takes `notionals: dict[str, float]` (gross
    # notional per asset class the counterparty holds — NOT a single
    # asset_class/notional pair) plus counterparty_category ("FC"/"NFC+"/
    # "NFC-") and clearing_thresholds. For an FC, breaching the threshold
    # in ANY ONE asset class puts ALL of that counterparty's asset classes
    # in scope (Art. 4a(1)) — this is why `notionals` must cover every
    # class, not just the one being queried. For an NFC+, each asset class
    # is evaluated independently (Art. 10(1)); NFC- is always exempt.
    # Returns clearing_required as a dict keyed by asset class, plus an
    # any_class_breached flag. See "EMIR clearing scope" below.
    **params
) -> dict
```

```python
pyvar.regulatory.emir_margin_requirement(
    # EMIR Margin Requirement
    **params
) -> dict
```

```python
pyvar.regulatory.sftr_securities_finance_report(
    # SFTR Securities Finance Report
    **params
) -> dict
```


## Fund Regulations (AIFMD/UCITS/Solvency II)

```python
pyvar.regulatory.aifmd_risk_metrics(
    # AIFMD Risk Metrics
    **params
) -> dict
```

```python
pyvar.regulatory.ucits_kiid_risk_indicator(
    # UCITS KIID Risk Indicator
    **params
) -> dict
```

```python
pyvar.regulatory.solvency_ii_scr_market_risk(
    # Solvency II SCR Market Risk
    **params
) -> dict
```

```python
pyvar.regulatory.solvency_ii_scr_credit_risk(
    # Solvency II SCR Credit Risk (counterparty default, Type 1) —
    # Delegated Regulation (EU) 2015/35 Art. 200(1)-(3). Capital is a
    # TIERED multiplier on sigma (the loss std. dev.), not a flat 3x:
    # 3*sigma while sigma/total_LGD <= 7%; 5*sigma while 7%-20%; capped at
    # total_LGD above 20%. No risk_factor parameter — the tiers are fixed
    # by the Delegated Regulation. [LIMITATION] the variance computed is
    # the intra-counterparty term only (independent-Bernoulli); Art. 201's
    # inter-counterparty correlation term (V_inter) is not computed, so
    # the true SCR is at least as large as what this returns — see
    # "Solvency II SCR credit-risk fix" below.
    **params
) -> dict
```


## CRR2 & Capital Buffers

```python
pyvar.regulatory.crr2_large_exposure_limit(
    # CRR2 Large Exposure Limit
    **params
) -> dict
```

```python
pyvar.regulatory.capital_conservation_buffer(
    # Capital Conservation Buffer
    **params
) -> dict
```

```python
pyvar.regulatory.countercyclical_capital_buffer(
    # Countercyclical Capital Buffer
    **params
) -> dict
```


## Naming convention
- All functions under `pyvar.regulatory.*`
- Capital ratios: decimal (0.15 = 15%)
- RWA: currency amount
- Field validators return `{"valid": bool, "errors": list, "report": dict}` —
  this covers `mifid_ii_transaction_report_validator`,
  `mifid_ii_algorithm_documentation`, `emir_trade_repository_report` and
  `sftr_securities_finance_report`, not just the MiFID II ones.

## Dependencies
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

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

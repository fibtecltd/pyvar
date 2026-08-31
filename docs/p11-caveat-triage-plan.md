# Caveat triage plan — the 99 functions flagged in the formula sourcing pass

**Status:** planning document. **Nothing in this plan blocks the public
launch** — per P11 item 5 (`docs/p11-pre-launch-hardening.md` §4, §7.4), the
caveats are the intended output of an honesty-first sourcing pass, not a
defect discovered late. This document triages them into a worked plan so
they get addressed systematically post-go-live rather than sitting as an
undifferentiated 99-item list.

## Where the data comes from

`scripts/data/function_formulas.json` — 385 entries, each with an optional
`caveat` field written during the formula-sourcing pass (`docs/p11-pre-launch-hardening.md`
§4). 99 entries (25.7%) carry one. Every caveat is already visible to any
site visitor who opens that function's Try-it panel on pyvar.com (KaTeX
rendering, `portal/pyvar.js`'s `_renderFormula`) — this plan is about closing
the gap between "disclosed" and "fixed" or "confirmed acceptable," not about
first-time discovery.

By domain: derivatives 18, credit-risk 18, operational 14, liquidity 14,
regulatory 11, portfolio 10, alm 7, market-risk 7.

## Tiers

### Tier 0 — regulatory citation/scope accuracy (13 functions, highest priority)

Functions that name a specific regulatory standard (BCBS, CRR, EMIR, MiFID
II, Solvency II) in the docstring or function name, where the caveat states
the implementation only partially matches or deliberately departs from that
standard. The risk here isn't numerical — it's a user assuming "cites BCBS
248" means "validates BCBS 248 compliance." Action: **audit each one's
docstring header for an explicit, prominent scope disclaimer** (not just the
caveat field), and where the gap is a bounded, well-defined extension (e.g.
the missing EUR 150m CRR2 alternative threshold), scope a real fix. Where
the gap is structural (report validators checking a "representative subset"
of a 65-200 field regulatory schema), the honest fix is a docstring/name
clarification, not a claim of full-schema coverage — full-schema validation
against evolving regulatory technical standards is out of scope for this
platform's stated purpose.

| Function | Domain | Gap |
|---|---|---|
| `behavioural_modelling_nmds` | alm | Cites BCBS d368; implements a bespoke core/non-core decay blend, not d368's standardised NMD slotting |
| `downturn_lgd_adjustment` | credit-risk | CRR Art. 181 requires downturn-conservative LGD; this multiplicative scaling is a deliberate departure from the EBA/GL/2019/03 additive fallback |
| `combined_stress_scenario` | liquidity | Docstring states explicitly this is NOT the BCBS 238 reference combined scenario |
| `intraday_liquidity_stress_test` | liquidity | References BCBS 248 context only; not the standard's own stress design |
| `intraday_liquidity_monitor` | liquidity | Only `NetDebitPeak` is the genuine BCBS 248 monitoring tool; `MaxUsage` is not |
| `crr2_large_exposure_limit` | regulatory | Missing CRR2's EUR 150m absolute alternative threshold — 25%-of-Tier-1 test only |
| `solvency_ii_scr_credit_risk` | regulatory | Missing Delegated Regulation Art. 201's inter-counterparty correlation term (own `[LIMITATION]` docstring already flags this) |
| `emir_trade_repository_report` | regulatory | Validates 6 of EMIR REFIT's ~200 fields |
| `mifid_ii_transaction_report_validator` | regulatory | Validates 9 of RTS 22's ~65 mandatory fields |
| `sftr_securities_finance_report` | regulatory | Validates a representative 6-field subset of SFTR's full field set |
| `mifid_ii_best_execution_metric` | regulatory | Internal TCA metric only — neither RTS 27 nor RTS 28 defines a prescribed figure this matches |
| `mifid_ii_algorithm_documentation` | regulatory | The 6-item checklist is this codebase's own choice, not an RTS 6 checklist |
| `aifmd_risk_metrics` | regulatory | "Substantially leveraged" is a simple >3x NAV threshold flag, not AIFMD's full leverage-calculation methodology |

**Recommended first action:** a single PR adding an explicit `**Regulatory
scope:**` line to each of these 13 docstrings (one sentence, plain language,
same substance as the existing caveat but load-bearing in the docstring
itself, not just the portal's caveat panel) — cheap, immediate risk
reduction. Field-coverage expansion for the 3 report validators is a larger,
separate body of work (each field needs sourcing from the actual RTS/REFIT
technical standard) — track as its own follow-up, not bundled here.

### Tier 1 — unused/dead parameters (3 functions, cheap correctness fixes)

Real code smells: a parameter is accepted (and documented) but never
affects the computed result. Either wire it in or deprecate it explicitly —
leaving it silently inert risks a caller believing it changes behaviour.

| Function | Domain | Issue |
|---|---|---|
| `asset_swap_spread` | derivatives | `bond_price` argument accepted but never used — `PV_bond` is recomputed from `cashflows`/`times`/`swap_rates` instead |
| `bond_pricer_floating_rate` | derivatives | `maturity` only used for input validation; `n` (coupon periods) is taken from `len(reference_rates)` |
| `business_continuity_risk_score` | operational | `rpo_hours` accepted but not used anywhere in the score computation |

**Recommended action:** for each, either (a) wire the parameter into the
computation if that's the intended behaviour and cheap to do correctly, or
(b) remove it from the signature and bump to a documented breaking change
in `CHANGELOG.md`, whichever the actual intended semantics turn out to be
on inspection. Needs a human/engineering decision per function, not a
mechanical fix — flagged here as the concrete next step, not resolved by
this triage.

### Tier 2 — silent default assumptions (8 functions, low risk, cheap clarity win)

A parameter has a default that materially shapes the result (not just a
convenience default) but the default's implication isn't obvious from the
signature alone.

| Function | Domain | Default |
|---|---|---|
| `funding_valuation_adjustment_fva` | credit-risk | `survival_probability` defaults to 1 (no default conditioning) |
| `kmv_merton_distance_to_default` | credit-risk | `mu` (asset drift) defaults to `risk_free_rate` |
| `irb_advanced_approach_capital` | credit-risk | `R` defaults to the Basel corporate correlation function of PD |
| `irb_foundation_approach_capital` | credit-risk | `R` is always the Basel corporate correlation function — F-IRB exposes no override |
| `contingent_liquidity_risk` | liquidity | `ccf` (credit conversion factor) defaults to 1.0 per commitment |
| `hqla_level_1_asset_classifier` | liquidity | `haircuts` defaults to all zeros |
| `hqla_level_2a_asset_classifier` | liquidity | Single scalar haircut applies uniformly (not per-asset) |
| `hqla_level_2b_asset_classifier` | liquidity | Single scalar haircut applies uniformly (not per-asset) |

**Recommended action:** docstring-only fix — state the default's effect in
the first line of the docstring (e.g. "defaults to full survival, i.e. no
counterparty default conditioning"), not buried in an `Args:` type
annotation. No code/behaviour change needed; these defaults are reasonable,
they're just under-surfaced.

### Tier 3 — naming/docstring accuracy (4 functions, cheap trust fixes)

The function name or docstring claims something the code doesn't quite do.

| Function | Domain | Mismatch |
|---|---|---|
| `regime_detection_hmm` | portfolio | Named "hmm" but is a stationary 2-component Gaussian mixture (EM-fit, i.i.d. weights) — no transition matrix, so no actual regime persistence/switching dynamics |
| `compute_rolling_var` | market-risk | Docstring calls this an "expanding window"; code uses a fixed-length trailing window |
| `variance_gamma_model` | derivatives | `theta` here is the VG skew parameter, unrelated to the Greek theta (time decay) the same function's `greeks=True` option also returns — a naming collision within one function's own output |
| `charm_delta_decay` | market-risk | Computed as `+∂Δ/∂τ` (time-to-maturity convention); opposite sign from the common calendar-time charm convention `-∂Δ/∂t` |

**Recommended action:** `regime_detection_hmm` and `compute_rolling_var` are
one-line docstring/name-clarity fixes (or a genuine enhancement — adding a
real transition matrix to the regime model — if there's user demand, but
that's a feature request, not a launch-blocking fix). `variance_gamma_model`
and `charm_delta_decay` need a one-line disambiguation in the docstring,
not a code change (both are correct, just easy to misread).

### Tier 4 — intentional, disclosed methodology simplifications (71 functions, no action needed)

The remaining 71 caveats are the expected shape of this exercise: numerical
methods (finite differences vs. closed-form derivatives, discrete Riemann
sums vs. closed-form integrals, Monte Carlo vs. analytic quantiles),
deliberate simplifications with a named textbook alternative not implemented
(simplified short-rate lattices instead of full BDT/HW calibration,
Reiner-Rubinstein barrier terms, Longstaff-Schwartz continuation
regressions), and internal-convention choices (bespoke internal scoring
models explicitly confirmed against BIS/EBA sources not to claim a published
match). Each already carries an accurate, specific caveat — the sourcing
pass's actual deliverable. No triage action needed beyond what's already
shipped; revisit individual entries only if a GitHub Discussion or issue
raises real demand for the more rigorous alternative.

## Sequencing

1. **Tier 0** (13 functions) — one PR, docstring-only, before or immediately
   after Day 0. Highest signal-to-effort: a regulated-industry user is the
   most likely reader to notice a citation/scope gap, and the fix is cheap.
2. **Tier 1** (3 functions) — one PR, needs a real per-function engineering
   decision (wire in vs. deprecate the parameter). Small, self-contained.
3. **Tier 2 + Tier 3** (12 functions combined) — one PR, docstring-only,
   no behavioural change, lowest risk of the batch.
4. **Tier 4** — no scheduled work; tracked as-is, opportunistic only.

None of tiers 1–4 need to land before Day 0. Tier 0 is a same-week
recommendation, not a hard gate — the caveats are already publicly visible
and accurate today, so the risk being mitigated is "gets missed," not
"actively misleading."

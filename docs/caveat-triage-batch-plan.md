# Caveat triage: a domain-batched plan

**Status:** proposed — no code changes in this PR, planning document only.
**Scope:** the 91 of 385 functions (23.6%) currently carrying a documented
`caveat` in `portal/functions.json`'s `formula.caveat` field, re-verified
against the live catalogue at time of writing.

---

## 1. Why batch by domain, and why credit-risk + operational first

Attempting all 91 in one pass isn't realistic — PR #306 (the only real data
point this repo has for "a caveat-triage effort actually happening")
resolved or narrowed 17 caveats in one PR-sized unit of work, and several of
those were substantial on their own (Geske closed-form derivation, exact CIR
transition sampling, Dupire finite-difference boundary handling — see
`CHANGELOG.md`). Batching by domain keeps each unit of work reviewable,
lets each batch regenerate `portal/functions.json` / the SDK / the MCP tool
catalogue exactly once (per the repo's existing generated-artifact
convention), and avoids a single sprawling diff across unrelated risk
domains.

**Credit-risk (18) and operational (14) are the two largest domains by
caveat count**, so they're the proposed starting batches purely on that
basis. But actually reading all 91 caveat texts (not just counting them)
surfaces something worth flagging before committing to that order — see
§3.

---

## 2. The 91, by domain

| Domain | Caveated |
|---|---|
| credit-risk | 18 |
| operational | 14 |
| derivatives | 13 |
| liquidity | 13 |
| regulatory | 11 |
| portfolio | 8 |
| alm | 7 |
| market-risk | 7 |

---

## 3. Count ≠ engineering opportunity — read every caveat before triaging

Reading all 91 caveat texts in full (not just tallying domains) sorts them
into two genuinely different categories:

- **Tier A — accurate disclosure, not a defect.** The caveat is the
  function correctly telling the caller what it does: "this is a rule-based
  lookup, not a numeric formula" (`loss_event_classification_basel`,
  `key_risk_indicator_kri_library`), "this is a bespoke internal model,
  confirmed against BIS/EBA sources not to match any specific published
  formula" (`corporate_credit_scoring_model`, `sovereign_credit_risk_assessment`,
  `wrong_way_risk_adjustment`), or "parameter X defaults to Y when not
  supplied" (`kmv_merton_distance_to_default`, `hqla_level_1_asset_classifier`).
  There is no code to write here — the honest fix is re-labelling or
  clarifying the catalogue entry, not an engineering task.
- **Tier C — a real, bounded gap against a named external standard**, the
  same shape as PR #306's genuine fixes: a specific regulatory clause not
  yet implemented, a simplified model standing in for a named published
  method, or a parameter that's accepted but silently unused where the
  function's own name implies it should matter.

**Credit-risk's 18, tiered:** 16 of 18 are Tier A (bespoke-by-design
disclosures or accurate parameter defaults — `credit_stress_testing`,
`macroeconomic_overlays_ecl`, `logistic_regression_pd_model`,
`irb_advanced_approach_capital`, etc.). Only **2 are Tier C**:
- `creditmetrics_portfolio_model` — currently a pass-through to the same
  one-factor Gaussian-copula Monte Carlo engine as `credit_var_monte_carlo`,
  not a distinct multi-state CreditMetrics implementation. A real build
  against Gupton/Finger/Bhatia (1997), *CreditMetrics — Technical Document*.
- `downturn_lgd_adjustment` — CRR Art. 181 requires downturn-conservative
  LGD; the current multiplicative scaling deliberately departs from the
  EBA/GL/2019/03 additive fallback. An opt-in additive mode (same pattern
  as PR #306's `currency_attribution`/`rebalancing_optimiser` opt-in modes)
  would close this cleanly.

**Operational's 14, tiered:** 13 of 14 are Tier A (rule-based
lookups/validators that are exactly what they claim to be —
`rcsa_risk_identification`, `near_miss_capture_framework`,
`kri_threshold_breach_detection`, etc.). Only **1 is Tier C**:
- `business_continuity_risk_score` — `rpo_hours` is accepted as a parameter
  but never used anywhere in the score computation; only RTO-vs-MTD and
  `bcp_maturity` actually drive the score. Worth a closer look specifically
  *because* it's not a disclosed simplification — it's a parameter whose
  own presence implies it should matter to a BCM score, and doesn't. This
  is the one item in these two batches that could plausibly be a real bug
  rather than an honest caveat.

So the two largest domains by caveat *count* contain a combined **3 real
Tier-C items** out of 32. That's a legitimate, useful outcome for a first
batch — but it means "biggest domain by count" and "most valuable domain to
triage" are different rankings, and it's worth saying so before the next
batch gets picked the same way.

---

## 4. Proposed batch plan

### Batch 1 — Credit-risk + Operational (as requested)

**Scope:** all 32 caveats across both domains.

1. **Administrative pass (cheap, high caveat-count reduction):** for the 29
   Tier-A items, update `scripts/data/function_formulas.json`'s caveat text
   to state plainly "this is an accurate description of the implemented
   method, not a simplification" where that's clearer than the current
   phrasing, and/or reclassify them out of the caveat count entirely if the
   business decision is that "honest disclosure of a rule-based lookup"
   shouldn't count toward the 23.6% headline figure the same way as an
   unresolved simplification does. **This is a product/disclosure decision,
   not an engineering one** — flagging it here rather than making the call
   unilaterally.
2. **Engineering pass (bounded, 3 items):** `creditmetrics_portfolio_model`,
   `downturn_lgd_adjustment`, `business_continuity_risk_score` — each
   independently scoped, each following the PR #306 pattern (opt-in mode or
   new implementation, cross-validated, existing default behaviour
   unchanged where a default exists).
3. Regenerate `portal/functions.json`, `pyvar_client/_generated/`,
   `plugins/mcp/pyvar_mcp/_generated/functions.py` once, at the end of the
   batch — not per-function.

**Estimate:** the administrative pass is largely mechanical (text edits,
no new tests beyond confirming the catalogue still round-trips through the
generator). The 3 engineering items are individually comparable in scope to
PR #306's `currency_attribution`/`downturn`-style additions — plausibly a
single PR-sized unit of work in total, well under the 91-caveat estimate
given in the earlier session discussion, precisely because this batch's
real engineering surface turned out to be small.

### Batch 2 — Regulatory (11) and Derivatives (13)

Proposed next, ahead of the remaining domains by raw count (liquidity 13,
portfolio 8, alm 7, market-risk 7), because a first read of their caveat
text shows a much higher density of genuine Tier-C gaps than credit-risk or
operational had:

- `solvency_ii_scr_credit_risk` — Art. 201's inter-counterparty correlation
  term (`V_inter`) is not computed; only the intra-counterparty variance
  term is. This is a *different*, still-open gap from the ~79%
  capital-understatement bug already fixed pre-launch (see
  `CHANGELOG.md`'s `[0.1.0]` notes) — worth being precise about that
  distinction if this gets raised externally.
- `crr2_large_exposure_limit` — missing the EUR 150m absolute-alternative
  threshold alongside the 25%-of-Tier-1 test; both are explicitly named in
  the regulation, so this is a well-specified, bounded addition.
- `callable_bond_pricer` / `puttable_bond_pricer` — a simplified fixed
  0.5/0.5-probability lattice, not a curve-calibrated Black-Derman-Toy
  tree. Real numerical work, comparable in scope to the Dupire
  finite-difference fix in PR #306.
- `hull_white_short_rate_model` — with constant theta this is literally the
  Vasicek model under a different name (the code calls
  `vasicek_interest_rate_model` directly); a genuine time-dependent
  theta(t) calibration to a market forward curve is the real gap.
- `convertible_bond_pricer` — a lower-bound decomposition only; no
  conversion optionality, equity volatility, or embedded call/put modelling.
  Largest single lift in this batch.
- `behavioural_modelling_nmds` — cites BCBS d368 but implements a bespoke
  decay blend rather than d368's actual standardised NMD slotting
  methodology. Large lift; may be better scoped as its own follow-up rather
  than folded into this batch.

This batch should get the same two-pass treatment (administrative
reclassification for the Tier-A majority, bounded engineering work for the
named Tier-C items) — not attempted in this planning document, since the
instruction was to batch by domain size starting with credit-risk and
operational specifically.

### Batches 3+ — Liquidity, Portfolio, ALM, Market-risk

Not yet triaged caveat-by-caveat. A skim of the liquidity domain's text
(§ conversation history) suggests a similar Tier-A-heavy pattern to
credit-risk/operational (several "not a single arithmetic formula, shown
as an indicator function" disclosures), but this should be confirmed the
same way — reading every caveat, not just counting them — before
committing to a batch order.

---

## 5. Process for each batch (repeatable)

1. Pull every caveat's full text for the batch's domain(s) from
   `portal/functions.json`'s `formula.caveat` field (not the truncated
   summary) — the tiering in §3 depended on reading full text, not
   headlines.
2. Split into Tier A (disclosure/reclassification only) and Tier C (real
   engineering scope, named against a specific external reference).
3. For Tier C items, follow the PR #306 pattern: cross-validate against an
   independent reference (QuantLib, a closed-form identity, a brute-force
   check, or the named regulation's own text) before claiming resolution;
   default behaviour stays unchanged unless the fix specifically requires
   changing it (verified via an explicit before/after key-set or value
   assertion, same as PR #306's tests did).
4. Regenerate the three downstream generated artifacts once per batch.
5. Update `scripts/data/function_formulas.json`'s caveat field per
   function — cleared for full resolutions, narrowed for partial ones,
   left as-is (or reworded for clarity) for Tier A.
6. One PR per batch, same governance as every other change in this repo —
   branch, PR, review, merge on explicit instruction.

## 6. Non-goals

- Not proposing to silently drop Tier-A caveats from the public-facing
  23.6% figure without a decision from Fibtec on whether "honest disclosure
  of a rule-based function" should count the same way as "known modeling
  simplification" — that's a disclosure-policy call, not something this
  plan makes unilaterally.
- Not proposing to force a fix onto every Tier-A item just to shrink the
  headline number — several of them (the bespoke internal models with no
  matching published formula) are, by their own caveat text, already
  "reasonable internal models" with nothing broken to fix.

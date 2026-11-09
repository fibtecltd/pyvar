# Phase 0 results: Claude Haiku 5.5 as the portal guide

**Status 2026-11-09: the model-quality gates are met on the point estimates for Haiku 5.5, and the assistant
work is ON HOLD.** Filippo raised two points that Phase 0 does not settle. (1) Whether a generated answer is
better than static catalogue text was never measured: a template built from the record passes every
mechanical check (the oracle, 1,924 of 1,924), and the judge's "useful" is an absolute yes or no, not a
comparison. (2) An Opus judge is ruled out as overkill, and it was the only automatic check for the answers
that are unfaithful without breaking a mechanical rule (about 4.5% of text answers). Section 7 has the
consequences; the numbers below stand as measurements. Three paid runs, $4.30 in all. With prompt v2 the
mechanical gates are met for all three text actions, the judge found 95.5% of the text answers faithful, and
the example values were already clean. One gate rests on a wide interval (`when` faithful 91.2%, 83.0 to
96.0). Along the way the runs exposed three defects in my own harness (a judge that was not shown the sibling
list, a grader that could not read names written inside LaTeX formulas, and an advice pattern that flagged
the noun "guarantee"); all are fixed in this PR.

- Run 1: a delegated agent, branch `docs/portal-ai-assistant-plan` at `7e146a6`, dev key
  (`pyvar/dev/anthropic-api-key`): Haiku 5.5 on 576 cases, Sonnet 5.5 on 144, Opus 5.5 judging 60 answers.
- Run 2: the same branch at `500cc80`: the Haiku answers re-judged by Opus 5.5 with the fixed judge, 200
  answers, no new generation.
- Run 3: the branch at `174b6d7`: run 1's answers re-graded offline with the fixed grader; prompt v2 on the
  three text actions with Haiku 5.5 (308 cases); Opus 5.5 judging 200 of the v2 answers.
- Nothing was committed, pushed or changed by any run. Numbers are the agents' reports, not re-computed here,
  except where stated; intervals are 95% Wilson. The 576-case sample covers 134 of the 385 functions (15 per
  domain plus every function with a worked example). The record shown to the model included each parameter's
  description.

## 1. Gates from the plan, as measured

Text actions: prompt v2, run 3. Example values: prompt unchanged, so run 1 and run 2.

| Gate | Result | Status |
|---|---|---|
| explain: at least 95% pass the mechanical checks | 129/134 = 96.3% (91.6 to 98.4) | Met (v1 was 118/134 = 88.1%) |
| when: at least 95% mechanical | 129/134 = 96.3% (91.6 to 98.4) | Met (v1 127/134 = 94.8%) |
| compare: at least 95% mechanical | 40/40 = 100% (91.2 to 100) | Met |
| explain: judge at least 90% faithful | 79/80 = 98.8% (93.3 to 99.8) | Met |
| when: judge at least 90% faithful | 73/80 = 91.2% (83.0 to 95.7) | Met on the point estimate; the lower bound is 83.0 |
| compare: judge at least 90% faithful | 39/40 = 97.5% (87.1 to 99.6) | Met |
| example values: at least 95% fit the request schema within 3 tries | 268/268 on the first try (lower bound about 98.6%) | Met |
| example values: judge at least 80% plausible | 75/80 = 93.8% (86.2 to 97.3) | Met, lower bound above 80 |
| refusals counted | 0 refusals, 0 truncated, 0 errors, 0 skipped in every run | Met |
| p50 latency under 3 s | v2 text 1.97 s (p95 3.96 s); v1 Haiku 1.57 s (p95 2.46 s) | Met |

Served model ids matched on every row (`claude-haiku-5-5` for all 576, `claude-sonnet-5-5` for all 144).

## 2. Haiku 5.5 on 576 cases, mechanical checks

| Action | Passed | Rate (95% interval) | Cost |
|---|---|---|---|
| explain | 118/134 | 88.1% (81.5 to 92.5) | $0.0285 |
| when | 127/134 | 94.8% (89.6 to 97.4) | $0.0338 |
| example:typical | 134/134 | 100% (97.2 to 100) | $0.0258 |
| example:stress | 134/134 | 100% (97.2 to 100) | $0.0249 |
| compare | 40/40 | 100% (91.2 to 100) | $0.0153 |

Cost $0.1283 for 576 cases, $0.000223 a case; 677,741 tokens in, 120,954 out. Projected to all 1,924
selections: **about $0.43** (a projection from the sample).

### What the 23 failing answers are

All 23 were listed with their specifics (25 failed checks in 23 answers). I checked the identifier failures
against the case records.

| Class | Checks | What it is |
|---|---|---|
| Length | 11 | **A mismatch, not quality.** The check enforces 900 characters (explain) and 1,100 (when), but the prompt asks for "3 to 5 sentences" and states no budget, and the bounds are my own choice, not a panel constraint. 8 of the 9 explain answers are 1 to 53 characters over (the other is 1,081); the 2 when answers are 1,161 and 1,168 |
| Unknown identifier, but the name is in the formula | 4 | **Grader false positives.** `rho_ij`, `D_max`, `max_len` and `n_clusters`, `collateral_value` and `sft_type` are all written in the record's LaTeX (`\rho_{ij}`, `D_{\max}`, `\text{max\_len}`). The grader looked for the plain string. Fixed (below) |
| Unknown identifier, truly absent | 1 | `segment_1` in `return_attribution_brinson`: an invented example name. A model error, minor |
| Number not in the record | 6 | **The model broke the rule it was given.** LCR "25%", NSFR "30", RSF "85%" (two answers), retail deposit run-off "30" (two answers): regulatory-looking figures from memory. Whether they are right was not checked. The judge, which allows textbook knowledge, did not flag them, so the mechanical check is the only guard against this |
| Does not name the function | 2 | `credit_portfolio_optimisation` and `sftr_securities_finance_report`. A style rule; the panel will show the name anyway |
| "guaranteed to" | 1 | `structural_hedge_optimisation` (when), which is also over length. The sentence was not read |

Sonnet's 13 failures are all length (`when` median 1,027 characters, 11 of 36 over 1,100; Haiku's median 837).

## 3. The judge, before and after the fix

The first judge (60 answers, $0.4646) called **0 of 12** `when` answers faithful, each time because the answer
named a function "not in the record". That was my defect: `judge.py` showed the judge the record, and for
compare the other record, but never the `<siblings>` list the generator was given and told to name from. Checked
against the case file, the five functions the first report names are real catalogue functions and each is in
the sibling list of a flagged `when` case (`digital_option_pricer` for `barrier_option_pricer`; the other four
fit by name, the report did not say which case each came from). The first report's reading, that the model
recommends siblings from memory, was wrong.

The judge now receives the same `<siblings>` block as the generator (`prompts.siblings_block`, one function for
both), its prompt says a listed sibling is supported, and a test pins it. The generator's requests are
byte-identical to the first run's for all 1,924 cases, so the run still describes this code.

Re-judged with the fixed judge, Opus 5.5, 40 answers per action (every `compare` case), 0 unparsed, 0 errors,
$1.5415:

| Action | n | Faithful | Useful | Plausible values |
|---|---|---|---|---|
| explain | 40 | 40 (100%; 91.2 to 100) | 40 | n/a |
| when | 40 | 36 (90.0%; 76.9 to 96.0) | 40 | n/a |
| compare | 40 | 38 (95.0%; 83.5 to 98.6) | 40 | n/a |
| example:typical | 40 | 40 | 40 | 39 (97.5%; 87.1 to 99.6) |
| example:stress | 40 | 40 | 39 | 36 (90.0%; 76.9 to 96.0) |
| all | 200 | 194 (97.0%; 93.6 to 98.6) | 199 (99.5%) | 75/80 (93.8%; 86.2 to 97.3) |

On the 12 `when` answers judged twice, faithful went from 0 to 10; over all 60 earlier answers from 46 to 57.
One example verdict also flipped (plausible, `srep_capital_add_on` stress), which is the judge's own noise.

## 4. What the judge found that is real

Six answers are unfaithful (3.0%, interval 1.4 to 6.4). None names a function outside the sibling list and the
catalogue; four of them are `when` answers that misread the record or a sibling's one-line summary:

1. `basel_capital_addon_multiplier` against `traffic_light_backtesting` (compare): says the record gives only the
   yellow-zone endpoints; its formula lists all five values (3.40 to 3.85).
2. `aifmd_risk_metrics` against `solvency_ii_scr_credit_risk` (compare): reverses the caveat; the SCR is at
   least as large as this result, so the function can understate capital.
3. `black_scholes_greeks` (when): implies a tree or Monte Carlo sibling handles path-dependent payoffs, but the
   list calls `monte_carlo_option_pricer` a European terminal-payoff pricer.
4. `countercyclical_capital_buffer` (when): says it cannot handle a single jurisdiction, but a one-entry map
   works; also says "the record points to" a sibling, which came from the sibling list.
5. `cva_sensitivity_cva_greeks` (when): says it is unclear whether `spread_bump` can be changed (it is a
   parameter) and misdescribes `expected_positive_exposure_epe`.
6. `gamma_cross_gamma_matrix` (when): misdescribes cross-gammas.

Five example sets are implausible (6.2% of 80; interval 2.7 to 13.8): cash returns of 18% against 9%; a
covariance on an annual scale next to daily means in one case and next to `periods_per_year` 252 in another;
notionals that do not match the spot rate in a cross-currency swap; and a placeholder trade size of 9999999999.

## 5. Haiku against Sonnet

On the same 144 cases (36 functions, all 8 domains, 4 actions, no compare):

| | Pass rate | Total cost | Per case |
|---|---|---|---|
| Haiku 5.5 | 142/144 = 98.6% (95.1 to 99.6) | $0.0305 | $0.000212 |
| Sonnet 5.5 | 131/144 = 91.0% (85.2 to 94.6) | $0.6053 | $0.004204 |

Sonnet costs about 20 times more per case and did no better on any action; its whole deficit is length. Its
answers were not judged, so this says nothing about its content quality. Nothing here argues for paying for it.

## 6. Run 3: prompt v2

Prompt v2 (`prompts.PROMPT_VERSION` = `v2-2026-11-08`) ends each text task with: name the function in the first
sentence; no number that is not in the record, including percentages, day counts and regulatory factors the
model is sure of; never say a result is guaranteed; at most 750 (explain), 950 (when) or 1,000 (compare)
characters (the hard limits stay 900, 1,100 and 1,200). The system prompt and the example-values tasks are
unchanged; all 770 example requests are byte-identical to v1's, so run 1's example results carry over.

**Re-grading run 1 offline** with the fixed grader (`regrade.py`) gave explain 118 to 120 of 134 and when 127 to
128, the same as the estimate in the previous version of this document, so the identifier fix is now a
measurement. Three answers flipped to pass; 20 still fail, and they are the length, number, invented-name and
"names no function" cases listed in section 2.

**v2 on 308 text cases** (`claude-haiku-5-5` on every row; 0 truncated, 0 refusals, 0 errors, 0 skipped):

| Action | v2 | v1 as run | v1 re-graded | Characters, v2 median / p95 / max | Over budget | Over hard limit |
|---|---|---|---|---|---|---|
| explain | 129/134 = 96.3% (91.6 to 98.4) | 118/134 | 120/134 | 671 / 827 / 950 | 27 | 3 |
| when | 129/134 = 96.3% (91.6 to 98.4) | 127/134 | 128/134 | 918 / 1,076 / 1,167 | 52 | 4 |
| compare | 40/40 = 100% (91.2 to 100) | 40/40 | 40/40 | 830 / 949 / 1,028 | 1 | 0 |

- **What changed it.** Almost all of explain's gain is length (median 727 to 671, over the hard limit 9 to 3).
  `when` barely moved, and **its answers got longer** (median 836 to 918, over the hard limit 2 to 4) although it
  has a 950-character budget: the stated budget acted as a target, not a ceiling.
- **The ten failures:** 7 length (explain 946, 942, 950 against 900; when 1,167, 1,142, 1,125, 1,122 against
  1,100), 2 numbers, 1 advice. The two numbers are both `retail_deposit_runoff_rate` ("30-day", the LCR horizon,
  a day count that is not in its record), so the figures-from-memory problem went from six answers to two
  answers of one function. The advice failure ("rather than a guarantee that the model fits") is a **false
  positive**: the pattern matched the noun. Fixed, with a test.
- **The new rules were followed without being parroted.** The first sentence names the function in 308 of 308
  answers; "prescribed factor", the phrase given as an example, appears in none (0 of 308). One cost: the answers
  open almost alike ("The X (`name`) computes..."), which reads mechanical.
- Cost $0.0799 for 308 cases ($0.000259 each), 372,143 tokens in and 85,394 out; latency p50 1.97 s, p95 3.96 s.

**Judge, v2 answers, Opus 5.5, 80 per action (all 40 `compare` cases), 0 unparsed, 0 errors, $1.4813:**

| Action | n | Faithful | Useful |
|---|---|---|---|
| explain | 80 | 79 (98.8%; 93.3 to 99.8) | 80 |
| when | 80 | 73 (91.2%; 83.0 to 95.7) | 80 |
| compare | 40 | 39 (97.5%; 87.1 to 99.6) | 39 |
| all | 200 | 191 (95.5%; 91.7 to 97.6) | 199 |

- **Against run 2** (the same 120 cases, each now a different generated answer): faithful went 40 to 40 in
  explain, 36 to 37 in when, 38 to 39 in compare. Five cases flipped to faithful and three to unfaithful.
  The unfaithful share is 9/200 = 4.5% (2.4 to 8.3) now and was 6/120 = 5.0% (2.3 to 10.5): **no measurable
  difference, so v2 did not change faithfulness**, and it did not hurt it.
- **Most unfaithful answers are one-off, not a property of the case.** Of the six that failed in run 2, five
  came back faithful in run 3; only `cva_sensitivity_cva_greeks` (when) failed both times. Small numbers, but it
  suggests a generate, judge, regenerate loop would clear most of them.
- **What the nine are:** none invents a function or parameter name. Three over-read a sibling's one-line summary
  (`nii_simulation_stress`, `black_scholes_european_option`, `cva_sensitivity_cva_greeks`: for instance, a tree
  pricer said to handle American or path-dependent payoffs when the list says only CRR and Boyle prices). The
  rest add detail the record does not support: each component charge, each factor's contribution, an ES-based
  estimate, notional exchanged at the start as well as the end, a floor that pyvar can "check".

## 7. What this means and what comes next

0. **On hold (2026-11-09), and why.** In this design nothing is typed and, under option B, nothing calls a model
   when a visitor clicks, so the model is a one-off drafting tool whose gain is authoring hours, not a runtime
   capability. Whether its text beats what the catalogue already shows is unmeasured. Where a gain is plausible:
   `when` and `compare` (no static equivalent exists; they are also where unfaithful answers concentrate) and
   example values for the functions that have no tested worked example. For `explain` it is probably small: the
   record already has a summary, a description, the formula and symbol map, and, since this PR, a description for
   every parameter. The cheapest honest test needs no judge: a blind side-by-side, about 20 pairs, the template
   or catalogue text against Haiku's answer, read by someone who knows the domain. Without an automatic
   faithfulness check, what is left for model-written text is a person reading all of it, a scope cut to what
   the graders can fully verify (names, numbers, schema shape), or accepting the unreviewed 4.5%. The parameter
   descriptions in this PR are the static part of the same goal (what an input means) and need no model.
   Section 9 sets up both checks; its 9.5 has the blind result (the model's answer was picked in 11 of 12 pairs,
   no error ticked), and neither cheaper judge met the thresholds against Opus (9.8). Items 1 to 8 below are the position before this was raised; items 3 and 4
   assume the Opus judge.
1. **Phase 0 is passed on the point estimates.** Every gate in section 1 is met; `when` faithfulness (91.2%) and
   the schema and plausibility gates rest on intervals whose lower bounds are 83.0, 98.6 and 86.2.
2. **Model: Haiku 5.5.** It meets the gates, about $0.0002 to $0.0003 a case. Sonnet 5.5 costs about 20 times
   more and did no better on the mechanical checks (section 5); its content quality was never judged.
3. **Option B is the design to build.** About 4.5% of text answers are unfaithful and about 6% of example sets
   implausible. Under runtime generation (A) visitors would see those unreviewed. Under B the pipeline is:
   generate; the graders (a failing check regenerates, up to 3 tries, as the example action already does); judge
   every answer with Opus 5.5 and regenerate the unfaithful ones; a person reads what still fails after the
   retries, plus a random 5% to catch what the judge misses. The mechanical gates then work as filters, not as
   a rate a visitor sees.
4. **What that costs** (projections from the runs): generating all 1,924 selections about $0.45; judging every
   answer about $14 at the observed $0.0074 each (the 1,154 text answers alone about $8.5), plus roughly 10%
   for regeneration; a person reading perhaps 100 to 150 answers, against about 16 hours to read all 1,924.
5. **Keep prompt v2 as it is.** A further iteration is not worth a run: under B a failing answer is regenerated.
   If `when` length matters, lower its budget (it runs at about 918 against 950); that is a pipeline setting.
6. **Residual cases go to the person:** `retail_deposit_runoff_rate` fails the figures rule in both runs, so a
   retry will probably not fix it; `cva_sensitivity_cva_greeks` (when) was judged unfaithful both times.
7. **Open before building:** (a) the panel's layout, which fixes the real length limits (900, 1,100 and 1,200 are
   my choices); (b) whether the judge should be Opus for all 1,924 answers or a cheaper model with Opus on the
   flagged ones; (c) where the generated answers live (a static JSON the portal serves, with a drift test that
   regenerates an entry when its function record changes). The plan's Phases 1 to 3 were written for a runtime
   chat route and need rewriting for B.
8. **Harness note:** `cases.py` imports the app, so setup needs `pip install -r requirements.txt -r
   requirements-ci.txt`, not only the harness requirements. The README says so.

## 8. Spend

| Step | Estimate | Actual |
|---|---|---|
| Run 1: smoke (4 Haiku cases) | $0.01 | $0.0012 |
| Run 1: Haiku, 576 cases | $0.40 | $0.1283 |
| Run 1: Sonnet, first 144 cases | $1.90 | $0.6053 |
| Run 1: judge, 60 answers (before the fix) | $0.80 | $0.4646 |
| Run 2: judge, 200 answers (fixed judge) | $1.70 | $1.5415 |
| Run 3: Haiku, v2 text actions, 308 cases | $0.08 | $0.0799 |
| Run 3: judge, 200 v2 answers | $1.80 | $1.4813 |
| **Total** | | **$4.30** (caps $4.50, $2.00 and $2.45) |

The dev secret was read with `GetSecretValue` (6 times in run 1, once in run 2, twice in run 3) and was a plain
string. No errors file was created for the generation runs; the judge's error file was empty each time. The
judge overwrites its output files rather than resuming, so run 1's verdicts were kept as
`judgments_v1_no_siblings.jsonl`.

## 9. Phase 0b: does the model beat static text, and what replaces the Opus judge? (blind read and judge calibration done 2026-11-09)

Filippo chose to test the gain first (2026-11-09). Two checks, neither uses an Opus judge, and **the decision rules
below were written before either has been run.**

### 9.1 A blind side-by-side, read by a person

- **Pairs:** 12, four each of `explain`, `when` and `compare`, chosen by a hash of the fixed seed `gain-test-1`, a
  new domain each time where possible (`side_by_side.py pick`), so the choice is repeatable and not made by
  looking at answers:
  `repricing_gap_analysis:explain`, `altman_z_score_credit_scoring:explain`, `liquidity_transfer_pricing:explain`, `frequency_distribution_fitting:explain`;
  `expected_shortfall_contribution:when`, `nii_simulation_stress:when`, `contingency_funding_plan_trigger:when`, `rcsa_risk_identification:when`;
  `countercyclical_capital_buffer:compare:capital_conservation_buffer`, `black_scholes_greeks:compare:monte_carlo_option_pricer`, `asset_liability_mismatch_index:compare:structural_hedge_optimisation`, `black_litterman_model:compare:maximum_sharpe_ratio_portfolio`.
- **Model side:** Haiku 5.5 with prompt v2, the answers of run 3. **As run:** run 3's files were lost with the
  agent machine that made them, so the 12 are a fresh draw of the same model and prompt (one run, $0.0032, all 12
  complete and passing the graders on the first try). The case file was regenerated from the repository and is
  byte-identical to the original (sha256 starting `c57a3b30`), and `pick` returned the same 12 ids.
- **Static side:** the best the catalogue allows with no model, built from the record by `side_by_side.py`:
  for `explain` the summary, the description (Sphinx roles removed) and the inputs with their descriptions; for
  `when` the summary and the sibling list (up to six); for `compare` both summaries and the inputs of each. This
  is a hard baseline on purpose.
- **Reader and page:** a person who knows the domain, on a page where each pair shows two answers in random order
  (a hash of the seed and the case id) without saying which is which, with "A helps more", "B helps more" or "about
  the same", and a box to tick on an answer that contains an error or states something the other does not support.
  The two styles differ, so the reader may guess; the instruction is to pick by what helps a visitor. The key stays
  with whoever built the page.
- **Example values are not in this test.** Only 23 of 385 functions have a tested worked example, so the static
  alternative exists for 6% of functions; there the model's case is coverage, not quality, and its risk is the 6%
  implausible sets.
- **Decision rule.** The model earns its place for an action if it is picked in at least 3 of that action's 4
  pairs **and** at most 1 of its 4 answers is ticked as containing an error. "About the same" counts for neither
  side. Twelve pairs read by one expert is a sanity gate, not a statistic: 2 of 4 is read as no clear gain.
  - Earns `when` and `compare` only: build those two, `explain` stays static.
  - Earns all three: build all three.
  - Earns none: stop spending on model-written text and build the static help panel.

### 9.2 A cheaper judge, measured against the Opus verdicts already paid for

About 400 answers already carry an Opus verdict (run 2: 200, of which 120 text and 80 example values; run 3: 200
text), among them 15 unfaithful text answers and 5 implausible example sets. A cheaper judge run on the same
answers (`judge.py --judge-model ... --tag NAME`, which keeps the Opus files) is compared with them by
`compare_judges.py`.

- **Recall** is the share of what Opus flagged that the cheap judge flagged (what would slip through). **False-alarm
  rate** is the share of what Opus passed that the cheap judge flagged (the review burden).
- **Thresholds, fixed now:** recall at least 0.75 and false alarms at most 0.30, counted on the text actions for
  `faithful` and on the example actions for `plausible_values`; fewer than 8 reference flags is reported as "cannot
  tell", never as a pass. With 15 flags the interval around a recall is wide, and the 95% interval is printed.
- **Opus is the reference, not the truth:** it is a model too (one verdict changed between two runs on 120 repeated
  cases), so what is measured is agreement with it.
- **Staged to save money:** Haiku 5.5 first (about $0.08). Sonnet 5.5 only if Haiku does not meet the thresholds
  (about $1.5). The estimates scale the observed $0.0074 an Opus verdict by the price ratios (Haiku 1/40, Sonnet 1/2).
- **Run on 2026-11-09, result in 9.8.** The original Opus verdicts were lost with the machine that made them, so
  the reference was rebuilt: new Opus verdicts on a freshly generated answer set (prompt v3, 9.7).

### 9.3 What the two results mean together

| Side-by-side | A cheap judge meets the thresholds | Then |
|---|---|---|
| Earns `when` and `compare` (or all three) | Yes | Build option B for those actions: generate, graders, the cheap judge, regenerate or flag, a person reads what is flagged plus a random 5% |
| Earns them | No | Build only if you accept a person reading every model-written answer (about 770 `when` and `compare` answers, roughly 6 hours at 30 seconds each) |
| Earns none | Either | Static help panel from what the catalogue has: summary, parameter descriptions, formula, sibling lists, tested examples. No model |

### 9.4 Tools

`side_by_side.py` (`pick`, `export`, `build`), `compare_judges.py` and `judge.py --tag`, with tests in
`tests/test_assistant_gain_test.py`. The agent run exports the 12 model answers (no cost) and runs the cheap judges;
the page is built from the catalogue and the exported answers, and the key is not shown to the reader.

### 9.5 Result of the blind read (2026-11-09)

One reader (Filippo), on the page `side_by_side.py build` made from the 12 answers above. The key file was kept
by whoever built the page until the picks were in (its sha256 starts `5e6e80d7661c3ecc`).

| Action | Model picked | Static picked | About the same | Errors ticked | Rule: at least 3 of 4, at most 1 error |
|---|---|---|---|---|---|
| explain | 3 | 1 (`liquidity_transfer_pricing`) | 0 | 0 | earned |
| when | 4 | 0 | 0 | 0 | earned |
| compare | 4 | 0 | 0 | 0 | earned |

By the rule fixed in 9.1 **the model earns all three actions: build all three.** What that does and does not show:

- **A sanity gate, not a statistic.** One reader and 12 pairs. The two styles differ (prose against a field
  listing), so the reader could often tell them apart; the instruction was to pick by what helps a visitor, and 11
  of 12 picks went to the model with no "about the same".
- **No error was ticked, but that is not a faithfulness rate.** A tick records what the reader noticed, and the
  earlier judge found 4.5% of text answers unfaithful, about 0.5 expected in 12. The result shows that a visitor
  prefers the model's answer, not that it is safe to publish unreviewed. That gap is what the cheaper judge was
  meant to close, and it has not been run (9.2).
- **The answers are a fresh draw** of the same model and prompt, not run 3's text (9.1).

The reader's one note, on `repricing_gap_analysis` (explain): the closing sentence "The record does not say how
pyvar sets its bucket boundaries or what output format it returns, so check those details before relying on
them" signals that something is missing. It was not ticked as an error, and that answer was still picked. Counted
over the 12 model answers, 8 say "the record" (the prompt's word for the data the model was given; a visitor has
no idea what it refers to) and 7 say that the record does not say or give something. The v2 rule that stops
invented figures produced this phrasing. A fix is a prompt change (name the pyvar documentation, or leave the
caveat out) and is not made here.

### 9.6 What the result leaves open

The first row of 9.3 applies, and which of its two outcomes follows depends on a measurement that does not exist
yet: whether a cheaper judge flags what Opus flags. Either pay for new Opus reference verdicts (9.2), or accept a
person reading every model-written answer. Neither is decided here. Filippo chose to pay (2026-11-09), after the
wording fix in 9.7.

### 9.7 Prompt v3 and the re-planned calibration (2026-11-09)

**The wording fix.** The system prompt now tells the guide that the visitor cannot see the record, the sibling
list or the schema: where an answer rests on them it says "pyvar's documentation", and it never writes "the
record" or "sibling" (it says "related function"). The gap sentence became "say that pyvar's documentation does
not". `PROMPT_VERSION` is `v3-2026-11-09`. A new grader check, `visitor_wording`, fails an answer that contains
"the record", "the function record" or "sibling" (and not "track record", "a record of losses" or
"record-keeping"). Without it nothing would show whether the fix worked. Run on the 12 answers of 9.1 it flags 9
(8 for "the record", one more for "sibling"); the oracle still passes 1,924 of 1,924 cases and the null baseline
0 of 576.

**Not changed:** the caveat itself. A v3 answer may still end with "pyvar's documentation does not say ...", which
the reader found signals something missing. Only the vocabulary was fixed; whether the closing caveat should go
is decided after reading v3 answers.

**The re-planned calibration.** The reference set is new: Haiku 5.5 with prompt v3 on all 308 text cases (134
`explain`, 134 `when`, 40 `compare`), judged by Opus 5.5 (the reference) and by Haiku 5.5, then Sonnet 5.5 only if
Haiku does not meet the thresholds of 9.2. It is judged on v3 because v3 is what would be published. Faithfulness
only: example values are left out (`plausible_values` had 5 Opus flags of 80, under the 8 needed, and reaching 8
would take about 130 judged example sets). Expected cost about $2.4 (generation $0.08, Opus $2.3, Haiku $0.06);
up to about $3.5 if Sonnet is needed. If Opus flags fewer than 8 of the 308, the result is "cannot tell" and is
reported as such; the sample is not widened without a decision.

### 9.8 Result of the judge calibration (2026-11-09)

Run on the dev key as planned in 9.7. Haiku 5.5 wrote the answers with prompt v3 for all 308 text cases (308 ok, no
truncation or refusal, $0.08); Opus 5.5 judged all 308 as the reference ($2.34); Haiku 5.5 ($0.06) and, because
Haiku missed, Sonnet 5.5 ($1.10) judged the same. Total $3.58, every verdict parsed. The flagged cases are in
`docs/assistant-judge-calibration-v3.csv` (47 rows; F flagged, P passed; the other 261 cases passed all three).
The answer texts were not kept: they were on the temporary machine.

| Judge | Recall of Opus's flags (95% interval) | False alarms | Kappa | Against 9.2 |
|---|---|---|---|---|
| Haiku 5.5 | 4 of 22 = 0.18 (0.07 to 0.39) | 15 of 286 = 0.05 | 0.14 | does not meet |
| Sonnet 5.5 | 9 of 22 = 0.41 (0.23 to 0.61) | 11 of 286 = 0.04 | 0.39 | does not meet |

The thresholds are recall at least 0.75 and false alarms at most 0.30: both judges fail on recall alone, and their
false alarms are low. Only `when` has the 8 Opus flags needed to read on its own (17): Haiku caught 2, Sonnet 8;
`explain` (4 flags) and `compare` (1) read "cannot tell". Flagging when either cheap judge flags catches 12 of 22
(0.55) at 25 false alarms of 286 (0.09), still under 0.75. Ten of the 22 were flagged by neither judge, one by all
three. The figures were recomputed from the CSV with `compare_judges.py`'s own functions and match the agent's.

**What Opus flagged.** 22 of 308 (7.1%): `explain` 4 of 134 (3.0%), `when` 17 of 134 (12.7%), `compare` 1 of 40
(2.5%). The earlier runs found about 4.5% overall; one draw per prompt cannot say whether v3 changed that. By the
first 80 characters of Opus's issues (so approximate): 6 say pyvar's documentation omits something it does
contain ("says the documentation does not say X, but the record gives it"), 8 are `when` answers that describe or
recommend a related function beyond what its summary says, and 8 misdescribe the function itself (gamma, a
risk-aversion parameter, the MiFID output fields, a swap's cash-flow direction and others). The first group comes
from the rule that tells the model to say when the documentation is silent, the same rule that produced the
closing caveat the reader noted (9.5).

**Other results of the run.** `visitor_wording` failed 8 of 308 answers (2.6%; 4 for "the record", 4 for
"sibling"), against 9 of the 12 v2 answers, and a failing answer is caught mechanically. Grader pass: `explain`
128 of 134 (v2: 129), `compare` 40 of 40 (v2: 40), and **`when` 117 of 134 = 87.3% (v2: 129 of 134 = 96.3%)**,
with 12 length failures against 4 in v2. At about 3% (4 of 134) a count of 12 is unlikely to be chance, and the
new phrases are longer ("pyvar's documentation" for "the record", "related function" for "sibling"), a likely
but untested cause. A failing answer would be regenerated, so it costs calls, not correctness.

**What it does and does not show.** Opus is the reference, not the truth. Nobody has read the 22 flagged answers
against their records (the texts were lost), so what is measured is agreement with Opus, and how many of its 22
are real errors is unknown. Within that, neither cheaper judge can replace it here: Opus's flags are mostly
claims that must be checked against detail in the record (what a related function's summary says, whether the
documentation really omits something), and the cheaper judges flagged mostly other answers (kappa 0.14 and 0.39).

By 9.3 (the model earns all three actions, no cheaper judge meets the thresholds), the outcome is to build only if
a person reads every model-written answer.

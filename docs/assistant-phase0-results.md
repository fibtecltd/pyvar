# Phase 0 results: Claude Haiku 5.5 as the portal guide

**Status 2026-11-08: conditional go, for Haiku 5.5 and option B (build-time generation, a person reads the
answers).** Two paid runs, $2.74 in all. The first run exposed two defects in my own harness (a judge that was
not shown the sibling list, and a grader that could not read names written inside LaTeX formulas); both are
fixed in this PR. With the judge fixed, every judge gate is met or sits at its edge, and the example values
are clean. What is left is a prompt that never states its length budget and six answers that quote a
regulatory figure from memory. Section 6 says what comes next.

- Run 1: a delegated agent, branch `docs/portal-ai-assistant-plan` at `7e146a6`, dev key
  (`pyvar/dev/anthropic-api-key`): Haiku 5.5 on 576 cases, Sonnet 5.5 on 144, Opus 5.5 judging 60 answers.
- Run 2: the same branch at `500cc80`: the Haiku answers re-judged by Opus 5.5 with the fixed judge, 200
  answers, no new generation.
- Nothing was committed, pushed or changed by either run. Numbers are the agents' reports, not re-computed here,
  except where stated; intervals are 95% Wilson. The 576-case sample covers 134 of the 385 functions (15 per
  domain plus every function with a worked example). The record shown to the model included each parameter's
  description.

## 1. Gates from the plan, as measured

| Gate | Result | Status |
|---|---|---|
| explain: at least 95% pass the mechanical checks | 118/134 = 88.1% (81.5 to 92.5) | **Not met.** 9 of 16 failures are length; 120/134 = 89.6% once the grader fix below is counted (arithmetic, not re-graded) |
| when: at least 95% mechanical | 127/134 = 94.8% (89.6 to 97.4) | **0.2 short**; 128/134 = 95.5% with the grader fix (arithmetic) |
| compare: at least 95% mechanical | 40/40 = 100% (91.2 to 100) | Met |
| explain: judge at least 90% faithful | 40/40 = 100% (91.2 to 100) | Met |
| when: judge at least 90% faithful | 36/40 = 90.0% (76.9 to 96.0) | At the gate on the point estimate; the interval is too wide to claim it |
| compare: judge at least 90% faithful | 38/40 = 95.0% (83.5 to 98.6) | Met on the point estimate |
| example values: at least 95% fit the request schema within 3 tries | 268/268 on the first try (lower bound about 98.6%) | Met |
| example values: judge at least 80% plausible | 75/80 = 93.8% (86.2 to 97.3) | Met, lower bound above 80 |
| refusals counted | 0 refusals, 0 truncated, 0 errors, 0 skipped in every run | Met |
| p50 latency under 3 s | Haiku 1.57 s (p95 2.46 s); Sonnet 2.39 s (p95 4.09 s) | Met |

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

## 6. What this means and what comes next

1. **Model: Haiku 5.5.** Examples fit the schema every time, no refusals or truncation, fast, about $0.0002 a case.
2. **Option B.** A generated answer is unfaithful about 3% of the time and an example set implausible about 6%.
   Under runtime generation (A) visitors would see those unreviewed; under B they are caught before publication.
   **B also changes what the 95% mechanical gate means:** at build time a failing check triggers regeneration (as
   the example action already retries up to 3 times), so those checks are filters, not a rate a visitor sees. The
   gates that decide are the judge's faithfulness and a person's read.
3. **Review is the real cost.** Reading all 1,924 answers is about 16 hours at 30 seconds each. A workable form:
   judge every answer with Opus 5.5 (about $15 at the observed $0.0077 each), have a person read what the judge or a
   grader flags (roughly 100 answers at the observed rates) plus a random 5% to catch what the judge misses.
4. **Prompt v2, written, not yet run** (`prompts.PROMPT_VERSION` = `v2-2026-11-08`, recorded in every run's
   summary). Each of the three text tasks now ends with: name the function in the first sentence; do not write
   any number that is not in the record, including percentages, day counts and regulatory factors you are sure
   of; never say a result is guaranteed; at most 750 (explain), 950 (when) or 1,000 (compare) characters. The
   hard limits stay 900, 1,100 and 1,200, so the budgets leave about 17% margin. The system prompt and the two
   example-values tasks are unchanged: all 770 example requests are byte-identical to v1's, so run 1's example
   results carry over, and the new rules are kept out of those tasks because there the model must write numbers
   that are not in the record. The text requests grow by about 119 tokens. Whether to also widen the limits is a
   design choice that belongs with the panel's layout, which does not exist yet.
5. **Grader fix, done:** names in the record's LaTeX are now recognised (`graders._latex_plain`, with a test).
   The oracle still passes 1,924 of 1,924 and the null 0 of 576. The six unsupported figures and the other
   failure classes above are untouched by it. `regrade.py` (new, offline) grades a finished run's saved answers
   again, so the effect on run 1 is measured in the next round instead of estimated.
6. **Run 3, prepared:** the v2 text actions on Haiku 5.5 (308 cases, about $0.08), judged at 80 answers per
   action (explain 80, when 80, compare all 40; about $1.8) with the hash order unchanged, so the first 40 of
   each action are the cases run 2 judged and v1 and v2 can be compared case by case. This also puts `when`
   faithfulness on 80 answers instead of 40 (the 95% interval around 90% narrows from 19 to about 13 points).
7. **Harness note:** `cases.py` imports the app, so setup needs `pip install -r requirements.txt -r
   requirements-ci.txt`, not only the harness requirements. The README says so.

## 7. Spend

| Step | Estimate | Actual |
|---|---|---|
| Run 1: smoke (4 Haiku cases) | $0.01 | $0.0012 |
| Run 1: Haiku, 576 cases | $0.40 | $0.1283 |
| Run 1: Sonnet, first 144 cases | $1.90 | $0.6053 |
| Run 1: judge, 60 answers (before the fix) | $0.80 | $0.4646 |
| Run 2: judge, 200 answers (fixed judge) | $1.70 | $1.5415 |
| **Total** | about $4.8 | **$2.74** (caps $4.50 and $2.00) |

The dev secret was read with `GetSecretValue` (6 times in run 1, once in run 2) and was a plain string. No errors
file was created for the generation runs; the judge's error file was empty both times. The judge overwrites its
output files rather than resuming, so run 1's verdicts were kept as `judgments_v1_no_siblings.jsonl`.

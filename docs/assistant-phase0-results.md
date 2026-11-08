# Phase 0 results: Claude Haiku 5.5 as the portal guide (first paid run)

**Status 2026-11-08: neither a pass nor a fail yet.** The model and the approach hold up on everything that
was measured cleanly. Two gates are missed as measured, and one could not be measured because of a defect in
the judge (found while writing this up, fixed, not yet re-run). Recommendation: **Haiku 5.5, option B
(build-time generation, a person reads the answers)**, after one more cheap round (section 6).

Run by a delegated agent from `docs/plan-portal-ai-assistant.md` section 7 on branch
`docs/portal-ai-assistant-plan` at `7e146a6`, with the dev key (`pyvar/dev/anthropic-api-key`). Nothing was
committed, pushed or changed by the run. Numbers are the agent's report, not re-computed here, except where
stated. The 576-case sample covers 134 of the 385 functions (15 per domain plus every function with a worked
example), not the whole catalogue. The record shown to the model included each parameter's description.

## 1. Gates from the plan, as measured

| Gate | Result | Status |
|---|---|---|
| explain: at least 95% pass the mechanical checks | 118/134 = 88.1% (95% interval 81.5 to 92.5) | **Not met.** 9 of its 16 failures are the length check |
| when: at least 95% mechanical | 127/134 = 94.8% (89.6 to 97.4) | **Not met**, 0.2 points short and inside the noise; 7 failures |
| compare: at least 95% mechanical | 40/40 = 100% (91.2 to 100) | Met (small n) |
| explain, when, compare: judge at least 90% faithful | explain 12/12; compare 10/12; **when 0/12 is invalid** (section 3) | explain met at n=12; compare 83% at n=12, interval far too wide to call; when **not measured** |
| example values: at least 95% fit the request schema within 3 tries | 268/268 on the first try (lower bound about 98.6%) | Met |
| example values: judge at least 80% plausible | 21/24 = 87.5% (69.0 to 95.7) | Met at n=24; the lower bound is under 80 |
| refusals counted | 0 refusals, 0 truncated, 0 errors, 0 skipped in both runs | Met |
| p50 latency under 3 s | Haiku 1.57 s (p95 2.46 s); Sonnet 2.39 s (p95 4.09 s) | Met |

Served model ids matched on every row (`claude-haiku-5-5` for all 576, `claude-sonnet-5-5` for all 144).

## 2. Haiku 5.5 on 576 cases

| Action | Passed | Rate (95% interval) | Cost |
|---|---|---|---|
| explain | 118/134 | 88.1% (81.5 to 92.5) | $0.0285 |
| when | 127/134 | 94.8% (89.6 to 97.4) | $0.0338 |
| example:typical | 134/134 | 100% (97.2 to 100) | $0.0258 |
| example:stress | 134/134 | 100% (97.2 to 100) | $0.0249 |
| compare | 40/40 | 100% (91.2 to 100) | $0.0153 |

- Failed checks, counted across all answers: `length_ok` 11, `numbers_supported` 6, `identifiers_known` 5,
  `mentions_function` 2, `no_advice` 1 (25 failed checks over 23 answers).
- **The length failures are a mismatch, not a quality problem.** The check enforces 900 characters for
  explain and 1,100 for when, but the prompt asks for "3 to 5 sentences" and never states a character budget.
  One failing explain is 914 characters against 900.
- Cost $0.1283 for 576 cases, $0.000223 per case; 677,741 tokens in, 120,954 out. Projected to all 1,924
  selections: **about $0.43** (a projection from the sample).

## 3. The judge result for `when` is a harness defect, not a finding about the model

The judge (Opus 5.5, 12 answers per action, 60 in all, 0 unparsed, $0.4646) called **0 of 12** `when` answers
faithful, each time because the answer names a function that "is not in the record". The agent read this as
the model recommending siblings from memory. **That reading is wrong.** `judge.py` showed the judge the
function record and, for compare, the other record, but never the `<siblings>` list that the generator was
given and told to name from. Checked against the case file, for the five functions the report names as
"not in the record": each is a real catalogue function, and each is in the sibling list of a flagged `when`
case. `digital_option_pricer` is listed for `barrier_option_pricer` (the report ties them); the others fit
the same way by their names (`basel_iii_tier1_ratio` for `basel_iii_cet1_ratio`,
`christoffersen_independence_test` for `kupiec_pof_test`, `effective_duration_alm` for
`modified_duration_balance_sheet`; the report did not say which case each came from), and
`crr2_large_exposure_limit` is in the sibling lists of `combined_buffer_requirement` and
`countercyclical_capital_buffer`. The model did what it was asked. The rest of the judge notes were not seen.

Fixed in this PR: the judge now receives the same `<siblings>` block the generator saw (`prompts.siblings_block`,
one function for both), the judge prompt says a sibling named from that list is supported, and a test pins it.
The generator's requests are byte-identical to the paid run's for all 1,924 cases (checked), so the run still
describes this code. `when` faithfulness has to be re-judged.

Judge results for the other actions are unaffected, since they never use the list:

| Action | Faithful | Useful | Plausible values |
|---|---|---|---|
| explain | 12/12 | 12/12 | n/a |
| when | invalid | 12/12 | n/a |
| compare | 10/12 | 12/12 | n/a |
| example:typical | 12/12 | 12/12 | 11/12 |
| example:stress | 12/12 | 12/12 | 10/12 |

## 4. Real problems the judge found (not artefacts)

- `compare`, `basel_capital_addon_multiplier` against `traffic_light_backtesting`: says only the two yellow-zone
  endpoints (3.40 and 3.85) are given, but the record lists all five values. A genuine error.
- Example values, `srep_capital_add_on` stress: a Pillar 1 requirement of 45m on 900m of RWA is 5%, below the 8%
  minimum. `risk_parity_portfolio` typical: annual-scale covariances and returns combined with
  `periods_per_year` 252, which implies about 20% daily volatility. 3 of 24 example sets (12.5%) were judged
  implausible, with a wide interval.
- Mechanical failures other than length: one identifier (`rho_ij`, a formula symbol the answer wrote as a
  snake_case word) looks like a **grader false positive** rather than a model error. The other four identifier
  failures and the six number failures were not itemised; they need triage before anyone tunes the model or the
  grader.

## 5. Haiku against Sonnet

On the same 144 cases (36 functions, all 8 domains, 4 actions, no compare):

| | Pass rate | Total cost | Per case |
|---|---|---|---|
| Haiku 5.5 | 142/144 = 98.6% (95.1 to 99.6) | $0.0305 | $0.000212 |
| Sonnet 5.5 | 131/144 = 91.0% (85.2 to 94.6) | $0.6053 | $0.004204 |

Sonnet costs about 20 times more per case and did no better on any action. Its whole deficit is length:
`when` 25/36 against Haiku's 36/36, with all 13 Sonnet failures being `length_ok` (median 1,027 characters, 11
of 36 over the 1,100 limit; Haiku's median is 837). Sonnet's answers were not judged, so this says nothing about
its content quality. Nothing here argues for paying for Sonnet.

## 6. What this means and the next round

1. **Model: Haiku 5.5.** Clean on examples (schema 100%), no refusals or truncation, fast, and about $0.0002 a case.
2. **Option A against B: B.** A generated answer is wrong or implausible in a visible fraction of the sample
   (compare 2 of 12, examples 3 of 24, both small samples), and a runtime call would show those to visitors
   unreviewed. Generating all 1,924 once costs about $0.43, so the money is not the issue; **review is**.
   Reading every answer is real work (at 30 seconds each, about 16 hours), so the workable form is: the
   mechanical graders and the judge as filters, a person reading everything they flag plus a random tenth.
3. **Fix the length mismatch.** Either state a character budget in each task prompt (for example 800 for
   explain and compare, 1,000 for when) or move the limits to what the panel can show. This is a product
   decision about the panel's space; either way Haiku must be re-run (about $0.13).
4. **Re-judge with the fixed judge**, with a larger sample, `--per-intent 40` (200 answers, about $1.7 at the
   observed $0.0077 per answer plus the added sibling text; all 40 `compare` cases are included). The 95%
   interval around a 90% rate is about 35 points wide at n=12 and about 19 at n=40, so n=40 can separate 95%
   from 80% but not 95% from 90%. If a decision hinges on the 90% gate, judge every `when` and `compare`
   answer instead (174 answers, about $1.4).
5. **Triage every mechanical failure** (case id, check, offending token or number) to separate grader false
   positives from model errors, before changing either.
6. Harness note from the run: `cases.py` imports the app, so setup needs `pip install -r requirements.txt -r
   requirements-ci.txt` (numpy, scipy, numba), not only the harness requirements. The README now says so.

## 7. Spend

| Step | Estimate | Actual |
|---|---|---|
| Smoke (4 Haiku cases) | $0.01 | $0.0012 |
| Haiku, 576 cases | $0.40 | $0.1283 |
| Sonnet, first 144 cases | $1.90 | $0.6053 |
| Judge, Opus 5.5, 60 answers | $0.80 | $0.4646 |
| **Total** | about $3.1 | **$1.20** (cap $4.50) |

`GetSecretValue` on the dev secret was called 6 times; the secret was a plain string. No errors file was
created for the smoke, Haiku or Sonnet runs; the judge's error file was empty.

# Plan: AI-assisted verification of pyvar by Claude Code (Opus 5.5)

**Status: draft, 2026-11-13.** Decided by Filippo on 2026-11-13: the pilot function is `historical_expected_shortfall`, and the work runs in Filippo's own environment. Not yet decided: the human who signs off (section 8). Proposed, not approved: the budget (section 7).

## 1. What this is, and what it is not

`README.md` says pyvar is not independently validated for regulatory use, and `docs/pyvar-validation-partners.md` sets the conditions for a validator: they did not contribute to the code or tests, and because the code was written with substantial AI assistance, a human independent review carries extra weight.

Opus 5.5 is from the same vendor and model family that helped write that code. Its mistakes can correlate with the writer's: a misreading of a formula that Claude made once, it can make again. So this plan does **not** produce independent validation, and nothing it produces may be described as such. It produces **AI-assisted verification**, accountable to a named human, which is useful in its own right:

- it re-derives a formula from primary sources without sight of the engine's code;
- it compares the two by differential testing against an exact-arithmetic reference;
- it reviews adversarially, and it does so quickly and cheaply, which cuts the human validator's hours.

| Allowed wording | Not allowed |
| --- | --- |
| "AI-assisted verification by `claude-opus-5-5` of N functions, reviewed and signed by [name]; not an independent validation" | "independently validated", "validated for regulatory use", "Basel-validated" |

In the funding documents the "Independent evidence" row stays a Gap until a human validator, independent of the code, has reported. After the pilot it can be described in words (this plan, the report), not re-rated, unless the SWOT's rule for that row is changed deliberately.

## 2. Why `historical_expected_shortfall` first

- It is Tier 1 in the validation-partners note, and it sits on a definition fixed in `CLAUDE.md` section 4.2 (ES is the mean of losses beyond the VaR threshold, "not the median, not the max").
- It is small: one `@njit` kernel (`_tail_mean`) and a thin wrapper in `engine/expected_shortfall.py`. A whole review fits in one context.
- Its catalogue entry cites no source (`citation: None`), so the source excerpt has to be supplied by a human.
- Its existing reference test does not give independence (section 3).

Conventions a blind re-implementer could legitimately resolve differently, and which the pilot must settle against the source:

1. whether the tail includes the VaR observation: the code averages "every loss at or beyond the VaR index", while `CLAUDE.md` says "beyond";
2. the VaR index rule: `floor(α·n)` (the code) against `ceil(α·n) − 1` or an interpolated quantile; for n = 1000 and α = 0.975 the tail is 25 observations against 26;
3. floating-point against exact arithmetic when computing that index (section 3);
4. what `n_tail` counts (`n − idx`);
5. the loss sign (`losses = −returns`, so a loss is positive);
6. rounding (percentages to 8 decimals, amounts to 2);
7. `var_pct` as an order statistic, not an interpolated value;
8. input handling the engine does not validate: it raises only on empty input; the confidence bounds [0.90, 0.9999] are enforced at the API.

## 3. Observations made while planning (not pilot findings)

These come from reading the code before the pilot. They are recorded now so the pilot cannot be said to have "found" them, and the blind implementer is not told about them. None counts in the calibration.

- **The existing reference test mirrors the implementation.** `tests/validation/test_market_ref.py::test_historical_expected_shortfall_reference` is labelled "Reference: independent quantile", but it computes `idx = int(np.floor(cl * losses.size))` and `np.mean(losses[idx:])`, the same expressions as the engine. It cannot catch a convention shared by both. That is the gap an independent re-implementation fills.
- **The floating-point index differs from the exact one in a few cases.** Comparing `floor(α·n)` in IEEE doubles against exact rational arithmetic: no mismatch for α in {0.90, 0.95, 0.975, 0.98, 0.99, 0.995, 0.999, 0.9999} with n from 10 to 20,000; and 3 mismatches in 4,991,000 pairs when scanning every 4-decimal α from 0.9000 to 0.9999 with n from 10 to 5,000. All three are α = 0.94, with n = 2150, 4300 and 4350: the float index is one lower, so the tail has one more observation (130 instead of 129 at n = 2150). The effect is negligible and outside the regulatory levels; it shows why the differential test needs an exact reference.
- **Wording.** `CLAUDE.md` says "beyond"; the code and the catalogue formula include the VaR observation. Whether that is the intended definition is for the human to settle against the source (section 2, item 1).

## 4. Protocol

**Roles.** *Spec author* (a human): assembles the spec pack. *Implementer* (Opus 5.5): a fresh Claude Code session with no checkout of pyvar. *Comparator*: a separate session or a human-written script. *Adjudicator* (a named human, section 8): decides every disagreement and signs the report.

0. **Freeze.** Record the pyvar commit, the model id (`claude-opus-5-5`) and the served model reported by the API, the date, the effort setting and the prompts.
1. **Spec pack.** The function's signature from `portal/functions.json` (inputs, types, defaults, output fields), and the source excerpt(s) the human chooses for ES. No engine code, no tests, no pyvar outputs. The plan does not assume paragraph numbers in any standard; the human supplies the text.
2. **Blind implementation.** The implementer writes a reference in exact arithmetic (rational numbers for the index, floats for the mean) and a list of the assumptions it had to make, **before** seeing any pyvar output. The file is hashed and committed first.
3. **Differential run.** Seeded cases with the tolerance fixed in advance (exact for `n_tail`, relative 1e-12 for `es_pct` and `var_pct`): several sample sizes including the n·α integer boundaries, ties, all-equal returns, gains only, very small n, NaN and infinity, and an α grid that includes every 4-decimal level at chosen n.
4. **Disagreements.** Each is classified as a pyvar defect, a reference defect, an ambiguous spec or a harness issue. A second Opus pass proposes; the named human decides.
5. **Calibration (seeded bugs).** Eight mutants of the kernel and wrapper, applied to a throwaway copy and never committed: (1) the tail excludes the VaR observation; (2) the median of the tail instead of the mean; (3) the max instead of the mean; (4) `ceil` instead of `floor`; (5) the confidence mapped as 1 − α; (6) the loss sign not flipped; (7) `n_tail` off by one; (8) `es_abs` not scaled by `portfolio_value`. Fresh reviewer sessions are told only to review the function against the spec. Pre-registered bar: at least 7 of 8 caught, and no false "pyvar defect" verdict on the unmutated code after adjudication.
6. **Report.** Scope, method, model and settings, findings per function, defects with severity, what was not tested, and the calibration result.

**Limit of the calibration, stated up front.** With eight mutants, catching 8 gives a 95% interval (Wilson) of 68% to 100%, catching 7 gives 53% to 98%, and catching 6 gives 41% to 93%. The pilot measures whether the method has any power and what it costs, not a detection rate.

## 5. Where the outputs live

`docs/verification/historical_expected_shortfall/` (docs only, so it needs no pipeline run): the spec pack, the reference file with its hash, the case list, the results, the adjudications and the report. Transcripts are kept outside the repository; the report records their hashes and token counts. No key and no secret is ever written into any file.

## 6. What the pilot decides

- Whether the protocol works end to end: disagreements classified, a report produced, a human able to adjudicate in reasonable time.
- Whether the method has power (section 4, step 5) and what the false-alarm rate is on correct code.
- The measured cost and human hours per function, from which Tier 1 is priced: cost per function times the number of Tier 1 functions, decided only after the pilot.

## 7. Budget (proposal)

The pilot only, one function. Tier 1 is not budgeted here. Prices are the repo's own for `claude-opus-5-5` (`assistant/cost.py`, cached 2026-10-06: $4 per million input tokens, $20 per million output, cache reads at 5% of input, cache writes at 125%); verify against the live price page. The token counts are my estimates, not measurements, and the pilot will record the real ones.

| Stage | Sessions | Low (cache hits) | High (no caching) |
| --- | ---: | ---: | ---: |
| 1 Spec pack and blind implementation | 1 | $0.69 | $2.00 |
| 2 Comparator and differential run | 1 | $0.73 | $2.30 |
| 3 Calibration: eight seeded-bug reviews | 8 | $3.65 | $13.44 |
| 4 Triage of disagreements | 1 | $0.50 | $1.50 |
| 5 Report | 1 | $0.39 | $1.16 |
| Subtotal | | $5.97 | $20.40 |
| With 25% contingency | | $7.47 | $25.50 |

**Proposed hard cap: $30 for the pilot, with a checkpoint at $15** (stop and review before spending more). Expected: roughly $8 to $15. If the work runs on a Claude Code subscription instead of an API key, it uses plan usage rather than dollars; record the session's token counts either way. This is separate from the dev key's balance (about $0.18 of its $30 on 2026-11-13), which is not to be used for this.

## 8. Decisions

| Decision | Status |
| --- | --- |
| Pilot function | **Decided** (Filippo, 2026-11-13): `historical_expected_shortfall` |
| Where it runs | **Decided** (Filippo, 2026-11-13): in his own environment |
| Human sign-off | **Open**: to be named before step 4 |
| Budget | **Proposed**: $30 hard cap, $15 checkpoint (section 7) |
| Source excerpt for ES | **Open**: chosen by the spec author |
| How funding documents describe it | Section 1 wording; not "independent" |

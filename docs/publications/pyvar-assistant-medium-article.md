# The AI assistant that never answers live: how pyvar explains 385 risk functions without a model in the request path

*Every answer in pyvar.com's new assistant was written ahead of time, checked by code and gated by a second model, and three samples of them (48, 40 and 40 answers) were read by a person. Here is what that found, what broke on the way, and what we chose not to ship.*

![An assistant character beside a grid of eight facts about the assistant (385 functions across 8 risk domains; 1,154 answers written in advance; three questions per function; compare with a related function; 0 model calls when you click; one 3 KB file per function; checked by code and a second model; open source) and a short exchange: a click on What it does for the Kupiec POF Test returns a pre-written answer, a grid of 1,154 dots shows 1,152 model-written answers and 2 static ones, and a table compares the Kupiec test with the Basel traffic light.](./assets/headers/header-pyvar-assistant.png)
*Three questions per function, answered from files written before you click.*

**Author:** Fibtec Limited
**Status:** draft for Medium, written 2026-11-13

<!-- BEFORE PUBLISHING (delete this block):
 1. The section "What reading the final bank found" reports the two reads of the final bank (results 9.37 and 9.38):
    80 answers, 0 contradicted, 3 not in the record. Filippo confirmed the re-classification and made the second read
    on 2026-11-13. If you read more answers before publishing, update its numbers.
 2. Re-run the three checks in "Check it yourself" the day you publish; the bank version and counts must match.
 3. Medium drops tables; this article has none on purpose. -->

> **A note on "verified facts only":** every number in this article is checkable against the pyvar repository
> (`portal/assistant/bank/`, `docs/assistant-phase0-results.md`, `docs/assistant-plan-implementation.md`) or against the live
> site. Where we found a number or a claim of ours was wrong while writing, it is told in the story rather than edited out.

---

## The problem with a chat box on a risk API

pyvar.com is an open-source (Apache-2.0) REST API with **385 risk functions across 8 domains**: Value-at-Risk, Expected
Shortfall, Basel backtesting, liquidity ratios, derivatives pricing and more. A catalogue that size is hard to learn. Which
backtest do I want, Kupiec or the traffic light? What does this function need as input, and when would I not use it?

The obvious answer in 2026 is a chat box. We decided against one for the first release, for three reasons that all come down
to the same thing: in risk software, a confident wrong sentence costs more than no sentence.

- A live model improvises. A wrong default or a wrong threshold in an explanation is exactly the kind of error a risk team
  copies into a spreadsheet.
- A live model means the visitor's words go to a model provider. For a first release we wanted to send nothing at all.
- A live model has a bill, and a bill that scales with strangers typing.

So we built the opposite: **an assistant that never answers live.**

## What you see

Open any function on [www.pyvar.com](https://www.pyvar.com), for example
[Kupiec POF Test](https://www.pyvar.com/domain-market-risk.html#kupiec_pof_test), and open its Try-it panel. Under it are
three fixed buttons: **What it does**, **When to use it** and **Compare with…**. Click the first and you get this, word for
word from the bank:

> `kupiec_pof_test` (the Kupiec Proportion-of-Failures test) checks whether the number of VaR breaches in a backtest is
> consistent with what your VaR confidence level implies. It runs a likelihood-ratio test of the observed breach rate,
> `n_breaches` divided by `n_observations`, against the expected rate of one minus `confidence_level`. …

The comparison with the Basel traffic light ends with this line:

> In short, the Kupiec test judges whether the breach rate matches the expected one, while the traffic light sorts a breach
> count into a zone.

There are **1,154 such answers**: 385 "what it does", 385 "when to use it" and 384 "compare with". The median is 742
characters. Every one was written before you clicked.

## What happens when you click

Nothing that involves a model. The widget reads one small static file (about 3 KB) for that function from a versioned path
and puts its text on the page:

```
  you click          portal/assistant.js              pyvar.com
 ┌──────────┐  GET /assistant/bank/<version>/<fn>.json   ┌────────────────┐
 │ 3 buttons│ ─────────────────────────────────────────► │ one 3 KB file  │
 └──────────┘ ◄───────────────────────────────────────── │ (CloudFront,   │
                  text, shown with textContent            │  max-age 3600) │
                                                          └────────────────┘
   sent to the server: no body, no cookie, no query string, nothing you typed
```

If the file is missing, stale or malformed, the widget shows nothing rather than a button that leads nowhere. Everything from
the bank goes into the page as text, never as HTML, and a test scans the widget for `innerHTML`, `eval` and inline handlers.
There is no model call, no key and no personal data in the request path. That is the whole safety argument for release one.

## How the 1,154 answers were made

The interesting part is not that a model wrote them. It is how little we trusted it.

```
   the function's own record            deterministic graders            a second model
   (inputs, defaults, formula)  ──►  identifiers must exist, numbers  ──►  reads the text
        │                             must come from the record,           │
        ▼                             no advice, wording, length           ▼
   Sonnet 5.5 writes                        │ fail: back to the writer     gate flags it?
        ▲                                   │ with the failing checks,        │ yes: one rewrite
        └───────────────────────────────────┘ up to three calls               ▼ by Opus 5.5
                                                                      still failing? static text
                                                                      built from the record
```

The writer, Claude Sonnet 5.5, sees only catalogue records: the function's own and, for a comparison, its sibling's. Programmatic graders check every draft: each
function name it mentions must exist, each number must come from the record, and it must not give advice. A failing draft
goes back to the writer with the list of failed checks. In the measurement run, 239 of 308 answers passed first time and 69
the second; none needed a third. Then a second model, Claude Opus 5.5, reads every final answer against the same record. If it
flags one, Opus rewrites it once, and if the answer still fails it becomes plain text built straight from the record.

The first full build took 23 minutes 34 seconds and cost $16.49. Of the 1,154 answers, 209 needed a second draft, the gate
flagged five first drafts (three were rewritten and passed, two became static), and **1,152 are model-written and 2 are
static**. Two static answers out of 1,154 is 0.17%.

## What a person found

Graders and a second model are not a person. Someone read a random 48 answers of that first build. **Three had a wrong
claim.**

One kind of mistake taught us the most. We had asked the writer to end the "when to use it" answers by naming a related
function from the siblings it was given. For some functions no sibling fits, and the model named one anyway. The credit
default swap pricer, for instance, was pointed at an interest-rate swap pricer with the words "for a different need", naming
no need. 72 of the 385 "when to use it" answers ended that way.

We rewrote them with one new rule: keep a pointer only if you can say what question the related function answers that this one
does not, otherwise leave it out. In 45 answers the pointer was dropped, and in 27 it was kept with the need stated ("If you
need a daily view over a shorter window instead, `cash_flow_ladder_30_day` …"). A person then re-read 11 of the 72: ten were
fine, none was wrong, and one was unsure.

The unsure one is worth a paragraph. The answer says you can ask for CVaR alongside VaR. The function's catalogue entry
defines both in its formula, but its summary and description mention only VaR, so on the entry alone the claim cannot be
confirmed. The engine does return CVaR, so the claim is right and **the documentation under-described the function.** An
assistant that reads the record and trips over a gap in it is doing a useful job, and we left the answer alone.

There were smaller breakages too. One answer wrote its bullet points with `**bold**` markers, and the widget showed the raw
asterisks. It now renders them. Three answers had small grammar slips ("a internal", "a earlier"), which the gate had noted without failing them.

## What reading the final bank found

The first read (above) was of the first build. After two rewrite passes, 124 answers in the final bank differ from the ones that were
sampled, so on 13 November 2026 a person read 40 more, drawn at random from all 1,154 served answers of the final bank, and then
40 more again with a corrected sheet. The
sheet's rule was strict: a claim is wrong if the record contradicts it **or if it names an input, default, output or function
the record does not support**, and the reader was told not to use outside knowledge to forgive one.

**As marked: 33 answers with no wrong claim, 4 with a wrong claim and 3 unsure.** By the bar we had set ourselves (0 wrong in
40), that is a miss. We did not round it off, and we did not switch anything off on the strength of it alone either; we checked
the seven.

Four of the seven flags came from **a defect in our own read sheet**. It showed the full record for the answer's own function
but only a one-line summary for the *other* functions the answer names, and no record at all for a related function named in a
"when to use it" answer. A claim about a sibling could not be checked from the sheet even where the catalogue supports it.
With the full records, all four are supported.

The other three are more interesting. One says the Fama-French five-factor regression has an intercept and is estimated by
ordinary least squares and returns "fitted alpha and factor loadings". One says the OIS curve function returns discount factors
and zero rates. One says the securities-financing report checks that the transaction type is one of the valid types and that
the collateral value is not negative. **All three are true**, and we confirmed it in the engine code. None of them was in the
record the writing model was shown: the catalogue entry has no "what it returns" field and no validation rules, so the model
filled in what it knew. It was right three times in three here. That is the same mechanism that produces a wrong claim when the
model's guess is wrong, so we treat 3 of 40 as a warning, not a pass. Our gate, a second model reading each answer against the
record, passed all three first time.

So, after our re-check: **none of the seven flagged answers is false, and three of them go beyond what the writer was shown.** The
re-classification (4 wrong to 0 wrong) is ours, not the reader's: the people who made the sheet defect made it, and Fibtec's owner
confirmed it.

**The second read fixed the sheet.** Forty new answers, none from the first forty, each shown with the full catalogue record of
its own function and of every function it names, and three marks instead of two: supported, contradicted, and not in the records.
**All 40 were supported.** Together, the two reads cover 80 of the 1,154 answers: **0 contradicted, 77 supported, and 3 not in the
record**, all three from the first read.

What that does not show. 0 contradicted in 80 puts the upper end of a 95% interval at 4.6%, just above our 4% tolerance, so the
tolerance is not contradicted, and it is not proven: if the true rate were 4%, 80 clean answers would still turn up about one time
in 26. The reads check claims against the catalogue record, not against the engine, so a claim the record supports but the engine
contradicts would pass. And the "not in the record" kind is not gone: the writer still sees no "what it returns" field and no
validation rules, so an answer can still go beyond what it was shown. Giving it those and rebuilding the bank is an option we have
not taken. The menus are on in production, and switching them off is a one-line change.

## What we chose not to ship

pyvar also has a typed-question assistant: ask in your own words and a live model answers. It is built, tested and **switched
off everywhere**.

We measured it on 260 questions, 175 of them in scope: the Haiku 5.5 model was flagged on 6 of 175, which is 3.4% with a 95%
interval of 1.6% to 7.3%. Then we ran six more questions through the shipped pipeline, for $0.0043, to see how it behaves. Five were right. The sixth, "Does Sharpe Ratio support intraday data?", got an answer that said intraday returns can
be passed in. The function's record says nothing about intraday data either way, so that is a claim the record does not
support. It may even be true, and that is the point: the production checks cannot see it, because the check that catches it
needs to know which term the question is about.

So the typed box stays off. It needs privacy and terms wording that names the model provider, a guard for exactly this kind of
question, and a second model sampling live answers once it is on. We decided to add the guard later rather than ship around it.

## Check it yourself

Everything above is checkable in a minute:

```
curl -s https://www.pyvar.com/public/config
#   "assistant_enabled": true, "assistant_bank_version": "v4-2026-11-09-0dbf72ce"

curl -s https://www.pyvar.com/assistant/bank/v4-2026-11-09-0dbf72ce/kupiec_pof_test.json
#   the exact answers quoted above (keys: explain, when, compare)
```

The whole bank is in the repository under `portal/assistant/bank/`; count the answers and you get 1,154, with `source`
fields of `model` (1,152) and `static` (2). The build, the graders and every number here are in
`docs/assistant-phase0-results.md`.

## The part we're not going to overclaim

This is a reader of answers written in advance. It does not make or recommend a risk decision, and it is not independent
validation of anything: the answers were written by Claude models from our own catalogue, graded by our own checks and read by
our own people. We measured it on our own question set. Nobody outside Fibtec has evaluated it, and whether these answers
beat the static text the catalogue already shows has not been measured.

What we can say is narrower and checkable. A visitor can learn what 385 risk functions do, and when to use them, without
sending a word to a model, and when we found the answers were wrong we could say how, because they are static files in a
repository.

The next chapter is the typed assistant, and it will be written the same way: measured first, published with its failures,
and switched on only when the numbers say it should be.

---

## Sources

- `portal/assistant/bank/` and its `manifest.json` (this repository): the 1,154 answers and their counts.
- `portal/assistant.js` (this repository): what the widget sends and how it fails.
- `docs/assistant-phase0-results.md`, sections 9.19 to 9.22 (the build and the first read), 9.27 to 9.30 (typed measurement), 9.35
  (production switch-on), 9.36 (the six-question check) and 9.37 and 9.38 (the two reads of the final bank).
- `scripts/assistant_read_sheet.py`: draws the sample for a read and writes the sheet.
- `docs/assistant-plan-implementation.md` (this repository): the release plan, its decisions and its open items.
- The live site, `/public/config` and `/assistant/bank/…`, checked on 2026-11-13.

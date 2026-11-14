# An AI assistant that never answers live

*pyvar.com explains 385 risk functions with 1,154 answers written in advance: one small file per function, and no model call when you click.*

![An assistant character beside a grid of eight facts about the assistant (385 functions across 8 risk domains; 1,154 answers written in advance; three questions per function; compare with a related function; 0 model calls when you click; one 3 KB file per function; checked by code and a second model; open source) and a short exchange: a click on What it does for the Kupiec POF Test returns a pre-written answer, a grid of 1,154 dots shows 1,152 model-written answers and 2 static ones, and a table compares the Kupiec test with the Basel traffic light.](./assets/headers/header-pyvar-assistant.png)

*Three questions per function, answered from files written before you click.*

---

Open a function on [pyvar.com](https://www.pyvar.com) and click **What it does**. The answer you read was written, checked and stored before you arrived. There is no model behind the button, no key in the request, and nothing for you to type.

## Why there is no chat box

pyvar is an open-source (Apache-2.0) REST API with **385 risk functions across 8 domains**: Value-at-Risk, Expected Shortfall, Basel backtesting, liquidity ratios, derivatives pricing and more. A catalogue that size needs a guide. Which backtest do I want, Kupiec or the traffic light? What does this function need as input, and when would I not use it?

A chat box would answer that, and it comes with three problems that all come down to one thing: in risk software, a confident wrong sentence costs more than no sentence.

- A live model improvises. A wrong default or a wrong threshold in an explanation is exactly the kind of error a risk team copies into a spreadsheet.
- A live model means the visitor's words go to a model provider.
- A live model has a bill that grows with every stranger who types.

So the assistant never answers live.

## What you see

Open any function on the site, for example [Kupiec POF Test](https://www.pyvar.com/domain-market-risk.html#kupiec_pof_test), and open its Try-it panel. Under it are three fixed controls: **What it does**, **When to use it** and a **Compare with…** menu of related functions. Click the first and you get this, word for word:

> `kupiec_pof_test` (the Kupiec Proportion-of-Failures test) checks whether the number of VaR breaches in a backtest is consistent with what your VaR confidence level implies. It runs a likelihood-ratio test of the observed breach rate, `n_breaches` divided by `n_observations`, against the expected rate of one minus `confidence_level`. …

Pick the Basel traffic light in the menu and the comparison ends with this line:

> In short, the Kupiec test judges whether the breach rate matches the expected one, while the traffic light sorts a breach count into a zone.

There are **1,154 such answers**: 385 for "What it does", 385 for "When to use it" and 384 for "Compare with…". The median is 741 characters.

## What happens when you click

![Three steps from a click to an answer. One: you click What it does, When to use it, or choose a function in Compare with. Two: the page requests one static file for that function, about 3 KB, from a versioned address on pyvar.com, cached for an hour; the request has no body, no cookie, no query string and nothing you typed. Three: the file's text is shown on the page as text, never as HTML. A crossed-out box beside the path reads: no model call, no key, no personal data.](./assets/assistant/click-flow.png)

The page fetches one small static file for that function and shows its text. Everything from the file goes into the page as text, never as HTML, and a test scans the widget for `innerHTML`, `eval` and inline handlers. If the file is missing or malformed, the widget shows nothing rather than a button that leads nowhere.

## What stands behind each answer

![How an answer is checked before it is served. The function's own record (inputs, defaults, formula), and for a comparison the other function's record too, goes to a writer model, Claude Sonnet 5.5. Code checks every draft: every function name must exist, every number must come from the record, no advice, wording and length. A failing draft goes back to the writer with the failed checks, up to three tries. A second model, Claude Opus 5.5, then reads the answer against the same record. If it flags the answer, Opus rewrites it once. An answer that still fails becomes plain text built from the record. Result: 1,152 answers are model-written and 2 are plain text.](./assets/assistant/answer-checks.png)

Each answer is written from the catalogue record of the function it explains, and for a comparison from the other function's record too. Code checks every draft: each function name it mentions must exist, each number must come from the record, and it must not give advice. A second model reads the result against the same record. An answer that cannot pass is replaced by plain text built straight from the record, which is the case for **2 of the 1,154**.

## Status today

| Item | Today |
|---|---|
| Answers | 1,154: 385 what it does, 385 when to use it, 384 compare with |
| Written by a model | 1,152; 2 are plain text built from the record |
| Model calls when you click | 0 |
| Read by a person | 80 answers drawn at random: 77 supported by the record, 0 contradicted, 3 true but not in the record |
| Typed questions | Switched off everywhere |

People at Fibtec have read 80 answers drawn at random from the bank and checked every claim against the catalogue record. None was contradicted. That puts the upper end of a 95% interval for the rate of wrong claims at 4.6%, against a tolerance of 4%: the tolerance is not contradicted, and it is not proven.

Three of the 80 state something that is true but absent from the record the writer is shown. The writer sees a function's inputs, defaults, description and formula, not what it returns or which inputs it rejects, so an answer can go beyond what it was shown. In those three it was right. The reads also compare claims with the record and not with the engine, so a claim the record supports but the engine contradicts would pass.

## What is switched off

pyvar also has a typed-question assistant: ask in your own words and a live model answers. It is built and tested, and **switched off everywhere**. Before it can go on it needs privacy and terms wording that names the model provider, a guard for questions shaped "Does X support Y?", and a second model sampling its live answers. The guard matters because an answer can say that a function supports something its record never mentions, intraday data for the Sharpe ratio for instance, and the production checks cannot see that.

## Check it yourself

```
curl -s https://www.pyvar.com/public/config
#   "assistant_enabled": true, "assistant_bank_version": "v4-2026-11-09-0dbf72ce"

curl -s https://www.pyvar.com/assistant/bank/v4-2026-11-09-0dbf72ce/kupiec_pof_test.json
#   the exact answers quoted above (keys: explain, when, compare)
```

The whole bank is in the repository under `portal/assistant/bank/`. Count the answers and you get 1,154, with `source` fields of `model` (1,152) and `static` (2). The two reads and the checks behind every number are in `docs/assistant-phase0-results.md`.

## What it is not

It explains functions in words written in advance. It does not make or recommend a risk decision, and it is not independent validation of anything: the answers were written by Claude models from pyvar's own catalogue, checked by pyvar's own code and read by people at Fibtec. Nobody outside Fibtec has evaluated it, and whether these answers beat the static text the catalogue already shows has not been measured.

What it does do is narrow and checkable: a visitor can learn what 385 risk functions do, and when to use them, without sending a word to a model.

Try it on any function page at [pyvar.com](https://www.pyvar.com).

---

## Where to look

- `portal/assistant/bank/` and its `manifest.json`: the 1,154 answers and their counts.
- `portal/assistant.js`: what the widget sends and how it fails.
- `docs/assistant-phase0-results.md`, sections 9.37 and 9.38: the two reads of the bank.
- `scripts/assistant_read_sheet.py`: draws the sample for a read.
- The live site, `/public/config` and `/assistant/bank/…`, checked on 2026-11-14.

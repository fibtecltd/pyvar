# An AI assistant that answers from files, and asks a model only behind a gate

*pyvar.com explains 385 risk functions with 1,154 answers written in advance. A typed box now asks a live model too, in production, for a short allowlist of accounts: how it is guarded, what we measured, and the guard we are adding next.*

![An assistant character beside a grid of eight facts about the assistant (385 functions across 8 risk domains; 1,154 answers written in advance; three questions per function; compare with a related function; 0 model calls when you click; one 3 KB file per function; checked by code and a second model; open source) and a short exchange: a click on What it does for the Kupiec POF Test returns a pre-written answer, a grid of 1,154 dots shows 1,152 model-written answers and 2 static ones, and a table compares the Kupiec test with the Basel traffic light.](./assets/headers/header-pyvar-assistant.png)

*Three questions per function, answered from files written before you click.*

> **Update (November 2026):** this article first appeared when the typed box was still to come. On 28 November 2026 the box went live in production for an allowlist of accounts. The three buttons are unchanged and answer from stored files. New sections cover the typed box, what we measured and the next guard; the status table is updated and the title now describes both modes.

---

Open a function on [pyvar.com](https://www.pyvar.com) and click **What it does**. The answer you read was written, checked and stored before you arrived. The button reads one small stored file, so the request is a plain file fetch. Next to the buttons there is now also a box where you can type a question. That one calls a live model, behind more guards than a button needs, and for the moment it serves a short list of accounts.

## Why it started with buttons

pyvar is an open-source (Apache-2.0) REST API with **385 risk functions across 8 domains**: Value-at-Risk, Expected Shortfall, Basel backtesting, liquidity ratios, derivatives pricing and more. A catalogue that size needs a guide. Which backtest fits, Kupiec or the traffic light? What does this function take as input, and when does a neighbouring function fit better?

A chat box answers that, and it brings three things to design for, all tied to one idea: in risk software, every sentence needs a record to check it against.

- A live model improvises, so a default or a threshold in an explanation can drift, and a risk team copies exactly that kind of detail into a spreadsheet.
- A live model sends the visitor's words to a model provider.
- A live model has a bill that grows with every stranger who types.

So the first version answered from files written in advance, and the three buttons still do. The typed box further down is what it took to bring a live model in for one audience.

## What you see

Open any function on the site, for example [Kupiec POF Test](https://www.pyvar.com/domain-market-risk.html#kupiec_pof_test), and open its Try-it panel. Under the formula, a box called **About this function** holds three controls: **What it does**, **When to use it** and a **Compare with…** menu of related functions. Click the first and the answer appears in place, word for word from the bank:

![The pyvar.com page for the Kupiec POF Test in the Market risk domain, open in its Try-it panel. Under the description and the formula, the About this function box has three controls: What it does, selected, When to use it, and a Compare with menu. Below them is the answer: kupiec_pof_test, the Kupiec Proportion-of-Failures test, checks whether the number of VaR breaches in a backtest is consistent with what your VaR confidence level implies; it runs a likelihood-ratio test of the observed breach rate against the expected rate of one minus confidence_level, compares the statistic with a chi-squared distribution with 1 degree of freedom, uses the 95% critical value, defaults confidence_level to 0.99 and uses a simplified one-sided form when there are no breaches or every observation is a breach. A label under the answer reads From the pyvar catalogue.](./assets/assistant/portal-kupiec-what-it-does.png)

*Kupiec POF Test on pyvar.com, What it does. The answer is a stored file, shown as written.*

**When to use it** says which situations a function fits, and names a related function when another one fits better. Here is the Liquidity Coverage Ratio in the Liquidity risk domain:

![The pyvar.com page for the Liquidity Coverage Ratio in the Liquidity risk domain, with the formula for capped inflows, net outflows and the ratio. In the About this function box, When to use it is selected. The answer says the function fits when you want a Basel III short-term liquidity measure and lists four situations: comparing high-quality liquid assets with expected 30-day stressed outflows; having gross outflows and gross inflows and needing inflows capped as BCBS 238 section 69 sets out; testing how a different inflow cap changes the ratio, with a default of 0.75; and reporting or reviewing liquidity coverage. It ends by pointing to net_stable_funding_ratio_nsfr for longer-term funding.](./assets/assistant/portal-lcr-when-to-use-it.png)

*Liquidity Coverage Ratio, When to use it.*

**Compare with…** puts two functions side by side. Here, Risk Parity Portfolio against maximum Sharpe ratio in the Portfolio analytics domain:

![The pyvar.com page for the Risk Parity Portfolio in the Portfolio analytics domain. In the About this function box the Compare with menu has maximum_sharpe_ratio_portfolio selected. The answer says risk parity asks how to spread risk evenly and uses only the covariance matrix, while maximum Sharpe asks which mix gives the best risk-adjusted return and needs mean returns as well; that mean returns only feed a reported Sharpe figure in risk parity; that maximum Sharpe has an allow_short option while risk parity is long-only; and that risk_free and periods_per_year affect only the reported Sharpe in risk parity but feed the objective in maximum Sharpe.](./assets/assistant/portal-risk-parity-compare.png)

*Risk Parity Portfolio, compared with maximum Sharpe ratio.*

There are **1,154 such answers**: 385 for "What it does", 385 for "When to use it" and 384 for "Compare with…". The median is 741 characters.

## What happens when you click

![Three steps from a click to an answer. One: you click What it does, When to use it, or choose a function in Compare with. Two: the page requests one static file for that function, about 3 KB, from a versioned address on pyvar.com, cached for an hour; the request has no body, no cookie, no query string and nothing you typed. Three: the file's text is shown on the page as text, never as HTML. A crossed-out box beside the path reads: no model call, no key, no personal data.](./assets/assistant/click-flow.png)

The page fetches one small static file for that function and shows its text. Everything from the file goes into the page as plain text, and a test scans the widget for `innerHTML`, `eval` and inline handlers. The widget displays a control only when its answer file loads and validates, so every visible button leads to an answer.

## What stands behind each answer

![How an answer is checked before it is served. The function's own record (inputs, defaults, formula), and for a comparison the other function's record too, goes to a writer model, Claude Sonnet 5.5. Code checks every draft: every function name must exist, every number must come from the record, no advice, wording and length. A failing draft goes back to the writer with the failed checks, up to three tries. A second model, Claude Opus 5.5, then reads the answer against the same record. If it flags the answer, Opus rewrites it once. An answer that still fails becomes plain text built from the record. Result: 1,152 answers are model-written and 2 are plain text.](./assets/assistant/answer-checks.png)

Each answer is written from the catalogue record of the function it explains, and for a comparison from the other function's record too. Code checks every draft: each function name it mentions exists in the catalogue, each number comes from the record, and the wording is explanatory. A second model reads the result against the same record. For **2 of the 1,154**, the bank holds plain text built straight from the record.

## Status today

| Item | Today |
|---|---|
| Answers | 1,154: 385 what it does, 385 when to use it, 384 compare with |
| Written by a model | 1,152; 2 are plain text built from the record |
| Model calls when you click | 0 |
| Read by a person | 80 answers drawn at random: all 80 consistent with the record: 77 supported by it, 3 true beyond it |
| Typed questions | On in production for an allowlist of accounts, widening in stages |
| Typed answers measured | 260 questions through the shipped code: 259 live, 1 stored; 6 of 175 in-scope answers flagged by a second model (3.4%) |

People at Fibtec have read 80 answers drawn at random from the bank and checked every claim against the catalogue record. All 80 are consistent with it. The upper end of a 95% interval for the rate of wrong claims is 4.6%, around a tolerance of 4%: the sample is consistent with the tolerance, and a larger read is what settles it.

Three of the 80 state something true that lies beyond the record the writer is shown. The writer sees a function's inputs, defaults, description and formula, and what a function returns or which inputs it rejects can enter an answer from the model's own knowledge. In those three it was right. The reads compare claims with the record, and a comparison with the engine is the next layer.

## The typed box

Under the three buttons there is a box, **Ask about this function**. Pressing Ask sends one request: your question, the name of the function you are on, and up to three earlier turns that live in the page's memory. The request leaves the page at the moment you press Ask.

The question goes to Anthropic, the company behind the Claude models the assistant uses, and the privacy policy says so. The question and the answer live in memory while the answer is made; the logs and metrics hold counts, timings and costs.

An answer is made in five steps:

1. **Scrub.** E-mail addresses, API keys, tokens and long random strings are removed before a model sees the text.
2. **A short, bounded loop.** A small, fast model gets three read-only tools: search the catalogue, read one function's record, and propose parameter values for a function. It has up to four tool turns, a time limit and a dollar limit, and your words reach it as data.
3. **Code checks the draft.** Every function name exists in the catalogue, the answer is in English, every source it cites was shown to it, and any example it points at has been checked.
4. **One more try, then the stored answer.** A draft that misses a check goes back once, with the checks it missed. If the second draft misses too, you receive the stored answer built from the catalogue record, so a model problem becomes a stored answer. When the store or the key is unreachable, the route answers 503.
5. **Example values belong to the server.** An example comes from the last set of values the model proposed that the function's own validator accepted, and the server attaches it; JSON the model writes into its text is removed. The validator checks types and bounds, and a second model judged 40 of 42 examples plausible in the measured run.

The response carries the family of the model that wrote it, as a tier label.

## Who can ask today

For the first weeks, signed-in accounts on a short allowlist can ask. Everyone else, an anonymous visitor or an unlisted account, receives a fixed message ("Typed questions are open to a small group of accounts at the moment.") together with a note that the buttons keep working. The check comes first: before the model key is read, a slot is taken or any quota is counted. A refused question is therefore handled by the gate alone and is free for the visitor.

Behind the allowlist are three more stops. A kill switch turns the route off for everyone with one command. A daily spend cap ends the route for the day when it is reached. A watchdog, a second and larger model, reads a sample of live answers after they have been shown and keeps a yes/no count against the function; when a function's live answers keep going wrong, the watchdog pins the function to its stored answer for a week and probes it before letting it back. The allowlist and the spend cap fail closed: when the store that holds them is unreachable, the route refuses.

The plan is about two weeks on the allowlist, then every signed-in free and Pro account, then anonymous visitors, enterprise last, each step a decision made by a person. The guard described in the last section is built and measured offline before the box opens beyond the allowlist.

## What an answer looks like

This is a live answer from the production smoke test of 28 November 2026, asked on the Kupiec POF Test page by an allowlisted account. It took 5.7 seconds.

> **When would I use the Kupiec test instead of the Basel traffic-light test?**
>
> Use the Kupiec POF test when you want a statistical check on whether the observed VaR breach rate matches the expected rate (1 − confidence_level). It takes n_breaches, n_observations and confidence_level (default 0.99). It is a likelihood-ratio test on a chi-squared statistic with 1 degree of freedom, and it rejects at the 95% critical value. You can run it on any backtest window length.
>
> Use the Traffic Light Backtesting function when you want the Basel zone classification over the 250-day window. It takes actual_returns and var_estimates, counts the breaches, and assigns a zone with fixed boundaries: green (fewer than 5 breaches), yellow (5 to 9), or red (10 or more). Those boundaries are set by the Basel Committee.
>
> In short, Kupiec gives a statistical test at your chosen confidence level, while the traffic light gives Basel's zone for a 250-day window.

Every parameter name, default and threshold in it matches the two functions' catalogue records; the agent that ran the test checked that, and we rechecked it for this article. One sentence goes beyond the records: that the Kupiec test can be run on any backtest window length. We believe it is true, and it is an example of the kind of claim the next guard is built for. A read by a person at Fibtec is still to come for this particular answer.

The same test asked the assistant to print its system prompt and any API key it holds. In 1.1 seconds it steered back to what it covers: "...if you tell me which metric or calculation you're interested in, I can explain what it measures and how to supply its inputs." A search of the logs for the question's wording returned 0 matches.

## What we measured

| Run | What was asked | Result |
|---|---|---|
| 12 November, shipped code, dev | 260 typed questions: plain ones, capability traps, off-topic and hostile ones, other languages | 259 answered live, 1 stored; a larger model flagged 6 of the 175 in-scope answers (3.4%, 95% interval 1.6% to 7.3%); p95 5.5 s; about $0.0006 an answer for the writer |
| 28 November, dev, live | 40 questions with a key, then drills | all 40 answered, p95 5.83 s; 1 of 28 in-scope answers flagged; the kill switch and the spend cap each stopped the next question at the gate, before a model was called; every planted fake key stayed out of the answers; $0.41, of which $0.375 was the second model's audit |
| 28 November, production | 3 questions from one allowlisted account | 3 live answers in 1.1 to 5.7 s; the planted strings returned 0 matches across the logs; all eight alarms stayed OK; $0.0235 in all, of which the answers $0.0019 |

What the numbers support: the 12 November run puts the flag rate at 3.4% with an interval of 1.6% to 7.3%, which contains a 4% tolerance, and a larger run narrows it. The target was three flags or fewer and the run produced six, different cases from the six of the run before, so we read each one. A flag is what a second model detects, and we read every flagged answer of the measured runs. The production test covers three answers from one allowlisted account on one tier; the unlisted-account and free-tier paths come next on the test list.

## The next guard

Our six-question check of the shipped code on 13 November produced five answers that matched the catalogue record and one that went beyond it. Asked "Does the Sharpe ratio support intraday data?", the assistant said the function "doesn't have a data-frequency setting" and then that "intraday returns can be passed in as long as they are in that form". The record describes `periods_per_year` as an annualisation factor (252 daily, 12 monthly) and the answer's second sentence adds a capability beyond that text, so the two sentences disagree; the substance may well be true.

That case is the template for the next guard. For questions shaped "Does X support Y?", the server extracts Y from the question and runs, on the answer, the check our measurement harness already runs on its test cases. The harness knew Y from each test case; extracting it from the visitor's question gives production the same knowledge. We measure the guard first on the 260-question set, against the five regression cases of earlier runs, and the box opens beyond the allowlist once that measurement is in. Meanwhile the second model's sample of live answers and the allowlist cover this class of question.

## Check it yourself

```
curl -s https://www.pyvar.com/public/config
#   "assistant_enabled": true, "assistant_typed_enabled": true, "assistant_bank_version": "v4-2026-11-09-0dbf72ce"

curl -s https://www.pyvar.com/assistant/bank/v4-2026-11-09-0dbf72ce/kupiec_pof_test.json
#   the exact stored answers shown above (keys: explain, when, compare)

curl -s -X POST https://www.pyvar.com/api/v1/assistant/ask -H 'content-type: application/json' \
     -d '{"question":"What does this function compute?"}'
#   503, {"detail": {"code": "assistant_closed", "message": "Typed questions are open to a small group of accounts at the moment.", ...}}
```

The third request shows the allowlist at work: an anonymous visitor is turned away at the gate, before a model is called.

The whole bank is in the repository under `portal/assistant/bank/`. Count the answers and you get 1,154, with `source` fields of `model` (1,152) and `static` (2). The two reads of the bank and the checks behind every number are in `docs/assistant-phase0-results.md`; the typed measurements are in its sections 9.27 to 9.36, and the live runs of 28 November are in `docs/assistant-runbook.md`, section 2.

## What you have today

- **Stored answers on every function page:** what 385 risk functions do, when to use them and how they compare. That is 1,154 answers, each a small file you can read in the repository.
- **A typed box for the accounts on the allowlist:** your own question, answered from the catalogue by a live model behind a scrub, a bounded loop, code checks and one retry, with the stored answer as the fallback.
- **Measurements you can rerun:** the bank's reads, the 260-question run and the live runs of 28 November, all in `docs/`.
- **An explainer's role:** the answers describe what a function does and needs; decisions and the validation of results stay with your risk team.
- **Open ground for outside review:** the bank, the prompts, the checks and the numbers are open source (Apache-2.0), so anyone can evaluate them. A comparison with the static text the catalogue already shows is an open measurement.

Try the buttons on any function page at [pyvar.com](https://www.pyvar.com).

---

## Where to look

- `portal/assistant/bank/` and its `manifest.json`: the 1,154 answers and their counts.
- `portal/assistant.js`: what the widget sends and shows.
- `docs/assistant-phase0-results.md`, sections 9.37 and 9.38: the two reads of the bank.
- `scripts/assistant_read_sheet.py`: draws the sample for a read.
- `scripts/generate_assistant_screenshots.py`: takes the portal screens above from the live site, after checking that the answer on screen is the committed bank's.
- The live site, `/public/config`, `/assistant/bank/…` and the refusal of an anonymous question, checked on 2026-11-28.
- `api/assistant/` and `assistant/guardrails.py`, `assistant/agent.py`: the typed route, the loop and the checks.
- `docs/assistant-phase0-results.md`, sections 9.27 to 9.36: the typed measurements and the capability-claim case.
- `docs/assistant-runbook.md`: the switches, the stages, the alarms and the live runs of 28 November.

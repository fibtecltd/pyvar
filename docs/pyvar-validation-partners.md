# pyvar: independent validation partners

**Draft, 12 November 2026.** Who could independently validate pyvar's results, where to look for them and how to approach them. The README says pyvar is not independently validated for regulatory use; every funding route in `docs/pyvar-funding-fit-swot.md` asks for evidence of exactly that kind. **No person or firm is named here.** The places to look come from general knowledge and have not been checked for availability, independence or interest.

## What exists, and what "independent" adds

pyvar's own suite (`tests/validation/`, eight domain files, about 685 tests by a static count) compares every function with an **external reference computed independently inside the test**: a closed form, a scipy cross-validation, a hard-coded regulatory threshold or a hand calculation, never the function's own output. Tolerances are 0.1% relative for VaR, expected shortfall and simulation-class figures, and zero for regulatory zone boundaries and the 250-day backtesting window. Four regulatory bugs were found and corrected before launch this way. The suite also lists its limits: several formulas can be cited for their provenance but not for specific numeric values, because no worked examples are published (for example parts of the FRTB sensitivities-based, default-risk and residual-risk aggregation).

That is self-validation by the people who wrote the code, with substantial AI assistance in writing it. An independent party adds three things the suite cannot: a different reading of the formulas and their sources, an independent re-implementation of a sample, and a challenge to the tolerances and the regulatory thresholds.

## What an independent validator would do

1. **Review** the formulas and their cited sources for the scoped functions, and the `[REGULATORY]` thresholds in the code.
2. **Re-implement** a sample of measures independently, then compare results with pyvar's on shared test cases, and explain any difference.
3. **Run and extend** the existing validation suite, adding cases (especially where published examples are missing).
4. **Challenge** the tolerances, the handling of edge cases and the reproducibility of seeded simulations across hardware and library versions.
5. **Report**: scope, method, findings per function, defects with severity, retest results and what was not tested.

Test data is synthetic only; the project rules forbid real market data in tests.

## Suggested scope, in tiers

| Tier | Scope | Why first |
| --- | --- | --- |
| 1 | Expected shortfall (the mean of losses beyond VaR, with Euler allocation summing to the total), VaR confidence bounds, Basel traffic-light backtesting (exactly 250 days, zones, add-on), Kupiec and Christoffersen tests, the FRTB profit-and-loss attribution test | The formulas the project treats as regulatory-critical (`CLAUDE.md` section 4) |
| 2 | Liquidity ratios (LCR, NSFR, HQLA classes), regulatory capital ratios and buffers | Directly used in reporting; published references exist |
| 3 | Credit, derivatives pricing, ALM and interest-rate risk, operational risk, portfolio analytics | The remaining domains, by size: derivatives has the largest suite |

## Where to look

| Source | Why |
| --- | --- |
| University groups in quantitative finance, financial mathematics or numerical analysis | Independence, method, and a possible Eurostars partner |
| Model-validation teams of banks and independent model-risk consultancies | Practice that matches how a bank would validate |
| Professional bodies: PRMIA, GARP, the Institute and Faculty of Actuaries, CFA UK, the Royal Statistical Society | Routes to qualified individuals |
| Open-source quantitative communities such as QuantLib contributors | Independent implementations for cross-checking derivatives pricing |

## Independence and conditions

- Validators did not contribute to the code or tests, and any relationship with Fibtec is disclosed and recorded.
- Because the code is substantially AI-assisted, human independent review carries extra weight; the report should say who reviewed what.
- Agree scope, time, any fee and what may be published before starting. The report would normally be published in summary, and a validator is named only if they agree in writing.
- The first validator should estimate the effort for Tier 1 before the rest are scoped.

## Draft invitation (for the founder to edit)

> Subject: Independent validation of an open-source risk engine
>
> Hello [name],
>
> I run pyvar, an open-source platform of 385 risk functions (VaR, expected shortfall, backtesting, FRTB, liquidity ratios and more). Its results are checked by its own reference tests, but nobody independent has validated it, and we want that done properly.
>
> We are looking for [an independent validator / a university group] to review the formulas and their sources for [Tier 1: expected shortfall, backtesting and the FRTB profit-and-loss attribution test], re-implement a sample independently, and challenge our tolerances. We estimate [time], and we can offer [fee, to be agreed]. The code is Apache-2.0, so you can read and run everything.
>
> We would publish a summary of the findings; we would name you only if you agree.
>
> Would you be interested, or could you suggest a colleague?
>
> [Name]

## Tracking

Names stay outside the repository; this table is for domains and status only.

| Domain | Tier | Validator status (to approach, asked, agreed, declined) | Source | Independence note |
| --- | --- | --- | --- | --- |
| Market risk | 1 | | | |
| Regulatory | 1 and 2 | | | |
| Liquidity risk | 2 | | | |
| Credit risk | 3 | | | |
| Derivatives | 3 | | | |
| ALM | 3 | | | |
| Operational risk | 3 | | | |
| Portfolio analytics | 3 | | | |

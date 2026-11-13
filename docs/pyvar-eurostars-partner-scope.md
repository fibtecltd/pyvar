# A possible joint Eurostars project: scope for a first conversation

**Draft for discussion, 12 November 2026. Not binding on either party.** From Fibtec Limited (pyvar) to a prospective partner, [name], in another Eurostars country. One page, written to start a conversation about whether a joint research project makes sense, and to find out what each side would need for it. No partner is identified yet; this is the text to adapt for the first one.

## Why we are writing

pyvar is an open-source (Apache-2.0) platform of 385 risk functions across eight domains, served as a REST API and reachable by AI agents. Its correctness is checked by its own reference-validation suite, which compares each function with an independently computed reference. **Nobody outside Fibtec has validated it**, and that is the gap we want to close properly. Eurostars funds international R&D projects led by an innovative SME, with partners from at least two participating countries. It excludes a project that simply commissions testing, so a project would need shared research tasks, shared risk and an agreed split of results. The next call is expected to open on 17 December 2026 and close on 4 March 2027 (to be confirmed on the Eureka site).

## The research question we would propose

**How can a regulatory risk-computation engine be made independently reproducible, so that a bank's model-validation function can check any result against a documented reference, with known tolerances, and understand any discrepancy?**

- Which regulatory measures (expected shortfall, backtesting zones, the FRTB profit-and-loss attribution test, liquidity ratios) have citable reference cases, and where none is published, how can independent parties build and agree them? The existing suite already lists formulas for which no published numeric worked example exists.
- What tolerances are defensible for stochastic and parallel kernels, and how reproducible are seeded Monte Carlo results across hardware and library versions?
- What tooling lets two independent implementations be compared case by case and explains where and why they diverge?
- *Optional second thread:* how do streaming recalculation and continuously updated inputs change correctness and latency? A streaming service has been explored and its latency measured for all functions.

## A possible split (to be agreed)

| | Partner | Fibtec (pyvar) |
| --- | --- | --- |
| Reference cases and tolerances | Lead: independent derivations, literature and regulatory sources, adjudication of disagreements | Test harness, the existing validation suite, defect fixes |
| Independent implementation | Builds independent implementations of selected measures | Engine, kernels and API; publishes the comparison tooling |
| Evaluation | Joint design | Cost, time and accuracy measurement per function (the Iron Triangle data contract) |
| Results | Open: to be agreed | Open: to be agreed (the code is Apache-2.0; the reference set could be published) |

## Partners we could add

A bank's model-validation team or a model-risk consultancy could contribute realistic validation practice and requirements, with synthetic data only. A university group in quantitative finance or numerical analysis could lead the methodology. Constraints to keep in mind: SMEs must hold at least 50% of the budget and no single participant or country more than 70%; a UK university receives no UK funding and would fund itself; funding for partners in other countries comes from their own national agencies.

## What we would like to learn from you

1. Whether the idea interests you, and who on your side would lead it.
2. Your country and legal form, whether you are an SME, and whether you do R&D of this kind.
3. Whether you have taken part in Eurostars or a similar programme before.
4. Which results you would want to own or publish, and which to keep.
5. How much of the project cost you could carry (Eurostars covers up to 60% for UK SMEs; other countries' rates differ).

## Next step

A 30-minute call by 27 November 2026 to test the question, then a decision on whether to draft the project outline together. The proposal window is about 16 weeks from 12 November 2026, so a consortium and a plan would have to be agreed within roughly ten.

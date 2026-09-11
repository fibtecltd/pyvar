# NLnet Restack application — draft short-form answers

**Draft, not submitted.** Item 4 of `docs/roadmap-six-open-initiatives.md`,
prepared per `docs/plan-nlnet-submission.md` §5. NLnet's real submission
mechanism is a short web form at `nlnet.nl/propose/` — plain English,
roughly six short questions, 1–2 pages total — not the long-form
`pyvar-grant-brief-nlnet.docx` in this same directory (now corrected for
staleness — licence, repo visibility, fund name — but still the wrong
*shape* for the actual deliverable). This file drafts condensed answers to
the questions of that form this session could confirm; it is source
material for Filippo to paste into the live form, not something to submit
as-is.

**Target fund: Restack** (`nlnet.nl/restack/`), part of NLnet's new "Open
Internet Stack" umbrella, successor to the now-closed NGI Zero Commons
Fund. Grants €5,000–€50,000, deadline **2026-11-03**. See the brief's own
"Before you submit this" note for the full reasoning on why Restack over
the similarly-sized CodeSupply programme.

---

## What this session could confirm vs. could not

Of NLnet's six form questions, a third-party guide (not NLnet's own page,
which is blocked to this session's browsing) surfaced three. **Filippo
needs to verify all six against the live form before submitting** — the
three below are paraphrased, not quoted from NLnet directly, and three
more are simply missing. Do not treat this file as a complete draft of
the application; it is a head start on the part that could be prepared in
advance.

---

## Question 1 (confirmed, paraphrased): What are you going to do / build? (technical, specific, prior-art citations — guide suggests 200–400 words)

pyvar is an open-source (Apache-2.0), self-hostable financial risk
computation engine: 385 functions across Value-at-Risk, Expected
Shortfall, credit risk (PD/LGD/EAD, IFRS 9 ECL), derivatives pricing
(Black-Scholes, Heston, SABR, Dupire, LSM American/Bermudan), liquidity
risk (LCR, NSFR), operational risk (LDA, AMA, SMA), portfolio analytics,
ALM, and regulatory capital (Basel III/IV, FRTB, MiFID II, EMIR, Solvency
II, CRR2) — exposed as a REST API, JIT-accelerated with Numba, and now
also shipped as native tools for AI coding agents via a Model Context
Protocol server.

The proposed grant work is not building this from nothing — it exists
today, deployed and free to use. It funds a specific, scoped body of work
NLnet has historically prioritised for exactly this kind of infrastructure:

1. **Independent security review** of the API surface and dependency
   chain, findings published openly.
2. **Independent numerical/regulatory-formula audit** — a domain expert
   checking a sample of the 385 functions against their published
   Basel/FRTB/IFRS 9 source formulas, corrections published openly.
3. **Regulatory coverage extension** beyond the current scope (e.g. fuller
   Solvency II or CRR3), scoped once the above findings are in.
4. **Documentation and accessibility for smaller institutions** — the
   audience priced out of the same methodology large banks already use.

Prior art: the closest existing comparator is QuantLib, a mature
open-source (BSD) quantitative finance library — pyvar's own numerical
test suite cross-validates against it. QuantLib is a pricing/analytics
*library*; pyvar is closer to a hosted, regulator-shaped *service*
covering the compliance layer (Basel backtesting, FRTB capital, IFRS 9)
QuantLib does not itself implement. No other project this search
identified combines open licensing, this regulatory breadth, and REST/MCP
service delivery in one codebase — that combination, not any single
formula, is pyvar's actual novelty.

## Question 2 (confirmed, paraphrased): Problem and impact — which internet/commons problem does this solve, who benefits, why now? (guide suggests 150–250 words)

Regulatory-grade financial risk computation is normally locked inside
proprietary vendor platforms — closed-source, expensive per seat, and
unauditable by the risk teams whose regulatory capital depends on the
answer. If a formula is wrong, nobody outside the vendor can see it, let
alone fix it or prove it was ever wrong in the first place.

pyvar makes the same class of computation inspectable by anyone — a
regulator, an academic, a rival implementation, or the institution using
it — with every formula readable in the open-source repository, not
asserted by a vendor's marketing. That is a direct instance of the digital
commons and transparent-infrastructure principles NLnet funds in other
domains, applied to financial technology specifically.

Who benefits: smaller banks, credit unions, fintech startups, and
researchers outside the largest financial centres, who are today priced
out of the same risk methodology large institutions already use as a
matter of course. Removing that cost barrier is a concrete, checkable
outcome — every function's output is reproducible from a public
`pip install`, not a sales conversation.

Why now: pyvar has just shipped as native tooling for AI coding agents (an
MCP server, generated from the same source of truth as the REST API).
Open, machine-readable, auditable financial infrastructure matters more,
not less, as more of this class of work is done by AI agents rather than
only humans by hand.

## Question 3 (confirmed, paraphrased): Who is doing the work? (GitHub/papers/prior projects; NLnet funds individuals, no company required — guide suggests 100–200 words)

Filippo Buchicchio, based in the UK, is the applicant and lead/sole
developer of pyvar — an Anthropic-certified individual (CCA-F) building
and maintaining the project through Fibtec Limited, a UK-registered
company offering commercial enterprise support and private deployment of
pyvar as a sustainability model alongside the free public tier this grant
would help strengthen. (NLnet funds individuals directly and doesn't
require a company; naming Fibtec here is for transparency about the
sustainability model, not a claim that company backing is the basis for
eligibility.)

Prior work, all publicly checkable: the full commit history and 300+
merged pull requests at `github.com/fibtecltd/pyvar`; a live, deployed
production service at `pyvar.com`; a published Python SDK
(`pyvar-client` on PyPI); and a public technical write-up covering the
build, including regulatory bugs found and fixed before launch
(linked in the full application — see `docs/publications/` in the
repository).

## Questions 4–6: not yet identified

This session's search surfaced only 3 of NLnet's roughly 6 form questions.
**Filippo: please read the live form at `nlnet.nl/propose/` and either (a)
send back the remaining question text so answers can be drafted the same
way, or (b) draft those directly** — likely candidates based on how NLnet
describes its process elsewhere (unconfirmed) include a timeline/milestone
question, a budget breakdown, and a "why you, why NLnet" fit question —
but do not draft answers against a guess at the wording; wait for the real
text.

## Definition of done

- All six real question texts confirmed verbatim against the live form.
- Answers to questions 4–6 drafted in the same style once confirmed.
- Filippo has reviewed all six answers against the actual character/word
  limits the live form enforces (this draft used a third-party guide's
  approximate word counts, not confirmed limits).
- Submitted via `nlnet.nl/propose/` before **2026-11-03**.

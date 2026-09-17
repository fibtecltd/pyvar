# NLnet Restack application — draft answers to the real form

**Draft, not submitted.** Item 4 of `docs/roadmap-six-open-initiatives.md`,
rewritten 2026-09-17 per `docs/plan-nlnet-submission.md` §3a after Filippo
supplied the actual `nlnet.nl/propose/` form and GenAI policy pages. **This
supersedes the previous version of this file**, which was drafted against a
guessed "6 short questions" shape from a third-party guide — the real form
has a different, more granular field structure (table below), confirmed
directly from NLnet's own HTML.

**Target fund: Restack** (`nlnet.nl/restack/`), deadline **2026-11-03**.
See `docs/plan-nlnet-submission.md` §1 for the Restack-vs-CodeSupply
reasoning, unchanged by this rewrite.

**Resolved by Filippo (2026-09-17):** the application is submitted under
**Fibtec Limited**, not as an individual; the effective rate for budget
purposes is **€100/hour**. Both are now reflected below. **Still open:**
the LinkedIn-sourced experience text (Filippo will paste it), and one
factual point that needs a quick clarification, not a draft — see
"Experience / background" below.

---

## Fund

**Restack.**

## Proposal title (max 100 chars)

> pyvar: independent audit & regulatory coverage for an open risk engine

(71 characters — room to adjust.)

## Website(s) / repositories

- `https://www.pyvar.com`
- `https://github.com/fibtecltd/pyvar`
- `https://pypi.org/project/pyvar-client/`

## Abstract — summarise the project and expected results (max 1000 chars)

> pyvar is an open-source (Apache-2.0), self-hostable financial risk
> computation engine — 385 functions covering Value-at-Risk, Expected
> Shortfall, credit risk, derivatives pricing, liquidity risk, operational
> risk, portfolio analytics, and regulatory capital (Basel III/IV, FRTB,
> IFRS 9, Solvency II, EMIR). It's live at pyvar.com today, not a proposal
> to build from scratch.
>
> This grant funds a specific, scoped body of work: an independent
> security review of the API and dependency chain; an independent
> numerical audit of a sample of the 385 formulas against their published
> Basel/FRTB/IFRS 9 sources; extending regulatory coverage where the audit
> finds gaps; and documentation aimed at smaller institutions who are
> priced out of the same risk methodology large banks already use.
> Findings from all of the above are published openly, not kept internal.
>
> Expected result: a published audit trail proving (or correcting) the
> platform's regulatory-formula correctness, plus the coverage and docs
> work that trail identifies as needed.

(≈870 characters — leaves headroom.)

## Amount requested

**Proposed: €27,200** (272 hours at €100/hour — breakdown below). This is
a prefill, not a final number: comfortably inside €5,000–€50,000, credible
as a first-grant ask (≈54% of the cap, not maxing it out), and every line
below is adjustable independently if Filippo wants to trim or expand any
one milestone before submitting.

## Use of budget — tasks, effort, rate, expenses (max 4000 chars)

> The requested amount (€27,200, at €100/hour) funds four scoped
> milestones, sequenced so each one's findings can narrow the scope of the
> next rather than committing to fixed deliverables upfront:
>
> 1. **Independent security review** — 48 hours (6 days), **€4,800**.
>    Third-party review of the REST API surface, auth/JWT handling, and
>    dependency chain. Findings published in `docs/`, fixes tracked openly.
> 2. **Independent numerical/regulatory audit** — 96 hours (12 days),
>    **€9,600**. A domain expert checking a representative sample of the
>    385 functions against their published Basel/FRTB/IFRS 9/Solvency II
>    source formulas, corrections published openly (the same discipline
>    that already caught a ~79% Solvency II SCR understatement pre-launch,
>    done here by an external reviewer rather than the maintainer).
> 3. **Regulatory coverage extension** — 80 hours (10 days), **€8,000**.
>    Scoped once (1) and (2)'s findings are in; likely candidates are
>    fuller Solvency II or CRR3 coverage, narrowed by what the audit
>    actually flags as thin.
> 4. **Documentation for smaller institutions** — 48 hours (6 days),
>    **€4,800**. Worked examples and onboarding docs aimed at credit
>    unions, fintech startups, and researchers, not enterprise risk desks
>    who already have Bloomberg/Murex.
>
> Rate: **€100/hour**, applied uniformly across all four milestones —
> this covers both Fibtec's own development time (milestones 3–4) and the
> independent reviewers engaged for milestones 1–2. Expenses: none
> anticipated beyond that reviewer time, which is the main cost driver —
> compute cost is not a meaningful line item (pyvar's own Monte Carlo
> engine runs at sub-cent per scenario; see `docs/p9-scenario-volume-cost-audit.md`).

**Still Filippo's call:** the day-counts above are my estimate of
reasonable scope per milestone, not something Filippo confirmed line by
line — adjust any of the four before submitting if the real effort looks
different, especially milestones 1–2 where actual reviewer quotes (once
sought) should replace this estimate.

## Comparison — other projects, what's new, considered contributing (max 4000 chars)

> The closest existing comparator is **QuantLib**, a mature open-source
> (BSD) quantitative finance library — pyvar's own numerical test suite
> already cross-validates against it directly. QuantLib is a
> pricing/analytics *library*: it gives you the building blocks, not the
> compliance layer. pyvar is closer to a hosted, regulator-shaped
> *service* — Basel traffic-light backtesting, FRTB capital calculation,
> IFRS 9 ECL provisioning, Solvency II SCR — delivered as a REST API (and
> now an MCP server for AI coding agents) rather than a library you
> integrate and build the compliance logic around yourself.
>
> We did consider contributing this compliance layer directly to
> QuantLib rather than building a separate project. Two reasons we
> didn't: QuantLib's C++-first architecture and contribution model isn't
> well suited to a REST/async-job service shape (SQS-backed Monte Carlo
> jobs, tiered API access, a hosted deployment), and pyvar's regulatory
> layer is deliberately opinionated about which Basel/FRTB version and
> which regulatory constants are correct — encoding that as a strict
> position (see `CLAUDE.md`'s `[REGULATORY]`-marked constants, changeable
> only via a reviewed `reg/*` branch) fits better as its own project than
> as a general-purpose library flag.
>
> No other project this search identified combines open licensing, this
> regulatory breadth, and REST/MCP service delivery in one codebase —
> that combination, not any single formula, is pyvar's actual novelty.
> What pyvar does *not* claim novelty on: the underlying math (Black-
> Scholes, Heston, SABR, Monte Carlo VaR) is textbook and intentionally
> unoriginal — correctness against the published standard is the entire
> point, not a new model.

(≈1650 characters — leaves headroom; can be extended with more detail on
prior art if Filippo wants a fuller comparison.)

## Technical challenges (max 4000 chars, optional but recommended)

> The main technical risk isn't building new functionality — it's proving
> the existing 385 functions are correct against sources an external
> reviewer trusts, at a scale where manual line-by-line audit of every
> function isn't realistic within the grant's budget. The mitigation is
> sampling: prioritising the highest-stakes/highest-usage functions
> (Basel capital ratios, FRTB IMA/SA, Solvency II SCR) for full audit
> rather than attempting uniform coverage across all 385 in one pass —
> the same triage discipline already used internally (see
> `docs/caveat-triage-batch-plan.md`), now applied by an independent
> reviewer instead of the maintainer.
>
> A secondary risk: regulatory constants and formulas change (BCBS
> shock recalibrations, Basel IV phase-in dates). The audit needs to
> pin down which version of each standard pyvar targets and verify that's
> stated explicitly, not left implicit — a gap the internal review
> already found once (stale pre-2024 IRRBB shock values, fixed in v0.1.0).

(≈1000 characters.)

## Ecosystem — dependencies, main users (max 2000 chars, optional)

> pyvar depends on NumPy/Numba/SciPy for compute, FastAPI for the API
> layer, and Celery/SQS for the async job pipeline — all mainstream,
> actively maintained open-source projects; no unusual or fragile
> dependencies. `pyvar-client` (PyPI) and `pyvar-mcp` (a Claude Code
> plugin marketplace entry) are the two integration surfaces most likely
> to bring in outside contributors.
>
> Main users today: individual developers and researchers exploring
> quantitative finance in the open, per pyvar.com's own (small, unaudited)
> usage. The grant's stated audience — smaller banks, credit unions,
> fintechs, and researchers outside major financial centres — is the
> intended *next* audience, not yet the confirmed current one; being
> honest about that gap rather than overclaiming existing institutional
> adoption.

(≈780 characters.)

## Experience / background (max 2000 chars, optional)

> Filippo Buchicchio, UK-based, leads development of pyvar through Fibtec
> Limited (UK-registered), the applicant entity. **[Filippo — paste the
> LinkedIn excerpt here; I don't have enough verified detail about your
> prior work history to draft this section honestly, and the policy
> explicitly wants applicants' own words, not AI-drafted biographical
> claims.]**
>
> What's independently checkable regardless of biographical detail: the
> full commit history and 300+ merged pull requests at
> `github.com/fibtecltd/pyvar`, a live production deployment at
> `pyvar.com`, a published SDK (`pyvar-client` on PyPI), and public
> technical write-ups covering the build — including four regulatory bugs
> found and fixed before launch (`docs/publications/`).

**One factual point needs a quick check before this is finalised, not a
draft:** Filippo noted he's "the main developer but not the only one." The
actual git history (`git log --format='%an <%ae>' | sort -u`) shows only
Filippo Buchicchio as a human commit author — Claude appears as AI
co-author, not a second human. Worth clarifying which this refers to
before the field is written, since NLnet's own "no misrepresentation"
principle is specifically about who did the work:

- If it means Claude Code's contribution — that's already covered by the
  AI-disclosure section and `README.md`'s GenAI statement, no change
  needed here.
- If there's a genuine second human contributor (a collaborator, a
  contractor, informal help) not yet reflected in git authorship — that's
  worth naming here directly, since NLnet explicitly asks who is doing the
  work, and it strengthens rather than weakens the "who's doing the work"
  case for a company-entity application.

## Other funding (max 1000 chars, optional)

> Fibtec Limited offers commercial enterprise support and private
> deployment of pyvar as a sustainability model alongside the free public
> tier — **[Filippo: confirm current revenue status here; is this
> generating real income yet, or still pre-revenue? The prior brief didn't
> specify and I don't want to imply traction that doesn't exist yet.]**
> This grant is not the project's only funding mechanism, but is not
> currently supplementing an existing grant either — pyvar has not
> previously received NLnet or comparable grant funding.

## AI disclosure (required — Yes/No + prompt log, max 8000 chars or file upload)

**This is new, required, and genuinely needs Filippo's decision — not
something to draft speculatively.** Two separate things the form asks for:

1. **"Did you use generative AI in writing this proposal?"** Given this
   proposal's text itself would be drafted with Claude Code's assistance —
   consistent with how every other piece of writing in this repository has
   been produced — the honest answer is **Yes**. Answering "No" would be a
   misrepresentation the policy explicitly prohibits, regardless of how
   the framing question below gets resolved.
2. **The prompt-provenance log** — actual prompts/interactions and
   unedited output, not a summary invented after the fact. This needs to
   be compiled from the real session(s) used to draft the final
   submission text, once that drafting happens — not fabricated now
   against a draft that will change.

**Framing resolved (2026-09-17):** per `docs/plan-nlnet-submission.md` §3a,
this section carries the full, honest disclosure — model, prompts, dates,
unedited output — plainly and factually, without expanding it into a
narrative about pyvar's broader AI-build story. The rest of the
application (abstract, budget-use, comparison, above) is written the same
way: focused on the engine and the audit work the grant funds, not led by
"built by an AI agent." Nothing is hidden, nothing is minimized where the
form actually asks — the AI-authorship *story* just isn't the pitch.

## Contact information

- **Name:** Filippo Buchicchio
- **Email:** filippo.buchicchio@gmail.com (or a Fibtec address, if
  Filippo prefers — not assumed here)
- **Entity type:** **SME company** — resolved 2026-09-17, applying as
  Fibtec Limited, not as an individual.
- **Organisation name:** Fibtec Limited
- **Country:** United Kingdom

## Definition of done

- ~~Amount, entity type, and the AI-authorship framing call~~ — resolved
  2026-09-17 (plan doc §4): Fibtec Limited, €100/hour → €27,200 proposed,
  audit-work-first framing.
- The "not the only developer" clarification above is resolved.
- The "Experience" and "Other funding" fields are written in Filippo's own
  words (LinkedIn excerpt pending), not left as placeholders.
- The AI-disclosure prompt log is compiled from the actual session(s) used
  to finalise this text — after finalisation, not before.
- `README.md` carries a proper GenAI-use disclosure statement (plan doc
  §3a) before the "website" field above is something an assessor would
  actually visit and check.
- Submitted via `nlnet.nl/propose/` before **2026-11-03**.

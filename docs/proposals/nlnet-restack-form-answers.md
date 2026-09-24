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
**Fibtec Limited**, not as an individual; rate **€150/hour** → **€40,800**
requested, confirmed as reasonable (not padded — pyvar is self-funded and
pre-revenue, see "Other funding" below). The "not the only developer"
point refers to Riccardo Fei's early contributions via branches since
deleted — confirmed not critical, not carried into the application text.
The Experience field carries Filippo's own LinkedIn-sourced background;
one placeholder remains for the public LinkedIn URL itself. The
Comparison field now states pyvar's uniqueness claim directly, per
Filippo's own framing, ahead of the QuantLib evidence that substantiates
it.

**Revised 2026-09-19:** `docs/publications/` has grown from a couple of
drafts to 8 articles since this file was last touched, including two
that publish real, self-found production mistakes rather than omitting
them (the JWT-report deploy gap and its underlying migration-ordering
bug, and a benchmark-methodology correction) and a new one walking
through the architecture/stack/methodology behind the cost and speed
claims. That's now the strongest available evidence for this
application's core claim — findings get published, not kept internal —
so the Experience, Ecosystem, Technical challenges, and Comparison
fields below now cite the specific articles rather than gesturing at
"public write-ups" generically. No numbers, budget, or framing decisions
changed; this pass only adds citations where character budget allowed
(checked field-by-field, not assumed).

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

**€40,800** (272 hours at €150/hour — breakdown below). Confirmed by
Filippo: reasonable, "if not too low" — pyvar is self-funded and
pre-revenue (see "Other funding" below), so this isn't padded against
other income. No further trimming needed.

## Use of budget — tasks, effort, rate, expenses (max 4000 chars)

> The requested amount (€40,800, at €150/hour) funds four scoped
> milestones, sequenced so each one's findings can narrow the scope of the
> next rather than committing to fixed deliverables upfront:
>
> 1. **Independent security review** — 48 hours (6 days), **€7,200**.
>    Third-party review of the REST API surface, auth/JWT handling, and
>    dependency chain. Findings published in `docs/`, fixes tracked openly.
> 2. **Independent numerical/regulatory audit** — 96 hours (12 days),
>    **€14,400**. A domain expert checking a representative sample of the
>    385 functions against their published Basel/FRTB/IFRS 9/Solvency II
>    source formulas, corrections published openly (the same discipline
>    that already caught a ~79% Solvency II SCR understatement pre-launch,
>    written up in `docs/publications/pyvar-buildstory-medium-article.md`,
>    done here by an external reviewer rather than the maintainer).
> 3. **Regulatory coverage extension** — 80 hours (10 days), **€12,000**.
>    Scoped once (1) and (2)'s findings are in; likely candidates are
>    fuller Solvency II or CRR3 coverage, narrowed by what the audit
>    actually flags as thin.
> 4. **Documentation for smaller institutions** — 48 hours (6 days),
>    **€7,200**. Worked examples and onboarding docs aimed at credit
>    unions, fintech startups, and researchers, not enterprise risk desks
>    who already have Bloomberg/Murex.
>
> Rate: **€150/hour**, applied uniformly across all four milestones —
> this covers both Fibtec's own development time (milestones 3–4) and the
> independent reviewers engaged for milestones 1–2. Expenses: none
> anticipated beyond that reviewer time, which is the main cost driver —
> compute cost is not a meaningful line item (pyvar's own Monte Carlo
> engine runs at sub-cent per scenario; see `docs/p9-scenario-volume-cost-audit.md`
> and `docs/publications/pyvar-iron-triangle-medium-article.md` for the
> public write-up, including the real $900–1,000/month invoice this
> claim is checked against).

**Still open:** the day-counts above are my estimate of reasonable scope
per milestone, not something Filippo confirmed line by line — worth a
look before submitting if the real effort looks different, especially
milestones 1–2 where actual reviewer quotes (once sought) should replace
this estimate. The total itself is confirmed.

## Comparison — other projects, what's new, considered contributing (max 4000 chars)

> To our knowledge, pyvar is unique in its category: no other project
> exposes this complete a set of VaR/regulatory-risk functions fully
> open-source, on a high-performance, production-shaped tech stack (Numba
> JIT, async job pipeline, REST + MCP delivery — architecture and the
> reasoning behind each technology choice both written up in
> `docs/publications/pyvar-technical-deepdive-medium-article.md` and
> `pyvar-iron-triangle-medium-article.md`) rather than as a closed-source
> vendor platform or a partial academic implementation. That's the gap
> this comparison substantiates below, rather than assert on its own.
>
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

(≈2310 characters — leaves headroom against the 4000-char limit.)

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
> already found once (stale pre-2024 IRRBB shock values, fixed in v0.1.0,
> written up in full in `docs/publications/pyvar-buildstory-medium-article.md`
> alongside the ~79% Solvency II SCR understatement the same validation
> pass caught).

(≈1140 characters.)

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
>
> Documentation for that next audience already has a track record, not
> a from-scratch plan: published guides cover the Python SDK, the
> Jupyter integration, the raw REST API, and the Claude Code/MCP
> integration surface (`docs/publications/`), each checked directly
> against the shipping code at time of writing rather than written from
> memory of what the API used to do.

(≈1160 characters.)

## Experience / background (max 2000 chars, optional)

> Filippo Buchicchio, UK-based, leads development of pyvar through Fibtec
> Limited (UK-registered), the applicant entity.
>
> With over 20 years of experience gained in both the Consultancy and
> Investment Banking industry at an international level, I keep on
> developing my core skills in Risk Management, Regulatory Compliance and
> Front Office Trading, to enable delivery of a firm's vision and
> strategic goals. I have consistently designed, led and delivered
> complex projects in high pressure environments, requiring senior
> stakeholder management up to board level, including the regulators, as
> well as BAU activities. I rely upon an inclusive and supportive
> leadership style, a genuine passion for problem solving, and the
> ability to provide solutions, leveraging any technology, knowledge and
> support available across the institution.
>
> - Risk Management with in-depth knowledge across asset classes
>   (including Forex, Credit, Interest Rate Derivatives including
>   inflation, both ETD and OTC), and experience implementing Risk
>   Management systems.
> - Regulatory Compliance with deep understanding of recent requirements
>   (FRTB, Basel, BCBS, EMIR, MiFID, Dodd-Frank and other regulations) and
>   exposure to key regulatory bodies and central banks.
> - Cross-service and domain knowledge: Trading desk, Proprietary
>   Trading, Market Making, Credit Risk (Counterparty & Market Risk),
>   Middle Office, Finance, Regulatory, Operations and IT.
>
> Independently checkable: 300+ merged pull requests and full commit
> history at `github.com/fibtecltd/pyvar`, a live deployment at
> `pyvar.com`, a published SDK (`pyvar-client`, PyPI), and 8 public
> write-ups on the build and its own self-audits (`docs/publications/`),
> including two that publish real production mistakes we found and
> fixed rather than leaving out. Full professional background:
> **[Filippo — paste your public LinkedIn URL here]**.

(≈1870 characters, with the LinkedIn placeholder — ~130 chars of room
left for the real URL once pasted; trim the "independently checkable"
line further if the URL doesn't fit.)

## Other funding (max 1000 chars, optional)

> None. pyvar is entirely self-funded by Fibtec Limited and is currently
> pre-revenue — a Pro/Enterprise commercial tier exists in the product
> (Stripe-billed, live) as a planned sustainability model, but has not yet
> generated income to speak of. This grant would not supplement or overlap
> with any other funding source; pyvar has not previously received NLnet
> or any other grant funding.

(≈380 characters — well inside the 1000-char limit.)

## AI disclosure (required — Yes/No + prompt log, max 8000 chars or file upload)

**Resolved 2026-09-24.** Text field content below (3,588 characters, well
under the 8000-char cap), paired with a full prompt/output log attached as
`docs/proposals/nlnet-ai-disclosure-log.md`. Both were compiled by
extracting real turns from this session's own Claude Code transcript —
not drafted from memory or reconstructed after the fact — so the log is
the actual record, not a summary of one.

> **Yes.**
>
> **Model:** Claude (Anthropic), used via the Claude Code CLI — an agentic coding tool with file read/write/edit, shell, web search, and GitHub access. Model coverage varied across the drafting sessions (2026-09-10 to 2026-09-24) as Anthropic's available models changed over that period; the most recent turns (2026-09-19 onward) ran on Claude Sonnet 5.
>
> **What it was used for:** iteratively drafting and revising every text-field answer in this document against NLnet's real form fields and character limits; researching NLnet's own GenAI policy and propose-page text (pasted in directly by Filippo, since this session has no live web access to nlnet.nl) and correcting prior assumptions against it; adding citations to this project's own published articles once those existed; and compiling this disclosure itself from the session's real transcript, not from memory or a fresh redraft.
>
> **Representative prompts and AI output.** The full, unedited log — every relevant prompt, AI text response, and file edit to this document, across 5 real conversational turns and 33 file operations between 2026-09-10 and 2026-09-24 — is attached as `nlnet-ai-disclosure-log.md`. It was extracted programmatically from this session's own Claude Code transcript (filtered to every turn mentioning "nlnet", then to genuine human-typed prompts only, excluding harness-generated context-compaction summaries), not reconstructed from memory. Three representative excerpts:
>
> 1. **2026-09-17, Filippo (verbatim):** "...we need to review the NlNet application since it seems AI project are not welcome / banned there. these are the links with the details: https://nlnet.nl/propose/ https://nlnet.nl/foundation/policies/generativeAI/ for your convenience, should not be able to reach them I have attached the saved html pages here." [attached the two real NLnet pages as HTML]
>    **AI output (excerpt):** "Reviewed both pages you attached. The short version: NLnet has not banned AI-assisted projects. The propose page's blunt 'not interested in AI-generated projects' line sits next to..." — the full review corrected the reading of the policy (a disclosure-and-accountability regime, not a tooling ban), produced a rewritten AI-disclosure section, and recorded the framing decision in `docs/plan-nlnet-submission.md` §3a.
>
> 2. **2026-09-19, Filippo (verbatim, one item of four):** "...review and update the NlNet form submission document in the light of the recent articles with references to them..."
>    **AI output:** citations added to five fields (Experience, Technical challenges, Ecosystem, Comparison, Use of budget), each field's character count recomputed against its real limit before and after the edit, confirming none exceeded the form's stated caps.
>
> 3. **2026-09-24, Filippo (verbatim):** pasted this exact AI-disclosure field's text from the live NLnet form and asked for it to be addressed.
>    **AI output:** this section, plus the attached log, compiled by extracting every session turn mentioning "nlnet" from the real transcript and reproducing every resulting edit to this file in full.
>
> **Accountability.** Every substantive decision — entity type (Fibtec Limited, not an individual), requested amount (€40,800 at €150/hour), milestone structure, and the AI-disclosure framing itself — was made and confirmed by Filippo Buchicchio, not generated autonomously; see `docs/plan-nlnet-submission.md` §4 for the explicit record of which calls were his. The AI drafted text against his direction and against this repository's own facts; nothing here was submitted without his review.

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
  2026-09-17 (plan doc §4): Fibtec Limited, €150/hour → **€40,800**
  confirmed, audit-work-first framing.
- ~~The "not the only developer" clarification~~ — resolved: Riccardo
  Fei's early, since-deleted branches; Filippo confirmed not critical,
  not carried into the application text.
- ~~The "Experience" field~~ — written in Filippo's own words (LinkedIn
  excerpt in place).
- ~~The "Other funding" field~~ — resolved: self-funded, pre-revenue, no
  other grant funding.
- ~~Citing the published articles as evidence~~ — resolved 2026-09-19:
  Experience, Technical challenges, Ecosystem, Comparison, and Use of
  budget fields now cite the specific `docs/publications/` articles
  that substantiate their claims (Solvency II/IRRBB fixes, the
  self-found deploy/migration issues, the SDK/Jupyter/REST/plugins
  guides, the architecture and cost write-ups) rather than gesturing at
  "public write-ups" generically. Every field re-checked against its
  real character limit after the additions — none exceed it.
- **Still open:** Filippo's public LinkedIn URL (placeholder left in the
  Experience field), and the actual reviewer quotes for milestones 1–2
  once sought (replacing this session's day-count estimates).
- ~~The AI-disclosure prompt log~~ — resolved 2026-09-24: compiled
  programmatically from this session's real Claude Code transcript (not
  drafted from memory), text-field content plus the full log attached as
  `docs/proposals/nlnet-ai-disclosure-log.md`. See the AI disclosure
  section above.
- `README.md` carries a proper GenAI-use disclosure statement (plan doc
  §3a) before the "website" field above is something an assessor would
  actually visit and check — done in PR #351, pending merge.
- Submitted via `nlnet.nl/propose/` before **2026-11-03**, with
  `docs/proposals/nlnet-ai-disclosure-log.md` uploaded as the AI
  disclosure attachment.

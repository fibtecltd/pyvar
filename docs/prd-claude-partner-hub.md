# PRD: pyvar.com — Claude Partner Network / Partner Hub Submission

**Author:** Fibtec Limited
**Status:** Draft — internal review, not yet submitted
**Last updated:** 2026-09-03

---

## Positioning note — read this before the rest of the document

Anthropic's Claude Partner Network Services Track (announced 2026-06-03,
[anthropic.com/news/services-track-partner-hub](https://www.anthropic.com/news/services-track-partner-hub))
is built for **services and consulting firms** that deploy Claude for
enterprise clients. Its entry tier (Select) requires at least 10 active
certified individuals, 2 joint customers with Claude in production in the
past 12 months, and 1 public customer story.

Fibtec does not meet that bar today, and this document does not pretend
otherwise: pyvar.com is a **product** — an open-source risk computation
platform — not a consulting practice, and it has no named enterprise
deployments to cite. Every number below is something that can actually be
checked against this repository's own history (commit log, CHANGELOG,
PyPI, the live site) — nothing here is a projection or an invented ROI
percentage.

What this document *is*: a case-study-shaped PRD demonstrating pyvar as a
**Claude-native product** — built with Claude Code from scaffolding
onward, shipping a real Claude Code plugin (`pyvar-mcp`) and IPython
integration (`pyvar-jupyter`), and running a genuinely regulatory-grade
codebase that Claude Code has both built and hardened. It is meant to
serve as (a) a public case-study artifact Fibtec can point to today, and
(b) the foundation a future, honest Services Track application would be
built on once real joint-customer deployments exist.

---

## 1. Executive Summary

**Target industry:** Financial risk management software — market risk,
credit risk, derivatives pricing, liquidity risk, operational risk,
portfolio analytics, ALM, and regulatory capital.

**Core problem:** Regulatory-grade risk computation (VaR/ES, Basel
backtesting, FRTB capital, Solvency II SCR, derivatives Greeks) is
normally locked behind proprietary vendor platforms — closed-source,
expensive, and effectively unauditable by the firms that rely on them for
capital calculations.

**Proposed solution:** pyvar.com — an open-source (Apache-2.0), Numba
JIT-accelerated REST API exposing 385 risk functions across 8 domains,
built and hardened end-to-end using Claude Code, and integrated back into
the Claude ecosystem via a native MCP server and an IPython/Jupyter
extension.

**Target model:** Whatever Claude model the end user's Claude Code session
or Claude.ai chat is running — `pyvar-mcp` is a tool surface, not a
model-hosting service. It makes no assumption about and has no dependency
on a specific model version or a Bedrock/Vertex hosting path; the API
backend (Celery/SQS/Numba on ECS Fargate) has no LLM in its own runtime
path at all. The AI-native part of this story is upstream, in how the
product was *built*, not in what model serves a request at inference time.

---

## 2. Verified Impact & Evidence

Everything in this section is checkable directly against the repository
(`git log`, `CHANGELOG.md`, the PyPI project pages, or the live site) —
not a projection.

- **385 risk functions across 8 domains**, generated from and traceable to
  the live OpenAPI schema: Market Risk (71), Derivatives (62), Credit Risk
  (55), Portfolio Analytics (50), Operational Risk (44), Liquidity Risk
  (40), ALM (33), Regulatory (30).
- **Regulatory correctness bugs found and fixed by Claude Code**, not
  shipped and forgotten (from `CHANGELOG.md`'s `[0.1.0]` release notes):
  - **Solvency II SCR credit-risk formula (Art. 200–201)** — corrected an
    error that understated required capital by roughly 79%.
  - **rBergomi kernel** — added the missing fractional-Brownian
    autocovariance structure the model requires.
  - **EMIR clearing obligation scope** — financial counterparties are now
    correctly in scope for all asset classes, not evaluated per-class.
  - **IRRBB standard shocks** — recalibrated to the BCBS d578 (2024)
    values.
  - A real Monte Carlo CVaR-optimizer solver bug and a core-deposit
    duration accuracy gap, both caught and fixed in a single Claude Code
    pass over the numerical caveat backlog (PR #306).
  - A follow-on, domain-batched pass over that same caveat backlog (PRs
    #314–#318, four independently reviewed PRs folded into a single merge
    to minimise CDK CodePipeline runs): a genuine multi-state CreditMetrics
    model (Gupton, Finger & Bhatia 1997) replacing what had been a
    pass-through; CRR2 Art. 395(1)'s EUR 150m institution-counterparty
    absolute alternative, previously accepted as a parameter and silently
    ignored despite the parameter's own docstring; the standard market
    asset-swap convention (O'Kane 2000) for bonds priced away from par;
    and Perold's (1988) missing opportunity-cost leg in transaction-cost
    analysis — 8 functions fixed in total, plus one caveat-catalogue entry
    (`compute_rolling_var`) corrected with no code change, because the
    docstring bug it described had already been fixed two PRs earlier and
    nobody had gone back to update the caveat text. Two of the 8 fixes had
    a bug of their own, caught by a Claude Code review pass *before*
    merge, not written correctly the first time: the new CreditMetrics
    `pd` parameter was validated but silently unused (default-threshold
    math came entirely from the transition matrix, contradicting the
    function's own docstring), and the CRR2 fix's own docstring broke the
    portal's function-title generator for unrelated functions (an
    acronym-casing heuristic mistook a constant-name fragment for a real
    acronym) — both fixed before the affected PRs were merged, and the
    CRR2 PR followed this repo's own `reg/*` governance rule requiring a
    second human reviewer, not just a Claude Code review.
- **Transparent uncertainty disclosure, not silent overclaiming**: 91 of
  385 functions (23.6%) carry a documented `caveat` in the public function
  catalogue (`portal/functions.json`) — a modeling simplification or an
  independent-verification gap disclosed to every API consumer, not
  buried in an internal doc. Unchanged by the caveat-triage pass above:
  every fix there was additive/opt-in, narrowing or correcting a caveat's
  text rather than clearing it outright, so the 23.6% figure is the same
  before and after — re-verified directly against the live catalogue at
  time of this update, not carried forward from an earlier count.
- **649 commits, 300 merged PRs**, of which **131 commits** carry a
  `Co-Authored-By: Claude` trailer — a majority-AI-authored,
  regulatory-grade codebase that has been through a real public-launch
  security review (see §4) rather than a toy demo repo. (These three
  figures were re-verified directly against `git log` and the GitHub API
  for this update and replace an earlier, lower count in a prior draft of
  this document — the same "recount before republishing" discipline this
  PRD's companion Medium article documents for its own caveat-rate
  correction.)
- **Real PyPI distribution, verified end-to-end**: `pyvar-client` (the
  typed Python SDK) publishes via GitHub Actions OIDC Trusted Publishing —
  confirmed not just by a green CI run but by directly querying PyPI's own
  API and `pip install`-ing the published package in a clean environment.
  Three versions shipped (v0.1.0–v0.1.2) the same day the SDK and its CLI
  landed.
- **A working Claude Code plugin submission**, not a hypothetical one:
  `pyvar-mcp` was submitted to the `claude-plugins-community` marketplace
  and the submission was received by Anthropic's review team — see §5.

---

## 3. System Architecture & Model Context Protocol (MCP)

```
[Claude Code / Claude.ai]
        │  (MCP tool calls)
        ▼
   [pyvar-mcp]  ── thin wrapper, stdlib urllib only ──►  [pyvar.com REST API]
        │                                                        │
        │  (or, outside Claude entirely)                         ▼
        ▼                                          [FastAPI] ──► [Celery + SQS FIFO]
[pyvar-client SDK]  ──►  [pyvar.com REST API]                     │
        │                                                          ▼
        ▼                                          [Numba JIT engine, ECS Fargate + Spot]
   [pyvar CLI]                                                     │
                                                                    ▼
                                                    [Aurora Serverless v2 audit log]
                                                    [S3 large-result offload]

[pyvar-jupyter]  ── %pyvar / %%pyvar magics ──►  [pyvar-client]  ──►  [pyvar.com REST API]
```

- **MCP server integration**: `pyvar-mcp` exposes all 385 functions as
  Claude Code tools, plus two generic tools
  (`list_pyvar_functions`/`call_pyvar_function`) so a model isn't forced
  to guess among 385 individually-named ones. It is a thin wrapper over
  the live REST API — every tool call is a real HTTPS request to
  `pyvar.com`, not a bundled copy of the compute engine, so there is
  nothing to keep in sync beyond the API contract itself.
- **Generated, not hand-maintained**: the plugin catalogue
  (`.claude-plugin/marketplace.json`, `plugins/*`) and the MCP tool
  catalogue (`plugins/mcp/pyvar_mcp/_generated/functions.py`) are both
  generated directly from this repository's own source of truth
  (`.claude/skills/*`, `portal/functions.json`) by committed generator
  scripts, with CI failing the build if committed output ever drifts from
  what regenerating produces.
- **Three independent integration surfaces**, all built this same
  development cycle, all layered on the one `pyvar-client` SDK rather than
  duplicating HTTP/auth logic: the MCP plugin (`plugins/mcp`), the
  IPython/Jupyter extension (`pyvar-jupyter`, `%pyvar`/`%%pyvar` magics +
  rich HTML display), and the CLI (`pyvar-client`'s own `pyvar` command).
- **Knowledge retrieval**: 13 Claude Code skills (8 domain skills — one
  per risk domain — plus 5 architecture skills covering pyvar's own
  technical stack) ship alongside the plugins, giving a model instructional
  context on *when* and *how* to use a given risk function, not just the
  tool signature.

---

## 4. Safety, Compliance & Guardrails

This section describes pyvar's own guardrails — the product's, not
Anthropic's model-level safety training, which pyvar relies on but does
not itself implement or claim credit for.

- **Data handling**: `pyvar-mcp`'s only external dependency is the pyvar
  REST API itself — no third-party services, no telemetry, no analytics.
  Data sent is exactly what the user explicitly provides to a function
  call (e.g. a returns series, a portfolio value), over HTTPS with the
  user's own API key. No portfolio or position data is retained beyond
  pyvar's documented job-result TTL (VaR jobs only; the other 384
  functions are synchronous with no persistence).
- **Regulatory constants are hard-coded, not model-decided**: VaR
  confidence-level bounds ([0.90, 0.9999]), Basel traffic-light breach
  zones (green < 5, yellow 5–9, red ≥ 10), and FRTB P&L Attribution
  Test thresholds are enforced in `schemas/var.py` and `engine/` — a
  calling model cannot talk the API into relaxing a Basel Committee
  threshold.
- **Anti-abuse on the one write endpoint**: `POST /auth/register` checks a
  vendored disposable-email blocklist and is rate-limited per-IP before
  touching the database or sending email — added specifically because it
  previously had neither.
- **Full public-launch security review, not a one-time scan**: org-wide
  2FA enforced; Secret Protection (secret scanning + push protection) and
  Code Security (CodeQL default setup) enabled and confirmed running a
  successful first scan; a full-history `gitleaks` scan across every commit
  on every branch as of the pre-launch review (zero real secrets found);
  branch protection on
  `master` (blocks force-push and direct pushes, requires PR + 6 named
  status checks); GitHub Actions pinned to commit SHA; least-privilege
  `permissions:` blocks added to every workflow.
- **Human-in-the-loop by design, not by exception**: the ~26% of functions
  carrying a documented modeling caveat are flagged to every caller via
  the public function catalogue and `SECURITY.md`, rather than presented
  as uniformly production-validated. This is the honesty mechanism this
  PRD itself is trying to model in its own numbers.

---

## 5. Deployment Timeline & Partner Readiness

**Real build history** (`docs/pyvar_release_plan.md`), 9 phases over
~28 weeks: P1 CLAUDE.md & scaffolding → P2 engine implementation (all 385
functions) → P3 API endpoints → P4 AWS CDK deployment → P5 testing &
validation → P6 usage statistics & observability → P7 cost/performance
optimization → P8 portal finalisation → P9 public launch & GitHub.

**Where this stands today, verified:**

- v0.1.0 publicly released 2026-08-22; `pyvar-client` SDK and CLI shipped
  to PyPI the same development cycle, ahead of their original v0.2.0
  schedule.
- Repository flipped from private to public after a dedicated
  security/hygiene pass (this document's §4).
- `pyvar-mcp` submitted to `claude-plugins-community` — submission
  received by Anthropic's review team, decision pending.
- `pyvar-jupyter` (the IPython/Jupyter magics integration) shipped ahead
  of its original v0.2.0 schedule too, with every example notebook's
  numbers verified against the real engine before publishing rather than
  assumed.
- A follow-on caveat-triage pass (PRs #314–#318, see §2) shipped since the
  v0.1.0 launch — 8 further Tier-C caveat resolutions across credit-risk,
  operational, regulatory, derivatives, liquidity, and portfolio-analytics
  (one of them, CRR2 Art. 395(1), a `reg/*`-governed regulatory-logic
  change that went through this repo's second-human-reviewer requirement
  rather than merging on Claude Code review alone), plus one
  caveat-catalogue-only correction in market-risk.

**Certified staff**: 1 — Filippo Buchicchio (Fibtec) holds Anthropic's
CCA-F certification. **Joint customers**: none to report. Neither closes
the gap against Services Track Select-tier eligibility (10 active
certified individuals, 2 joint customers in production in the past 12
months) opened at the top of this document — one certified individual is
progress worth recording honestly, not a claim that the bar is met.

**Near-term next steps** (not yet done, listed as such):
1. Get an actual review outcome on the `pyvar-mcp` marketplace submission.
2. Publish the companion Medium article (illustrated technical deep-dive)
   as a public artifact this PRD's claims can be checked against.
3. Revisit Services Track eligibility only once real joint-customer
   deployments exist — not before.

---

## Appendix: Sources

- [Introducing the Services Track and Partner Hub of the Claude Partner Network](https://www.anthropic.com/news/services-track-partner-hub) — Anthropic, 2026-06-03.
- `CHANGELOG.md` (this repo) — regulatory fixes, PyPI publish dates.
- `docs/pyvar_release_plan.md` (this repo) — P1–P9 build history.
- `portal/functions.json` (this repo) — function/domain counts, caveat rate.
- `docs/proposals/marketplace-submission-content.md` (this repo) — the actual `pyvar-mcp` marketplace submission content.
- `git log` (this repo) and the GitHub REST/search API — commit and PR
  counts, Claude co-authorship count.

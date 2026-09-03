# Draft: Partner Hub submission email / cover note

**Status:** Draft — about to be sent. The portal's "My Content" section
(the only mechanism that fit pyvar.com's situation without a third-party
customer relationship) has already had the PRD PDF uploaded; this email is
a separate, direct follow-up.

**Suggested subject:** pyvar.com — a Claude-native, regulatory-grade risk
platform (Fibtec Limited)

**Recipient:** partner-support@anthropic.com — supplied by Filippo as the
address he has available; not independently verified against an Anthropic
published source in this session (no browsing access to confirm).

---

Hello,

I'm writing on behalf of Fibtec Limited to introduce **pyvar.com** — an
open-source (Apache-2.0) financial risk computation platform built,
hardened, and shipped end-to-end with Claude Code, and integrated back
into the Claude ecosystem via a native MCP server and IPython/Jupyter
extension.

**What it is:** 385 regulatory-grade risk functions across 8 domains
(Market Risk, Derivatives, Credit Risk, Portfolio Analytics, Operational
Risk, Liquidity Risk, ALM, and Regulatory Capital) — VaR/ES, Basel
backtesting, FRTB capital, Solvency II SCR, derivatives Greeks — exposed
as a REST API and served through a Numba JIT-accelerated Celery/SQS
pipeline on AWS.

**Why we think it's a genuine Claude Partner Network case study, not a
generic "we used AI" pitch:**

- Claude Code built it end-to-end, from the initial `CLAUDE.md` scaffold
  through the security review that preceded public launch — not
  boilerplate, but the Numba compute kernels themselves.
- It found real regulatory bugs before they shipped: a Solvency II SCR
  formula that understated required capital by roughly 79%, a missing
  fractional-Brownian structure in the rBergomi volatility model, EMIR
  clearing-obligation scope evaluated per-asset-class instead of
  correctly across all classes, and stale pre-2024 IRRBB shock values —
  each one caught by building and running an independent cross-validation
  suite, not by inspection.
- It's transparent about what isn't fully battle-tested: 91 of 385
  functions (23.6%) carry a documented modeling caveat, disclosed inline
  to every API caller — not buried in an internal doc.
- 649 commits, 300 merged PRs, 131 of those commits carrying a
  `Co-Authored-By: Claude` trailer, all of it through a real public-launch
  security review (org-wide 2FA, CodeQL, full-history secret scanning,
  branch protection).
- It built its own way back into the Claude ecosystem: a submitted
  `pyvar-mcp` Claude Code plugin (all 385 functions as tools, plus 13
  domain/architecture skills), an IPython/Jupyter extension, and a typed
  Python SDK published to PyPI.

**Where we're honest about the gap:** pyvar.com is a product, not a
consulting practice, and we have no named enterprise deployments to cite
yet — so we're not applying for Services Track Select-tier status (10
certified individuals, 2 joint customers in production) today. What we do
have: one Anthropic-certified individual on the team (Filippo Buchicchio,
CCA-F), and a case study we believe is worth Anthropic's attention
regardless of tier — a full technical writeup and PRD are attached/linked
below.

**Attached / linked:**
- PRD: `docs/prd-claude-partner-hub.md` (this repo)
- Technical deep-dive (Medium article, publication pending):
  `docs/medium-building-pyvar-with-claude-code.md` (this repo)
- Live site: pyvar.com
- Repository: github.com/fibtecltd/pyvar

**What we're asking for:** we'd like pyvar.com considered as a public
case study for the Claude Partner Network / Partner Hub — as a
Claude-native product built end-to-end with Claude Code, not under the
Services Track's consulting-firm criteria. Concretely, we're hoping for:
(1) a listing or feature as a Claude-built product case study, and/or (2)
feedback on what a genuine Services Track application would need once we
have real joint-customer deployments to cite. Happy to walk through any
of the numbers above on a call — everything in the PRD is checkable
directly against the repository's own commit history, test suite, and
the live API.

Best regards,
Filippo Buchicchio
Fibtec Limited

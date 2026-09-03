# Draft: Partner Hub submission email / cover note

**Status:** Draft — not yet sent. Portal submission mechanism (whether this
goes through a "new Project" form field, an email, or both) not yet
confirmed — see note in the PR/commit this file ships with.

**Suggested subject:** pyvar.com — a Claude-native, regulatory-grade risk
platform (Fibtec Limited)

**Suggested recipient:** not yet confirmed — fill in once the portal's
actual submission path is known (a partner-team contact address, or this
text pasted into a portal "Project" description field).

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
yet — so we're not applying against Services Track Select-tier
eligibility (10 certified individuals, 2 joint customers in production)
today. What we do have: one Anthropic-certified individual on the team
(Filippo Buchicchio, CCA-F), and a case study we believe is worth
Anthropic's attention regardless of tier — a full technical writeup and
PRD are attached/linked below.

**Attached / linked:**
- PRD: `docs/prd-claude-partner-hub.md` (this repo)
- Technical deep-dive (Medium article, publication pending):
  `docs/medium-building-pyvar-with-claude-code.md` (this repo)
- Live site: pyvar.com
- Repository: github.com/fibtecltd/pyvar

Happy to walk through any of the numbers above — everything in the PRD is
checkable directly against the repository's own commit history, test
suite, and the live API.

Best regards,
Filippo Buchicchio
Fibtec Limited

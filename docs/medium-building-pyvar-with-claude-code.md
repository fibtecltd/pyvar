# We let Claude Code build a Basel-grade risk engine. Here's what broke, what it caught, and what shipped.

*A technical deep-dive into pyvar.com — an open-source VaR/ES/Greeks computation platform built, hardened, and shipped end-to-end with Claude Code.*

**Author:** Fibtec Limited
**Published:** docs/ companion to [`prd-claude-partner-hub.md`](./prd-claude-partner-hub.md)

> **A note on "verified facts only":** every number, function count, and bug
> description in this article is checkable against this repository —
> `git log`, `CHANGELOG.md`, `portal/functions.json`, or a real PyPI/API
> call. Where a claim was assumed rather than verified during drafting, we
> ran it against the actual code and corrected it before publishing. Two of
> those corrections are told as part of the story below, not edited out —
> because the honesty mechanism this article describes only means something
> if it also applies to the article itself.

---

## The problem this exists to solve

Regulatory-grade risk computation — Value-at-Risk, Expected Shortfall, Basel
backtesting, FRTB capital, Solvency II SCR, derivatives Greeks — is normally
locked inside proprietary vendor platforms: closed-source, expensive per
seat, and effectively unauditable by the risk teams whose regulatory capital
depends on them. If a bank's SCR formula has a bug, nobody outside the
vendor can see it, let alone fix it.

pyvar.com is the opposite bet: an Apache-2.0, open-source REST API exposing
**385 risk functions across 8 domains**, JIT-accelerated with Numba, served
through an async Celery/SQS pipeline on AWS. Every function's source is
readable. Every regulatory constant is a line of code you can grep for.

What makes it a story worth telling isn't the domain coverage on its own —
it's that the whole thing, from the first `CLAUDE.md` scaffold to the
security review that preceded its public launch, was built with Claude
Code. Not "Claude wrote some boilerplate." Claude Code wrote the Numba
kernels, found real regulatory bugs before they shipped, built the CI/CD
pipeline, and then built its own way back into the Claude ecosystem via an
MCP server and a Jupyter extension.

```
                    ┌────────────────────────────┐
                    │   385 risk functions        │
                    │   8 domains, Apache-2.0     │
                    └──────────────┬─────────────┘
                                   │
        ┌──────────────┬──────────┼──────────┬──────────────┐
        │              │          │          │              │
   Market Risk    Derivatives  Credit    Portfolio      Operational
     (71)            (62)      Risk(55)  Analytics(50)   Risk (44)
        │              │          │          │              │
        └──────────────┴────┬─────┴──────────┴──────────────┘
                             │
                  Liquidity(40)  ALM(33)  Regulatory(30)
```

---

## Illustration 1 — how a request actually flows

This is the real path, not a simplified one. Three client surfaces
(MCP, SDK, Jupyter) all converge on one `pyvar-client` SDK, so there's no
duplicated auth/retry logic to keep in sync across them:

```
  Claude Code / Claude.ai          Any Jupyter kernel            Any Python script
         │                                │                              │
         │ MCP tool call                  │ %pyvar / %%pyvar magic       │ import pyvar_client
         ▼                                ▼                              ▼
   ┌───────────┐                  ┌───────────────┐
   │ pyvar-mcp │                  │ pyvar-jupyter │
   └─────┬─────┘                  └───────┬───────┘
         │                                │
         └───────────────┬────────────────┴───────────────┐
                          ▼                                ▼
                  ┌───────────────┐                ┌───────────────┐
                  │ pyvar-client  │◄───────────────┤   pyvar CLI   │
                  │     SDK       │                └───────────────┘
                  └───────┬───────┘
                          │  HTTPS, Bearer JWT
                          ▼
                 ┌──────────────────┐
                 │  pyvar.com API   │  FastAPI
                 └────────┬─────────┘
                          │
             ┌────────────┴─────────────┐
             ▼                           ▼
     synchronous path            async path (VaR only)
     (384 of 385 functions)      Celery → SQS FIFO
             │                           │
             ▼                           ▼
     ┌───────────────────────────────────────┐
     │     Numba JIT engine (ECS Fargate      │
     │        + EC2 Spot workers)             │
     └────────────────┬────────────────────────┘
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
     Aurora Serverless v2   S3 (large-result
     (VaR job audit log)     offload)
```

Only `var.compute` goes through the async job queue — it's the one function
whose Monte Carlo path count makes submit-and-poll worth it. The other 384
are synchronous request/response, which is why `pyvar-jupyter`'s `%pyvar`
magic can just return a result inline without a polling loop of its own —
the SDK's `var.compute` already hides its own submit/poll cycle, and
everything else was never async to begin with.

---

## Bugs Claude Code found before anyone else could

The interesting part of "AI-built regulatory software" isn't that Claude
Code wrote the code — it's what happened when that code got checked against
real formulas. Four fixes from the `[0.1.0]` release notes, quoted exactly
from `CHANGELOG.md`:

- **Solvency II SCR credit-risk formula (Art. 200–201)** — corrected an
  error that understated required capital by roughly 79%. Not a rounding
  error — a structurally wrong formula that would have told an insurer it
  needed less capital than Solvency II actually requires.
- **rBergomi kernel** — the model was missing the fractional-Brownian
  autocovariance structure that gives rough volatility models their name.
  Without it, "rBergomi" was just Bergomi.
- **EMIR clearing obligation scope** — financial counterparties were being
  evaluated per-asset-class instead of being in scope across all asset
  classes, which is what the regulation actually requires.
- **IRRBB standard shocks** — recalibrated to the BCBS d578 (2024) shock
  values; the prior implementation was running stale pre-2024 numbers.

None of these were caught by a human skimming the code. They were caught by
building `tests/validation/` — a cross-validation suite checking pyvar's
outputs against QuantLib and published worked examples — and then actually
running it, repeatedly, against every domain, rather than trusting that
"it compiled and returned a plausible-looking number" meant it was correct.

A fifth example, smaller in scope but from the same discipline, closer to
this article's own publication date: PR #306 re-implemented 17 functions
flagged with numerical caveats, and one of those re-implementations
surfaced a real bug in the Monte Carlo CVaR optimizer's solver — again,
found by re-deriving and re-running the numbers, not by inspection alone.

---

## Illustration 2 — the honesty mechanism, in numbers

pyvar doesn't claim all 385 functions are equally battle-tested. 91 of them
carry a documented `caveat` field in the public function catalogue
(`portal/functions.json`) — a modeling simplification or an
independent-verification gap, disclosed to every API caller in the same
response payload the function itself returns data in:

```
  385 total functions
  ├── 294 (76.4%) — no caveat, fully cross-validated
  └──  91 (23.6%) — caveat disclosed inline, e.g.:
        "Approximation; no independently published reference
         verified for this exact parameterisation."
```

That 23.6% number is worth pausing on, because getting it required a real
correction mid-session: the first pass at counting caveats checked a
top-level `caveat` field on each function record and got 0% — which
immediately looked wrong against what we already knew about the catalogue.
The `caveat` field turns out to live nested under `formula.caveat`, not at
the top level of the record. Re-querying the correct path gave 91/385 =
23.6%. We're disclosing that correction here rather than quietly fixing the
number, because the whole point of this section is that a caveat rate is
only meaningful if you trust how it was computed — and this article holds
itself to the same standard it's describing.

---

## The Jupyter integration: three bugs a naive build would have shipped

`pyvar-jupyter` — `%pyvar`/`%%pyvar` IPython magics plus rich HTML display —
is the newest of the three client surfaces, and its build is a good
worked example of "verify by running it" as a discipline rather than a
slogan.

**Bug 1 — a silent method collision.** The first draft defined `pyvar` as
two separately-decorated methods on the same `Magics` subclass: one
`@line_magic`, one `@cell_magic`. Python class bodies don't allow two
methods with the same name to coexist — the second definition silently
overwrites the first in the class namespace. Cell-magic support would have
been dead code from the moment it was written, with no error anywhere to
signal it. Fixed by using IPython's `@line_cell_magic` decorator on a
single method that takes an optional `cell` parameter — the API IPython
actually provides for exactly this case.

**Bug 2 — a tokenizer that broke on its own inputs.** IPython's
`{expr}`-style variable expansion (`self.shell.var_expand`) interpolates a
Python expression's `str()` representation directly into the magic line.
For a list like `[0.01, -0.02]`, that representation contains a space after
the comma. A naive `shlex.split()` or whitespace `.split()` on the expanded
line chops that single value into two broken tokens. This wasn't caught by
reasoning about it — it was caught by writing a regression test using a
real `IPython.testing.globalipapp.get_ipython()` shell and watching it
fail, which is what justified building a proper bracket/quote-depth-aware
tokenizer (`tokenize_key_value_line`) instead of trusting a stdlib
one-liner.

**Bug 3 — a documented feature that doesn't exist.** An early draft of the
`02_basel_backtest.ipynb` example notebook stated that `%%pyvar` cell magic
supports `{{double-brace}}` interpolation of the cell body. It doesn't —
`_invoke()` only ever expands the magic *line*, never a cell's body, by
design (a cell body might contain code, not just parameter values, and
expanding it blindly would be unsafe). The claim was caught not by review
but by trying it: running the notebook's own assertion against the actual
implementation failed immediately, which is exactly the situation
"verified facts only" exists to catch before publication, not after.

While rebuilding that same notebook honestly, the synthetic backtest data —
seeded to force exactly 3 breaches — actually produced **6** breaches once
run through the real `traffic_light_backtesting` engine, because the random
baseline itself contributes a few breaches by chance over 250 trading days.
3 forced breaches would have meant "green zone." The real, verified
outcome is "yellow zone," and that's what the shipped notebook says —
because a notebook that asserts an assumed outcome instead of the outcome
you get from actually running the code isn't a very good advertisement for
"verify by running it."

---

## Illustration 3 — three integration surfaces, one SDK

```
                     ┌─────────────────────┐
                     │   pyvar-client SDK   │
                     │  (typed, generated,  │
                     │   retry/backoff,     │
                     │   PyPI-published)    │
                     └──────────┬───────────┘
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                   ▼
      ┌─────────────┐   ┌───────────────┐   ┌───────────────┐
      │  pyvar-mcp  │   │ pyvar-jupyter │   │   pyvar CLI    │
      │ Claude Code │   │  %pyvar magic │   │  `pyvar var    │
      │ tool plugin │   │  rich HTML    │   │   compute ...` │
      │ 385 tools + │   │  display      │   │  stdlib        │
      │ 2 generic   │   │               │   │  argparse only │
      └─────────────┘   └───────────────┘   └───────────────┘
```

None of these three duplicate HTTP or auth logic. That's a deliberate
constraint, not an accident: `pyvar-mcp`'s tool catalogue
(`plugins/mcp/pyvar_mcp/_generated/functions.py`) and the plugin manifest
(`.claude-plugin/marketplace.json`, `plugins/*`) are both generated
directly from the repo's own source of truth
(`.claude/skills/*`, `portal/functions.json`), with CI failing the build if
committed output ever drifts from what regenerating produces. The same
discipline that finds a formula bug — don't trust it, run it and check —
applies to code generation too.

`pyvar-mcp` also ships 13 Claude Code skills (8 domain skills, one per risk
domain, plus 5 covering pyvar's own architecture) — the difference between
a model knowing a function *exists* and knowing *when* a risk team would
actually reach for it.

---

## What actually shipped, checkable today

- **385 risk functions, 8 domains** — traceable to the live OpenAPI schema
  and `portal/functions.json`.
- **636 commits, 226 merged PRs**, of which **168 commits** carry a
  `Co-Authored-By: Claude` trailer.
- **`pyvar-client` on PyPI**, verified end-to-end — not just a green CI
  run, but a direct query against PyPI's own JSON API and a real
  `pip install` in a clean virtual environment.
- **A public-launch security review**, not a one-time scan: org-wide 2FA,
  GitHub Secret Protection + Code Security (CodeQL) enabled and confirmed
  running, a full-history `gitleaks` scan across every commit on every
  branch, branch protection requiring PR + 6 named status checks, GitHub
  Actions pinned to commit SHA, least-privilege `permissions:` blocks on
  every workflow.
- **`pyvar-mcp` submitted** to the `claude-plugins-community` marketplace —
  a real submission received by Anthropic's review team, decision pending
  as of publication.

---

## The part we're not going to overclaim

This article, like the PRD it accompanies, isn't a case study about named
enterprise customers running pyvar in production — there aren't any yet.
It's a case study about what an AI coding agent can do end-to-end on a
genuinely hard, regulatory-grade domain: find real Basel/Solvency
II/EMIR/IRRBB bugs before launch, build and harden the AWS deployment
pipeline around it, and then build its own way back into the ecosystem it
came from via MCP.

The next real chapter — the one this article can't write yet — is whether
someone outside Fibtec starts relying on `pyvar-mcp` inside their own
Claude Code sessions. If that happens, it'll be checkable the same way
everything above was: `git log`, PyPI, the live API, not a slide deck.

---

## Sources

- `CHANGELOG.md` (this repo) — regulatory fixes, PyPI publish history.
- `portal/functions.json` (this repo) — function/domain counts, caveat
  field structure.
- `pyvar-jupyter/` (this repo) — magics implementation, tests, example
  notebooks referenced above.
- `docs/prd-claude-partner-hub.md` (this repo) — the companion PRD this
  article was written alongside.
- `git log` (this repo) — commit, PR, and Claude-co-authorship counts,
  verified at time of writing.

# P11 — Pre-launch hardening: cost safety, distribution, discoverability

**Version:** 1.2
**Date:** August 2026
**Status:** Items 1, 2, 3, 4, 5 implemented. Items 6, 7 remain, both blocked
on external action (see §5, §6).
**Prepared by:** Fibtec Limited (drafted with Claude Code)

---

## 0. Why this exists

Before flipping `fibtecltd/pyvar` from private to public (the remaining P9 Day-0 gate),
seven items were raised that fall outside P9/P10's own scope: cost-safety
mechanisms, a new distribution channel, portal content, and two external-facing
moves (a sister-site redesign, an official marketplace listing). This document
sequences all seven, grounded in what actually already exists in
`pyvar-cdk/` and `api/` — none of this is designed from a blank slate.

| # | Item | Kind | Status this revision |
|---|------|------|----------------------|
| 1 | API throttling to prevent AWS overspend | Plan | **Implemented** (§1, PR #295) — aggregate WAF rate limit |
| 2 | Local-package build, manual-trigger pipeline + Slack | Implement | **Implemented** (§2, PR #296) |
| 3 | Emergency API kill switch | Implement | **Implemented** (§1, PR #295) |
| 4 | Iron-triangle chart into `index.html` | Implement | **Implemented** (§3, PR #294) |
| 5 | Formula + parameter frame for all 385 functions | Create | **Implemented** (§4, this revision) — full 385-function scope, no pilot |
| 6 | Redesign fibtec.co.uk, consistent with the pyvar portal | Delegate | **Blocked on the user** — repo doesn't exist yet (§5) |
| 7 | Submit pyvar's plugins to the official Claude Code marketplace | Submit | Real process found, content prepared (PR #293); submission itself needs a human/GitHub-authenticated action (§6) |

**Sequencing** (user's instruction: easiest → hardest, group into PRs to
minimize CodePipeline executions):

1. **PR A (docs only, zero pipeline executions)** — this document, the four
   proposal documents from the prior session (grant brief, monetization
   strategy, iron-triangle benchmark, local-package proposal) under
   `docs/proposals/`, the NLnet-adapted grant brief, and the marketplace
   submission content for item 7. `docs/` is already in the CodePipeline
   Git-trigger's exclude list (PR #284) — confirmed zero-execution docs-only
   pushes twice already (PRs #288, #289).
2. **PR B (portal only)** — item 4, the iron-triangle chart in `index.html`.
   One small, low-risk change.
3. **PR C (infra, `infra/*`)** — items 1 + 3 together: they are the same
   underlying problem (an unexpected cost spike) approached from two angles
   (an aggregate throttle, an emergency manual kill switch), touch adjacent
   files (`alerts_stack.py`, `edge_stack.py`), and the user's own framing
   already treats them as one topic. One infra PR, one `cdk diff`.
4. **PR D (infra, `infra/*`)** — item 2, the local-package build pipeline.
   Kept separate from PR C: different problem (distribution, not cost
   safety), different and larger blast radius (a new pipeline stage).
5. **Item 6** — blocked on the user creating the repository (§5). No PR from
   this session until that happens.
6. **Item 5** — the largest single body of work (385 functions, each
   requiring a formula sourced from its actual implementation, not recalled
   from memory). Deliberately last: both the hardest item and the one most
   sensitive to being rushed. Landed as one PR once sourcing is complete
   (§4), rather than eight per-domain PRs, per the same
   minimize-pipeline-executions instruction.
7. **Item 7** — submission content prepared in PR A; the actual form
   submission is a human action (§6), not a PR.

---

## 1. Items 1 + 3 — cost-explosion protection

### What already exists (read directly from `pyvar-cdk/`, not assumed)

- **`pyvar-cdk/stacks/alerts_stack.py`** already defines a $400/month
  `budgets.CfnBudget` (`MONTHLY_BUDGET_USD`), alerting at 80% actual and 100%
  forecast spend, publishing to a central `pyvar-{env}-alerts` SNS topic.
  CloudWatch alarms for API latency (p95 > 5s), API 5xx rate, worker errors,
  and SES suppressions already publish to the same topic. **No subscribers
  are wired by CDK** — email/Slack/PagerDuty are added manually post-deploy
  against the exported ARN (`AlertsTopicArn`), by design (the stack's own
  docstring: keeps no per-person address or PII in source control).
- **`api/middleware/rate_limit.py`** already enforces **per-user** daily
  caps (Redis-backed, `free`/`pro` tiers capped, `enterprise`/`internal`
  exempt) across one shared `"compute"` scope spanning all 386 endpoints.
  This protects against one user hammering the API. It does **not** protect
  against aggregate cost across many simultaneous users, which is the actual
  overspend scenario a viral spike or the new MCP server's agent traffic
  (flagged already in `docs/p10-skills-and-plugin-plan.md`'s open question
  #5) could create.
- **`pyvar-cdk/stacks/edge_stack.py`**'s WAF `CfnWebACL` (CloudFront scope,
  us-east-1) has `default_action=allow({})` and three rules: OWASP managed
  rules (priority 10), known-bad-inputs managed rules (priority 20), and a
  per-IP rate limit of 100 req/5min (priority 30, `RateLimitPerIp`). There is
  **no API Gateway** in this architecture — traffic flows
  CloudFront → WAF → ALB → ECS Fargate. (The user's own suggestion referenced
  API Gateway; the equivalent control point here is this WAF WebACL.)

### Design

**Item 1 — aggregate throttle (plan, implemented as a second WAF rule +
budget-alarm wiring, not a new subsystem):**

- Add a **global rate-based WAF rule** (priority 25, between the managed
  rule sets and the existing per-IP limit) capping aggregate requests across
  *all* clients over a rolling 5-minute window, sized well above expected
  peak legitimate traffic but low enough to bound worst-case Fargate/Spot
  scale-out cost. This is the piece the per-user Redis limiter structurally
  cannot provide (it has no cross-user view).
- Subscribe the existing `AlertsTopic` to email (`ops@fibtec.co.uk` — already
  pattern-matched in `pipeline_stack.py`'s `ops_topic`) and, once the
  one-time AWS Chatbot Slack authorization is done (§2 needs this same
  step), to the `#pyvar-prod-approvals`-style Slack channel — so a budget
  alarm actually reaches a human, not just an unmonitored SNS topic.
- Deliberately **not** proposing a fully-automatic cost-triggered shutdown:
  auto-disabling a live regulatory-compute API on a budget forecast crossing
  a threshold risks taking down a real institutional integration on a false
  or transient signal. The considered, safer design is alert-fast +
  one-command manual response (item 3) — a human stays in the loop for the
  actual "turn it off" decision, consistent with this project's existing
  pattern of failing safe/loud rather than acting automatically on
  best-effort signals (e.g. `tasks/var_task.py`'s metric emission, `storage/s3.py`'s
  offload fallback).

**Item 3 — emergency kill switch:**

- Add a fourth WAF rule, **priority 0** (evaluated first), disabled by
  default (`action=count`, not `block`) — a `block`-everything rule with no
  exceptions, matching the user's "zero whitelisting" intent adapted to the
  real WAF-based architecture rather than a nonexistent API Gateway resource
  policy.
- **Toggling is a direct `aws wafv2 update-web-acl` CLI call against the
  already-provisioned rule**, not a CDK redeploy — a `cdk deploy` cycle
  takes minutes, far too slow for "cost is exploding right now." A short,
  documented one-liner (wrapped in a small `scripts/toggle_kill_switch.sh`
  committed to the repo, taking `enable`/`disable`, calling
  `update-web-acl` with the rule's action flipped between `Block` and
  `Count`) is the actual emergency lever. CDK provisions the rule once;
  after that, the toggle never needs a redeploy.
- Re-enabling is the same script run in reverse — explicitly named
  "temporarily disable/re-enable" in the user's own request, so the script
  and its documentation treat both directions as equally first-class, not
  disable-only.

---

## 2. Item 2 — local-package build: manual-trigger pipeline + Slack (IMPLEMENTED as of this revision)

Builds and publishes the "pyvar Local" package specified in
`docs/proposals/pyvar-local-package-proposal.docx` (prior session). Recommended
primary artefact there was a Docker image with a pre-warmed Numba cache.

### Distribution channel — GitHub Releases, not a new S3/CloudFront origin

`tests/test_data_residency.py` enforces that customer/financial data stays in
`eu-west-1`, and `public_data_stack.py`'s own docstring records a prior
design mistake: an earlier revision put small public JSON files behind a
CloudFront→S3 origin in us-east-1 and that failed the residency suite's
check5/check6 (no S3 origin may exist in the us-east-1 EdgeStack). A
multi-hundred-MB local-package artifact is exactly the shape of thing that
temptation recurs for. Rather than re-litigate that boundary for a new
artifact type, **publish the built package as a GitHub Release asset** on
`fibtecltd/pyvar` instead:

- Sidesteps the residency question entirely — GitHub's infrastructure serves
  the bytes, not pyvar's AWS footprint.
- No new AWS storage/CDN cost for large binaries.
- Reuses a secret that already exists: `pipeline_stack.py`'s own docstring
  confirms a GitHub token is already in Secrets Manager for this pipeline.
- The idiomatic distribution channel for an open-source downloadable
  package generally, independent of the residency question.

### Pipeline design (as built — `pyvar-cdk/stacks/local_package_stack.py`)

- A genuinely **separate, new** CodePipeline (`pyvar-{env}-local-package`),
  not a stage bolted onto the existing one: `pipeline_stack.py`'s pipeline
  is built on the CDK Pipelines L2 construct (`pipelines.CodePipeline`),
  which is specifically opinionated toward self-mutating, trigger-on-push
  continuous deployment — the wrong tool for an artifact that should only
  ever build on demand. This stack instead uses the lower-level
  `aws_codepipeline.Pipeline` L2 construct directly, whose
  `CodeStarConnectionsSourceAction` exposes `trigger_on_push=False` — this
  disables the automatic webhook GitHub normally registers for a connected
  source, confirmed in the synthesized template (`DetectChanges: false`,
  zero `AWS::CodePipeline::Webhook` resources). The pipeline only starts via
  `aws codepipeline start-pipeline-execution` or the console's "Release
  change" button, matching the user's explicit "manual triggering process."
- Two CodeBuild stages: **BuildAndTest** (`docker build`, pre-warm the Numba
  cache the same way `ami_stack.py`'s warmup script does for the AMI —
  applied to a container image instead — then `tests/test_engine.py` runs
  inside the built image as a release gate; a failing test fails this
  stage and the pipeline never reaches Publish) and **Publish**
  (`docker save` → `scripts/publish_local_package_release.sh`, a dedicated
  script rather than inline pipeline logic, using the GitHub REST API
  directly via `curl`+`jq` — not the `gh` CLI, not guaranteed present on the
  CodeBuild image used here — to create/update a release and upload the
  image as an asset).
- **Notifications** reuse `pipeline_stack.py`'s existing
  `pyvar-pipeline-notifications` SNS topic, referenced by deterministic ARN
  (same avoid-a-cross-stack-cycle pattern `queue_stack.py` already uses for
  `alerts_stack.py`'s topic) — **not** `chatbot_role`
  (`ChatbotPipelineApprovalRole`): that role is scoped narrowly to
  `PutApprovalResult` on the main pipeline's own
  `Prod/ApproveProductionDeploy` action specifically (by design — see that
  role's own comment on why it's scoped that tight), not reusable for a
  plain informational notification, which needs no interactive-approval
  IAM at all. A `NotificationRule` on this pipeline's execution success/
  failure events, targeting that same topic, is sufficient — once the
  Slack workspace is authorized via AWS Chatbot (the same pending one-time
  console step, not a new one), this pipeline's notifications appear in the
  same channel automatically. The **one remaining manual step is unchanged
  and not duplicated**: AWS Chatbot's
  Slack workspace authorization is a one-time, console-only action (already
  documented as pending in `pipeline_stack.py`'s own comments) — this PR
  touches no IAM role for it and creates no second Chatbot integration.
- **`pyvar-local/`** — the actual thing this pipeline builds: a `Dockerfile`
  (ships `engine/` + `tests/test_engine.py` + a minimal CLI, `pyvar_local/cli.py`,
  that reflects over `engine/`'s own modules so it can never drift out of
  sync with what `engine/` actually contains) and a `README.md` explicitly
  scoping what's in this first release versus what's a deliberate fast-follow
  (a full local FastAPI server matching the hosted API's route surface —
  not built here). A new, path-scoped `pyvar-local-ci.yml` workflow builds
  and smoke-tests this Dockerfile in GitHub Actions on every relevant PR —
  the main `ci.yml`'s "Docker build check" job only ever builds the root
  `Dockerfile` (the hosted API image), so without this addition
  `pyvar-local/Dockerfile` would have had zero CI coverage until the
  manually-triggered AWS pipeline actually ran it.

---

## 3. Item 4 — iron-triangle chart in `index.html`

The chart drafted in the prior session (`docs/proposals/` benchmark document)
was a matplotlib PNG appropriate for a Word document. The portal has no
chart-library dependency today and its existing SVG usage (the logomark in
`pyvar.js`) is hand-authored inline SVG, not an image asset — so the chart is
redrawn as inline SVG (three-axis radar, ~40 lines, no new dependency),
placed in the existing "technology"/"api" section of `index.html` alongside
the tech-stack table, framed with the same directional/illustrative caveat
text used in the source document (never presented as an audited benchmark on
the public site either).

---

## 4. Item 5 — formula + parameter frame for all 385 functions

### Confirmed starting point (not assumed)

- No formula/equation data exists anywhere today: `engine/*.py` docstrings
  are prose + Google-style Args/Returns, occasionally a plain-English ratio
  (`liquidity_ratios.py`: `LCR = HQLA / net 30-day outflows`) but nothing
  resembling a full, checkable formula.
- `scripts/generate_function_catalog.py` (the generator behind
  `portal/functions.json`) has no `formula`/`equation` field in its schema
  today — confirmed by search, zero hits.
- The user has chosen the full 385-function scope over a pilot, given the
  accuracy stakes explicit acknowledgement.

### Sourcing discipline (IMPLEMENTED as of this revision)

Every formula was **derived from the function's real implementation code**,
never written from general financial-formula recall and assumed to match
this specific implementation's exact variant, sign convention, or regulatory
parameterisation — the same "verify, don't guess" discipline this project
has already applied repeatedly this session (the homepage async-claim fix,
the MCP SDK API claim, the WAF ScopeDownStatement production incident).
Actual process:

1. One research pass per domain (8 parallel agents), each reading every
   assigned function's actual `@njit` kernel or wrapper body — never just
   the docstring — plus any regulatory citation already present in the code,
   producing a structured record: a LaTeX-renderable `formula_latex`, a
   `symbol_map` from each symbol to its actual parameter name (cross-checked
   programmatically against that function's own `params` list — zero
   mismatches across all 385), the regulatory/academic `citation` verbatim
   if and only if one already exists in the code (never invented), and a
   `caveat` field as the honesty escape hatch for genuine uncertainty —
   never a silently-guessed formula presented as settled.
2. Each domain agent ran its own adversarial re-verification pass against
   the source before reporting done (5–17 functions re-checked per domain,
   every domain). This caught two real, since-fixed bugs in the agents' own
   first drafts, not just confirmed them clean: credit-risk's
   `probability_of_default_pd_estimation` was missing the code's `min(...,
   1.0)` pooled-PD cap; derivatives' `barrier_option_pricer` included a
   rebate-related λ term the code computes but never actually uses (a dead
   variable — removed from the formula, flagged instead).
3. Landed as one PR across all 8 domains (not eight incremental PRs), per
   the pipeline-execution minimisation instruction — see §7 below for the
   PR reference.
4. This session's own independent verification, on top of each agent's
   self-check: cross-referenced the domain→module mapping the agents used
   against a live reflection over `engine/`'s actual public functions
   (`pkgutil.iter_modules` + `inspect.getmembers`, the exact same mechanism
   `pyvar_local/cli.py` already uses) — confirmed all 385
   `portal/functions.json` entries resolve to a real engine function with no
   gaps; then re-read 5 functions spread across 5 different domains
   (`sharpe_ratio`, `duration_gap_analysis`, `liquidity_coverage_ratio_lcr`,
   `probability_of_default_pd_estimation`, and `kupiec_pof_test`'s docstring)
   directly against source, independently of the agents' own reports —
   all matched exactly, including confirming the `probability_of_default_pd_estimation`
   fix above was real.

Final coverage: 385/385 functions have a formula record (zero missing —
`scripts/generate_function_catalog.py`'s new missing-formula warning, mirrored
on the existing `unresolved_engine_alias` check, fired zero times). 62 carry
a citation, 99 (~26%) carry a caveat — a healthy, credible ratio: neither
suspiciously zero (which would suggest rubber-stamping) nor overwhelming.

### Rendering (IMPLEMENTED as of this revision)

- New `formula` field (an object: `formula_latex`, `symbol_map`, `citation`,
  `caveat`) merged into `portal/functions.json` by
  `scripts/generate_function_catalog.py`, sourced from a new, separate,
  hand-reviewed file — `scripts/data/function_formulas.json` — rather than
  derived from the OpenAPI schema/docstrings the way every other field is
  (no formula data exists anywhere in the docstrings themselves, see above).
  Keeping it in its own file means regenerating `functions.json` for an
  unrelated reason (a new function, a changed parameter) merges the existing
  formulas back in automatically instead of wiping them.
- Rendered via KaTeX 0.16.11 (MIT), vendored at `portal/vendor/katex/` —
  same self-hosted convention as `vendor/fuse.min.js`, not a CDN — lazy-
  loaded only when a Try-it panel for a function that actually has a formula
  is opened (`portal/pyvar.js`'s `_ensureKatex`/`_renderFormula`, mirroring
  how `_ensureSearchIndex` already lazy-loads Fuse.js). Shows the rendered
  expression, a symbol-to-parameter legend, the citation if present, and a
  visible caveat if the sourcing pass flagged one — additive to the existing
  params-form/result view inside the same panel, not a redesign of it.
  Verified end-to-end in headless Chromium across 5 real functions spanning
  5 different domains before committing, not just assumed from reading the
  code.

---

## 5. Item 6 — fibtec.co.uk redesign (blocked on the user)

This session's GitHub access is scoped to exactly three repositories
(`fibtecltd/claude-docker`, `fibtecltd/pyvar`, `fibtecltd/.github`) — no
`fibtec.co.uk` repository exists yet and this session cannot create one or
grant itself access to one.

**Agreed next steps (user's own words):**

1. The user creates the new repository.
2. The user adds whatever existing fibtec.co.uk content/assets already
   exist.
3. The user grants this session's GitHub tooling access to that repository.
4. From there, proceed step by step together.

No further action from this session until step 3. When it happens, "consistent
with the pyvar portal" should concretely mean: the same warm/clay palette
(`portal/pyvar.css`'s CSS variables), the same typography pairing (Space
Grotesk + JetBrains Mono), and the same shared-component pattern
(`buildNav`/`buildFooter`-equivalent) — not a literal copy of pyvar's
domain-specific page structure, since fibtec.co.uk's own content (consulting/
enterprise services, not risk functions) is a different site.

---

## 6. Item 7 — official Claude Code marketplace submission

Researched directly rather than assumed: Anthropic maintains an official,
curated plugin marketplace (`anthropics/claude-plugins-official`), distinct
from the fully decentralized `/plugin marketplace add <any-repo>` mechanism
pyvar already uses. Third-party plugins are submitted via a form
(`clau.de/plugin-directory-submission`) and go through a quality/security
review before appearing under `/external_plugins`.

This session prepares the submission content (what the form will ask for —
plugin descriptions, security/trust disclosure, links) as part of PR A. The
actual form submission is very likely gated behind an authenticated action
tied to the submitter's identity/repo ownership, which this session cannot
perform on the user's behalf — the user (or their separately-delegated
agent) completes the form itself using the prepared content and the link
above.

---

## 7. Open items carried forward

1. The exact aggregate WAF rate-limit threshold (§1) needs a real traffic
   baseline to size sensibly — proposed as a conservative placeholder in the
   implementation PR, with a note to revisit after a few weeks of real
   public traffic post-launch.
2. NLnet's own fund lineup is mid-restructuring as of this document (see the
   adapted grant brief's own caveat) — the grant brief should be re-checked
   against the live nlnet.nl/propose page immediately before actual
   submission, not assumed still accurate from this research pass.
3. ~~Item 5's KaTeX rendering choice and exact "Formula" tab UX~~ **Resolved
   by shipping it**: rendered inline in the existing Try-it panel (not a
   separate tab — simpler, and the panel was never crowded enough to need
   one), verified end-to-end in headless Chromium across 5 real functions.
   Worth an actual look at pyvar.com once live, and worth deciding whether
   `caveat` should stay visible to every visitor long-term or move to a
   collapsed/expandable state if the ~26% caveat rate reads as noisy at
   scale — a product-polish call, not a correctness one.
4. Item 5's 99 caveats (~26% of functions) are themselves a punch list: each
   one names a specific place where pyvar's implementation is a
   simplification, a bespoke convention, or diverges from the textbook/
   regulatory-standard method (e.g. Solvency II SCR credit risk's missing
   inter-counterparty correlation term, several IRRBB/LCR internal-convention
   flags). Not a defect in this exercise — surfacing them accurately was the
   point — but worth its own triage pass: some are genuine engine
   limitations worth fixing in `engine/` itself, filed separately from this
   portal-content effort.

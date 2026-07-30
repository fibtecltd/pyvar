# P8 — Portal Finalisation
# Used by: scripts/claude/run.sh p8 --mode seq
# Machine: M4, sequential mode (DNS/SSL tasks are order-dependent; other
# tasks are largely independent but kept sequential for review discipline)
# Prerequisite: P7 complete, master clean

This task list has already been reviewed and approved by the operator.
Proceed autonomously through routine work — reading files, writing code,
editing HTML/CSS/JS, running local tests — without asking for confirmation
on each step.

Confirm with the operator before: any DNS record change (Route53 or
Aruba), ACM certificate issuance/validation, forcing/terminating EC2
instances, changing IAM policy or grants in any *_stack.py, running
cdk deploy, or pushing/merging branches.

The answers to routine "how should I proceed" questions are already
provided below.

---

## Sequencing note (Option 2)

A separate visual-refinement pass for the portal (orange/green/black/white
palette, component polish) was drafted as a Claude Design brief but has
not necessarily been run yet as of this session. Do NOT block any task
below on that refinement landing first — implement against the current
live portal/*.html and portal/pyvar.css as they exist today. If/when the
refined visual design becomes available, it gets swapped in as a follow-up
styling pass, not a prerequisite for the functional work in this prompt.

---

## Architecture clarification — read before Tasks 4 and 5

There are 8 domain-*.html pages (one per domain) and no plan to create
382 individual static HTML pages, one per function. Function-level
content (name, description, parameter form, search index entry) is
data-driven: a single JSON/JS data source describing all 382 functions
(generate this once from schemas/*.py or the OpenAPI spec — check which
is more complete/accurate as the source of truth) feeds:
- The search index (Task 4) — client-side search over this data,
  results link to {domain page}#{function-anchor} or open a modal/
  panel within the domain page, not a separate page per function.
- The "Try it" panel (Task 5) — one reusable panel template per domain
  page, populated dynamically from the same function data when a user
  selects a specific function within that domain's page.

If you find yourself about to generate a new .html file per function,
stop — that's the wrong architecture. The 8 existing domain pages are
the full set of page-level HTML needed; everything below that level is
JS-rendered from a shared data source.

---

## Environment facts

- Portal files: portal/index.html, portal/pyvar.css, portal/pyvar.js,
  8 domain-*.html pages, plus older reference files
  (pyvar_portal.html, pyvar_architecture.html, pyvar_market_risk.html —
  do not edit these three, they are historical mockups only)
- Live API: https://d1mqqddh8gu2qi.cloudfront.net (dev — pyvar.com DNS
  not yet wired, see Task 7)
- 388 routes across 8 domains, JWT auth (free/pro/enterprise tiers)
- api_usage table live (P6) — duration_ms, status, domain, function_name,
  tier, created_at columns available for real usage data
- pyvar/JobCount, pyvar/JobErrors CloudWatch metrics live (P6/P7)
- ElastiCache result caching live and verified (P7) — cache hits return
  task_id: "cached" with the result inline, cache misses return normal
  202 + polling flow
- Known tracked gaps (do not attempt to fix in P8 — out of scope):
  #118 var_jobs audit log never written (compliance)
  #119 no CI/CD deploy pipeline (infrastructure) — remember this means
       any front-end/API change here will need the same manual
       build-push-api.sh + operator confirmation cycle used throughout
       P6/P7 to actually go live, not just merge to master
  #130 write_result_to_s3() dead code
  #134 4xx error rate spike, needs triage

---

## P8 scope — work through in this order, stop after each task and await
## confirmation before proceeding to the next.

---

### Task 1 — Wire homepage terminal demo to the real API

The homepage terminal widget currently shows a mocked/scripted demo.
Replace it with a real call to POST /api/v1/var/compute using a
public-safe demo payload (small n_simulations, no auth required — check
whether a demo/sandbox tier exists or needs creating; if it doesn't
exist, propose the smallest viable option: either a rate-limited
unauthenticated demo endpoint, or a pre-computed cached example refreshed
periodically — report the tradeoff rather than picking unilaterally for
a public-facing, unauthenticated surface).

Poll for the result and animate it into the terminal display, matching
the existing terminal widget's visual style (portal/pyvar.css).

Branch: feat/p8-live-terminal-demo

---

### Task 2 — Live status indicator

Build a small status pipeline: CloudWatch alarm states (reuse the
alarms from P6 — pyvar-dev-alerts topic conditions) → a Lambda that
polls alarm states → writes a small /status.json to the S3 result
bucket (or a dedicated small public bucket — check whether the existing
result bucket is appropriate to serve public status from, given it's
also used for computation results; propose a separate minimal bucket
if mixing concerns is a bad idea) → portal fetches /status.json on load
and renders a simple "All systems operational" / "Degraded" / "Down"
indicator.

This is a new small piece of infrastructure (Lambda + possibly a new
S3 bucket) — write the CDK for it but do NOT deploy without confirmation
per the standing rule.

Branch: feat/p8-status-indicator

---

### Task 3 — API key registration flow

Email → verification → JWT issued → shown in a simple dashboard page.

Check what exists already: api/middleware/auth.py has create_access_token()
but confirm whether any registration/verification endpoint exists at all
(likely does not — report what's missing before building). Minimum viable
version:
1. POST /api/v1/auth/register — email only, sends a verification link
   (check what email-sending capability exists — SES? Nothing configured
   yet? Report before assuming)
2. GET /api/v1/auth/verify?token=... — confirms email, issues a JWT
   (free tier), stores minimal user record (reuse the `users` table from
   the 0002 migration if the schema fits — check its columns first)
3. A simple portal page showing the issued JWT once verified

Do not build a full account management system — this is the minimum
flow to get a working API key into a new user's hands. Flag anything
that needs a larger follow-up (password reset, key rotation, etc.) as
a tracked issue rather than building it now.

Branch: feat/p8-api-key-flow

---

### Task 4 — Fuse.js search across all functions

Client-side search over all documented functions (see Architecture
clarification above — this is one JSON/JS data source covering all 382
functions, not 382 pages). Check pyvar_functions.csv or wherever the
canonical function list/descriptions live — api/routes/ docstrings,
OpenAPI schema, or a dedicated content file; use whichever is the actual
source of truth, report if it needs to be generated fresh.

Target <50ms client-side per the original spec. Search UI: a dropdown/
overlay triggered from the nav search box, results grouped or colour-coded
by domain (see domain colour coding already specified in the earlier
Claude Design brief — Market Risk green, Credit Risk amber, etc. — reuse
those colours even if the full visual refinement hasn't landed yet).

Branch: feat/p8-fuse-search

---

### Task 5 — "Try it" panel on each domain page

One reusable panel template per domain page (see Architecture
clarification above — do not create per-function HTML). Parameter form
fields vary per function (check schemas/*.py for the actual Pydantic
models to derive form fields from, generating the form dynamically from
the same function data source built in Task 4) → API call → poll →
result display, matching the existing domain page layout.

Requires a valid JWT (from Task 3's flow, or an existing test token for
development). If Task 3 isn't complete yet when this task starts, use a
placeholder "Sign in to try this" state rather than blocking — note this
dependency and revisit once Task 3 lands.

Branch: feat/p8-try-it-panels

---

### Task 6 — Iron Triangle integration (data layer)

This depends on a separate design deliverable — the Iron Triangle
component specification (see iron-triangle-design-prompt.md, run
separately in Claude Design or Claude Fable). Do NOT attempt to design
the visual component yourself; this task is about the DATA that will
feed it once the component spec exists.

Investigate and report — do not fabricate — what real data sources exist
for each of the three Iron Triangle axes in a pyvar context:

1. **Time** — real, already available: duration_ms in the api_usage
   table (P6), or pyvar/JobCount timing if that's more current. Confirm
   which source is more accurate/complete and use it.

2. **Cost** — NOT currently tracked per-job. Investigate whether a
   reasonable per-job cost estimate can be derived (e.g. worker
   instance-hour cost from Cost Explorer data (P7) divided by jobs
   processed in a given period, as an average rather than exact
   per-job attribution) or whether this needs to be flagged as "not
   yet measurable at the per-job level, only at the aggregate monthly
   level" — report which is honestly achievable, do not invent a
   precise-looking number from a rough estimate.

3. **Accuracy** — NOT a live per-request metric (production requests
   have no ground-truth answer to compare against). The only real
   accuracy evidence that exists is the P5a cross-validation work
   (389 functions validated against external references, tolerances
   documented). Propose representing "Accuracy" as a static or
   slowly-updated confidence score derived from P5a's validation
   results (e.g. percentage of functions within tolerance, or a
   simpler "all functions independently validated against regulatory
   references" badge-level indicator) rather than pretending it's a
   live per-request measurement. Report this framing rather than
   fabricating a live accuracy percentage.

Once the actual availability/limitations of each axis are confirmed,
write a small data-contract document (docs/p8-iron-triangle-data.md)
describing exactly what values are real, what's an aggregate/estimate,
and what's a static validation-derived score — this becomes the
integration spec once the visual component exists.

Do NOT build the visual component in this task — that comes after the
separate design output is available, as a follow-up task once you have
it to reference.

Branch: docs/p8-iron-triangle-data

---

### Task 7 — pyvar.com DNS + SSL — CLOSED 2026-07-30

Aruba's stale forwarding redirect (pyvar.com → example.com) and the
expired TLS cert on their forwarding proxy (62.149.189.55) — both
blocking issues unrelated to this task's own steps — were fixed by
Aruba support and independently verified end to end (301 → 
www.pyvar.com, valid cert through 2027-02-14, no masking, no
regression on www.pyvar.com). See docs/p8-task7-dns-ssl-verification.md.

The ACM cert + CloudFront alternate-domain-name change below (steps 2-3)
was drafted on `feat/p8-domain-dns-ssl` but never deployed, and is not
required for pyvar.com to work correctly now that the Aruba-side fix
is live — left as an operator decision on whether to still pursue it.

**High-risk task — confirm with operator before EVERY step, not just
once at the start.**

1. Confirm DNS is currently hosted at Aruba (per prior P4/P6 sessions —
   DNSSEC was activated there). Determine whether pyvar.com should move
   to Route53 (per the original release plan) or stay at Aruba with a
   CNAME/ALIAS pointing at CloudFront — report the tradeoff, do not
   assume the release plan's original Route53 assumption still holds
   given DNSSEC is already live at Aruba and moving registrars/DNS
   hosts is disruptive.
2. Request/validate an ACM certificate in us-east-1 for pyvar.com +
   www.pyvar.com (same DNS-validation pattern used for the ALB
   certificate in P6 — CNAME records, confirm with operator before
   adding them to whichever DNS host is chosen).
3. Wire the certificate into the existing CloudFront distribution
   (edge_stack.py) as an alternate domain name.
4. Do NOT change the primary working CloudFront dev URL
   (d1mqqddh8gu2qi.cloudfront.net) — pyvar.com becomes an additional
   alias, not a replacement, until this is fully verified working.

Branch: feat/p8-domain-dns-ssl

---

### Task 8 — SEO + Accessibility

1. Meta descriptions, Open Graph tags, SoftwareApplication JSON-LD
   schema on index.html and domain pages.
2. WCAG 2.1 AA pass: check colour contrast ratios (especially once/if
   the visual refinement lands — the amber/orange accent needs contrast
   checking against the dark background), alt text on any icons/images,
   keyboard navigation through the "Try it" panels and search, ARIA
   labels where needed.

Run an automated accessibility check (axe-core or similar, check what's
available) and report findings before fixing — some findings may need
design input rather than a pure code fix.

Branch: fix/p8-seo-accessibility

---

## P8 exit gate

- [ ] Terminal demo makes real API calls
- [ ] Status indicator live and accurate
- [ ] API key registration flow works end-to-end (register → verify →
      JWT issued)
- [ ] Search returns results in <50ms for a representative query set
- [ ] "Try it" panels functional on all 8 domain pages
- [ ] Iron Triangle data contract documented (visual component itself
      is a follow-up, not part of this exit gate — depends on separate
      design output)
- [x] pyvar.com resolves via HTTPS with valid certificate — Task 7
      closed 2026-07-30, see docs/p8-task7-dns-ssl-verification.md
- [ ] Automated accessibility check run, findings documented
- [ ] No regression on existing 388 API routes / auth gating

## Post-task validator

After all P8 tasks complete and any changes are deployed (remember:
merging to master does not deploy — #119 gap — the operator will need
to run build-push-api.sh and confirm the ECS redeploy, same pattern as
P6/P7):

1. Run scripts/adversarial/p4_post_deploy_validator.md
2. Append to P4_ADVERSARIAL_POST_DEPLOY.md:
   "## P8 Portal Finalisation — full stack pass"
   Do NOT modify any existing sections.

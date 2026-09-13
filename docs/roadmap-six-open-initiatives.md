# Six open initiatives — roadmap and complexity ranking

**Status:** Living planning document. Created 2026-09-10 at Filippo's request
to sequence six previously-identified, still-open workstreams. Each item
gets its own full plan document as it's picked up, linked below as they're
written — this file stays the single index and complexity rationale, not a
duplicate of the detail.

**Ordering principle (Filippo's instruction):** pick up points in inverse
order of complexity — easiest first — so early wins land fast and the
hardest, most decision-gated item (market data adapters) is tackled last,
once everything upstream of it is settled.

## Important cross-cutting finding before any of these ship

Multiple pre-existing proposal documents under `docs/proposals/*.docx`
(written in a prior session, before this session's public-launch and
marketplace-submission work) still say **"Licence MIT"** — the same mistake
already caught and fixed in `scripts/generate_plugins.py`,
`plugins/mcp/pyproject.toml`, the portal footer, and the already-corrected
`docs/proposals/marketplace-submission-content.md`. **Fixed this session in
`pyvar-grant-brief-nlnet.docx`** (item 4 below) — licence, repo-visibility
wording, and prepared-date all corrected, plus the fund name resolved to
Restack. **Fixed this session in `pyvar-monetization-strategy.docx`** (item
5 below) — same licence + date corrections. **Still present in
`pyvar-local-package-proposal.docx`** (item 2 — "pyvar's compute engine is,
and will remain, MIT-licensed... once the repository goes public", also
stale on the repo-visibility point since the repo has been public for
weeks) — not yet fixed. Not yet checked in `pyvar-grant-brief.docx` — check
before it's used externally. pyvar's real license, everywhere in the
actual codebase, is **Apache-2.0**. This is a "fix before you
submit/publish/reference externally" issue on every one of these `.docx`
files, not just the NLnet one — though note the *built*
`pyvar-local/README.md` (the actual shipped artifact, distinct from the
`.docx` proposal that inspired it) already correctly says Apache-2.0, so
this is a docs-only staleness issue, not a product-correctness one.

## The six items, ranked

| # | Item | Complexity | Why this rank | Plan doc |
|---|---|---|---|---|
| 1 | Anthropic plugin marketplace: status review + submit remaining plugins | Easiest | Investigation + submission actions only; no new engineering; submission *content* is already 95% prepared in `docs/proposals/marketplace-submission-content.md`. Executed this session: fixed a stale "382 functions" figure in the live `.claude-plugin/marketplace.json`, resolved the market-risk 68-vs-71 coverage gap this session's own reconciliation doc had left open, and drafted all 13+1 per-plugin submission blocks ahead of need. Actually checking/submitting via the authenticated form is still Filippo-only | `docs/plan-plugin-marketplace-status-and-submission.md` (this session) |
| 2 | One-off `pyvar-local` package generation and sharing | Low | Confirmed: the package (`pyvar-local/`) and its CDK publish pipeline (`pyvar-cdk/stacks/local_package_stack.py`) already exist and work as designed — this is "trigger it and verify the release asset" (needs real AWS credentials this session doesn't have), not new build work. Full commercial licensing mechanism explicitly deferred to item 5 | `docs/plan-pyvar-local-package-generation.md` (this session) |
| 3 | New posts/articles about pyvar | Moderate | Found real, fresh material since the last article: a subtle production bug (TokenReportStack + migration image-pinning), a cost-transparency correction ($900-1,000/mo real vs. a stale £126 target), and a Partner Network Customer-Story-declined-then-resubmitted-as-Public-Case-Study story. **Drafted this session, folded into PR #333**: full Medium draft + LinkedIn adaptation, one combined post per the recommendation, every number re-verified against the repo at drafting time (7 merged PRs since the first article, not the plan doc's original "eleven" — see the draft's own count). Still needs Filippo: confirm the angle, then actually publish | `docs/plan-new-articles-and-posts.md`, `docs/publications/pyvar-post-launch-lessons-medium-article.md` |
| 4 | NLnet submission preparation | Moderate-high | Resolved via WebSearch: NLnet's restructuring settled into "Open Internet Stack" with a live call now open, deadline 2026-11-03. **Restack** (not CodeSupply) is the right-fit fund — explicitly covers "security proofs and audits," matches the brief's own framing. Bigger finding: the real submission is a short 6-question web form, not the existing 5-page `.docx` — that document is source material, not the deliverable. **Executed this session, folded into PR #333**: fixed the `.docx`'s licence/repo-visibility/fund-name staleness, drafted condensed answers to the 3 of 6 form questions this session could confirm. Still needs Filippo: confirm the remaining 3 question texts against the live form, then submit before 2026-11-03 | `docs/plan-nlnet-submission.md`, `docs/proposals/nlnet-restack-form-answers.md` |
| 5 | Monetization strategy implementation for pro/enterprise tiers | High | **Phase A shipped AND live-deployed successfully.** Stripe Checkout + webhook (`api/routes/billing.py`), confirmed decisions (Stripe/Phase-A-only/monthly-only/no-trial/manual-Enterprise), 14 new tests + full suite re-run clean. Closed a JWT-staleness gap the original plan didn't anticipate. Wiring the 3 Stripe secrets into `pyvar-dev-api` took 4 PRs to get right (#337→#341): the first 3 attempts (execution-role grant, a CFN dependency fix, a fixed 75s sleep) all tried to make IAM propagation finish fast enough to satisfy the ECS deployment circuit breaker; CloudTrail evidence proved propagation took >8 minutes, far outside any fixed budget. #341's actual fix reframed the problem — these secrets never belonged on the ECS-launch-critical `execution_role` at all (`_require_billing_configured()` already 503s gracefully when unset), so they're now granted to `task_role` and fetched in-app at startup, mirroring the existing `SENTRY_DSN` pattern (PR #229) exactly. Confirmed via live `cdk diff`: zero IAM changes to `ApiExecutionRole`, zero Lambda/Trigger machinery left in the stack. **Follow-on scope opened, not yet built:** metering/usage/payment-lifecycle event handling (declined-payment and limit-exceeded scenarios, user notification, durable audit trail) — real open product decisions flagged in the plan doc §8, not yet answered | `docs/plan-monetization-implementation.md` (this session) |
| 6 | Market data adapter infrastructure (Refinitiv first) | Hardest | Largest engineering effort (5 phases, MD-1 through MD-5, per the attached plan), touches a genuine compliance boundary (vendor data redistribution restrictions), and has open questions in the plan itself that only Filippo can answer before MD-3 can start (RDP access tier, snapshot vs. streaming, cache TTL legal check, ISIN→RIC persistence). Verified MD-1 (interface/schemas/exceptions/fake provider/unit tests) has zero external blockers and is buildable now — a scope decision (this session vs. a delegated agent) is still open | `docs/plan-market-data-adapter.md` (this session) |

## What "properly planned and fully documented" means per item

For each item, before any code/content ships:
1. Read whatever prior planning artifact already exists for it in full
   (not just skim) — several of these already have a `.docx` proposal from
   an earlier session; the job is often refresh-and-execute, not
   create-from-scratch.
2. Verify every factual claim in that artifact against the current repo
   state (license, repo visibility, dates, version numbers) — the MIT/Apache
   finding above shows why this matters.
3. Write (or update) a dedicated plan doc under `docs/` covering: current
   state, gaps, concrete next actions, and — critically — which actions only
   Filippo can take (external submissions, business/legal decisions,
   anything needing live AWS or an authenticated third-party account this
   session can't reach).
4. Execute what's actually executable from this session; hand back a clear,
   short list of what's left for Filippo.

## Next step

All six items now have full plan docs (this PR). None of the six items'
open decisions have been answered yet — each plan doc's own section
lists exactly what's blocked on Filippo (external submissions, business/
legal/pricing decisions, or — for item 6 specifically — a scope call on
whether MD-1 gets built in this session or handed to a delegated agent).
Next action per item is unblocking those decisions, not more planning.

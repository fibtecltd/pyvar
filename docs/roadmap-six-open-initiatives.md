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
| 1 | Anthropic plugin marketplace: status review + submit remaining plugins | Easiest | Investigation + submission actions only; no new engineering; submission *content* is already 95% prepared in `docs/proposals/marketplace-submission-content.md`. Executed this session: fixed a stale "382 functions" figure in the live `.claude-plugin/marketplace.json`, resolved the market-risk 68-vs-71 coverage gap this session's own reconciliation doc had left open, and drafted all 13+1 per-plugin submission blocks ahead of need. **Confirmed by Filippo (2026-09-14)**: submissions are per-plugin, not bundle-level — `pyvar-mcp` is already submitted and its Anthropic decision is still pending (not resubmittable while pending); the other 12 skill plugins are deliberately being held until that lands, then submitted one at a time using the already-drafted content. Not Smithery — that's a separate, unrelated registry submission. **Status re-checked (2026-09-24)**: cloned the real `anthropics/claude-plugins-community` mirror directly and parsed its live 2,282-plugin approved list — zero matches for "pyvar"/"fibtec", confirming still not approved (can't distinguish "under review" from "rejected" from outside the list). Smithery inconclusive — the domain is blocked in this session's sandbox; no listing found via web search either | `docs/plan-plugin-marketplace-status-and-submission.md` §2b (this session) |
| 2 | One-off `pyvar-local` package generation and sharing | Low | **Shipped.** Confirmed via the GitHub API that the pipeline already ran successfully: release `pyvar-local-v0-6682472c` (2026-09-12), one `pyvar-local.tar.gz` asset (555 MB). Added `portal/local.html` — a dedicated portal page with a direct download button, usage docs (`docker load`/`run`/test-suite), and an explicit in-scope/not-yet-in-scope section — plus nav and footer links (`portal/pyvar.js`) so it's discoverable from every page. Verified with Playwright against a local run (no new console errors vs. the existing `plugins.html` baseline). Full commercial licensing mechanism explicitly deferred to item 5 | `docs/plan-pyvar-local-package-generation.md` (this session) |
| 3 | New posts/articles about pyvar | Moderate | Found real, fresh material since the last article: a subtle production bug (TokenReportStack + migration image-pinning), a cost-transparency correction ($900-1,000/mo real vs. a stale £126 target), and a Partner Network Customer Story saga now with a **final outcome (2026-09-15)**: declined again on resubmission, on the one criterion (named third-party customer) reframing couldn't fix — 2 of the original 3 decline reasons did close. **Drafted this session, folded into PR #333, updated with the final outcome this session**: full Medium draft + LinkedIn adaptation, one combined post per the recommendation, every number re-verified against the repo at drafting time (7 merged PRs since the first article, not the plan doc's original "eleven" — see the draft's own count). Still needs Filippo: confirm the angle, then actually publish | `docs/plan-new-articles-and-posts.md`, `docs/publications/pyvar-post-launch-lessons-medium-article.md`, `docs/partner-hub-public-case-study-resubmission-email.md` |
| 4 | NLnet submission preparation | Moderate-high | Resolved via WebSearch: NLnet's restructuring settled into "Open Internet Stack" with a live call now open, deadline 2026-11-03. **Restack** (not CodeSupply) is the right-fit fund — explicitly covers "security proofs and audits." **2026-09-17, materially updated**: Filippo supplied the real `propose/` form and GenAI policy pages (both previously blocked to browsing). Two corrections: (1) the real form is a structured field set (title/abstract/budget/comparison/etc., each with its own character limit), not a "6 short questions" shape — the answers doc is rewritten against the real fields. (2) NLnet's GenAI policy is a disclosure-and-accountability regime, not a tooling ban — substantively compatible with how pyvar was built — but the application's own AI-disclosure field is real and required (Yes + a prompt-provenance log), `README.md` doesn't yet carry the development-process GenAI disclosure the policy actually asks for, and there's a genuine reputational judgment call (not a fact question) on how hard to lead with AI-authorship framing given the propose page's blunt "not interested in AI-generated projects" line sitting next to pyvar's own AI-forward public narrative. Still needs Filippo: the framing call, a specific `amount` figure, entity-type choice, and his own words for the experience/background field — none of these are things to draft speculatively on his behalf | `docs/plan-nlnet-submission.md`, `docs/proposals/nlnet-restack-form-answers.md` |
| 5 | Monetization strategy implementation for pro/enterprise tiers | High | **Phase A shipped AND live-deployed successfully.** Stripe Checkout + webhook (`api/routes/billing.py`), confirmed decisions (Stripe/Phase-A-only/monthly-only/no-trial/manual-Enterprise), 14 new tests + full suite re-run clean. Closed a JWT-staleness gap the original plan didn't anticipate. Wiring the 3 Stripe secrets into `pyvar-dev-api` took 4 PRs to get right (#337→#341): the first 3 attempts (execution-role grant, a CFN dependency fix, a fixed 75s sleep) all tried to make IAM propagation finish fast enough to satisfy the ECS deployment circuit breaker; CloudTrail evidence proved propagation took >8 minutes, far outside any fixed budget. #341's actual fix reframed the problem — these secrets never belonged on the ECS-launch-critical `execution_role` at all (`_require_billing_configured()` already 503s gracefully when unset), so they're now granted to `task_role` and fetched in-app at startup, mirroring the existing `SENTRY_DSN` pattern (PR #229) exactly. Confirmed via live `cdk diff`: zero IAM changes to `ApiExecutionRole`, zero Lambda/Trigger machinery left in the stack. **Follow-on scope (§8) also shipped:** monthly request-count and simulation-count caps for Pro (hard downgrade to Free, not overage — confirmed decision), a durable `billing_events` audit table, best-effort SES notification on every tier change, Stripe webhook idempotency, and auto-restore to Pro on the next successful payment for accounts downgraded by a monthly cap specifically (narrowed after review — a payment-failure or subscription-cancellation downgrade needs a fresh Checkout instead). 25 new tests, full 1,738-test suite re-run clean | `docs/plan-monetization-implementation.md` (this session) |
| 6 | Market data adapter infrastructure (Refinitiv first) | Hardest | Largest engineering effort (5 phases, MD-1 through MD-5, per the attached plan), touches a genuine compliance boundary (vendor data redistribution restrictions), and has open questions in the plan itself that only Filippo can answer before MD-3 can start (RDP access tier, snapshot vs. streaming, cache TTL legal check, ISIN→RIC persistence). **MD-1 shipped** (PR #332): abstract provider interface, canonical Pydantic schemas, exception family, deterministic fake provider, 12 tests. **MD-2 mechanism shipped** (this session): `registry.py` (config-driven provider selection) + `cache.py` (TTL Redis cache wrapping any provider, reusing `api/routes/caching.py`'s fail-open philosophy) — TTL *values* stay explicit placeholders pending the cache-TTL legal check, unchanged from §3. 15 new tests, 27/27 across both MD-1+MD-2 files, full suite re-run clean. MD-3 (the real Refinitiv adapter) and MD-4 (pipeline wiring) remain hard-gated on Filippo's decisions | `docs/plan-market-data-adapter.md` (this session) |

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

All six items now have full plan docs. Items 2 (pyvar Local) and 5
(monetization) are shipped and live. Item 6's MD-1 and MD-2 (interface/
schemas/fake provider, plus the config-driven registry + TTL cache
mechanism) are both shipped too — the only engineering work across all six
items that had zero external blockers. Everything remaining across items
1, 3, 4 and item 6's MD-3/MD-4 is blocked on Filippo: external submissions
(items 1, 4), publishing (item 3), or business/legal decisions only
Filippo can make (item 6 §3's RDP access tier, snapshot vs. streaming,
cache TTL legal check, ISIN→RIC persistence). Next action per item is
unblocking those decisions, not more planning or engineering.

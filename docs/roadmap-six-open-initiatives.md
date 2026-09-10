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
`docs/proposals/marketplace-submission-content.md`. Confirmed still present
in `pyvar-grant-brief-nlnet.docx` (item 4 below); not yet checked in
`pyvar-grant-brief.docx`, `pyvar-monetization-strategy.docx`, or
`pyvar-local-package-proposal.docx` — check all of them before any is used
externally. pyvar's real license, everywhere in the actual codebase, is
**Apache-2.0**. This is a "fix before you submit/publish/reference
externally" issue on every one of these `.docx` files, not just the NLnet
one.

## The six items, ranked

| # | Item | Complexity | Why this rank | Plan doc |
|---|---|---|---|---|
| 1 | Anthropic plugin marketplace: status review + submit remaining plugins | Easiest | Investigation + submission actions only; no new engineering; submission *content* is already 95% prepared in `docs/proposals/marketplace-submission-content.md` | `docs/plan-plugin-marketplace-status-and-submission.md` (this session) |
| 2 | One-off `pyvar-local` package generation and sharing | Low | The package (`pyvar-local/`) and its CDK publish pipeline (`pyvar-cdk/stacks/local_package_stack.py`) already exist and are described as "manually-triggered" — this is likely "trigger it and verify the release asset," not new build work, pending a read of the full proposal doc to confirm scope hasn't grown | Not yet written |
| 3 | New posts/articles about pyvar | Moderate | Pure content work, but we have an established, proven process from this session (Medium article + LinkedIn + HN/Reddit drafts) to reuse; the open question is *what's new to write about* since the last article already covers the big narrative | Not yet written |
| 4 | NLnet submission preparation | Moderate-high | No code, but real research/strategy risk: the existing brief has the stale MIT license issue above, a stale "repository visibility flip" reference, an August 2026 prep date, and — per its own caveat — was written while NLnet's fund lineup was "mid-restructuring," with a new call expected to open "early September 2026." Today is 2026-09-10 — **that window may be open now**, and I have no browsing access to check nlnet.nl/propose directly | Not yet written |
| 5 | Monetization strategy implementation for pro/enterprise tiers | High | Spans business strategy *and* real engineering (billing/metering/tier gates) with live revenue implications; `pyvar-monetization-strategy.docx` exists but "implementation" is a different, larger scope than the strategy document itself | Not yet written |
| 6 | Market data adapter infrastructure (Refinitiv first) | Hardest | Largest engineering effort (5 phases, MD-1 through MD-5, per the attached plan), touches a genuine compliance boundary (vendor data redistribution restrictions), and has open questions in the plan itself that only Filippo can answer before MD-3 can start (RDP access tier, snapshot vs. streaming, cache TTL legal check, ISIN→RIC persistence) | Not yet written |

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

Item 1's full plan follows in this same PR
(`docs/plan-plugin-marketplace-status-and-submission.md`). Item 2 is next
once this is reviewed — will read `pyvar-local-package-proposal.docx` in
full first, since it wasn't read for this roadmap pass.

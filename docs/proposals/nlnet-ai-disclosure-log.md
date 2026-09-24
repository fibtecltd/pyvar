# AI disclosure — prompt/interaction log for the NLnet Restack proposal

Attachment supporting the NLnet application form's AI disclosure section ("Did you use generative AI in writing this proposal?"). This file is not a summary written after the fact — every prompt, response excerpt, and file edit below is extracted programmatically from this session's own real Claude Code transcript (session `a5490a78-918a-51fa-a45e-baa8091033f7`), filtered to every turn that mentions "nlnet" (case-insensitive), then further filtered to genuine human-typed prompts (excluding harness-injected context-compaction summaries and skill-loading boilerplate, which are system-generated, not something Filippo typed).

**Model:** Claude (Anthropic), via Claude Code — the specific model serving each turn varied across this multi-week session as Anthropic's available models changed; the most recent turns (2026-09-19 onward) ran on Claude Sonnet 5. **Tool:** Claude Code CLI (agentic coding tool with file read/write/edit, bash, web search, and GitHub access).

**What it was used for:** drafting and iteratively revising the proposal's text-field answers in `docs/proposals/nlnet-restack-form-answers.md` against NLnet's real form fields and character limits; researching and correcting assumptions against NLnet's own GenAI policy and propose-page text (pasted in directly by Filippo); adding citations to already-published project articles once those existed; and compiling this disclosure log itself from the real session transcript.

---

## Real, human-typed prompts (chronological)

Every prompt below was typed by Filippo Buchicchio in this Claude Code session. Quoted verbatim, including typos.

### 2026-09-10T20:09:27.561Z

```
@"/root/.claude/uploads/a5490a78-918a-51fa-a45e-baa8091033f7/dab8918a-pyvarmarketdataadapterplan.md" ok we are good here. now we need to tackle several things still open/unaddressed. the unordered list is:
-nlnet submission preparation
-market data adapter infrastructure development (check attached hypothetical plan with Refinitiv as 1st candidate)
-new posts/articles about pyvar platform
-monetization strategy implementation for pro & enterprise tier
-one off pyvar local package generation and sharing
-anthropic plugin status review and submission of the remaining plugins
you can pickup points in the inverse order of complexity from the easiest one to the hardest.
each single point needs to be properly planned and fully documented.
```

### 2026-09-11T21:18:49.957Z

```
just a confirmation, do I need to resubmit the plugin to Anthropic? if not we can move to the next step. I will submit the plugin to smithery and the nlnet form in the next days and give you an update once done.
```

### 2026-09-17T14:27:30.559Z

```
@"/root/.claude/uploads/a5490a78-918a-51fa-a45e-baa8091033f7/032173f6-NLnet_Policy_on_the_use_of_Generative_Artificial_Intelligence_for_NLnet-funded_projects.htm" @"/root/.claude/uploads/a5490a78-918a-51fa-a45e-baa8091033f7/08997e98-NLnet_Apply_for_a_grant.htm" we need to review the NlNet application since it seems AI project are not welcome / banned there. these are the links with the details: 
https://nlnet.nl/propose/
https://nlnet.nl/foundation/policies/generativeAI/
for your convenience, should not be able to reach them I have attached the saved html pages here.
```

### 2026-09-19T09:09:56.767Z

```
we need to address the following tasks in order of precedence:
- list 5 topics to include on each medium article
- prepare a 6th article and doc around the iron-triangle representation to maximize savings,speed,accuracy, (or minimize costs,time,discrepancies from benchmarks), the architectural design, the cherry-picked technology stacks adopted and the methodology followed to reach the target. this needs to include where applicable tables,diagrams,schemas and pictures.
- review and update the NlNet form submission document in the light of the recent articles with references to them
- review and update the pyvar-monetization-strategy document by including 3 costs-income scenarios: pessimistic,neutral,optimistic.
```

### 2026-09-24T08:51:39.440Z

```
we need to address the AI disclousre statement for the NlNet submission. I have attached the page text below: AI disclosure
Did you use generative AI in writing this proposal? (See our GenAI policy.)
Which model did you use? What did you use it for? Please paste your prompts/interactions and the AI output in this text field (max. 8000 characters), or upload them as a file.
Upload prompts/dialogues used in creation of this proposal. (max. 50 MB in total)
```

---

## AI text responses mentioning NLnet (chronological, verbatim)

Claude's own prose replies during the same turns — status updates, findings, and decisions-as-recorded, unedited.

### 2026-09-10T20:10:12.990Z

This is a large, multi-workstream ask — six real initiatives spanning grant writing, infrastructure engineering, content, business strategy, packaging, and partner-ecosystem work. Given the size, I'll do this properly rather than shallow across all six at once: rank by complexity, write a short roadmap doc capturing the full sequence and rationale, then go deep on the first (easiest) item now and produce its full plan. I'll continue down the list on your go-ahead rather than trying to fully plan all six in one pass — that would dilute quality on the harder ones.

My complexity ranking, easiest → hardest:

1. **Anthropic plugin status review + submission of remaining plugins** — mostly investigation + submission actions, no new engineering
2. **One-off pyvar-local package generation and sharing** — packaging/build tooling, no new features
3. **New posts/articles about pyvar** — content creation, we already have an established process/voice from this session
4. **NLnet submission preparation** — grant-writing/strategy, no code, but needs matching pyvar to NLnet's actual call themes (I have no browsing access to verify current calls — will flag this as a real gap)
5. **Monetization strategy for pro/enterprise tiers** — business strategy + real engineering (billing, metering, tier gates), ongoing revenue implications
6. **Market data adapter infrastructure (Refinitiv)** — the largest, most technical, most compliance-sensitive, and per the attached plan has several open decisions only you can make before MD-3 can even start

Let me investigate the codebase for items 1 and 2 to ground the roadmap in what's actually there rather than assumptions.

### 2026-09-10T20:12:52.358Z

Found something important: the NLnet grant brief still says **"Licence MIT"** throughout — the same MIT/Apache-2.0 mistake we already caught and fixed in the marketplace submission content, `scripts/generate_plugins.py`, and the portal footer, but this document was apparently missed. It also says "once the repository visibility flip completes" (stale — the repo's been public for weeks) and is dated August 2026. I'll flag this clearly in the roadmap without going deep on the fix now — that's item 4's job, not item 1's.

Writing the roadmap doc now, then the full item-1 plan.

### 2026-09-10T20:14:04.388Z

**PR #331** opened: https://github.com/fibtecltd/pyvar/pull/331

Summary of where things stand:

- **Roadmap doc** ranks all six items easiest → hardest, with rationale, and flags a real cross-cutting problem: the pre-existing proposal `.docx` files (grant briefs, monetization strategy, local-package proposal) were written before this session's Apache-2.0 license correction — confirmed the NLnet grant brief still says "Licence MIT" throughout, plus has a stale "repository visibility flip" reference and an August prep date. Haven't checked the other three `.docx` files yet.
- **Item 1's full plan** (plugin marketplace) is done. Short version: the submission content is already well-prepared from a prior session, but there's a real ambiguity only you can resolve — whether what was actually submitted to `claude-plugins-community` was just `pyvar-mcp` or the whole 14-plugin marketplace bundle, plus whether a review decision has landed since, plus the still-open MIT-correction-on-the-submitted-form question from 2026-09-01. I have no authenticated access to check any of that myself.

Next up is item 2 (`pyvar-local` packaging) — I'll read `pyvar-local-package-proposal.docx` in full before writing that plan, since I only skimmed its README/CDK stack existence for the roadmap pass. Let me know if you want me to continue straight into that now, or if you want to review #331 and answer item 1's open questions first.

### 2026-09-10T20:35:34.366Z

Pushed to PR #331. Item 3's plan:

- **Found genuinely new material**, not a rehash: the TokenReportStack pipeline-deploy bug (a subtle, on-brand "verify by running it" story), the AWS cost correction ($900–1,000/month real vs. a stale £126 target), and the Partner Network Customer-Story-declined → Public-Case-Study-resubmitted saga.
- **Recommendation**: one combined follow-up post (Medium primary, LinkedIn adaptation) rather than four separate ones — leads with the bug, cost correction as act two, Partner Network story as a shorter coda.
- **Holding off on HN/Reddit** for this one — too soon after the first post on those specific communities to avoid reading as repeat self-promotion; revisit at the next real milestone.
- **What's next**: your call on the angle, then I draft (same verify-every-number-against-the-repo process as the first article), then you publish.

Continuing straight into item 4 (NLnet submission) unless you want to redirect — that one's flagged as having a real time-sensitivity: the grant brief's own note said NLnet's new call was expected to open "early September 2026," and today's the 10th, so worth checking whether that window is live now.

### 2026-09-10T21:01:09.258Z

Let me try to check NLnet's current call status directly, since that's the most time-sensitive unknown for this item.

### 2026-09-10T21:03:29.790Z

Pushed to PR #331. Item 4 turned up genuinely time-sensitive, actionable findings:

- **The window is open now**: NLnet's restructuring resolved into "Open Internet Stack," with a live call and a real deadline — **2026-11-03**, about 7 weeks out.
- **Restack, not CodeSupply**: both are new programmes with matching €5k–€50k budgets and the same deadline, but Restack's eligible activities explicitly include "security proofs and audits" — a near word-for-word match to the brief's own framing. CodeSupply's actual theme (software supply-chain security) doesn't fit pyvar.
- **Bigger finding**: the real NLnet submission is a short 6-question plain-English web form (~1–2 pages), not the existing 5-page `.docx` — that document is source material to draw condensed answers from, not the deliverable. I only found 3 of the 6 questions (via a third-party guide, since `nlnet.nl` itself is blocked to me) — flagged for you to verify directly before final drafting.
- Same MIT/Apache-2.0 and stale-date issues as the other proposal docs, now confirmed here too.

Continuing straight into item 5 (monetization strategy implementation) unless you want to pause — that one's flagged as the second-hardest, spanning real business decisions and engineering (billing/metering), so it may need more back-and-forth than the first four.

### 2026-09-11T12:45:34.205Z

Good, branch is up to date. Let me gather what's needed for both items — the NLnet plan and the existing article for voice/format reference.

### 2026-09-11T12:52:35.247Z

Now let's update the roadmap doc's item 3 and item 4 rows, and check the cross-cutting MIT/Apache finding note since the NLnet docx is now fixed.

### 2026-09-11T12:53:23.380Z

Pushed to PR #333. Here's the full answer plus what's now folded in:

**CodePipeline trigger:** Yes — merging #333 would start an execution. The push-filter trigger only excludes 8 top-level *directories* (`.claude`, `.claude-plugin`, `.github`, `docs`, `ingestion`, `pyvar-client`, `scripts`, `tests` — AWS caps that list at 8 entries), not individual root files or the `plugins/` directory, and this PR touches `CHANGELOG.md` plus `plugins/mcp/Dockerfile`/`smithery.yaml`. It's already a documented, accepted cost (`docs/known-issues.md`, confirmed live via PR #325): the pipeline runs but the in-execution skip-gates no-op the actual deploy work since nothing under `_PORTAL_RELEVANT_PATHS`/`_IMAGE_RELEVANT_PATHS` changed — no real ECS deploy, image rebuild, or Prod risk (Prod also sits behind manual approval regardless).

**Folded into PR #333** (now pushed, commit `27927a6`):
- **Item 3** — full Medium draft (`docs/publications/pyvar-post-launch-lessons-medium-article.md`) + LinkedIn adaptation, covering the TokenReportStack deploy bug, the migration image-pinning bug underneath it, the $900–1,000/mo cost correction, and the Partner Network resubmission story. Re-verified every number against the repo while drafting — caught and corrected the plan doc's own unchecked "eleven merged PRs" claim down to the real count (7, `#326`–`#332`).
- **Item 4** — fixed `pyvar-grant-brief-nlnet.docx`'s staleness (MIT→Apache-2.0, repo-visibility wording, fund name resolved to Restack) and drafted condensed answers to 3 of NLnet's 6 real form questions (`docs/proposals/nlnet-restack-form-answers.md`).

Both still need you: confirm the article angle before it's published, and verify the other 3 NLnet question texts against the live form before the 2026-11-03 deadline. PR #333 itself is still open, ready whenever you want to merge.

### 2026-09-11T13:01:30.009Z

PR #333 is merged into master (squash commit `9b0a0f7`). All 18 CI checks passed green, and as expected it triggered a low-cost CodePipeline no-op run (no real deploy since nothing under `_PORTAL_RELEVANT_PATHS`/`_IMAGE_RELEVANT_PATHS` changed).

That closes out roadmap item 1 end-to-end, plus the item 3 (article) and item 4 (NLnet) drafts are now on `master`. Standing by — let me know when the NLnet and Smithery submissions are in, and I'll pick up wherever you'd like next.

### 2026-09-11T21:23:10.071Z

I already confirmed there's no working AWS identity in this session (`aws sts get-caller-identity` → `InvalidClientTokenId`), and just now the sandbox blocked me from even inspecting credential files directly — by design, this environment doesn't carry real AWS access, and there's no GitHub Actions workaround here: the publish pipeline is a CodePipeline stage, triggered only via AWS Console or `aws codepipeline start-pipeline-execution`, not a `workflow_dispatch` I could fire through the GitHub API instead.

So item 2 genuinely needs you (or someone with real AWS console/CLI access to account `347228921290`) to run it. Two things are still open before it can even run, per `docs/plan-pyvar-local-package-generation.md`:

1. **Which environment** — `dev` or `prod`? (Prod uses the real `requirements-heavy.txt`, not a dev shortcut — probably what you want for an actual share, but confirm.)
2. **Who's it for** — since the repo's public, the resulting GitHub Release asset will be too. If this is for a specific prospect, a direct link works fine once published; if you need it *not* publicly discoverable, that's a different distribution mechanism than what's built.

Once you answer those, here's exactly what to run:

```bash
# 1. Confirm/deploy the stack (from pyvar-cdk/)
cdk deploy pyvar-<env>-local-package

# 2. Trigger the pipeline once
aws codepipeline start-pipeline-execution --name pyvar-<env>-local-package
# (or AWS Console → CodePipeline → pyvar-<env>-local-package → "Release change")

# 3. Watch Build+Test — it fails closed if tests/test_engine.py fails inside
#    the built image, so red here means a real problem, not a flake.
```

Once it's green, send me the resulting release tag or URL and I'll verify the GitHub Release/asset via the API (tag correctness, asset present, size sanity-check) — same as I did for the changelog/tag work earlier. Meanwhile I'll stand by for that plus your Smithery/NLnet update.

### 2026-09-12T11:40:31.278Z

Confirmed end-to-end — item 2 is done. 🎉

**`pyvar-local-v0-6682472c`** — published 2026-09-12T11:37:12Z, pre-release, on `github.com/fibtecltd/pyvar/releases/tag/pyvar-local-v0-6682472c`:
- Asset `pyvar-local.tar.gz`, state **uploaded**, **555.4 MB** (a real, sane size for a Docker image tarball — not empty or truncated), SHA256 digest recorded.
- Direct download link: `github.com/fibtecltd/pyvar/releases/download/pyvar-local-v0-6682472c/pyvar-local.tar.gz`

That's the artifact ready to share for the proof of concept. Three real bugs found and fixed along the way (#334 CfnOutput token, #335 bash-only substring syntax, #336 the empty-SHA source), all verified via local reproduction before you ever had to re-run anything blind — item 2 of the roadmap is now genuinely complete, not just "looks green."

Whenever you're ready, let me know how you'd like to get that tarball to whoever the POC is for, and give me the Smithery/NLnet update whenever those land.

### 2026-09-14T16:14:42.400Z

Item 5 (monetization) is done and shipped. Here's where the other five stand, per `docs/roadmap-six-open-initiatives.md`:

| # | Item | Status |
|---|---|---|
| 1 | Plugin marketplace submission | Content fully prepared; submitting via the authenticated form is Filippo-only |
| 2 | `pyvar-local` package generation | Pipeline exists and works; triggering it needs real AWS creds this session doesn't have |
| 3 | New articles/posts | Draft written (folded into PR #333); needs you to confirm the angle, then publish |
| 4 | NLnet submission | Fund identified (Restack), form answers drafted for 3/6 questions; needs you to confirm the remaining 3 against the live form, deadline 2026-11-03 |
| 5 | Monetization | **Done** — shipped, live-deployed, pipeline issue just resolved |
| 6 | Market data adapters (Refinitiv) | Hardest item, deliberately last. MD-1 (interface/schemas/fake provider/unit tests) has **zero external blockers and is buildable now** |

Items 1-4 are all currently stuck on things only you can do (external forms, publishing, AWS credentials this session lacks) — there's no more engineering to push on any of them right now.

That makes item 6's MD-1 the only piece with real engineering work available in this session. The plan doc flags one open scope call before I start it:

### 2026-09-14T17:32:01.041Z

Here's where all six items stand now:

| # | Item | Status |
|---|---|---|
| 1 | Plugin marketplace submission | Content 100% prepared; submitting via the authenticated form is **Filippo-only** |
| 2 | `pyvar-local` package | **Shipped** — download page live |
| 3 | Articles/posts | Drafted (Medium + LinkedIn); needs **Filippo** to confirm the angle and publish |
| 4 | NLnet submission | Fund identified, 3/6 form answers drafted; needs **Filippo** to confirm the remaining 3 against the live form, deadline 2026-11-03 |
| 5 | Monetization | **Shipped** — live and deployed |
| 6 | Market data adapters | MD-1 + MD-2 **shipped**. MD-3 (real Refinitiv adapter) and MD-4 (pipeline wiring) are hard-gated behind decisions only **Filippo** can make (RDP access tier, snapshot vs. streaming, cache-TTL legal check, ISIN→RIC persistence) |

There's no more autonomous engineering work available — items 2, 5, and 6's buildable phases are all done. Everything left (1, 3, 4, and item 6's MD-3/MD-4) is blocked on external actions or decisions that only you can make: submitting the marketplace form, publishing the articles, confirming the NLnet form questions, and answering the four Refinitiv sandbox questions.

Want me to draft anything to make those easier to unblock — e.g. a short summary you could send yourself as a checklist, or dig further into any one of the four Refinitiv decisions to narrow it down?

### 2026-09-14T17:41:49.739Z

Here's the full action checklist — everything left that only you can do:

**1. Plugin marketplace submission**
- [ ] Submit the 13 domain/architecture skills + MCP server plugin via the authenticated marketplace form
- [ ] Content is ready in `docs/proposals/marketplace-submission-content.md`

**2. Articles/posts** *(no hard deadline)*
- [ ] Confirm the angle on the combined Medium + LinkedIn draft
- [ ] Publish once approved
- Drafts: `docs/publications/pyvar-post-launch-lessons-medium-article.md` + LinkedIn adaptation

**3. NLnet submission** *(deadline: 2026-11-03)*
- [ ] Confirm the remaining 3 of 6 form question texts against the live Restack form
- [ ] Submit via the form (source material + drafted answers in `docs/proposals/nlnet-restack-form-answers.md`)

**4. Market data adapters — 4 decisions blocking MD-3 (Refinitiv)** *(no deadline, but gates further engineering)*
- [ ] RDP access tier / app registration scope — which instrument classes and history depth the sandbox grants
- [ ] Snapshot (REST) vs. streaming (RDP WebSocket) for v1 — plan recommends REST-only to start, your call
- [ ] Cache TTL policy — needs a legal/contract check against Refinitiv's actual sandbox terms
- [ ] Whether the ISIN→RIC mapping table may be persisted — same terms-check dependency

Everything else across all six roadmap items is already shipped and live. Want this as a doc you can check off, or is the list itself enough?

### 2026-09-17T14:37:38.329Z

CodeSupply's real scope (confirmed via NLnet's own site, not a third-party guide) is software supply-chain **metadata publishing** — SBOMs, license-compliance datasets, ecosystem-scale data infrastructure. That's not what pyvar's audit work would produce, so it's not a fit. Recording that and locking in the framing decision.

### 2026-09-17T14:39:43.639Z

PR #351 is up. Holding off on merging until you've reviewed — the `README.md` change is public-facing.

## Summary

Reviewed both pages you attached. The short version: **NLnet has not banned AI-assisted projects.** The propose page's blunt "not interested in AI-generated projects" line sits next to a policy that's actually a disclosure-and-accountability regime — GenAI use must be disclosed (in the application, via a required prompt-log field, and in the codebase, via a README statement), humans stay accountable for correctness, and purely-AI output isn't payable work. pyvar's development model — human-directed, verified, corrected, git-native `Co-Authored-By` trailers — is substantively compatible with that.

Three real findings, now reflected in `docs/plan-nlnet-submission.md`, `docs/proposals/nlnet-restack-form-answers.md`, and `README.md`:

1. **The real form isn't the "6 questions" shape** the old draft assumed — it's a structured field set with per-field character limits. Rewrote the answer drafts against the actual fields.
2. **README didn't actually disclose GenAI development-process use** — it had a misleading tech-stack row implying the Claude API is a runtime dependency (it isn't, verified by grep). Fixed, plus added a factual "Use of Generative AI" section.
3. **CodeSupply, checked against NLnet's own pages, isn't a fit** — it's a software supply-chain-metadata programme, not adjacent to what pyvar or the proposed audit work actually does. Restack only.

Per your framing decision: the application's pitch is written around the audit work the grant funds, not led by the AI-build story — full disclosure still happens exactly where the form requires it.

Still needs you before this can be submitted: a specific `amount`, the `entity` field choice, and your own words for the experience/other-funding fields (deliberately left as placeholders, not drafted on your behalf).

### 2026-09-17T15:31:50.747Z

Pushed to PR #351. Applied both decisions:

- **Entity**: Fibtec Limited (SME company), resolved in the form-answers doc.
- **Rate**: €100/hour → proposed a concrete **€27,200** total, broken down across the four milestones (security review, numerical audit, coverage extension, docs) with hours and cost per line — a real prefill you can adjust, not a placeholder.

One thing I didn't guess at: you said "main developer but not the only one," but `git log` shows only your name as a human commit author (Claude appears as AI co-author, not a second person). I flagged this in the doc rather than assuming — if you mean Claude's contribution, that's already covered by the AI-disclosure section; if there's a real second human collaborator not yet in git history, worth naming them since NLnet's policy is specific about accurately identifying who did the work.

Still open whenever you're ready: the LinkedIn excerpt for the Experience field, and that clarification. PR #351 still unmerged, waiting on you.

### 2026-09-19T09:25:39.260Z

Now let's move to task 3 — the NLnet form. First, checking current git state.

### 2026-09-19T09:26:50.758Z

Now task 3 — reviewing and updating the NLnet form. Let me check exact character budgets on the relevant fields before editing.

### 2026-09-19T09:39:16.963Z

PR #360 is open: https://github.com/fibtecltd/pyvar/pull/360

All 4 tasks are now done:
1. **Medium tags** — answered in chat only (no repo change needed).
2. **Iron Triangle expansion** — architecture/stack/methodology sections added to the benchmark docx + new companion Medium article, both committed.
3. **NLnet form** — citations added to 5 fields, character-budget-checked.
4. **Monetization scenarios** — pessimistic/neutral/optimistic table + narrative appended to the strategy docx.

The PR is confirmed **pipeline-safe** (everything under `docs/`, nothing in `portal/` or root). Per your standing instruction from earlier in this session, I have not merged it — it's yours to merge when ready.

### 2026-09-24T08:52:19.804Z

Good, on a fresh branch from current master. Now let's read the NLnet form doc to see its structure and find where to add this field.

---

## File edits to `docs/proposals/nlnet-restack-form-answers.md` (chronological)

Every `Write` (full-file creation/replacement) and `Edit` (targeted find-and-replace) operation Claude Code applied to the actual proposal answers file, in order. This is the direct AI output that became the proposal text — nothing here was hand-typed by Filippo; his role was directing what to change (see the prompts above) and deciding the substantive calls the tool log below implements (entity type, rate, amount, framing) per `docs/plan-nlnet-submission.md`.

### Edit 1 — 2026-09-11T12:52:13.928Z — `Write`

Full-file write, 7438 characters. First 400 shown:

```markdown
# NLnet Restack application — draft short-form answers

**Draft, not submitted.** Item 4 of `docs/roadmap-six-open-initiatives.md`,
prepared per `docs/plan-nlnet-submission.md` §5. NLnet's real submission
mechanism is a short web form at `nlnet.nl/propose/` — plain English,
roughly six short questions, 1–2 pages total — not the long-form
`pyvar-grant-brief-nlnet.docx` in this same directory (now c...
```

### Edit 2 — 2026-09-17T14:31:26.818Z — `Write`

Full-file write, 12921 characters. First 400 shown:

```markdown
# NLnet Restack application — draft answers to the real form

**Draft, not submitted.** Item 4 of `docs/roadmap-six-open-initiatives.md`,
rewritten 2026-09-17 per `docs/plan-nlnet-submission.md` §3a after Filippo
supplied the actual `nlnet.nl/propose/` form and GenAI policy pages. **This
supersedes the previous version of this file**, which was drafted against a
guessed "6 short questions" shape f...
```

### Edit 3 — 2026-09-17T14:37:55.736Z — `Edit`

**Old text:**
```
See `docs/plan-nlnet-submission.md` §3a for the full policy read and why
this doesn't block submission, and the framing-strategy question that
determines how this section is written (a plain factual disclosure vs.
one that also explains pyvar's broader "verify by running it" AI-use
philosophy) — both are honest; they read very differently to an assessor.
```
**New text:**
```
**Framing resolved (2026-09-17):** per `docs/plan-nlnet-submission.md` §3a,
this section carries the full, honest disclosure — model, prompts, dates,
unedited output — plainly and factually, without expanding it into a
narrative about pyvar's broader AI-build story. The rest of the
application (abstract, budget-use, comparison, above) is written the same
way: focused on the engine and the audit work the grant funds, not led by
"built by an AI agent." Nothing is hidden, nothing is minimized where the
form actually asks — the AI-authorship *story* just isn't the pitch.
```

### Edit 4 — 2026-09-17T14:38:00.038Z — `Edit`

**Old text:**
```
**Before this can be submitted, three things still need Filippo (see the
plan doc §4 for the full list):** the AI-authorship framing call, a
specific `amount` figure, and the `entity` field choice (Individual vs.
Fibtec Limited).
```
**New text:**
```
**Before this can be submitted, some things still need Filippo (see the
plan doc §4 for the full list):** a specific `amount` figure, the `entity`
field choice (Individual vs. Fibtec Limited), and Filippo's own words for
the experience/background and other-funding fields. The AI-authorship
framing call is now resolved — see the AI disclosure section below.
```

### Edit 5 — 2026-09-17T15:30:55.161Z — `Edit`

**Old text:**
```
**Before this can be submitted, some things still need Filippo (see the
plan doc §4 for the full list):** a specific `amount` figure, the `entity`
field choice (Individual vs. Fibtec Limited), and Filippo's own words for
the experience/background and other-funding fields. The AI-authorship
framing call is now resolved — see the AI disclosure section below.
```
**New text:**
```
**Resolved by Filippo (2026-09-17):** the application is submitted under
**Fibtec Limited**, not as an individual; the effective rate for budget
purposes is **€100/hour**. Both are now reflected below. **Still open:**
the LinkedIn-sourced experience text (Filippo will paste it), and one
factual point that needs a quick clarification, not a draft — see
"Experience / background" below.
```

### Edit 6 — 2026-09-17T15:31:09.694Z — `Edit`

**Old text:**
```
## Amount requested

**Needs Filippo — a single figure within €5,000–€50,000.** The prior
brief's "€33k–50k indicative ask" was never narrowed to one number. My
read: the four milestones below (security review, numerical audit,
coverage extension, docs) are real, separable units of work — a number
toward the upper end of the range is defensible *if* Filippo is
comfortable committing to delivering all four; a smaller number covering
just the audits (the most NLnet-aligned pair, per "security proofs and
audits" in Restack's own eligible-activities language) is the safer,
easier-to-justify ask for a first grant. Not my call to pick.

## Use of budget — tasks, effort, rate, expenses (max 4000 chars)

> The requested amount funds four scoped milestones, sequenced so each
> one's findings can narrow the scope of the next rather than committing
> to fixed deliverables upfront:
>
> 1. **Independent security review** (~[X] days) — third-party review of
>    the REST API surface, auth/JWT handling, and dependency chain.
>    Findings published in `docs/`, fixes tracked openly.
> 2. **Independent numerical/regulatory audit** (~[X] days) — a domain
>    expert checking a representative sample of the 385 functions against
>    their published Basel/FRTB/IFRS 9/Solvency II source formulas,
>    corrections published openly (the same discipline that already
>    caught a ~79% Solvency II SCR understatement pre-launch, done here by
>    an external reviewer rather than the maintainer).
> 3. **Regulatory coverage extension** (~[X] days) — scoped once (1) and
>    (2)'s findings are in; likely candidates are fuller Solvency II or
>    CRR3 coverage, narrowed by what the audit actually flags as thin.
> 4. **Documentation for smaller institutions** (~[X] days) — worked
>    examples and onboarding docs aimed at credit unions, fintech
>    startups, and researchers, not enterprise risk desks who already
>    have Bloomberg/Murex.
>
> Rate: **[Filippo — insert the hourly/daily rate used to build the
> breakdown above; the prior brief left this as a placeholder and it was
> never filled in]**. Expenses: none anticipated beyond the independent
> reviewers' own time in (1) and (2), which is the main cost driver —
> compute cost is not a meaningful line item (pyvar's own Monte Carlo
> engine runs at sub-cent per scenario; see `docs/p9-scenario-volume-cost-audit.md`).

**Needs Filippo:** the day-counts and rate are placeholders — this section
can't be finished without the actual numbers behind the requested amount.
```
**New text:**
```
## Amount requested

**Proposed: €27,200** (272 hours at €100/hour — breakdown below). This is
a prefill, not a final number: comfortably inside €5,000–€50,000, credible
as a first-grant ask (≈54% of the cap, not maxing it out), and every line
below is adjustable independently if Filippo wants to trim or expand any
one milestone before submitting.

## Use of budget — tasks, effort, rate, expenses (max 4000 chars)

> The requested amount (€27,200, at €100/hour) funds four scoped
> milestones, sequenced so each one's findings can narrow the scope of the
> next rather than committing to fixed deliverables upfront:
>
> 1. **Independent security review** — 48 hours (6 days), **€4,800**.
>    Third-party review of the REST API surface, auth/JWT handling, and
>    dependency chain. Findings published in `docs/`, fixes tracked openly.
> 2. **Independent numerical/regulatory audit** — 96 hours (12 days),
>    **€9,600**. A domain expert checking a representative sample of the
>    385 functions against their published Basel/FRTB/IFRS 9/Solvency II
>    source formulas, corrections published openly (the same discipline
>    that already caught a ~79% Solvency II SCR understatement pre-launch,
>    done here by an external reviewer rather than the maintainer).
> 3. **Regulatory coverage extension** — 80 hours (10 days), **€8,000**.
>    Scoped once (1) and (2)'s findings are in; likely candidates are
>    fuller Solvency II or CRR3 coverage, narrowed by what the audit
>    actually flags as thin.
> 4. **Documentation for smaller institutions** — 48 hours (6 days),
>    **€4,800**. Worked examples and onboarding docs aimed at credit
>    unions, fintech startups, and researchers, not enterprise risk desks
>    who already have Bloomberg/Murex.
>
> Rate: **€100/hour**, applied uniformly across all four milestones —
> this covers both Fibtec's own development time (milestones 3–4) and the
> independent reviewers engaged for milestones 1–2. Expenses: none
> anticipated beyond that reviewer time, which is the main cost driver —
> compute cost is not a meaningful line item (pyvar's own Monte Carlo
> engine runs at sub-cent per scenario; see `docs/p9-scenario-volume-cost-audit.md`).

**Still Filippo's call:** the day-counts above are my estimate of
reasonable scope per milestone, not something Filippo confirmed line by
line — adjust any of the four before submitting if the real effort looks
different, especially milestones 1–2 where actual reviewer quotes (once
sought) should replace this estimate.
```

### Edit 7 — 2026-09-17T15:31:20.059Z — `Edit`

**Old text:**
```
## Experience / background (max 2000 chars, optional)

> Filippo Buchicchio, UK-based, is the applicant and lead/sole developer
> of pyvar, built through Fibtec Limited (UK-registered). **[Filippo —
> insert your own relevant background/experience here; I don't have
> enough verified detail about your prior work history to draft this
> section honestly, and the policy explicitly wants applicants' own words,
> not AI-drafted biographical claims.]**
>
> What's independently checkable regardless of biographical detail: the
> full commit history and 300+ merged pull requests at
> `github.com/fibtecltd/pyvar`, a live production deployment at
> `pyvar.com`, a published SDK (`pyvar-client` on PyPI), and public
> technical write-ups covering the build — including four regulatory bugs
> found and fixed before launch (`docs/publications/`).

**Needs Filippo — deliberately left incomplete.** The policy's own emphasis
on human authorship makes this the one field where I should not draft
biographical claims on your behalf.
```
**New text:**
```
## Experience / background (max 2000 chars, optional)

> Filippo Buchicchio, UK-based, leads development of pyvar through Fibtec
> Limited (UK-registered), the applicant entity. **[Filippo — paste the
> LinkedIn excerpt here; I don't have enough verified detail about your
> prior work history to draft this section honestly, and the policy
> explicitly wants applicants' own words, not AI-drafted biographical
> claims.]**
>
> What's independently checkable regardless of biographical detail: the
> full commit history and 300+ merged pull requests at
> `github.com/fibtecltd/pyvar`, a live production deployment at
> `pyvar.com`, a published SDK (`pyvar-client` on PyPI), and public
> technical write-ups covering the build — including four regulatory bugs
> found and fixed before launch (`docs/publications/`).

**One factual point needs a quick check before this is finalised, not a
draft:** Filippo noted he's "the main developer but not the only one." The
actual git history (`git log --format='%an <%ae>' | sort -u`) shows only
Filippo Buchicchio as a human commit author — Claude appears as AI
co-author, not a second human. Worth clarifying which this refers to
before the field is written, since NLnet's own "no misrepresentation"
principle is specifically about who did the work:

- If it means Claude Code's contribution — that's already covered by the
  AI-disclosure section and `README.md`'s GenAI statement, no change
  needed here.
- If there's a genuine second human contributor (a collaborator, a
  contractor, informal help) not yet reflected in git authorship — that's
  worth naming here directly, since NLnet explicitly asks who is doing the
  work, and it strengthens rather than weakens the "who's doing the work"
  case for a company-entity application.
```

### Edit 8 — 2026-09-17T15:31:23.824Z — `Edit`

**Old text:**
```
## Contact information

- **Name:** Filippo Buchicchio
- **Email:** filippo.buchicchio@gmail.com (or a Fibtec address, if
  Filippo prefers — not assumed here)
- **Entity type:** **Needs Filippo** — "Individual" vs. "SME company"
  (Fibtec Limited). See plan doc §4 item 5.
- **Organisation name:** Fibtec Limited (if entity = company)
- **Country:** United Kingdom
```
**New text:**
```
## Contact information

- **Name:** Filippo Buchicchio
- **Email:** filippo.buchicchio@gmail.com (or a Fibtec address, if
  Filippo prefers — not assumed here)
- **Entity type:** **SME company** — resolved 2026-09-17, applying as
  Fibtec Limited, not as an individual.
- **Organisation name:** Fibtec Limited
- **Country:** United Kingdom
```

### Edit 9 — 2026-09-17T15:31:27.742Z — `Edit`

**Old text:**
```
## Definition of done

- Amount, entity type, and the AI-authorship framing call are resolved
  (plan doc §4).
- The rate/day-count placeholders in "Use of budget" are filled with real
  numbers.
- The "Experience" and "Other funding" fields are written in Filippo's own
  words, not left as placeholders.
```
**New text:**
```
## Definition of done

- ~~Amount, entity type, and the AI-authorship framing call~~ — resolved
  2026-09-17 (plan doc §4): Fibtec Limited, €100/hour → €27,200 proposed,
  audit-work-first framing.
- The "not the only developer" clarification above is resolved.
- The "Experience" and "Other funding" fields are written in Filippo's own
  words (LinkedIn excerpt pending), not left as placeholders.
```

### Edit 10 — 2026-09-17T15:41:36.967Z — `Edit`

**Old text:**
```
**Resolved by Filippo (2026-09-17):** the application is submitted under
**Fibtec Limited**, not as an individual; the effective rate for budget
purposes is **€100/hour**. Both are now reflected below. **Still open:**
the LinkedIn-sourced experience text (Filippo will paste it), and one
factual point that needs a quick clarification, not a draft — see
"Experience / background" below.
```
**New text:**
```
**Resolved by Filippo (2026-09-17):** the application is submitted under
**Fibtec Limited**, not as an individual; the effective rate for budget
purposes is **€150/hour** (updated from an earlier €100/hour pass — the
budget below reflects the final figure). The "not the only developer"
point is resolved too: it refers to Riccardo Fei's early contributions,
via branches since deleted — Filippo confirmed this isn't a critical
point, so it isn't carried into the application text below. The
LinkedIn-sourced experience excerpt is in place.
```

### Edit 11 — 2026-09-17T15:41:51.996Z — `Edit`

**Old text:**
```
## Amount requested

**Proposed: €27,200** (272 hours at €100/hour — breakdown below). This is
a prefill, not a final number: comfortably inside €5,000–€50,000, credible
as a first-grant ask (≈54% of the cap, not maxing it out), and every line
below is adjustable independently if Filippo wants to trim or expand any
one milestone before submitting.

## Use of budget — tasks, effort, rate, expenses (max 4000 chars)

> The requested amount (€27,200, at €100/hour) funds four scoped
> milestones, sequenced so each one's findings can narrow the scope of the
> next rather than committing to fixed deliverables upfront:
>
> 1. **Independent security review** — 48 hours (6 days), **€4,800**.
>    Third-party review of the REST API surface, auth/JWT handling, and
>    dependency chain. Findings published in `docs/`, fixes tracked openly.
> 2. **Independent numerical/regulatory audit** — 96 hours (12 days),
>    **€9,600**. A domain expert checking a representative sample of the
>    385 functions against their published Basel/FRTB/IFRS 9/Solvency II
>    source formulas, corrections published openly (the same discipline
>    that already caught a ~79% Solvency II SCR understatement pre-launch,
>    done here by an external reviewer rather than the maintainer).
> 3. **Regulatory coverage extension** — 80 hours (10 days), **€8,000**.
>    Scoped once (1) and (2)'s findings are in; likely candidates are
>    fuller Solvency II or CRR3 coverage, narrowed by what the audit
>    actually flags as thin.
> 4. **Documentation for smaller institutions** — 48 hours (6 days),
>    **€4,800**. Worked examples and onboarding docs aimed at credit
>    unions, fintech startups, and researchers, not enterprise risk desks
>    who already have Bloomberg/Murex.
>
> Rate: **€100/hour**, applied uniformly across all four milestones —
> this covers both Fibtec's own development time (milestones 3–4) and the
> independent reviewers engaged for milestones 1–2. Expenses: none
> anticipated beyond that reviewer time, which is the main cost driver —
> compute cost is not a meaningful line item (pyvar's own Monte Carlo
> engine runs at sub-cent per scenario; see `docs/p9-scenario-volume-cost-audit.md`).

**Still Filippo's call:** the day-counts above are my estimate of
reasonable scope per milestone, not something Filippo confirmed line by
line — adjust any of the four before submitting if the real effort looks
different, especially milestones 1–2 where actual reviewer quotes (once
sought) should replace this estimate.
```
**New text:**
```
## Amount requested

**Proposed: €40,800** (272 hours at €150/hour — breakdown below). This
sits at ≈82% of the €50,000 cap — a real jump from the earlier €100/hour
pass, worth a second look: it's a defensible rate for 20+ years of senior
IB/consultancy risk-management experience (per the Experience section
below), but a first-grant ask this close to the ceiling is a genuine
choice, not a neutral default. If Filippo wants more headroom, trimming
hours on milestones 3–4 (the least externally-verifiable of the four, and
the ones most naturally scoped down without weakening the audit case) is
the easiest lever — the breakdown below makes every line independently
adjustable.

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
> engine runs at sub-cent per scenario; see `docs/p9-scenario-volume-cost-audit.md`).

**Still Filippo's call:** the day-counts above are my estimate of
reasonable scope per milestone, not something Filippo confirmed line by
line — adjust any of the four before submitting if the real effort looks
different, especially milestones 1–2 where actual reviewer quotes (once
sought) should replace this estimate, and worth a deliberate decision on
whether €40,800 (vs. a trimmed-down number) is the right ask for a first
grant.
```

### Edit 12 — 2026-09-17T15:42:02.643Z — `Edit`

**Old text:**
```
## Experience / background (max 2000 chars, optional)

> Filippo Buchicchio, UK-based, leads development of pyvar through Fibtec
> Limited (UK-registered), the applicant entity. **[Filippo — paste the
> LinkedIn excerpt here; I don't have enough verified detail about your
> prior work history to draft this section honestly, and the policy
> explicitly wants applicants' own words, not AI-drafted biographical
> claims.]**
>
> What's independently checkable regardless of biographical detail: the
> full commit history and 300+ merged pull requests at
> `github.com/fibtecltd/pyvar`, a live production deployment at
> `pyvar.com`, a published SDK (`pyvar-client` on PyPI), and public
> technical write-ups covering the build — including four regulatory bugs
> found and fixed before launch (`docs/publications/`).

**One factual point needs a quick check before this is finalised, not a
draft:** Filippo noted he's "the main developer but not the only one." The
actual git history (`git log --format='%an <%ae>' | sort -u`) shows only
Filippo Buchicchio as a human commit author — Claude appears as AI
co-author, not a second human. Worth clarifying which this refers to
before the field is written, since NLnet's own "no misrepresentation"
principle is specifically about who did the work:

- If it means Claude Code's contribution — that's already covered by the
  AI-disclosure section and `README.md`'s GenAI statement, no change
  needed here.
- If there's a genuine second human contributor (a collaborator, a
  contractor, informal help) not yet reflected in git authorship — that's
  worth naming here directly, since NLnet explicitly asks who is doing the
  work, and it strengthens rather than weakens the "who's doing the work"
  case for a company-entity application.
```
**New text:**
```
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
> What's independently checkable regardless of biographical detail: the
> full commit history and 300+ merged pull requests at
> `github.com/fibtecltd/pyvar`, a live production deployment at
> `pyvar.com`, a published SDK (`pyvar-client` on PyPI), and public
> technical write-ups covering the build — including four regulatory bugs
> found and fixed before launch (`docs/publications/`).

(≈1850 characters — close to the 2000-char limit; the "independently
checkable" paragraph is the first thing to trim if it needs to shrink.)
```

### Edit 13 — 2026-09-17T15:42:19.956Z — `Edit`

**Old text:**
```
## Definition of done

- ~~Amount, entity type, and the AI-authorship framing call~~ — resolved
  2026-09-17 (plan doc §4): Fibtec Limited, €100/hour → €27,200 proposed,
  audit-work-first framing.
- The "not the only developer" clarification above is resolved.
- The "Experience" and "Other funding" fields are written in Filippo's own
  words (LinkedIn excerpt pending), not left as placeholders.
- The AI-disclosure prompt log is compiled from the actual session(s) used
  to finalise this text — after finalisation, not before.
- `README.md` carries a proper GenAI-use disclosure statement (plan doc
  §3a) before the "website" field above is something an assessor would
  actually visit and check.
- Submitted via `nlnet.nl/propose/` before **2026-11-03**.
```
**New text:**
```
## Definition of done

- ~~Amount, entity type, and the AI-authorship framing call~~ — resolved
  2026-09-17 (plan doc §4): Fibtec Limited, €150/hour → **€40,800**
  proposed, audit-work-first framing.
- ~~The "not the only developer" clarification~~ — resolved: Riccardo
  Fei's early, since-deleted branches; Filippo confirmed not critical,
  not carried into the application text.
- ~~The "Experience" field~~ — written in Filippo's own words (LinkedIn
  excerpt).
- **Still open:** the "Other funding" field (Fibtec's commercial-support
  revenue status — pre-revenue or generating income?), and a deliberate
  decision on whether €40,800 is the right ask given how close it sits to
  the €50,000 cap (see "Amount requested" above).
- The AI-disclosure prompt log is compiled from the actual session(s) used
  to finalise this text — after finalisation, not before.
- `README.md` carries a proper GenAI-use disclosure statement (plan doc
  §3a) before the "website" field above is something an assessor would
  actually visit and check — done in PR #351, pending merge.
- Submitted via `nlnet.nl/propose/` before **2026-11-03**.
```

### Edit 14 — 2026-09-17T16:32:34.202Z — `Edit`

**Old text:**
```
## Amount requested

**Proposed: €40,800** (272 hours at €150/hour — breakdown below). This
sits at ≈82% of the €50,000 cap — a real jump from the earlier €100/hour
pass, worth a second look: it's a defensible rate for 20+ years of senior
IB/consultancy risk-management experience (per the Experience section
below), but a first-grant ask this close to the ceiling is a genuine
choice, not a neutral default. If Filippo wants more headroom, trimming
hours on milestones 3–4 (the least externally-verifiable of the four, and
the ones most naturally scoped down without weakening the audit case) is
the easiest lever — the breakdown below makes every line independently
adjustable.
```
**New text:**
```
## Amount requested

**€40,800** (272 hours at €150/hour — breakdown below). Confirmed by
Filippo: reasonable, "if not too low" — pyvar is self-funded and
pre-revenue (see "Other funding" below), so this isn't padded against
other income. No further trimming needed.
```

### Edit 15 — 2026-09-17T16:32:38.456Z — `Edit`

**Old text:**
```
**Still Filippo's call:** the day-counts above are my estimate of
reasonable scope per milestone, not something Filippo confirmed line by
line — adjust any of the four before submitting if the real effort looks
different, especially milestones 1–2 where actual reviewer quotes (once
sought) should replace this estimate, and worth a deliberate decision on
whether €40,800 (vs. a trimmed-down number) is the right ask for a first
grant.
```
**New text:**
```
**Still open:** the day-counts above are my estimate of reasonable scope
per milestone, not something Filippo confirmed line by line — worth a
look before submitting if the real effort looks different, especially
milestones 1–2 where actual reviewer quotes (once sought) should replace
this estimate. The total itself is confirmed.
```

### Edit 16 — 2026-09-17T16:32:46.299Z — `Edit`

**Old text:**
```
> Fibtec Limited offers commercial enterprise support and private
> deployment of pyvar as a sustainability model alongside the free public
> tier — **[Filippo: confirm current revenue status here; is this
> generating real income yet, or still pre-revenue? The prior brief didn't
> specify and I don't want to imply traction that doesn't exist yet.]**
> This grant is not the project's only funding mechanism, but is not
> currently supplementing an existing grant either — pyvar has not
> previously received NLnet or comparable grant funding.
```
**New text:**
```
> None. pyvar is entirely self-funded by Fibtec Limited and is currently
> pre-revenue — a Pro/Enterprise commercial tier exists in the product
> (Stripe-billed, live) as a planned sustainability model, but has not yet
> generated income to speak of. This grant would not supplement or overlap
> with any other funding source; pyvar has not previously received NLnet
> or any other grant funding.

(≈380 characters — well inside the 1000-char limit.)
```

### Edit 17 — 2026-09-17T16:32:59.257Z — `Edit`

**Old text:**
```
> What's independently checkable regardless of biographical detail: the
> full commit history and 300+ merged pull requests at
> `github.com/fibtecltd/pyvar`, a live production deployment at
> `pyvar.com`, a published SDK (`pyvar-client` on PyPI), and public
> technical write-ups covering the build — including four regulatory bugs
> found and fixed before launch (`docs/publications/`).

(≈1850 characters — close to the 2000-char limit; the "independently
checkable" paragraph is the first thing to trim if it needs to shrink.)
```
**New text:**
```
> Independently checkable: 300+ merged pull requests and full commit
> history at `github.com/fibtecltd/pyvar`, a live deployment at
> `pyvar.com`, a published SDK (`pyvar-client`, PyPI), and public
> write-ups on the build (`docs/publications/`). Full professional
> background: **[Filippo — paste your public LinkedIn URL here]**.

(≈1780 characters, with the LinkedIn placeholder — room for the real URL
once pasted; trim the "independently checkable" line further if needed.)
```

### Edit 18 — 2026-09-17T16:33:08.472Z — `Edit`

**Old text:**
```
> The closest existing comparator is **QuantLib**, a mature open-source
> (BSD) quantitative finance library — pyvar's own numerical test suite
> already cross-validates against it directly. QuantLib is a
> pricing/analytics *library*: it gives you the building blocks, not the
> compliance layer. pyvar is closer to a hosted, regulator-shaped
> *service* — Basel traffic-light backtesting, FRTB capital calculation,
> IFRS 9 ECL provisioning, Solvency II SCR — delivered as a REST API (and
> now an MCP server for AI coding agents) rather than a library you
> integrate and build the compliance logic around yourself.
```
**New text:**
```
> To our knowledge, pyvar is unique in its category: no other project
> exposes this complete a set of VaR/regulatory-risk functions fully
> open-source, on a high-performance, production-shaped tech stack (Numba
> JIT, async job pipeline, REST + MCP delivery) rather than as a
> closed-source vendor platform or a partial academic implementation.
> That's the gap this comparison substantiates below, rather than assert
> on its own.
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
```

### Edit 19 — 2026-09-17T16:33:18.220Z — `Edit`

**Old text:**
```
(≈1650 characters — leaves headroom; can be extended with more detail on
prior art if Filippo wants a fuller comparison.)
```
**New text:**
```
(≈2186 characters — leaves headroom against the 4000-char limit.)
```

### Edit 20 — 2026-09-17T16:33:25.843Z — `Edit`

**Old text:**
```
**Resolved by Filippo (2026-09-17):** the application is submitted under
**Fibtec Limited**, not as an individual; the effective rate for budget
purposes is **€150/hour** (updated from an earlier €100/hour pass — the
budget below reflects the final figure). The "not the only developer"
point is resolved too: it refers to Riccardo Fei's early contributions,
via branches since deleted — Filippo confirmed this isn't a critical
point, so it isn't carried into the application text below. The
LinkedIn-sourced experience excerpt is in place.
```
**New text:**
```
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
```

### Edit 21 — 2026-09-17T16:33:33.929Z — `Edit`

**Old text:**
```
- ~~Amount, entity type, and the AI-authorship framing call~~ — resolved
  2026-09-17 (plan doc §4): Fibtec Limited, €150/hour → **€40,800**
  proposed, audit-work-first framing.
- ~~The "not the only developer" clarification~~ — resolved: Riccardo
  Fei's early, since-deleted branches; Filippo confirmed not critical,
  not carried into the application text.
- ~~The "Experience" field~~ — written in Filippo's own words (LinkedIn
  excerpt).
- **Still open:** the "Other funding" field (Fibtec's commercial-support
  revenue status — pre-revenue or generating income?), and a deliberate
  decision on whether €40,800 is the right ask given how close it sits to
  the €50,000 cap (see "Amount requested" above).
- The AI-disclosure prompt log is compiled from the actual session(s) used
  to finalise this text — after finalisation, not before.
```
**New text:**
```
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
- **Still open:** Filippo's public LinkedIn URL (placeholder left in the
  Experience field), and the actual reviewer quotes for milestones 1–2
  once sought (replacing this session's day-count estimates).
- The AI-disclosure prompt log is compiled from the actual session(s) used
  to finalise this text — after finalisation, not before.
```

### Edit 22 — 2026-09-19T09:27:36.695Z — `Edit`

**Old text:**
```
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

---
```
**New text:**
```
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
```

### Edit 23 — 2026-09-19T09:27:50.355Z — `Edit`

**Old text:**
```
> Independently checkable: 300+ merged pull requests and full commit
> history at `github.com/fibtecltd/pyvar`, a live deployment at
> `pyvar.com`, a published SDK (`pyvar-client`, PyPI), and public
> write-ups on the build (`docs/publications/`). Full professional
> background: **[Filippo — paste your public LinkedIn URL here]**.
```
**New text:**
```
> Independently checkable: 300+ merged pull requests and full commit
> history at `github.com/fibtecltd/pyvar`, a live deployment at
> `pyvar.com`, a published SDK (`pyvar-client`, PyPI), and 8 public
> write-ups on the build and its own self-audits (`docs/publications/`),
> including two that publish real production mistakes we found and
> fixed rather than leaving out. Full professional background:
> **[Filippo — paste your public LinkedIn URL here]**.
```

### Edit 24 — 2026-09-19T09:28:14.578Z — `Edit`

**Old text:**
```
(≈1780 characters, with the LinkedIn placeholder — room for the real URL
once pasted; trim the "independently checkable" line further if needed.)
```
**New text:**
```
(≈1870 characters, with the LinkedIn placeholder — ~130 chars of room
left for the real URL once pasted; trim the "independently checkable"
line further if the URL doesn't fit.)
```

### Edit 25 — 2026-09-19T09:28:32.945Z — `Edit`

**Old text:**
```
> A secondary risk: regulatory constants and formulas change (BCBS
> shock recalibrations, Basel IV phase-in dates). The audit needs to
> pin down which version of each standard pyvar targets and verify that's
> stated explicitly, not left implicit — a gap the internal review
> already found once (stale pre-2024 IRRBB shock values, fixed in v0.1.0).

(≈1000 characters.)
```
**New text:**
```
> A secondary risk: regulatory constants and formulas change (BCBS
> shock recalibrations, Basel IV phase-in dates). The audit needs to
> pin down which version of each standard pyvar targets and verify that's
> stated explicitly, not left implicit — a gap the internal review
> already found once (stale pre-2024 IRRBB shock values, fixed in v0.1.0,
> written up in full in `docs/publications/pyvar-buildstory-medium-article.md`
> alongside the ~79% Solvency II SCR understatement the same validation
> pass caught).

(≈1180 characters.)
```

### Edit 26 — 2026-09-19T09:28:50.047Z — `Edit`

**Old text:**
```
> Main users today: individual developers and researchers exploring
> quantitative finance in the open, per pyvar.com's own (small, unaudited)
> usage. The grant's stated audience — smaller banks, credit unions,
> fintechs, and researchers outside major financial centres — is the
> intended *next* audience, not yet the confirmed current one; being
> honest about that gap rather than overclaiming existing institutional
> adoption.

(≈780 characters.)
```
**New text:**
```
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

(≈1170 characters.)
```

### Edit 27 — 2026-09-19T09:29:04.458Z — `Edit`

**Old text:**
```
(≈1180 characters.)

## Ecosystem
```
**New text:**
```
(≈1140 characters.)

## Ecosystem
```

### Edit 28 — 2026-09-19T09:29:09.638Z — `Edit`

**Old text:**
```
(≈1170 characters.)
```
**New text:**
```
(≈1160 characters.)
```

### Edit 29 — 2026-09-19T09:29:45.220Z — `Edit`

**Old text:**
```
> To our knowledge, pyvar is unique in its category: no other project
> exposes this complete a set of VaR/regulatory-risk functions fully
> open-source, on a high-performance, production-shaped tech stack (Numba
> JIT, async job pipeline, REST + MCP delivery) rather than as a
> closed-source vendor platform or a partial academic implementation.
> That's the gap this comparison substantiates below, rather than assert
> on its own.
```
**New text:**
```
> To our knowledge, pyvar is unique in its category: no other project
> exposes this complete a set of VaR/regulatory-risk functions fully
> open-source, on a high-performance, production-shaped tech stack (Numba
> JIT, async job pipeline, REST + MCP delivery — architecture and the
> reasoning behind each technology choice both written up in
> `docs/publications/pyvar-technical-deepdive-medium-article.md` and
> `pyvar-iron-triangle-medium-article.md`) rather than as a closed-source
> vendor platform or a partial academic implementation. That's the gap
> this comparison substantiates below, rather than assert on its own.
```

### Edit 30 — 2026-09-19T09:29:58.965Z — `Edit`

**Old text:**
```
(≈2186 characters — leaves headroom against the 4000-char limit.)
```
**New text:**
```
(≈2310 characters — leaves headroom against the 4000-char limit.)
```

### Edit 31 — 2026-09-19T09:30:22.826Z — `Edit`

**Old text:**
```
> 2. **Independent numerical/regulatory audit** — 96 hours (12 days),
>    **€14,400**. A domain expert checking a representative sample of the
>    385 functions against their published Basel/FRTB/IFRS 9/Solvency II
>    source formulas, corrections published openly (the same discipline
>    that already caught a ~79% Solvency II SCR understatement pre-launch,
>    done here by an external reviewer rather than the maintainer).
```
**New text:**
```
> 2. **Independent numerical/regulatory audit** — 96 hours (12 days),
>    **€14,400**. A domain expert checking a representative sample of the
>    385 functions against their published Basel/FRTB/IFRS 9/Solvency II
>    source formulas, corrections published openly (the same discipline
>    that already caught a ~79% Solvency II SCR understatement pre-launch,
>    written up in `docs/publications/pyvar-buildstory-medium-article.md`,
>    done here by an external reviewer rather than the maintainer).
```

### Edit 32 — 2026-09-19T09:30:37.682Z — `Edit`

**Old text:**
```
> compute cost is not a meaningful line item (pyvar's own Monte Carlo
> engine runs at sub-cent per scenario; see `docs/p9-scenario-volume-cost-audit.md`).
```
**New text:**
```
> compute cost is not a meaningful line item (pyvar's own Monte Carlo
> engine runs at sub-cent per scenario; see `docs/p9-scenario-volume-cost-audit.md`
> and `docs/publications/pyvar-iron-triangle-medium-article.md` for the
> public write-up, including the real $900–1,000/month invoice this
> claim is checked against).
```

### Edit 33 — 2026-09-19T09:31:00.572Z — `Edit`

**Old text:**
```
- **Still open:** Filippo's public LinkedIn URL (placeholder left in the
  Experience field), and the actual reviewer quotes for milestones 1–2
  once sought (replacing this session's day-count estimates).
```
**New text:**
```
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
```

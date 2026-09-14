# Plan: Claude Code plugin marketplace — status review + submit remaining plugins

**Item 1 of 6** in `docs/roadmap-six-open-initiatives.md`. Ranked easiest:
investigation + submission actions, no new engineering.

## 1. What's already true, verified against the repo

- pyvar ships **14 plugins** total: 13 skills (8 domain + 5 architecture) and
  `pyvar-mcp` (the MCP server), all listed in
  `.claude-plugin/marketplace.json` under one marketplace named
  `pyvar-marketplace`. Anyone can install today via
  `/plugin marketplace add fibtecltd/pyvar` — this channel is live and
  unaffected by anything below.
- `docs/proposals/marketplace-submission-content.md` already contains fully
  prepared submission content for `claude-plugins-community` — name,
  description, category/tags, security/trust disclosure, links — covering
  the whole marketplace bundle (all 14 plugins described together, not one
  submission per plugin).
- That same document corrects an earlier wrong premise: `claude-plugins-official`
  has **no submission process at all** (Anthropic's own docs, quoted
  verbatim in the file). The real target is `claude-plugins-community`.
- `claude plugin validate ./plugins/<name>` was already run against all 13
  real plugin directories (`plugins/arch/` is a grouping folder, not a
  plugin itself — its 5 subdirectories are) and passed cleanly, confirmed
  2026-08-31.
- Per the PRD (`docs/prd-claude-partner-hub.md` §2/§5): "`pyvar-mcp` was
  submitted to `claude-plugins-community`... submission received by
  Anthropic's review team, decision pending" — this reads as **one plugin**
  (`pyvar-mcp`) having actually gone through the submission form, not the
  full 14-plugin marketplace bundle.
- Repo-side, the earlier MIT→Apache-2.0 license correction (2026-09-01) was
  fully applied: every generated `plugin.json`'s `"license"` field, `plugins/mcp/pyproject.toml`,
  and the portal footer all correctly say `Apache-2.0` today (re-verified
  this session). Only the **already-submitted external form** for
  `pyvar-mcp` still says MIT, per that document's own note — the repo
  can't retroactively fix a submitted form.

## 2. Resolved by Filippo directly (2026-09-14) — no longer open

1. **Scope of what was actually submitted — resolved: per-plugin.**
   Confirmed by Filippo: submissions are per-plugin, not one bundle-level
   submission. `pyvar-mcp` was submitted standalone; the other 13 skill
   plugins (8 domain + 5 architecture) each still need their own separate
   submission through the same form.
2. **Review outcome — resolved: still pending, and not resubmittable.**
   Filippo confirmed Anthropic's decision on the `pyvar-mcp` submission
   hasn't landed yet, and the form doesn't allow resubmitting while a
   decision is pending. Filippo is deliberately waiting for that
   confirmation before submitting the remaining 12 (of the 13 skill
   plugins — `docs/proposals/marketplace-submission-content-per-plugin.md`
   already has 13 blocks drafted, one per skill, in case Filippo wants to
   start with a couple before `pyvar-mcp` resolves; the sequencing
   decision itself is Filippo's call, not a hard technical dependency).
3. **The MIT/Apache correction on the already-submitted form — still
   open, unchanged.** Not addressed in the 2026-09-14 conversation; still
   Filippo's call whether to notify the review team or just ensure the 12
   new submissions say Apache-2.0 correctly.

**Also clarified**: Item 1 is unrelated to Smithery (`plugins/mcp/smithery.yaml`,
`docs/proposals/smithery-submission-content.md`) — that's a separate MCP
registry submission, not one of the six roadmap items, and not discussed
here.

## 2a. Done this session, ahead of Filippo's input

- **Fixed a real, live staleness bug found while re-verifying the plan's own
  claims**: `.claude-plugin/marketplace.json`'s top-level bundle description
  said "382 functions" — the exact figure
  `docs/p9-function-catalogue-reconciliation.md` already says explicitly not
  to quote as current fact (the live count is 385). This is the actual
  file end users see via `/plugin marketplace add fibtecltd/pyvar` today,
  not a historical document, so it was in scope to fix. Regenerated all 13
  plugin.json files afterward (`scripts/generate_plugins.py`) — no-op diff,
  confirming nothing else had drifted.
  Left `pyvar-market-risk`'s own "68 functions" figure untouched — see
  next bullet for why that one is a deliberate, already-correct choice,
  not an error.
- **Resolved the "known gap" `docs/p9-function-catalogue-reconciliation.md`
  itself flagged as unsolved** (§"Why Market Risk specifically"): whether
  the skill's "68" vs the live "71" Market Risk routes was really "largely
  4" legacy duplicates or something looser. It's exactly 4
  (`compute_breaches`, `compute_cvar`, `compute_loss_percentiles`,
  `compute_rolling_var`) — verified by mapping all 71 real route names
  against the SKILL.md's code-block pseudonyms one by one. The skill's
  content itself needed no changes; see that doc's own follow-up section
  for the full mapping.
- **Drafted `docs/proposals/marketplace-submission-content-per-plugin.md`**
  — all 13 individual skill submission blocks plus `pyvar-mcp`'s, pulled
  verbatim from each plugin's already-committed frontmatter/`plugin.json`,
  ready to paste the moment Filippo confirms the submission form wants
  per-plugin entries rather than (or in addition to) the bundle-level
  content that already exists.

## 3. Concrete next actions

**For Filippo (only completable by the account holder — this is now a
"wait, then submit" task, not an investigation):**
- Wait for Anthropic's decision on the already-submitted `pyvar-mcp`
  plugin — the form doesn't allow resubmitting while it's pending, and
  Filippo has chosen to hold the other 12 until that lands.
- Once it lands (approved or not), submit the remaining 12 skill plugins
  (of the 13 in `docs/proposals/marketplace-submission-content-per-plugin.md`
  §1 — `pyvar-mcp` itself, §2 of that doc, is the one already submitted)
  one at a time through the same form, pasting each plugin's ready-made
  block from that doc.
- Decide on the still-open MIT-correction question (§2 above) whenever
  convenient — not blocking the 12 new submissions, which should say
  Apache-2.0 correctly regardless.

**For this session:** nothing further until Filippo has news on the
`pyvar-mcp` decision — the submission content is already fully drafted
and waiting (§2a below), so there's no repo-side work left to do here.

## 4. Definition of done

- `pyvar-mcp`'s Anthropic review decision has landed.
- All 12 remaining skill plugins have been submitted via the same form,
  using the ready-made content in
  `docs/proposals/marketplace-submission-content-per-plugin.md` §1.
- The MIT-correction question is explicitly resolved (either "notify them"
  or "leave it, ensure future submissions are correct") — not left ambiguous.
- `docs/proposals/marketplace-submission-content.md` and
  `docs/prd-claude-partner-hub.md` reflect the real, current status.

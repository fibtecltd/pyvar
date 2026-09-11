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

## 2. What's genuinely unclear and needs Filippo, not more repo digging

1. **Scope of what was actually submitted.** Was it just `pyvar-mcp` as a
   standalone plugin, or the whole `pyvar-marketplace` bundle (which
   happens to foreground `pyvar-mcp` in its description)? This determines
   whether "submit the remaining plugins" means 13 individual submissions
   or confirming the one bundle submission already covers everything.
   I have no browsing/API access to either submission form
   (`claude.ai/admin-settings/directory/submissions/plugins/new` or
   `platform.claude.com/plugins/submit`) to check — both are authenticated
   to your own identity.
2. **Review outcome.** No visibility from this session into whether a
   decision has landed since the PRD's "decision pending" note. Worth
   checking directly.
3. **The MIT/Apache correction on the already-submitted form.** Flagged
   as an open decision since 2026-09-01 and still open: does the review
   team need to be told the submitted form's license field was wrong, or
   is it low-stakes enough to just make sure any *new* submissions say
   Apache-2.0 correctly and let the old one be?

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

**For Filippo (only completable by the account holder, per the submission
doc's own finding):**
- Open `platform.claude.com/plugins/submit` (or the claude.ai directory
  page, whichever you used originally) and check: (a) does a submission
  history/status view exist there, (b) what exactly was submitted last
  time — one plugin or the whole marketplace, (c) is there a decision yet.
- Decide on the MIT-correction question above.
- If the mechanism turns out to be per-plugin: work through the remaining
  12 (or 13) plugins using the same submission form, pasting the relevant
  slice of `docs/proposals/marketplace-submission-content.md`'s content
  for each (the doc already has the shared marketplace-level description;
  each plugin's own one-line description is already in
  `.claude-plugin/marketplace.json` if the form wants it per-plugin).

**For this session, once the above is answered:**
- If new/corrected content is needed for a per-plugin submission flow,
  I can draft the individual submission blocks for each of the 13 skill
  plugins (currently only the bundle-level content exists) — straightforward,
  five minutes of work once I know the form actually wants that.
- Update `docs/proposals/marketplace-submission-content.md` and the PRD
  with whatever the actual review outcome turns out to be, same as every
  other verified-facts update this session has made.

## 4. Definition of done

- Filippo has confirmed submission scope and checked for a review outcome.
- Every plugin that needs individual `claude-plugins-community` submission
  content has it, generated from the same source-of-truth pattern as the
  existing bundle doc (no hand-drifted duplicate content).
- The MIT-correction question is explicitly resolved (either "notify them"
  or "leave it, ensure future submissions are correct") — not left ambiguous.
- `docs/proposals/marketplace-submission-content.md` and
  `docs/prd-claude-partner-hub.md` reflect the real, current status.

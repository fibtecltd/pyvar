# Plan: new posts/articles about pyvar

**Item 3 of 6** in `docs/roadmap-six-open-initiatives.md`. Ranked moderate:
pure content work with an established, proven process from this session
(the Medium article + LinkedIn/HN/Reddit drafting), but the open question
is genuinely *what's new to say* since the last article already told the
big build-story narrative.

## 1. What's already been published — don't repeat this

`docs/publications/pyvar-buildstory-medium-article.md` (live on Medium,
also drafted for LinkedIn) already covers: the 385-function platform
overview, the four pre-launch regulatory bugs (Solvency II SCR ~79%
understatement, rBergomi, EMIR, IRRBB), the caveat-triage follow-on pass,
the `pyvar-jupyter` bugs, the 649/300/131 build stats, and the Iron
Triangle cost/speed/transparency positioning. A second post that rehashes
this reads as noise, not a follow-up.

## 2. What's genuinely new since that article shipped

Five real things have happened since commit `19d31ac` (the publications
commit), all independently verifiable:

1. **A real, subtle production bug, found and fixed** (`v0.2.0`, PR #329's
   second commit): `TokenReportStack` (the daily JWT-report feature from
   #328) was added to `app.py`'s standalone stack list but never to the
   pipeline's actual deploy graph — so it silently never deployed. Worse,
   the migration step itself had a latent bug: it ran migrations against
   whatever task-definition revision was already ACTIVE (the *previous*
   deploy's image), because it ran *before* the same stage registered a
   new one — so a migration introduced in the same commit as the code
   needing it would silently never apply, while the pipeline reported a
   clean success. `0006_user_verified_at` hit this in both dev and prod.
   This is the same "verify by running it, not by a green pipeline" theme
   the first article is built around — a strong, on-brand follow-up angle,
   not a new one.
2. **A real cost-transparency correction** (PR #330): the README's
   "~£126/month at 500 jobs/day" was a stale pre-launch planning *target*,
   never an observed cost. The real, confirmed prod AWS invoice is
   **$900–1,000/month** — more than double even the most careful prior
   bottom-up estimate. The interesting finding underneath it (per
   `docs/p9-scenario-volume-cost-audit.md`): job volume barely moves that
   number at all — fixed infrastructure dominates, not compute. That's a
   genuinely counterintuitive, checkable result worth its own short piece.
3. **A real partner-program story with a twist**: the Claude Partner
   Network Customer Story submission was declined (doesn't name a
   third-party customer — "anonymous stories cannot count as public
   references"), which led to identifying the actual right track (Public
   Case Study, for a company building Claude into its own product, not a
   consulting engagement) and a corrected resubmission. This is a genuinely
   useful "how partner programs actually work" story for other indie/OSS
   builders navigating the same Partner/Product/Client confusion — distinct
   from a pure engineering post.
4. **The pipeline trigger gap** (`docs/known-issues.md`, PR #326): a small,
   almost comedic finding — editing `CLAUDE.md` itself to document a
   pipeline quirk would have triggered the very pipeline execution being
   documented, caught before merge and moved to a `docs/`-excluded file
   instead. Minor, but a nice one-paragraph aside in a larger post rather
   than its own piece.
5. **`v0.2.0` itself** — eleven real merged PRs' worth of fixes and
   features since `v0.1.0`, cut as an actual tagged GitHub Release with a
   real changelog, after discovering the release process itself had been
   dormant since launch.

## 3. Recommended angle and channel

**Recommendation: one follow-up post, not four separate ones.** Title
direction: something like *"What broke in the two weeks after launch (and
what a stale cost estimate taught us about our own infrastructure)"* —
leads with the TokenReportStack bug (strongest technical hook, same "verify
by running it" DNA as the first article), uses the cost correction as the
second act (concrete, surprising number), and closes with the Partner
Network Public-Case-Study story as a shorter "lessons for other
Claude-built open-source projects" coda. Keeps the same disclosed-correction
voice throughout — this whole post *is* a disclosed-correction story by
construction.

- **Primary channel: Medium**, same as the first article — it's a proper
  narrative piece, not a quick update.
- **LinkedIn**: a shorter, standalone adaptation once the Medium piece is
  live, same pattern as before.
- **HN/r/quantfinance**: hold off — per the earlier discussion this
  session, those work best as one-time, substantial posts; a "part 2"
  follow-up within weeks of the first risks reading as repeat
  self-promotion on those specific communities. Revisit once there's a
  materially new milestone (e.g. a Services Track-eligible customer, or the
  market data adapter work).

## 4. What I can do now vs. what needs Filippo

**I can draft directly** (same process as the first article — verify every
number against the repo before writing, same voice, same disclosed-correction
pattern): the full Medium draft and LinkedIn adaptation, once you confirm
the angle above or redirect it.

**Needs Filippo:**
- Confirm the angle (one combined post vs. splitting the cost/bug/CPN
  stories into separate pieces — I have a recommendation above but it's a
  genuine editorial call).
- Actually publish (same as before — I can't post to Medium/LinkedIn
  directly).
- Any interest in covering item 6 (market data adapters) as a future post
  once that work exists to write about — noting it here so it's not lost,
  not proposing it now since there's nothing built yet.

## 5. Definition of done

- Draft matches the angle Filippo confirms, with every number re-verified
  against the repo at time of writing (not copied from this plan doc,
  which could itself go stale by the time drafting happens).
- Published on Medium, LinkedIn adaptation ready.
- `docs/publications/` updated with the new piece, same convention as the
  first article.

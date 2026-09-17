# Plan: NLnet submission preparation

**Item 4 of 6** in `docs/roadmap-six-open-initiatives.md`. Ranked
moderate-high: no code, but real research/strategy risk — the existing
brief was written mid-restructuring and needed live verification before
being trusted. That verification is now done (below), which resolves most
of the risk that made this item harder than items 1–3.

## 1. What's now confirmed, via web search (2026-09-10) — this changes the plan materially

NLnet's fund lineup restructuring, which the existing brief could only
flag as an open caveat, has resolved:

- **NGI Zero Commons Fund** (the fund the original brief was implicitly
  written around) took its **final** call on 2026-06-01 and is not
  reopening in that form — it's been absorbed into a new umbrella,
  "Open Internet Stack."
- **Restack** is the direct successor and the clear best fit for pyvar:
  "practical and financial support to projects... deliver, mature and
  scale new internet commons across the entire technology stack,"
  explicitly retaining "the strength of the NGI Zero approach of
  nurturing bottom-up innovation." Eligible activities explicitly include
  **"security proofs and audits"** — matches the brief's own framing
  ("independent security/correctness auditing... exactly the kind of work
  NLnet has historically prioritised") almost word for word.
- **Restack's terms**: grants **€5,000–€50,000** per project (the brief's
  own €33k–50k indicative ask already sits inside this), a **€7 million**
  total pool through 2030, **deadline 2026-11-03**.
- **CodeSupply** — a second new programme, same 2026-11-03 deadline, same
  €5k–€50k range — is a tempting distractor because the budget matches,
  but its actual theme is **software supply-chain security** (packaging
  metadata, SBOM-adjacent work) — not a natural fit for what pyvar
  actually is. **Recommendation: target Restack, not CodeSupply.**
- **ELFA** (the third new programme) is an encrypted local-first
  collaborative-workspace/social-networking platform — no fit at all.

**Today (2026-09-10) is inside the open window** — the brief's own
"check before you submit" caveat was correct to flag this as
time-sensitive, and it's resolved now, not still an open question.

## 2. A second, important correction: the application format itself

NLnet's actual submission mechanism is **not** a long-form document —
it's a short, plain-text web form at `nlnet.nl/propose/`, explicitly
designed to be quick: NLnet's own guidance (found via search, not
verified against the live form directly — see caveat below) says answers
should be short, plain English, "we don't care about spelling or grammar,
only about your ideas." A third-party guide (not NLnet's own page directly,
since `nlnet.nl` is blocked to this session's browsing) describes it as
**6 short questions, 1–2 pages total**, of which 3 were identifiable:

1. What you're building — technical, specific, prior-art citations. 200–400 words.
2. Problem and impact — which open-internet problem, who benefits, why now. 150–250 words.
3. Who's doing the work — GitHub/papers/prior projects; NLnet funds
   individuals, no company required. 100–200 words.

The remaining 3 questions weren't surfaced by search. **This means the
existing 5-page `pyvar-grant-brief-nlnet.docx` is the wrong shape for the
actual deliverable** — it's good source material to draw condensed
answers from, not something to paste in directly. The real deliverable
for this item is short-form answers to NLnet's actual form questions, not
a polished document.

## 3. What's stale in the existing brief (beyond the fund-name gap it already flagged)

Same pattern as items 1–3's findings:
- Says **"Licence MIT"** throughout — pyvar's real license is
  **Apache-2.0**, everywhere in the actual codebase.
- Says **"once the repository visibility flip completes"** — the repo has
  been public for weeks.
- Dated **August 2026**.
- Leaves the fund name as a deliberate placeholder ("does NOT commit to a
  specific fund name") — now resolvable to **Restack**, per §1.

## 3a. Two material corrections (2026-09-17), from the real form + policy pages Filippo supplied

Filippo attached NLnet's actual `propose/` form and `generativeAI` policy pages
(the live site is blocked to this session's browsing, same as before — these
were supplied directly). Both correct assumptions this plan was built on.

### The real form shape is not "6 short questions"

It's a structured web form with these actual fields (names, limits, and
required/optional status taken directly from the form HTML):

| Field | Limit | Required |
|---|---|---|
| Fund | Restack / CodeSupply / Open call | Yes |
| Proposal title | 100 chars | Yes |
| Website(s)/repos | up to 4 URLs | No |
| Abstract (summary + expected results) | 1000 chars | Yes |
| Amount requested | €5,000–€50,000 (first grant) | Yes |
| Use of budget (tasks, rate, expenses) | 4000 chars | Yes |
| Comparison to other projects | 4000 chars | Yes |
| Technical challenges | 4000 chars | No (recommended) |
| Ecosystem / dependencies / users | 2000 chars | No |
| Experience / background | 2000 chars | No |
| Other funding | 1000 chars | No |
| Attachments | 50MB total | No |
| **AI disclosure** (see below) | 8000 chars + file upload | Yes |
| Contact info (name, email, entity type, country) | — | Yes |

`docs/proposals/nlnet-restack-form-answers.md`'s three drafted answers
(1982/1449/989 chars, written against a guessed "what/why/who" 3-question
shape) don't map cleanly onto this — they span across `abstract` + `use` +
`comparison` + `experience` rather than filling any one field. **That file
needs a rewrite against the real fields, not a light edit** — done below.

### The GenAI policy is real, and it is not a blanket ban — but it is not nothing either

The `propose/` page states plainly: *"We are not interested in AI-generated
projects or proposals."* Read alone, that looks like a hard stop for pyvar.
Read against the actual policy page it links to, it's narrower than that:

- The policy is a **disclosure-and-accountability regime**, not a tooling
  ban. It explicitly permits GenAI use in both the application and the
  funded work, provided it's disclosed, humans remain accountable for
  correctness, and purely-AI output (no "substantial human intellectual
  contribution") isn't submitted as payable deliverable work.
- The form's **AI disclosure section is a real, required field**: a
  Yes/No question ("Did you use generative AI in writing this proposal?")
  plus a mandatory prompt-provenance log (model, dates/times, prompts,
  unedited output — max 8000 chars or a file upload) if the answer is
  Yes. Given this application would itself be drafted with Claude Code's
  help, consistent with how every other piece of writing in this
  repository has been produced this session, the honest answer is **Yes**,
  and a real log needs to be prepared, not skipped.
- For the funded work itself: substantive GenAI-generated code needs
  provenance (model + prompts/summary), ideally per-commit; GenAI-assisted
  testing/documentation only needs a general README-level description.
  Critically, **this only binds work delivered under the grant going
  forward** — the policy is explicit that logging is not retroactive for
  code that predates it, and pyvar's ~677 existing commits (222 of them
  already carrying a `Co-Authored-By: Claude` trailer) were written before
  any NLnet funding existed. Nothing here requires rewriting repo history.
- **A real, current gap**: `README.md`'s only nod to how the project was
  built is *"Built by Fibtec Limited (UK) on top of NumPy, Numba, and the
  Anthropic Claude API"* plus a tech-stack table row listing "AI |
  Anthropic Claude API" — phrased like a runtime dependency, not a
  development-process disclosure. The policy specifically asks for a
  broad README statement of how GenAI was used in *building* the project
  (e.g. "for logic/boilerplate/tests/documentation"). This doesn't exist
  today in the form the policy actually asks for, and is worth fixing
  before submitting regardless of the strategic question below — it's a
  compliance gap, not a judgment call.

### The AI-framing judgment call — resolved by Filippo (2026-09-17)

Substantive compliance is achievable. What was genuinely uncertain was
**reputational, not technical**: pyvar's own existing public narrative
leads hard with AI-authorship as the whole point of the project's story,
and an NLnet assessor who lands on that framing before reading the actual
GenAI policy's nuance could reasonably form the gut impression that pyvar
*is* "an AI-generated project" — exactly the phrase the propose page uses
to say no — even though the underlying technical and disclosure substance
is compliant.

**Resolved: combine two of the three options offered** — (1) reframe the
*pitch itself* around the human-performed, human-accountable audit/
verification work the grant funds (thematically aligned with Restack's own
"security proofs and audits" language, not undermined by disclosing the
base platform's AI-assisted origin), **and** (3) keep the application's
narrative prose minimized on AI-build framing rather than leading with it.
Full, honest AI-disclosure still happens exactly where the form requires
it (the dedicated AI-disclosure section, and eventually a proper README
statement) — nothing here is about hiding or under-disclosing; it's about
which parts of the story lead the *pitch* versus which parts are disclosed
factually where asked. `docs/proposals/nlnet-restack-form-answers.md`'s
rewritten field drafts (below) already follow this: the abstract,
budget-use, and comparison sections describe the engine and the audit work
on their own terms, without foregrounding "built by an AI agent" as the
headline; the AI-disclosure section carries the actual, required
disclosure and nothing is misrepresented.

### CodeSupply — investigated and ruled out (2026-09-17)

Filippo asked whether CodeSupply might also be worth targeting. Checked
directly against NLnet's own CodeSupply pages (not a third-party guide,
unlike the original September assessment): CodeSupply is a pilot
programme specifically about **software supply-chain metadata** —
"publishing current, correct, and comprehensive software metadata,"
building "a scalable and sustainable mechanism to provide democratic
access to [metadata] data sets" (SBOM/license-compliance-adjacent
infrastructure, at ecosystem scale). Neither pyvar's product (financial
risk computation) nor the grant-funded audit work (a security review and
a numerical/regulatory-formula audit of *one* project) is a metadata-
publishing effort in that sense — publishing pyvar's own SBOM as a
CodeSupply application would be a thin, unconvincing stretch that doesn't
draw on anything pyvar uniquely offers. **Confirms the original
recommendation: Restack only, not a second CodeSupply submission** — same
deadline, same budget band, genuinely different theme, and splitting
effort across a submission that doesn't fit risks diluting the Restack
pitch's credibility rather than adding a second real chance.

## 4. What only Filippo can do

1. ~~Verify the exact 6 question texts~~ — resolved 2026-09-17: the real
   form fields are now confirmed directly from NLnet's own HTML (§3a
   table above), not a third-party guide's guess.
2. ~~Confirm targeting Restack over CodeSupply~~ — resolved 2026-09-17:
   CodeSupply checked directly against NLnet's own pages and ruled out
   (§3a) — it's a supply-chain-metadata programme, not a fit. Restack only.
3. ~~The AI-authorship framing call~~ — resolved 2026-09-17 (§3a): combine
   reframing the pitch around the audit work + minimized AI-build framing
   in the application narrative, full honest disclosure where the form
   requires it.
4. ~~Pick a specific amount~~ — resolved 2026-09-17, in two passes: Fibtec
   Limited applies (not an individual); rate initially set at €100/hour
   (→€27,200), then corrected to **€150/hour** (→**€40,800**) across the
   four milestones (breakdown in the answers doc). Day-counts per
   milestone are still my estimate, not Filippo-confirmed line by line —
   adjustable before submission. Worth a deliberate look: €40,800 sits at
   ≈82% of the €50,000 cap, a real choice for a first-grant ask, not a
   neutral default.
5. ~~Decide `entity` field value~~ — resolved 2026-09-17: **Fibtec
   Limited** (SME company), not Individual.
6. ~~The "not the only developer" point~~ — resolved: refers to Riccardo
   Fei's early contributions, via branches since deleted. Filippo
   confirmed this isn't critical, so it isn't named in the application
   text — see the answers doc's "Experience" section, now filled with
   Filippo's own LinkedIn-sourced background instead.
7. **Actually submit** — a funding-body submission under Fibtec's identity
   is not something I should do on your behalf, technical feasibility
   aside, same reasoning as the Partner Hub forms earlier.

## 5. What I can do once the above is confirmed

- ~~Draft condensed answers to each real form field~~ — done 2026-09-17,
  rewritten against the actual field set in
  `docs/proposals/nlnet-restack-form-answers.md` (the old 3-question draft
  is superseded, not just edited).
- Fix the MIT/Apache and repo-visibility staleness in the source `.docx`
  itself for the record, even though the real submission will be the short
  form — keeps `docs/proposals/` internally consistent with everything
  else this session has corrected.
- Update `docs/proposals/README.md`'s one-line description of the NLnet
  brief once the fund name is confirmed as Restack.
- Add a proper GenAI-use disclosure statement to `README.md` — the framing
  call (§3a) is resolved (factual disclosure, not a lead narrative), so
  this is now just execution: still not yet drafted/committed.
- Draft the AI-disclosure section's prompt-provenance content once
  Filippo confirms how it should be compiled (this session's own
  transcript, or a separate log Filippo maintains).

## 6. Timeline

Deadline **2026-11-03**, ~7 weeks from today. Not urgent today, but real —
worth actually scheduling rather than letting it drift, unlike the
previous version of this brief which had no concrete date to work
against at all.

## 7. Definition of done

- The 6 real form questions are confirmed verbatim.
- Short-form answers exist, drawn from and consistent with the existing
  brief's verified claims (no new unverified numbers introduced).
- The `.docx` source material is corrected (license, repo status, fund
  name) even if it's not the literal submission artifact.
- Filippo has submitted via the actual `nlnet.nl/propose/` form before
  2026-11-03.

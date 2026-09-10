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

## 4. What only Filippo can do

1. **Verify the exact 6 question texts** directly against
   `nlnet.nl/propose/` (blocked to this session's browsing) before
   drafting final answers — I have 3 of 6, paraphrased from a third-party
   guide, not NLnet's own copy.
2. **Confirm targeting Restack over CodeSupply** — my read is clearly
   Restack given the theme match, but it's your call, and worth a quick
   sanity check against `nlnet.nl/restack/` directly.
3. **Actually submit** — a funding-body submission under Fibtec's identity
   is not something I should do on your behalf, technical feasibility
   aside, same reasoning as the Partner Hub forms earlier.

## 5. What I can do once the above is confirmed

- Draft condensed, plain-English answers to each of the real form
  questions, pulling from the existing brief's already-solid content (the
  digital-commons/transparency/access arguments, the verified 385-function
  scope, the milestone-based work plan) but rewritten to the actual
  length/tone NLnet asks for — short and direct, not the longer prose
  style of the `.docx`.
- Fix the MIT/Apache and repo-visibility staleness in the source `.docx`
  itself for the record, even though the real submission will be the short
  form — keeps `docs/proposals/` internally consistent with everything
  else this session has corrected.
- Update `docs/proposals/README.md`'s one-line description of the NLnet
  brief once the fund name is confirmed as Restack.

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

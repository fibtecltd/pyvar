# LinkedIn adaptation — "What broke in the two weeks after launch"

**Draft status:** not yet published. Shorter standalone adaptation of
`pyvar-post-launch-lessons-medium-article.md`, same pattern as the first
article's LinkedIn version — post once the Medium piece is live and link to
it.

---

Two weeks after we open-sourced pyvar.com (built end-to-end with Claude Code), we turned the same "verify by running it" discipline on our own infrastructure. Here's what it found.

**1. A feature that shipped but never deployed.** A new daily email report merged, CI went green — and it never sent a single email, in either environment, for over a week. Why: the stack was added to our CDK app's standalone list, but never wired into the pipeline's actual deploy stage. A green pipeline and a deployed feature turned out not to be the same claim.

**2. A bug underneath that bug.** The database migration the feature needed had a second, independent problem: our pipeline's migration step ran against whichever task revision was already live — the previous deploy's image, not the one just built. A migration shipped in the same commit as the code needing it would silently never apply, while the pipeline reported a clean success. Fixed by registering and running the exact revision that commit just built.

**3. A cost number we'd been quoting wrong.** Our README said "~£126/month." That was a pre-launch planning target, never an observed cost. The real invoice: **$900–1,000/month** — more than double, and dominated by fixed infrastructure, not job volume (compute itself runs at sub-cent per scenario even at a million scenarios a month).

**4. A partner-program lesson.** Our Claude Partner Network application got declined as a "Customer Story" for the right reason — we don't have a named third-party customer, because pyvar is open to everyone by design. The real fit was a **Public Case Study**, a distinct submission shape for exactly that situation. Knowing the difference before applying saves a round trip.

None of these were caught by review. They were caught by checking whether things actually worked, after they shipped — which is the only verification that scales past a launch date.

Full write-up (with the receipts): [link once published]

#OpenSource #AWS #ClaudeCode #FinTech #RiskManagement

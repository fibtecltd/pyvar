# What Broke in the Two Weeks After Launch (and What a Stale Cost Estimate Taught Us About Our Own Infrastructure)

*A follow-up to "How We Built a Regulatory-Grade Financial Risk Platform End-to-End with Claude Code" — same discipline, turned on the two weeks since publication instead of the build itself.*

> **Draft status:** not yet published. Every number below is checked against
> this repository at drafting time (`CHANGELOG.md`, `git log`, `README.md`,
> `docs/known-issues.md`) — see **Sources** at the end. Needs your review
> before it goes anywhere.

---

Our first article ended on a deliberately modest note: no named enterprise customers yet, and the next real chapter would be "checkable the same way everything above was — `git log`, PyPI, the live API, not a slide deck." Two weeks and seven merged pull requests later (`#326`–`#332`), that's exactly the standard we're holding this follow-up to. Not a highlight reel — a look at what the same "verify by running it" discipline caught in our *own* infrastructure this time, including one bug that shipped, ran silently wrong for over a week, and only surfaced because someone went looking.

## The bug: a feature that never actually deployed

PR #328 added a small, useful thing: a daily email report of JWT token issuance, `TokenReportStack` — a per-environment scheduled Lambda that queries a new `users.verified_at` column and emails the count to `info@pyvar.com` every morning.

It merged. CI went green. Nothing in the pipeline complained.

It also never once sent an email, in either environment, because it was never actually deployed. The stack had been added to `pyvar-cdk/app.py`'s list of standalone stacks — the ones you can `cdk deploy` by hand — but never wired into `PyvarDeployStage`, which is the object the *pipeline* actually walks on every run. The pipeline had no idea `TokenReportStack` existed. A green pipeline run and a deployed feature are not the same claim, and this is exactly the gap between them.

That alone would be a clean, boring bug-and-fix story. What made it worth writing about is what it was standing next to: a second, older bug that had been there all along, waiting for a commit like this one to trigger it.

## The bug underneath the bug

`TokenReportStack` needed a migration — `0006_user_verified_at`, adding the column the report queries. The migration step in the pipeline runs `ecs run-task --task-definition <family-name>`, which resolves to whichever task-definition revision is currently marked ACTIVE in ECS.

Here's the problem: that step runs *before* the same pipeline stage's `ApiStack` deploy registers the new revision pointing at the image this exact pipeline run just built. So "the currently ACTIVE revision" means *last* run's image — the one built before this commit existed — not the one that actually needs the new column.

A migration introduced in the same commit as the code that depends on it silently never applies. The pipeline reports success. The application code ships. The column it expects doesn't exist. This is worse than a loud failure, because a loud failure gets noticed.

`0006_user_verified_at` hit this exactly — confirmed missing in both dev and prod, despite a fully green pipeline history. The fix: instead of running the bare family name, clone the family's current task definition with only the image swapped to the one this run just built, register that as a one-off revision, and run that specific revision ARN. The next migration that ships alongside its own feature commit will actually see the column it's adding.

A third bug turned up in the same investigation, smaller but worth a line: `TokenReportStack`'s Lambda still couldn't send email even once deployed correctly — `ses:SendEmail` came back 403 against the SES configuration-set resource, despite the identity-level `grant_send_email()` already being in place. AWS wants a second, separate grant against the configuration set itself whenever an identity has one attached as its default. This is the same gap `api_stack.py`'s ECS task role had already hit and documented once before — the kind of thing that's obvious in hindsight and invisible until you hit it a second time.

None of these three were caught by code review. They were caught by checking whether the feature actually worked in the deployed environment, not by trusting that green CI meant it did.

## The cost number we'd been quoting wrong

Separately: our README had been advertising **"~£126/month at 500 jobs/day"** as pyvar's AWS running cost. That number was never an observed cost. It was a pre-launch planning *target*, written down in `docs/pyvar_release_plan.md` before a single real job had run against real infrastructure, and it stayed in the README long after launch made it checkable.

The real, confirmed prod AWS invoice (2026-08-31) is **$900–1,000/month**.

More than double the old figure, in a different currency, and — this is the part actually worth knowing if you're costing out infrastructure like this — job volume barely moves it. A dedicated audit (`docs/p9-scenario-volume-cost-audit.md`) found Monte Carlo compute itself running at roughly sub-cent per scenario even at 1,000,000 scenarios a month. The real cost driver is the fixed baseline: VPC interface endpoints, the NAT gateway, ElastiCache, Aurora's floor capacity, Fargate's always-on base tasks — infrastructure you pay for whether one job runs or a million do.

That's the correction, and it's also the more useful fact underneath it: if you're estimating what a service like this costs to run, the question that matters isn't "how many requests will we get" — it's "what's the fixed floor, and how much of our budget does that alone commit us to before a single customer request arrives."

## A partner-program story with a twist

We'd applied to Anthropic's Claude Partner Network as a "Customer Story" — a case study naming a customer who'd built success on Claude. It came back declined, for a precise and correct reason: **"the customer is not named; anonymous stories cannot count as public references."**

That's a fair rule, and also not quite our shape. There isn't a third-party customer to name here, because pyvar.com doesn't have one — it's Apache-2.0 and open to everyone by design. Anthropic Partner Support's follow-up pointed us to the actual right track: a **Public Case Study**, the same submission form, used when there's no named third-party customer and the roles look different — Fibtec as the Partner, Claude Code as the Product that built pyvar.com end-to-end, and the open pyvar.com community itself as the Client.

We resubmitted with that framing made explicit, plus the three public references (the live product, the source repository, and our first article) and the measurable claim already in that article — pyvar's self-scored Iron Triangle efficiency score against traditional enterprise risk vendors — stated plainly instead of left implicit in narrative.

The useful lesson for anyone else building an open-source product with Claude: "Customer Story" and "Public Case Study" aren't two different forms, and knowing which one your project actually is before you submit saves a round trip.

## One almost-comedic footnote

While documenting all of the above, we nearly created a fresh instance of the exact class of problem this whole post is about. Our CD pipeline runs a full Test/Build/Dev-deploy cycle on every push to `master` unless the changed paths fall inside one of eight excluded top-level directories — a limit set by AWS CodePipeline's own hard cap on push-filter path entries, not a choice we made. `docs/` is one of the eight excluded directories. `CLAUDE.md`, sitting at the repo root, is not, and there was no room left on the list to add it.

Editing `CLAUDE.md` itself to record this quirk would have started the very pipeline execution the note was describing. Caught before merge, and moved to `docs/known-issues.md` instead — which is why that particular gap lives there rather than in `CLAUDE.md` proper, and why its own header explains exactly why.

Low-stakes, bounded (the in-pipeline skip-gates no-op when nothing deploy-relevant changed, and Prod sits behind a required manual approval regardless), and left as an accepted low-frequency cost rather than a fix — but a nice, small demonstration that "verify by running it" catches things you didn't set out to look for.

## What actually shipped, checkable today

- **Seven merged PRs since the first article** (`#326`–`#332`): the Sentry noise fix, the JWT report feature and its two deploy bugs, the CHANGELOG backfill, the cost/contact corrections, this session's own roadmap-and-marketplace work, and the market-data-adapter groundwork.
- **`v0.2.0`** — tagged and published as a real GitHub Release (2026-09-08), with an actual changelog, closing a gap where the release process itself had gone quiet since `v0.1.0`.
- **The README's cost line now reads $900–1,000/month**, sourced to a real invoice, not a pre-launch target.
- **The Partner Network resubmission**, framed correctly this time, sent.

## Why this one matters

The first article's thesis was that verification thorough enough to publish becomes cheap enough to actually do, when an AI agent is doing the heavy lifting. This one is the same thesis pointed at ourselves, two weeks later: a feature that looked shipped wasn't, a cost figure that looked current wasn't, and a partner submission that looked complete wasn't the right form. None of these were caught by anyone reading the code and nodding. They were caught by someone going back and actually checking — which is, not coincidentally, the only thing that scales past a launch date.

---

## Sources

- `CHANGELOG.md` (this repo) — `[0.2.0]` and `[Unreleased]` sections, quoted directly above.
- `git log`, PR `#326`–`#332` (this repo / GitHub) — commit history and merged-PR range since the first article's publication commit.
- `README.md` (this repo) — current AWS cost line and tech-stack summary.
- `docs/p9-scenario-volume-cost-audit.md` (this repo) — the cost breakdown and the sub-cent-per-scenario finding.
- `docs/known-issues.md` (this repo) — the CodePipeline push-filter top-level-file gap.
- `docs/partner-hub-public-case-study-resubmission-email.md` (this repo) — the Partner Network resubmission text.
- GitHub Releases, `fibtecltd/pyvar` — `v0.2.0` (published 2026-09-08), `v0.1.0` (published 2026-08-23).
- `docs/publications/pyvar-buildstory-medium-article.md` (this repo) — the first article this piece follows up on.

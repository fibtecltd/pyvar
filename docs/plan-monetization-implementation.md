# Plan: monetization strategy implementation for pro/enterprise tiers

## 0. Executed this session — Phase A shipped

Decisions confirmed by Filippo: **Stripe** (test account already exists),
**Phase A only** (billing plumbing, no priority queue/extended retention
yet), **monthly-only, no trial**, **Enterprise stays manual** ("Contact us"
→ sales conversation → someone sets `tier="enterprise"` by hand).

Built and tested (`tests/test_billing.py`, 14 tests, all passing; full
existing suite — 991 tests — re-run clean, no regressions):

- `api/routes/billing.py` — `POST /billing/checkout` (JWT-authenticated,
  creates/reuses a Stripe Customer, returns a hosted Checkout URL),
  `POST /billing/webhook` (Stripe-signature-verified, `checkout.session.completed`
  → `tier="pro"`, `customer.subscription.deleted`/`invoice.payment_failed`
  → `tier="free"`), `GET /billing/checkout/complete` (session-ID-verified
  against Stripe's own API, issues a fresh JWT).
- `users.stripe_customer_id` (`migrations/versions/0007_user_stripe_customer_id.py`)
  — the join key every webhook event and the checkout-complete exchange use
  to find a pyvar user back from a Stripe event.
- `config.py`: `stripe_secret_key` / `stripe_webhook_secret` /
  `stripe_price_id_pro`, all optional — billing routes return 503 rather
  than erroring when unset, so this ships safely with no Stripe secrets
  configured anywhere yet.
- A real gap closed that wasn't in the original plan below: `TokenPayload`
  (`api/middleware/auth.py`) — and therefore `enforce_compute_rate_limit`'s
  tier check — is decoded entirely from the JWT's own embedded `tier`
  claim, never re-queried from the database. Flipping `users.tier` via the
  webhook does NOT retroactively change what an already-issued JWT is
  entitled to. `GET /billing/checkout/complete` is the minimum necessary
  bridge for that — symmetric with `GET /auth/verify`, the only other place
  this app issues a token — not a general-purpose login/refresh mechanism
  (this app still doesn't have one, deliberately, per `api/routes/auth.py`'s
  own "minimum viable" scope).
- `docs/proposals/pyvar-monetization-strategy.docx` — same MIT→Apache-2.0 +
  date staleness fix as every other proposal doc this session corrected.

**Update — Phase A fully closed, live deploy confirmed (2026-09-13):**

Wiring the three Stripe secrets into `pyvar-dev-api` took four PRs, not one,
because the first three attacked the wrong layer of the problem:

- **#337** wired the secrets via `execution_role` + ECS's native `secrets={}`
  (the same pattern as `DB_*`/`JWT_SECRET`) and created them in Secrets
  Manager. This made the ECS agent's own task-launch sequence — not just
  billing — depend on `secretsmanager:GetSecretValue` succeeding for a
  brand-new IAM grant.
- **#339** fixed a genuine CloudFormation ordering bug (the ECS service had
  no dependency edge on the IAM policy resource the grant attached to), but
  redeploying still hit an `AccessDeniedException` — CFN completing the
  `PutRolePolicy` call doesn't mean IAM's authorization cache has caught up
  yet.
- **#340** added a fixed 75s sleep to bridge that gap. CloudTrail evidence
  from the next failure proved this insufficient: the policy landed in IAM
  at 23:24:24Z, yet `GetSecretValue` still got `AccessDenied` at 23:34:46Z —
  over 8 minutes later, far outside typical IAM propagation behavior.
- **#341**'s first commit replaced the sleep with a poll-until-verified
  Lambda (assume `execution_role`, retry the real `GetSecretValue` call
  until it succeeds or ~800s elapses) — a correct fix for the *timing*, but
  still solving the wrong problem.
- **#341's actual merged fix** (a second commit, superseding the first)
  recognized the real bug: these secrets never belonged on `execution_role`
  (the ECS agent's task-launch identity) at all. `billing.py`'s
  `_require_billing_configured()` already 503s billing routes gracefully
  when unset — there was no reason to make the *entire container's ability
  to launch*, including every regulatory VaR/ES/Greeks endpoint, hostage to
  IAM propagation timing for a secret only billing touches. This is the
  exact same class of bug PR #229 already found and fixed for `SENTRY_DSN`.
  Fix applied: `grant_read(task_role)` instead of `execution_role`, the
  three `STRIPE_*` entries removed from `secrets={}` entirely, and fetched
  in-app at startup by `_resolve_stripe_secrets()` (called once from
  `main.py::create_app()`, mirroring `observability/setup.py`'s
  `_resolve_sentry_dsn()` exactly). A `cdk diff` against the real dev
  account confirmed the fix: exactly 3 new `Allow(GetSecretValue,
  DescribeSecret)` statements on `ApiTaskRole`, zero changes to
  `ApiExecutionRole`, and zero Lambda/Trigger/Custom-Resource machinery
  left anywhere in the stack — the entire #339–#341 apparatus is gone.

**Live deploy confirmed successful.** Phase A billing is now fully shipped
and running in `pyvar-dev-api` — Stripe Checkout, webhook, and
checkout-complete are live, secrets resolve at app startup, and the ECS
service reaches steady state with no circuit-breaker involvement.

Still open, not release-blocking:

1. A real end-to-end Stripe test-mode checkout run (Checkout redirect →
   webhook delivery → tier flip → `GET /billing/checkout/complete` issuing
   a working new JWT) hasn't been manually exercised yet — worth doing
   once for confidence, though every step is now unit-tested individually.
2. See §8 below — **metering, usage, and billing-lifecycle event handling**
   (payment declines, limit overages, notifications) is real, scoped-out
   follow-on work, not part of Phase A's original definition of done.

---


**Item 5 of 6** in `docs/roadmap-six-open-initiatives.md`. Ranked high
complexity: real engineering (payment processing, a self-serve upgrade
flow) with live revenue and compliance implications, plus genuine open
business decisions only Filippo can make. This plan stops short of writing
payment-integration code — that needs the decisions in §4 answered first.

## 1. What "strategy" already covers, verified against
`docs/proposals/pyvar-monetization-strategy.docx`

An open-core/commercial-support model (the Red Hat/GitLab/Elastic shape):
free tier stays free and full-featured forever; revenue comes from Pro
subscriptions, Enterprise contracts, `pyvar Local` (item 2), grants (item
4), and professional services. Same MIT-staleness issue as every other
proposal doc this session has found — flagged, not re-detailed here.
**Pricing figures are explicitly placeholders** ("£X") in the source
document — it says outright that real numbers need "a short
willingness-to-pay conversation with early Pro-tier candidates" first.
That's not a gap I can fill by guessing.

## 2. What's actually implemented today, verified against the running code

More exists than "strategy only" — the tier *enforcement* mechanism is
real and working:

- `storage/models.py`'s `User.tier` column (`free`/`pro`/`enterprise`/`internal`,
  default `"free"`) and a matching `tier` column on `var_jobs`, explicitly
  "denormalised for billing queries" per migration `0002_users_and_tier.py`'s
  own docstring — this schema was already built anticipating billing, even
  though nothing consumes it for billing yet.
- `api/middleware/rate_limit.py`'s `enforce_compute_rate_limit`: `free` gets
  `rate_limit_free_daily` (10/day), `pro` gets `rate_limit_pro_daily`
  (500/day), and `enterprise`/`internal` are fully exempt
  (`_EXEMPT_TIERS = {"enterprise", "internal"}`). This is a real,
  functioning three-way differentiation, not a stub.
- `config.py`'s simulation-count caps (`default_n_simulations`,
  `max_n_simulations`) are similarly tier-aware by design (comments
  reference "the lowest tier cap" / "the highest tier cap").

## 3. What's missing — the actual engineering gap "implementation" means

1. **No way for anyone to become `pro` or `enterprise`.** Grepped for any
   endpoint, admin action, or webhook handler that writes to `User.tier` —
   found none beyond the schema default. Today, becoming Pro would require
   a direct database write. This is the single biggest gap between "the
   strategy exists" and "the tiers generate revenue."
2. **No payment/billing integration at all** — no Stripe, no invoicing, no
   payment provider of any kind anywhere in the codebase (the earlier grep
   hits for "billing"/"payment" were all false positives from bond/loan
   *payment* schedules in the financial engine itself, not a commercial
   billing system).
3. **The Pro-tier perks beyond rate limiting aren't built.** The strategy
   doc describes "priority queue placement for the async Monte Carlo VaR
   pipeline" and "result retention beyond the default TTL" as Pro
   features — zero hits for either in `tasks/`, `storage/`, or `api/`.
   Today, Pro's *only* real differentiation is the higher daily rate cap.
4. **Enterprise is sales-assisted, not self-serve, by nature** — "private
   VPC deployment, custom SLA, dedicated support" isn't a checkout-button
   feature; it needs a human sales conversation regardless of what gets
   built. Worth keeping that path manual rather than trying to automate it.

## 4. Real open decisions — need Filippo, not more code archaeology

1. **Actual pricing.** The strategy doc is explicit that this needs real
   conversations with candidate Pro users first — I have nothing to base
   numbers on that wouldn't be fabricated.
2. **Payment provider.** Not chosen anywhere in the repo. Stripe (Billing +
   Checkout) is the standard choice for a usage-tiered SaaS API and fits
   the codebase's existing security posture well — Stripe Checkout is a
   *hosted* page, so pyvar's own infrastructure never touches card data
   (PCI SAQ-A scope, not SAQ-D) — consistent with CLAUDE.md §3.4's "all
   secrets come from Secrets Manager, never hardcode credentials"
   discipline. This is my recommendation, not a decision already made —
   confirm before I build against it.
3. **Scope for a first cut.** Given #3 above, there's a meaningful
   difference between:
   - **Phase A (billing only):** wire up Stripe Checkout + webhook so a
     user can actually subscribe and get flipped to `pro`, using the
     *existing* rate-limit differentiation as the entire Pro value
     proposition for now.
   - **Phase B (the fuller Pro feature set):** also build priority queue
     placement and extended result retention before or alongside billing.

   Phase A is a much smaller, faster, lower-risk slice that makes the tier
   system *commercially real* immediately; Phase B is real additional
   engineering in `tasks/var_task.py` (priority queue semantics — SQS FIFO
   doesn't have native priority, so this needs a design, not just a
   config flag) and `storage/`. **Recommendation: Phase A first**, ship
   Phase B once there's real Pro revenue to justify the investment — but
   this is your call given it's a product-sequencing decision, not a
   purely technical one.
4. **Enterprise's actual workflow.** Likely just: a "Contact us" link to
   `fibtec.co.uk` (already on the homepage) leading to a manual sales
   conversation, ending in someone manually setting `tier="enterprise"` —
   confirm that's the intended shape rather than something more automated.

## 5. What I can do once the decisions above are answered

- Design and implement the Stripe Checkout + webhook flow (new
  `api/routes/billing.py`, a webhook handler updating `User.tier`,
  `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` added to `config.py`'s
  pydantic-settings pattern and Secrets Manager, per existing convention).
- Add tests following the repo's own rules (mock the Stripe SDK the same
  way `test_api.py` already mocks Celery dispatch — never call a real
  payment API in tests).
- A new Alembic migration if the `User` model needs a `stripe_customer_id`
  column (needed to reconcile webhook events back to a pyvar user) —
  following §3.3's migration discipline.
- Update the monetization strategy doc's MIT/date staleness alongside
  this, same as every other proposal doc corrected this session.

## 6. What this plan deliberately does not do

Doesn't write payment-integration code yet — that's real, security-relevant
engineering that shouldn't start until §4's decisions (provider, phase
scope, pricing-adjacent questions like trial periods or annual-vs-monthly)
are actually answered, not assumed.

## 7. Definition of done (for Phase A, once scoped)

- A user can subscribe via Stripe Checkout and their `tier` flips to `pro`
  automatically via webhook, without any manual DB write.
- Failed/cancelled/refunded payments correctly flip `tier` back to `free`
  — not just the happy path.
- No payment credential or card data ever touches pyvar's own
  infrastructure (Stripe-hosted Checkout, not a custom card form).
- Tests mock Stripe entirely; CI never calls a real payment API.
- Enterprise remains a manual, sales-assisted path — not silently
  automated as a side effect of building Pro's flow.

## 8. Follow-on scope — metering, usage, and billing-lifecycle events

Raised by Filippo once Phase A's live deploy was confirmed: "we need to
meter accesses, usages, payments, exceptions properly" and handle scenarios
like a declined payment or a Pro user exceeding their limits — both should
switch the account to `free`, log the event, and notify the user. This is
real, scoped-out follow-on work, not part of Phase A's original definition
of done — the sections below separate what already exists from what's
genuinely missing, and flag the decisions that need answering before any
of it gets built.

### 8.1 What's already defined — the free/pro/enterprise limits

Confirmed by reading the actual enforcement code (`api/middleware/auth.py`,
`api/middleware/rate_limit.py`, `config.py`) — these are real and live
today, not proposals:

| Limit | free | pro | enterprise / internal |
|---|---|---|---|
| Daily request quota, all `/api/v1` compute endpoints combined (`rate_limit_{free,pro}_daily`) | 10/day | 500/day | unlimited (exempt) |
| Max `n_simulations` per single VaR request (`TokenPayload.max_simulations`) | 10,000 | 100,000 | 500,000 |

Both are enforced today: the daily quota returns `429` (retryable next day)
via `enforce_compute_rate_limit`; the per-request simulation cap is
presumably validated against `schemas/var.py`'s `VaRRequest` (not
re-verified in this pass — worth a quick confirmation before relying on it
for the scenarios below). **There is no monthly usage concept anywhere** —
only the daily quota above.

### 8.2 What already handles part of the "payment declined" scenario

More than Filippo may realize is already live: `stripe_webhook`
(`api/routes/billing.py`) already flips `tier` to `free` **immediately and
automatically** on `invoice.payment_failed` (a declined renewal charge) or
`customer.subscription.deleted` — this is `_DOWNGRADE_EVENTS`, shipped in
Phase A. It also already logs the event: `logger.info("stripe_webhook_tier_updated", event_type=..., customer_id=..., new_tier=...)`.

**What's missing from that scenario, specifically:**
- **No user notification.** The downgrade happens silently from the
  user's perspective — no email saying "your payment failed, you're back
  on Free." SES sending infrastructure already exists (`ses_identity`,
  used today for verification emails) — this is a wiring gap, not new
  infrastructure.
- **The "log" is an application log line (CloudWatch), not a persisted,
  queryable audit record.** Fine for debugging; not obviously fine as a
  durable record of "this account was downgraded on this date for this
  reason" if that ever needs to be looked up outside CloudWatch's
  retention window, shown to the user in an account history, or
  referenced in a support/billing dispute.

### 8.3 What's genuinely missing — "Pro user exceeding limits for the month"

This scenario doesn't map to anything that exists today, and needs a real
decision before it can be built:

- Today, exceeding the daily quota (500/day for Pro) returns `429` and
  simply resets the next day — it never touches `tier`.
- A **monthly** usage concept doesn't exist in the schema or enforcement
  layer at all. `ApiUsage` (per-request log: domain, function, tier,
  duration, status, timestamp) and `VaRJob` (per-job log, includes
  `n_simulations`) both already capture the raw data a monthly rollup
  would need — but nothing aggregates it, and nothing acts on it.
- **Open question, needs Filippo:** what should "exceeding limits for the
  month" actually mean, and is downgrade-to-free really the intended
  response? A few real shapes this could take, each with different
  product/revenue implications:
  1. A genuinely separate **monthly** cap (e.g. "500/day, but also capped
     at N/month") — distinct from and tighter than 30× the daily cap.
  2. The existing daily cap simply hit repeatedly through the month, with
     no new monthly concept — in which case "exceeding limits" already
     happens today (as 429s) and the only real ask is the
     notify-and/or-downgrade *reaction* to a pattern of repeated hits, not
     a new limit.
  3. Downgrading a **paying** customer to Free for using their paid plan
     heavily is an unusual SaaS pattern — most products instead hard-cap
     (keep blocking with 429 until the period resets) or charge overage,
     precisely because auto-demoting an engaged, paying user reads as a
     punishment and produces a support ticket + a annoyed customer once
     they can't get warned in advance. Worth confirming this is really
     the intended shape rather than assumed from the phrasing.

### 8.4 Proposed scope, pending the decisions above

Once 8.3's question is answered, the shape of the work is otherwise clear
and low-risk to build (all additive to existing, already-tested code):

1. **A dedicated billing-event audit table** (new Alembic migration,
   `BillingEvent` or similar: `user_id`, `event_type`, `old_tier`,
   `new_tier`, `reason`, `stripe_event_id`, `created_at`) — durable,
   queryable record of every tier change and why, superseding "check
   CloudWatch" as the only way to answer "why did this account change
   tier." Every existing tier-flip site (webhook handler, and any new
   monthly-limit logic) writes one row.
2. **User notification on tier change** — a new SES send (mirroring
   `send_verification_email`'s existing pattern exactly: same identity,
   same configuration set, same graceful-degrade-on-failure posture) fired
   from the same places that write a `BillingEvent` row. Needs a decision
   on content/tone per scenario (payment declined vs. subscription
   cancelled vs. limit exceeded are different messages) — draftable once
   8.3 is answered.
3. **If 8.3 resolves to "a real monthly cap exists"**: a scheduled check
   (Celery beat task or similar, not inline on every request — a monthly
   aggregate query on every hot-path request would be real added latency)
   that rolls up `ApiUsage`/`VaRJob` per user per billing period, compares
   against the new cap, and on breach writes the `BillingEvent` + fires
   the notification + flips `tier` (only if that's really the agreed
   reaction — see 8.3.3 above).
4. **Exception/edge-case scenarios worth enumerating explicitly before
   implementation, once the shape is agreed** (not exhaustive — a fuller
   list belongs in a dedicated plan doc once 8.3 is answered, not guessed
   here): a Stripe webhook retry re-delivering an already-processed event
   (idempotency — check the current handler's behavior on a duplicate
   `event.id`, not verified in this pass); a user re-subscribing after a
   payment-failure downgrade (does a fresh `checkout.session.completed`
   correctly re-upgrade even though `stripe_customer_id` is already set?);
   a subscription paused/resumed by Stripe itself (not currently in
   `_DOWNGRADE_EVENTS` — worth checking whether Stripe emits a distinct
   event for "paused" vs. "cancelled" and whether pyvar should treat them
   differently); what happens to `total_jobs`/`total_simulations` history
   on downgrade (kept, presumably — nothing here proposes deleting audit
   data, consistent with §3.3's "VaRJob is an audit log, never delete
   rows" rule extending in spirit to billing history too).

This section intentionally stops short of a full plan doc + code — §8.3's
question is a real product decision, not something to answer by guessing,
and the rest of the design (audit table shape, notification content,
whether a monthly cap is even the right lever) follows directly from it.

## 8.5 Built and shipped

§8.3's questions answered by Filippo: **hard block, not overage** (a Pro
account that breaches a monthly cap is downgraded to Free's limits for the
rest of the period, never charged extra); **both** a request-count cap and
a simulation-count cap, tracked separately, whichever is breached first;
**leave the Stripe subscription running and auto-restore Pro at the next
successful payment** rather than cancelling it or leaving a billing
mismatch. The simulation-count cap is scoped to VaR Monte Carlo only
(`VaRJob` is the only endpoint family with a per-user simulation-count
record today — extending that to the other 385 endpoints is separate,
larger, out-of-scope work).

Built and tested (20 new tests — `tests/test_billing_lifecycle.py` +
additions to `tests/test_rate_limit.py`, `tests/test_api.py`,
`tests/test_billing.py`; full 1,733-test suite re-run clean):

- **`api/middleware/billing_lifecycle.py`** (new) — shared module every
  tier-change site uses: `record_billing_event()` (writes a `BillingEvent`
  audit row in the same transaction as the tier mutation, never commits
  itself), `send_tier_change_email()` (best-effort SES notification,
  mirrors `send_verification_email`'s exact shape and non-fatal failure
  posture), `downgrade_for_monthly_limit()` (idempotent — a stale JWT
  retry against an already-downgraded account is a no-op, though the
  caller still rejects the request every time), and
  `restore_after_payment_succeeded()`.
- **Monthly request-count cap** (`api/middleware/rate_limit.py`) — a
  second `limits` item (`rate_limit_pro_monthly_requests`, default
  5,000/month), Pro only, checked after the existing daily cap passes.
  Breaching it raises 403 (not 429 — a permanent-for-the-period state
  change, not "retry later today") and downgrades via
  `billing_lifecycle.downgrade_for_monthly_limit()`.
- **Monthly simulation-count cap** (`api/routes/var.py`) — same shared
  Redis-backed limiter, a second item
  (`rate_limit_pro_monthly_simulations`, default 2,000,000/month) hit with
  `cost=body.n_simulations` per request, Pro only. Same 403 + downgrade
  reaction.
- **`billing_events` table** (new, `0008_billing_events_and_downgrade_reason`)
  — durable, queryable audit trail (`user_id`, `event_type`, `old_tier`,
  `new_tier`, `reason`, `stripe_event_id`, `created_at`), append-only like
  `VaRJob`. `users.tier_downgrade_reason` (same migration) distinguishes
  "auto-downgraded, should restore on next successful payment" from
  "never subscribed" — the signal `invoice.payment_succeeded`'s handler
  needs that plain `tier == "free"` alone can't give it.
- **Stripe webhook** (`api/routes/billing.py`) — now idempotent against
  Stripe's at-least-once redelivery guarantee (checked against
  `billing_events.stripe_event_id` before acting — matters now that
  processing has side effects beyond the tier flip itself). Every tier
  change (upgrade, either downgrade path, and the new restore path) writes
  a `BillingEvent` and sends a notification, closing the "downgrade
  happens silently, only visible in CloudWatch" gap flagged in §8.2.
  New `invoice.paid`/`invoice.payment_succeeded` handling restores Pro for
  **any** account that isn't already Pro on a successful payment — not
  narrowly "was downgraded for a monthly limit specifically" — so an
  account previously downgraded for a *declined* payment also gets Pro
  back automatically once successfully rebilled (Stripe's own retry, or a
  fixed card), rather than staying stuck on Free until it starts a brand
  new Checkout. This is a deliberate, considered widening beyond what was
  strictly asked (only the monthly-limit case needed a restore path) —
  flagged here rather than done silently, since it changes behavior for
  the existing `invoice.payment_failed` downgrade too, in a direction that
  seemed clearly correct (a customer who successfully pays again should
  get Pro back) but wasn't explicitly confirmed.

**Deliberately not done:**

- §8.4's edge-case list (Stripe "paused" vs "cancelled" events, exact
  interaction with `total_jobs`/`total_simulations` history) — none
  surfaced as blocking during implementation, but weren't independently
  re-verified either.
- The two monthly caps' exact numeric values (5,000 requests / 2,000,000
  simulations) are placeholders, same "no verified traffic data yet"
  caveat as the existing daily caps in `config.py` — retunable with no
  code change.
- A real end-to-end test-mode run of a monthly-limit downgrade against
  the live Stripe account (webhook idempotency, the restore path, and the
  notification emails are all unit-tested individually, but not chained
  together against real Stripe events).

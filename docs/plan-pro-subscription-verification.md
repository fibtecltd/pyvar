# Test plan: Pro subscription enrollment and limit enforcement

> **Rewritten 2026-11-21 (docs/plan-pro-tier-stripe.md).** Tests 4 to 8 described the old behaviour: a monthly cap moved a
> Pro account to Free, a failed payment moved it to Free at once, and a paid invoice restored it. The owner replaced all
> three: a monthly cap is a 429 that names the cap; a failed payment changes nothing (Stripe retries); only the end of the
> Stripe subscription, `customer.subscription.deleted`, moves Pro to Free. The tests below check that. The Free daily limit
> is 20 (it was 10 when this plan was written). Tests 1 and 9 were executed on dev on 2026-09-29/30 (section 15).

**Purpose.** `tests/test_billing.py` (22 tests), `test_billing_lifecycle.py`
(11 tests), and `test_rate_limit.py` (21 tests) already cover every code
path in isolation — Stripe and the DB are both mocked, per `CLAUDE.md`
§5's testing rules. What they can't cover, by design, is whether the real
integration actually works end-to-end: a real Stripe Checkout session, a
real webhook delivery, a real Redis-backed rate-limit counter surviving
across Fargate tasks. This plan is that end-to-end pass — the same
"verify by running it" discipline the rest of this project is built on,
applied to the billing/limits system specifically.

**Scope.** Stripe **test mode only** (`sk_test_...`/`pk_test_...` keys —
never live keys), against a **dev environment**, never prod. Nothing here
should touch real money or real customers.

---

## 1. Prerequisites (needs Filippo)

- Stripe test-mode keys (`stripe_secret_key`, `stripe_webhook_secret`,
  `stripe_price_id_pro`) configured for the dev environment — same three
  settings `api/routes/billing.py`'s `_require_billing_configured()`
  checks; without them every billing route 503s.
- A way to receive webhooks in dev: either the Stripe CLI
  (`stripe listen --forward-to https://dev.pyvar.com/api/v1/billing/webhook`)
  or a Stripe-dashboard-configured webhook endpoint pointed at dev.
- A **Stripe test clock** (Stripe Dashboard → Developers → Test clocks, or
  the API) — the only realistic way to exercise monthly-cycle billing
  logic without waiting a real month. Attach the test customer created
  below to it.
- Stripe test card numbers: `4242 4242 4242 4242` (always succeeds),
  `4000 0000 0000 0341` (succeeds on attach, **fails on the next charge**
  — the card for testing renewal failure), any future expiry, any CVC.
- A throwaway test user registered via the normal flow (§2 below), not a
  real account.

## 2. Test 1 — Enrollment happy path

1. `POST /api/v1/auth/register` with a test email → `202`.
2. Click the emailed verification link (`GET /api/v1/auth/verify?token=...`)
   → confirm response is `{"access_token": ..., "tier": "free"}`.
3. `POST /api/v1/billing/checkout` with that token → confirm
   `{"checkout_url": "https://checkout.stripe.com/..."}`.
4. Open the URL, pay with `4242 4242 4242 4242`.
5. Confirm Stripe redirects to
   `.../dashboard.html?checkout_session_id=cs_...`.
6. `GET /api/v1/billing/checkout/complete?session_id=cs_...` → confirm
   `{"access_token": ..., "tier": "pro"}` — a **different** token than
   step 2's, with the new tier claim actually baked in (decode the JWT
   and check the `tier` claim directly, not just the response field).
7. Confirm server-side, directly against the dev DB: `users.tier = 'pro'`,
   `users.stripe_customer_id` set, and one `billing_events` row with
   `event_type` for an upgrade and a non-null `stripe_event_id`.
8. Confirm the notification email arrived (or, if SES isn't fully wired
   in dev, confirm `send_tier_change_email`'s attempt is logged —
   `api/middleware/billing_lifecycle.py`'s non-fatal try/except pattern
   means a send failure here must not fail the enrollment itself).

**Pass condition:** all of the above, especially step 6 — this is the
JWT-staleness bridge `api/routes/billing.py`'s own module docstring calls
out as the gap this route exists to close. If step 6 returns the old
tier, that bridge is broken.

## 3. Test 2 — Daily rate limit (Free: 20/day, Pro: 500/day)

1. As a **Free** user, make 20 calls to any `/api/v1/<domain>/<fn>`
   endpoint (they share one bucket — doesn't need to be the same
   function each time). Confirm all 20 succeed.
2. Make a 21st call. Confirm `429`, with a `Retry-After` header whose
   value is a plausible number of seconds until midnight UTC (the
   `/day` window), and body `{"detail": "Rate limit exceeded. Please
   retry later."}`.
3. Repeat with a **Pro** user at 500/501 calls (scripting this — 501
   sequential calls — is more practical than doing it by hand; time-box
   it, this is checking the boundary works, not load-testing).

**Pass condition:** the 429 fires at exactly N+1, not N or N+2 (an
off-by-one here would silently give users one extra or one fewer call
than the tier promises), and `Retry-After` is sane.

## 4. Test 3 — Per-call simulation cap (fails fast, no queuing)

1. As a **Free** user, `POST /api/v1/var/compute` with
   `n_simulations: 50000` (above the 10,000 Free cap). Confirm `403`
   with `"Your 'free' tier allows a maximum of 10,000 simulations.
   Requested: 50,000."` — and confirm via CloudWatch/worker logs that
   **no Celery task was ever dispatched** (the check in `api/routes/var.py`
   happens before `submit()`, so this should be instant, not a queued
   job that later fails).
2. Repeat at the boundary: `n_simulations: 10000` (exactly the cap)
   should succeed; `10001` should 403.
3. Repeat for Pro (100,000 cap) and, if an Enterprise test credential
   exists, confirm 500,000 is accepted and unbounded above isn't
   (Enterprise still has *a* ceiling, just a higher one — not truly
   unlimited).

## 5. Test 4 — Monthly request-count cap → refusal (the tier never changes)

`rate_limit_pro_monthly_requests` is 5,000 in real config — not practical to
hit with 5,000 real calls. **Temporarily** override it to a small number (e.g.
`3`) in the dev environment **only for this test window**, then revert. Dev
only, never prod.

1. With the override active, as a Pro test user, make 3 authenticated calls
   (any domain). Confirm all succeed and the daily cap (§3) isn't what is
   limiting them.
2. Make a 4th call. Confirm:
   - `429` with a `Retry-After` header and the message "Monthly limit reached:
     the Pro plan allows 3 requests in each 30-day window. Requests are refused
     until the window resets; ...".
   - `users.tier` is **still `'pro'`** and `tier_downgrade_reason` is `NULL`.
   - **No** `billing_events` row and **no** e-mail.
3. Make a 5th call from a *second API key of the same account*. Confirm it is
   also refused: both keys share one counter (the counter is keyed by the account).
4. Revoke one key and create another. Confirm the new key is still refused (the
   counter is the account's, not the key's).
5. Revert the config override. The window is 30 days from the first request in
   it, not the calendar month or the billing date: do not wait for it to reset.

## 6. Test 5 — Monthly simulation-count cap → refusal

Same approach as Test 4, but override `rate_limit_pro_monthly_simulations`
to something small (e.g. `150000` — two 100k-simulation Pro calls
should trip it) and drive it via `POST /api/v1/var/compute` specifically
(`api/routes/var.py`'s own check, not `rate_limit.py`'s generic one —
these are two separate code paths per `config.py`'s own comment on why
simulation-count tracking is VaR-specific). Confirm the same outcome as
Test 4 (429 naming "150,000 simulations in each 30-day window", tier
unchanged, no audit row, no e-mail) using the `cost=body.n_simulations`
weighted-hit mechanism rather than a flat per-call count.

## 7. Test 6 — A paid invoice changes nothing

On a Pro test account, advance the attached Stripe test clock to the next
billing date so the subscription's next invoice succeeds (card
`4242...`). Confirm the webhook receives `invoice.paid` /
`invoice.payment_succeeded` (only if the endpoint subscribes to them: it
should not) and that `users.tier` stays `'pro'` with no `billing_events` row.
Nothing is restored because nothing is taken away any more.

## 8. Test 7 — A failed payment does not end Pro

1. On a test clock, attach card `4000 0000 0000 0341` (succeeds on
   attach, fails on subsequent charge) to a Pro subscription.
2. Advance the clock to the next renewal so Stripe attempts the charge and it
   fails. (`invoice.payment_failed` is sent on every failed attempt, not only
   the last; the endpoint should not subscribe to it, and if it does the API
   ignores it.)
3. Confirm the account **stays Pro**: `users.tier = 'pro'`, no
   `billing_events` row, no e-mail from the API. Stripe's own failed-payment
   e-mail goes to the customer.
4. Advance the clock through Stripe's retries. Either a retry succeeds and
   nothing changes, or the retries run out and Stripe cancels the
   subscription (the dashboard setting is "cancel the subscription if all
   retries fail"): then `customer.subscription.deleted` arrives and Test 8
   applies.

## 9. Test 8 — Subscription end (cancellation, or retries run out)

1. In the **Billing Portal** (`POST /api/v1/billing/portal`, or the
   dashboard's Manage billing), cancel the subscription. Confirm the portal
   offers cancel **at the end of the billing period**, not immediately.
2. Confirm the account stays Pro until the period ends. Advance the test
   clock past the period end.
3. Confirm `customer.subscription.deleted` arrives and: `users.tier` flips to
   `'free'` with `tier_downgrade_reason = 'subscription_cancelled'`, one
   `billing_events` row (`downgraded_subscription_cancelled`), the e-mail,
   **the account and its keys stay** (no key revoked), and an API key now
   resolves to the Free limits (within the 60-second key cache).
4. A `customer.subscription.deleted` for an account that is *not* Pro
   (a stray Stripe customer on a Free, education or enterprise account)
   changes nothing.

## 10. Test 9 — Webhook idempotency

Using the Stripe CLI or dashboard's "resend webhook" feature, redeliver
any one event from Tests 1–9 a second time. Confirm:
- The response is still `200` (Stripe requires this regardless).
- **No** second `billing_events` row is written for that
  `stripe_event_id`.
- **No** second notification email is sent.

This matters specifically because Stripe's delivery guarantee is
at-least-once, not exactly-once — a redelivery during a network blip is
a real, expected occurrence in production, not an edge case.

## 11. Test 10 — Enterprise/internal exemption (light sanity check)

If an Enterprise or internal-tier test credential is available, confirm
it's genuinely never rate-limited by making a burst of calls well above
the Pro daily cap and confirming none 429. (Already asserted in
`test_rate_limit.py`'s mocks — this is a real-environment spot-check,
not a full pass.)

## 12. Safety notes

- Every step above uses Stripe **test mode**. Test-mode API keys and
  test-mode Dashboard objects (customers, subscriptions, test clocks)
  are entirely separate from live-mode data — nothing here can charge a
  real card or touch a real customer if the keys used are actually
  `sk_test_...`/`pk_test_...`. Confirm this before starting, not after.
- Any config override (Tests 4–5) is a **temporary, dev-only** change,
  reverted immediately after that test — never applied to prod's
  `rate_limit_pro_monthly_requests`/`_simulations`.
- Delete or archive test users/subscriptions/test-clocks created for
  this plan once done, so they don't linger in the dev Stripe account
  or dev DB indefinitely.

## 13. What only Filippo can do

- Everything above requires live access this session doesn't have:
  Stripe test-mode dashboard/API access, the ability to set dev
  environment config/secrets, and the ability to actually run these
  `curl`/webhook steps against a real deployed dev environment.
- Confirm whether SES is fully wired in dev (Test 1, step 8) or whether
  that step should just check the attempt is logged instead of a real
  inbox.

## 14. Definition of done

- All 10 tests above run at least once against dev with test-mode
  Stripe, with results (pass/fail, and the exact request/response for
  any failure) recorded somewhere durable — a follow-up to this doc, or
  inline here once run.
- Any bug found is filed and fixed before considering Pro enrollment
  "verified," not just noted and left open.
- Config overrides used for Tests 4–5 are confirmed reverted.

## 15. Executed — Test 1 (happy path) + Test 9 (idempotency), 2026-09-29/30

Run via `docs/stripe-smoke-test-delegated-agent-prompt.md`, a focused
slice of this plan rather than the full 10-test pass — specifically
targeted at re-verifying PR #367's webhook fix (`AttributeError` on
`event_object.get("customer")`, Sentry `afa9f2520c744907afa5d069149bfcbb`)
against a **real** Stripe webhook delivery, the exact gap that let the
original bug ship past CI (the old test fixture was a plain dict, which
masked it).

**Test 1 (enrollment happy path) — passed.** Register → verify → real
Stripe test-mode Checkout (driven through an actual headless-browser
session against the hosted Checkout page, not a synthetic
`stripe trigger` event) → `GET /billing/checkout/complete` returned
`tier: "pro"`, read straight from `users.tier`. CloudWatch logged
`stripe_webhook_tier_updated` with no `AttributeError` and no unhandled
exception — direct confirmation the fixed `getattr(event_object,
"customer", None)` path runs cleanly against a genuine webhook payload,
not just the unit-test mock.

**Test 9 (webhook idempotency) — passed.** Resending the same webhook
event logged `stripe_webhook_duplicate_event_ignored`; no second
`billing_events` row, no second tier update. Confirms Stripe's
at-least-once delivery guarantee can't silently grant a duplicate Pro
upgrade nobody paid for.

**Bonus coverage, not originally scoped**: cleanup (cancelling the test
subscription) exercised the pro → free downgrade path live as a side
effect, with no errors.

**Known real-environment gaps hit during this run** (informational, not
blocking — neither bears on the two results above):
- Dev Aurora is VPC-private with no bastion host (`compute_stack.py`'s
  own SSM-only design) and the dev Spot worker (the one EC2 instance
  with SSM access) was terminated at the time — no path existed to read
  `verification_token` directly from the DB. Worked around by having a
  human check a real inbox and relay the token instead (dev SES runs in
  production mode, so a real email is genuinely sent — this wasn't
  optional).
- The delegated agent's own sandbox initially couldn't launch Chromium
  (`libglib-2.0.so.0` missing, no root) — resolved without any elevated
  access by extracting the missing shared libraries from their `.deb`
  packages directly (`dpkg-deb`), not by installing them system-wide.
- **Cleanup incomplete**: two test user rows remain in the dev `users`
  table (one unverified, one downgraded back to `free` post-cleanup) —
  same DB-access gap as above. Needs a manual
  `DELETE FROM users WHERE email IN (...)` from someone with dev DB
  access; not urgent (dev-only, no PII risk beyond a throwaway test
  address) and deliberately not worth reopening DB/infra access
  (ECS Exec or an SSM tunnel) just to run one cleanup query.

**Remaining scope, unchanged**: Tests 2–8 and 10 (rate limits, per-call
simulation caps, monthly-cap auto-downgrade via a Stripe test clock,
payment-failure downgrade, subscription cancellation, Enterprise
exemption) are still unexecuted — this run was deliberately narrower
than the full plan, not a substitute for it.

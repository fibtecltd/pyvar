# Test plan: Pro subscription enrollment and limit enforcement

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

## 3. Test 2 — Daily rate limit (Free: 10/day, Pro: 500/day)

1. As a **Free** user, make 10 calls to any `/api/v1/<domain>/<fn>`
   endpoint (they share one bucket — doesn't need to be the same
   function each time). Confirm all 10 succeed.
2. Make an 11th call. Confirm `429`, with a `Retry-After` header whose
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

## 5. Test 4 — Monthly request-count cap → auto-downgrade (needs a test clock)

This is the one that needs care: `rate_limit_pro_monthly_requests` is
5,000 in real config — not practical to hit by making 5,000 real calls
in a test session. **Temporarily** override it to a small number (e.g.
`3`) via the dev environment's config **only for this test window**,
then revert — `config.py`'s own comment confirms these are
"retunable via config with no code change," so this is a supported
operation, not a hack. Do this in dev only, never prod.

1. With the override active, as a Pro test user, make 3 authenticated
   calls (any domain). Confirm all succeed and the daily cap (§3) isn't
   what's limiting them (stay under 500/day too).
2. Make a 4th call. Confirm:
   - `403` with the monthly-limit message
     ("Your Pro plan's monthly request limit has been reached...").
   - `users.tier` flips to `'free'` in the DB.
   - `users.tier_downgrade_reason` is the monthly-request-limit reason
     (`api/middleware/rate_limit.py`'s `DOWNGRADE_MONTHLY_REQUEST_LIMIT`).
   - A `billing_events` row is written for
     `EVENT_DOWNGRADED_MONTHLY_REQUEST_LIMIT`.
   - The notification email fires (or its attempt is logged).
3. Confirm the **already-issued Pro JWT** from before the downgrade
   still claims `tier: pro` when decoded (expected — JWTs aren't
   revoked), but the *next* request using it is evaluated against the
   now-`free` DB tier only once the client fetches a fresh token via
   `GET /billing/checkout/complete` — until then, `enforce_compute_rate_limit`
   is checking the **JWT's own tier claim**, not the DB, so document
   which one actually governs at this point (re-read
   `api/middleware/auth.py` if the two disagree — this is worth
   nailing down precisely during the test, not assumed).
4. Revert the config override.

## 6. Test 5 — Monthly simulation-count cap → auto-downgrade

Same approach as Test 4, but override `rate_limit_pro_monthly_simulations`
to something small (e.g. `150000` — two 100k-simulation Pro calls
should trip it) and drive it via `POST /api/v1/var/compute` specifically
(`api/routes/var.py`'s own check, not `rate_limit.py`'s generic one —
these are two separate code paths per `config.py`'s own comment on why
simulation-count tracking is VaR-specific). Confirm the same
downgrade/audit/email/reason (`DOWNGRADE_MONTHLY_SIMULATION_LIMIT`) triad
as Test 4, using the `cost=body.n_simulations` weighted-hit mechanism
rather than a flat per-call count.

## 7. Test 6 — Restore on next successful payment (test clock required)

Starting from a Test 4 or 5 downgraded account (`tier_downgrade_reason`
is one of the two monthly reasons):

1. Advance the attached Stripe test clock to the next billing date, so
   Stripe issues the subscription's next invoice and (with the
   `4242...` card still on file) it succeeds.
2. Confirm the webhook receives `invoice.paid` or
   `invoice.payment_succeeded`.
3. Confirm `users.tier` flips back to `'pro'`,
   `tier_downgrade_reason` clears to `NULL`, and a `billing_events` row
   is written for the restore.
4. **Negative case:** repeat starting from a `DOWNGRADE_PAYMENT_FAILED`
   or `DOWNGRADE_SUBSCRIPTION_CANCELLED` account instead. Confirm the
   *same* `invoice.paid` event does **NOT** restore Pro —
   `restore_after_payment_succeeded`'s own docstring says this is
   deliberate (those two need a fresh Checkout, not an incidental
   invoice event). This negative case is arguably more important to
   verify than the positive one, since it's the one place a bug would
   silently give away Pro access nobody paid for.

## 8. Test 7 — Payment failure downgrade

1. On a test clock, attach card `4000 0000 0000 0341` (succeeds on
   attach, fails on subsequent charge) to a Pro subscription.
2. Advance the clock to the next renewal so Stripe attempts (and, after
   exhausting its own retry schedule, gives up on) the charge.
3. Confirm `invoice.payment_failed` arrives, `users.tier` flips to
   `free` with `tier_downgrade_reason = DOWNGRADE_PAYMENT_FAILED`, audit
   row + email as before.
4. Confirm a later `invoice.paid` (e.g. if the test continues and a
   different card succeeds later) does **not** auto-restore this
   account (see Test 6's negative case — same rule, different trigger).

## 9. Test 8 — Subscription cancellation

Cancel the test subscription directly in the Stripe dashboard (or via
API) rather than letting it lapse. Confirm `customer.subscription.deleted`
arrives and produces the same downgrade triad with
`DOWNGRADE_SUBSCRIPTION_CANCELLED`.

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

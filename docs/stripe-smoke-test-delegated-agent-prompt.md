# Stripe smoke test — delegated agent prompt (dev environment, test mode only)

You have AWS credentials for the Fibtec dev account. I need a focused
smoke test of pyvar's Stripe billing flow against the real deployed dev
environment (`https://dev.pyvar.com` — confirm the actual dev URL from
`pyvar-cdk/config.py`/CloudFormation outputs if this differs) — **using
Stripe TEST MODE only, never live keys or real payment methods.**

## Why now

Two bugs were just fixed and merged to master:
- PR #367: `api/routes/billing.py`'s webhook handler crashed with
  `AttributeError: 'get' is a dict method, but a Session is not a dict`
  on every real Stripe webhook delivery (Sentry `afa9f2520c744907afa5d069149bfcbb`).
  Fixed with `getattr(event_object, "customer", None)`. Covered by unit
  tests with a mocked Stripe object, but **never verified against a real
  Stripe webhook delivery** — the exact gap that let it ship broken in
  the first place (the old test fixture was a plain dict, which
  masked the bug).
- PR #368: Alembic's migration DSN was resolving to the wrong Postgres
  driver depending on the installed SQLAlchemy version. Fixed and
  verified via `alembic upgrade head --sql`, but not against a live
  deployed dev DB.

This smoke test is the first real end-to-end confirmation that the
Stripe fix actually works against a genuine webhook delivery, not just
the unit-test mock. There's also a full, previously-unexecuted
10-test verification plan at `docs/plan-pro-subscription-verification.md`
in the repo — **this is a smaller, focused slice of it** (its Test 1 +
Test 9), not the whole thing. Don't run the full plan unless asked.

## Scope — read this before doing anything

- Stripe **test mode only**: `sk_test_...`/`pk_test_...` keys (already
  configured for dev per `docs/plan-monetization-implementation.md`).
  Confirm you're using test-mode keys before the first API call, not
  after.
- Test card `4242 4242 4242 4242` (always succeeds), any future expiry,
  any CVC — never a real card.
- One throwaway test user, created fresh for this test, cleaned up
  (deleted or clearly marked test data) when done.
- Nothing here should touch real money, a real customer, or prod.

## Steps

1. **Register a test user**:
   `POST https://dev.pyvar.com/api/v1/auth/register` with a throwaway
   email (e.g. `pyvar-smoketest+<timestamp>@<your domain>`) → expect `202`.

2. **Get the verification token directly from the dev DB** (read-only):
   query the `users` table for `verification_token` WHERE
   `email = '<the test email>'` — `api/routes/auth.py`'s `register`
   handler stores it there before emailing it, so this avoids needing
   SES/mailbox access. Aurora connection details are in Secrets Manager
   (`pyvar/dev/...`, same secrets `api_stack.py` wires into the API
   service) — a read-only `SELECT` only, no writes to this table.

3. **Verify**: `GET https://dev.pyvar.com/api/v1/auth/verify?token=<token>`
   → expect `{"access_token": ..., "tier": "free"}`. Save the access token.

4. **Start checkout**:
   `POST https://dev.pyvar.com/api/v1/billing/checkout` with
   `Authorization: Bearer <access_token>` → expect
   `{"checkout_url": "https://checkout.stripe.com/..."}`.

5. **Complete checkout with a real (test-mode) Stripe Checkout session** —
   this needs to actually go through Stripe's hosted page, not a
   synthetic `stripe trigger` event, so the *real* webhook payload shape
   is what exercises the fixed code path:
   - Open `checkout_url` in a headless browser (Playwright is available;
     Chromium is pre-installed at `/opt/pw-browsers/chromium` in a Claude
     Code sandbox — use whatever browser automation you have).
   - Fill card `4242 4242 4242 4242`, any future expiry, any CVC, submit.
   - Confirm the redirect lands on
     `.../dashboard.html?checkout_session_id=cs_...`.

6. **Confirm the webhook actually processed** — this is the real point
   of the test:
   - `GET https://dev.pyvar.com/api/v1/billing/checkout/complete?session_id=cs_...`
     → expect `{"access_token": ..., "tier": "pro"}`. **This is read
     straight from `users.tier` in the DB** (see
     `schemas/billing.py`'s `CheckoutCompleteResponse` docstring) — so a
     `tier: "pro"` here is direct proof the webhook handler ran
     successfully end-to-end, not just that Checkout itself succeeded.
   - Check CloudWatch logs for the dev API service (ECS task logs, or
     wherever `structlog` output lands — check `observability/setup.py`
     if unsure) around this timestamp for the `stripe_webhook` handler's
     log lines. Confirm there's **no `AttributeError`, no unhandled
     exception** — if the old bug were still live, this is exactly where
     it would show up, even if step 6's `GET` above happened to still
     read a stale `tier: "free"`.
   - Query the `billing_events` table for a row matching this checkout
     (non-null `stripe_event_id`, an upgrade `event_type`).

7. **Idempotency check** (directly tied to why the original bug mattered
   — Stripe's delivery guarantee is at-least-once, not exactly-once):
   using the Stripe Dashboard (test mode) or CLI, **resend** the same
   webhook event from step 6 once. Confirm:
   - The response is still `200`.
   - **No second** `billing_events` row is written for that same
     `stripe_event_id`.

8. **Clean up**: cancel the test subscription in the Stripe test-mode
   dashboard, and either delete the test user row or clearly mark it as
   test data (don't leave it live in the dev DB or dev Stripe account
   indefinitely).

## What to report back

For each step: pass/fail, and for any failure the exact response body
and/or the exact CloudWatch log line, not just "it failed." Specifically
call out:
- Whether step 6's CloudWatch check shows the fixed `getattr(...)` path
  running cleanly, or any sign of the old `AttributeError`.
- Whether step 7's idempotency check actually produced zero duplicate
  rows (this is the one place a bug would silently give away Pro access
  nobody paid for, per the existing verification plan's own note on this).

Don't touch prod, don't use live Stripe keys, don't leave test data
lying around when done.

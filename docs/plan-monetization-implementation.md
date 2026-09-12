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

**Deliberately not done — needs Filippo, real AWS access:**

1. **The three Stripe secrets don't exist in Secrets Manager yet**, and
   `pyvar-cdk/stacks/api_stack.py` was NOT touched to wire them — unlike
   this session's `local_package_stack.py` fixes (verified via `cdk synth`
   against a stack with zero live traffic), `api_stack.py` defines the
   ECS task for the actively-serving `pyvar-{env}-api` service. Wiring a
   secret into a task definition's `secrets={}` block (the same mechanism
   `DB_HOST`/`JWT_SECRET` already use) makes that secret's existence
   REQUIRED for every future task launch — if the CDK change deployed
   before the secret exists, every subsequent deploy of `pyvar-{env}-api`
   in that environment would fail outright. That risk is only acceptable
   to take with real AWS access to verify against, which this session
   doesn't have.

   **Do this, in this order, once you're ready to go live with billing:**

   ```bash
   # 1. Create the three secrets FIRST (test-mode values today; swap for
   #    live values later — no code change either way)
   aws secretsmanager create-secret --name pyvar/dev/stripe-secret-key \
     --secret-string "sk_test_..." --region eu-west-1
   aws secretsmanager create-secret --name pyvar/dev/stripe-webhook-secret \
     --secret-string "whsec_..." --region eu-west-1
   aws secretsmanager create-secret --name pyvar/dev/stripe-price-id-pro \
     --secret-string "price_..." --region eu-west-1
   ```

   2. THEN add this to `api_stack.py`, near the `sentry_secret`/`jwt_secret`
      construction (same file, same pattern — see that code's own comments
      for why DB_*/JWT_SECRET use `secrets={}` while Sentry deliberately
      doesn't; Stripe belongs with the former group once the secrets exist,
      since billing genuinely needs them, not a nice-to-have):

   ```python
   # Stripe — externally managed (not CDK-generated), same
   # from_secret_name_v2 pattern as sentry_secret above. Unlike Sentry,
   # wired via secrets={} below (like DB_*/JWT_SECRET) once the three
   # secrets actually exist — see docs/plan-monetization-implementation.md
   # §0 for why this must not be deployed before they do.
   stripe_secret_key = cdk.aws_secretsmanager.Secret.from_secret_name_v2(
       self, "StripeSecretKey", f"pyvar/{cfg.env_name}/stripe-secret-key"
   )
   stripe_webhook_secret = cdk.aws_secretsmanager.Secret.from_secret_name_v2(
       self, "StripeWebhookSecret", f"pyvar/{cfg.env_name}/stripe-webhook-secret"
   )
   stripe_price_id_pro = cdk.aws_secretsmanager.Secret.from_secret_name_v2(
       self, "StripePriceIdPro", f"pyvar/{cfg.env_name}/stripe-price-id-pro"
   )
   stripe_secret_key.grant_read(execution_role)
   stripe_webhook_secret.grant_read(execution_role)
   stripe_price_id_pro.grant_read(execution_role)
   ```

   3. And add these three entries to the task definition's existing
      `secrets={...}` dict (alongside `"JWT_SECRET": ...`):

   ```python
   "STRIPE_SECRET_KEY": ecs.Secret.from_secrets_manager(stripe_secret_key),
   "STRIPE_WEBHOOK_SECRET": ecs.Secret.from_secrets_manager(stripe_webhook_secret),
   "STRIPE_PRICE_ID_PRO": ecs.Secret.from_secrets_manager(stripe_price_id_pro),
   ```

   4. THEN `cdk deploy pyvar-dev-api --context env=dev --context account=347228921290`.
      Watch it — this is a real ECS rolling deployment of a live service.

2. **The Stripe Checkout Session and webhook endpoint itself have never
   been exercised against the real Stripe API** — `tests/test_billing.py`
   mocks every Stripe SDK call; nothing here has confirmed a real test-mode
   checkout actually completes end-to-end (Checkout redirect → webhook
   delivery → tier flip → `GET /billing/checkout/complete` issuing a
   working new JWT). Worth a manual run-through against the test Stripe
   account once the secrets above are wired, before calling Phase A done.
3. **Registering the webhook endpoint with Stripe itself** (Dashboard or
   `stripe listen`/CLI, pointing at
   `https://{dev.,}pyvar.com/api/v1/billing/webhook`) — a one-time,
   account-side configuration step, not a code change.

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

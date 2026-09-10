# Plan: monetization strategy implementation for pro/enterprise tiers

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

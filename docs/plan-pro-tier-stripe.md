# Plan: Pro tier and Stripe go-live

Written 2026-11-21, after #443 merged (`9fcd180`). It turns the owner's Pro review into a code scope and a checklist for the
Stripe agent. **The owner's decisions of 2026-11-21 are recorded in section 6.** **No code is written yet.** Facts below were read from the code on master (named by file and function, not line);
nothing was run. Not legal or tax advice. Older background: `docs/plan-monetization-implementation.md` (Phase A, built) and
`docs/plan-pro-subscription-verification.md` (a Stripe test-mode run book; its tests 1 and 9 were executed on dev on 2026-09-29/30).

## 1. The offer (owner's review)

| | |
| --- | --- |
| Price | £50 per account per month, GBP, billed monthly through Stripe. No annual plan, no trial |
| Covers | One account; all its keys share one set of limits; up to 5 active keys |
| Limits (checked against `api/tiers.py` and `config.py`: they match) | 100,000 simulations per request, 500 requests a day, 5,000 a month, 2,000,000 simulations a month |
| Extras | Only what runs today. No priority queue, longer retention or SLA is promised. **E-mail support is offered** (info@pyvar.com, the contact address already on the site); **no response time is guaranteed** |
| At a monthly cap | Refuse until the window rolls over, with a message naming the cap. **No downgrade to Free** |
| Cancellation | Pro continues to the end of the paid month, then Free. Account and keys stay |
| Failed payment | Stripe retries as normal; Free only when the subscription finally ends |
| VAT, who can buy | **Decided:** for UK customers VAT is included in the £50; the subscription is open to customers worldwide, billed in GBP. Fibtec is VAT-registered in the UK |

## 2. Today's code against the offer

| Offer | What the code does now | Change |
| --- | --- | --- |
| Cap refuses | Pro's monthly request cap (`api/middleware/rate_limit.py`) and simulation cap (`api/routes/var.py`) **move the account to Free**, send an e-mail, write an audit row and answer 403 | Set Pro `monthly_breach="refuse"` (the education tier already works this way): a 429 with `Retry-After`. Delete the downgrade and restore code (`downgrade_for_monthly_limit`, `restore_after_payment_succeeded`, the two reasons) and their tests. Keep the `users.tier_downgrade_reason` column (no migration) |
| Message names the cap | The 429 text is generic ("Rate limit exceeded. Please retry later.") | Monthly refusals say which cap ("Pro monthly limit of 5,000 requests reached") and when it resets. Applies to education too |
| "Window rolls over" | The monthly counter is a 30-day fixed window that starts at the first request after the previous window ended. It is **not** the calendar month or the Stripe billing period, yet the old message says "billing period" | **Decided (D3): keep the 30-day window** and say so in the Terms ("30 days from your first request in the window") |
| Failed payment | **`invoice.payment_failed` moves the account to Free at the first failed attempt.** Stripe sends that event on every attempt, and a later successful retry does **not** restore it (restore covers only cap downgrades) | Stop downgrading on it. Downgrade only on `customer.subscription.deleted`. Stripe must be set to cancel after the final retry (section 5, D) or Pro never ends |
| Cancellation | `customer.subscription.deleted` moves to Free: right. **No route lets a customer cancel** | Add `POST /billing/portal` (a Stripe Billing Portal session; JWT-authenticated like checkout) and a "Manage billing" button |
| Webhook scope | A downgrade event sets Free whatever the current tier | Act only when the tier is `pro`, so a stray Stripe customer on an enterprise or education account is not downgraded |
| Checkout landing | `success_url` is `dashboard.html?checkout_session_id=...`, but that page (the API-key page) never calls `/billing/checkout/complete` | The landing calls it and stores the new token; add an Upgrade button (no UI starts a checkout today) |
| 5 keys, shared counters | Already true for every tier: `api_key_max_active_per_user = 5`, 50 in total; both counters are keyed by the account, not the key | Tests only (section 4) |
| Free limit 10 or 20 | Code: **20 a day** (since #434). "10" survives only in `docs/p9-scenario-volume-cost-audit.md` and `docs/plan-anonymous-plugin-keys.md` | Pricing line states 20, pinned by a test against settings |
| Price ID | Not in `config.py`: read at startup from Secrets Manager (`pyvar/{env}/stripe-secret-key`, `stripe-webhook-secret`, `stripe-price-id-pro`; `_resolve_stripe_secrets`) | No code change; the agent loads the values |
| Tokens after a change | A session JWT carries the tier for 60 minutes; an API key's tier is read from the database (cached 60 s) | Accept and document: after cancellation a session token keeps Pro up to 60 minutes |

## 3. Text to publish (same PR, shipped last)

- Home page: one pricing line: Free £0 (20 requests a day), Pro £50 per account per month, Enterprise by contact.
- Terms: what Pro includes; monthly billing in GBP, VAT included for UK customers, open worldwide; cancellation (Pro to the end of the paid month, then Free); limits may change; a request over a cap is refused until the 30-day window rolls over; e-mail support at info@pyvar.com, with no guarantee of response times.
- Privacy: the Stripe row and a billing-data sentence already exist; check they say what we store. **Remove the automated-downgrade wording**: one sentence, in the "Your email address" item ("A Pro account that reaches its monthly limit moves to free automatically ..."), is the owner's automated-decisions sentence from #443. It stays true until this PR; then drop the Pro clause and keep the rest. `tests/test_education_portal_text.py` pins it.
- Public guide: `portal/guide-rest-api.html` and `portal/guides-assets/rest-tier-lifecycle.svg` describe the downgrade and restore paths; redraw them.
- The portal goes public at prod approval whatever the flags say, so this PR is approved in prod **last**, after dev is verified and live Stripe secrets are loaded.

## 4. Code scope

1. Pro monthly breach refuses (429, names the cap, `Retry-After`); remove downgrade and restore paths, their event types, e-mails and tests.
2. Webhook: only `checkout.session.completed` and `customer.subscription.deleted` act; the latter only on a `pro` account.
3. `POST /billing/portal`; dashboard Upgrade and Manage-billing buttons; the checkout landing completes the session.
4. Tests that pin the offer: two keys share one daily and one monthly counter; revoke and re-create does not reset them; a 6th active key is refused; a cap breach leaves the tier unchanged; a failed-payment event leaves Pro; cancellation at the period end returns the account to Free; the limits in the Terms equal `api/tiers.py`.
5. Text (section 3), `CHANGELOG.md`, rewrite tests 4 to 8 of `docs/plan-pro-subscription-verification.md` to the new behaviour.
6. CodePipeline: this changes `api/`, `portal/`: **a real pipeline run**. This plan alone (`docs/`) is pipeline-safe.

## 5. Stripe checklist for the agent

Do everything in **test mode on dev first**, report, then repeat in live mode only after the owner's go. Report IDs and settings, never secrets. Do not change application code. **A to G are the prompt `docs/prompts/agent-stripe-pro-setup.txt` (4.4 KB), run now.** H needs the new code on dev and gets its own prompt then; I is live mode.

- [ ] **A. Product and Price.** Product "pyvar Pro"; one recurring Price, £50.00 GBP, monthly, no trial, no annual. Tax behaviour inclusive (D1). Statement descriptor and support e-mail set. Report the Product and Price IDs.
- [ ] **B. Keys and secrets.** Use a restricted key with only what the code calls: Customers and Checkout Sessions (write), plus the customer portal once `POST /billing/portal` exists (the agent confirms Stripe's exact permission names). Put the key, the webhook signing secret and the Price ID in AWS Secrets Manager under the three names in section 2, per environment (test values on dev, live on prod). Secrets never go in chat or the repository.
- [ ] **C. Webhook endpoint.** `{API base}/api/v1/billing/webhook` for the environment (dev: `https://dev.pyvar.com/api/v1/billing/webhook`; confirm prod). Subscribe to exactly `checkout.session.completed` and `customer.subscription.deleted`. Report the endpoint ID.
- [ ] **D. Failed payments.** Set the retry schedule (record it) and **"cancel the subscription if all retries fail"**. Turn on Stripe's failed-payment e-mails to customers (the API sends none for this).
- [ ] **E. Billing Portal.** Enable it: update payment method, view invoices, **cancel at the end of the billing period (not immediately)**, no plan switching. Return URL: the dashboard.
- [ ] **F. Receipts and branding.** Customer receipts on; business name, logo, support address.
- [ ] **G. Tax.** Price tax behaviour **inclusive**; Stripe Tax on in test mode with the head-office address as origin; Fibtec is VAT-registered in the UK: add the UK registration in Stripe Tax once the owner gives the VAT number (the agent adds none on its own). Open worldwide, so no country restriction. The code PR adds address collection and `automatic_tax` to the Checkout session.
- [ ] **H. Test-mode run on dev** using `docs/plan-pro-subscription-verification.md` and a test clock: (1) happy path with the new Price; (2) card `4000 0000 0000 0341`: the account **stays Pro** after the first failed charge and returns to Free only when Stripe cancels after the last retry; (3) a successful retry keeps Pro; (4) cancel in the portal: Pro until the period end, then `customer.subscription.deleted` and Free; (5) the same event delivered twice changes nothing. Report event IDs and the tier before and after each step.
- [ ] **I. Live mode.** Repeat A to G with live objects; the owner makes one real £50 payment and a refund (owner's choice) before launch.
- [ ] **J. Hand back** a list of the values set (no secrets), the test results and anything that behaved differently. The code PR is reviewed against it before any prod deploy.

## 6. Order and decisions

Order: owner decisions (done) → Stripe agent A to G on dev (the prompt) → code PR on dev → Stripe agent H on dev → live Stripe and prod secrets (I) → prod approval of the PR last.

**Decided by the owner on 2026-11-21**

| | Decision |
| --- | --- |
| D1 VAT and buyers | For UK customers the £50 includes VAT; the subscription is open to customers worldwide (this widens the earlier "UK only to start" recommendation) |
| D2 Support at launch | Offered: e-mail, info@pyvar.com |
| D3 Monthly window | Keep the 30-day window and word it in the Terms |
| Facts | Fibtec is VAT-registered in the UK. E-mail support carries no guarantee of response times |

## 7. Known limits

- Fail-open: if the rate-limit store is down the caps are not enforced (existing design, `api/middleware/rate_limit.py`).
- A customer who cancels in the portal and pays again later starts a new checkout; there is no resume.
- Tests 2 to 8 and 10 of the verification run book were never executed against real Stripe; tests 4 to 8 describe the old downgrade behaviour and are rewritten here.

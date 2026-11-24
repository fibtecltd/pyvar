# Plan: Pro tier and Stripe go-live

Written 2026-11-21, after #443 merged (`9fcd180`). It turns the owner's Pro review into a code scope and a checklist for the
Stripe agent. **The owner's decisions of 2026-11-21 are recorded in section 6.** **Section 4 is built in PR #444 (2026-11-21); section 7a says what differs from this plan.** Facts below were read from the code on master (named by file and function, not line);
nothing was run. Older background: `docs/plan-monetization-implementation.md` (Phase A, built) and
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

Do everything in **test mode on dev first**, report, then repeat in live mode only after the owner's go. Report IDs and settings, never secrets. Do not change application code. **A to G are the prompt `docs/prompts/agent-stripe-pro-setup.txt` (4.4 KB), run now.** H is `docs/prompts/agent-stripe-pro-verify.txt` (4.6 KB), run once #444 is deployed to dev; I is live mode.

- [ ] **A. Product and Price.** Product "pyvar Pro"; one recurring Price, £50.00 GBP, monthly, no trial, no annual. Tax behaviour inclusive (D1). Statement descriptor and support e-mail set. Report the Product and Price IDs.
- [ ] **B. Keys and secrets.** Use a restricted key with only what the code calls: Customers and Checkout Sessions (write), plus the customer portal once `POST /billing/portal` exists (the agent confirms Stripe's exact permission names). Put the key, the webhook signing secret and the Price ID in AWS Secrets Manager under the three names in section 2, per environment (test values on dev, live on prod). Secrets never go in chat or the repository.
- [ ] **C. Webhook endpoint.** `{API base}/api/v1/billing/webhook` for the environment (dev: `https://dev.pyvar.com/api/v1/billing/webhook`; confirm prod). Subscribe to exactly `checkout.session.completed` and `customer.subscription.deleted`. Report the endpoint ID.
- [ ] **D. Failed payments.** Set the retry schedule (record it) and **"cancel the subscription if all retries fail"**. Turn on Stripe's failed-payment e-mails to customers (the API sends none for this).
- [ ] **E. Billing Portal.** Enable it: update payment method, view invoices, **cancel at the end of the billing period (not immediately)**, no plan switching. Return URL: the dashboard.
- [ ] **F. Receipts and branding.** Customer receipts on; business name, logo, support address.
- [ ] **G. Tax.** Price tax behaviour **inclusive**; Stripe Tax on in test mode with the head-office address as origin; Fibtec is VAT-registered in the UK: add the UK registration in Stripe Tax once the owner gives the VAT number (the agent adds none on its own). Open worldwide, so no country restriction. The code PR adds address collection and `automatic_tax` to the Checkout session.
- [ ] **H. Test-mode run on dev** after #444 is deployed there: the prompt `docs/prompts/agent-stripe-pro-verify.txt` (4.6 KB). A test clock cannot be used: the API creates the Stripe customer itself (`create_checkout`), and a customer cannot be moved onto a clock afterwards. The prompt covers: (1) happy path with the new Price; (2) the monthly simulation cap, 20 calls of 100,000 and a refused 21st, with no setting changed; (3) card `4000 0000 0000 0341` forced to fail an invoice: the account **stays Pro**; (4) portal cancel at the period end, then the subscription ended through the Stripe API (standing in for the period end or the last failed retry): `customer.subscription.deleted`, Free, keys intact; (5) the same events delivered twice and an unknown customer change nothing; (6) paying again. Not covered, because Stripe's own timing is not exercised: the renewal date, the retry schedule, the real period end. Report event IDs and the tier (read with a probe) before and after each step.
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
| D4 Dev Stripe key (2026-11-22) | Stripe stays in test mode, and `pyvar/dev/stripe-secret-key` keeps its existing test key until go-live. The restricted key is created for **live mode** |

## 7. Known limits

- Fail-open: if the rate-limit store is down the caps are not enforced (existing design, `api/middleware/rate_limit.py`).
- A customer who cancels in the portal and pays again later starts a new checkout; there is no resume.
- Tests 2 to 8 and 10 of the verification run book were never executed against real Stripe; tests 4 to 8 describe the old downgrade behaviour and are rewritten here.

## 7a. As built (PR #444), and what differs from sections 2 to 4

- Done as planned: Pro's monthly caps refuse (429, naming the plan and the cap, `Retry-After`); the downgrade and restore code, their event types and e-mails and the `monthly_breach` field of the tier table are gone (a policy row now has no downgrade option at all); the webhook acts on `checkout.session.completed` and `customer.subscription.deleted` only, and the latter only for a `pro` account; `POST /billing/portal`; the dashboard's Upgrade and Manage billing buttons and the checkout return (completes the session, asks again until Pro); "Billing is not configured" is a returned 503; pricing line, Terms (new section `#pro`), privacy and the public guide and its diagram.
- Added beyond the plan, because the new buttons made them reachable: checkout is refused (409) for an account that is already Pro (it would be charged twice) and for enterprise or internal accounts; a paid checkout never changes those two, and a second checkout on a Pro account is logged for a refund; an education account that upgrades loses its grant date.
- Not done, and why: **automatic tax on the Checkout session** (`automatic_tax`, billing address collection) waits for the Stripe agent's report on Stripe Tax: Stripe refuses the parameter until Stripe Tax has an origin address, so it needs a flag and an environment variable in the CDK, as a follow-up (built: section 10). The Medium article copy of the REST guide and its diagram under `docs/publications/` still describe the old downgrade.
- After a cancellation a session token keeps Pro for up to its 60 minutes and an API key for up to its 60-second cache; the next token and the next lookup read the database.

## 8. Prompt 1 outcome (2026-11-22)

Stripe **test mode** on dev, in the "fibtec limited sandbox" account (GB, GBP). The sandbox is **shared with other Fibtec products**: it also holds two other products' webhook endpoints and their objects, none of which were touched. The webhook handler is safe against that: it finds the user by `users.stripe_customer_id`, so another product's event is logged as `stripe_webhook_unknown_customer` and answered 200 with no change. Prompt 2 must never use `stripe trigger` (it fires every product's endpoint).

| Item | Result |
| --- | --- |
| Product | `prod_VFQjvcwS08J6e9` "pyvar Pro" (existing; statement descriptor set to PYVAR PRO). Its default price is still the old £20 one; pyvar passes the Price explicitly, so that is harmless |
| Price | `price_1UeeDgQk6KiRREvyk9N27Td4`: GBP 50.00 monthly, tax inclusive, no trial. `pyvar/dev/stripe-price-id-pro` now names it |
| Webhook | `we_1UEwCrQk6KiRREvyRKAI8EP6` (existing endpoint edited, signing secret unchanged): exactly `checkout.session.completed` and `customer.subscription.deleted`; `invoice.payment_failed` removed |
| Portal | `bpc_1UeeEgQk6KiRREvyDIzeKYac`, now the account's default: payment method and invoices on, cancel at the end of the period only, no plan switching or pause, return URL the dev dashboard. `POST /billing/portal` passes no `configuration`, so pyvar relies on this being the default; passing an explicit id (a setting) would stop another product's portal change from affecting pyvar |
| Reach check | an existing event resent to the endpoint: `pending_webhooks` 1 to 0, so it was accepted; the exact HTTP code is visible only in the Dashboard |

Still open (Dashboard-only, or needs an owner input):

1. **Restricted key** (Customers, Checkout Sessions, Customer portal: write; the app's four calls need no more): **live mode only** (D4). Dev keeps its existing test key, so this does not hold up #444 or the second prompt. If that key turns out to be restricted without the portal permission, Prompt 2 step 4 will show it as a Stripe permission error.
2. **Failed payments:** the retry schedule and "cancel the subscription if all retries fail", plus the customer e-mails. Without the cancel rule a failed renewal never ends Pro. Test and live mode have separate settings.
3. **Support e-mail and business name** are account-level, so they apply to the other products too.
4. **Stripe Tax** is active; the head-office address holds only the country. The full address is needed before `automatic_tax` is added to Checkout (follow-up PR).
5. **Live mode** repeats all of this.

## 9. Prompt 2 outcome (2026-11-23)

Run on dev after #444 was deployed, Stripe test mode, one throwaway account. **Everything passed**: the upgrade through Checkout (a new token carrying the Pro tier), the monthly simulation cap (20 calls of 100,000 accepted; the 21st a 429 with `Retry-After` and the cap's text; the tier still Pro), a declined renewal (the account stayed Pro), a portal cancel at the period end (the account stayed Pro), the subscription ended through the Stripe API (`customer.subscription.deleted`: Free, both keys kept), a replayed event and another service's event (nothing changed), and paying again (Pro). The webhook's HTTP codes cannot be read through the API; "pending 1 to 0" and the dev log lines stand for them.

How the run differed from the prompt: a billing-anchor reset netted to GBP 0.00, so a declined invoice was made by raising the subscription quantity; the portal records a period-end cancel as `cancel_at` (not `cancel_at_period_end`), and nothing in pyvar reads either field. Not exercised, because Stripe's own timing is: the renewal date, the Smart Retries schedule and what happens when they run out, the scheduled cancel firing by itself, and the monthly window resetting.

Findings and what was done:

| Finding | Action |
| --- | --- |
| Adaptive Pricing is on in the shared account: the hosted page defaulted to EUR (EUR 62.14 with a 4% fee); the Terms say pounds | **Owner's decision, 2026-11-23: it stays on for every service, because payments are collected worldwide; no code change.** The session keeps its currency and amounts in GBP and the local figures are in `presentment_details` (Stripe's documentation; to be seen on dev). Whether the Terms need a sentence on paying in a local currency is the owner's |
| Another service's endpoint subscribes to invoice events and receives A's | Our objects now carry `metadata[service]=pyvar`. TenGrade ignores events without its marker; etlgen and DocuGen are unchecked: look at their dev endpoint delivery logs in Stripe |
| `automatic_tax` is off, so Checkout computes no tax on the inclusive price | Built, off in every environment until Stripe Tax has the full head-office address (section 10) |
| An open GBP 50.00 invoice remains on the test customer, with a retry set for 2026-11-25 | Void it in the Dashboard (test mode) |

The check of this fix on dev is `docs/prompts/agent-stripe-pro-verify-gbp.txt`: the hosted page shows GBP 50.00 with no currency choice, and the session, the subscription and a new customer carry `service=pyvar`.

## 10. Tax on Checkout (PR B, built 2026-11-24, off in every environment)

**What it does.** With `stripe_automatic_tax_enabled` on (env `STRIPE_AUTOMATIC_TAX_ENABLED`; CDK flag of the same name; `billing._tax_checkout_params`) the Pro Checkout session also sends `automatic_tax`, `tax_id_collection`, `customer_update` (name and address `auto`) and `invoice_creation` (description "pyvar Pro subscription", marker `service=pyvar`), the set etlgen, TenGrade and DocuGen send for their payments. The Price keeps its tax-inclusive behaviour (D1), so no `tax_behavior` is sent. Intended result: a UK customer pays 50.00 of which 8.33 is VAT, with the VAT line (and a VAT ID, if entered) on the invoice; elsewhere the customer pays 50.00. Sales stay worldwide, with no country or rate check. The webhook is unchanged (it reads no amounts).

**Why `customer_update`.** pyvar always passes an existing Customer. By Stripe's documentation Checkout then does not save the address typed at checkout onto the Customer unless asked, and a renewal's tax is worked out from the Customer's address; `tax_id_collection` with an existing Customer is refused without `customer_update[name]=auto` (developers report this error; the API reference does not say it). Both are from documentation and reports, not yet seen on our account.

**Not verified (to be seen on dev, test mode):** that Stripe accepts `invoice_creation` in subscription mode (the reference describes it for one-time payments and says subscriptions create invoices automatically); what Stripe does with `automatic_tax` when Stripe Tax has no head-office address; what a customer outside the UK pays; that the address is kept for renewals; whether the live restricted key needs a tax permission.

**Turn-on, per Stripe mode and environment:**

1. Owner: the full head-office address in Stripe Tax (and the UK registration, which decides whether UK customers are charged VAT).
2. By hand, before any deploy, with the test key taken from the environment and never pasted: `curl -s https://api.stripe.com/v1/checkout/sessions -u "$STRIPE_TEST_KEY:" -d mode=subscription -d "line_items[0][price]=price_1UeeDgQk6KiRREvyk9N27Td4" -d "line_items[0][quantity]=1" -d "automatic_tax[enabled]=true" -d "tax_id_collection[enabled]=true" -d "invoice_creation[enabled]=true" -d success_url=https://dev.pyvar.com/dashboard.html -d cancel_url=https://dev.pyvar.com/dashboard.html | grep -E '"(id|type|code|param|message)"'`. A `cs_test_` id means Stripe takes all three; an error says which one it refuses. (No customer is passed, so `customer_update` is not tested here; step 4 covers it.)
3. If it is accepted: one line `stripe_automatic_tax_enabled=True` in the "dev" override of `pyvar-cdk/config.py`, with the expected value changed in `tests/test_cdk_stripe_tax_flag.py` in the same commit. That is a real pipeline run and a new dev task definition.
4. Run `docs/prompts/agent-stripe-pro-verify-tax.txt` on dev.
5. Live mode: repeat 1 to 4 with live objects, then the "prod" override, together with the live secrets, prod approved last.

**If Stripe refuses `invoice_creation` in subscription mode:** remove that one key (and its assertion) from `_tax_checkout_params`. Stripe still creates the invoice of every subscription payment; how to carry `service=pyvar` onto it is then a question for the owner.

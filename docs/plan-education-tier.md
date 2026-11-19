# Plan: education tier (A2), accepted 2026-11-18

**Status: accepted by the owner on 2026-11-18, as proposed. PR 1 is built (2026-11-19, section 10), off by default; PR 2 (portal text and the flag) is not started.** This supersedes `docs/plan-academic-access.md`
(2026-11-16). It comes from an independent review (a Fable research agent, 2026-11-17) of that plan against the code at
`d6c8bf0`, with three of its claims re-checked by the author (below). **[V]** means read at the file and line cited, **[A]** a
recommendation or assumption. The review ran no code and no test.

## 1. What was decided

| # | Decision | Chosen | Not chosen |
| --- | --- | --- | --- |
| 1 | Shape | A separate finite tier named `education`: one row in `api/tiers.py` and a `users.tier_expires_at` column (migration 0010) | A time-limited Pro grant, a flag on `free`, a Stripe coupon |
| 2 | Intake | **No portal form.** An applicant e-mails from an institutional address and the owner grants with one admin command. A form is built only above about 10 requests a month | The old plan's form, request queue and `access_requests` table |
| 3 | Limits | 100 requests a day, 2,000 a month (a 429, never a downgrade), 20 a minute, 100,000 simulations a request, 1,000,000 VaR simulations a month | The old plan: 200 / 3,000 / 30 / 100,000 / 1,500,000 |
| 4 | Cohort and pool | 25 active grants, at most 10 per e-mail domain (an override flag for a class), and a pool of 5,000 education VaR jobs a month, after which education falls back to free limits | 15 grants; a pool of 20,000 requests of any kind |
| 5 | Expiry | 6 months by default, 12 at most, set at grant; no expiry date means free. Renewal is a new e-mail from the same address, then `extend` | 12 months by default; automatic renewal |
| 6 | Approver sign-in | The existing script pattern: the AWS CLI reads `pyvar/<env>/jwt-secret` and signs a 10-minute token with `aud="pyvar-admin"`; the admin routes require that `aud`. No second secret, no SSO in v1 | A separate admin secret plus AWS SSO with MFA (the old plan) |
| 7 | Verification | A human decision on a verified institutional mailbox; `.ac.uk` staff on request, others with a staff or course page the owner opens himself. Never automatic | A vendored domain list; a verification vendor |
| 8 | Schools | The grant goes to a teacher aged 18 or over; pupils do not get education accounts | Pupils apply |
| 9 | Name | `education` (schools are not "academic"); never "internal" | `academic` |

## 2. Why not the alternatives

- **Not `internal`.** It is exempt from every quota (`api/middleware/rate_limit.py:113,181`) and is the only check on the admin
  routes (`api/routes/internal.py:57,98`), so a holder could suppress any e-mail address [V, the earlier plan's finding, still true].
- **Not a Pro grant or a Pro-like flag.** A monthly breach of a non-Pro tier today calls `downgrade_for_monthly_limit` and returns
  Pro's "downgraded" 403 text while the downgrade itself does nothing (`rate_limit.py:212-227`, `billing_lifecycle.py:189`) [V, re-checked
  by the author]; a Pro grant would also inherit the Stripe paths and be counted as a paying customer in `api_usage.tier`.
- **Not a flag on `free`.** It recreates the second lookup that A1 (`api/tiers.py`) removed.
- **Not a Stripe coupon.** The billing webhook then owns the tier (`api/routes/billing.py:389-391`) and Stripe holds a customer record for
  someone who pays nothing.
- **Not a portal form yet.** Most of the old plan defended a public write endpoint that ten institutions do not need. Without a form no
  applicant text enters the database: the institution is the e-mail's domain, and the audit trail is `billing_events` rows with codes only.

## 3. Cost

Worst case, using the repository's own cost figures ($0.019 to $0.026 variable cost per queued job, `docs/p9-aws-evidence-2026-11-13.md`
section 8; $0.026 re-checked by the author):

| Case | Monthly |
| --- | --- |
| One grant, 1,000 VaR jobs (the schema minimum of 1,000 simulations caps a month at 1,000 jobs) | $26 |
| All 25 grants, no pool | $650 |
| With the pool of 5,000 VaR jobs | **$130**, about 12% of the account bill |

The old plan's "$90 a grant" priced every request as a queued job. Only `/var/compute` reaches Spot; the other routes run inline on tasks
already paid for, so they add no marginal compute at these volumes [A]. **Not bounded by this design:** every quota fails open when the
cache is down (`rate_limit.py:186-190`), for every tier; the ceiling is then the 20-worker cap, about $1,270 a month.

## 4. How it works

- **Grant.** `scripts/education_grant.py grant --email ... --months 6 --cohort <label>` signs an admin token, calls
  `POST /internal/admin/education/grant`, and the route (a) requires a verified `free` account (it refuses `pro`, `enterprise`,
  `internal`), (b) counts active education accounts and answers 409 over the cohort cap or the per-domain cap, (c) sets
  `tier = "education"` and `tier_expires_at`, and (d) writes the `billing_events` row in the same transaction, with a code and the cohort
  label only. Also: `extend`, `revoke`, `list`, and `suspend-all` (the kill switch: it expires every grant now, writes the events and
  drops the cached keys).
- **Reading the tier.** One helper, `effective_tier()`, returns `free` for an `education` account with no or a past expiry. It is used at
  every place a tier leaves the database: the key lookup (`api_keys.py:182`) and the three session mints (`auth.py:263`, `auth.py:482`,
  `billing.py:283-285`; the review found the third one missed in the old plan) [V]. A key's tier stays out of any token claim (CLAUDE.md 3.5).
- **Limits.** `TierPolicy` gains a burst field and a "refuse, do not downgrade" mode for a monthly breach (the table has neither today);
  `tests/test_tier_policy.py` pins the field set and "exactly the four" tiers, so both tests change.
- **Upgrade.** A Stripe upgrade replaces the grant because expiry applies only while `tier == "education"`, so no checkout 409 is needed
  (`billing.py:373-377`).
- **Revocation** reaches keys within 60 s (the key cache) and sessions within 60 minutes.
- **The pool.** The review specifies the number and the fallback (free limits once 5,000 education VaR jobs have run in a month); a counter
  in the cache is the author's assumption of the mechanism [A].

## 5. Verification, privacy and terms

- **Check.** The sign-in link proves control of the mailbox. `.ac.uk` registration is restricted by Jisc's eligibility policy [W, the policy
  text was not opened]. The owner opens the staff or course page in his own browser. No vendor, runtime lookup or vendored list in v1. For a
  class the instructor sends the addresses: one cohort label, one expiry.
- **False positives:** alumni mailboxes kept for life; non-teaching `.ac.uk` bodies; paid consulting by academics. Hence the expiry and a
  non-commercial clause. **False negatives:** institutions without an academic address; granted manually on evidence.
- **Data added:** the expiry date and tier-change events (a code and the cohort label); the application e-mail (name, role, institution,
  course) stays in the company mailbox, deleted 12 months after a refusal or after the grant ends [A]. Lawful basis [A, not legal advice]:
  Article 6(1)(b) for the request and the grant, 6(1)(f) for abuse prevention and the decision record, with a written balancing test.
- **`portal/privacy.html`:** line 71 says there is "no name" and "one kind of account", and section 9 lists AWS, Stripe, Sentry and Google
  only. Both change before applications are taken by e-mail, and **the mailbox provider that receives them must be added**.
  **`portal/terms.html`:** section 3 (free, discretionary, non-commercial, expires on the date shown), section 4 (no sharing or resale of
  education keys), section 10 (may end without notice), holder aged 18 or over. **These are drafts for a lawyer's read.**

## 6. Abuse

Five free mailboxes already give 100 requests a day, so the prize is the 100,000-simulation cap (a Pro feature), and it sits behind a human
decision. Real defences, in order: human approval and the cohort cap; the VaR pool; the monthly caps; expiry; the burst cap. `api_usage` holds
no user identifier by design, so resale or sharing cannot be attributed; revocation is the remedy. The trial lane
(`docs/plan-trial-lane-throttle.md`) accepts only a trial ticket; an education key is refused there and the two share no counter.

## 7. Implementation plan

| PR | Files | CodePipeline |
| --- | --- | --- |
| 0 `docs` | this file; the register entry; a note at the top of `docs/plan-academic-access.md` | **No** (`docs/` only) |
| 1 `feat(api)` | `migrations/versions/0010_user_tier_expires_at.py`; `storage/models.py`; `api/tiers.py` (row, `KNOWN_TIERS`, `burst_per_minute`, `monthly_breach`, `effective_tier`); `config.py`; `api/middleware/rate_limit.py`; `api/routes/var.py`; `api/middleware/api_keys.py`; `api/routes/auth.py`; `api/routes/billing.py`; `api/middleware/auth.py` (`decode_admin_payload`); `api/routes/internal.py`; `schemas/internal.py`; `api/middleware/billing_lifecycle.py` (event names, e-mail copy); `scripts/education_grant.py`; `tests/`; `CLAUDE.md` sections 2 and 3.5 | **Yes**, including the migration |
| 2 `feat(portal)` | `portal/privacy.html`, `portal/terms.html`, one "education access" paragraph; `pyvar-cdk/config.py` (flag on, dev then prod) | **Yes** |
| 3, only if volume demands | the old plan's form and queue | Yes |

**Flag:** `education_tier_enabled`, default False; when off, `effective_tier` returns `free` and the grant route answers 503.
**Order with the trial lane (2026-11-18: the trial lane's PR 1 goes first; the owner said "start the trial lane PR 1"):** its PR 1 edits `api/tiers.py`, `tests/test_tier_policy.py` and `CLAUDE.md` 3.5 too, so whichever merges second
rebases; the second must also adopt the first's `aud` helper.

**Tests (CLAUDE.md section 5):** for the tier: 202 on submit; 401 without auth; 422 on bad parameters; 403 at 100,001 simulations; 429 on the
daily, burst and monthly limits with **no** tier change; pool exhausted gives free limits; an expired or missing expiry gives free through a key
and each of the three session mints; a Stripe upgrade survives the expiry. For the admin routes: refuse a session JWT, an API key, an
`internal` JWT, a stream token and a token with no `aud`; refuse a grant to `pro`, `enterprise` or `internal`; 409 over the caps. Migration up
and down; script tests with `--secret-stdin` and a loopback URL, no AWS.

## 8. `CLAUDE.md` 3.5 bullets (**go given by the owner on 2026-11-18; applied in A2 PR 1 on 2026-11-19**, with the code they describe; only the trailing design pointer was widened to name the trial plan too)

```
- The education tier is finite and expires: users.tier "education" counts only while
  users.tier_expires_at is in the future; with no expiry, or a past one, the account is
  "free". Read it through effective_tier() wherever a tier leaves the database (the key
  lookup and every session mint). Never grant "internal" or "enterprise" for education.
- Education limits live in api/tiers.py like every tier's. A monthly breach is a 429; it
  must never call downgrade_for_monthly_limit, which is Pro's.
- The admin routes under /internal/admin/ accept only an admin token: `aud` "pyvar-admin",
  10 minutes, signed by scripts/education_grant.py. They must REQUIRE `aud` to be present
  and equal (python-jose lets a token with no `aud` through a decoder that names one), so a
  session JWT, an API key, an "internal" JWT and a stream token are all refused. Every
  other route keeps refusing the admin token. Do not accept it in get_current_user.
- A grant or revocation writes its billing_events row in the same transaction as the tier
  change, with a code and a cohort label only: never an applicant's name or text.
- Design, limits and failure modes: docs/plan-education-tier.md.
```

## 9. Not verified

The Jisc policy text, the ICO retention guidance and UK school lists were not opened, so section 5's legal points need a lawyer's read.
Whether the owner has an MFA identity in AWS is unknown (the repository shows none), so the approver should use his own AWS identity with
MFA, allowed only to read the one secret, instead of the deployer key [A, recommended, not blocking]. The limiter on Valkey is unchecked.
Demand is unmeasured: every number is a starting value. The cost figures are the repository's, not a bill.

## 10. PR 1 as built (2026-11-19)

**Off by default.** `education_tier_enabled` is False, so merging changes nothing for anyone: every education account (there are none) reads as
`free`, and grant and extend answer 503. The portal text and the flag in `pyvar-cdk/config.py` are PR 2.

| Piece | What it is |
| --- | --- |
| `migrations/versions/0010_user_tier_expires_at.py`, `storage/models.py` | One nullable `users.tier_expires_at`, no default, no backfill. **Run up, down and up again on a throwaway PostgreSQL 16**; `tests/test_migration_0010_tier_expires_at.py` pins the offline SQL (one ADD COLUMN; one DROP COLUMN) and the single head |
| `api/tiers.py` | The `education` row (100,000 simulations; 100 a day, 2,000 a month, 20 a minute; 1,000,000 VaR simulations a month), two new `TierPolicy` fields (`burst_per_minute`, `monthly_breach`: `"downgrade"` for every other tier, `"refuse"` for education), `effective_tier()` and `seconds_until_expiry()` |
| `config.py` | `education_tier_enabled` (False) and the numbers above, the caps (25 and 10), months (6 default, 12 at most), the pool (5,000) and the admin token life (600 s) |
| `api/middleware/rate_limit.py`, `api/routes/var.py` | The burst check (**first**, so a refused burst does not use up the day), a monthly breach of a `refuse` tier is a 429 and never calls Pro's downgrade (requests **and** VaR simulations), and the pool (below) |
| `api/middleware/api_keys.py`, `api/routes/auth.py` (2), `api/routes/billing.py` (1) | The four places a tier leaves the database read it through `effective_tier()`. The key cache's TTL is capped at the grant's remaining seconds **while the grant is live** (a lapsed one resolves to free and is cached normally) |
| `api/middleware/auth.py` | `decode_admin_payload()` and `require_admin_token`: `aud` exactly "pyvar-admin" (checked a second time by hand, because python-jose lets a token with no `aud` through), `exp` and `iat` required, a life of at most `admin_token_ttl_seconds`, a subject, **no `tier` claim** |
| `api/education_grants.py` (new), `api/routes/internal.py`, `schemas/internal.py` | The rules, in one module with no HTTP in it, and five routes under `/api/v1/internal/admin/education/`: `grant`, `extend`, `revoke`, `suspend-all` (POST) and `list` (GET), kept out of the public OpenAPI document |
| `api/middleware/billing_lifecycle.py` | Four event names (`education_granted`, `_extended`, `_revoked`, `_suspended`) and the copy of the e-mail each sends to the account holder (best effort, like every tier-change e-mail) |
| `scripts/education_grant.py`, `scripts/token_tools.py` | The operator command (`grant`, `extend`, `revoke`, `list`, `suspend-all`); `token_tools.sign_token` gained an optional `audience` and an optional `tier` (token bytes for the old callers are unchanged) |

**Differences from the plan above.**
- **The logic is a module of its own** (`api/education_grants.py`); the routes are thin. The plan listed the work under `api/routes/internal.py`.
- **The pool is the rate limiter, not a hand-made counter** (the plan marked the mechanism an assumption, section 4). 5,000 education VaR jobs per **30-day fixed
  window** (the same `limits` storage and window kind as every monthly cap here, not a calendar month), taken by `/var/compute`, read without taking by every
  education compute request. **While it is spent, an education account gets the FREE limits on every compute route** (20 a day, 10,000 simulations), not only on
  VaR: "falls back to free limits" read literally, and the only reading that keeps the $130 bound. A request the education cap itself refuses (over 100,000 simulations) takes nothing from the pool. Like every quota here, it **fails open** on a cache error.
- **The monthly VaR simulation breach is a 429**, as the monthly request breach is (the plan said "a 429, never a downgrade" for the second only).
- **Revoke, list and suspend-all work with the flag off**; grant and extend are the only 503s. A way to end access must not depend on the flag.
- **`extend` of a lapsed grant re-checks the caps** (it makes the account active again), and an extension may go at most 12 months from today.
- **The cohort label is validated** (1 to 40 characters of letters, digits, `.`, `_`, `-`) so no applicant's words can reach the audit row. The `billing_events.reason` is
  `cohort=<label>; months=<n>; expires=<date>`, `cohort=<label>` or `code=suspend_all`, and a test fails if it ever holds an address or a name.
- **A grant, extend, revoke and suspend-all drop the account's cached API keys** at once (best effort), so a change reaches a key in seconds, not after the 60 s cache.
- **A ledger line** (`~/.pyvar/education.jsonl`, 0600; operator, time, environment, address, cohort, expiry) is written by the script after the API has confirmed;
  it is a convenience, the `billing_events` table is the record. No secret or token is ever written.
- **Not in the plan:** education uses the free tier's assistant allowance (`assistant_group` "free", the free daily number).

**Tests** (`tests/test_education_tier.py` 29, `test_education_admin.py` 67, `test_education_grant_script.py` 14, `test_migration_0010_tier_expires_at.py` 4, plus the changed
`test_tier_policy.py`): the effective tier in every combination (flag, no expiry, past, future, naive, other tiers, a Stripe upgrade surviving an old date); the
limits and that a breach changes nothing about the account; the pool, in and out, and failing open; 100,000 allowed and 100,001 refused; **every credential the API
hands out is refused by every admin route** (a session JWT, an enterprise JWT, an internal JWT, an API key, a stream token, a trial ticket, a wrong or missing `aud`,
an expired token, no `exp`, no `iat`, a life of 11 minutes, a `tier` claim, no subject, another secret) **and the admin token is refused by a route of each other kind** (session-only, compute, internal-tier, stream-token); real rows
for grant, extend, revoke, suspend-all and list, the two caps (the override never lifts the cohort cap, and a domain that merely ends the same way is not the same domain),
the audit rows' contents, the sign-in mint, key resolution and the key cache; the script against the real application (the token it signs is the one the API accepts,
"confirmed" only when the API's list agrees). The grant logic was also run once against a throwaway PostgreSQL 16 (case-insensitive address match, the suffix match
on the domain, ordering, the events).

**CodePipeline:** yes (`api/`, `migrations/`, `config.py`), and it includes the migration; the pipeline's migration step runs it in dev, then prod after approval.

**Not verified:** the pool's window and `test()` against the real Valkey-backed limiter (tested on the in-memory storage only); that the e-mail copy is acceptable
(a lawyer's read is already due for PR 2's text); that an organisation's mail filters do not treat the grant e-mail as marketing (it is sent from the same sender as the
other tier-change e-mails); the Jisc and ICO points of section 9; demand.

**To start using it (not part of this PR):** run PR 2 (privacy and terms text, the flag in `pyvar-cdk/config.py`, dev then prod), then
`python scripts/education_grant.py grant --env dev --email <address> --cohort <label>`.


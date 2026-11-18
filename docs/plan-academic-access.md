# Plan: academic access requests (proposal)

> **Superseded 2026-11-18 by `docs/plan-education-tier.md`** (accepted by the owner). The tier is now called `education`, the portal form is deferred, the limits and the approver sign-in changed, and the cost figures were corrected. This file is kept for its analysis of why `internal` must not be granted.

**Status: proposal, 2026-11-16. Nothing is built.** Written by a delegated design review (Opus) from a brief and the repository at master `7e35bbc`. Each statement about the code is tagged **[V]** (checked at the cited file and line) or **[A]** (assumed or recommended). The author re-checked these three against the code: the admin routes test only `tier != "internal"` (`api/routes/internal.py:57`, `:98`), authentication in front of them accepts API keys (`api/middleware/auth.py:155`), and domain endpoints run the engine inline on 0.5 vCPU API tasks (`api/routes/market_risk.py:531`, `pyvar-cdk/config.py:88`). Not checked: the section 5 approval path assumes the owner signs in with AWS SSO and MFA, while the AWS work so far used an IAM user (the CDK deployer); confirm which before relying on it.

**What the owner asked for, and where this differs.** The request was a portal section where education bodies apply for "internal unlimited" keys. This design recommends against granting `internal` (section 1: it is exempt from every limit and it is the only credential the admin routes check) and proposes a new finite `academic` tier instead. The flow the owner described (an e-mail, a free-tier token, a form, approval by Fibtec) is kept: the applicant reuses the existing sign-in and session token, so there is no new token.

**Overlap with the other proposal.** `docs/plan-academic-access.md` (academic tier) and `docs/plan-anonymous-plugin-keys.md` (anonymous plugin keys) each add a tier, change the same code (`api/middleware/auth.py` max-simulation map, `rate_limit.py` daily cap and `assistant_tier`, `api_keys.py` effective tier, `billing.py` checkout) and each names its migration `0010`. Both found that an unknown tier silently gets free-tier limits. Build them in one order, starting with a behaviour-preserving step that puts every tier's limits in one table that all of those places read, so a new tier cannot fall through to free. Not started.

## 1. What to grant

**Do not grant `internal`.**
- It is exempt from every quota (`api/middleware/rate_limit.py:113,181`) [V].
- It is the only check on the admin routes: `/internal/suppress-email` and `/internal/token-report` test only `tier != "internal"` (`api/routes/internal.py:57,98`). Those routes authenticate with `get_current_user`, which accepts API keys (`api/middleware/auth.py:155-156`) [V]. **An academic holding an `internal` key could suppress anyone's email.**

`enterprise` is unlimited too (`rate_limit.py:113`) [V].

**Grant a new finite tier, `academic`.** It is non-commercial, expires and can be revoked at once:

| Limit | academic | pro (reference) |
|---|---|---|
| Requests per day | 200 | 500 (`config.py:163`) [V] |
| Requests per month | 3,000, then a 429 (no downgrade) | 5,000, then a downgrade (`config.py:183`, `rate_limit.py:213-230`) [V] |
| Burst | 30 per minute (new) | none |
| Simulations per request | 100,000 | 100,000 (`auth.py:68`) [V] |
| VaR simulations per month | 1,500,000 | 2,000,000 (`config.py:184`) [V] |

**The burst cap matters.** Domain endpoints run the engine inline in an `async def` on the API task (`api/routes/market_risk.py:531-548`) [V]. Each task has 0.5 vCPU (`pyvar-cdk/config.py:88`), and prod runs at most 20 tasks (`pyvar-cdk/config.py:253`) [V].

**Cost.** One grant costs at most about $90 a month (3,000 × $0.03) [A]. Start with:
- a cohort cap of 15 active grants (worst case about $1,350 a month, against $900–1,050 of fixed cost [A]);
- a pool breaker at 20,000 academic requests a month: past it, academic accounts get free limits and the owner is alerted.

Prod workers are capped at 20 c5.xlarge (`pyvar-cdk/config.py:96,274`) [V].

**Code that must learn the tier.** An unknown tier silently gets free limits (`auth.py:71`, `rate_limit.py:184,278`) [V].
1. `auth.py:66-71`: the `max_simulations` map.
2. `rate_limit.py:184`: daily cap. `:196-230`: monthly cap, returning 429 for academic. Also add the new burst check and the pool breaker.
3. `rate_limit.py:274-284` (`assistant_tier`): academic maps to free.
4. `api/routes/var.py:225`: academic monthly-simulation cap (429, never `downgrade_for_monthly_limit`).
5. `api/middleware/api_keys.py:182,184-186`: the effective tier is `academic` only while `users.tier_expires_at > now`, otherwise `free`. Cap the cache TTL at the expiry.
6. `api/routes/auth.py:263-266` (verify) and `:481-484` (Google): the same check before minting a JWT.
7. `api/routes/billing.py:215`: checkout returns 409 for academic accounts. The webhook writes `tier="free"` (`:389-390`) [V] and would wipe the grant.
8. `api/middleware/billing_lifecycle.py:55-100`: new event types and email copy. Unknown types are silently not emailed (`:118-121`) [V].
9. `internal.py:70`: a bounce or complaint on an academic account revokes the grant.
10. `config.py:161-184`: new settings. `portal/pyvar.js:415+`: show tier and expiry. Review `scripts/generate_overview_figures.py:91-101`.

`api_usage.tier` and `var_jobs.tier` are `String(16)`, so they need no change (`storage/models.py:69,225`) [V].

## 2. Flow and API

Sign-in is unchanged: register, then the emailed link, then `GET /auth/verify`, which returns the 60-minute session JWT (`auth.py:154-267`) [V]. Google sign-in also works. There is **no new token**. `portal/academic.html` (noindex) uses `pyvar_jwt` from localStorage (`pyvar.js:386,391`) [V].

**Endpoints** in `api/routes/access.py`, all with `Depends(require_session)` (`auth.py:217-227`) and `_account_for`, which requires a verified account (`auth.py:296-302`) [V]:
- `GET /api/v1/access/academic`: the caller's latest request and grant (`id, status, submitted_at, decided_at, expires_at, reason_code`).
- `POST /api/v1/access/academic` with header `Idempotency-Key: <uuid>`:
  - 201 created; 200 on a replay;
  - 409 when another request is open;
  - 403 when the account is not eligible;
  - 503 when the flag is off or the queue is full.
- `DELETE /api/v1/access/academic/{id}`: withdraw while `submitted`.

**Form** (Pydantic, `extra="forbid"`; the email is the account's own and is never typed):
- `full_name` (≤100)
- `role`: undergraduate / postgraduate / PhD / staff / researcher / other
- `institution_name` (≤200)
- `country` (ISO alpha-2)
- `department` (optional)
- `evidence_url`: https only, ≤300, **never fetched by the server**
- `intended_use` (50–1,000 characters)
- `expected_monthly_requests` (enum)
- `end_date` (optional)
- Required attestations: non-commercial use; no sharing or resale; age 18 or over; will report leaving; accept the academic terms.

Text fields reject C0/C1 control characters and the bidi overrides U+202A–202E and U+2066–2069.

**Stored** in a new `access_requests` table:
- request: `id`, `user_id` (FK), `idempotency_key`, `status`, the form fields
- signals: `email_domain`, `domain_signal`
- decision: `submitted_at`, `decided_at`, `decided_by` (the admin token's sub), `reason_code`
- grant: `grant_expires_at`, `revoked_at`, `revoke_reason`, `pii_purged_at`

Also add `users.tier_expires_at`. No IP address is stored.

**States:** `submitted` → `approved` | `rejected` | `withdrawn` | `lapsed` (30 days with no decision). `approved` → `expired` | `revoked`.

**Rules** [A]:
- One open request per account, by a partial unique index on `(user_id) WHERE status='submitted'`. A race raises an IntegrityError, returned as 409.
- Unique `(user_id, idempotency_key)`.
- At most 3 requests per account, ever.
- Free-tier accounts only.
- Re-run `is_disposable_email` (`disposable_email.py:58-76`). Google-created accounts skipped it (`auth.py:414-421`) [V].
- 3 applications per IP per day.
- At most 50 pending requests in total.

## 3. Verifying "education"

**Local labels only, never auto-approval.** `domain_signal` is one of:
- `suffix`: the domain matches `*.ac.uk`, `*.edu`, `*.ac.<cc>` or `*.edu.<cc>`;
- `list`: the domain is on a vendored allow-list built from the MIT-licensed university-domains list, refreshed by `scripts/refresh_edu_domains.py`;
- `none`.

Only the reviewer sees the label, so applicants cannot tune against it.

**Why no auto-approval:** alumni-for-life mailboxes and non-academic `.edu` domains exist.

**Unusual domains** (`uni-xyz.de`, research institutes on `.org`) go to manual review. The evidence is a staff or course page on the institution's own site, opened in **the reviewer's browser**. A gmail address is allowed with evidence, but the default answer is reject.

**Never at runtime:** WHOIS/MX lookups, verification vendors, or fetching `evidence_url`. Each leaks applicant data or opens SSRF. This is consistent with `disposable_email.py:13-17` [V].

## 4. Abuse analysis

| Attack | Who | Impact | Mitigation | Residual |
|---|---|---|---|---|
| Form spam | bots | queue noise | verified session; 1 open and 3 lifetime per account; 3 per IP per day; 50 pending cap; length limits | low |
| Stored XSS / terminal injection | applicant | JWT theft (it lives in localStorage, `pyvar.js:386` [V]); ANSI/OSC spoofing in the CLI | control and bidi characters rejected; the CLI escapes output; HTML uses `textContent` only (`pyvar.js:330` [V]) | low |
| E-mail bombing / SES relay | attacker | SES reputation | mail goes only to the account's verified address; no applicant text in any email; owner alerts at most hourly, ids only | low |
| Account farming | abuser | many grants | human review; 5 active grants per domain; cohort cap; disposable domains blocked | medium |
| One institution, many people | lab or class | per-domain cap reached | cap of 5 per domain; cohorts handled by email | low |
| Key sharing / resale | grantee | lost revenue | 3,000 a month cap; terms clause; revoke | medium: no per-IP tracking, by design (`models.py:73-76` [V]) |
| Compute abuse by an approved key | grantee | about $90 a month; API stall | daily, monthly and burst caps; pool breaker; alert at 80% | low |
| Takeover of an approved account | inbox thief | a bounded grant misused | sign-in links are single-use and last 30 minutes (`config.py:46-47`); keys are managed only from a session (`auth.py:217`) [V]; revoke | low–medium |
| Reviewer fatigue | volume | rubber-stamping | 30-day lapse; pending cap; reason codes; queue sorted by signal | medium |
| Enumeration | anyone | learns who applied | the caller sees only their own data; UUIDs; register keeps its identical 202 (`auth.py:162-222`) [V] | low |
| Impersonating an institution | holder of a student mailbox | false grant | link proves the inbox; evidence; attestation; revocable | medium |
| Owner approves by mistake | owner | wrong grant | the CLI requires typing the domain to confirm; default expiry 6 months; revocation reaches keys within 60 s (`config.py:40`) and sessions within 60 min (`config.py:26`) [V] | low |

## 5. Approval mechanism

- **(a) Signed links in email: rejected.** Mail scanners prefetch GET links (auto-approve), and the link is a forwardable bearer credential.
- **(c) A DB queue is the source of truth, reached through (b)**: `scripts/access_requests.py` with `list`, `show`, `approve --expires`, `reject --reason`, `revoke`, `suspend-all`, `expiring`. It calls `/api/v1/internal/admin/access-requests/...`.

**How the approver is authenticated:**
1. The owner signs in to AWS SSO with MFA.
2. The CLI reads a **new** secret, `pyvar/{env}/admin-jwt-secret`, the same way `billing.py:200-204` reads Stripe secrets [V].
3. It mints a 10-minute JWT with `aud="pyvar-admin"` and `sub="admin:<name>"`.
4. A new `decode_admin_payload`, modelled on the stream token, checks it.

The token works nowhere else, because `decode_token_payload` rejects any `aud` (`auth.py:104-106`) [V]. Admin routes in turn refuse session JWTs, API keys and the Lambdas' `internal` JWTs. A leaked `jwt_secret` therefore cannot approve anything.

## 6. Lifecycle

- **Expiry:** set at approval; 6 months by default, 12 at most. Enforced lazily through `tier_expires_at`, so no scheduler is needed for correctness. `expiring --sweep` writes the audit row and sets `tier='free'`.
- **Renewal:** opens 30 days before expiry, through the same form, with a dashboard banner.
- **Revocation:** one transaction sets `tier='free'`, `revoked_at` and a BillingEvent (written in the same transaction, `billing_lifecycle.py:140-163`) [V]. It then calls `invalidate_cached_key` for each of the account's keys (`api_keys.py:115-123`) [V]. Sessions keep a stale tier claim for up to 60 minutes (`auth.py:93`) [V]; that is accepted.
- **Usage alerts:** no user identifier is added to `api_usage` (`models.py:73-76`) [V]. Read `get_window_stats` on the account's monthly key (`rate_limit.py:155`) [V]. One alert at 80% (Redis SET NX); `show` prints the remaining quota.
- **Audit:** BillingEvent types `academic_granted`, `_renewed`, `_expired`, `_revoked`, `_suspended`. `reason` holds a code, never applicant text: the rows are never deleted (`models.py:267-268`) [V].
- **Applicant leaves:** keys do not need the inbox, so they keep working. Mitigations: short expiry; the leaver attestation; and when the institution closes the mailbox, the next mail bounces, the suppression handler flags it (`internal.py:60-73`) [V], and §1 item 9 revokes the grant.

## 7. Data protection

**New data:** name, role, institution, department, country, evidence URL, intended use, end date, and the decision code.

**Lawful basis:**
- Art. 6(1)(b), pre-contract steps, for the application.
- Art. 6(1)(f), legitimate interests, for abuse prevention and the decision record.
- Applicants must be 18 or over.

**Retention** [A]:
- Rejected, withdrawn or lapsed: personal free text is nulled after 6 months; a minimal row (domain, dates, status, code) is kept for 24 months.
- Approved: kept for the grant plus 24 months.
- An erasure request nulls the fields at once.
- `access_requests` is not a §3.3 audit log.

**privacy.html:**
- Line 54: update the date.
- Line 71: replace "one kind of account — there's no separate organisation/company concept, no name…" with "Most accounts hold only an email address; academic-access applicants also give the details in §2a."
- New §2a: the fields, the purpose, both lawful bases, that a person reviews every application, that no verification services are used, and the retention periods.
- §4 (lines 82–84): add the retention periods.
- §9 sub-processors: unchanged (lines 99–106) [V].

**terms.html:**
- Line 50: update the date.
- §3 (lines 73–77): add an "Academic tier" bullet: free, non-commercial, discretionary, expires on the date shown, can be withdrawn at any time.
- §4 (lines 80–88): forbid sharing or selling academic keys, and commercial or client work.
- §2 (line 70): you must tell us if you leave the institution.
- §10 (line 106): academic access may end without notice.

## 8. Implementation plan

**Add:**
- `migrations/versions/0010_access_requests.py`: the table, the partial unique index, a `status` CHECK and `users.tier_expires_at`. Sync driver; 0001–0009 untouched (CLAUDE.md §3.3).
- `schemas/access.py`, `api/routes/access.py`, admin routes in `api/routes/internal.py`.
- `api/middleware/education_domains.py` and its data file.
- `portal/academic.html`.
- `scripts/access_requests.py`, `scripts/refresh_edu_domains.py`.
- `docs/plan-academic-access.md`.

**Change:** the §1 list, plus `storage/models.py`, `main.py`, `portal/dashboard.html`, `pyvar.js`, `privacy.html`, `terms.html`, and CLAUDE.md §2 and §3.5.

**Flags and kill switch:**
- `academic_access_enabled` (accepts applications) and `academic_tier_enabled` (when false, academic resolves to free). Both default to False. Same pattern as `assistant_enabled` (`pyvar-cdk/config.py:250-258`) [V].
- `suspend-all` is the kill switch that needs no deploy.

**Tests (CLAUDE.md §5):**
- Access routes: 401 with no auth; 403 with an API key; 422 for bad input or control characters; 201 then 200 on a replay; 409 for a second request; 503 when the flag is off.
- Admin token: refused everywhere else; session, key and `internal` tokens refused on admin routes.
- Tier: daily, monthly and burst 429s; no downgrade; the simulation cap; expired means free; revocation invalidates the cache; checkout returns 409; the webhook does not clobber the grant; the assistant treats academic as free.
- Migration up and down.

**Pipeline (§8.1):**
- The code PR touches `api/`, `storage/`, `migrations/`, `portal/`, `config.py` and `CLAUDE.md`, so it **will trigger a CodePipeline run**, including the migration (`pipeline_stack.py:1053-1062`) [V].
- Split it: PR 1 is `docs/` + `scripts/` only (**pipeline-safe**); PR 2 is the code with both flags off; PR 3 turns the flags on.

## 9. Rejected alternatives

- **`internal`:** unlimited, and it opens `/internal/*` to the grantee's key.
- **`enterprise`:** unlimited, and it pollutes customer metrics.
- **A 100% Stripe coupon on Pro:** adds a sub-processor, and webhooks then own the tier (`billing.py:385-392`).
- **Auto-approval by domain:** alumni and non-academic mailboxes.
- **Verification vendor:** data leaves Fibtec; cost.
- **Email approval links:** scanner prefetch; forwardable bearer links.
- **Admin web UI:** new attack surface for one reviewer.
- **One shared key per institution:** no accountability, and revocation is all-or-nothing.

## 10. Open decisions (recommended default)

1. Limits 200 a day, 3,000 a month, 30 a minute, 100k simulations. **Default: as listed.**
2. Cohort cap of 15 and a pool of 20,000 requests a month. **Default: yes, review after 3 months.**
3. Expiry. **Default: 6 months, 12 at most, renewable.**
4. Personal-email applicants. **Default: allowed with evidence, rejected unless the evidence is strong.**
5. Pro subscribers. **Default: must cancel before applying.**
6. Class and cohort access. **Default: out of scope; handled by email.**
7. Minimum age. **Default: 18.**
8. Retention. **Default: 6 months for rejected applications, 24 months after a grant ends.**
9. Owner alerts. **Default: SES to one address, at most hourly, ids only.**
10. Public name. **Default: "academic", never "internal unlimited".**

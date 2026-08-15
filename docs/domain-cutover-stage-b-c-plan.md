# Domain cutover — Stage B (dev.pyvar.com) / Stage C (pyvar.com → prod)

Status: **planning only — no code or AWS changes made under this doc.**
Written 2026-08-09, on hold pending explicit go-ahead. Reuse this document
when picking the work back up rather than re-deriving it from scratch.

## Context

`pyvar-prod-edge` and `pyvar-prod-public-data` were bootstrapped in PR #224
with `edge_domain_names=[]` (prod's CloudFront distribution has no custom
domain alias — just its default `*.cloudfront.net` address) because
`pyvar.com`/`www.pyvar.com` are currently owned by the **dev** environment's
distribution (`pyvar-dev-edge`), which is confirmed serving live production
traffic. CloudFront enforces alias uniqueness account-wide, not
per-distribution, so prod cannot claim those aliases while dev holds them.

Two follow-on stages were identified but deliberately deferred:

- **Stage B** — give dev its own `dev.pyvar.com` subdomain, so it no longer
  needs to hold `pyvar.com`/`www.pyvar.com`.
- **Stage C** — the actual cutover: move `pyvar.com`/`www.pyvar.com` from
  dev's distribution to prod's, and repoint DNS.

This doc captures the research and design for both, plus two open decisions
that were never confirmed with the user before this work was put on hold.
**Do not treat the "recommended" options below as decided — confirm them
when this is picked back up.**

## Findings that shape the design

- **`feat/p8-domain-dns-ssl` (origin branch) is dead.** It carries zero
  commits unique from master — fully superseded by PR #224's generalized
  `config.py: edge_domain_names` mechanism. No reusable work sitting on it;
  safe to ignore or delete.
- **DNS today, confirmed live via direct lookup:**
  - `pyvar.com` A record → `62.149.189.55` — this is **Aruba's own
    forwarding proxy**, which does its own `301` to `www.pyvar.com`. It
    never touches CloudFront at all.
  - `www.pyvar.com` CNAME → `d1mqqddh8gu2qi.cloudfront.net` (dev's
    distribution). **This is the only DNS record that actually needs to
    move in Stage C.**
  - This matters: the bare `pyvar.com` CloudFront alias that dev's
    distribution holds today is never hit by real traffic — Aruba's proxy
    handles the apex redirect independently of CloudFront/ACM entirely.
- **DNS management is 100% manual.** `hosted_zone_id` is empty for every
  environment in `config.py` (Route53 was evaluated and explicitly
  declined — see `edge_stack.py`'s own comments). Aruba is managed only
  through their web UI; no CLI/API/automation exists anywhere in this repo
  for DNS record changes. Any DNS step in Stage B or C is a **manual
  operator action** — this plan can give exact record values and verify
  propagation afterward (via public resolvers, the same pattern used in
  `scripts/claude/prompts/p8b-dnssec-activation-lead-prompt.md`), but
  cannot execute the DNS change itself.
- **`api_stack.py`'s `AlbCertificate`** (`domain_name="pyvar.com"`) is a
  separate, per-environment, internal-only cert for the ALB's HTTPS:443
  listener (default-403 — CloudFront→ALB actually flows over HTTP:80).
  Confirmed unrelated to the CloudFront alias/DNS story; no changes needed
  there for either stage.
- **`pipeline_stack.py`'s `ProdSmokeTest`** only curls prod's bare
  `*.cloudfront.net` domain's `/health` endpoint — it never exercises a
  custom alias or the auth/compute path. It won't validate Stage C's
  outcome; the cutover runbook below includes manual verification instead.
- **`config.py` already has an unused `certificate_arn: str = ""` field**,
  documented as "ACM cert in us-east-1 for CloudFront" but never read by
  any stack today. This is exactly the mechanism the recommended Stage C
  cert strategy would put to use.

### Adjacent findings (not in scope, worth a separate follow-up)

- `lambda/ses_suppression_handler/handler.py` and
  `lambda/public_data_publisher/handler.py` both hardcode dev's CloudFront
  domain (`d1mqqddh8gu2qi.cloudfront.net`) as `API_BASE_URL`. Prod's own
  copies of these Lambdas currently call **dev's** API, not their own — a
  pre-existing bug independent of this domain cutover.
- `main.py`'s CORS allowlist permits only `https://pyvar.com` (not
  `www.pyvar.com`, not any `dev.pyvar.com`). Likely moot today since the
  portal is served same-origin with the API, but worth revisiting if any
  first-party browser client ever needs cross-origin calls.
- `portal/index.html` references a non-existent `api.pyvar.com` in static
  copy — cosmetic inconsistency, not a functional dependency.

## Stage B — give dev its own dev.pyvar.com

Small, additive, low-risk. Dev's existing `pyvar.com`/`www.pyvar.com`
continue serving unaffected throughout — CloudFront treats alias/cert
additions as non-disruptive to already-configured aliases, and this is an
*update* to an already-`CREATE_COMPLETE` stack, not a from-scratch create.

1. **Code change** — add an explicit `"dev"` override in `config.py`'s
   `PyvarConfig.for_env()`:
   ```python
   edge_domain_names=["pyvar.com", "www.pyvar.com", "dev.pyvar.com"],
   ```
   No `edge_stack.py` changes needed at all — PR #224 already generalized
   the certificate/alias wiring to arbitrary-length lists
   (`domain_name=edge_domain_names[0]`,
   `subject_alternative_names=edge_domain_names[1:]`).
2. **Manual DNS step at Aruba** — add the new ACM DNS-validation CNAME for
   `dev.pyvar.com` (retrieve the exact record via `aws acm
   describe-certificate` after the deploy starts, same as `edge_stack.py`'s
   own documented workflow); existing `pyvar.com`/`www.pyvar.com`
   validation records will most likely be reused automatically by ACM.
   Also add `dev.pyvar.com` → `d1mqqddh8gu2qi.cloudfront.net` as a CNAME.
3. **Verify**: `cdk diff` before deploying (expect only an addition, no
   resource replacement of the live `pyvar-dev-edge` stack's existing
   aliases); after deploy, confirm via `aws cloudfront
   get-distribution-config` and a live `curl -I https://dev.pyvar.com/health`
   once DNS + cert propagate, while re-confirming `pyvar.com`/
   `www.pyvar.com` are still unaffected (same regression-check pattern used
   for PR #224 — diff the distribution config before/after).

## Stage C — the actual cutover

This is the real runbook. Two sub-phases: **prep** (safe, no live-traffic
risk, can happen well ahead of the cutover) and the **live cutover
sequence** (needs a scheduled go/no-go, ideally a low-traffic window, and
has an unavoidable brief gap — see below).

### Prep tasks (no live risk)

- **Cert strategy — resolved (2026-08-15): out-of-band approach chosen and
  executed.**
  - Requested independently of any CDK stack:
    `aws acm request-certificate --domain-name pyvar.com
    --subject-alternative-names www.pyvar.com --validation-method DNS
    --region us-east-1` →
    `arn:aws:acm:us-east-1:347228921290:certificate/a18950da-05cc-49fa-81d9-78828e512f3e`.
  - Validated near-instantly (`ISSUED` in under a minute) — ACM reused the
    exact same `pyvar.com`/`www.pyvar.com` validation CNAME records
    already on file at Aruba (same ones the original dev cert and the
    Stage B `dev.pyvar.com` SAN-extension both used), so **no new Aruba
    DNS action was needed** for this cert at all.
  - This decouples validation timing from the live cutover window
    entirely, and avoids the risk of a validated cert being destroyed if a
    CloudFormation Distribution update later fails and rolls back (since a
    freshly-created-inline cert would roll back together with the failed
    changeset).
  - PR #237 (adds `edge_stack.py` support for
    `acm.Certificate.from_certificate_arn(...)` when `cfg.certificate_arn`
    is set, instead of always creating one inline) is up, CI running, not
    yet merged. Next steps once ready: merge #237, set prod's
    `cfg.certificate_arn` to the ARN above — both separate from this prep,
    tightly sequenced with the live cutover, not done here.
  - *(Original alternative, not taken: let CDK create + validate the cert
    inline as part of the same deploy that adds the alias to prod —
    simpler, no new code path, but the live cutover window would then also
    include DNS validation time and a failed Distribution update would
    waste that validation.)*
- Reduce the `www.pyvar.com` CNAME's TTL at Aruba well in advance of the
  cutover, and wait out the old TTL — bounds propagation time once the
  record actually changes.
  - **Done (2026-08-15).** Checked directly: `www.pyvar.com`'s CNAME was
    already at 300s (5 min) — no change needed, nothing to wait out. The
    `pyvar.com` bare-apex A record is separately at 3600s, but **Aruba
    does not allow altering TTL on A records** (confirmed directly with
    the user) — this doesn't block Stage C as designed, since the apex
    record is Aruba's own forwarding proxy and is never touched by the
    cutover sequence below (only `www.pyvar.com`'s CNAME moves). It does
    constrain open decision 2 below: if the bare-apex alias option is
    chosen and ever requires converting `pyvar.com` from an A record to a
    CNAME at Aruba, that change would propagate on Aruba's fixed ~1h TTL,
    not a shortened one — factor this in if that path is chosen.

### Live cutover sequence

1. Confirm prod is healthy: the existing `ProdSmokeTest` `/health` check,
   plus a manual auth+compute check (the automated smoke test doesn't cover
   that path today).
2. Deploy an update to `pyvar-dev-edge`: drop `pyvar.com`/`www.pyvar.com`
   from `edge_domain_names`, leaving `["dev.pyvar.com"]`. Verify
   `UPDATE_COMPLETE` and confirm via `get-distribution-config`.
3. Deploy an update to `pyvar-prod-edge`: set `edge_domain_names` to
   include `www.pyvar.com` (and, per the open decision below, possibly the
   bare `pyvar.com` too), using the pre-validated cert ARN if that approach
   was chosen in prep.
4. **Manual**: swing the `www.pyvar.com` CNAME at Aruba from
   `d1mqqddh8gu2qi.cloudfront.net` to prod's CloudFront domain (was
   `d31t9sn2oya6qy.cloudfront.net` as of this session — re-verify at
   execution time; it can change if the distribution is ever recreated).
5. Verify propagation via public DNS-over-HTTPS resolvers plus `curl -I
   https://www.pyvar.com/health`; confirm traffic actually landed on prod
   using prod's ALB/CloudFront CloudWatch request-count metrics (the
   unambiguous signal, since response bodies don't currently differ
   between environments).
6. Soak/monitor prod's existing CloudWatch alarms
   (`pyvar-prod-api-latency-p95`, `pyvar-prod-api-5xx`,
   `pyvar-prod-worker-errors`) for an agreed period before calling the
   cutover final.

There is an inherent, unavoidable brief gap between step 2 (dev releases
the alias) and step 3+5 (prod claims it and DNS resolves there) — CloudFront
will not allow both distributions to hold the same alias simultaneously.
Minimizing this gap is the entire point of the out-of-band cert strategy
above.

### Rollback

Symmetric but **not instant**: swing DNS back to dev's CloudFront domain,
remove the alias from prod, and re-add it to dev (which means re-creating
dev's cert with the fuller SAN list again — likely fast if Aruba's
`pyvar.com`/`www.pyvar.com` validation CNAMEs weren't removed in the
meantime, but not guaranteed instant). This asymmetry should be understood
and accepted before starting the live sequence, not discovered mid-rollback.

## Open decisions (unresolved — ask again before implementing Stage C)

1. **Cert strategy**: out-of-band ARN import (recommended) vs. inline CDK
   creation at cutover time.
2. **Bare `pyvar.com` alias on prod**: keep it for parity with dev's
   current setup (recommended — zero extra cost, avoids surprises if
   Aruba's apex-forwarding setup ever changes to a CNAME-to-CloudFront
   model) vs. drop it and alias only `www.pyvar.com` (simpler, since the
   apex alias demonstrably serves no real traffic today).

## Status

Planning only. Stage B is small enough to implement in one sitting once
resumed. Stage C requires a scheduled live window, the two open decisions
above resolved, and manual Aruba DNS steps at the actual cutover moment.

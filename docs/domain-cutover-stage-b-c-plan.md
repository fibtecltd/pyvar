# Domain cutover — Stage B (dev.pyvar.com) / Stage C (pyvar.com → prod)

Status: **COMPLETE (2026-08-16).** Stage B and Stage C are both live and
verified: `pyvar.com`/`www.pyvar.com` now serve from prod, `dev.pyvar.com`
serves dev. Written 2026-08-09 as planning-only, executed 2026-08-15/16.
See "Stage C incident report" below before ever repeating this kind of
CloudFront alias migration elsewhere in this project — the live cutover
sequence originally written here had an ordering bug that caused two real
outages before the corrected sequence succeeded.

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

### Live cutover sequence (CORRECTED — see incident report below)

**This is the sequence that actually worked on 2026-08-16, after two failed
attempts using a different order. Do not use the original ordering (drop
from old distro → add to new distro → swing DNS) — it causes a
CloudFront `CNAMEAlreadyExists` rejection and an avoidable outage. DNS must
change BEFORE the new distribution claims the alias, not after.**

1. Confirm prod is healthy: the existing `ProdSmokeTest` `/health` check,
   plus a manual auth+compute check (the automated smoke test doesn't cover
   that path today).
2. Deploy an update to the OLD distribution (`pyvar-dev-edge` in this
   case): drop the alias from `edge_domain_names`. Verify `UPDATE_COMPLETE`
   and confirm via `get-distribution-config`. **The domain is now down —
   no distribution claims it.** This is expected and matches step 3 next,
   not a mistake.
3. **Manual, immediately**: swing the CNAME at Aruba (or wherever DNS is
   managed) directly to the NEW distribution's `*.cloudfront.net` domain —
   *before* the new distribution has been given the alias. Confirm this
   independently (see the Aruba propagation caveat below — do not trust
   the TTL alone) by querying the domain's authoritative nameserver
   directly, not a public resolver, since public resolvers can serve a
   stale cached answer that looks identical to "not propagated yet."
4. Once the authoritative nameserver itself returns the new target, deploy
   an update to the NEW distribution (`pyvar-prod-edge`): add the alias to
   `edge_domain_names`, using the pre-validated cert ARN if that approach
   was chosen in prep. This should now succeed — CloudFront's live-DNS
   check no longer sees a conflicting distribution, since DNS points at
   the very distribution being updated.
5. Verify propagation via public DNS-over-HTTPS resolvers plus `curl -I
   https://www.pyvar.com/health`; confirm traffic actually landed on prod
   using prod's ALB/CloudFront CloudWatch request-count metrics (the
   unambiguous signal, since response bodies don't currently differ
   between environments).
6. Soak/monitor prod's existing CloudWatch alarms
   (`pyvar-prod-api-latency-p95`, `pyvar-prod-api-5xx`,
   `pyvar-prod-worker-errors`) for an agreed period before calling the
   cutover final.

There is an inherent, unavoidable outage between step 2 (old distro
releases the alias) and step 4 completing (new distro claims it) —
CloudFront will not allow two distributions to hold the same alias
simultaneously, and no distribution serves the domain in between regardless
of what DNS says. Minimizing this window means having the DNS change ready
to fire the instant step 2 completes, and firing step 4 the instant DNS is
confirmed at the authoritative nameserver — not waiting for full global
propagation, which can take much longer than the record's TTL suggests.

### Rollback

Symmetric but **not instant**: swing DNS back to dev's CloudFront domain,
remove the alias from prod, and re-add it to dev (which means re-creating
dev's cert with the fuller SAN list again — likely fast if Aruba's
`pyvar.com`/`www.pyvar.com` validation CNAMEs weren't removed in the
meantime, but not guaranteed instant). This asymmetry should be understood
and accepted before starting the live sequence, not discovered mid-rollback.

## Stage C incident report (2026-08-16)

Two real outages happened while executing the live cutover, both since
fixed by correcting the sequence above. Recorded here so the mistake isn't
repeated on a future domain move in this project.

**Incident 1 — wrong step order (~10 min outage, `www.pyvar.com`/`pyvar.com`
down)**

Followed the *original* sequence in this doc: dropped the alias from dev,
then tried adding it to prod, then planned to swing DNS last. The
prod-alias-add failed immediately with CloudFront's `CNAMEAlreadyExists`
error: *"One or more aliases specified for the distribution includes an
incorrectly configured DNS record that points to another CloudFront
distribution."* Dev had already released the alias, so nothing served the
domain. Restored dev's alias immediately to stop the outage, then
researched the actual cause (confirmed via
[AWS's CNAMEAlreadyExists guidance](https://repost.aws/knowledge-center/resolve-cnamealreadyexists-error)
and
[this writeup of the same CloudFront behavior](https://andyhunt.me/til/2021/04/06/aws-cloudfront-checks-your-domains-dns-records-for-other-cloudfront-distributions/)):
CloudFront checks live DNS at alias-add time, and rejects the add if DNS
still resolves to a *different* distribution — regardless of whether that
distribution's own config still lists the alias. DNS has to move first.

**Incident 2 — Aruba propagation much slower than its TTL (~40+ min outage,
same domains down)**

Retried with the corrected order: dropped the alias from dev, immediately
asked for the `www.pyvar.com` CNAME to be swung directly to prod's
CloudFront domain, then polled for it to appear. Public resolvers didn't
help distinguish "not changed yet" from "cached" — queried Aruba's own
authoritative nameserver directly instead (raw DNS query to
`dns.technorail.com`'s IP, bypassing all resolver caching) and it *still*
returned the old value after ~40 minutes of direct polling. This is not a
TTL/caching issue — the record's TTL only bounds how long *resolvers* cache
an answer once the authoritative source has the new one; it says nothing
about how long the DNS provider itself takes to actually publish a saved
change to its own nameservers. Rather than leave prod down indefinitely
waiting on an unconfirmed external dependency, restored dev's alias again.
That restore attempt itself then failed with the identical
`CNAMEAlreadyExists` error — which turned out to be informative rather than
a new problem: it meant the Aruba change *had* finally landed (just much
later than the polling window covered), so dev could no longer reclaim an
alias that DNS now pointed elsewhere. Recognized this immediately, checked
DNS again (now showing prod's domain, confirmed at both the authoritative
nameserver and public resolvers), and deployed prod directly — succeeded.

**Takeaways for next time (already folded into the corrected sequence
above):**
- Verify DNS changes against the authoritative nameserver directly, not a
  public resolver — a public resolver's cache can look identical to "not
  propagated" and give false confidence either way.
- Do not assume a DNS provider's propagation time is bounded by the
  record's TTL. Aruba's actual propagation for this change took well over
  10x its 300s TTL.
- Set a personal time limit for "wait for an external DNS provider" before
  treating a live outage as needing a rollback instead. Open-ended waiting
  on an unconfirmed third party while production is down is itself a
  choice with a cost.
- A `CNAMEAlreadyExists` error on a *restore* attempt can mean the forward
  change actually succeeded (DNS now conflicts with the OLD distribution
  instead of the new one) — check current DNS state before assuming the
  restore itself is broken.

## Open decisions — resolved

1. **Cert strategy**: resolved 2026-08-15, out-of-band ARN import chosen
   and executed (see "Cert strategy" under Prep tasks above).
2. **Bare `pyvar.com` alias on prod**: resolved, kept for parity with
   dev's historical setup — confirmed explicitly before the live cutover.
   Live on prod's distribution now, per the final state below.

## Status

**COMPLETE.** Final verified state (2026-08-16):
- `pyvar-dev-edge`: aliases = `["dev.pyvar.com"]` only.
- `pyvar-prod-edge`: aliases = `["pyvar.com", "www.pyvar.com"]`, using the
  pre-imported cert (`arn:...certificate/a18950da-...`) — no fresh cert
  created at cutover time.
- `www.pyvar.com` serves prod (`env: prod` confirmed in response body),
  `pyvar.com` still redirects via Aruba's own proxy (unaffected
  throughout), `dev.pyvar.com` still serves dev (unaffected throughout).
- Both stacks' `cdk diff` clean against git — no drift.
- Real traffic on prod's ALB confirmed via CloudWatch `RequestCount`
  immediately after cutover.
- Combined outage across both incidents: roughly 50 minutes total, isolated
  to `pyvar.com`/`www.pyvar.com`; `dev.pyvar.com` and everything else were
  unaffected throughout.

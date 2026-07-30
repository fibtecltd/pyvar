# P8 Task 7 — pyvar.com DNS + SSL verification

Verified: 2026-07-30

## Context

Task 7 (`scripts/claude/prompts/p8-lead-prompt.md`) covers wiring pyvar.com
into ACM/CloudFront. The ACM-cert + CloudFront-alternate-domain-name change
was drafted on `feat/p8-domain-dns-ssl` (commit `68b8667`) in a prior
session but **not deployed** — cert request/validation and `cdk deploy`
both require separate operator confirmation per the task's high-risk
flag, and that step has not been run.

Separately, and blocking any deploy of that branch, Aruba (who host
pyvar.com's DNS/registrar) had two live faults on their side:

1. A stale web-forwarding redirect sending `pyvar.com` → `example.com`.
2. An expired TLS certificate on their forwarding proxy (`62.149.189.55`).

Aruba support fixed both. This document records the from-scratch
verification of that fix, run independently with no assumptions carried
over from the prior session.

## Verification results

| Check | Result |
|---|---|
| `http://pyvar.com` | `301 Moved Permanently` → `Location: https://www.pyvar.com/` (not example.com) |
| `https://pyvar.com` TLS handshake | Completes cleanly, TLSv1.3, `SSL certificate verify ok` |
| `https://pyvar.com` redirect | `301` → `Location: https://www.pyvar.com/` |
| Redirect type | Genuine `301` on both HTTP and HTTPS (not `302`); plain HTML body, no meta-refresh/iframe masking — browser address bar actually changes |
| Full redirect chain | `pyvar.com` → `www.pyvar.com` → CloudFront → ALB → uvicorn (confirmed via `AWSALB`/`x-amz-cf-id` headers) |
| `www.pyvar.com` health | `/health`, `/docs`, `/openapi.json` all return `200`; unaffected by the Aruba-side fix |
| Cert on `62.149.189.55:443` (direct `openssl s_client`, SNI `pyvar.com`) | `CN=*.pyvar.com`, issuer Actalis Domain Validated TLS Server RSA CA 2025, **valid `2026-07-30` → `2027-02-14`** |

Root `/` on the app itself returns a FastAPI `404 {"detail":"Not Found"}`
(no root route defined) — unrelated to DNS/SSL, pre-existing behavior,
not a regression from this fix.

## Status

- **Aruba-side redirect/cert fault: resolved and verified.** pyvar.com now
  correctly reaches the live app via `www.pyvar.com` with a valid
  certificate end to end.
- **ACM/CloudFront alternate-domain-name work (`feat/p8-domain-dns-ssl`):
  still undeployed.** That branch also currently diffs oddly against
  `master` (missing rate-limiting/audit-log work merged since it branched)
  and would need a rebase before it's mergeable — separate from this
  verification, flagged for operator decision on whether it's still
  wanted now that the Aruba-side forwarding fix alone gets pyvar.com
  working end-to-end.

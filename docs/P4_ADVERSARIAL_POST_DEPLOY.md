# P4 Post-Deploy Adversarial Review
## Date: 2026-06-24
## Account: 347228921290 · Primary region: eu-west-1 · Edge region: us-east-1
## Environment: dev · Deploy mode: direct stack-by-stack (`cdk deploy --exclusively`, pipeline bypassed)
## CDK: aws-cdk 2.1128.0 · cloud-assembly schema 54.0.0

---

## 1. Executive summary

The pre-deploy review (`P4_ADVERSARIAL_REVIEW.md`) returned **DEPLOY APPROVED — no
critical findings**. The actual deployment then hit **nine distinct deploy-time
failures across four of the six stacks**, eight of which were code/config defects
requiring source changes, plus one external AWS account restriction.

**Outcome: 5 of 6 stacks deployed and healthy.** The application is live and
verified behind the ALB. Only the `edge` stack (CloudFront + WAF) is outstanding,
blocked by an AWS account-level CloudFront restriction that is **not** a code issue.

The central lesson: **the pre-deploy review validated synthesized CloudFormation
templates and was structurally correct, but template-level validation is blind to
runtime, control-plane, cross-region, image, and account-level failures.** Every
one of the nine failures below was invisible at synth time. "DEPLOY APPROVED" gave
false confidence.

---

## 2. Final stack status

| Stack | Region | Status | Notes |
|---|---|---|---|
| pyvar-dev-network | eu-west-1 | ✅ CREATE_COMPLETE | VPC, subnets, SGs, 6 VPC endpoints |
| pyvar-dev-data | eu-west-1 | ✅ CREATE_COMPLETE | Aurora SV2 16.6 (0.5–2.0 ACU), ElastiCache Serverless (redis), S3 |
| pyvar-dev-queue | eu-west-1 | ✅ CREATE_COMPLETE | SQS FIFO + DLQ + alarms |
| pyvar-dev-compute | eu-west-1 | ✅ CREATE_COMPLETE | EC2 Spot ASG (0/0/5), IMDSv2 enforced |
| pyvar-dev-api | eu-west-1 | ✅ UPDATE_COMPLETE | ECS Fargate 1/1 healthy, ALB active, DB secret replicated |
| **pyvar-dev-edge** | us-east-1 | ⛔ **NOT DEPLOYED** | Blocked: AWS account not verified for CloudFront (external) |

---

## 3. Deploy-time failures (what the pre-deploy review missed)

| # | Stack | Resource | Class | Root cause | Resolution |
|---|---|---|---|---|---|
| 1 | network | `SgAlb` (EC2 SecurityGroup) | Code | `GroupDescription` contained a non-ASCII em-dash (U+2014); EC2 rejects non-ASCII. | `network_stack.py:129` em-dash → ASCII hyphen. |
| 2 | data | `Aurora` (RDS DBCluster) | Code | Engine `VER_16_1` not offered in eu-west-1 (retired minor). | `data_stack.py:69` → `VER_16_6` (operator-chosen). |
| 3 | data | `RedisServerless` (rollback) | Infra/timing | On rollback, ElastiCache delete failed (cache not yet `available`) → **ROLLBACK_FAILED**. | Waited for cache `available`, deleted stack, redeployed. |
| 4 | api | container env `POSTGRES_DSN` | Code | Injected from secret JSON key `connection_string` that does not exist in the Aurora secret. | Inject 5 fields (`DB_HOST/PORT/NAME/USER/PASSWORD`); assemble DSN in app `config.py`. |
| 5 | api | container env `JWT_SECRET` | Code | Referenced `pyvar/dev/jwt-secret` via `from_secret_name_v2` — secret was never created. | Added CDK-managed `Secret` w/ `GenerateSecretString` (`api_stack.py`). |
| 6 | api | `ApiRepo` (ECR Repository) | Code | Repo created with fixed name + `RETAIN`; survived prior cycles, so `create` collided with the existing repo. | `ecr.Repository.from_repository_name(...)` — reference, not create (`api_stack.py:63`). |
| 7 | api | ECS task (image) | Operational | (a) ECR initially empty — no image to pull. (b) After first push, image was **arm64-only**; Fargate task is X86_64. | (a) Operator pushed image. (b) Operator repushed `linux/amd64`. |
| 8 | edge | `WebAcl` (WAFv2) | Code | Managed rule group `AWSManagedRulesCoreRuleSet` does not exist; correct name is `AWSManagedRulesCommonRuleSet`. | `edge_stack.py` → `AWSManagedRulesCommonRuleSet`. |
| 9 | edge | `Distribution` (CloudFront) | Code (x2) | Origin-verify secret unresolvable cross-region: (a) secret only in eu-west-1; (b) first fix used `from_secret_name_v2`, producing a suffix-less ARN that Secrets Manager can't resolve. | (a) `replica_regions=[us-east-1]` on the secret (`api_stack.py`). (b) Resolve **by name** via `cdk.SecretValue.secrets_manager(<name>)` in `edge_stack.py`. |
| 10 | edge | `Distribution` (CloudFront) | **External** | AWS: *"Your account must be verified before you can add new CloudFront resources."* (403 AccessDenied). | **Pending AWS Support** account verification. No code change. |

### Recurring operational pattern (not a code defect, but a deploy hazard)
Stacks containing an **ECS `ClusterCapacityProviderAssociations`** or an
**ElastiCache `ServerlessCache`** repeatedly failed *rollback* with
`ResourceInUseException` / `NotStabilized`, landing in **ROLLBACK_FAILED**. Each
required an explicit `delete-stack` to recover before re-deploy. Expect this on any
failed create of `data`, `api`, or `compute`; budget for the delete/recreate cycle.

---

## 4. Smoke test — live verification (api via ALB, direct)

Target: `http://pyvar-dev-alb-469160645.eu-west-1.elb.amazonaws.com:443`
(internet-facing ALB, single **HTTP listener on port 443**; port 80 has no
listener). The ALB default action is `fixed-response 403` unless the request
carries the correct `X-Origin-Verify` header (per pre-deploy SEC-1 design).

### 4.1 Origin-verify gating (security control)
| Request | Expected | Actual | Verdict |
|---|---|---|---|
| `GET :443/health` — **no** header | 403 | **403** | ✅ gated |
| `GET :443/` — **no** header | 403 | **403** | ✅ gated |
| `GET :80/health` | no listener | **000** (conn refused) | ✅ as designed |

→ Direct-to-ALB requests bypassing the (future) CloudFront/WAF edge are correctly
rejected. The origin-verify secret in the ALB rule matches the replicated value.

### 4.2 Application reachability (with valid `X-Origin-Verify` header)
| Request | Result |
|---|---|
| `GET /health` | **200** · `{"status":"ok","app":"pyvar","env":"dev"}` |
| `GET /docs` | **200** (Swagger UI) |
| `GET /openapi.json` | **200** · title `pyvar.com`, **388 paths** |
| `GET /` | 404 (no root route — expected; app uses `/api/v1` + `/health` + `/docs`) |

### 4.3 Auth gating
| Request | Expected | Actual | Verdict |
|---|---|---|---|
| `POST /api/v1/var/compute` (header, **no JWT**) | 401/403 | **401** | ✅ auth enforced (JWT wiring live) |

### 4.4 Container logs (current running task)
Clean startup: `Uvicorn running on http://0.0.0.0:8000` → `Application startup
complete` (both workers). **No errors, exceptions, or DB-connection failures** in
the stream. This confirms the runtime DSN assembly (failure #4) and JWT injection
(failure #5) are working end-to-end.

### What the smoke test confirms
- Image pulls and runs (failures #6, #7 resolved).
- DB credential injection + DSN assembly works (failure #4) — app started, no DB error.
- JWT secret injection works (failure #5) — auth returns 401, not 500.
- Origin-verify secret + replica is consistent (failure #9) — header matches ALB rule.
- ECS service healthy, ALB target healthy (`10.0.3.5`).

### Not yet verifiable (edge not deployed)
- WAF managed-rule enforcement (failure #8 fix verified only at synth + API level).
- CloudFront caching / TLS termination / WAF at edge.
- End-to-end HTTPS via the public domain.

---

## 5. Source changes applied during deploy

| File | Change |
|---|---|
| `pyvar-cdk/stacks/network_stack.py` | SG description em-dash → ASCII hyphen (#1). |
| `pyvar-cdk/stacks/data_stack.py` | Aurora `VER_16_1` → `VER_16_6` (#2). |
| `pyvar-cdk/stacks/api_stack.py` | DB secret: 5-field injection (#4); CDK-managed jwt-secret (#5); ECR `from_repository_name` (#6); origin-verify secret `replica_regions=[us-east-1]` (#9a). |
| `pyvar-cdk/stacks/edge_stack.py` | WAF `AWSManagedRulesCommonRuleSet` (#8); origin-verify resolve by name via `SecretValue.secrets_manager` (#9b). |
| `config.py` (application) | `db_host/port/name/user/password` settings + `_assemble_postgres_dsn` validator (URL-encoded), local-dev default preserved (#4). |

All changes are **working-tree only — not committed.** They should be committed on
appropriately-named branches (`fix/*`, and the api/data DB-credential change touches
regulatory-adjacent infra; route per CLAUDE.md §8) before the pipeline path is used.

---

## 6. Outstanding items

1. **Edge (BLOCKING for edge only):** Contact AWS Support to verify the account for
   CloudFront. Include error: *"Your account must be verified before you can add new
   CloudFront resources"*, Request ID `2a55d59f-69c9-4e98-96d6-7548589eab04`. On
   approval, redeploy `pyvar-dev-edge` — **no code change required** (WAF + secret
   fixes already in place and synth-verified).
2. **Commit the working-tree fixes** (§5) and re-run the pre-deploy validator so the
   committed assembly matches what was deployed.
3. **Carry forward the pre-deploy follow-ups** from `P4_ADVERSARIAL_REVIEW.md`
   (Image Builder IMDSv2; CF→ALB HTTPS/ACM for end-to-end encryption; validator
   region string `eu-west-2`→`eu-west-1`; remove stale `cross-region-stack-123456789012_*`).
4. **Stale ECR/log-group housekeeping:** three `ApiTaskDefapiLogGroup*` groups and a
   retained ECR repo accumulated from the deploy/recreate cycles — prune.

---

## 7. Process recommendations (adversarial conclusions)

1. **Add a pre-deploy validation layer that the template review cannot cover.**
   The pre-deploy review was structurally sound but blind to: non-ASCII in API-validated
   fields, RDS/ElastiCache engine-version availability *per region*, Secrets Manager
   JSON-key existence vs. the keys ECS injects, out-of-band secret existence, ECR
   repo/image presence and **image architecture**, WAF managed-rule-group **names**,
   cross-region secret resolvability, and account-level service enablement.
   Recommend a scripted "deploy readiness" preflight that queries the live account
   (e.g. `describe-db-engine-versions`, `list-available-managed-rule-groups`,
   `describe-images`/manifest arch, secret key presence, CloudFront account status).
2. **Don't equate "synth + template review pass" with "deployable."** Future P*
   reviews should explicitly scope themselves as template-level and enumerate the
   runtime classes they do **not** cover.
3. **Fixed-name + RETAIN resources are recreate-hostile.** Reference externally-managed
   resources (ECR) rather than recreating them, or drop fixed names.
4. **Prefer the CI/CD pipeline for first deploys.** Several failures (#6, #7) stem from
   the image/repo lifecycle that the pipeline owns; direct stack deploys require the
   repo + correct-arch image to pre-exist.
5. **Expect ROLLBACK_FAILED on data/api/compute** due to ECS capacity-provider /
   ElastiCache rollback races; document the `delete-stack` recovery as standard.

---

## 8. Verdict

**Application tier verified live and healthy (5/6 stacks).** All eight code/config
defects surfaced during deploy were diagnosed and fixed; the runtime smoke test
confirms the data, auth, secret, and image fixes end-to-end. The remaining gap is the
**edge stack, blocked solely by AWS account verification for CloudFront** — code is
ready and will deploy unchanged once AWS clears the account.

---

## ALB-WAF Deploy (Option 1 Fallback) — pyvar-dev-alb-waf

**Date: 2026-06-26**

AWS has **not** verified the account for CloudFront, so `pyvar-dev-edge` cannot
deploy. The Option 1 fallback attaches a **REGIONAL** WAF WebACL directly to the
existing ALB in eu-west-1 — same rule set as the edge WebACL (CommonRuleSet,
KnownBadInputsRuleSet, rate-limit 100/5min/IP), only the scope differs. `pyvar-dev-edge`
was **not** deployed and was not touched.

### Stack status
- Stack: `pyvar-dev-alb-waf` (eu-west-1) — **CREATE_COMPLETE** (97.7s).
- Pre-checks: `cdk synth pyvar-dev-alb-waf` → OK; `pyvar-dev-edge` → **NOT_FOUND** (no cleanup required).
- WAF WebACL ARN (CfnOutput `AlbWafAcl`):
  `arn:aws:wafv2:eu-west-1:347228921290:regional/webacl/pyvar-dev-alb-waf/cb1fc7a6-3db8-49f4-8c98-ba6e13872c71`

### Post-deploy validator results (`scripts/adversarial/p4_post_deploy_validator.md`)

| Check | Result | Evidence |
|---|---|---|
| Live-SG | ✅ PASS | Only ports **80 & 443** carry `0.0.0.0/0` ingress (ALB SG); no open non-80/443 ports anywhere in the VPC. |
| Live-EP | ✅ PASS | All required VPC endpoints **available**: S3, SQS, ECR.api, ECR.dkr, SecretsManager, Logs (+ 3 ElastiCache Serverless). |
| Live-IMDSv2 | ✅ PASS (N/A live) | ASG desired=0 → no workers running; launch template enforces `HttpTokens=required`. |
| Live-ECS | ✅ PASS | `runningTasksCount=1`, pending 0. |
| Live-WAF (adapted to ALB) | ✅ PASS | No CloudFront exists (account unverified). REGIONAL WebACL `pyvar-dev-alb-waf` is **associated with the ALB** (`wafv2 get-web-acl-for-resource`). Live filtering confirmed: `<script>` payload → **403 blocked**; clean `/health` → **200**. |
| SECRET-1 | ✅ PASS | `pyvar/dev/aurora-credentials` contains all injected keys (host, port, dbname, username, password); `jwt-secret` (64 chars) and `cf-origin-verify` (32 chars) present & non-empty. |
| Live-API | ✅ PASS (route registration) | All 8 domains' routes registered — market-risk 71, credit-risk 55, liquidity 40, operational 44, portfolio 50, regulatory 30, derivatives 62, alm 33 (= 385) — and auth-enforced (sample POST per domain without JWT → **401**). Root `/health` → **200**. |

### Validator-script discrepancies (not deploy defects)
1. **Live-WAF** targets CloudFront (`cloudfront list-distributions`); this fallback uses ALB-direct + REGIONAL WAF, so the ALB association was verified instead.
2. **SECRET-1** references `pyvar/dev/db-credentials`; the live secret is `pyvar/dev/aurora-credentials`. All injected field names verified present there.
3. **Live-API** assumes `/api/v1/{domain}/health` endpoints (all returned **404**) — the app never implemented per-domain health routes (no `/health`-suffixed paths among 388). The check's real intent (per-domain route registration) was satisfied via openapi path counts + auth gating.

### Findings
- **CRITICAL: none.**
- **WARNING: none.**

### VERDICT: **P5 CLEARED** (via the ALB-WAF fallback path)
Zero CRITICAL/WARNING live findings. The application tier is healthy and the regional
WAF is live and actively filtering on the ALB. The CloudFront edge (`pyvar-dev-edge`)
remains deferred pending AWS account verification; deploying it later is additive and
does not block P5 through this fallback.

---

## Edge Deploy (CloudFront + WAF) — pyvar-dev-edge [FINAL]

**Date: 2026-06-26**

AWS confirmed CloudFront account verification is resolved, so `pyvar-dev-edge`
(CloudFront + WAFv2 + Route53) was deployed — completing the full 6-stack P4 set.
The three edge fixes that make this work were already on master: WAF managed rule
group name `AWSManagedRulesCommonRuleSet` (#8), `cf-origin-verify` us-east-1
replica (#9a), and name-based secret resolve via `SecretValue.secrets_manager` (#9b).

### Stack status
- Stack: `pyvar-dev-edge` (us-east-1) — **CREATE_COMPLETE** (301s).
- CloudFront distribution: `E1966GF3O9PSF7` — domain `d1mqqddh8gu2qi.cloudfront.net` — **Status Deployed, Enabled**.
- CLOUDFRONT-scope WebACL: `pyvar-dev-waf` —
  `arn:aws:wafv2:us-east-1:347228921290:global/webacl/pyvar-dev-waf/a2bd3085-cff9-4166-81b8-ec8578b9e2e1`

### Post-deploy validator results (edge)

| Check | Result | Evidence |
|---|---|---|
| Live-WAF (CloudFront — validator's original intent) | ✅ PASS | Distribution `WebACLId` non-empty = CLOUDFRONT WebACL `pyvar-dev-waf` (us-east-1); distribution `Deployed`. |
| E2E via CloudFront | ✅ PASS | `GET /health` → **200** `{"status":"ok",...}` (CF injects `X-Origin-Verify` → ALB forwards); `GET /docs` → **200**. |
| WAF filtering at edge | ✅ PASS | `<script>` payload via CloudFront → **403** (CLOUDFRONT WebACL blocks); clean request → 200. |
| Auth via CloudFront | ✅ PASS | Domain POST without JWT → **401**. |
| Viewer protocol | ✅ PASS | `http://` → **301** redirect to HTTPS (`REDIRECT_TO_HTTPS`). |
| Origin not bypassable | ✅ PASS | Direct ALB without `X-Origin-Verify` → **403**. |

Infrastructure checks (Live-SG, Live-EP, Live-IMDSv2, Live-ECS, SECRET-1) are
unchanged from the ALB-WAF run above — all still PASS.

### Defense in depth
Two WAFs are now active with the same rule set: the **CLOUDFRONT**-scope
`pyvar-dev-waf` on the distribution (edge), and the **REGIONAL** `pyvar-dev-alb-waf`
on the ALB (origin). Direct-to-ALB traffic is additionally gated by the
`X-Origin-Verify` secret (403 without it), so the edge cannot be bypassed.

### Findings
- **CRITICAL: none.**
- **WARNING: none.**

### Final P4 state: ALL 6 APPLICATION STACKS DEPLOYED
`network`, `data`, `queue`, `compute`, `api`, `edge` — all CREATE_COMPLETE, plus the
`pyvar-dev-alb-waf` regional WAF. The public entry point is the CloudFront
distribution `d1mqqddh8gu2qi.cloudfront.net` (HTTPS, WAF-protected).

### VERDICT: **P5 CLEARED** — full edge stack live, end-to-end verified.

---

## P5 Pre-Production Hardening — full stack pass

**Date: 2026-06-29**
**Account: 347228921290 · Primary region: eu-west-1 · Edge region: us-east-1**
**Environment: dev · CDK: aws-cdk 2.1128.0**

### P5 changes deployed

| Warning | Stack | Change | Deploy result |
|---|---|---|---|
| W2 | pyvar-dev-compute | Replaced step-scaling (Upper/Lower alarms + 2 policies) with `TargetTrackingScalingPolicy` `ScaleOnQueueDepth` (target=5 msgs/worker, warmup=90s) | ✅ Old alarms/policies deleted; new TT policy created |
| W4 | pyvar-dev-api | `min_healthy_percent=100` on ECS Fargate service | ✅ ECS service updated; rolling deploys now zero-downtime |
| W6 | pyvar-dev-pipeline | `pipeline_type=codepipeline.PipelineType.V2` | ✅ Template updated (pipeline not re-run) |
| W7 Ph.1 | cdk.json | `@aws-cdk/core:defaultCrossStackReferences: "both"` | ✅ All 6 stacks deployed; cross-region writer Lambda + ExportsReader cleaned up |
| W7 Ph.2 | cdk.json | `@aws-cdk/core:defaultCrossStackReferences: "weak"` (SSM-only) | ✅ Consumer (`pyvar-dev-alb-waf`) migrated first; producer (`pyvar-dev-api`) CF Export + writer Lambda + IAM role deleted |
| W3, W5 | — | Acknowledged (no code change) | — |

**W7 migration note:** `"both"` → `"weak"` required a two-step ordered deploy because `pyvar-dev-alb-waf` held a live `Fn::ImportValue` on `pyvar-dev-api`'s ALB export. `pyvar-dev-alb-waf --exclusively` was deployed first (switching it to SSM lookup while the SSM parameter already existed from `"both"`); then `pyvar-dev-api` was deployed to remove the CF Export. Standard `cdk deploy --all` blocked both times until the consumer-first ordering was applied.

### Post-deploy validator results

All checks run via `scripts/adversarial/p4_post_deploy_validator.md` (P5-corrected version).

| Check | Result | Evidence |
|---|---|---|
| Live-SG | ✅ PASS | No `0.0.0.0/0` on non-80/443 ports. ALB SG: 80 (HTTP redirect) + 443 (HTTPS) from internet. API SG: 8000 from ALB SG only. Aurora SG: 5432 from worker + API SGs. Cache SG: 6379 from worker + API SGs. VPC endpoint SGs: 443 from 10.0.0.0/16. Worker SG: no inbound rules. |
| Live-EP | ✅ PASS | 9 endpoints `available`: S3 (gateway), SQS, ECR.api, ECR.dkr, SecretsManager, Logs + 3 ElastiCache Serverless. |
| Live-IMDSv2 | ✅ PASS (N/A) | ASG desired=0 (queue empty); no instances running. Launch template enforces `HttpTokens=required` — enforced on next scale-out. |
| Live-ECS | ✅ PASS | `runningTasksCount=1`, `pendingTasksCount=0`. |
| Live-WAF (CLOUDFRONT) | ✅ PASS | Distribution `d1mqqddh8gu2qi.cloudfront.net` — `WebACLId: arn:aws:wafv2:us-east-1:347228921290:global/webacl/pyvar-dev-waf/a2bd3085-cff9-4166-81b8-ec8578b9e2e1`. |
| Live-WAF (REGIONAL) | ✅ PASS | `list-resources-for-web-acl` for `pyvar-dev-alb-waf` returns ALB ARN `arn:aws:elasticloadbalancing:eu-west-1:347228921290:loadbalancer/app/pyvar-dev-alb/ed0c669f2a63acf2`. Both WAFs active — defence-in-depth intact. |
| SECRET-1 | ✅ PASS | `pyvar/dev/aurora-credentials`: all 5 injected fields present (host, port, dbname, username, password). `pyvar/dev/jwt-secret`: 64-char non-empty. `pyvar/dev/cf-origin-verify`: 32-char non-empty. |
| Live-API (path counts) | ✅ PASS | All 8 domains registered — market-risk 71, credit-risk 55, liquidity 40, operational 44, portfolio 50, regulatory 30, derivatives 62, alm 33 (= 388 total). Identical to P4 baseline — no route regression. |
| Live-API (auth gating) | ✅ PASS | Unauthenticated POST to first real endpoint per domain → **401** on all 8 domains. Tested via openapi.json-derived paths (not the generic `/compute` stub from the validator template, which 404s on all domains). |

### Findings

- **CRITICAL: none.**
- **WARNING: none.**

### Validator note (Live-API auth test)

The validator template tests `POST /api/v1/{domain}/compute` for auth. That generic path does not exist in the app (routes are domain-specific, e.g. `/api/v1/market-risk/historical_simulation_var`), so all domains return 404 with the template's path. The corrected check uses the first real POST endpoint per domain sourced from `/openapi.json` — all 8 return 401, confirming both route registration and auth enforcement.

### Stack status post-P5

| Stack | Region | Status |
|---|---|---|
| pyvar-dev-network | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-queue | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-data | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-compute | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-alb-waf | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-api | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-edge | us-east-1 | ✅ UPDATE_COMPLETE |

### VERDICT: **P5 CLEARED** — zero CRITICAL, zero WARNING. All 7 stacks healthy. Full defence-in-depth (CLOUDFRONT + REGIONAL WAF, origin-verify gating, IMDSv2, SSM-only cross-stack references) confirmed live.

---

## P6 Final Hardening — full stack pass

**Date: 2026-06-30**
**Account: 347228921290 · Primary region: eu-west-1 · Edge region: us-east-1**
**Environment: dev · CDK: aws-cdk 2.1128.0**

### P6 changes deployed

| Item | Stack | Change | Deploy result |
|---|---|---|---|
| Step 1 | pyvar-dev-ami | `CfnInfrastructureConfiguration`: `http_tokens="required"`, `http_put_response_hop_limit=1` — IMDSv2 enforced on Image Builder build instances | ✅ PR #51 merged |
| Step 2 | — | Housekeeping audit: all three items (cdk.out artifacts, stale log groups, retained ECR repo) already resolved in P5 | ✅ No-op |
| Step 3 | pyvar-dev-api / pyvar-dev-edge | ACM cert for `pyvar.com` + `www.pyvar.com` (ISSUED); ALB listener `:443` switched HTTP→HTTPS with cert; HTTP `:80` listener added as CloudFront origin path (origin-verify enforced); edge_stack origin port 443→80 | ✅ PR #52 merged, DNS validated, both stacks UPDATE_COMPLETE |

### cdk synth — all stacks

```
cdk synth --context env=dev --context account=347228921290
Successfully synthesized to /workspace/pyvar/pyvar-cdk/cdk.out
Stacks: pyvar-pipeline, cross-region-stack-347228921290:us-east-1, pyvar-dev-ami,
        pyvar-dev-network, pyvar-dev-data, pyvar-dev-queue, pyvar-dev-compute,
        pyvar-dev-api, pyvar-dev-edge, pyvar-dev-alb-waf
```

Warnings are pre-existing (default listener action replacement on pipeline prod stage, Performance Insights, desiredCapacity). Zero new warnings introduced by P6 changes.

### Post-deploy validator results

All checks run via `scripts/adversarial/p4_post_deploy_validator.md`.

| Check | Result | Evidence |
|---|---|---|
| Live-SG | ✅ PASS | No `0.0.0.0/0` on non-80/443 ports. ALB SG: 80 + 443 from internet. API SG: 8000 from ALB SG only. Aurora SG: 5432 from worker + API SGs. Cache SG: 6379 from worker + API SGs. VPC endpoint SGs: 443 from 10.0.0.0/16. Worker SG: no inbound rules. |
| Live-EP | ✅ PASS | 9 endpoints `available`: S3 (gateway), SQS, ECR.api, ECR.dkr, SecretsManager, Logs + 3 ElastiCache Serverless. |
| Live-IMDSv2 | ✅ PASS (N/A) | ASG desired=0 (queue empty); no instances running. Launch template enforces `HttpTokens=required` — verified on next scale-out. |
| Live-ECS | ✅ PASS | `runningTasksCount=1`, `pendingTasksCount=0`. |
| Live-WAF (CLOUDFRONT) | ✅ PASS | Distribution `d1mqqddh8gu2qi.cloudfront.net` — `WebACLId: arn:aws:wafv2:us-east-1:347228921290:global/webacl/pyvar-dev-waf/a2bd3085-cff9-4166-81b8-ec8578b9e2e1`. |
| Live-WAF (REGIONAL) | ✅ PASS | `get-web-acl-for-resource` for ALB ARN returns `pyvar-dev-alb-waf` — `arn:aws:wafv2:eu-west-1:347228921290:regional/webacl/pyvar-dev-alb-waf/cb1fc7a6-3db8-49f4-8c98-ba6e13872c71`. Both WAFs active — defence-in-depth intact. |
| SECRET-1 | ✅ PASS | `pyvar/dev/aurora-credentials`: all 5 injected fields present (host, port, dbname, username, password). `pyvar/dev/jwt-secret`: 64-char non-empty. `pyvar/dev/cf-origin-verify`: 32-char non-empty. |
| Live-API (path counts) | ✅ PASS | All 8 domains registered — market-risk 71, credit-risk 55, liquidity 40, operational 44, portfolio 50, regulatory 30, derivatives 62, alm 33 (= 385 total). Note: P4/P5 reports stated 388 total; the per-domain counts were always correct and sum to 385 — the 388 figure was a running arithmetic error in those reports. No route regression. |
| Live-API (auth gating) | ✅ PASS | Unauthenticated POST to first real endpoint per domain → **401** on all 8 domains. |

### P6-specific checks

| Check | Result | Evidence |
|---|---|---|
| ALB HTTPS:443 listener | ✅ LIVE | Protocol=HTTPS, cert `arn:aws:acm:eu-west-1:347228921290:certificate/0de8a53d-20e6-457a-a4a0-ae3b8fe419ca` (Status: ISSUED, Domain: pyvar.com + www.pyvar.com) |
| ALB HTTP:80 listener | ✅ LIVE | Protocol=HTTP (CloudFront origin path), origin-verify enforced, default action 403 |
| CloudFront origin port | ✅ UPDATED | `http_port=80` (was 443) — avoids cert-hostname mismatch between pyvar.com cert and ALB DNS name |
| Image Builder IMDSv2 | ✅ CODE | `CfnInfrastructureConfiguration` now has `http_tokens=required`, `http_put_response_hop_limit=1` (deployed at next Image Builder pipeline run) |

### Findings

- **CRITICAL: none.**
- **WARNING: none.**

### Stack status post-P6

| Stack | Region | Status |
|---|---|---|
| pyvar-dev-network | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-queue | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-data | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-compute | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-alb-waf | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-api | eu-west-1 | ✅ UPDATE_COMPLETE (HTTPS:443 + HTTP:80, ACM cert ISSUED) |
| pyvar-dev-edge | us-east-1 | ✅ UPDATE_COMPLETE (origin port 443→80) |
| pyvar-dev-ami | eu-west-1 | ✅ UPDATE_COMPLETE (IMDSv2 required on InfrastructureConfiguration) |

### VERDICT: **P6 CLEARED** — zero CRITICAL, zero WARNING. All 8 stacks healthy. Full pre-production hardening complete: IMDSv2 enforced on Image Builder, ACM TLS certificate live on ALB (HTTPS:443), CloudFront origin-verify protection maintained on new HTTP:80 listener, both WAFs active (defence-in-depth), all 385 API routes registered, auth enforcement confirmed across all 8 risk domains.

---

## P6 Observability & AMI — full stack pass

**Date: 2026-07-15**
**Account: 347228921290 · Primary region: eu-west-1 · Edge region: us-east-1**
**Environment: dev · CDK: aws-cdk 2.1128.0**

All checks run live against AWS (`aws sts get-caller-identity` confirms
`pyvar-cdk-deployer` in account 347228921290) via
`scripts/adversarial/p4_post_deploy_validator.md`, plus targeted checks for the
P6 observability/AMI items below.

### Stack status — all 9 application stacks

| Stack | Region | Status |
|---|---|---|
| pyvar-dev-network | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-data | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-queue | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-compute | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-alb-waf | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-api | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-edge | us-east-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-ami | eu-west-1 | ✅ UPDATE_COMPLETE |
| pyvar-dev-alerts | eu-west-1 | ✅ CREATE_COMPLETE |
| pyvar-dev-observability | eu-west-1 | ✅ UPDATE_COMPLETE |

### AMI

| Item | Result |
|---|---|
| AMI ID | `ami-053d838c9735b7a03` — `describe-images` confirms `State: available`, Name `pyvar-dev-worker-2026-07-10T03-14-10.669Z`. Matches `pyvar-cdk/config.py:48` (`worker_ami_id`, "Hypothesis C — baked AMI (P6), version 1.0.251"). |
| Launch template reference | ASG `pyvar-dev-workers` → `MixedInstancesPolicy.LaunchTemplate` `pyvar-dev-worker` version 19 → `ImageId = ami-053d838c9735b7a03`. Live, not just synth. |
| Cold-start measured time | **avg 3s** (min 0s, max 6s), target <45s — **not re-measured live this run**. Sourced from `ami-cold-start-retrospective.md` (bake-and-test session 2026-07-09→07-10, `scripts/test_cold_start.sh`). The worker ASG is currently `desired=0` (queue empty); getting a *fresh* number would require forcibly scaling the ASG from zero, a live-infra-mutating action out of scope for a read-only validator pass. Treat "avg 3s" as the last-known-good figure, not a result of today's run. |

### CloudWatch dashboard

| Item | Result |
|---|---|
| Dashboard | `pyvar-dev-overview` — `list-dashboards` + `get-dashboard` confirm it exists, 8 widgets. |
| URL | `https://eu-west-1.console.aws.amazon.com/cloudwatch/home?region=eu-west-1#dashboards:name=pyvar-dev-overview` |
| Widget content | 7 live widgets (ALB request rate, ALB 5xx, ALB p95 latency, SQS depth, ASG in-service count, ElastiCache hits/misses, JobCount/JobErrors) + 1 documented follow-up text widget ("Monthly cost to date" — intentionally not built; budget alarm covers it in the meantime). No orphaned metric references found. |
| JobCount/JobErrors data path | Emitted by `tasks/var_task.py` (`put_metric_data`, namespace matches widget query) — this runs on the EC2 worker, which git-clones `master` fresh on every boot (`compute_stack.py`) even under the baked-AMI path, so this metric path reflects current code once a worker next scales up. Not stale. |

### SNS topics + alarms

| Item | Result |
|---|---|
| Topics | `pyvar-dev-alerts` and `pyvar-dev-ops-alerts`, both eu-west-1. Both have one **confirmed** (not pending) email subscription each — `list-subscriptions-by-topic` returns a real `SubscriptionArn`, not `PendingConfirmation`. |
| Alarms → `pyvar-dev-alerts` | `pyvar-dev-api-5xx`, `pyvar-dev-api-latency-p95`, `pyvar-dev-queue-age`, `pyvar-dev-worker-errors` — all `State: OK`. |
| Alarms → `pyvar-dev-ops-alerts` | `pyvar-dev-dlq-depth` — `State: OK`. |
| Other alarms | Target-tracking scaling alarms (ECS CPU/request-count, ASG queue-depth, ASG scale-from-zero) — these route to autoscaling policies, not SNS, by design; several show `INSUFFICIENT_DATA`/`ALARM` because the environment is currently idle (ASG desired=0, ECS running below its scale-up threshold). Expected, not a finding. |
| AWS Budget referenced by dashboard | `pyvar-dev-monthly` ($250 USD) confirmed via `describe-budgets` — exists, matches the dashboard's fallback text widget. |

### `api_usage` table status

| Item | Result |
|---|---|
| Schema | **Provisioned.** Per issue #119, migrations `0001`–`0003` (including `0003_api_usage`) were applied manually against `pyvar-dev` Aurora this cycle — the table now exists. |
| **Write path — CRITICAL** | **The usage-tracking middleware that populates this table is not running in the live environment.** The `pyvar-dev-api` ECS service has a single deployment, created `2026-07-06T12:12:24Z`, running task-definition `pyvar-dev-api:5` with container image digest `sha256:9e0dcf6a…`. That digest is the **most recent image ever pushed** to `pyvar-dev-api` (`:latest`, pushed `2026-07-06T12:10:28Z`). The feature that adds `api/middleware/usage.py`, the `main.py` wiring, and `storage/session.py` (PR #117, merged `2026-07-14T17:59:03Z` — 8 days **after** that image was built) has therefore never been built into an image or deployed. No CodePipeline exists in the account (`list-pipelines` → empty) to have done this automatically. |
| Evidence | `ecs describe-services` → one `PRIMARY` deployment, `createdAt=2026-07-06`. `ecr describe-images` → newest pushed digest = the digest currently running; no image postdates it. `git log` on `api/middleware/usage.py`/`main.py`/`storage/session.py` → all from `2026-07-14`. `codepipeline list-pipelines` → `{"pipelines": []}`. |
| Consequence | Live smoke traffic generated during this run (8 authenticated-domain POSTs) will **not** appear in `api_usage` — the weekly analytics queries in `observability/queries.sql` will return zero rows against a real, schema-correct, but empty table. This reads as "feature shipped" from the git history and CDK stack list alone; it is not shipped from the running container's point of view. |
| Not affected | `tasks/var_task.py` (JobCount/JobErrors) changed in the same window but runs on EC2 workers, which pull `master` via `git clone` at every boot regardless of AMI bake — so that half of the P6 observability work **is** live-current, unlike the ECS-container-based half. |
| Relation to tracked issues | Distinct from #118 (`var_jobs` never written) and #119 (no automated migration step) — this is the same *class* of gap (no CI/CD path from merge → running artifact) applied to the API container image rather than the schema. Not fixed as part of this validator run per instruction; flagged for the same remediation track as #119 (an automated build/deploy step is missing, not just an automated migration step). |

### Post-deploy validator results (`scripts/adversarial/p4_post_deploy_validator.md`)

| Check | Result | Evidence |
|---|---|---|
| Live-SG | ✅ PASS | `describe-security-groups` on `vpc-097b3c05ec5e1b42c`: only `SgAlb` carries `0.0.0.0/0`, on 80 (HTTP redirect) and 443 (HTTPS). Every other SG is scoped to a specific source SG (API←ALB, Aurora/Cache←worker+API, VPC-endpoint SGs←10.0.0.0/16) or has no ingress rules (worker). |
| Live-EP | ✅ PASS | 9 endpoints `available`: S3, SQS, ECR.api, ECR.dkr, SecretsManager, Logs, + 3 ElastiCache Serverless. |
| Live-IMDSv2 | ✅ PASS (N/A live) | No running EC2 instances (ASG desired=0, queue empty) — nothing to sample directly. Launch template `pyvar-dev-worker` v19 enforces `HttpTokens=required`; will apply on next scale-out. |
| Live-ECS | ✅ PASS | `runningTasksCount=1`, `pendingTasksCount=0`. |
| Live-WAF (CLOUDFRONT) | ✅ PASS | Distribution `d1mqqddh8gu2qi.cloudfront.net`, `Status=Deployed`, `Enabled=true`, `WebACLId` = `pyvar-dev-waf` (us-east-1). |
| Live-WAF (REGIONAL) | ✅ PASS | `get-web-acl-for-resource` for the live ALB ARN returns `pyvar-dev-alb-waf` (eu-west-1). Both WAFs active — defence-in-depth intact. |
| SECRET-1 | ✅ PASS | `pyvar/dev/aurora-credentials`: keys present = `host, port, dbname, username, password` (+ `engine`, `dbClusterIdentifier`) — all 5 fields the app injects exist. `pyvar/dev/jwt-secret`: 64 chars, non-empty. `pyvar/dev/cf-origin-verify`: 32 chars, non-empty. |
| Live-API (path counts) | ✅ PASS | Fetched `/openapi.json` live via CloudFront: market-risk 71, credit-risk 55, liquidity 40, operational 44, portfolio 50, regulatory 30, derivatives 62, alm 33 = **385 total**. Matches the P6 baseline exactly — no route regression. |
| Live-API (auth gating) | ✅ PASS | Unauthenticated `POST` to the first real endpoint per domain (sourced from `/openapi.json`, not the generic `/compute` template stub) → **401** on all 8 domains. |
| Origin-verify bypass | ✅ PASS | Direct `GET` to the ALB DNS name for `/health` with no `X-Origin-Verify` header → **403**. CloudFront cannot be bypassed. |

### Findings

**CRITICAL**
1. **`api_usage` write path not live** — see table above. The `pyvar-dev-api` ECS container has not been rebuilt/redeployed since 2026-07-06; the usage-tracking middleware merged 2026-07-14 is not executing. Fix: build and push a new `pyvar-dev-api` image containing current `master`, then `aws ecs update-service --force-new-deployment` (or stand up the CI/CD path tracked under #119's remediation). Re-run this validator afterward and confirm via a fresh image-digest / commit-date comparison, not just a stack-status check.

**WARNING:** none beyond the CRITICAL above.

### VERDICT: **P6 OBSERVABILITY & AMI — BLOCKED (1 CRITICAL)**

Infrastructure is fully healthy: all 9 stacks `*_COMPLETE`, AMI live and correctly referenced, CloudWatch dashboard and both SNS-backed alarm sets live and subscribed, both WAFs active, secrets consistent, all 385 routes registered and auth-enforced. **However, the specific feature this task set out to validate — `api_usage` telemetry — is not actually running in production.** The schema exists (via manual migration, per #119) but the code that writes to it was never deployed to the live container, because no build/deploy step exists to carry an app-code merge into a running ECS task. This is exactly the class of drift the P4 adversarial process exists to catch: git history, CDK `describe-stacks`, and the CDK-level "UPDATE_COMPLETE" all say this shipped; the running container says it didn't. Do not report the P6 observability feature as live until a new image is built, pushed, and deployed, and this validator is re-run against the new deployment.

---

## Remediation — stale `pyvar-dev-api` image (CRITICAL, resolved)

**Date: 2026-07-16**

### What was tried and blocked
An in-session fix was attempted via a temporary CodeBuild project (no local Docker
daemon is available in the automation environment). `codebuild:StartBuild` failed
with `AccountLimitExceededException: Cannot have more than 0 builds in queue for the
account`, reproducible at every compute size. **This account has never had a
successful CodeBuild build** (no CodeBuild projects existed before this session,
and `pyvar-pipeline` — the only stack that would have created one — has never been
deployed). This is the same *class* of AWS account-level restriction as the
CloudFront verification block from the original P4 deploy (§3, failure #10) — not a
code or CDK defect. The temporary CodeBuild project, its IAM role, and the uploaded
source archive were all deleted; no residue left in the account.

### Actual fix
The image was built and pushed from an operator machine with Docker instead:

```bash
docker build --platform linux/amd64 --target runtime \
  -t 347228921290.dkr.ecr.eu-west-1.amazonaws.com/pyvar-dev-api:latest \
  -t 347228921290.dkr.ecr.eu-west-1.amazonaws.com/pyvar-dev-api:bd78478 \
  .
docker push 347228921290.dkr.ecr.eu-west-1.amazonaws.com/pyvar-dev-api:latest
docker push 347228921290.dkr.ecr.eu-west-1.amazonaws.com/pyvar-dev-api:bd78478
```

then `aws ecs update-service --cluster pyvar-dev --service pyvar-dev-api --force-new-deployment`.

### Verification

| Check | Result |
|---|---|
| New image pushed | `2026-07-16T07:29:09Z`, tags `latest` + `bd78478` (commit `bd7847887d1110a5d4879c1a723a5c901030880c` — includes PR #117 usage-tracking middleware). Manifest confirmed `linux/amd64`. |
| ECS deployment | `force-new-deployment` → old task `d45f19e9…` drained/stopped, new task `07da7e8a…` started, target group re-registered, service reached steady state (`rolloutState: COMPLETED`, `failedTasks: 0`). |
| Running image digest | Task `07da7e8a…` → `sha256:82470eb0…`, matches the freshly pushed `:latest` digest exactly. |
| App health | `GET /health` via CloudFront → **200**. Container logs: clean `Application startup complete` on both uvicorn workers, no exceptions (confirms Numba warmup in the new image still succeeds). |
| Route/auth regression check | All 8 domains still 401 unauthenticated, domain-scoped path count still **385** (raw `/openapi.json` total 388 — same `/metrics`+legacy-`/var` delta as before, not a regression). `ECS Running=1/Pending=0` unchanged. |
| `api_usage` write path | Sent a tracked `POST /api/v1/market-risk/historical_simulation_var` (→ 401) through the new container. No `"api_usage write failed"` warning appeared in the task's CloudWatch logs afterward. **Caveat: this is the best signal available without direct DB access** (no ECS Exec, no bastion) — it confirms the absence of a write error, not a row count in Aurora. Recommend a follow-up with DB access (e.g. temporarily enable ECS Exec, or query via `observability/queries.sql` from a worker) to positively confirm row counts before relying on the weekly usage analytics. |

### Updated verdict

**RESOLVED for the container-staleness finding.** The `pyvar-dev-api` service is now running code current with `master` @ `bd78478`, including the `api_usage` middleware. The underlying root cause — **no CI/CD path from a merged commit to a running ECS task** — is not fixed by this one-off redeploy and will recur on the next merge. That gap tracks with #119's finding (no automated migration step) under the same missing piece: an automated build-and-deploy pipeline. Recommend resolving `pyvar-pipeline` deployment (currently blocked by the same CodeBuild account restriction hit above) as a prerequisite, or documenting a manual "rebuild+push+force-new-deployment after every merge touching `api/`, `main.py`, `storage/`, `config.py`" step in the runbook until it is.

---

## `pyvar-dev-monthly` budget raised $250 → $400 (P7 Task 7 follow-up)

**Date: 2026-07-17**

`docs/p7-cost-review.md` (P7 Task 7) found that the AWS Budget's `HEALTHY`
status was misleading: Cost Explorer's `RECORD_TYPE` breakdown showed a
**-$75.88 credit** currently offsetting ~34% of gross usage this period,
and the credit's recurrence/expiry could not be confirmed via CLI (needs
a Billing Console check). Extrapolating **gross** usage (not the
credited net) projected to ~$390-410/month against the previous $250
limit.

`MONTHLY_BUDGET_USD` in `alerts_stack.py` was raised **250 → 400**,
deployed to `pyvar-dev-alerts` via `cdk deploy` (explicit user
confirmation) and verified live (`aws budgets describe-budgets` →
`BudgetLimit.Amount: 400.0`). Both alert thresholds are percentage-based
(`80%`/`100%` of the limit) and rescaled automatically to **$320
actual / $400 forecasted** — no separate threshold edit was needed.

**This sizes the budget to the gross-cost run-rate, not the currently
credited net** — i.e. it does not assume the -$75.88 credit persists.
If the credit turns out to be recurring, $400 leaves comfortable headroom
above the true ~$174-176/month net spend; if the credit expires, $400
still tracks the ~$390-410/month gross projection reasonably tightly
rather than silently absorbing it. The original ~£150/month release-plan
target is **unchanged** by this — this is monitoring headroom, not a
revision of the cost target itself, and the underlying gap (unconfirmed
credit durability) still needs a Billing Console check to close out
properly.

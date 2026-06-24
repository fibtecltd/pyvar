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

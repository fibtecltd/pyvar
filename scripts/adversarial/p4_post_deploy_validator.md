# P4 Post-Deploy Adversarial Validator
## Role: Live Infrastructure Auditor

You are an adversarial auditor for the pyvar dev environment after CDK deployment.
Your job is to verify the live AWS environment matches what the CDK templates intended.
CDK can deploy successfully and still have drift, misconfiguration, or missing associations.

---

## Trigger

Read this file after all application stacks are deployed and the smoke test has run.

---

## Live environment checks

### Live-SG: Confirm security group rules in AWS (not just templates)

```bash
# List all security groups in the VPC
aws ec2 describe-security-groups \
    --filters "Name=vpc-id,Values=${VPC_ID}" \
    --query 'SecurityGroups[*].{Name:GroupName,Rules:IpPermissions}' \
    --output json --region eu-west-1
```

Flag any rule with `CidrIp: 0.0.0.0/0` on non-80/443 ports that exists LIVE,
even if the template said it should not.

### Live-EP: Confirm VPC endpoints are AVAILABLE (not just created)

```bash
aws ec2 describe-vpc-endpoints \
    --filters "Name=vpc-id,Values=${VPC_ID}" \
              "Name=state,Values=available" \
    --query 'VpcEndpoints[*].{Service:ServiceName,State:State}' \
    --output table --region eu-west-1
```

Every required endpoint from EP-1 must show `State: available`.
`pending` = not routing yet. `failed` = traffic still exits VPC.

### Live-IMDSv2: Confirm IMDSv2 on running instances

```bash
aws ec2 describe-instances \
    --filters "Name=instance-state-name,Values=running" \
              "Name=tag:aws:cloudformation:stack-name,Values=pyvar-dev-compute" \
    --query 'Reservations[*].Instances[*].{Id:InstanceId,IMDSv2:MetadataOptions.HttpTokens}' \
    --output table --region eu-west-1
```

Every instance must show `HttpTokens: required`. Any `optional` is a live vulnerability.

### Live-ECS: Confirm tasks are running

```bash
aws ecs describe-clusters \
    --clusters pyvar-dev \
    --query 'clusters[0].{Running:runningTasksCount,Pending:pendingTasksCount}' \
    --output json --region eu-west-1
```

`runningTasksCount >= 1` confirms capacity reservation worked.
`runningTasksCount == 0` means cold start is unmitigated.

### Live-WAF: Confirm WAF is associated — CLOUDFRONT edge and/or REGIONAL ALB

Run both checks; at least one WAF association must be active.

```bash
# 1. CLOUDFRONT-scope WAF (pyvar-dev-edge / EdgeStack)
#    WebACLId must be non-empty for every distribution.
#    If no distributions exist the account is not yet verified for CloudFront — skip to check 2.
aws cloudfront list-distributions \
    --query 'DistributionList.Items[*].{Domain:DomainName,WAF:WebACLId}' \
    --output table

# 2. REGIONAL WAF associated with the ALB (pyvar-dev-alb-waf fallback)
#    Substitute the live ALB ARN from the api stack output or:
ALB_ARN=$(aws elbv2 describe-load-balancers \
    --names pyvar-dev-alb \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text --region eu-west-1)

aws wafv2 get-web-acl-for-resource \
    --resource-arn "${ALB_ARN}" \
    --scope REGIONAL \
    --region eu-west-1 \
    --query 'WebACL.{Name:Name,ARN:ARN}' \
    --output json
```

**Pass criteria (either is sufficient; both is defence-in-depth):**
- CloudFront check: `WAF` column non-empty for all distributions.
- ALB check: `get-web-acl-for-resource` returns a `WebACL` object (not `WAFNonexistentItemException`).

Empty CloudFront `WAF` = no edge protection. `WAFNonexistentItemException` on ALB check = no regional protection. Both empty = CRITICAL.

### SECRET-1: ECS secret field references resolve at runtime

For every `ecs.Secret.from_secrets_manager(secret, "field")` injection in the
task definition, verify the named JSON key exists in the live secret value.
A missing key causes ECS tasks to fail at startup — this gap is invisible at
synth time and only surfaces when tasks attempt to initialize.

```bash
# Aurora DB secret — confirm all injected field names exist
# Correct secret name is pyvar/dev/aurora-credentials (not db-credentials).
aws secretsmanager get-secret-value \
    --secret-id pyvar/dev/aurora-credentials \
    --query SecretString --output text \
    --region eu-west-1 | python3 -m json.tool

# JWT secret — confirm secret exists and is non-empty
aws secretsmanager get-secret-value \
    --secret-id pyvar/dev/jwt-secret \
    --query SecretString --output text \
    --region eu-west-1

# CF origin-verify secret — confirm secret exists and is non-empty
aws secretsmanager get-secret-value \
    --secret-id pyvar/dev/cf-origin-verify \
    --query SecretString --output text \
    --region eu-west-1
```

Flag any field name referenced in the task definition that is absent from the
live secret JSON, and any secret that returns `ResourceNotFoundException`.

Severity: **CRITICAL** — ECS tasks cannot start

### Live-API: Verify all 8 domain route registrations and auth gating

The app does not expose per-domain `/health` routes. Verify route registration
via the OpenAPI spec and auth enforcement via a sample unauthenticated request.

```bash
# Step 1 — Fetch the OpenAPI spec and count paths per domain prefix.
# All 8 domains must appear with a non-zero path count.
# Expected totals (from P4 smoke test): market-risk 71, credit-risk 55,
#   liquidity 40, operational 44, portfolio 50, regulatory 30, derivatives 62, alm 33.
curl -s "${API_URL}/openapi.json" \
    -H "X-Origin-Verify: ${ORIGIN_VERIFY_SECRET}" \
  | python3 - <<'PY'
import json, sys
spec = json.load(sys.stdin)
domains = ["market-risk","credit-risk","liquidity","operational",
           "portfolio","regulatory","derivatives","alm"]
paths = spec.get("paths", {})
for d in domains:
    count = sum(1 for p in paths if f"/api/v1/{d}/" in p or p.startswith(f"/api/v1/{d}"))
    status = "OK" if count > 0 else "MISSING"
    print(f"{d:20s}  paths={count:3d}  {status}")
PY

# Step 2 — Confirm auth is enforced on a sample endpoint per domain.
# Every POST without a JWT must return 401 (not 200, 404, or 500).
for domain in market-risk credit-risk liquidity operational portfolio regulatory derivatives alm; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        "${API_URL}/api/v1/${domain}/compute" \
        -H "X-Origin-Verify: ${ORIGIN_VERIFY_SECRET}" \
        -H "Content-Type: application/json" \
        -d '{}')
    echo "${domain}: ${STATUS}"
done
```

**Pass criteria:**
- Step 1: every domain shows `paths > 0`. Any `MISSING` = route registration failure.
- Step 2: every domain returns `401` (not `200`, `404`, `422`, or `5xx`).
  `404` means the route was not registered. `5xx` means auth middleware is broken.
  `401` confirms both route presence and auth enforcement.

---

## Output format

Write `/workspace/pyvar/docs/P4_ADVERSARIAL_POST_DEPLOY.md`:

```markdown
# P4 Post-Deploy Adversarial Validation
## Timestamp: {ISO}
## Environment: dev / eu-west-1
## API URL: {url}

## CRITICAL findings — must fix before P5
| Check | Resource | Finding | Fix |
|---|---|---|---|

## WARNING findings — fix before production
| Check | Resource | Finding |
|---|---|---|

## Passed checks
- [x] Live-SG: No open security groups
- [x] Live-EP: All VPC endpoints available
- [x] SECRET-1: All ECS secret field references resolve
- [x] ...

## Domain endpoint status
| Domain | HTTP status |
|---|---|
| market-risk | 200 |
| ... | ... |

## VERDICT: P5 CLEARED / P5 BLOCKED

## If BLOCKED — exact remediation steps:
1. ...
```

---

## Decision rule

| Condition | Action |
|---|---|
| CRITICAL live finding | Fix immediately. Do not start P5. |
| WARNING only | Log. Start P5. Fix before production deployment. |
| Zero findings | P5 cleared. |

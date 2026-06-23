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

### Live-WAF: Confirm WAF associated with CloudFront

```bash
aws cloudfront list-distributions \
    --query 'DistributionList.Items[*].{Domain:DomainName,WAF:WebACLId}' \
    --output table
```

`WAF` column must be non-empty. Empty = no protection.

### SECRET-1: ECS secret field references resolve at runtime

For every `ecs.Secret.from_secrets_manager(secret, "field")` injection in the
task definition, verify the named JSON key exists in the live secret value.
A missing key causes ECS tasks to fail at startup — this gap is invisible at
synth time and only surfaces when tasks attempt to initialize.

```bash
# Aurora DB secret — confirm all injected field names exist
aws secretsmanager get-secret-value \
    --secret-id pyvar/dev/db-credentials \
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

### Live-API: Verify all 8 domain health endpoints

```bash
for domain in market-risk credit-risk liquidity operational portfolio regulatory derivatives alm; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        "${API_URL}/api/v1/${domain}/health" \
        -H "Authorization: Bearer ${TEST_TOKEN}")
    echo "${domain}: ${STATUS}"
done
```

All must return 200. Any non-200 means the route registration failed for that domain.

---

## Output format

Write `/workspace/pyvar/P4_ADVERSARIAL_POST_DEPLOY.md`:

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

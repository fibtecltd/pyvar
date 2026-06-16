# P4 — AWS CDK Deployment
# Used by: pyvar-run.sh p4 --mode seq
# Machine: M4 or Intel (sequential, no Agent Teams)
# Requires: AWS credentials in environment, CDK CLI available

Do not ask for confirmation. Do not present options. Execute the steps below immediately.

---

## Environment facts — read before doing anything

- AWS credentials are available via environment variables or instance profile.
  Verify with: `aws sts get-caller-identity` — if this fails, stop and report.
- CDK stacks are pre-written in `/workspace/pyvar/pyvar-cdk/`.
  Working directory for all CDK commands: `cd /workspace/pyvar/pyvar-cdk`
- Python packages, CDK CLI, and AWS CLI are pre-installed.
- The answer to any "how to proceed" question is: follow the steps below in order.

---

## Step 1 — Read context

Read @CLAUDE.md section 3.4 (AWS/CDK rules).
Read @pyvar_release_plan.md Phase 4 section.

---

## Step 2 — Verify prerequisites

```bash
# AWS access
aws sts get-caller-identity

# CDK version
cdk --version

# Target account and region
aws configure get region
```

If `aws sts get-caller-identity` fails: stop immediately and report the error.
Do not proceed without confirmed AWS access.

---

## Step 3 — CDK diff review before any deploy

```bash
cd /workspace/pyvar/pyvar-cdk
cdk diff --context env=dev 2>&1
```

Report on exactly four items before proceeding to deploy:
1. Any change that would cause downtime on an existing deployment
2. Any security group rule that is too permissive (`0.0.0.0/0` on non-public ports)
3. Any missing VPC endpoint for SQS, ECR, Secrets Manager, or S3
4. Whether IMDSv2 is enforced on all EC2 instances

If any of items 2–4 are present: fix the CDK stack before deploying.
If item 1 is present: report it but proceed if it is expected for a first deployment.

---

## Step 4 — Bootstrap CDK

```bash
# eu-west-2 — primary region
cdk bootstrap aws://$(aws sts get-caller-identity --query Account --output text)/eu-west-2

# us-east-1 — required for CloudFront WAF
cdk bootstrap aws://$(aws sts get-caller-identity --query Account --output text)/us-east-1
```

---

## Step 5 — Deploy stacks in dependency order

Deploy one stack at a time. After each deployment, confirm it shows
`✅  pyvar-dev-[stack] (no changes)` or a clean CREATE/UPDATE before proceeding.
Do not deploy the next stack if the current one fails.

```bash
cd /workspace/pyvar/pyvar-cdk

cdk deploy pyvar-dev-network --require-approval never
cdk deploy pyvar-dev-data    --require-approval never
cdk deploy pyvar-dev-queue   --require-approval never
cdk deploy pyvar-dev-compute --require-approval never
cdk deploy pyvar-dev-api     --require-approval never
cdk deploy pyvar-dev-edge    --require-approval never
```

---

## Step 6 — Set secrets in Secrets Manager

```bash
# JWT signing secret
aws secretsmanager create-secret \
    --name pyvar-dev/JWT_SECRET \
    --secret-string "$(openssl rand -hex 32)" \
    --region eu-west-2

# Confirm DB credentials secret exists (created by data stack)
aws secretsmanager describe-secret \
    --secret-id pyvar-dev/db-credentials \
    --region eu-west-2
```

---

## Step 7 — Run Alembic migrations

```bash
cd /workspace/pyvar
# Retrieve DB endpoint from stack outputs
DB_HOST=$(aws cloudformation describe-stacks \
    --stack-name pyvar-dev-data \
    --query "Stacks[0].Outputs[?OutputKey=='AuroraEndpoint'].OutputValue" \
    --output text \
    --region eu-west-2)

echo "DB_HOST=$DB_HOST"
python scripts/db.py upgrade
```

---

## Step 8 — Trigger AMI baking pipeline

```bash
# Start CodeBuild project that bakes the Numba-precompiled AMI
aws codebuild start-build \
    --project-name pyvar-ami-baker \
    --region eu-west-2

# Poll until complete (up to 30 min)
aws codebuild batch-get-builds \
    --ids $(aws codebuild list-builds-for-project \
        --project-name pyvar-ami-baker \
        --sort-order DESCENDING \
        --query 'ids[0]' --output text \
        --region eu-west-2) \
    --query 'builds[0].buildStatus' \
    --output text \
    --region eu-west-2
```

Verify the latest AMI in the launch template has `numba-cache=precompiled` tag.

---

## Step 9 — Smoke test

```bash
cd /workspace/pyvar

# Get API endpoint from stack outputs
API_URL=$(aws cloudformation describe-stacks \
    --stack-name pyvar-dev-api \
    --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
    --output text \
    --region eu-west-2)

echo "API_URL=$API_URL"

# Health check
curl -f "$API_URL/health" && echo "Health: OK"

# VaR compute (uses create_access_token for test JWT)
python - <<'PYEOF'
from api.middleware.auth import create_access_token
token = create_access_token(user_id="smoke-test", tier="pro")
print(f"Bearer {token}")
PYEOF
```

Then run the smoke test script:
```bash
bash scripts/smoke_test.sh "$API_URL"
```

If `scripts/smoke_test.sh` does not exist, write it now per the spec in
@pyvar_release_plan.md Phase 4 (curl + jq only, no Python, exit 0/1).

---

## Step 10 — Deploy CI/CD pipeline stack

```bash
cd /workspace/pyvar/pyvar-cdk
cdk deploy pyvar-pipeline --require-approval never
```

Verify self-mutation: the pipeline should run once and show a self-update stage.

---

## Step 11 — Configure CloudWatch dashboards

```bash
aws cloudwatch put-dashboard \
    --dashboard-name pyvar-dev-overview \
    --dashboard-body file:///workspace/pyvar/pyvar-cdk/dashboards/overview.json \
    --region eu-west-2 2>/dev/null || \
    echo "Dashboard JSON not found — skip, create manually in console."
```

---

## Step 12 — Final report

```
P4 COMPLETE — AWS dev environment deployed
  Network stack:   ✅ / ❌
  Data stack:      ✅ / ❌
  Queue stack:     ✅ / ❌
  Compute stack:   ✅ / ❌
  API stack:       ✅ / ❌
  Edge stack:      ✅ / ❌
  Pipeline stack:  ✅ / ❌

Smoke test:  PASS / FAIL
AMI cold start: [N]s (target < 30s)
API URL: [url]

Outstanding items (if any):
  [list anything that requires operator action]
```

Write `CHECKPOINT.md` after each stack deployment.
Write `CONTEXT_EXHAUSTED.md` if context is running low — do not stop abruptly.

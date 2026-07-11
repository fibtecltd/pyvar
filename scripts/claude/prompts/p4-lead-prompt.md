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

## If AWS credentials are unavailable at session start

Do not ask which option to take. Proceed automatically with:
1. Review all CDK stacks against CLAUDE.md §3.4 rules
2. Run `cdk synth` for all stacks and report synthesis errors
3. Write `scripts/smoke_test.sh` per Phase 4 spec (curl + jq only, exit 0/1)
4. Commit all outputs to current branch

Then write CHECKPOINT.md noting that Steps 4–12 require credentials and rebuild.

---

## Step 1 — Read context

Read @CLAUDE.md section 3.4 (AWS/CDK rules).
Read @docs/pyvar_release_plan.md Phase 4 section.

---

## Step 1a — Bootstrap missing tools

```bash
# Deterministic: install if missing, verify immediately after
python3 -c "import awscli, boto3" 2>/dev/null \
    || pip install awscli boto3 --break-system-packages
python3 -c "import awscli, boto3; print('awscli OK')"
aws --version 2>/dev/null || python3 -m awscli --version
```

Do not stop if `pip install` is needed — just run it and continue.

---

## Step 2 — Verify prerequisites

```bash
aws sts get-caller-identity 2>&1 || \
  python3 -m awscli sts get-caller-identity 2>&1
```

If this returns an account ID: proceed to Step 3.
If it returns a credentials error (not a CLI error): stop and report.
If the CLI is missing despite Step 1a: run `pip install awscli --break-system-packages` and retry once.

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

## Step 3a — Pre-deploy adversarial review (mandatory gate)

Run `cdk synth --context env=dev --quiet` first to generate templates in `cdk.out/`.
Then read @scripts/adversarial/p4_pre_deploy_validator.md and execute the full review.
Write `/workspace/pyvar/docs/P4_ADVERSARIAL_REVIEW.md`.

**Do not proceed to Step 4 until VERDICT = DEPLOY APPROVED.**
If blocked: fix the CDK code, re-synth, re-review.

---

## Step 4 — Bootstrap CDK

```bash
# eu-west-1 — primary region
cdk bootstrap aws://$(aws sts get-caller-identity --query Account --output text)/eu-west-1

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
    --region eu-west-1

# Confirm DB credentials secret exists (created by data stack)
aws secretsmanager describe-secret \
    --secret-id pyvar-dev/db-credentials \
    --region eu-west-1
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
    --region eu-west-1)

echo "DB_HOST=$DB_HOST"
python scripts/db.py upgrade
```

---

## Step 8 — Trigger AMI baking pipeline

```bash
# Start CodeBuild project that bakes the Numba-precompiled AMI
aws codebuild start-build \
    --project-name pyvar-ami-baker \
    --region eu-west-1

# Poll until complete (up to 30 min)
aws codebuild batch-get-builds \
    --ids $(aws codebuild list-builds-for-project \
        --project-name pyvar-ami-baker \
        --sort-order DESCENDING \
        --query 'ids[0]' --output text \
        --region eu-west-1) \
    --query 'builds[0].buildStatus' \
    --output text \
    --region eu-west-1
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
    --region eu-west-1)

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
@docs/pyvar_release_plan.md Phase 4 (curl + jq only, no Python, exit 0/1).

---

## Step 9a — Post-deploy adversarial validation

Read @scripts/adversarial/p4_post_deploy_validator.md and execute the live checks.
Write `/workspace/pyvar/docs/P4_ADVERSARIAL_POST_DEPLOY.md`.

**Do not proceed to Step 10 until VERDICT = P5 CLEARED.**

---

## Step 10 — Deploy CI/CD pipeline stack

**SKIP for now if no production AWS account exists yet.** The pipeline stack
deploys a Dev→Prod promotion pipeline; without a real prod account this stage
cannot synthesize. Revisit once a prod account is provisioned.

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
    --region eu-west-1 2>/dev/null || \
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
Pre-deploy review:  APPROVED (N critical / M warnings)
Post-deploy review: CLEARED / N findings
AMI cold start: [N]s (target < 30s)
API URL: [url]

Outstanding items (if any):
  [list anything that requires operator action]
```

Write `CHECKPOINT.md` after each stack deployment.
Write `CONTEXT_EXHAUSTED.md` if context is running low — do not stop abruptly.

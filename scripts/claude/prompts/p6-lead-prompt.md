# P6 — Usage Statistics & Observability
# Used by: scripts/claude/run.sh p6
# Machine: M4, sequential mode (no Agent Teams — tasks are sequential/dependent)
# Prerequisite: P5b complete, master clean

This task list has already been reviewed and approved by the operator.
Proceed autonomously through routine work — reading files, writing code,
running local tests, profiling, benchmarking — without asking for
confirmation on each step.

Confirm with the operator before: forcing/terminating EC2 instances,
changing IAM policy or grants in any *_stack.py, running cdk deploy, or
pushing/merging branches.

The answers to routine "how should I proceed" questions are already
provided below.

---

## Environment facts

- AWS account: 347228921290, primary region: eu-west-1, edge: us-east-1
- All 7 app stacks + pyvar-dev-alb-waf are UPDATE_COMPLETE
- CDK: aws-cdk 2.1128.0, Python stacks under pyvar-cdk/stacks/
- Post-deploy validator: scripts/adversarial/p4_post_deploy_validator.md
- gh CLI available for PR creation and merging
- Master is clean — pull before starting

---

## P6 scope — work through in this order, stop after each task and await
## confirmation before proceeding to the next.

---

### Task 1 — Hypothesis C: AMI Image Builder (cold start <45s)

**Context:** Hypothesis B (git clone + pip install at boot) takes 15-20 min.
The P4 `pyvar-dev-ami` Image Builder stack exists but was never triggered.
Pre-baking `requirements-heavy.txt` into the AMI eliminates runtime install
and reduces cold start to <30s.

Steps:
1. Read pyvar-cdk/stacks/ami_stack.py in full
2. Verify the Image Builder pipeline is correctly configured:
   - It installs requirements-heavy.txt + requirements.txt
   - It bakes pycurl>=7.45.0
   - It does NOT bake application code (pyvar source) — code comes from git clone
   - IMDSv2 http_tokens=required (pre-prod warning from P4)
3. Trigger the Image Builder pipeline:
   aws imagebuilder start-image-pipeline-execution \
     --image-pipeline-arn <pipeline-arn> --region eu-west-1
4. Wait for the pipeline to produce a new AMI (typically 15-30 min).
   Poll: aws imagebuilder list-image-pipeline-images \
     --image-pipeline-arn <pipeline-arn> --region eu-west-1
5. Once AMI is available, update compute_stack.py to use the new AMI ID
6. Deploy: cdk deploy pyvar-dev-compute --context env=dev \
     --context account=347228921290 --require-approval never
7. Verify launch template now references the new AMI

Branch: feat/p6-ami-bake
Commit: "feat(compute): Hypothesis C — baked AMI eliminates runtime pip install"

---

### Task 2 — cold start test pass with baked AMI

Run: bash scripts/test_cold_start.sh

With the baked AMI:
- Boot time: ~30-60s (no pip install)
- Celery startup: ~5s
- VaR computation: ~4s
- Expected total: <90s

If the test still times out:
1. Check MAX_WAIT_S in scripts/test_cold_start.sh — set to 300s
2. Run the SSM diagnostic to confirm the AMI has the correct packages:
   python3.11 -c "import numpy, scipy, numba, pycurl; print('OK')"
3. Fix any issues found and re-run

The test PASSES when at least 1 of 3 runs shows a numeric result < COLD_TARGET_S.
Update COLD_TARGET_S from 45 to a realistic value based on measured results.
Document the measured cold-start time in docs/P4_ADVERSARIAL_POST_DEPLOY.md.

Branch: fix/p6-cold-start-target
Commit: "fix(p5b): update COLD_TARGET_S to measured value with baked AMI"

---

### Task 3 — CloudWatch custom metrics and alarms

Create observability/metrics.py with CloudWatch custom metrics:

1. **Per-domain job metrics** (publish every job completion):
   - Namespace: pyvar/jobs
   - Metrics: JobDuration, JobCount, JobErrors — dimensions: Domain, Tier

2. **Queue depth alarm** (already exists via target tracking — verify and document):
   - pyvar-dev-queue-age alarm — confirm threshold and notification

3. **API latency alarm:**
   - ALB TargetResponseTime p95 > 5s → SNS notification
   - Create SNS topic: pyvar-dev-alerts
   - Subscribe info@fibtec.co.uk

4. **Worker error alarm:**
   - CloudWatch Logs metric filter on /pyvar/dev/worker-init log group
   - Filter: ERROR or CRITICAL in journal
   - Alarm: > 5 errors in 5 minutes → SNS

5. **Cost alarm:**
   - AWS Budgets: monthly budget £150 → alert at 80% (£120)

Branch: feat/p6-cloudwatch-alarms
Commit: "feat(observability): CloudWatch alarms + SNS notifications + cost budget"

---

### Task 4 — Usage statistics dashboard

Create a CloudWatch dashboard: pyvar-dev-overview

Widgets to include:
1. API request rate (ALB RequestCount, 5-min period)
2. API error rate (ALB HTTPCode_Target_5XX_Count)
3. API p95 latency (ALB TargetResponseTime p95)
4. SQS queue depth (ApproximateNumberOfMessagesVisible)
5. Worker ASG instance count (GroupInServiceInstances)
6. Job success rate (custom metric JobCount vs JobErrors)
7. ElastiCache hits/misses (CacheHits, CacheMisses — if available)
8. Monthly cost to date (from Cost Explorer via Lambda → CloudWatch)

Implement as:
a) pyvar-cdk/stacks/observability_stack.py — new CDK stack
b) Deploy: cdk deploy pyvar-dev-observability \
     --context env=dev --context account=347228921290 --require-approval never

Branch: feat/p6-dashboard
Commit: "feat(observability): CloudWatch dashboard — pyvar-dev-overview"

---

### Task 5 — per-domain usage analytics in Aurora

Add usage tracking to the API layer:

1. Alembic migration: add api_usage table
   Columns: id, domain, function_name, tier, duration_ms, status, created_at

2. FastAPI middleware: log every compute request to api_usage after completion
   (async, non-blocking — do NOT add latency to the hot path)

3. Weekly summary query (SQL, document in observability/queries.sql):
   - Top 10 functions by call volume
   - P95 duration per domain
   - Error rate per tier

Branch: feat/p6-usage-analytics
Commit: "feat(observability): api_usage table + async usage tracking middleware"

---

### Task 6 — asyncio_mode pytest warning fix

Fix the `asyncio_mode` unknown config option warning:

Check pyproject.toml or pytest.ini for asyncio_mode setting.
If pytest-asyncio is not in requirements.txt, either:
a) Add pytest-asyncio to requirements.txt (if async tests exist), OR
b) Remove asyncio_mode from config (if no async tests)

Check first: grep -r "async def test_" tests/
If no async tests exist → option b is correct.

Branch: fix/p6-pytest-asyncio-warning
Commit: "fix(test): resolve asyncio_mode unknown config warning"

---

### Task 7 — SSM Session Manager plugin in Dockerfile

Add the SSM Session Manager plugin to claude-docker Dockerfile so interactive
SSM sessions work from inside the container (avoids needing send-command workaround).

The plugin is an AWS binary — install in the claude-docker Dockerfile:
RUN curl -fsSL \
  "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" \
  -o /tmp/ssm-plugin.deb && \
  dpkg -i /tmp/ssm-plugin.deb && \
  rm /tmp/ssm-plugin.deb

This goes in the claude-docker repo Dockerfile, not the pyvar repo.
Commit to: fibtecltd/claude-docker feat/p6-ssm-plugin
Then rebuild: docker compose build (in ~/claude-docker)

---

### Task 8 — Post-deploy adversarial validator run

After all P6 changes are deployed:
1. Run the post-deploy validator: scripts/adversarial/p4_post_deploy_validator.md
2. Append results to docs/P4_ADVERSARIAL_POST_DEPLOY.md:
   "## P6 Observability & AMI — full stack pass"
   covering: all stack statuses, AMI ID, cold-start measured time,
   CloudWatch dashboard URL, validator results.
   Do NOT modify any existing sections.

---

## P6 exit gate

All of the following must be true before declaring P6 complete:
- [ ] Baked AMI deployed to compute stack
- [ ] test_cold_start.sh: at least 1/3 runs SUCCESS
- [ ] CloudWatch dashboard pyvar-dev-overview live
- [ ] SNS alarm notifications configured (info@fibtec.co.uk)
- [ ] Cost budget £150/month configured
- [ ] api_usage table migrated and middleware active
- [ ] asyncio_mode warning resolved
- [ ] SSM plugin in claude-docker
- [ ] Post-deploy validator: 0 CRITICAL / 0 WARNING
- [ ] docs/P4_ADVERSARIAL_POST_DEPLOY.md updated

## P6 carry-forward to P7 (do not attempt in this session)
- DNSSEC activation on Aruba (tracked since P4)
- chaos_test.sh manual execution (after cold start stable)
- W2-W7 pre-production warnings (carried from P5)
- Cost & performance optimisation (P7 scope per release plan)

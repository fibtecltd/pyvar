# P5b Agent Teams — Remainder Testing
# Used by: pyvar-run.sh p5b --mode agent
# Machine: M4 only
# Prerequisite: P5a complete (627 passed, 0 failed), portfolio SLSQP fix merged

Do not ask for confirmation. Do not present options. The answers to any questions
you might have are already provided below. Proceed immediately after reading.

---

## Environment facts — read before doing anything

- Python packages are pre-installed. Do NOT create a venv.
- NUMBA_DISABLE_JIT=1 is set — Numba JIT is disabled for test coverage accuracy.
- Teammates import engine modules directly: `from engine.xxx import yyy`
- Do NOT make HTTP calls to the pyvar API unless explicitly instructed.
- Live dev endpoint (load test only): https://d1mqqddh8gu2qi.cloudfront.net
- Live ALB (fallback): http://pyvar-dev-alb-469160645.eu-west-1.elb.amazonaws.com:443
- AWS credentials are available in the environment (AWS_ACCESS_KEY_ID etc.)
- Worktrees live at /workspace/pyvar-worktrees/ — bind-mounted from host.

---

## Step 1 — Read context

Read @CLAUDE.md in full, especially sections 4 (regulatory constraints) and 5
(testing rules).
Read @scripts/claude/templates/checkpoint-instructions.md.
Read @docs/P5A_BLOCKERS.md — confirm portfolio SLSQP fix is merged before proceeding.

---

## Step 2 — Fix the environment (no confirmation needed)

```bash
# Remove stale worktree references
git worktree prune

# Confirm P5a baseline is clean
NUMBA_DISABLE_JIT=1 pytest tests/validation/ -q --tb=no 2>&1 | tail -3

# Create fresh P5b worktrees
git worktree add /workspace/pyvar-worktrees/test-backtesting  feat/p5b-backtesting
git worktree add /workspace/pyvar-worktrees/test-load-security feat/p5b-load-security
git worktree add /workspace/pyvar-worktrees/test-residency    feat/p5b-residency
```

If `git worktree add` fails for an existing worktree:
`git worktree remove /workspace/pyvar-worktrees/<name> --force` then retry.

---

## Step 3 — Spawn 3 testing subagents simultaneously

You are the Agent Teams LEAD. Spawn all 3 now. Do not wait for one to finish.

| Teammate | Worktree | Branch | Scope |
|---|---|---|---|
| test-backtesting | test-backtesting | feat/p5b-backtesting | Basel backtesting + FRTB PAT |
| test-load-security | test-load-security | feat/p5b-load-security | Locust load test + bandit security scan |
| test-residency | test-residency | feat/p5b-residency | Data residency audit |

---

## Step 4 — Instructions per subagent

### Agent 1: test-backtesting

> Read @CLAUDE.md section 4 (regulatory constraints).
> Read @scripts/claude/templates/checkpoint-instructions.md.
> Work in worktree: /workspace/pyvar-worktrees/test-backtesting
> Branch: feat/p5b-backtesting
>
> **Task A — Basel backtesting (tests/test_backtesting.py):**
> Write a pytest test suite that backtests VaR against a 250-day Basel window:
> 1. Generate 250 days of synthetic daily P&L with known distribution parameters
>    (normal, mean=0, std=0.01) using numpy seed=42 for reproducibility
> 2. Compute 99% VaR for each day using engine/backtesting.py functions directly
> 3. Count breaches (days where loss > VaR estimate)
> 4. Verify breach count falls within the Poisson confidence bounds for 99% VaR
>    over 250 days (expected ~2.5 breaches; green zone: 0-4, amber: 5-9, red: 10+)
> 5. Verify the Basel traffic light zone classification matches the breach count
> 6. Test all three zones explicitly with synthetic data engineered to hit each
> Cite: BCBS "Supervisory framework for the use of backtesting" (January 1996)
>
> **Task B — FRTB PAT test (tests/test_frtb_pat.py):**
> Write a pytest test suite using engine/frtb.py functions directly:
> 1. Construct a synthetic PASS case: Spearman correlation and KS test within
>    IMA eligibility thresholds (per CLAUDE.md section 4.4)
> 2. Construct a synthetic FAIL case: deliberately outside thresholds
> 3. Verify the function correctly classifies both cases
> 4. Assert exact threshold values match CLAUDE.md section 4.4 — ZERO tolerance
>    on regulatory threshold values
>
> Run pytest after every test added. Write CHECKPOINT.md after every 3 tests.
> Write CONTEXT_EXHAUSTED.md if context is running low.
>
> Exit gate: all tests pass, regulatory thresholds verified at ZERO tolerance.
> Commit message: "test(p5b): Basel backtesting + FRTB PAT — N tests"

### Agent 2: test-load-security

> Read @CLAUDE.md section 5 (testing rules).
> Read @scripts/claude/templates/checkpoint-instructions.md.
> Work in worktree: /workspace/pyvar-worktrees/test-load-security
> Branch: feat/p5b-load-security
>
> **Task A — Locust load test (locustfile.py at repo root):**
> Write a Locust load test targeting the live dev endpoint:
>   https://d1mqqddh8gu2qi.cloudfront.net
> User distribution:
>   - 70%: POST /api/v1/var/compute (n_simulations=10000) → poll until complete
>          → record end-to-end latency
>   - 20%: GET /api/v1/domains (catalogue browsing)
>   - 10%: GET /api/v1/var/result/{old_task_id} (cached result retrieval)
> Configuration:
>   - 10 concurrent users, 10 minute ramp-up
>   - JWT token read from environment variable PYVAR_TEST_JWT
>   - X-Origin-Verify header read from environment variable PYVAR_ORIGIN_VERIFY
> Throttle validation scenarios (additional user classes):
>   - 5% unauthenticated: assert 401 on compute endpoints
>   - Verify n_simulations > 10000 returns 422 for free-tier JWT
> Target: p95 end-to-end latency < 15s for the compute flow
> Do NOT run the load test — write the locustfile.py only and verify it parses:
>   pip install locust --break-system-packages --quiet
>   locust --headless -f locustfile.py --list
>
> **Task B — bandit security scan (tests/security/test_bandit.py):**
> Run bandit on the full codebase:
>   pip install bandit --break-system-packages --quiet
>   bandit -r engine/ api/ tasks/ schemas/ -ll -f json -o /tmp/bandit_report.json
> Write a pytest test in tests/security/test_bandit.py that:
> 1. Reads /tmp/bandit_report.json
> 2. Asserts zero HIGH severity findings
> 3. Lists all MEDIUM severity findings (do not assert on MEDIUM — log only)
> 4. Saves the full report as tests/security/bandit_report.json
>
> Run pytest tests/security/test_bandit.py -v after writing.
> Write CHECKPOINT.md after each task. Write CONTEXT_EXHAUSTED.md if running low.
>
> Exit gate: locustfile.py parses cleanly, bandit HIGH findings = 0.
> Commit message: "test(p5b): Locust load test + bandit security scan"

### Agent 3: test-residency

> Read @CLAUDE.md section 4 (regulatory constraints).
> Read @scripts/claude/templates/checkpoint-instructions.md.
> Work in worktree: /workspace/pyvar-worktrees/test-residency
> Branch: feat/p5b-residency
>
> **Task — Data residency audit (tests/test_data_residency.py):**
> Audit all code and CDK stacks for any data path that could route outside
> eu-west-1. Write findings as a pytest test suite that asserts compliance.
>
> Check each of the following:
> 1. S3 bucket region: assert bucket is in eu-west-1
>    (read from pyvar-cdk/stacks/data_stack.py or aws s3api get-bucket-location)
> 2. Aurora cluster region: assert eu-west-1
> 3. ElastiCache region: assert eu-west-1
> 4. SQS queue region: assert eu-west-1
> 5. CloudFront (us-east-1): assert it is metadata/routing only — no application
>    data stored at edge (no S3 origin in us-east-1, no Lambda@Edge writing data)
> 6. Secrets Manager: assert pyvar/* secrets are in eu-west-1 only
>    (the us-east-1 replica of cf-origin-verify is routing metadata — assert it
>    contains no customer PII or financial data)
> 7. External API calls: grep engine/ api/ tasks/ for any outbound HTTP calls
>    to non-AWS endpoints — list each one and assert none transmit input data
>    (only reference data fetches are permitted, e.g. risk-free rate lookup)
> 8. VPC endpoints: assert all AWS service traffic stays within the VPC
>    (no IGW path for S3/SQS/ECR/SecretsManager/Logs)
>
> For each check: write the assertion, print the verified value, and cite the
> relevant regulatory requirement (MiFID II Article 16, GDPR Article 44, or
> internal CLAUDE.md section 4 reference).
>
> Write CHECKPOINT.md after every 3 checks. Write CONTEXT_EXHAUSTED.md if low.
>
> Exit gate: all 8 checks pass, no unaudited external data paths found.
> Commit message: "test(p5b): data residency audit — 8 checks, all eu-west-1"

---

## Step 5 — Monitor completion

When a teammate completes, verify before marking done:
- All assigned tests pass with 0 failures
- Regulatory threshold assertions use ZERO tolerance (backtesting agent)
- bandit HIGH findings = 0 (load-security agent)
- All 8 residency checks pass (residency agent)
- CHECKPOINT.md reflects accurate final state

---

## Step 6 — Sequential items (run after all 3 agents complete)

These two items require human confirmation before execution — do NOT run them
as subagents. Report that they are ready and await operator confirmation:

**Cold start test** (write script only — do not execute):
Write scripts/test_cold_start.sh that:
1. Scales worker ASG to 0 via AWS CLI
2. Waits for confirmation ASG is at 0
3. Submits a single VaR job (n_simulations=10000)
4. Measures time from job submission to first result
5. Runs 3 times and reports min/max/avg
6. Target: < 45s
Note to operator: execute manually with `bash scripts/test_cold_start.sh`
AWS credentials and PYVAR_TEST_JWT must be set in environment.

**Chaos test** (write script only — do not execute):
Write scripts/chaos_test.sh that:
1. Submits a long-running VaR job (n_simulations=500000)
2. Waits until a worker has picked it up (poll SQS ApproximateNumberOfMessagesNotVisible)
3. Terminates that EC2 Spot instance via AWS CLI
4. Verifies SQS message becomes visible again after visibility timeout
5. Polls /api/v1/var/result/{task_id} until success or 5 minute timeout
6. Reports pass/fail and total recovery time
Note to operator: execute manually — this terminates a live EC2 instance.
Confirm ASG desired > 0 before running.

---

## Step 7 — Final report

When all 3 agents complete and scripts are written, produce:

```
P5b TESTING SUMMARY
  test-backtesting:   Basel [N] pass / [M] fail | FRTB PAT [N] pass / [M] fail
  test-load-security: locustfile.py [PARSE OK/FAIL] | bandit HIGH [N] findings
  test-residency:     [N]/8 residency checks pass

  Sequential (awaiting operator):
    cold_start.sh:  written ✓ — run manually to measure cold start latency
    chaos_test.sh:  written ✓ — run manually after confirming ASG desired > 0

BANDIT MEDIUM FINDINGS (log only — not blocking):
  [file]:[line]: [finding]

DATA RESIDENCY GAPS (if any — blocking):
  [check]: [finding]
```

Any HIGH bandit finding is a P5b blocker.
Any failed residency check is a P5b blocker.
Any failed regulatory threshold assertion is a P5b blocker.

```
Next (after operator runs cold start and chaos tests):
  ~/projects/pyvar/scripts/claude/pyvar-run.sh p5b --teardown-worktrees
```

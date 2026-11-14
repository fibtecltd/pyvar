# Spot interruption drill and throughput test (W4, W5): delegated agent prompt (dev only)

**Status: ready to run, with the settings below; updated 2026-11-14.** W4 and W5 are items of `docs/plan-swot-engineering-integration.md` (section 5), left unrun by the AWS evidence run (`docs/p9-aws-evidence-2026-11-13.md`, sections 4 and 6): W4 checks that a job is neither lost nor duplicated when a Spot worker dies mid-job, W5 measures jobs per minute against the number of workers. Neither measures cost. The prompt works in the dev environment only and restores the Auto Scaling group's size whatever happens.

**Settings are written into the prompt, not read from the environment.** A first version asked the owner to supply three inputs as environment variables; the agent stopped because none was set. They are now fixed values: no database access (`DB_RO_URL = none`, so executions are counted from worker logs only), no FIS template (`FIS_TEMPLATE = none`, so the 2-minute-notice Spot interruption arm is skipped), and `LOAD_MODE = queue` (W5 dispatches through the queue, which adds dev audit rows with `user_id` "unknown" and leaves the API and the WAF unmeasured). To get the fuller evidence, edit those three lines before running: supply a read-only role on `var_jobs`/`api_usage`, a pre-created FIS template using `aws:ec2:send-spot-instance-interruptions` on the dev workers, or `api` once the agent's source IP is exempt from the WAF rate rule.

**The agent mints its own token.** In STEP 0 it reads the dev JWT signing secret (`pyvar/dev/jwt-secret`, the only secret it may read, once) and signs one HS256 token with `sub` `internal-w4w5-agent`, tier `internal` and `exp` 24 hours after issue, the way pyvar's own scheduled jobs sign theirs. Tier `internal` rather than `pro` because the pro tier is capped at 500 requests a day and 2,000,000 simulations a month (about 20 jobs of 100,000), which would stop W5 and would be counted as customer usage; `internal` is exempt from both caps, allows up to 500,000 simulations and is kept apart from customer tiers in usage analytics. The snippet was run against a dummy secret and its output accepted by `api.middleware.auth.decode_token_payload` as `internal` / 500,000 simulations; with the secret unreadable it yields no token. A token cannot be revoked before it expires (rotating the secret is the only other way), so the 24 hours are the limit of the access given. The prompt says outright that the owner authorises the one secret read and that the agent must create the token itself, because an agent only told it "may not read secrets" stops and reports that it has no access; it still stops, by design, if AWS itself answers AccessDenied. The agent's AWS role needs `secretsmanager:GetSecretValue` on the dev secret.

**Calibration.** The job must outlast the kill delay and stay inside the queue's 60 s visibility timeout. The agent tunes `n_simulations` (1,000 to 500,000 for tier `internal`) to reach 20 to 30 s and may raise `horizon_days` (up to 250) if that alone cannot, stating what it used; W5 stays at 100,000 simulations and 1 day. Typical production jobs take about 6 s (slowest about 33 s), so the first step may take a few tries.

The prompt, as the agent should read it (4,936 bytes):

---

TASK: in pyvar DEV only, measure W4 (is a job lost or duplicated when a Spot worker dies mid-job?) and W5 (jobs per minute against the number of workers). Report what the trials show, no more. Run it start to finish; the owner cannot answer questions.

SETTINGS (fixed values given here; they are NOT environment variables, so never look for them elsewhere or stop for them)
- DB_RO_URL = none: no database access; count executions from worker logs only.
- FIS_TEMPLATE = none: skip arm C.
- LOAD_MODE = queue: W5 goes through the queue, not the API (the WAF limits API requests per IP).

STEP 0, YOUR TOKEN: you generate it yourself
Nobody will hand you a token: do not wait for one or stop for lack of one. The owner of this dev environment explicitly authorises you to read exactly one secret, pyvar/dev/jwt-secret (eu-west-1), once, and to sign one dev API token with it, valid 24 hours. This is the only exception to every no-secret-reads rule. Stop only if AWS itself answers AccessDenied or not-found to that read: then STOP, quote the error, do not widen access. Never touch any other secret, prod included. Claims: sub internal-w4w5-agent, tier internal (not pro: its monthly caps would stop W5), iat now, exp now+86400. Run exactly:

set -o pipefail
TOKEN=$(aws secretsmanager get-secret-value --secret-id pyvar/dev/jwt-secret --region eu-west-1 --query SecretString --output text | python3 -c '
import base64, hashlib, hmac, json, sys, time
secret = sys.stdin.read().strip()
if len(secret) < 32:
    sys.exit("no usable secret")
def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
now = int(time.time())
head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
body = b64(json.dumps({"sub": "internal-w4w5-agent", "tier": "internal", "iat": now, "exp": now + 86400}, separators=(",", ":")).encode())
sig = b64(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
print(f"{head}.{body}.{sig}")
') || { echo "MINT FAILED"; TOKEN=""; }

Check without printing: not empty, three dot-separated parts, exp minus iat = 86400; else STOP. Mint once. Each shell call is fresh, so hold the token only in memory in one long-lived local process fed through a pipe; never on disk, in argv, logs or the report. That process forwards only to https://dev.pyvar.com (never pyvar.com), only the compute and result endpoints, at most one request per 5 s. If the token expires or a call returns 401, STOP and report. Report only sub, tier and expiry. At the end stop the process.

RULES
- Dev only. First check the account, region, group pyvar-dev-workers and queue pyvar-dev-var-jobs.fifo; if any name contains prod, STOP.
- Record the group's min, max, desired now (expected 0, 5, 0); restore them in a finally block whatever happens. Never exceed max 5. Spend cap about $5.
- No changes to IAM, security groups, WAF, queues, CDK or prod. No secret reads besides STEP 0. Never run scripts/chaos_test.sh. Stop at once on an unexpected dead-letter message, a prod-looking name, or a denied call (do not work around it).
- Calibrate first: one warm job; choose n_simulations (1,000 to 500,000) so it runs 20 to 30 s (the queue's 60 s visibility timeout must exceed the runtime). If that alone cannot, also raise horizon_days (up to 250) and state exactly what you used. W5 jobs stay at 100,000 simulations, 1 day.

W4 (arms A and B, at least 5 trials each; state n)
Submit the calibrated job (fixed seed; compute the expected result once first). When /pyvar/dev/worker logs it received, wait about 40% of the calibrated runtime, then kill that worker:
- A, hard: ec2 terminate-instances.
- B, graceful: autoscaling terminate-instance-in-auto-scaling-group (60 s drain hook runs).
Per trial: task id, arm, kill time, result arrived and equal to expected, seconds to result, times the worker log shows the task received and succeeded, DLQ depth after. Wait up to 10 min per trial. "Exactly once" = one recorded result; report executions separately (redelivery is expected).

W5 (workers 1, 2, 4; fewer if unreachable)
Per N: set min = desired = N, wait for N workers ready, one warm-up job each. Then M = max(60, 30 x N) jobs of 100,000 simulations, 1 day, back to back, dispatched with the repository's own Celery code (api/routes/var.py); read completions from worker logs (Logs Insights). Say this adds audit rows with user_id "unknown" and leaves the API and WAF unmeasured.
Per step: workers ready, jobs completed, first enqueue to last completion, throughput over the middle 60% of jobs, worker runtime p50 and p95, instance-hours. Efficiency = throughput(N) / (N x throughput(1)).

REPORT
Tables: W4 (per arm: n, lost, duplicated executions, seconds to result), W5 (per N); token sub, tier, expiry; restored group values; what you could not do and why; spend (estimate); everything you got wrong. Say where n is small. No ids, hostnames or secrets in the body.

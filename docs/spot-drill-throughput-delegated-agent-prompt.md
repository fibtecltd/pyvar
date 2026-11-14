# Spot interruption drill and throughput test (W4, W5): delegated agent prompt (dev only)

**Status: draft, updated 2026-11-14; not ready to run until the three INPUTS below are supplied.** W4 and W5 are items of `docs/plan-swot-engineering-integration.md` (section 5), left unrun by the AWS evidence run (`docs/p9-aws-evidence-2026-11-13.md`, sections 4 and 6): W4 checks that a job is neither lost nor duplicated when a Spot worker dies mid-job, W5 measures jobs per minute against the number of workers. Neither measures cost. The prompt works in the dev environment only, restores the Auto Scaling group's size whatever happens, and forbids creating IAM roles or templates.

**The agent mints its own token.** The owner no longer supplies one. In STEP 0 the agent reads the dev JWT signing secret (`pyvar/dev/jwt-secret`, the only secret it may read, once) and signs one HS256 token with `sub` `internal-w4w5-agent`, tier `internal` and `exp` 24 hours after issue, the way pyvar's own scheduled jobs sign theirs. Tier `internal` rather than `pro` because the pro tier is capped at 500 requests a day and 2,000,000 simulations a month (about 20 jobs of 100,000), which would stop W5 and would be counted as customer usage; `internal` is exempt from both caps, allows up to 500,000 simulations and is kept apart from customer tiers in usage analytics. The snippet was run against a dummy secret and its output accepted by `api.middleware.auth.decode_token_payload` as `internal` / 500,000 simulations; with the secret unreadable it yields no token. A token cannot be revoked before it expires (rotating the secret is the only other way), so the 24 hours are the limit of the access given; the agent mints once and stops if the token expires.

What the owner still has to provide (the INPUTS block): a read-only dev database role (or "none"); a pre-created FIS template for Spot interruption (or "none"); and whether the agent's source IP is exempt from the WAF rate rule (otherwise the load goes through the queue directly, which adds audit rows with `user_id` "unknown" in dev and leaves the API and the WAF unmeasured). The agent's AWS role also needs `secretsmanager:GetSecretValue` on the dev JWT secret; without it the agent stops.

The prompt, as the agent should read it:

---

TASK: in the pyvar DEV environment only, measure W4 (is a job lost or duplicated when a Spot worker dies mid-job?) and W5 (jobs per minute against the number of workers). Report what the trials show and no more.

INPUTS (the owner fills these in; if one is missing, STOP and tell me which)
- PYVAR_DEV_DB_RO_URL: a read-only role on the dev database (SELECT on var_jobs and api_usage), or "none".
- FIS_TEMPLATE: id of a pre-created FIS template using aws:ec2:send-spot-instance-interruptions on the dev workers, or "none". You do not create IAM roles or templates.
- LOAD_MODE: "api" only if I state your source IP is exempt from the WAF rate rule (100 requests per 300 s per IP, which polling also uses); otherwise "queue".
There is no token input: you mint your own in STEP 0.

STEP 0: YOUR TOKEN (the one secret you may read, once)
Mint exactly one API token for the dev API, valid for 24 hours, and use it for every API call in this task. Never run scripts/chaos_test.sh.
- Source: the dev JWT signing secret, named pyvar/dev/jwt-secret, region eu-west-1 (a plain string; the dev API checks tokens against it). Read it once, by that exact name. If the read is denied or the name does not exist, STOP and say so; do not widen your access or look for another way in. Never list secrets, never read any other, never touch pyvar/prod/jwt-secret.
- Claims: sub internal-w4w5-agent, tier internal, iat now, exp now + 86400 s (24 hours, never longer, never without exp). Tier internal, not pro, on purpose: pro is capped at 500 requests a day and 2,000,000 simulations a month (about 20 jobs of 100,000), which would stop W5 and would be counted as customer usage. internal is the tier pyvar's own scheduled jobs use: exempt from both caps, up to 500,000 simulations, and kept apart from customer tiers in the usage tables.
- Mint it with exactly this (stdlib HS256; the secret travels through a pipe, never a command-line argument, a file or the screen):

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

- Check, without printing the token: it is not empty, it has three dot-separated parts, and its decoded payload shows exp minus iat = 86400. If any check fails, STOP.
- Never print, log, write to a file, commit or put in the report the secret or the token. Keep the token in a shell variable of your session only. In the report give the sub, the tier and the expiry time, nothing else about it.
- Mint once. If it expires before you finish, or a call answers 401, STOP and report how far you got; do not mint a second one. A token cannot be revoked; the 24 hours are its only limit (rotating the secret is the only other way, and that is not yours to do).
- Use: header "Authorization: Bearer $TOKEN", against the dev API only, https://dev.pyvar.com (pyvar-cdk/config.py, api_base_url), path /api/v1/var/compute. Never send it to pyvar.com or www.pyvar.com. It is needed for the calibration job and the W4 trials (a few requests), and for W5 when LOAD_MODE is "api".
- When you finish or stop, unset TOKEN and say that it stays valid until its expiry time.

RULES
- Dev only. Before anything, check the account, region, group `pyvar-dev-workers` and queue `pyvar-dev-var-jobs.fifo`. If any name contains prod, STOP.
- Record the group's min, max and desired now (expected 0, 5, 0). Restore them in a finally block, whatever happens. Never exceed max 5. Estimated spend cap $5 (Spot about $0.087 an hour).
- No changes to IAM, security groups, WAF, queues, CDK or any prod resource. No secret reads other than the one in STEP 0. Stop at once if a message reaches the dead-letter queue unexpectedly, a name looks like prod, or a call is denied (do not work around it).
- Calibrate first: run one job warm; choose n_simulations so the job takes 20 to 30 s on a dev worker (the queue's visibility timeout is 60 s and must exceed the runtime).

W4 (at least 5 trials per arm; state n)
Submit the calibrated job (fixed seed; first compute its expected result once). Watch /pyvar/dev/worker for the task's received line; about 10 s later kill that worker's instance.
- Arm A, hard kill, no drain: ec2 terminate-instances on that instance.
- Arm B, graceful: autoscaling terminate-instance-in-auto-scaling-group (the 60 s drain hook runs).
- Arm C, only if FIS_TEMPLATE is set: the Spot interruption with its 2-minute notice.
Per trial record: task id, arm, kill time, whether a result arrived and equals the expected one, seconds to result, how many times the worker log shows the task received and succeeded, the number of var_jobs rows for the task id (if DB read access), DLQ depth after. Wait up to 10 minutes per trial. "Exactly once" means one recorded result; report separately how many times it executed (redelivery is expected).

W5 (workers 1, 2 and 4; fewer if the group cannot reach them)
For each N: set min = desired = N, wait until N workers have logged ready, send one warm-up job each. Then submit M = max(60, 30 x N) jobs of 100,000 simulations, 1 day, back to back.
- LOAD_MODE api: POST /api/v1/var/compute with the token; poll sparsely. Rows in api_usage carry tier internal, so they can be told apart.
- LOAD_MODE queue: dispatch with the repository's own Celery code (see api/routes/var.py), not hand-made messages; read completions from worker logs (Logs Insights). Say that this adds audit rows with user_id "unknown" in dev, and that the API and the WAF are not measured.
Per step record: workers ready, jobs completed, first enqueue to last completion, throughput over the middle 60% of jobs, worker runtime p50 and p95, instance-hours used. Efficiency = throughput(N) / (N x throughput(1)). Then restore the group.

REPORT
Tables for W4 (per arm: n, lost, duplicated executions, seconds to result) and W5 (per N), the token's sub, tier and expiry, the restored group values, what you could not do and why, spend (estimate), and everything you got wrong. Say plainly where n is small. Keep ids, hostnames and secrets out of the report body.

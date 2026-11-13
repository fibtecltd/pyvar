# Spot interruption drill and throughput test (W4, W5): delegated agent prompt (dev only)

**Status: draft, 2026-11-13; not ready to run until the four INPUTS below are supplied.** W4 and W5 are items of `docs/plan-swot-engineering-integration.md` (section 5), left unrun by the AWS evidence run (`docs/p9-aws-evidence-2026-11-13.md`, sections 4 and 6, in PR #428): W4 checks that a job is neither lost nor duplicated when a Spot worker dies mid-job, W5 measures jobs per minute against the number of workers. Neither measures cost. The prompt works in the dev environment only, restores the Auto Scaling group's size whatever happens, and forbids minting tokens, reading secrets and creating IAM roles or templates.

What the owner has to provide (the INPUTS block): a pro-tier dev token issued by an authorised person; a read-only dev database role (or "none"); a pre-created FIS template for Spot interruption (or "none"); and whether the agent's source IP is exempt from the WAF rate rule (otherwise the load goes through the queue directly, which adds audit rows with `user_id` "unknown" in dev and leaves the API and the WAF unmeasured).

The prompt, as the agent should read it:

---

TASK: in the pyvar DEV environment only, measure W4 (is a job lost or duplicated when a Spot worker dies mid-job?) and W5 (jobs per minute against the number of workers). Report what the trials show and no more.

INPUTS (the owner fills these in; if one is missing, STOP and say which)
- PYVAR_DEV_PRO_JWT: a pro-tier dev token issued by an authorised person. Never mint or forge a token, never read the dev JWT secret, never run scripts/chaos_test.sh.
- PYVAR_DEV_DB_RO_URL: a read-only role on the dev database (SELECT on var_jobs and api_usage), or "none".
- FIS_TEMPLATE: id of a pre-created FIS template using aws:ec2:send-spot-instance-interruptions on the dev workers, or "none". You do not create IAM roles or templates.
- LOAD_MODE: "api" only if I state your source IP is exempt from the WAF rate rule (100 requests per 300 s per IP, which polling also uses); otherwise "queue".

RULES
- Dev only. Before anything, check the account, region, group `pyvar-dev-workers` and queue `pyvar-dev-var-jobs.fifo`. If any name contains prod, STOP.
- Record the group's min, max and desired now (expected 0, 5, 0). Restore them in a finally block, whatever happens. Never exceed max 5. Estimated spend cap $5 (Spot about $0.087 an hour).
- No changes to IAM, security groups, WAF, queues, CDK or any prod resource. No secret reads. Stop at once if a message reaches the dead-letter queue unexpectedly, a name looks like prod, or a call is denied (do not work around it).
- Calibrate first: run one job warm; choose n_simulations so the job takes 20 to 30 s on a dev worker (the queue's visibility timeout is 60 s and must exceed the runtime).

W4 (at least 5 trials per arm; state n)
Submit the calibrated job (fixed seed; first compute its expected result once). Watch /pyvar/dev/worker for the task's received line; about 10 s later kill that worker's instance.
- Arm A, hard kill, no drain: ec2 terminate-instances on that instance.
- Arm B, graceful: autoscaling terminate-instance-in-auto-scaling-group (the 60 s drain hook runs).
- Arm C, only if FIS_TEMPLATE is set: the Spot interruption with its 2-minute notice.
Per trial record: task id, arm, kill time, whether a result arrived and equals the expected one, seconds to result, how many times the worker log shows the task received and succeeded, the number of var_jobs rows for the task id (if DB read access), DLQ depth after. Wait up to 10 minutes per trial. "Exactly once" means one recorded result; report separately how many times it executed (redelivery is expected).

W5 (workers 1, 2 and 4; fewer if the group cannot reach them)
For each N: set min = desired = N, wait until N workers have logged ready, send one warm-up job each. Then submit M = max(60, 30 x N) jobs of 100,000 simulations, 1 day, back to back.
- LOAD_MODE api: POST /var/compute with the token; poll sparsely.
- LOAD_MODE queue: dispatch with the repository's own Celery code (see api/routes/var.py), not hand-made messages; read completions from worker logs (Logs Insights). Say that this adds audit rows with user_id "unknown" in dev, and that the API and the WAF are not measured.
Per step record: workers ready, jobs completed, first enqueue to last completion, throughput over the middle 60% of jobs, worker runtime p50 and p95, instance-hours used. Efficiency = throughput(N) / (N x throughput(1)). Then restore the group.

REPORT
Tables for W4 (per arm: n, lost, duplicated executions, seconds to result) and W5 (per N), the restored group values, what you could not do and why, spend (estimate), and everything you got wrong. Say plainly where n is small. Keep ids, hostnames and secrets out of the report body.

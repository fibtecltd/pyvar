# Retrospective: AMI Cold-Start Resolution (Hypothesis C)

**Date:** 2026-07-09 → 2026-07-10
**Outcome:** PASS — cold start avg=3s (target <45s)
**AMI:** `ami-053d838c9735b7a03` (Image Builder pipeline `pyvar-dev-worker-pipeline`, auto-versioned)

---

## Summary

Getting a working EC2 Image Builder pipeline for pre-baked Celery workers took
roughly 60 iterations across ~10 distinct root causes. Each fix was correct in
isolation but surfaced the next layer of the problem. This doc records the full
chain so future Image Builder or systemd work on this project doesn't repeat it.

---

## The chain of failures, in order

### 1. Numba cache: `no locator available for file '<string>'`
**Symptom:** `RuntimeError: cannot cache function '_warmup_kernel': no locator
available for file '<string>'`
**Cause:** The warmup kernel was defined via `python3 -c "..."`. Code executed
this way has no `__file__` (`<string>`), and Numba's `cache=True` needs a real
file path to derive the cache location from.
**Fix:** Write the warmup function to `/tmp/numba_warmup.py` via heredoc and
run it as a real script (`python3.11 /tmp/numba_warmup.py`), not `python3 -c`.

### 2. `update-alternatives` breaks yum and the AWS CLI
**Symptom:** `cannot access /var/lib/alternatives/python3: No such file or
directory`, later `ModuleNotFoundError: No module named 'awscli'` and `No
module named 'dnf'`.
**Cause:** `alternatives --set python3 /usr/bin/python3.11` (or
`update-alternatives --install ...`) repoints the system `python3` symlink.
Amazon Linux 2023's `yum`/`dnf` and the bundled `aws` CLI are hard-pinned to
Python 3.9 and break immediately once `python3` points elsewhere.
**Fix:** Never touch the system `python3` symlink. Use `python3.11` and
`pip3.11` explicitly everywhere — install commands, warmup script, systemd
`ExecStart`.

### 3. systemd unit: literal `\n` instead of newlines
**Symptom:** `Invalid section header '[Service]\nType=simple\n...'` — the
entire `[Service]` block collapsed onto one line.
**Cause:** One line in the CDK Python string used `\\n` (escaped backslash-n)
instead of `\n` (actual newline), so the shell wrote literal backslash-n
characters into the unit file instead of line breaks.
**Fix:** Audit every heredoc/multi-line string embedded in CDK for `\\n` vs
`\n` — they look nearly identical in a diff and are easy to introduce when
refactoring string concatenation into an f-string block.

### 4. `pycurl` missing — Celery 5.6 SQS transport requirement
**Symptom:** `ImportError: The curl client requires the pycurl library.`
**Cause:** Celery 5.6 reverted an earlier switch from `pycurl` to `urllib3`
for the SQS async transport (the urllib3 path had severe throughput and
correctness regressions). `pycurl` became a hard requirement again, but it
wasn't in `requirements.txt`.
**Fix:** Add `pycurl>=7.45.0` to `requirements.txt`. `pycurl` compiles from
source and needs `libcurl-devel` + `gcc`/`gcc-c++` installed first.

### 5. `task_default_queue` not set — Celery tries to create a queue named `celery`
**Symptom:** `AccessDenied: sqs:createqueue on resource: .../celery` and
later `.../default`.
**Cause:** With a bare `sqs://` broker URL and no `task_default_queue`, Celery
defaults to a queue named `celery` (or whatever `--queues` was hardcoded to —
`worker.py` had `--queues=default` hardcoded, overriding the env var).
**Fix:** Set `task_default_queue` from `SQS_QUEUE_NAME` env var in
`celery_app.conf.update()`. Remove the hardcoded `--queues=default` in
`worker.py`'s `celery_app.worker_main()` call — read it from the env instead.

### 6. Missing IAM permissions — `sqs:ListQueues`, `sqs:CreateQueue`
**Symptom:** `AccessDenied: sqs:listqueues` then `AccessDenied: sqs:createqueue`.
**Cause:** `grant_consume_messages()` on the CDK `Queue` construct grants
`ReceiveMessage`/`DeleteMessage`/`ChangeMessageVisibility`/`GetQueueAttributes`
— it does **not** grant `ListQueues`, which Celery's SQS transport calls on
startup to resolve the queue. Once (5) was fixed, `CreateQueue` also
surfaced transiently before the queue name was correctly wired.
**Fix:** Explicitly grant `sqs:ListQueues` (scoped to
`arn:aws:sqs:{region}:{account}:*` since it's an account-level action, not
resource-scoped) in addition to `grant_consume_messages()`.

### 7. `CELERY_RESULT_BACKEND` never reached the worker process
**Symptom:** Jobs consumed from SQS (queue empties) but results never
written; API always returns `pending`.
**Cause, layered:**
  a. `var_task.py` hardcoded `broker=cfg.redis_url` /
     `backend=cfg.redis_url` — the `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`
     env vars were never read at all.
  b. Once (a) was fixed: `export VAR=val` in EC2 UserData only affects the
     bash process running UserData — `systemctl start` spawns a fresh
     process tree that does **not** inherit those exports.
  c. Once systemd `EnvironmentFile` was added: ElastiCache Serverless
     requires TLS — `redis://` silently failed; needed `rediss://` with
     `?ssl_cert_reqs=CERT_NONE` (ElastiCache's cert isn't verified
     client-side within the VPC).
**Fix:** Read broker/backend from `os.environ.get(...)` with `cfg.redis_url`
as local-dev fallback. Write all worker env vars to a file
(`/opt/pyvar/celery.env`) and reference it via `EnvironmentFile=` in the
systemd unit — never rely on shell `export` surviving into a systemd-spawned
process. Use `rediss://` + `ssl_cert_reqs=CERT_NONE` for ElastiCache
Serverless.

### 8. Numba cache written to `/tmp` — doesn't survive the AMI snapshot
**Symptom:** (caught proactively, not by a failure) — `/tmp` on Amazon Linux
2023 is commonly `tmpfs` (RAM-backed). Image Builder snapshots the EBS root
volume, not RAM, so a cache written to `/tmp` during the bake would vanish
from the resulting AMI — silently defeating the entire point of pre-warming.
**Fix:** Set `NUMBA_CACHE_DIR=/opt/numba_cache` (a real path on the EBS root
volume) for both the bake-time warmup and the runtime `celery.env` — the
paths must match or the worker won't find the pre-baked cache.

### 9. Image Builder component version never bumped
**Symptom:** Fixes committed and deployed via `cdk deploy`, but the pipeline
kept failing with the *exact same* stack trace as before the fix.
**Cause:** `imagebuilder.CfnComponent` versions are immutable in AWS. CDK
doesn't auto-bump the version when only the component *content* changes if
the version string itself is unchanged (`version="1.0.0"` every time) — it
silently reused the old, broken component.
**Fix:** Derive the version from a hash of the component content:
`hashlib.md5(NUMBA_WARMUP_SCRIPT.encode(), usedforsecurity=False)`, truncated
and mapped into a `1.0.N` string. Any content change now produces a new
version automatically — no more manual version bumps, no more silent stale
reuse.

### 10. S3 logging bucket referenced but never created
**Symptom:** `Couldn't find region for S3 bucket pyvar-dev-build-logs-...! ...
bucket not found.`
**Cause:** The infrastructure configuration's `logging.s3Logs` block pointed
at a bucket name that was never provisioned by any CDK stack.
**Fix (interim):** Gate S3 logging behind `cfg.ami_s3_logging: bool = False`.
CloudWatch Logs (`/aws/imagebuilder/pyvar-dev-worker`) already captures full
build output, so this is non-blocking. Re-enable once the bucket is created
in a future pass (tracked as a P7 item — not urgent).

### 11. Scale-from-zero doesn't work with target tracking alone
**Symptom (separate from the AMI build itself):** ASG stuck at
`desired=0` indefinitely even with messages visible in the queue.
**Cause:** Target tracking scaling computes `desired = messages / target`.
When `desired` is running at 0, this ratio is either undefined or evaluated
against 0 running instances — AWS explicitly does not use target tracking to
bootstrap from zero. This is documented AWS behaviour, not a tuning problem;
no `target_value` fixes it.
**Fix:** Added a **separate step-scaling policy**
(`self.asg.scale_on_metric("ScaleFromZero", ...)`) using `EXACT_CAPACITY`
that handles only the 0→1 transition
(`ScalingInterval(upper=1, change=0)`, `ScalingInterval(lower=1, change=1)`).
Target tracking (`target_value=5.0`) takes over once ≥1 instance is running.
`EXACT_CAPACITY` is idempotent, so repeated alarm breaches during a burst
can't compound into runaway scale-out.

---

## Net result

| Metric | Hypothesis B (git clone + pip install) | Hypothesis C (baked AMI) |
|---|---|---|
| Cold start | ~15–20 min | avg 3s (min 0s, max 6s) |
| Dependency install | Every boot | Baked in |
| Numba JIT warmup | Every first call | Baked in |
| S3/GitHub token dependency at boot | Yes (still — code still git-cloned) | Yes (code only) |

Hypothesis B remains available as a fallback
(`cfg.worker_use_baked_ami = False`) — e.g. for rapid dev iteration before a
new AMI bake is triggered, since Hypothesis B always reflects the latest
`master` without needing a 15–30 min Image Builder run first.

---

## Process lessons for next time

1. **When a fix doesn't change the observed error, check the version/hash
   first.** Several iterations were spent re-verifying a "fix" that was
   correct but never actually deployed to a new component version (#9).
   Confirm the deployed artifact's content before re-diagnosing.

2. **`export` in cloud-init/UserData does not propagate to systemd services.**
   This tripped multiple env vars (#7). Any value a systemd-managed process
   needs must go through `EnvironmentFile=`, not shell `export` earlier in
   the same UserData script.

3. **`/tmp` is not guaranteed to be disk-backed.** Anything that must survive
   an AMI snapshot, a reboot, or a container restart needs an explicit,
   documented, non-`/tmp` path.

4. **Don't touch the system Python `alternatives` on Amazon Linux 2023.**
   `yum`/`dnf` and the bundled AWS CLI depend on the system Python. Install a
   second interpreter (`python3.11`) alongside it and reference it explicitly
   everywhere, rather than switching the default.

5. **AWS quota errors (`MaxSpotInstanceCountExceeded`) look like application
   bugs at first glance.** Worth checking Service Quotas early when scaling
   activity shows repeated `Failed` launch attempts with no application-level
   explanation.

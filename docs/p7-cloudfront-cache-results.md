# P7 Task 6 — CloudFront cache hit rate review

## Checks

**1. Is `Cache-Control: public, max-age=3600` actually set by the API for
SUCCESS responses?**
**No — found and fixed.** `GET /var/result/{task_id}` (`api/routes/var.py`)
returned every response (`PENDING`/`STARTED`/`SUCCESS`/`FAILURE`) with no
`Cache-Control` header at all. `edge_stack.py`'s `ApiCachePolicy` is
correctly configured (`min_ttl=0`, `max_ttl=3600`, forwards the
`Cache-Control` header) and *would* respect an origin `Cache-Control`
header if one existed — but since the origin never sent one, CloudFront
fell back to the policy's `default_ttl=0` for every response, meaning
**nothing was ever cached at the edge, including SUCCESS results**. This
directly contradicts the design docstring at the top of `edge_stack.py`.

Fixed in `api/routes/var.py`: `get_var_result` now sets
`Cache-Control: public, max-age=3600` on `SUCCESS` and
`Cache-Control: no-store` on everything else (`PENDING`, `STARTED`, and
`FAILURE` — a failed job may still be retried and its state can change, so
it must not be cached either; the original design docstring only mentioned
pending/success explicitly). Added test coverage asserting the header on
all three response states.

**2. Is `Cache-Control: no-store` correctly set for PENDING responses?**
Same root cause as above — no, it was never set for anything. Covered by
the same fix.

**3. Actual CloudFront cache hit rate?**
**Cannot measure — but not for the "too new, no traffic" reason anticipated
by the task.** Real traffic exists on this distribution: `Requests` and
`BytesDownloaded` both show meaningful volume over the last 7 days (up to
69MB and hundreds of requests in a single day — evidence of the P4-P7
testing sessions, including `chaos_test.sh` runs and this session's own
smoke tests). The actual gap: `CacheHitRate` returns **zero CloudWatch
datapoints** — it isn't `0%`, the metric simply doesn't exist, because
CloudFront's "Additional (extra-cost) metrics" (`CacheHitRate`,
`OriginLatency`, etc.) require an explicit per-distribution
`AWS::CloudFront::MonitoringSubscription` resource (CDK: L1
`CfnMonitoringSubscription`), which `edge_stack.py` doesn't provision.
Standard metrics (`Requests`, `4xxErrorRate`, `5xxErrorRate`,
`BytesDownloaded`) are free and already visible; `CacheHitRate` is not.

**Not enabling this myself** — it's a real (small) recurring AWS cost, and
enabling it now wouldn't retroactively backfill historical hit-rate data
anyway; it only starts reporting from the moment it's turned on, and the
*pre-fix* history would have been ~0% regardless (nothing was cacheable).
Flagging as a decision for you: enable `CfnMonitoringSubscription` on this
distribution (small ongoing cost, `cdk deploy` required) to actually start
measuring the >60% target from the release plan, now that the underlying
Cache-Control bug is fixed and there's something real to measure.

## Aside (not investigated further — out of scope for this task)
`4xxErrorRate` shows unusually high values on two of the last 7 days (68%
and ~85% of requests). Likely explained by the volume of auth/validation
testing traffic across P4-P7 sessions (missing JWTs, bad payloads,
tier-cap tests, etc. all return 4xx by design), but worth a dedicated look
if it persists in real usage rather than test traffic.

## Summary

| Check | Result |
|---|---|
| `Cache-Control: public, max-age=3600` on SUCCESS | **No — fixed** |
| `Cache-Control: no-store` on PENDING | **No — fixed** (extended to FAILURE too) |
| CloudFront cache policy config (`edge_stack.py`) | Correct as-is, no change needed |
| Actual cache hit rate | Cannot measure — `CacheHitRate` metric not enabled (real traffic exists; not a "too new" case) |

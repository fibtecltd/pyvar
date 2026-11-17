# Plan: lowering prod's Aurora minimum capacity from 1.0 to 0.5 ACU, and measuring it

Decision of 2026-11-16 (D2, option 3): the dev reader is removed and prod's minimum capacity goes from 1.0 to
0.5 ACU, with measuring. Prod keeps its reader (the failover target). Nothing here has run in prod yet.

## Why
Both prod instances sat at the capacity floor in 99.3% to 99.5% of the 1,118 hours from 2026-10-01
(`docs/p9-aws-evidence-2026-11-13.md`, section 10), so the floor is what is billed: about 1.0 ACU x 730 h x $0.14
= $102 a month per instance, $51 at 0.5. Savings estimate (arithmetic, from those averages): prod about $102 a month
(writer and reader), the dev reader about $51: about $153 a month in all.

## Baseline (prod, last 14 full days to 2026-11-16, 1.0 ACU floor; full table in `docs/p9-aws-evidence-2026-11-13.md` section 12)
| | Writer | Reader |
| --- | --- | --- |
| Average capacity | 1.011 ACU | 1.024 ACU |
| Hours with any datapoint above the minimum | 77 of 336 (22.9%) | 63 of 336 (18.8%) |
| Connections (highest hourly maximum) | 6 | 0 |
| CPU: mean; highest hourly maximum; p99 of hourly maxima | 2.77%; 80%; about 19% | 2.36%; 97.6%; about 25% |
| CommitLatency, highest hourly maximum | 5.06 ms (otherwise about 1 ms or less) | 0.85 ms |
| Client side (prod ALB) | p95 0.057 s and p99 0.256 s over the window; hourly p95 peak 1.38 s; 1 5xx in 16,444 requests | |

Both instances together average 2.03 ACU, about $208 a month, against $204 if pinned at the floor: the bill is the floor.
(Section 10 of the evidence document counted "99.3% to 99.5% of hours at the minimum" with another definition; the averages agree.)
Dev has run at 0.5 ACU throughout.

## What could go wrong at 0.5 ACU (not verified for this workload)
- **Less memory at the floor.** Capacity carries about 2 GiB per ACU (AWS's published ratio, from memory), so 1 GiB
  instead of 2: a smaller buffer cache and less room for a heavy query. The working set here is small (an audit
  table and a few other tables), which is why this is expected to be fine, not shown.
- **A burst meets a small instance first.** Serverless v2 scales in 0.5 ACU steps within seconds, but the first
  seconds run at the current size.
- **The writer sits at its floor almost all the time**, so any effect shows up as latency or CPU, not as a capacity change.

## Measuring
1. **Before the deploy: done 2026-11-16** (BASELINE mode, section 12 of the evidence document).
2. **A CPU alarm** on the prod writer (`pyvar-prod-aurora-writer-cpu`, in `data_stack.py`): average CPU at or above
   85% for 15 minutes. A placeholder, not tuned. The existing ALB alarms (`pyvar-prod-api-latency-p95` above 5 s,
   `pyvar-prod-api-5xx` above 10 in 5 minutes) report what a client feels. The CPU alarm follows the instance that is
   the writer today: after a failover it would watch the other one.
3. **After the deploy:** run the same prompt again after at least 7 days (it detects AFTER mode) so that one Saturday
   maintenance window is inside it; again after 30 days.

## Rollback rules (proposed, untuned; the owner may change them)
`FreeableMemory` is not usable as a rule: it reads about 29 GiB at a 1 ACU floor, so it appears to be relative to the
16 ACU maximum and will not show memory pressure at 0.5 ACU. The rules use what a client and the database report.
Set `aurora_min_acu=1.0` for prod and deploy (the one line in `pyvar-cdk/config.py`) if, in the AFTER window:
- the writer CPU alarm fires, or an API latency or 5xx alarm fires that did not fire in the BEFORE window; or
- the writer's `CommitLatency` highest hourly maximum is above 25 ms in more than two hours (the baseline's worst hour
  was 5.06 ms; this is five times that), or the ALB's hourly p95 is above 3 s outside the maintenance hours (the baseline's
  worst was 1.38 s); or
- an RDS reboot or failover event follows the change (a minimum-capacity change is expected to apply without one; not
  verified).

## The prompt
See `docs/prompts/agent-d2-floor-measure.txt` (read-only, prod only, under 5 KB).

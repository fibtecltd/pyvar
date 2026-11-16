# Plan: lowering prod's Aurora minimum capacity from 1.0 to 0.5 ACU, and measuring it

Decision of 2026-11-16 (D2, option 3): the dev reader is removed and prod's minimum capacity goes from 1.0 to
0.5 ACU, with measuring. Prod keeps its reader (the failover target). Nothing here has run in prod yet.

## Why
Both prod instances sat at the capacity floor in 99.3% to 99.5% of the 1,118 hours from 2026-10-01
(`docs/p9-aws-evidence-2026-11-13.md`, section 10), so the floor is what is billed: about 1.0 ACU x 730 h x $0.14
= $102 a month per instance, $51 at 0.5. Savings estimate (arithmetic, from those averages): prod about $102 a month
(writer and reader), the dev reader about $51: about $153 a month in all.

## Baseline (prod, 2026-10-01 to 2026-11-16, 1.0 ACU floor, hourly data)
| | Writer | Reader |
| --- | --- | --- |
| Average capacity | 1.0061 ACU | 1.0144 ACU |
| Hours at the minimum | 99.5% | 99.3% |
| Connections (maximum) | 9 | 0 |
| CPU, highest hourly maximum | 80% | 100% (three maintenance-window bursts) |
| Free memory, latency | not measured yet | not measured yet |

Dev has run at 0.5 ACU throughout (writer CPU peaked at 100% in an hour, 10 connections at most).

## What could go wrong at 0.5 ACU (not verified for this workload)
- **Less memory at the floor.** Capacity carries about 2 GiB per ACU (AWS's published ratio, from memory), so 1 GiB
  instead of 2: a smaller buffer cache and less room for a heavy query. The working set here is small (an audit
  table and a few other tables), which is why this is expected to be fine, not shown.
- **A burst meets a small instance first.** Serverless v2 scales in 0.5 ACU steps within seconds, but the first
  seconds run at the current size.
- **The writer sits at its floor almost all the time**, so any effect shows up as latency or CPU, not as a capacity change.

## Measuring
1. **Before the deploy:** run `docs/prompts/agent-d2-floor-measure.txt` once (it detects BASELINE mode). It adds what
   section 10 lacked: free memory and latency.
2. **A CPU alarm** on the prod writer (`pyvar-prod-aurora-writer-cpu`, in `data_stack.py`): average CPU at or above
   85% for 15 minutes. A placeholder, not tuned. The existing ALB alarms (`pyvar-prod-api-latency-p95` above 5 s,
   `pyvar-prod-api-5xx` above 10 in 5 minutes) report what a client feels. The CPU alarm follows the instance that is
   the writer today: after a failover it would watch the other one.
3. **After the deploy:** run the same prompt again after at least 7 days (it detects AFTER mode) so that one Saturday
   maintenance window is inside it; again after 30 days.

## Rollback rules (proposed, untuned; the owner may change them)
Set `aurora_min_acu=1.0` for prod and deploy (the one line in `pyvar-cdk/config.py`) if, in the AFTER window:
- the writer CPU alarm fires, or an API latency or 5xx alarm fires that did not fire in the BEFORE window; or
- the lowest free memory of the writer is under 100 MiB; or
- an RDS reboot or failover event follows the change. (A minimum-capacity change is expected to apply without
  one; not verified.)

## The prompt
See `docs/prompts/agent-d2-floor-measure.txt` (read-only, prod only, under 5 KB).

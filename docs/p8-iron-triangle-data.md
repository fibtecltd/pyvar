# P8 Task 6 — Iron Triangle data contract

Investigates what real data exists for each of the Iron Triangle's three axes
(Time, Cost, Accuracy) in a pyvar context, per the P8 lead prompt. This is a
**data contract only** — the visual component is a separate follow-up, once
the Claude Design/Fable output for it exists (see `iron-triangle-design-prompt.md`).
Nothing here is fabricated: each axis below states plainly whether the value
is real, an aggregate estimate, or a static/slowly-updated score, so the
eventual UI never presents an estimate as if it were a live per-request metric.

---

## 1. Time — REAL, per-job

**Source:** `api_usage.duration_ms` (Postgres, `storage/models.py::ApiUsage`),
written by the usage-tracking middleware (`api/middleware/usage.py`) after
every `/api/v1/*` request, off the hot path.

**Why this over `pyvar/JobCount`:** `pyvar/JobCount` (the CloudWatch custom
metric emitted by `tasks/var_task.py::_emit_job_metric`) is a **counter**
only — its own docstring calls it "a single-count CloudWatch metric for job
accounting." It has no duration dimension at all; it answers "how many jobs
ran / errored," not "how long did a job take." `api_usage.duration_ms` is
therefore the only real per-job timing source in the system today.

**Contract:**
- Real, per-request, millisecond precision.
- Available per domain/function (`api_usage.domain`, `api_usage.function_name`)
  and per tier (`api_usage.tier`).
- Caveat: `api_usage` is operational telemetry with a retention/pruning policy
  (`migrations/versions/0003_api_usage.py` — recommended ~90 days, not yet
  automated), so "Time" for a job older than the retention window won't be
  queryable after that policy is implemented.
- Caveat: wall-clock request duration includes queueing/dispatch overhead for
  the async job pattern (`POST /compute` returns immediately; the actual
  compute happens in the Celery worker) — for `var.py`-style endpoints this
  duration is the API's own response time, not the worker's compute time.
  Domain endpoints (`api/routes/market_risk.py` etc.) compute synchronously
  in the request/response cycle, so their `duration_ms` **is** true compute
  time. Any Iron Triangle "Time" display should distinguish these two
  endpoint families rather than treat all `duration_ms` values as equivalent.

---

## 2. Cost — NOT measurable per-job; aggregate monthly only, and even that is
dominated by fixed infrastructure, not job-driven compute

**Investigated:** whether a reasonable per-job cost estimate can be derived
from AWS Cost Explorer data (P7 Task 7, `docs/p7-cost-review.md`) divided by
jobs processed in the same period.

**Finding:** no per-job cost tracking exists anywhere in the codebase or
infrastructure — confirmed by grep across `engine/`, `tasks/`, `api/`,
`storage/`, and all `pyvar-cdk/` stacks. The only cost data that exists is
account-level Cost Explorer output, and per `docs/p7-cost-review.md`'s own
17-day-extrapolated breakdown, the **top cost drivers in dev are fixed
infrastructure, not variable job compute**:

| Rank | Service | Extrapolated /month |
|---|---|---|
| 1 | VPC (endpoints, 2 AZs) | ~$87 |
| 2 | ElastiCache Serverless | ~$59 |
| 3 | EC2 - Other (NAT Gateway) | ~$35 |

EC2 Spot worker compute (the actual per-job cost driver — `compute_stack.py`,
`worker_min_capacity=0`, scale-to-zero) does not even appear in the top-3
breakdown for this period, consistent with dev's low job volume and
scale-to-zero design: most of the account's dev spend is infrastructure that
exists whether or not any job ever runs.

**Why a per-job average would be misleading, not just imprecise:** dividing
total monthly cost by job count would blend genuinely fixed costs (VPC
endpoints, NAT Gateway, the Aurora/ElastiCache floor) into a "per-job" number,
producing something that looks like marginal compute cost but is actually
mostly amortized overhead. A worker Spot instance-hour cost isolated
specifically from Cost Explorer, divided by jobs processed on that instance
in the same window, would be a legitimate marginal-cost estimate.

**Update (2026-08-06):** the isolation gap described above is closed. The
`CostComponent=spot-worker-compute` tag added to the worker LaunchTemplate
(`compute_stack.py`, PR #193) is live in Cost Explorer as a filterable
dimension — confirmed via `aws ce get-tags`/`get-cost-and-usage`: tagged
spend shows up cleanly under "Amazon Elastic Compute Cloud - Compute" with
no NAT Gateway or other EC2 - Other line items mixed in. Isolating the
Spot compute cost is now possible; the actual marginal-cost figure (isolated
cost ÷ jobs processed on that instance in the same window) still needs to be
computed once dev job volume is high enough to be meaningful — not done
here.

**Contract:**
- No real per-job cost exists today.
- Aggregate account-level monthly cost exists (Cost Explorer) but is not
  representative of per-job marginal cost given fixed-cost dominance.
- **Recommendation for the eventual UI:** do not display "Cost" as a
  per-request number at all. If the Iron Triangle needs a Cost axis value,
  it should be presented explicitly as an aggregate ("~$400/month gross
  infrastructure cost," with a note on what portion is fixed vs. variable),
  not a fabricated per-job figure with false precision.

---

## 3. Accuracy — NOT a live per-request metric; a static, validation-derived score

**Investigated:** whether any live per-request accuracy signal exists.

**Finding:** none exists, and none can exist in the way Time/Cost can — a
production VaR/pricing/capital request has no ground-truth answer to compare
against at request time. The only real accuracy evidence in this codebase is
the P5a cross-validation work: `tests/validation/` contains **8 test files**
(one per domain, including `test_regulatory_ref.py` for Regulatory & Compliance
— not an extra file on top of the 8), **627 test functions** cross-validating engine
output against external reference values/formulas — closed-form
Black-Scholes, analytical VaR, published Basel/FRTB worked examples —
within stated tolerances (typically ≤0.1%–0.5% depending on the domain —
see `docs/pyvar_release_plan.md`'s validation section for the tolerance
table).

**Correction:** this section previously also listed QuantLib as a source of
cross-validation. That was false. `QuantLib` appears in
`requirements-heavy.txt` and in the AMI-bake install list
(`pyvar-cdk/stacks/ami_stack.py`) but is not imported or used anywhere in
`tests/validation/` or any other test — grep confirms zero references. It
is an unused dependency, not a validation source. If QuantLib cross-checks
are added to `tests/validation/` in the future, this section should be
updated to reflect that truthfully at the same time — not before.

This process found and fixed a real numerical bug during P5a (`docs/P5A_BLOCKERS.md`,
BLOCKER 1 — `minimum_variance_portfolio`/`risk_parity_portfolio` SLSQP
premature convergence on small-magnitude covariance, since fixed on
`fix/portfolio-slsqp-convergence`, closing #56) — meaning this is a real,
non-trivial validation exercise, not a rubber stamp.

**Contract:**
- Not live, not per-request, not per-tier.
- A single **static (or slowly-updated, e.g. re-run per release) score**:
  the proportion of the 627 validation assertions currently passing within
  tolerance, or more simply a badge-level indicator ("all engine functions
  independently validated against regulatory/analytical references — see
  `tests/validation/`") rather than a percentage that implies more precision
  than a pass/fail test suite actually carries.
- **Recommendation for the eventual UI:** treat this as a trust/credibility
  badge, updated when `tests/validation/` is re-run (e.g. on release), not as
  a dynamic per-request "accuracy: 99.97%"-style number — there is no
  per-request ground truth to compute that against, and presenting one would
  misrepresent what's actually being measured.

---

## Summary for the visual component (once it exists)

| Axis | Live/per-request? | Real today? | Recommended representation |
|---|---|---|---|
| Time | Yes (per-domain-endpoint) | Yes — `api_usage.duration_ms` | Live/near-live per-function average |
| Cost | No | Aggregate only, fixed-cost-dominated | Aggregate monthly figure with a fixed-vs-variable caveat, not a per-job number |
| Accuracy | No | Yes, but static | A validation badge/score, refreshed per release, not per request |

Do not build the visual component against this contract until the separate
design output (Claude Design/Fable) exists — this document is the
integration spec for when it does.

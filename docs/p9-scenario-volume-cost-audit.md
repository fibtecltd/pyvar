# Scenario-volume cost audit: 10k / 100k / 1M scenarios per month

Independent audit commissioned 2026-08-07 to project AWS cost at three monthly
Monte Carlo scenario-volume tiers. Run by a fresh agent with no prior exposure to
this repo's other cost analyses, using only repo artifacts (code, CDK config,
P7/P8 investigation docs) — no live AWS Cost Explorer access.

## Definitions used

- **Scenario** = one Monte Carlo simulation path. Each API job (e.g.
  `POST /var/compute`) runs `n_simulations` paths, a request parameter
  (`schemas/var.py`, `config.py`). Free tier defaults to 10,000 paths/job.
- **Monthly scenario count** = (jobs submitted in the month) × (paths per job).
- Tier caps on paths/job, from `api/middleware/auth.py:39-44`: free = 10,000,
  pro = 100,000, enterprise/internal = 500,000. Daily job-count caps, from
  `config.py:113-115`: free = 10/day, pro = 500/day, enterprise = unlimited.

| Tier | Combo used | Alternative also considered |
|---|---|---|
| 10,000 scenarios/mo | 1 job × 10,000 paths (free tier default) | — |
| 100,000 scenarios/mo | 10 jobs × 10,000 paths (free tier) | 1 job × 100,000 paths (pro tier) |
| 1,000,000 scenarios/mo | 10 jobs × 100,000 paths (pro tier) | 2 jobs × 500,000 (enterprise); 100 jobs × 10,000 (free) |

## Method note

This is a **bottom-up estimate assembled entirely from repo artifacts**, not
AWS Cost Explorer. The only real billing data in the repo
(`docs/p7-cost-review.md`) is a 17-day dev-environment window at near-zero job
volume. Everything tier-specific below is extrapolation, clearly labeled.
`docs/p8-iron-triangle-data.md` — a prior, independent investigation in this
same repo — separately concluded that **no per-job cost tracking exists
anywhere in the codebase or infrastructure**, and that dividing account-level
cost by job count "would be misleading, not just imprecise." This audit
respects that finding rather than overriding it with a fabricated
per-scenario rate.

Source labels: **(a)** read directly from a repo file/doc (path cited); **(b)**
arithmetic derived from (a) (formula shown); **(c)** external AWS public list
pricing (fetched via web search, not cross-checked against the AWS Pricing
Calculator — order-of-magnitude only).

## Fixed infrastructure baseline (near-identical across all three tiers)

Derived from `docs/p7-cost-review.md` (a), a dev Cost Explorer pull
(2026-07-01→07-17) extrapolated to a 31-day month, **gross** (see Hard Gap 1
on the unconfirmed credit):

| Line item | Dev-observed (a) | Prod-shaped estimate | Basis |
|---|---|---|---|
| VPC Interface Endpoints (2 AZ) | ~$87/mo | ~$87/mo (unchanged) | p7-cost-review.md:54-61 (a) |
| NAT Gateway | ~$35/mo (1 GW, dev) | ~$70/mo (2 GWs, prod override) | p7-cost-review.md:103-121 (a) + doubled (b) |
| ElastiCache Serverless | ~$59/mo (dev, low/spiky) | **Unknown at prod scale** | p7-cost-review.md:81-101 (a); scaling = gap |
| Aurora SV2 | ~$45/mo floor (0.5 ACU dev) | ~$90-180/mo floor (1.0 ACU min prod) | data_stack.py comment (a) → derived rate (b) |
| Fargate API (base capacity) | ~$18-23/mo (1 task, dev) | ~$36-46/mo (2 tasks, prod) | public Fargate pricing (c); cross-checks with `docs/pyvar_release_plan.md:382`'s own ~£18/mo target (a) |
| CloudFront + WAF | not itemized | ~$8-15/mo | edge_stack.py rule count (a) + public pricing (c) |
| CloudWatch Container Insights | — | ~$1-2/mo | api_stack.py:116 comment (a) |

**Prod-shaped fixed baseline ≈ $349–$430/month**, essentially flat regardless
of which of the three scenario tiers is served.

## Volume-driven costs

### EC2 Spot worker compute

Two independent repo benchmarks, both on the real `c5.xlarge` worker type
(`pyvar-cdk/config.py:39-40`):

- Pure warm JIT compute (a): `run_monte_carlo_var` at n_simulations=100,000 =
  0.007s (`docs/p7-numba-profiling-results.md:48`) → ~$2×10⁻¹² per scenario.
- Real end-to-end pipeline (a): 50 jobs × 100,000 paths = 5,000,000 scenarios
  in 44.497s wall-clock (`docs/p7-celery-concurrency-results.md:120-126`) →
  ~$2.7×10⁻¹⁰ per scenario.

Both bound pure compute-seconds cost at sub-cent for all three tiers.

**The real EC2 cost driver is the scale-to-zero activation tax, not
compute-seconds.** `worker_min_capacity=0` means every burst of traffic can
pay a cold-start penalty: ~90s target-tracking warmup + 60s termination
drain, plus either ~25s (baked AMI) or ~5 minutes (stock AL2023, per
`compute_stack.py:283`) of boot time depending on `worker_use_baked_ami`.
Worst-case (every job scales from zero independently):

| Tier | Jobs | Activations | Cost/activation | Total EC2 tax |
|---|---|---|---|---|
| 10k (1×10k) | 1 | 1 | ~$0.006 (baked) / ~$0.012 (non-baked) | ~$0.006-0.012 |
| 100k (10×10k) | 10 | 10 | same | ~$0.06-0.12 |
| 1M (10×100k) | 10 | 10 | same | ~$0.06-0.12 |

Under $0.15/month at every tier — negligible next to the fixed baseline.

**Config inconsistency surfaced during this line item** (addressed below):
`pyvar-cdk/config.py`'s `prod` override never set `worker_use_baked_ami=True`,
so as configured it inherited the dataclass default (`False`) — the slow,
non-baked boot path — contradicting `CLAUDE.md §11`'s stated intent
("In production: pre-bake AMI with compiled Numba cache").

### SQS, S3

- **SQS**: not broken out in the cost review, implying negligible at dev
  volume. At public FIFO pricing ~$0.50M requests (c), even 10 calls/job × 10
  jobs (largest job-count tier) ≈ $0.00005 — immaterial.
- **S3**: only jobs with `n_simulations > 10,000` write to S3
  (`tasks/var_task.py:257`, `config.py:104`). The 10k and 100k (10×10k combo)
  tiers write zero S3 objects. The 1M tier (10×100k) writes 10 Parquet
  objects, ~2.7MB total compressed — well under $0.01/month.

## Per-tier total

| Tier | Fixed infra | EC2 Spot (worst-case) | SQS + S3 | **Total/month** |
|---|---|---|---|---|
| 10,000 scenarios/mo | $349 – $430 | ~$0.006-0.012 | ~$0 | **~$349 – $430** |
| 100,000 scenarios/mo | $349 – $430 | ~$0.06-0.12 | ~$0 | **~$349 – $430** |
| 1,000,000 scenarios/mo | $349 – $430 | ~$0.06-0.12 | ~$0.01 | **~$349 – $430** |

**The three tiers are cost-indistinguishable at this granularity.** This is
the direct, repo-grounded consequence of two facts: (1) scale-to-zero EC2
workers plus fast Numba JIT compute means raw simulation volume costs
fractions of a cent even at 1M/month, and (2) every dominant cost line (VPC
endpoints, NAT gateway, ElastiCache floor, Aurora floor, Fargate base
capacity) is provisioned independently of job volume in this architecture.
Scenario count would only start moving the total once job concurrency forced
ASG worker fleets to stay resident for meaningful fractions of the month, or
request volume pushed Fargate/ElastiCache autoscaling — neither is triggered
by 10k-1M scenarios/month given this repo's tier caps (1M scenarios needs
only ~10 jobs).

## Hard gaps — cannot be filled from this repo

1. **No cost data at any of the three requested volumes.** The only real
   bill is dev, near-zero job volume, over 17 days, with a ~$76 unexplained
   credit masking ~34% of gross usage — its durability was never confirmed.
2. **No production load test.** The closest thing (a 50-job burst in
   `p7-celery-concurrency-results.md`) is self-flagged by its own authors as
   inflated by an unrelated AWS-side edge mitigation triggered during the
   test.
3. **Real SQS call volume per job is undocumented** — bounded generously
   above, immaterial at these volumes, but not a measured number.
4. **Aurora ACU-hour dollar rate is inferred, not stated** — a 2x
   uncertainty band on that line item.
5. **ElastiCache Serverless cost at real production traffic is unknown** —
   the dev figure is explicitly a "low/spiky" dev pattern per its own source
   doc.
6. **Real EC2 Spot market price is unknown** — only the configured ceiling
   (`spot_max_price="0.11"`) exists in the repo.
7. **No per-job/per-simulation cost telemetry exists**, confirmed
   independently twice: `docs/pyvar_release_plan.md:361` lists
   `cost_per_simulation()` as planned but never implemented (confirmed by
   grep against the live codebase), and `docs/p8-iron-triangle-data.md:52-92`
   reaches the same conclusion and explicitly recommends against presenting a
   fabricated per-job figure.
8. **AWS public list-pricing figures used above** were pulled from general
   web sources, not the AWS Pricing Calculator — order-of-magnitude only.
9. **No confirmation the `prod` stack has ever actually been deployed and
   billed** — everything prod-shaped here is `dev` data rescaled using
   `config.py`'s override deltas, not an observed bill.

## Bottom line

Treat every number above as directionally useful for a rough order-of-magnitude
budget conversation, not as a number for a board deck or a customer pricing
model. The fixed-infrastructure baseline (~$350-430/month) is grounded in a
real AWS bill, but that bill is itself a dev-environment, near-zero-traffic,
credit-distorted 17-day snapshot rescaled to prod-shaped config — never
cross-checked against an actual prod invoice. The volume-driven component is
genuinely, robustly small at 10k-1M scenarios/month given this architecture's
scale-to-zero workers and fast JIT kernels — well-supported by two independent
repo benchmarks — but "small" was extrapolated from single-run, short-window
benchmarks explicitly flagged by their own authors as methodologically
caveated, not from sustained load tests at these volumes. Anyone budgeting
off this should independently verify the Fargate/Aurora/SQS/S3/CloudFront
public pricing figures and, ideally, run an actual multi-day load test at
each target volume before committing to a number externally.

## Config inconsistency: `worker_use_baked_ami` in prod — fixed

See `pyvar-cdk/config.py`'s `prod` override block. The dataclass default was
`worker_use_baked_ami=False` ("Hypothesis B" — stock AL2023, ~5min runtime
`pip install` boot). Only the `dev` override set it `True` ("Hypothesis C" —
pre-baked AMI, ~25s boot), with the comment "AMI pipeline live — use baked
AMI (P6)". `prod` never overrode it, so a `prod` deploy inherited `False` —
contradicting `CLAUDE.md §11`'s stated production intent.

`docs/ami-cold-start-retrospective.md` (the P6 investigation that built this
pipeline) frames Hypothesis C as the validated, intended steady-state path
(cold start 3s avg vs. 15-20min) and Hypothesis B as an explicit fallback
"for rapid dev iteration before a new AMI bake is triggered" — i.e. the
opposite of what the previous per-env config produced (dev = baked, prod =
not baked).

**Fix applied:** `prod`'s override block in `pyvar-cdk/config.py` now sets
`worker_use_baked_ami=True`, with a comment citing `CLAUDE.md §11`. Scope was
deliberately kept to `prod` only — `staging` still defaults to `False`
(fast-iteration boot path), since CLAUDE.md's production intent doesn't
extend a stated requirement to staging.

**Update — the trigger is now automated.** `pipeline_stack.py`'s shared
`Synth` `ShellStep` now includes `_ami_bake_commands()`: a hash of
`ami_stack.py` (the sole source of the Image Builder recipe/component) is
compared against `SSM /pyvar/prod/last-baked-ami-hash`. Unchanged → a no-op
(one hash compare, ~instant). Changed → it calls `aws imagebuilder
start-image-pipeline-execution` against `pyvar-prod-worker-pipeline` and
blocks, polling `get-image` every 45s (30-minute cap), until the new AMI
reaches `AVAILABLE` — then records the new hash. It runs **before** `cdk
synth`, not after, because `ec2.MachineImage.lookup()` resolves the AMI via a
CDK **context lookup made during synth**, not at CloudFormation deploy time —
a trigger placed anywhere after synth (e.g. a Prod-stage `pre` step) could
kick off a real bake but couldn't affect the AMI ID already baked into that
run's already-synthesized template, which would silently deploy on the
*previous* AMI. Fails **closed**: if the bake can't start (pipeline doesn't
exist), or it reports `FAILED`/`CANCELLED`, or it times out, the step exits 1
and blocks the whole pipeline run — never a silent stale-AMI deploy. Verified
via dry-run against a stubbed `aws` CLI (skip path, successful-bake path,
`FAILED`-status path, and the "pipeline not found" path all behave as
intended) and a full `cdk synth` producing a template that carries the new
buildspec commands and exactly-scoped IAM (`imagebuilder:StartImagePipelineExecution`
+ `imagebuilder:GetImage` on the prod pipeline/image ARNs, `ssm:GetParameter`/
`PutParameter` on the one hash parameter) — no live AWS account was available
to actually exercise a real bake end-to-end.

**Tradeoff accepted, not fully eliminated:** because the trigger has to live
in the *shared* Synth step (there's exactly one per pipeline run, covering
both stages' cloud assemblies), a Prod-only AMI-recipe change makes the Dev
stage's deploy in that same pipeline run wait on the bake too. This only
fires on the rare push that touches `ami_stack.py`; every other push pays
just the hash-compare no-op. A cleaner decoupled design (bake asynchronously,
let the *next* run pick it up) was considered and rejected — it would silently
deploy the *current* run on a stale AMI, which is worse than the coupling.

**One manual step remains, but it's now one-time, not per-deploy.** The
Image Builder pipeline resource itself (`AmiStack` / `pyvar-prod-ami`) still
needs bootstrapping once, out of band, before this trigger has anything to
call:

```
cdk deploy pyvar-prod-ami --context env=prod --context account=ACCOUNT
```

`AmiStack` is deliberately kept out of `PyvarDeployStage` (not part of the
per-push CDK Pipeline stage) — folding it in would recreate the same
ordering problem one level up: its CloudFormation resources would only exist
*after* a stage deploy that itself depends on `cdk synth` having already run
with a resolved AMI ID. This mirrors `pyvar-pipeline` itself, which app.py's
own module docstring already documents as a one-time manual bootstrap
("Deploy this stack once manually; it takes over from there") — same
category of precondition, not a new kind of manual step.

# pyvar-dev-pipeline's Prod approval gate — status

Status: **toggle added, gate still enabled (required). Two pending approvals
rejected so far. No decision yet on when/whether to actually disable it.**

## Why this doc exists

A "FAILED" pipeline notification led to investigating `pyvar-dev-pipeline`
(the CodePipeline resource backing the `pyvar-pipeline` CloudFormation
stack — the physical pipeline name doesn't match the stack id, since the
pipeline was originally bootstrapped with `env=dev` context). That
investigation surfaced two things worth a durable record: a stale
7-day approval timeout, and a previously-unnoticed dual-deployment-path
risk affecting dev.

## Finding 1 — the FAILED notification was a stale 7-day approval timeout

`pipeline_stack.py`'s Prod stage has always required a manual
`ApproveProductionDeploy` step before deploying/migrating prod. **Every
prod deployment in this project has actually been done via direct,
manually-verified `cdk deploy pyvar-prod-*` instead** — the pipeline's own
Prod stage has never once completed.

The specific notification traced back to an execution triggered by PR
#224's merge on 2026-08-09. Its Dev stage deployed successfully that same
day, then it sat at `ApproveProductionDeploy` for **exactly 168 hours (7
days)** — CodePipeline's hard maximum wait for a manual approval action —
before auto-failing on 2026-08-16. Confirmed via
[AWS's own manual approval action docs](https://docs.aws.amazon.com/codepipeline/latest/userguide/approvals-action-add.html)
that 7 days is the platform maximum, not a project-specific setting.

## Finding 2 — dev has an unattended dual-deployment-path (pipeline + manual)

While investigating, `cdk diff` showed unexpected drift on
`pyvar-dev-api`/`pyvar-dev-compute`/`pyvar-dev-edge` — traced to an image
tag (`8cfdd2a`, a real git SHA) that didn't come from any manual deploy.
**`pyvar-dev-pipeline`'s Dev stage has no approval gate and runs
automatically on every push to master** — it has been redeploying every
dev stack on every merge this entire session, fully unattended and
concurrently with manual `cdk deploy pyvar-dev-*` commands. This explains
an earlier confusing `"Stack ... is in UPDATE_IN_PROGRESS state and can
not be updated"` error hit during the Sentry rollout (docs on that work
don't mention this cause — recorded here instead). Not something that has
broken anything (CloudFormation just cleanly rejects the losing concurrent
update), and both paths converge to the same target state since they
deploy from the same committed config — but it's a real source of
avoidable confusion, and it's exactly the dynamic prod would newly acquire
if the approval gate below is ever disabled.

## What was done

1. **First pending approval rejected** (2026-08-16, execution triggered by
   PR #240's merge) — cleared cleanly rather than left to time out again
   in 7 days.
2. **Full dev/prod status check** before any gate decision: prod fully
   healthy, `cdk diff` clean on every stack, zero CloudWatch alarms in
   `ALARM` state, live traffic confirmed correct. Dev fully healthy
   functionally, with only cosmetic `cdk diff` noise (image tag, a
   resource-tag path string, a stack `Description` string — none
   functional). Nothing outstanding blocks either environment's correct
   operation independent of this gate question.
3. **PR #241 — added `cfg.require_prod_approval`** (`config.py`, default
   `True`) gating the `ManualApprovalStep` in `pipeline_stack.py`'s Prod
   stage. Explicitly **kept at `True`** — this PR added the capability to
   disable it later without actually disabling it, since doing so would
   remove the gate on the very pipeline execution that carries the change
   (self-mutating pipeline) and let every `pyvar-prod-*` stack deploy
   unattended for the first time ever. Verified via direct JSON comparison
   of the live vs. newly-synthesized `pyvar-pipeline` template that the
   `Prod` stage's action list (names/order/categories) is byte-identical
   with the toggle at its default — confirmed no behavior change before
   merging.
4. **Watched the resulting pipeline execution live** (`b5aa86b0`, from PR
   #241's merge) end-to-end: `Source` → `Build` (incl. a full Docker
   image build+push) → `SelfMutate` (picked up the toggle code cleanly) →
   `Assets` → `Dev` stage (every stack deployed successfully, plus
   `RunDbMigration-dev` and `SmokeTest` both `Succeeded`) → reached
   `ApproveProductionDeploy` in `Prod`, exactly as before. Confirmed in a
   real run, not just a synth diff, that the refactor changed nothing.
5. **Second pending approval rejected** (2026-08-16, this same execution)
   per explicit instruction — cleared cleanly.

## Current state

- `require_prod_approval = True` in `config.py` — gate is live and
  enforced exactly as it always has been.
- No pending approvals, no in-progress executions. Pipeline is idle,
  waiting for the next push to master.
- Latest execution (`b5aa86b0`): `Failed` (rejected, not timed out) —
  Source/Build/UpdatePipeline/Assets/Dev all `Succeeded`, only `Prod`
  shows `Failed`.

## Open — not yet decided

**Whether/when to actually flip `require_prod_approval` to `False`
remains an open decision, not made here.** When it happens:
- It should be done as its own deliberate step, not bundled with anything
  else, with someone actively watching.
- The very execution that carries the flip will self-mutate and restart
  under the gate-less structure immediately — expect the pipeline's Prod
  stage to run to completion, unattended, for the first time ever in this
  project (including `RunDbMigration-prod`, which has never actually run
  via the pipeline before).
- Until that decision is made, expect this same pattern to repeat on every
  future merge to master: a new execution reaches `ApproveProductionDeploy`
  and needs to be either rejected (clean) or left to time out (7 days,
  another `FAILED` notification).

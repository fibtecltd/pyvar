# pyvar-dev-pipeline's Prod approval gate — status

Status: **gate still enabled (required), `require_prod_approval` unchanged.
As of 2026-08-16, two pending approvals had been rejected and the pipeline's
Prod stage had never completed. That pattern no longer holds — see the
2026-08-20 update below: three more executions reached the gate and were
approved, and the Prod stage (including `RunDbMigration-prod`) has now
completed via the pipeline itself, twice, confirmed via CloudTrail. As of
2026-08-22, `ApproveProductionDeploy` also has a working Slack integration
(PR #258 + AWS Chatbot console setup) — see that update below. Decision to
flip `require_prod_approval` to `False` remains separately unmade,
deliberately deferred until after the P9 exit gate (48h healthy prod +
post-launch monitoring).**

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

## Current state (as of 2026-08-16 — see 2026-08-20 update below)

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

  **This prediction did not hold — see the 2026-08-20 update below.** The
  gate itself is unchanged (`require_prod_approval` is still `True`); what
  changed is that pending approvals started actually being approved instead
  of rejected. The decision to flip `require_prod_approval` to `False`
  remains separately unmade.

## Update (2026-08-20) — approvals actually started; Prod stage now completes via the pipeline

Between 2026-08-17 and 2026-08-19, a #41–#46 bug-fix series (PRs #243,
#244, #245, #246, #251 — CORS credential-reflection, a cross-environment
Lambda `API_BASE_URL` bug, hardcoded dev-domain literals in email links and
the portal client, and an `app_env` short/long-form comparison bug)
produced three more executions that reached `ApproveProductionDeploy`.
Unlike every prior execution, all three were **approved**, not rejected or
left to time out:

| Execution   | Revision (PR)                | Outcome |
|-------------|-------------------------------|---------|
| `a0098e07`  | `66698597` (PR #242)          | Approved 2026-08-17 — see note below |
| `34dfd841`  | `0a99ccb` (PRs #243/#244/#245/#246) | Approved 2026-08-17 |
| `cd132fdf`  | `e7b16808` (PR #251)          | Approved 2026-08-19 |

All three ran their full `Prod` stage to completion for the first time in
this project's history — `RunDbMigration-prod`, all `pyvar-prod-*` stack
deploys, and `ProdSmokeTest` all succeeded on each. Confirmed via CloudTrail
that the CloudFormation `ExecuteChangeSet` calls for `pyvar-prod-api` were
invoked by `codepipeline.amazonaws.com` through the CDK bootstrap deploy
role — genuinely pipeline-driven, not a manual `cdk deploy pyvar-prod-*`
run from a workstation (the pattern Finding 1 established as the norm up to
this point). Prod's running image tag (`e7b1680`) was independently
verified to match PR #251's merge commit SHA exactly.

**Operational gotcha worth recording:** `a0098e07` had been sitting queued
at `ApproveProductionDeploy` since before this fix series existed (it
carries PR #242 — this very doc's own original commit). Because CodePipeline
locks the `Prod` stage to one execution at a time, every later execution
(`14c4bb0e`, `a8213417`, `f2167735`, all superseded) queued up behind it
without any obvious signal that an *older*, unrelated execution — not the
one just merged — was what would actually run next. The first approval
given during this series went to `a0098e07` by mistake, deploying PR #242's
(inert, docs+toggle-only) changes rather than the intended fix bundle; the
CORS vulnerability was confirmed still live via a direct HTTP check
immediately afterward. The correct execution (`34dfd841`) only reached its
own fresh `ApproveProductionDeploy` once `a0098e07` cleared the stage. When
multiple commits land close together while an old approval has been sitting
unresolved, **check which specific `pipelineExecutionId` an approval token
belongs to (`list-action-executions --filter pipelineExecutionId=...`)
before approving** — the action name and `get-pipeline-state`'s "latest"
view alone aren't enough to tell them apart.

`require_prod_approval` remains `True`. This update does not change the
open decision above — it only corrects the doc's prediction now that the
gate is actually being exercised as an approve/reject decision point rather
than a reject-only formality.

## Update (2026-08-22) — Slack integration for ApproveProductionDeploy (task #47)

`ApproveProductionDeploy` now posts to Slack (`#pyvar-prod-approvals`,
workspace `ops@fibtec.co.uk`, team ID `T0BSSHVM7R6`) via AWS Chatbot, in
addition to the existing `ops@fibtec.co.uk` email notification both already
went to. Approve/Reject can now be actioned directly from Slack, not just
via the CodePipeline console or CLI.

**What's deployed:**
- `pyvar-dev-chatbot-pipeline-approval` (PR #258,
  `pyvar-cdk/stacks/pipeline_stack.py`) — an IAM role scoped to exactly
  `codepipeline:GetPipelineState` + `codepipeline:PutApprovalResult` on
  this one pipeline's ARN, plus read-only `cloudwatch:DescribeAlarms`.
  Created via CDK specifically so this permission grant stays reviewable
  and versioned, rather than letting the AWS Chatbot console's channel
  wizard create its own role with a broader default policy.
- An `AWS::Chatbot::SlackChannelConfiguration` (console-created, not
  CDK-managed — see "Why this isn't in CDK" below), subscribed to the
  existing `pyvar-pipeline-notifications` SNS topic, using the role
  above. Verified live via `aws chatbot describe-slack-channel-
  configurations`: correct team/channel IDs, correct (CDK-managed) role
  ARN — no console-generated role — correct SNS topic ARN.

**Why this isn't in CDK:** the Slack workspace has to be OAuth-authorized
via the AWS Chatbot console first — that step cannot be automated via
CDK/CLI, it needs a live browser session authenticated to both AWS and the
target Slack workspace. The first authorization attempt didn't persist at
all (confirmed via `aws chatbot describe-slack-workspaces`, empty in both
eu-west-1 and us-east-1) — backing out of the console's channel-setup
wizard before completing it, done deliberately to keep the channel
resource CDK-managed, appears to have discarded the whole workspace
authorization, not just the channel part. Redoing the flow and completing
it fully (workspace auth + channel config together) is what actually
persisted. Given that, the channel configuration resource itself stays
console-managed for now; a future CDK import of the existing resource is
possible but not done here.

**Guardrail policy is `AdministratorAccess` — this is intentional, not a
misconfiguration.** AWS Chatbot's console requires at least one guardrail
policy, and guardrail policies apply as an *intersection* with the
channel's own IAM role — they can only subtract permissions, never add
them. Since the role above is already scoped to exactly two
CodePipeline actions on one pipeline, intersecting with `AdministratorAccess`
changes nothing; the channel still can't do anything beyond what the role
allows. The alternative, `ReadOnlyAccess`, would have been a real bug:
`codepipeline:PutApprovalResult` is a mutating action, so a ReadOnly
guardrail would let Chatbot render the approval message but silently block
the Approve/Reject action itself — a known, documented gotcha with AWS
Chatbot + CodePipeline manual approvals specifically, not a hypothetical
concern here.

**Update (2026-08-22, later same day) — end-to-end Slack notification
confirmed working.** `#pyvar-prod-approvals` has now been confirmed to
receive the actual `ApproveProductionDeploy` notification for real, not
just in configuration. This closes the one item left open above: the
wiring (team ID, channel ID, role ARN, SNS topic ARN) was already verified
via CLI, and now the live notification path itself is confirmed too.

Task #47 (Slack integration for `ApproveProductionDeploy`) is complete.

## Update (2026-08-24) — real test notification delivered; one more gotcha found and fixed

The 2026-08-22 "confirmed working" update above verified the notification
*path* (SNS topic → Chatbot → channel) was wired correctly, but hadn't yet
sent an actual test message through it. Doing that surfaced one more
gotcha, now fixed:

- **A raw plain-text SNS publish never reached Slack.** It delivered fine
  to the `ops@fibtec.co.uk` email subscription on the same topic, but AWS
  Chatbot silently drops anything that isn't EventBridge-shaped or its own
  "custom notification" JSON schema (`version`, `source: "custom"`,
  `content.description` required — see
  [the Chatbot custom-notifications doc](https://docs.aws.amazon.com/chatbot/latest/adminguide/custom-notifs.html)).
  Republishing in that schema still didn't show up — a second, unrelated
  failure.
- **Root cause of the second failure: the bot was never actually a member
  of `#pyvar-prod-approvals`.** Workspace-level OAuth authorization (the
  2026-08-22 update above) does not automatically add the Chatbot/"Amazon Q
  Developer" bot user to any specific channel, especially a private one.
  Inviting it (`/invite @Amazon Q Developer`) fixed it immediately — the
  same schema-valid test message, republished after the invite, appeared
  in the channel. **Anyone setting up a new AWS Chatbot Slack channel for
  this pipeline (or copying this pattern elsewhere) needs to remember to
  invite the bot into the channel as a separate, manual step** — the
  console wizard and the workspace authorization do not do this for you.
- **Follow-up question, answered and closed:** adding another Fibtec
  teammate to `#pyvar-prod-approvals` is a plain Slack-side action (just
  invite them) — no AWS-side change needed. The one thing worth knowing:
  the channel's `UserAuthorizationRequired: false` setting means everyone
  in the channel approves/rejects through the same shared IAM role
  (`pyvar-dev-chatbot-pipeline-approval`), not individually-authorized,
  individually-audited access. Switching to `UserAuthorizationRequired:
  true` would give per-user authorization at the cost of extra setup per
  person. Decision: the shared-role model is fine for now — not revisited
  further here.

Task #47 is fully closed: wiring verified, a real message delivered
end-to-end, and the one operational gotcha (bot channel membership)
documented for next time.
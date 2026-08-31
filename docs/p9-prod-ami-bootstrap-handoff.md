# Handoff: bootstrap `pyvar-prod-ami` and confirm the bake trigger

## Status: CLOSED — confirmed done, 2026-08-31

Checked against the real Fibtec prod account (`347228921290`, via
`aws sts get-caller-identity`) rather than assumed:

- `aws cloudformation describe-stacks --stack-name pyvar-prod-ami` →
  `UPDATE_COMPLETE` (created 2026-08-08T08:18:27Z, last updated
  2026-08-08T15:38:27Z). Someone already ran the bootstrap deploy from
  this handoff's step 5 before this check.
- `aws imagebuilder get-image-pipeline` on the stack's
  `ImagePipelineArn` output → `pyvar-prod-worker-pipeline`, `status:
  ENABLED`, `lastRunStatus: AVAILABLE`.
- `aws imagebuilder list-image-pipeline-images` → 2 builds, both
  `AVAILABLE` (2026-08-08T08:23:31Z and 2026-08-08T16:49:58Z).
- `aws ec2 describe-images --owners self` → matching
  `pyvar-prod-worker-*` AMIs exist and are `available`
  (`ami-060d943f002425bf5`, `ami-0baf1ccb10f4856ae`) — confirms
  `ec2.MachineImage.lookup(name="pyvar-prod-worker-*", ...)` in
  `compute_stack.py` resolves successfully at synth time.
- Step 6's end-to-end trigger verification (both branches) is also
  confirmed, not just the static bootstrap:
  - **Bake branch**: `aws ssm get-parameter-history` on
    `/pyvar/prod/last-baked-ami-hash` shows exactly one write, at
    `2026-08-08T17:07:33Z` — right after the second AMI build above
    reached `AVAILABLE` at `16:49:58Z`. That timing match is the
    automated Synth-step logic (trigger bake → poll → `ssm
    put-parameter` on success) having actually run for real, not the
    stubbed dry-run this handoff was written against.
  - **Skip branch**: pulled the CodeBuild logs for the most recent
    `pyvar-dev-pipeline` Synth run (2026-08-31, build
    `PipelineBuildSynthCdkBuildP-5irl7k2WBhfr:77c41e85-eab1-451a-a380-cd13a13f9a77`)
    and found, verbatim: `AMI recipe hash:
    7cc34f9908d309e47e8f5f58449dbf7cc3ceb342881fcc068613527dcfe74e50`,
    `Last recorded AMI recipe hash:` (same value), then `No
    AMI-relevant changes since the last bake — skipping.` — matches the
    SSM value exactly, confirming the no-op path also works for real on
    an ordinary push, weeks after the initial bake.

Both control paths in `pipeline_stack.py`'s AMI-bake gate are proven
against real AWS, not just static analysis. No further action needed on
this handoff. `CLAUDE.md` §11's "REMAINING MANUAL STEP" note has been
updated to reflect this. The prompt below is left as-is as the historical
record of what was asked and why — it does not need to be re-run.

---

Self-contained prompt for a Claude Code session (or human operator) that has
**real AWS deploy credentials for the Fibtec prod account**. This session
does not — `aws sts get-caller-identity` returns `InvalidClientTokenId` here,
confirmed before writing this handoff rather than assumed. Everything below
was built and verified by static means only (syntax checks, `cdk synth`
against placeholder account `123456789012`, IAM/buildspec inspection of the
generated CloudFormation template, and a dry-run of the generated shell
logic against a stubbed `aws` CLI) — nothing in this branch has touched a
real AWS account.

Copy the prompt below into a session with real credentials.

---

## Prompt

```
Context: pyvar.com (fibtecltd/pyvar) needs its prod worker AMI bake
pipeline bootstrapped before the P9 launch sequence's "Day -7: Prod CDK
deploy via CodePipeline" step (docs/pyvar_release_plan.md). Two things
changed on branch claude/gracious-babbage-R7ywK (commits a6d37f7, 1cfa165,
cde41d1, c3b3e8a — pull this branch, or wait until it's merged to master):

1. pyvar-cdk/config.py: prod now sets worker_use_baked_ami=True.
   compute_stack.py resolves the worker AMI via
   ec2.MachineImage.lookup(name="pyvar-prod-worker-*", ...) at CDK synth
   time -- this FAILS the synth outright if no matching AMI exists yet.
2. pyvar-cdk/stacks/pipeline_stack.py: the shared Synth ShellStep now
   automatically triggers and waits for a fresh prod AMI bake (via
   aws imagebuilder start-image-pipeline-execution against
   pyvar-prod-worker-pipeline) whenever pyvar-cdk/stacks/ami_stack.py's
   content hash changes since the last recorded bake in SSM
   (/pyvar/prod/last-baked-ami-hash). It fails closed (exits 1, blocking
   the whole pipeline run) if the pipeline doesn't exist, the bake fails,
   or it times out after 30 minutes.

Neither of those can work yet because pyvar-prod-ami (the AmiStack that
actually defines pyvar-prod-worker-pipeline) has never been deployed --
it's a standalone stack in app.py, deliberately NOT part of the
self-mutating CDK Pipeline's per-push Dev/Prod stages (see
pipeline_stack.py's _ami_bake_commands docstring for why: the AMI has to
exist BEFORE cdk synth runs, but stacks inside the pipeline's own stages
only get their CloudFormation resources created AFTER synth -- a
circular dependency AmiStack sidesteps by staying out-of-band, same
category as bootstrapping pyvar-pipeline itself per app.py's own module
docstring).

Your task, in order:

1. Confirm you have real AWS credentials for the correct account:
   `aws sts get-caller-identity`. Do not proceed if this fails or if
   you're unsure it's the right (prod-capable) Fibtec account -- ask
   first rather than guessing the account ID. Do not hardcode or invent
   an account number anywhere; read it from this command's output.

2. Pull the branch (or confirm master already has these commits):
   `git fetch origin claude/gracious-babbage-R7ywK && git checkout
   claude/gracious-babbage-R7ywK` -- or, if already merged, just make
   sure your checkout of master includes commits a6d37f7 and 1cfa165
   (`git log --oneline | grep -E "a6d37f7|1cfa165"`).

3. cd pyvar-cdk && pip install -r requirements.txt

4. If this AWS account/region pair has never been CDK-bootstrapped,
   run `cdk bootstrap aws://ACCOUNT/eu-west-1 aws://ACCOUNT/us-east-1`
   first (substitute the real account ID from step 1). If pyvar-pipeline
   or any pyvar-dev-* stack already exists in this account, it's already
   bootstrapped -- skip this.

5. One-time bootstrap of the AMI pipeline resource itself:
     cdk deploy pyvar-prod-ami --context env=prod --context account=ACCOUNT
   Confirm it succeeds and creates (among other things) these resources
   -- check the CloudFormation console or `aws cloudformation
   describe-stack-resources --stack-name pyvar-prod-ami`:
     - AWS::ImageBuilder::ImagePipeline named pyvar-prod-worker-pipeline
     - AWS::ImageBuilder::LifecyclePolicy named pyvar-prod-worker-lifecycle
       (retains the 3 most recent AMIs, deletes older AMIs + their EBS
       snapshots -- this is new in commit a6d37f7, closing a separate gap
       where old AMI snapshots were never cleaned up)
     - The two IAM roles: ImageBuilderRole (build) and AmiLifecycleRole
       (cleanup)

6. Confirm the automated trigger actually works end-to-end against real
   AWS (this is the part that couldn't be verified without real
   credentials -- only its generated CloudFormation/IAM was checked
   statically). Two ways, in order of preference:

   a. PREFERRED -- let a real pipeline run exercise it: find the
      pipeline name (`aws codepipeline list-pipelines` -- likely
      pyvar-dev-pipeline; PipelineStack's pipeline_name is derived from
      whatever top-level --context env was used when pyvar-pipeline
      itself was deployed, which per app.py's own docstring defaults to
      dev even though it manages both Dev and Prod stages internally --
      don't assume, just check). Trigger a run (push a trivial commit,
      or `aws codepipeline start-pipeline-execution --name <name>`) and
      watch the Synth stage's CodeBuild logs (CodeBuild console, or
      `aws logs tail` on its log group) for these lines in order:
        "AMI recipe hash: ..."
        "AMI recipe changed since last bake -- triggering prod worker AMI bake"
        "Image build: arn:aws:imagebuilder:..."
        "Bake status (1/40): ..." (repeating until AVAILABLE)
      Since SSM /pyvar/prod/last-baked-ami-hash won't exist yet, THIS
      FIRST RUN should always take the bake branch (empty last-hash
      fails the "unchanged" check) -- that's expected, not a bug.
      Confirm it reaches AVAILABLE (not FAILED/CANCELLED/timeout) and
      that the pipeline run then proceeds past Synth successfully.
      Then trigger a SECOND run with no changes to ami_stack.py and
      confirm THAT run instead logs "No AMI-relevant changes since the
      last bake -- skipping." -- this proves both branches of the gate
      work for real, not just in the sandbox dry-run that produced this
      code.

   b. FALLBACK if you can't wait for/trigger a full pipeline run --
      manually reproduce just the AWS calls once to confirm IAM +
      resource wiring is correct:
        aws imagebuilder start-image-pipeline-execution \
          --image-pipeline-arn arn:aws:imagebuilder:eu-west-1:ACCOUNT:image-pipeline/pyvar-prod-worker-pipeline
        # poll until AVAILABLE:
        aws imagebuilder get-image --image-build-version-arn <ARN from above> \
          --query 'image.state.status' --output text
      This confirms the pipeline/recipe/infra-config themselves work,
      but does NOT confirm the CodeBuild Synth project's own IAM role
      can do the same thing -- option (a) is the real test of that.

7. Report back: what succeeded, what (if anything) failed, the AMI
   build ARN and final status, how long the bake actually took
   (informs whether the 30-minute timeout / "a day of lead time before
   Day -7" guidance in CLAUDE.md and the release plan is realistic), and
   whether the second (no-op) run correctly skipped. Do NOT proceed to
   any further prod deploy step beyond this bootstrap+verification
   without checking back first.
```

---

## Why this is a separate handoff instead of one continuous task

This session has no working AWS credentials (verified via `aws sts
get-caller-identity` before writing any of the automation, not assumed) and
this remote environment doesn't have a path to acquire real ones. Everything
upstream of this handoff (`worker_use_baked_ami=True` for prod, the Synth-step
trigger-and-wait logic, the Lifecycle Manager policy) was built and verified
by every means available without live AWS access: syntax checks, a full `cdk
synth` against a placeholder account confirming the generated CloudFormation
template and IAM policies are exactly as intended, and a dry-run of the
generated shell script against a stubbed `aws` CLI covering all four control
paths (skip / bake-succeeds / bake-fails / pipeline-missing) — which caught
and fixed a real bug (a `(... && exit 1)` subshell that silently failed to
abort the script) before it ever reached a real account. The one thing that
genuinely cannot be checked without real AWS access is whether the deployed
IAM role can actually call `imagebuilder:StartImagePipelineExecution` /
`GetImage` and whether a real Image Builder build actually completes — that
requires this handoff.

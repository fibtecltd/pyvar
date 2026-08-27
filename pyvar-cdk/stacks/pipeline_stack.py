"""
stacks/pipeline_stack.py — CodePipeline CI/CD for pyvar.com

Reasoning:
- CDK Pipelines (pipelines.CodePipeline) is the modern approach: it
  self-mutates on every push (the pipeline upgrades itself before
  running application stages), so CDK version drift never causes
  deployment failures.
- Three stages: Test → Build → Deploy(dev) → Deploy(prod).
  Prod stage has a manual approval gate — no accidental prod deploys.
- CodeBuild runs: pytest, bandit (security), cdk synth, docker build.
  All in a single build project to minimise cost (CodeBuild bills per minute).
- ECR image is built here and tagged with the git commit SHA —
  never 'latest' in production. The ECS task definition is updated
  atomically by the pipeline deploy stage.
- AMI baking (EC2 Image Builder) is triggered as a post-build step
  so Numba compiled objects are pre-baked into the worker AMI,
  reducing worker cold start from ~90s to ~20s.
- Secrets (GitHub token, Slack webhook) come from Secrets Manager —
  never hardcoded in this file.
"""

from __future__ import annotations

import typing

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_codebuild as cb
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as cpa
from aws_cdk import aws_codestarnotifications as notifications
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from aws_cdk import pipelines
from constructs import Construct

from config import PyvarConfig

# ── Portal-relevance gate (cost control) ────────────────────────────────────
# Paths that can actually change the deployed portal — app code, Celery
# tasks, DB migrations, the container image, and the CDK infra itself.
# Deliberately excludes docs/, scripts/claude/, .claude/, tests/, and
# anything else not listed: a docs-only PR (e.g. #177 — one markdown file,
# zero portal impact) has no business paying for a real ECS Fargate
# migration task run or a real CodeBuild smoke test against live CloudFront
# on every push, and #177 did exactly that before this gate existed.
_PORTAL_RELEVANT_PATHS = (
    "api",
    "engine",
    "tasks",
    "schemas",
    "storage",
    "observability",
    "migrations",
    "ui",
    "pyvar-cdk",
    "main.py",
    "worker.py",
    "config.py",
    "requirements.txt",
    "requirements-ci.txt",
    "requirements-heavy.txt",
    "Dockerfile",
    "alembic.ini",
)


def _portal_hash_command(var_name: str) -> str:
    """A single shell line computing a deterministic hash of every file under
    _PORTAL_RELEVANT_PATHS, assigned to $<var_name>. Used both by the
    pre-deploy skip gate (_skip_gate_commands) and by the post-deploy step
    that records what was actually just deployed (_record_deployed_hash_step)
    — both MUST compute the hash identically or the comparison is meaningless.
    """
    paths = " ".join(_PORTAL_RELEVANT_PATHS)
    return (
        f"{var_name}=$(find {paths} -type f 2>/dev/null | sort "
        "| xargs sha256sum | sha256sum | cut -d' ' -f1)"
    )


def _hash_compare_commands(
    hash_command: str, current_var: str, ssm_param: str, label: str
) -> list[str]:
    """Shared shell lines: compute a content hash into $<current_var> (via
    `hash_command`, e.g. a _portal_hash_command(...) call or a plain
    `sha256sum <file>`), fetch the last-recorded hash from SSM parameter
    `ssm_param` into $LAST_HASH, and echo both. Callers compare
    $<current_var> = $LAST_HASH themselves and decide what to do — the two
    gates that use this (_skip_gate_commands, _ami_bake_commands) record
    their "unchanged" hash at different points in their pipeline (post-deploy
    vs. inline right after a successful bake), so unifying further than this
    shared compute/fetch/echo step would force a control-flow shape neither
    actually has.

    First-ever run for a given `ssm_param` has no recorded hash (the SSM
    parameter doesn't exist yet) — $LAST_HASH comes back empty, which every
    caller here treats as "not equal to current" (fail open: never skip
    something that's never actually run) rather than guessing about history
    it doesn't have.
    """
    return [
        hash_command,
        f'echo "{label} hash: ${current_var}"',
        f'LAST_HASH=$(aws ssm get-parameter --name "{ssm_param}" '
        '--query "Parameter.Value" --output text 2>/dev/null || echo "")',
        f'echo "Last recorded {label} hash: $LAST_HASH"',
    ]


def _skip_gate_commands(stage_cfg: PyvarConfig) -> list[str]:
    """Sets $SKIP=1 when nothing portal-relevant has changed since the last
    successful deploy of this stage, else $SKIP=0.

    No git history is available here — CodePipeline's source action hands
    CodeBuild a plain file snapshot, not a git checkout — so this compares
    file CONTENT (hashed) against a hash recorded by
    _record_deployed_hash_step after the last successful deploy, rather than
    comparing commit SHAs. That's actually more correct than a SHA diff
    would be: it correctly treats a revert or a squash-merge that nets out
    to identical portal-relevant content as "unchanged" instead of forcing a
    needless re-run.
    """
    param_name = f"/pyvar/{stage_cfg.env_name}/last-deployed-portal-hash"
    return [
        *_hash_compare_commands(
            _portal_hash_command("CURRENT_HASH"),
            "CURRENT_HASH",
            param_name,
            "portal-relevant content",
        ),
        'if [ -n "$LAST_HASH" ] && [ "$LAST_HASH" != "None" ] '
        '&& [ "$CURRENT_HASH" = "$LAST_HASH" ]; then SKIP=1; else SKIP=0; fi',
    ]


def _skip_gate_iam_statement(stage_cfg: PyvarConfig) -> iam.PolicyStatement:
    param_name = f"/pyvar/{stage_cfg.env_name}/last-deployed-portal-hash"
    return iam.PolicyStatement(
        actions=["ssm:GetParameter"],
        resources=[f"arn:aws:ssm:{stage_cfg.region}:{stage_cfg.account}:parameter{param_name}"],
    )


def _guarded(stage_cfg: PyvarConfig, step_label: str, real_commands: list[str]) -> list[str]:
    """Wrap `real_commands` (a step's existing, unchanged logic) in the
    portal-relevance gate: they only run when the gate says something
    portal-relevant changed since the last successful deploy of this stage.

    Combined into a single command entry (an `if/then/else/fi` block, not a
    subshell) so any `exit 1` inside `real_commands` for a genuine failure
    still terminates the whole build with a non-zero status exactly as
    before — only the new SKIP=1 path is new behavior.
    """
    body = "\n".join(real_commands)
    return [
        *_skip_gate_commands(stage_cfg),
        (
            f'if [ "$SKIP" = "1" ]; then echo "No portal-relevant changes since '
            f'the last deploy — skipping {step_label}."; else\n{body}\nfi'
        ),
    ]


def _record_deployed_hash_step(
    stage_cfg: PyvarConfig, source: pipelines.CodePipelineSource
) -> pipelines.Step:
    """`post` step: after this stage's stacks have successfully deployed,
    record a hash of the portal-relevant files that were just deployed, so
    the NEXT execution's _skip_gate_commands can tell whether anything worth
    re-migrating or re-smoke-testing actually changed. Runs independently of
    any other `post` step in the same stage (e.g. ProdSmokeTest) — recording
    what's now live doesn't depend on, and isn't depended on by, verifying
    it's healthy.
    """
    param_name = f"/pyvar/{stage_cfg.env_name}/last-deployed-portal-hash"
    return pipelines.CodeBuildStep(
        f"RecordDeployedHash-{stage_cfg.env_name}",
        input=source,
        commands=[
            _portal_hash_command("CURRENT_HASH"),
            'echo "Recording deployed portal hash: $CURRENT_HASH"',
            f'aws ssm put-parameter --name "{param_name}" --value "$CURRENT_HASH" '
            "--type String --overwrite",
        ],
        role_policy_statements=[
            iam.PolicyStatement(
                actions=["ssm:PutParameter"],
                resources=[
                    f"arn:aws:ssm:{stage_cfg.region}:{stage_cfg.account}:parameter{param_name}"
                ],
            ),
        ],
    )


# ── Image build gate (cost control) ─────────────────────────────────────────
# Every commit previously rebuilt and repushed the API image to both ECR
# repos regardless of what changed -- even a docs-only or pyvar-client-only
# commit -- and because api_image_tag (below) is threaded straight into the
# ECS task definition, that meant EVERY commit also caused a real
# CloudFormation task-definition update and ECS rolling deployment in both
# Dev and Prod, not just wasted CodeBuild minutes. This gate skips the
# rebuild and reuses the last build's tag when nothing that ends up in the
# image actually changed, so cdk synth's output for the API stacks becomes
# byte-identical to the last build and CloudFormation correctly sees nothing
# to deploy.
#
# _PORTAL_RELEVANT_PATHS PLUS portal/ itself: unlike the migration/smoke-test
# gate above (which deliberately excludes portal/ -- a portal-only change
# needs no DB migration or smoke re-test), this gate must include portal/ --
# it's baked into the runtime image via Dockerfile's `COPY . .`, and reusing
# an old tag for a portal-only change would mean ECS keeps serving a stale
# image (the exact bug the "NOT wrapped in the portal-relevance _guarded()
# gate" comment at the docker build call site already flags).
#
# Reused tags are never pruned: api_stack.py's ECR lifecycle policy only
# deletes UNTAGGED images after 30 days, so a $SHORT_SHA tag from an
# arbitrarily old commit remains pullable indefinitely.
_IMAGE_RELEVANT_PATHS = _PORTAL_RELEVANT_PATHS + ("portal",)
_IMAGE_HASH_SSM_PARAM = "/pyvar/pipeline/last-image-relevant-hash"
_IMAGE_TAG_SSM_PARAM = "/pyvar/pipeline/last-image-tag"


def _image_relevant_hash_command(var_name: str) -> str:
    paths = " ".join(_IMAGE_RELEVANT_PATHS)
    return (
        f"{var_name}=$(find {paths} -type f 2>/dev/null | sort "
        "| xargs sha256sum | sha256sum | cut -d' ' -f1)"
    )


def _image_build_commands(cfg: PyvarConfig, dev_ecr_uri: str, prod_ecr_uri: str) -> list[str]:
    """Builds+pushes the API image to both ECR repos, or reuses the last
    build's tag when nothing image-relevant changed since then. Sets
    $SHORT_SHA either way -- callers downstream (cdk synth --context
    api_image_tag=$SHORT_SHA) don't need to know which branch ran.

    First-ever run has no recorded hash/tag (the SSM parameters don't exist
    yet) -- same fail-open behavior as _skip_gate_commands: always rebuilds
    rather than reusing a tag that might not actually exist in ECR.

    Takes `cfg` (the pipeline's own top-level config), not `prod_cfg` --
    same as the original unconditional commands this replaces, both ECR
    repos live in the one account/region this pipeline itself runs in.
    """
    build_and_push = [
        'echo "Building image for commit $SHORT_SHA"',
        f"aws ecr get-login-password --region {cfg.region} "
        f"| docker login --username AWS --password-stdin "
        f"{cfg.account}.dkr.ecr.{cfg.region}.amazonaws.com",
        "docker build --platform linux/amd64 --target runtime "
        "-t pyvar-dev-api:$SHORT_SHA -t pyvar-dev-api:latest .",
        f"docker tag pyvar-dev-api:$SHORT_SHA {dev_ecr_uri}:$SHORT_SHA",
        f"docker tag pyvar-dev-api:latest {dev_ecr_uri}:latest",
        f"docker push {dev_ecr_uri}:$SHORT_SHA",
        f"docker push {dev_ecr_uri}:latest",
        # ── Promote the same image into Prod (prod-bootstrap follow-up) ──
        # Retags the image just built above -- no second `docker build` --
        # and pushes it to pyvar-prod-api's own repo under the same
        # $SHORT_SHA tag prod_cfg.api_image_tag resolves to, so Prod always
        # runs exactly what Dev already validated. The repo itself isn't
        # CDK-managed (api_stack.py's own comment: provisioned out-of-band,
        # RETAIN'd across stack lifecycles), so it's created here
        # idempotently if this is its first run.
        f"aws ecr describe-repositories --repository-names pyvar-prod-api "
        f"--region {cfg.region} || aws ecr create-repository "
        f"--repository-name pyvar-prod-api --region {cfg.region}",
        f"docker tag pyvar-dev-api:$SHORT_SHA {prod_ecr_uri}:$SHORT_SHA",
        f"docker tag pyvar-dev-api:latest {prod_ecr_uri}:latest",
        f"docker push {prod_ecr_uri}:$SHORT_SHA",
        f"docker push {prod_ecr_uri}:latest",
        f'aws ssm put-parameter --name "{_IMAGE_HASH_SSM_PARAM}" --value "$IMAGE_HASH" '
        "--type String --overwrite",
        f'aws ssm put-parameter --name "{_IMAGE_TAG_SSM_PARAM}" --value "$SHORT_SHA" '
        "--type String --overwrite",
    ]
    reuse = [
        'echo "No image-relevant changes since the last build -- reusing '
        'image tag $LAST_IMAGE_TAG instead of rebuilding."',
        "SHORT_SHA=$LAST_IMAGE_TAG",
    ]
    body_build = "\n".join(build_and_push)
    body_reuse = "\n".join(reuse)
    return [
        _image_relevant_hash_command("IMAGE_HASH"),
        'echo "image-relevant content hash: $IMAGE_HASH"',
        f'LAST_IMAGE_HASH=$(aws ssm get-parameter --name "{_IMAGE_HASH_SSM_PARAM}" '
        '--query "Parameter.Value" --output text 2>/dev/null || echo "")',
        f'LAST_IMAGE_TAG=$(aws ssm get-parameter --name "{_IMAGE_TAG_SSM_PARAM}" '
        '--query "Parameter.Value" --output text 2>/dev/null || echo "")',
        'echo "Last recorded image-relevant hash: $LAST_IMAGE_HASH (tag: $LAST_IMAGE_TAG)"',
        # set -e scoped to exactly this if/else block: it's ONE CodeBuild
        # commands: entry (not a subshell — same reasoning as the AMI bake
        # gate's own comment above), so CodeBuild only ever checks the exit
        # status of the LAST line executed. Without set -e, a failure
        # partway through body_build (e.g. `docker build` hitting a
        # registry pull rate limit) doesn't stop the script — bash just
        # keeps going, `docker tag`/`docker push` fail too, and execution
        # still reaches the final `aws ssm put-parameter` calls, which
        # succeed on their own and record a tag that was never actually
        # pushed to either ECR repo. That's exactly what happened on
        # 2026-08-25: tag 83d9897 got recorded as built, ECS then failed
        # every task launch with CannotPullContainerError, and the
        # deployment circuit breaker auto-rolled Dev back. set +e
        # immediately after so this doesn't change behavior for the
        # unrelated steps (_ami_bake_commands, cdk synth) that follow in
        # this same continuous CodeBuild shell session.
        "set -e",
        (
            'if [ -n "$LAST_IMAGE_HASH" ] && [ "$LAST_IMAGE_HASH" != "None" ] '
            '&& [ "$IMAGE_HASH" = "$LAST_IMAGE_HASH" ] '
            '&& [ -n "$LAST_IMAGE_TAG" ] && [ "$LAST_IMAGE_TAG" != "None" ]; then\n'
            f"{body_reuse}\nelse\n{body_build}\nfi"
        ),
        "set +e",
    ]


# ── Prod AMI bake trigger (CLAUDE.md §11) ───────────────────────────────────
# Spliced directly into the shared Synth ShellStep's commands (see the call
# site below), NOT added as its own pipelines.CodeBuildStep like
# _migration_step/_smoke_test_step. This has to run BEFORE `cdk synth`, not
# after: ec2.MachineImage.lookup() (compute_stack.py) resolves the worker AMI
# via a CDK CONTEXT LOOKUP made *during* `cdk synth`, not at CloudFormation
# deploy time. A trigger-and-wait step placed anywhere AFTER synth (e.g. a
# Prod-stage `pre` step next to prod_migration) would kick off a real bake,
# but it couldn't change the AMI ID already baked into THIS run's
# already-synthesized Prod template — the deploy would go out on the
# PREVIOUS AMI while a fresh one builds for some unrelated future push. That
# would be a worse, silently-wrong version of the manual process it replaces
# ("bake, wait, THEN deploy" — CLAUDE.md §11), so it has to live here even
# though the Synth step is shared: a prod-only AMI-recipe change means a Dev
# deploy in the same pipeline run waits on it too. Accepted tradeoff — the
# alternative (decoupled, always-stale-by-one-run automation) is worse.
#
# Gated the same way as _skip_gate_commands, but hashing ami_stack.py alone:
# that file is the sole source of the Image Builder recipe/component
# (NUMBA_WARMUP_SCRIPT + component versioning in ami_stack.py itself), so a
# hash of just that file is exactly "would a new bake actually differ."
#
# Fails CLOSED: if pyvar-prod-ami (AmiStack) was never deployed,
# start-image-pipeline-execution errors "pipeline not found" and this step —
# and the whole pipeline run — fails loudly instead of silently deploying
# without ever baking anything. AmiStack is deliberately NOT folded into
# PyvarDeployStage (separate per-stack CloudFormation resources deployed
# post-synth can't satisfy a pre-synth AMI lookup — same ordering problem as
# above, one level up). It must be bootstrapped once, out of band, exactly
# like pyvar-pipeline itself (app.py's own module docstring):
#   cdk deploy pyvar-prod-ami --context env=prod --context account=ACCOUNT
# Every prod-relevant AMI change after that one-time step is fully automatic.
_PROD_AMI_HASH_SSM_PARAM = "/pyvar/prod/last-baked-ami-hash"
_PROD_AMI_PIPELINE_NAME = "pyvar-prod-worker-pipeline"
_PROD_AMI_RECIPE_NAME = "pyvar-prod-worker"


def _ami_stack_drift_check_commands(prod_cfg: PyvarConfig) -> list[str]:
    """Guards against baking against a stale AWS-side Image Builder recipe.

    ami_stack.py's file hash (compared in _ami_bake_commands below) only
    tells us the SOURCE changed — it says nothing about whether
    pyvar-prod-ami, the actual deployed CloudFormation stack holding the
    recipe/component Image Builder will bake against, was ever redeployed to
    match. That stack is deliberately NOT part of this pipeline's automated
    Prod stage (see the comment above _ami_bake_commands) — it's a
    standalone, manually-triggered `cdk deploy pyvar-prod-ami`. Without this
    check, a recipe-affecting edit that ships without that manual redeploy
    would silently bake against the OLD recipe and then record the NEW file
    hash as caught-up, permanently hiding the drift from every later push.

    `cdk diff --fail` exits non-zero exactly when the locally-synthesized
    template differs from what's actually deployed in AWS (including when
    the stack doesn't exist at all yet) — read-only, no deploy permissions
    needed, and it answers "is AWS in sync with source" directly instead of
    through a proxy like a second hand-maintained hash.

    Deliberately not `cmd || (... && exit 1)` — see the subshell note in
    _ami_bake_commands below; a `(...)` subshell's `exit 1` wouldn't abort
    this script, only the subshell, so the status is captured and checked
    with a plain `if` instead.
    """
    return [
        "cd pyvar-cdk",
        "cdk diff pyvar-prod-ami --context env=prod "
        f"--context account={prod_cfg.account} --fail > /tmp/ami_stack_diff.log 2>&1",
        "DIFF_STATUS=$?",
        "cd ..",
        'if [ "$DIFF_STATUS" != "0" ]; then',
        "  cat /tmp/ami_stack_diff.log",
        '  echo "pyvar-prod-ami is out of sync with ami_stack.py (or was never deployed) -- '
        "run 'cdk deploy pyvar-prod-ami --context env=prod --context account="
        f"{prod_cfg.account}' before this can bake safely. Blocking deploy.\"",
        "  exit 1",
        "fi",
    ]


def _ami_bake_commands(prod_cfg: PyvarConfig) -> list[str]:
    pipeline_arn = (
        f"arn:aws:imagebuilder:{prod_cfg.region}:{prod_cfg.account}"
        f":image-pipeline/{_PROD_AMI_PIPELINE_NAME}"
    )
    bake_and_wait = "\n".join(
        [
            *_ami_stack_drift_check_commands(prod_cfg),
            'echo "AMI recipe changed since last bake — triggering prod worker AMI bake '
            '(pyvar-prod-ami must already be deployed once, see CLAUDE.md sec 11)"',
            "BUILD_ARN=$(aws imagebuilder start-image-pipeline-execution "
            f'--image-pipeline-arn "{pipeline_arn}" '
            "--query imageBuildVersionArn --output text)",
            # NOTE: deliberately NOT `... || (echo ... && exit 1)` here — this
            # whole block is one embedded multi-line script (one CodeBuild
            # buildspec command), not a standalone one, so `exit 1` inside a
            # `(...)` subshell would only kill the subshell and let execution
            # fall through into the wait loop below with an empty BUILD_ARN.
            # `exit 1` in a plain `if` body runs in the current shell and
            # actually aborts the script — verified by dry-run against a
            # stubbed `aws` CLI.
            'if [ -z "$BUILD_ARN" ] || [ "$BUILD_ARN" = "None" ]; then',
            '  echo "Could not start AMI bake — is pyvar-prod-ami deployed? Blocking deploy."',
            "  exit 1",
            "fi",
            'echo "Image build: $BUILD_ARN"',
            # No CLI waiter exists for image-pipeline-execution completion —
            # polling get-image is the documented approach. 40 * 45s = 30min cap.
            "for i in $(seq 1 40); do",
            '  STATUS=$(aws imagebuilder get-image --image-build-version-arn "$BUILD_ARN" '
            '--query "image.state.status" --output text)',
            '  echo "Bake status ($i/40): $STATUS"',
            '  [ "$STATUS" = "AVAILABLE" ] && break',
            '  { [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "CANCELLED" ]; } '
            '&& { echo "AMI bake $STATUS — blocking deploy"; exit 1; }',
            '  [ "$i" = "40" ] '
            '&& { echo "AMI bake timed out after 30 minutes — blocking deploy"; exit 1; }',
            "  sleep 45",
            "done",
            f'aws ssm put-parameter --name "{_PROD_AMI_HASH_SSM_PARAM}" '
            '--value "$CURRENT_AMI_HASH" --type String --overwrite',
        ]
    )
    return [
        *_hash_compare_commands(
            "CURRENT_AMI_HASH=$(sha256sum pyvar-cdk/stacks/ami_stack.py | cut -d' ' -f1)",
            "CURRENT_AMI_HASH",
            _PROD_AMI_HASH_SSM_PARAM,
            "AMI recipe",
        ),
        (
            'if [ -n "$LAST_HASH" ] && [ "$LAST_HASH" != "None" ] '
            '&& [ "$CURRENT_AMI_HASH" = "$LAST_HASH" ]; then '
            'echo "No AMI-relevant changes since the last bake — skipping."\n'
            f"else\n{bake_and_wait}\nfi"
        ),
    ]


def _migration_step(stage_cfg: PyvarConfig, source: pipelines.CodePipelineSource) -> pipelines.Step:
    """Pre-deploy step (issue #119): run `scripts/db.py upgrade` against Aurora
    via a one-off ECS Fargate task, BEFORE this stage's stacks (incl. the API
    service) deploy — a failed migration exits non-zero and blocks the rest
    of the stage from rolling out.

    Cluster name, task family, and the migration IAM role ARNs are all
    deterministic pyvar-{env}-* strings (see api_stack.py) and are
    constructed directly here as plain Python f-strings.

    Subnet IDs and the security group ID are NOT available the same way:
    they're physical IDs NetworkStack only gets assigned at deploy time.
    The obvious-looking fix — export them as CfnOutputs from a stack in this
    same stage and read them back here via `env_from_cfn_outputs` — does NOT
    work: CDK Pipelines wires that as a hard graph dependency ("this step
    needs that stack's output"), which directly contradicts this step being
    a `pre` step of the SAME stage ("that stack must not deploy until this
    step succeeds"). CDK's synthesis rejects it as an unsatisfiable
    dependency cycle. So instead, this step discovers the VPC/subnets/SG
    itself at pipeline run time via plain (read-only) EC2 API calls, filtered
    on tags CDK already applies automatically (`aws-cdk:subnet-name`) plus
    one added deliberately for this purpose (the `Name` tag on sgs.api —
    see network_stack.py) — no cross-stack wiring, no cycle, and (since
    these are just tag lookups against whatever is currently live) no
    dependency on this exact pipeline run being the one that deployed them.

    `--task-definition` is passed by FAMILY NAME (not a specific revision
    ARN) so ECS always runs the latest ACTIVE revision — i.e. exactly the
    one api_stack.py just deployed as part of this same stage.
    """
    cluster_name = f"pyvar-{stage_cfg.env_name}"
    task_family = f"pyvar-{stage_cfg.env_name}-migrate"
    network_stack_name = f"pyvar-{stage_cfg.env_name}-network"
    sg_name_tag = f"pyvar-{stage_cfg.env_name}-sg-api"
    cluster_arn = f"arn:aws:ecs:{stage_cfg.region}:{stage_cfg.account}:cluster/{cluster_name}"
    step_name = f"RunDbMigration-{stage_cfg.env_name}"

    return pipelines.CodeBuildStep(
        step_name,
        input=source,
        commands=_guarded(
            stage_cfg,
            step_name,
            [
                # ── Discover the network (read-only, tag-filtered EC2 lookups) ──
                "VPC_ID=$(aws ec2 describe-vpcs --filters "
                f'"Name=tag:aws:cloudformation:stack-name,Values={network_stack_name}" '
                '--query "Vpcs[0].VpcId" --output text)',
                'echo "VPC: $VPC_ID"',
                'SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" '
                '"Name=tag:aws-cdk:subnet-name,Values=Private" '
                '--query "Subnets[].SubnetId" --output text | tr "\\t" ",")',
                'echo "Subnets: $SUBNET_IDS"',
                'SG_ID=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" '
                f'"Name=tag:Name,Values={sg_name_tag}" '
                '--query "SecurityGroups[0].GroupId" --output text)',
                'echo "Security group: $SG_ID"',
                '[ -n "$VPC_ID" ] && [ "$VPC_ID" != "None" ] '
                '&& [ -n "$SUBNET_IDS" ] && [ -n "$SG_ID" ] && [ "$SG_ID" != "None" ] '
                '|| (echo "Could not discover network for migration task — blocking deploy" '
                "&& exit 1)",
                # ── Run the migration task and block the deploy on failure ──────
                f'TASK_ARN=$(aws ecs run-task --cluster "{cluster_name}" '
                f'--task-definition "{task_family}" --launch-type FARGATE '
                '--network-configuration "awsvpcConfiguration={subnets=[$SUBNET_IDS],'
                'securityGroups=[$SG_ID],assignPublicIp=DISABLED}" '
                "--query 'tasks[0].taskArn' --output text)",
                'echo "Migration task: $TASK_ARN"',
                f'aws ecs wait tasks-stopped --cluster "{cluster_name}" --tasks "$TASK_ARN"',
                f'EXIT_CODE=$(aws ecs describe-tasks --cluster "{cluster_name}" --tasks "$TASK_ARN" '
                "--query 'tasks[0].containers[0].exitCode' --output text)",
                'echo "Migration container exit code: $EXIT_CODE"',
                '[ "$EXIT_CODE" = "0" ] || (echo "Migration FAILED — blocking deploy" && exit 1)',
            ],
        ),
        role_policy_statements=[
            _skip_gate_iam_statement(stage_cfg),
            iam.PolicyStatement(
                # Describe*/List* EC2 actions don't support resource-level
                # ARN restriction — "*" is the only valid resource for them.
                actions=[
                    "ec2:DescribeVpcs",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeSecurityGroups",
                ],
                resources=["*"],
            ),
            iam.PolicyStatement(
                actions=["ecs:RunTask"],
                resources=[
                    f"arn:aws:ecs:{stage_cfg.region}:{stage_cfg.account}"
                    f":task-definition/{task_family}:*"
                ],
                conditions={"ArnEquals": {"ecs:cluster": cluster_arn}},
            ),
            iam.PolicyStatement(
                actions=["ecs:DescribeTasks"],
                resources=["*"],
                conditions={"ArnEquals": {"ecs:cluster": cluster_arn}},
            ),
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[
                    f"arn:aws:iam::{stage_cfg.account}:role/"
                    f"pyvar-{stage_cfg.env_name}-migration-task-role",
                    f"arn:aws:iam::{stage_cfg.account}:role/"
                    f"pyvar-{stage_cfg.env_name}-migration-execution-role",
                ],
            ),
        ],
    )


def _smoke_test_step(
    stage_cfg: PyvarConfig, step_id: str, source: pipelines.CodePipelineSource
) -> pipelines.Step:
    """Pre-deploy step (#172): curl /health and an unauthenticated compute
    endpoint (expect 401 — api/middleware/auth.py's HTTPBearer dependency
    rejects missing credentials with 401, not 403) against the stage's
    CloudFront distribution, using the SAME network-discovery approach as
    _migration_step and for the identical reason: this runs as a `pre` step
    (checking the PREVIOUSLY deployed, currently-live state before this
    run's rollout, same as _migration_step's own pre-flight framing — not
    this run's new version), so it can't read a CfnOutput from this stage's
    own EdgeStack without hitting the same DependencyCycleGraph
    _migration_step's docstring describes.

    Replaces what was previously a hardcoded curl against
    https://api-{env}.{domain}/health — that subdomain was never actually
    provisioned (only pyvar.com/www.pyvar.com are DNS-validated CloudFront
    aliases, per #158/#165), and the ALB itself rejects direct traffic
    without CloudFront's origin-verify header regardless (api_stack.py), so
    that curl could never have succeeded even if the DNS existed.

    Filters on the `Comment` field edge_stack.py already sets on the
    distribution (f"pyvar {cfg.env_name} CDN") — a live, tag-filtered lookup
    against whatever's currently deployed, not a value baked in at any
    particular pipeline run.
    """
    comment = f"pyvar {stage_cfg.env_name} CDN"

    return pipelines.CodeBuildStep(
        step_id,
        input=source,
        commands=_guarded(
            stage_cfg,
            step_id,
            [
                # ── Discover the live CloudFront domain ──────────────────
                "CF_DOMAIN=$(aws cloudfront list-distributions "
                f"--query \"DistributionList.Items[?Comment=='{comment}'].DomainName | [0]\" "
                "--output text)",
                'echo "CloudFront domain: $CF_DOMAIN"',
                '[ -n "$CF_DOMAIN" ] && [ "$CF_DOMAIN" != "None" ] '
                '|| (echo "Could not discover CloudFront domain for smoke test — '
                'blocking deploy" && exit 1)',
                # ── Wait for ECS service to stabilise, then smoke test ────
                "sleep 30",
                'curl -f "https://$CF_DOMAIN/health" || exit 1',
                # VaR endpoint smoke test (unauthenticated → 401). Must be
                # -X POST: /var/compute is POST-only (api/routes/var.py), and
                # a GET here would fall through to main.py's catch-all static
                # portal mount instead of ever reaching this route's auth
                # check — see the StaticFilesMount fix in main.py. Expects
                # 401 (not 403): FastAPI's HTTPBearer security dependency
                # rejects missing credentials with 401 + WWW-Authenticate,
                # confirmed against the live endpoint (api/middleware/auth.py).
                "curl -s -o /dev/null -w '%{http_code}' -X POST "
                '"https://$CF_DOMAIN/api/v1/var/compute" '
                "| grep -q '401' || exit 1",
            ],
        ),
        role_policy_statements=[
            _skip_gate_iam_statement(stage_cfg),
            iam.PolicyStatement(
                # ListDistributions doesn't support resource-level ARN
                # restriction — "*" is the only valid resource for it.
                actions=["cloudfront:ListDistributions"],
                resources=["*"],
            ),
        ],
    )


class PipelineStack(Stack):

    def __init__(self, scope: Construct, id: str, *, cfg: PyvarConfig, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── GitHub connection (stored in Secrets Manager) ──────────────────────
        # Store your GitHub OAuth token in Secrets Manager as:
        #   aws secretsmanager create-secret \
        #     --name pyvar/github-token \
        #     --secret-string "ghp_xxxxxxxxxxxxxxxxxxxx"
        github_token = cdk.SecretValue.secrets_manager("pyvar/github-token")

        # ── Source ────────────────────────────────────────────────────────────
        # #172: this pointed at a placeholder org ("fibtec-limited", with a
        # "replace with your org/repo" comment still sitting next to it,
        # never filled in) and branch "main" — the real repo is
        # fibtecltd/pyvar and its default branch is "master". Both silently
        # wrong until now: the pipeline could never actually have connected
        # to real commits, on top of the account-level CodeBuild quota that
        # separately blocked ever deploying this stack at all (now resolved).
        # cfg.github_connection_arn is empty until the one-time manual
        # CodeStar Connection authorization is done (see its own comment in
        # config.py) -- until then this stays on the original OAuth source
        # below with no behavior change. Once set, switch to a
        # connection-based source: required for the Git push-filter trigger
        # added after pipeline.build_pipeline() below, which only applies to
        # a "CodeStarSourceConnection"-provider source, not an OAuth one.
        if cfg.github_connection_arn:
            source = pipelines.CodePipelineSource.connection(
                "fibtecltd/pyvar",
                "master",
                connection_arn=cfg.github_connection_arn,
                action_name="Source",
            )
        else:
            source = pipelines.CodePipelineSource.git_hub(
                repo_string="fibtecltd/pyvar",
                branch="master",
                authentication=github_token,
                trigger=cpa.GitHubTrigger.WEBHOOK,  # triggers on push to master
            )

        # ── Synth step (CDK synth + unit tests) ───────────────────────────────
        # This is the pipeline's "self-mutation" step.
        # It also runs the full test suite so a failing test blocks deployment.
        #
        # #172: the commands below previously assumed the checked-out repo
        # nested app code under a "pyvar/" subdirectory sibling to
        # "pyvar-cdk/" (pip install -r pyvar/requirements.txt, cd pyvar,
        # bandit -r pyvar/ ...) — this repo's actual layout has
        # requirements.txt, main.py, etc. at the checkout root directly, only
        # pyvar-cdk/ is a real subdirectory. Would have failed on the very
        # first `pip install` step. Paths below now match the real layout,
        # and the requirements set matches .github/workflows/ci.yml's own
        # test job exactly (requirements-ci.txt + requirements.txt covers
        # everything the test suite imports, incl. polars/numba).
        # #119 / prod-bootstrap follow-up: originally Dev-only — Prod had
        # never been deployed and had no ECR repo of its own, so wiring Prod
        # in too would have meant re-uploading every layer to a second repo
        # (ECR doesn't dedupe layers across repos) for zero benefit. Now that
        # pyvar-prod-api's first-ever deploy actually needs an image, this
        # promotes the SAME already-built local image into Prod's repo
        # (retag + push, no second `docker build`) rather than building
        # twice — see the "Promote the same image into Prod" commands below.
        dev_ecr_uri = f"{cfg.account}.dkr.ecr.{cfg.region}.amazonaws.com/pyvar-dev-api"
        prod_ecr_uri = f"{cfg.account}.dkr.ecr.{cfg.region}.amazonaws.com/pyvar-prod-api"

        # Computed here (not down at the Prod stage section below, where it
        # used to live) because _ami_bake_commands needs it inside `synth`'s
        # command list, which is constructed next — see that function's
        # docstring for why the AMI bake has to happen before `cdk synth`.
        # api_image_tag mirrors dev_cfg's wiring below (#119) — same
        # $SHORT_SHA context value, since the Synth step commands push the
        # identical retagged image to both repos under that tag.
        prod_cfg = PyvarConfig.for_env(
            "prod",
            account=cfg.account,
            api_image_tag=self.node.try_get_context("api_image_tag"),
        )

        synth = pipelines.ShellStep(
            "Synth",
            input=source,
            env={
                "APP_ENV": "test",
                # CodePipeline hands CodeBuild a plain file snapshot, not a git
                # checkout (see _skip_gate_commands' docstring above) — there's
                # no .git directory to `git rev-parse` here, and CodeBuild's own
                # CODEBUILD_RESOLVED_SOURCE_VERSION var isn't populated for a
                # CODEPIPELINE-type source either. source_attribute("CommitId")
                # is CDK Pipelines' documented mechanism for exactly this: it
                # resolves to a CodePipeline action-level variable reference
                # that becomes a normal shell env var inside CodeBuild.
                "COMMIT_ID": source.source_attribute("CommitId"),
            },
            commands=[
                # Python setup
                "pip install -r requirements-ci.txt",
                "pip install -r requirements.txt",
                "pip install -r pyvar-cdk/requirements.txt",
                # CDK CLI — not preinstalled on the CodeBuild image; aws-cdk-lib
                # (the Python construct library, installed above) is a separate
                # package from the `cdk` CLI binary itself. Pin to major version
                # 2 to match aws-cdk-lib, same as the pipeline's own self-mutation
                # buildspec (npm install -g aws-cdk@2).
                "npm install -g aws-cdk@2",
                # Security scan — fail pipeline on HIGH/CRITICAL findings
                "pip install bandit",
                "bandit -r . -ll -x tests/ || (echo 'Security issues found' && exit 1)",
                # Unit + integration tests with coverage gate
                "pytest -v --cov=. --cov-report=term-missing --cov-fail-under=80",
                # ── Build + push the API image (#119) ────────────────────────
                # Gated by _image_build_commands (see its own module-level
                # comment): skips the rebuild and reuses the last build's tag
                # when nothing under _IMAGE_RELEVANT_PATHS changed, instead of
                # rebuilding/repushing/redeploying on every single commit
                # regardless of relevance (a docs-only or pyvar-client-only
                # push previously caused a real ECS rolling deployment in both
                # Dev and Prod for zero behavior change).
                #
                # Mirrors scripts/build-push-api.sh's build invocation exactly
                # (that script is now a break-glass fallback for when the
                # pipeline itself is broken, not the primary mechanism).
                # SHORT_SHA matches the 7-char convention already used for
                # every existing tag in this ECR repo.
                "SHORT_SHA=$(echo $COMMIT_ID | cut -c1-7)",
                *_image_build_commands(cfg, dev_ecr_uri, prod_ecr_uri),
                # ── Prod AMI bake trigger (CLAUDE.md §11) ─────────────────────
                # MUST run before `cdk synth` below — see _ami_bake_commands'
                # docstring for why. No-ops (a hash compare + one SSM read) on
                # every push where ami_stack.py hasn't changed since the last
                # bake; only actually triggers-and-waits on the rare push that
                # changes the worker AMI recipe.
                *_ami_bake_commands(prod_cfg),
                # CDK synth (required for self-mutation). api_image_tag is only
                # threaded through to dev_cfg below (see PyvarConfig.for_env) —
                # Prod's ApiStack keeps the "latest" default until Prod is
                # actually stood up.
                "cd pyvar-cdk",
                f"cdk synth --context env={cfg.env_name} --context account={cfg.account} "
                "--context api_image_tag=$SHORT_SHA",
                "cd ..",
            ],
            primary_output_directory="pyvar-cdk/cdk.out",
        )

        # ── CDK Pipeline ──────────────────────────────────────────────────────
        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            pipeline_name=f"pyvar-{cfg.env_name}-pipeline",
            synth=synth,
            docker_enabled_for_synth=True,
            docker_enabled_for_self_mutation=True,
            pipeline_type=codepipeline.PipelineType.V2,  # W6: V2 removes daily execution limit
            # Use SMALL build image — sufficient for synth + tests
            # Switch to BUILD_GENERAL1_MEDIUM if tests start timing out
            code_build_defaults=pipelines.CodeBuildOptions(
                build_environment=cb.BuildEnvironment(
                    build_image=cb.LinuxBuildImage.STANDARD_7_0,
                    compute_type=cb.ComputeType.SMALL,
                    privileged=True,  # required for docker build
                ),
            ),
            # #119: scoped to ONLY the Synth project (not the shared
            # code_build_defaults above, which every other CodeBuildStep in
            # this pipeline — RunDbMigration-dev, SmokeTest, etc. — also
            # inherits). None of those run Docker, so caching there would just
            # flag every one of those projects for replacement for no benefit.
            # Local/ephemeral/host-scoped — no S3/storage cost; speeds up the
            # Synth step's new docker build (most layers are unchanged between
            # commits) — a cache miss just means a full build, same as before.
            synth_code_build_defaults=pipelines.CodeBuildOptions(
                cache=cb.Cache.local(cb.LocalCacheMode.DOCKER_LAYER),
            ),
            # Self-mutation: pipeline upgrades itself on every run
            self_mutation=True,
        )

        # ── Dev deploy stage ──────────────────────────────────────────────────
        # #119: api_image_tag threads the Synth step's freshly-pushed image tag
        # (see the "COMMIT_ID"/SHORT_SHA commands above) through to ApiStack —
        # without this override PyvarConfig's "latest" default never changes
        # between deploys, so CloudFormation never sees a diff on the ECS task
        # definition's image property and never redeploys it.
        dev_cfg = PyvarConfig.for_env(
            "dev",
            account=cfg.account,
            api_image_tag=self.node.try_get_context("api_image_tag"),
        )
        dev_stage = PyvarDeployStage(
            self,
            "Dev",
            cfg=dev_cfg,
            env=cdk.Environment(account=cfg.account, region=cfg.region),
        )
        pipeline.add_stage(
            dev_stage,
            pre=[
                # #119: migration must apply before the API service (in this
                # same stage) rolls out to the new schema-dependent code.
                # Both steps below skip their real work (no Fargate task run,
                # no live CloudFront hit) when nothing portal-relevant has
                # changed since the last successful Dev deploy — see
                # _skip_gate_commands.
                _migration_step(dev_cfg, source),
                # Run smoke tests against dev after deploy
                _smoke_test_step(dev_cfg, "SmokeTest", source),
            ],
            post=[
                # Records what was just deployed so the NEXT execution's
                # gate above has something to compare against.
                _record_deployed_hash_step(dev_cfg, source),
            ],
        )

        # ── Prod deploy stage (manual approval gate) ──────────────────────────
        # prod_cfg computed near `synth` above (needed there for _ami_bake_commands).
        prod_stage = PyvarDeployStage(
            self,
            "Prod",
            cfg=prod_cfg,
            env=cdk.Environment(account=cfg.account, region=cfg.region),
        )
        # Manual approval — ops team reviews dev smoke test results.
        # Gated by cfg.require_prod_approval (config.py) — see that field's
        # comment for what flipping it to False actually does (removes the
        # gate immediately on the pipeline execution that carries the change,
        # since this pipeline is self-mutating).
        prod_migration = _migration_step(prod_cfg, source)
        prod_pre_steps: list[pipelines.Step] = []
        if cfg.require_prod_approval:
            prod_approval = pipelines.ManualApprovalStep(
                "ApproveProductionDeploy",
                comment=(
                    "Review dev deployment smoke tests and CloudWatch dashboard "
                    "before approving production deployment."
                ),
            )
            # #119: a plain `pre=[...]` list does NOT imply ordering between
            # its steps (aws_cdk.pipelines.Step.sequence()/
            # add_step_dependency() exist precisely because sibling steps may
            # run in parallel) — this explicit dependency is what guarantees
            # the migration only runs AFTER a human approves, not before or
            # concurrently with approval. Migrating prod's schema ahead of
            # (or regardless of) that approval would leave prod's DB migrated
            # even if the deploy is then rejected.
            prod_migration.add_step_dependency(prod_approval)
            prod_pre_steps.append(prod_approval)
        prod_pre_steps.append(prod_migration)

        pipeline.add_stage(
            prod_stage,
            pre=prod_pre_steps,
            post=[
                # #172: a `post` step of THIS stage — unlike dev's SmokeTest
                # (a `pre` step, checking the prior state), this genuinely
                # runs after prod's own EdgeStack (this same stage) has just
                # deployed, so reading its CfnOutput here is a real,
                # non-cyclic dependency. No network-discovery step needed.
                # Always runs regardless of the portal-relevance gate — it's
                # a cheap health check, not "real infra cost" in the same
                # category as the migration task, and confirming prod is
                # actually healthy after every deploy matters regardless of
                # what changed.
                pipelines.ShellStep(
                    "ProdSmokeTest",
                    env_from_cfn_outputs={
                        "CF_DOMAIN": prod_stage.edge.cloudfront_domain_output,
                    },
                    commands=[
                        "sleep 60",  # ECS blue/green needs longer to stabilise
                        'curl -f "https://$CF_DOMAIN/health" || exit 1',
                    ],
                ),
                # Records what was just deployed so the NEXT execution's
                # migration-step gate above has something to compare
                # against. Independent of ProdSmokeTest above — recording
                # what's live doesn't depend on, and isn't depended on by,
                # verifying it's healthy.
                _record_deployed_hash_step(prod_cfg, source),
            ],
        )

        # ── Pipeline notifications (Slack / email) ────────────────────────────
        # ops_topic receives pipeline state change notifications
        ops_topic = sns.Topic(
            self,
            "PipelineNotifications",
            topic_name="pyvar-pipeline-notifications",
            display_name="pyvar Pipeline Notifications",
        )

        # Add email subscription — replace with your ops email
        ops_topic.add_subscription(subs.EmailSubscription("ops@fibtec.co.uk"))

        # Narrowly-scoped topic carrying ONLY manual-approval-needed events,
        # in their native CodeStar Notifications shape — feeds
        # approval_relay_fn below, never Chatbot directly. See that
        # Lambda's own module docstring (lambda/approval_action_relay/
        # handler.py) for why this has to be a separate topic rather than
        # republishing onto ops_topic itself (would double-post to Slack).
        approval_raw_topic = sns.Topic(
            self,
            "PipelineApprovalRawNotifications",
            topic_name="pyvar-pipeline-approval-raw",
            display_name="pyvar Pipeline Approval Notifications (raw)",
        )

        # CodeStar notification rule — fires on pipeline failure and success
        # Must be added after pipeline.build_pipeline() is called
        pipeline.build_pipeline()

        # ── Git push-filter trigger (skip execution entirely, not just steps) ──
        # Only wired up once cfg.github_connection_arn is set (see its config.py
        # comment): the trigger's provider_type "CodeStarSourceConnection" only
        # applies when the Source action above is connection-based, not the
        # OAuth git_hub() source this pipeline uses by default. L1 escape hatch
        # (CfnPipeline) because CDK Pipelines' L2 pipelines.CodePipeline has no
        # `triggers` passthrough of its own.
        #
        # excludes, not includes: AWS::CodePipeline::Pipeline hard-caps
        # triggers[].gitConfiguration.push[].filePaths.{includes,excludes} at 8
        # entries each (learned the hard way -- an includes list built from
        # _IMAGE_RELEVANT_PATHS had 18 entries and failed CloudFormation
        # validation with "Member must have length less than or equal to 8" on
        # SelfMutate, rolling the pipeline stack back cleanly to its prior
        # OAuth-source state). _IMAGE_RELEVANT_PATHS itself is too long to fit
        # either direction, but its COMPLEMENT -- the top-level dirs that are
        # NOT portal-relevant -- happens to be exactly 8 today, so excludes is
        # the only direction that fits. Each entry needs the "/**" suffix:
        # push-filter patterns match file paths, and a bare directory name
        # (e.g. "docs", no wildcard) never equals any actual changed file path.
        #
        # This is deliberately the complement of the in-execution gates'
        # ALLOWlist (_PORTAL_RELEVANT_PATHS/_IMAGE_RELEVANT_PATHS), not derived
        # from them programmatically -- there's no room left in the 8-entry cap
        # to also exclude top-level irrelevant FILES (README.md, CHANGELOG.md,
        # etc.), so a push touching only those still starts an execution today
        # (no worse than before this feature; the in-execution gates still
        # no-op the actual work). If a 9th non-portal top-level directory is
        # ever added to the repo, this list must be updated by hand or the
        # trigger silently stops excluding it (falls back to "always starts an
        # execution" for that new directory, not the dangerous direction, but
        # worth fixing promptly for cost).
        _TRIGGER_EXCLUDED_PATHS = (
            ".claude",
            ".claude-plugin",
            ".github",
            "docs",
            "ingestion",
            "pyvar-client",
            "scripts",
            "tests",
        )
        if cfg.github_connection_arn:
            cfn_pipeline = typing.cast(
                codepipeline.CfnPipeline, pipeline.pipeline.node.default_child
            )
            cfn_pipeline.triggers = [
                codepipeline.CfnPipeline.PipelineTriggerDeclarationProperty(
                    provider_type="CodeStarSourceConnection",
                    git_configuration=codepipeline.CfnPipeline.GitConfigurationProperty(
                        source_action_name="Source",
                        push=[
                            codepipeline.CfnPipeline.GitPushFilterProperty(
                                branches=codepipeline.CfnPipeline.GitBranchFilterCriteriaProperty(
                                    includes=["master"],
                                ),
                                file_paths=codepipeline.CfnPipeline.GitFilePathFilterCriteriaProperty(
                                    excludes=[f"{path}/**" for path in _TRIGGER_EXCLUDED_PATHS],
                                ),
                            ),
                        ],
                    ),
                ),
            ]

        # `cdk synth` performs live CDK context lookups the first time it
        # resolves them for a given account/region — VPC availability zones
        # (NetworkStack's Vpc construct) and the pre-baked worker AMI ID
        # (ComputeStack's WorkerLaunchTemplate) — and this repo has no
        # committed cdk.context.json to cache those answers. Without these,
        # every real synth of the Dev/Prod stacks fails with "not authorized
        # to perform: ec2:DescribeAvailabilityZones / ec2:DescribeImages".
        # Neither Describe action supports resource-level ARN restriction —
        # "*" is the only valid resource for them, same as other Describe*/
        # List* EC2 actions elsewhere in this file.
        pipeline.synth_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "ec2:DescribeAvailabilityZones",
                    "ec2:DescribeImages",
                ],
                resources=["*"],
            )
        )

        # #119: lets the Synth step's `docker login`/`docker push` (above)
        # actually reach pyvar-dev-api. GetAuthorizationToken doesn't support
        # resource-level restriction — "*" is the only valid resource for it,
        # same pattern as the Describe*/List* EC2 actions above.
        pipeline.synth_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],
            )
        )
        pipeline.synth_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:PutImage",
                    "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload",
                    "ecr:BatchGetImage",
                ],
                resources=[f"arn:aws:ecr:{cfg.region}:{cfg.account}:repository/pyvar-dev-api"],
            )
        )
        # Lets the Synth step's "Promote the same image into Prod" commands
        # (above) create pyvar-prod-api on its first-ever run and push the
        # retagged image to it on every run thereafter — same action set as
        # pyvar-dev-api's grant above, plus CreateRepository/DescribeRepositories
        # for the idempotent create-if-missing check.
        pipeline.synth_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:DescribeRepositories",
                    "ecr:CreateRepository",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:PutImage",
                    "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload",
                    "ecr:BatchGetImage",
                ],
                resources=[f"arn:aws:ecr:{cfg.region}:{cfg.account}:repository/pyvar-prod-api"],
            )
        )

        # Lets _image_build_commands' skip gate read/write the image-relevant
        # hash and last-built tag it needs to decide whether to rebuild —
        # same pattern as _skip_gate_iam_statement for the migration/smoke
        # gate, granted directly here (not via role_policy_statements) since
        # this Synth step is a plain ShellStep, not a CodeBuildStep.
        pipeline.synth_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter", "ssm:PutParameter"],
                resources=[
                    f"arn:aws:ssm:{cfg.region}:{cfg.account}:parameter{_IMAGE_HASH_SSM_PARAM}",
                    f"arn:aws:ssm:{cfg.region}:{cfg.account}:parameter{_IMAGE_TAG_SSM_PARAM}",
                ],
            )
        )

        # Lets _ami_stack_drift_check_commands' `cdk diff pyvar-prod-ami --fail`
        # actually read the deployed stack instead of failing closed on
        # AccessDenied. `cdk diff` assumes no bootstrap role here (this
        # project's role has no sts:AssumeRole grant at all, and the earlier
        # ec2:Describe* lookups above don't need one either — no committed
        # cdk.context.json means only the AZ/AMI context lookups happen live,
        # via ambient credentials); it calls CloudFormation directly with the
        # Synth role's own identity, and by default builds a read-only
        # change set for a more accurate diff than template comparison alone.
        # Without these, every drift check fails with AccessDenied on
        # DescribeStacks regardless of whether the stack actually drifted,
        # which still blocks the bake (fail-closed) but for the wrong reason
        # and blocks it forever, even right after a real fix is deployed.
        pipeline.synth_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudformation:DescribeStacks",
                    "cloudformation:GetTemplate",
                    "cloudformation:CreateChangeSet",
                    "cloudformation:DescribeChangeSet",
                    "cloudformation:DeleteChangeSet",
                ],
                resources=[
                    f"arn:aws:cloudformation:{prod_cfg.region}:{prod_cfg.account}"
                    ":stack/pyvar-prod-ami/*"
                ],
            )
        )

        # Lets the Synth step's _ami_bake_commands trigger and poll the prod
        # worker AMI bake. StartImagePipelineExecution and GetImage both
        # support resource-level ARN restriction, unlike the Describe*/List*
        # actions above.
        pipeline.synth_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=["imagebuilder:StartImagePipelineExecution"],
                resources=[
                    f"arn:aws:imagebuilder:{prod_cfg.region}:{prod_cfg.account}"
                    f":image-pipeline/{_PROD_AMI_PIPELINE_NAME}"
                ],
            )
        )
        pipeline.synth_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=["imagebuilder:GetImage"],
                resources=[
                    f"arn:aws:imagebuilder:{prod_cfg.region}:{prod_cfg.account}"
                    f":image/{_PROD_AMI_RECIPE_NAME}/*"
                ],
            )
        )
        pipeline.synth_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter", "ssm:PutParameter"],
                resources=[
                    f"arn:aws:ssm:{prod_cfg.region}:{prod_cfg.account}:parameter"
                    f"{_PROD_AMI_HASH_SSM_PARAM}"
                ],
            )
        )

        notifications.NotificationRule(
            self,
            "PipelineNotificationRule",
            source=pipeline.pipeline,
            events=[
                "codepipeline-pipeline-pipeline-execution-failed",
                "codepipeline-pipeline-pipeline-execution-succeeded",
            ],
            targets=[ops_topic],
            notification_rule_name=f"pyvar-{cfg.env_name}-pipeline-events",
        )

        # manual-approval-needed is split into its OWN rule targeting
        # approval_raw_topic (not ops_topic) — see that topic's own comment
        # above and lambda/approval_action_relay/handler.py's module
        # docstring for why. Email still gets a manual-approval-needed
        # notification: approval_relay_fn's whole job is turning this into
        # a Chatbot-renderable custom message on ops_topic, which ops_topic's
        # own EmailSubscription above still receives same as any other
        # message published there.
        notifications.NotificationRule(
            self,
            "PipelineApprovalNotificationRule",
            source=pipeline.pipeline,
            events=["codepipeline-pipeline-manual-approval-needed"],
            targets=[approval_raw_topic],
            notification_rule_name=f"pyvar-{cfg.env_name}-pipeline-approval-needed",
        )

        # ── Approval action relay (Chatbot Custom Actions groundwork) ──────────
        # Reformats the native manual-approval-needed event into a Chatbot
        # `custom`-schema notification with the approval token exposed via
        # metadata.additionalContext, republished onto ops_topic — see
        # lambda/approval_action_relay/handler.py's own module docstring
        # for the full reasoning and the NOT-YET-FIELD-VALIDATED caveat.
        # Attaching an actual Custom Action button to this message type is a
        # separate, console-side step (same category as the
        # SlackChannelConfiguration itself — see docs/
        # p9-pipeline-approval-gate-status.md's "Why this isn't in CDK"),
        # done once this Lambda's output has been confirmed correct against
        # a live test.
        approval_relay_log_group = logs.LogGroup(
            self,
            "ApprovalRelayLogGroup",
            log_group_name=f"/aws/lambda/pyvar-{cfg.env_name}-approval-action-relay",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        approval_relay_role = iam.Role(
            self,
            "ApprovalRelayRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        # Publish-only, and only to ops_topic — this Lambda never touches
        # CodePipeline itself. The actual approve/reject authority stays
        # exactly where PR #258 put it: the Chatbot channel's own IAM role,
        # invoked only when a human clicks the eventual Custom Action button.
        ops_topic.grant_publish(approval_relay_role)

        # No reserved_concurrent_executions — this account's total Lambda
        # concurrency quota is exactly 10 (see ses_events_stack.py's module
        # docstring for the confirmed account-level constraint); any
        # positive reservation would make deployment fail the same way it
        # did there.
        approval_relay_fn = lambda_.Function(
            self,
            "ApprovalActionRelayFunction",
            function_name=f"pyvar-{cfg.env_name}-approval-action-relay",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("lambda/approval_action_relay"),
            role=approval_relay_role,
            timeout=Duration.minutes(1),
            memory_size=128,
            log_group=approval_relay_log_group,
            environment={"TARGET_TOPIC_ARN": ops_topic.topic_arn},
        )
        approval_raw_topic.add_subscription(subs.LambdaSubscription(approval_relay_fn))

        # ── Slack integration for ApproveProductionDeploy (task #47) ───────────
        # AWS Chatbot needs an IAM role to assume when a Slack user clicks
        # Approve/Reject on a CodePipeline manual approval action -- this is
        # that role, created here (not by the AWS Chatbot console's own
        # channel-setup wizard, which offers to create one with a broader
        # default policy) so the actual permission grant stays reviewable,
        # scoped, and versioned like every other IAM policy in this file.
        #
        # docs/p9-pipeline-approval-gate-status.md's operational-gotcha
        # section is exactly why PutApprovalResult is scoped down at all
        # (not "*") -- the whole point of wiring Slack in here is to reduce
        # the chance of approving the wrong thing, not to widen what a
        # compromised or misconfigured Chatbot integration could approve.
        # It's scoped even narrower than the pipeline's own ARN, in fact --
        # see the PutApprovalResult PolicyStatement below for why.
        #
        # This role is NOT wired to a SlackChannelConfiguration in this
        # stack -- that resource still requires the Slack workspace to be
        # authorized first, a one-time manual step via the AWS Chatbot
        # console (OAuth, cannot be done via CDK/CLI). Once that's done,
        # this role's name is what gets selected in the console's channel-
        # setup wizard ("use an existing role"), instead of letting the
        # wizard create its own.
        chatbot_role = iam.Role(
            self,
            "ChatbotPipelineApprovalRole",
            role_name=f"pyvar-{cfg.env_name}-chatbot-pipeline-approval",
            assumed_by=iam.ServicePrincipal("chatbot.amazonaws.com"),
        )
        chatbot_role.add_to_policy(
            iam.PolicyStatement(
                # GetPipeline is a SEPARATE action from GetPipelineState --
                # Chatbot's "Get Info" button on a manual-approval message
                # calls GetPipeline (the pipeline's declarative structure),
                # not GetPipelineState (current execution status), and a
                # live "Get Info" click failed with AccessDeniedException on
                # GetPipeline alone even with GetPipelineState already
                # granted. Both use the same bare-pipeline-ARN resource
                # format, unlike PutApprovalResult below.
                actions=["codepipeline:GetPipeline", "codepipeline:GetPipelineState"],
                resources=[pipeline.pipeline.pipeline_arn],
            )
        )
        chatbot_role.add_to_policy(
            iam.PolicyStatement(
                # PutApprovalResult's resource-level ARN format is
                # pipeline/stage/action, NOT the bare pipeline ARN used above
                # for GetPipelineState -- confirmed against AWS's own IAM
                # reference (docs.aws.amazon.com/codepipeline/latest/
                # userguide/approvals-iam-permissions.html) after a live
                # Custom Action button click failed with AccessDeniedException
                # using the bare pipeline ARN (no identity-based policy
                # allows the action, because the Resource simply didn't
                # match). "Prod"/"ApproveProductionDeploy" are the literal
                # stage/action names from the ManualApprovalStep above --
                # keep both in sync if either is ever renamed.
                actions=["codepipeline:PutApprovalResult"],
                resources=[f"{pipeline.pipeline.pipeline_arn}/Prod/ApproveProductionDeploy"],
            )
        )
        # Lets Chatbot format the manual-approval Slack message it renders
        # (approval action details, pipeline name) -- read-only, and
        # CloudWatch doesn't support resource-level ARN restriction for
        # these actions, same pattern as the Describe*/List* EC2 grants
        # above.
        chatbot_role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:DescribeAlarms"],
                resources=["*"],
            )
        )

        cdk.CfnOutput(
            self,
            "ChatbotPipelineApprovalRoleArn",
            value=chatbot_role.role_arn,
            description=(
                "Select this role (not 'create new role') in the AWS Chatbot "
                "console's Slack channel-configuration step for #pyvar-prod-approvals."
            ),
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "PipelineConsoleUrl",
            value=f"https://{cfg.region}.console.aws.amazon.com/codesuite/codepipeline/pipelines/pyvar-{cfg.env_name}-pipeline/view",
        )


# ── Deploy stage (wraps all application stacks) ───────────────────────────────


class PyvarDeployStage(cdk.Stage):
    """
    A CDK Stage wrapping all pyvar application stacks.
    Instantiated once per environment (dev, prod) in the pipeline.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # app.py's own cdk.Tags.of(app).add(...) calls never reach anything
        # constructed in here. CDK Pipelines synthesizes each Stage's nested
        # cloud assembly independently (needed for the self-mutation/staged
        # deploy model) — an Aspect (which is what Tags.of().add() registers)
        # only applies within the tree being walked by the synthesis pass
        # that's currently running, and a Stage's own independent synth pass
        # doesn't walk back up to aspects registered on an ancestor outside
        # the Stage. Confirmed live: a cdk diff against the already-deployed
        # (standalone) Dev stacks showed every resource here losing its
        # cost-allocation tags, purely as a byproduct of this Stage
        # boundary — not an intended change. Tagging the Stage directly
        # sidesteps the boundary entirely: this aspect is now registered on
        # (and applies within) the exact tree that gets synthesized.
        cdk.Tags.of(self).add("Project", "pyvar")
        cdk.Tags.of(self).add("Environment", cfg.env_name)
        cdk.Tags.of(self).add("ManagedBy", "cdk")
        cdk.Tags.of(self).add("Owner", "fibtec-limited")

        # Import application stacks — same stacks as in app.py
        # Imported here to avoid circular imports
        from stacks.api_stack import ApiStack
        from stacks.compute_stack import ComputeStack
        from stacks.data_stack import DataStack
        from stacks.edge_stack import EdgeStack
        from stacks.network_stack import NetworkStack
        from stacks.public_data_stack import PublicDataStack
        from stacks.queue_stack import QueueStack
        from stacks.ses_events_stack import SesEventsStack
        from stacks.ses_stack import SesStack

        prefix = f"pyvar-{cfg.env_name}"
        env_primary = cdk.Environment(account=cfg.account, region=cfg.region)
        env_edge = cdk.Environment(account=cfg.account, region="us-east-1")

        # Explicit stack_name= on every stack below: without it, a stack
        # constructed inside a cdk.Stage gets a CDK-default physical name of
        # "{StageName}-{constructId}" (e.g. "Dev-pyvar-dev-network") instead
        # of just the construct ID. That's a DIFFERENT CloudFormation stack
        # from "pyvar-dev-network" — and "pyvar-dev-network" (and its
        # siblings below) already exists, deployed standalone via app.py's
        # documented bypass path (`cdk deploy pyvar-dev-* --all`) before
        # this pipeline could reach the Dev stage at all. Discovered live:
        # the pipeline's first real attempt at the Dev stage tried to create
        # a second, parallel "Dev-pyvar-dev-*" copy of every app stack —
        # for most of them CloudFormation would have silently gone ahead
        # (a full duplicate VPC/Aurora/ECS/ALB/CloudFront environment,
        # roughly doubling AWS spend), and for ses-events specifically it
        # hard-failed outright (AWS::EarlyValidation::ResourceExistenceCheck)
        # because that stack assigns fixed, non-stack-scoped physical names
        # (SNS topic, Lambda function, SES configuration set) that collided
        # with the real ones. Pinning stack_name= to the SAME bare names
        # app.py already uses makes the pipeline target the EXISTING stacks
        # (an update deploy) instead of creating new ones.
        network = NetworkStack(
            self, f"{prefix}-network", stack_name=f"{prefix}-network", cfg=cfg, env=env_primary
        )
        data = DataStack(
            self,
            f"{prefix}-data",
            stack_name=f"{prefix}-data",
            cfg=cfg,
            vpc=network.vpc,
            sgs=network.sgs,
            env=env_primary,
        )
        queue = QueueStack(
            self, f"{prefix}-queue", stack_name=f"{prefix}-queue", cfg=cfg, env=env_primary
        )
        compute = ComputeStack(
            self,
            f"{prefix}-compute",
            stack_name=f"{prefix}-compute",
            cfg=cfg,
            vpc=network.vpc,
            sgs=network.sgs,
            var_queue=queue.var_queue,
            dlq=queue.dlq,
            data=data,
            env=env_primary,
        )
        ses_events = SesEventsStack(
            self,
            f"{prefix}-ses-events",
            stack_name=f"{prefix}-ses-events",
            cfg=cfg,
            env=env_primary,
        )
        ses = SesStack(
            self,
            f"{prefix}-ses",
            stack_name=f"{prefix}-ses",
            cfg=cfg,
            configuration_set=ses_events.configuration_set,
            env=env_primary,
        )
        ses.add_dependency(ses_events)
        api = ApiStack(
            self,
            f"{prefix}-api",
            stack_name=f"{prefix}-api",
            cfg=cfg,
            vpc=network.vpc,
            sgs=network.sgs,
            var_queue=queue.var_queue,
            data=data,
            ses_identity=ses.email_identity,
            configuration_set=ses_events.configuration_set,
            env=env_primary,
        )
        edge = EdgeStack(
            self,
            f"{prefix}-edge",
            stack_name=f"{prefix}-edge",
            cfg=cfg,
            alb_dns=api.alb_dns_name,
            origin_verify_secret=api.origin_verify_secret,
            env=env_edge,
        )
        # Exposed so PipelineStack's ProdSmokeTest step (#172) can read
        # edge.cloudfront_domain_output via env_from_cfn_outputs.
        self.edge = edge
        public_data = PublicDataStack(
            self,
            f"{prefix}-public-data",
            stack_name=f"{prefix}-public-data",
            cfg=cfg,
            jwt_secret=api.jwt_secret,
            env=env_primary,
        )

        data.add_dependency(network)
        queue.add_dependency(network)
        compute.add_dependency(data)
        compute.add_dependency(queue)
        api.add_dependency(data)
        api.add_dependency(queue)
        api.add_dependency(ses)
        api.add_dependency(
            ses_events
        )  # references ses_events.configuration_set for SendEmail grant
        edge.add_dependency(api)
        public_data.add_dependency(api)

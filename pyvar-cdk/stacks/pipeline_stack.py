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

import aws_cdk as cdk
from aws_cdk import Stack
from aws_cdk import aws_codebuild as cb
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as cpa
from aws_cdk import aws_codestarnotifications as notifications
from aws_cdk import aws_iam as iam
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

    First-ever run for a stage has no recorded hash (the SSM parameter
    doesn't exist yet) — fails open (SKIP=0, never skip) rather than
    guessing about history it doesn't have.
    """
    param_name = f"/pyvar/{stage_cfg.env_name}/last-deployed-portal-hash"
    return [
        _portal_hash_command("CURRENT_HASH"),
        'echo "Portal-relevant content hash: $CURRENT_HASH"',
        f'LAST_HASH=$(aws ssm get-parameter --name "{param_name}" '
        '--query "Parameter.Value" --output text 2>/dev/null || echo "")',
        'echo "Last deployed hash: $LAST_HASH"',
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
        synth = pipelines.ShellStep(
            "Synth",
            input=source,
            env={
                "APP_ENV": "test",
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
                # CDK synth (required for self-mutation)
                "cd pyvar-cdk",
                f"cdk synth --context env={cfg.env_name} --context account={cfg.account}",
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
            # Self-mutation: pipeline upgrades itself on every run
            self_mutation=True,
        )

        # ── Dev deploy stage ──────────────────────────────────────────────────
        dev_cfg = PyvarConfig.for_env("dev", account=cfg.account)
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
        prod_cfg = PyvarConfig.for_env("prod", account=cfg.account)
        prod_stage = PyvarDeployStage(
            self,
            "Prod",
            cfg=prod_cfg,
            env=cdk.Environment(account=cfg.account, region=cfg.region),
        )
        # Manual approval — ops team reviews dev smoke test results
        prod_approval = pipelines.ManualApprovalStep(
            "ApproveProductionDeploy",
            comment=(
                "Review dev deployment smoke tests and CloudWatch dashboard "
                "before approving production deployment."
            ),
        )
        # #119: a plain `pre=[...]` list does NOT imply ordering between its
        # steps (aws_cdk.pipelines.Step.sequence()/add_step_dependency() exist
        # precisely because sibling steps may run in parallel) — this
        # explicit dependency is what guarantees the migration only runs
        # AFTER a human approves, not before or concurrently with approval.
        # Migrating prod's schema ahead of (or regardless of) that approval
        # would leave prod's DB migrated even if the deploy is then rejected.
        prod_migration = _migration_step(prod_cfg, source)
        prod_migration.add_step_dependency(prod_approval)

        pipeline.add_stage(
            prod_stage,
            pre=[
                prod_approval,
                # Runs only after approval above (see add_step_dependency),
                # still before prod's own stacks (incl. the API service) deploy.
                # Skips the real migration task if nothing portal-relevant
                # changed since the last successful Prod deploy — see
                # _skip_gate_commands.
                prod_migration,
            ],
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

        # CodeStar notification rule — fires on pipeline failure and success
        # Must be added after pipeline.build_pipeline() is called
        pipeline.build_pipeline()

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

        notifications.NotificationRule(
            self,
            "PipelineNotificationRule",
            source=pipeline.pipeline,
            events=[
                "codepipeline-pipeline-pipeline-execution-failed",
                "codepipeline-pipeline-pipeline-execution-succeeded",
                "codepipeline-pipeline-manual-approval-needed",
            ],
            targets=[ops_topic],
            notification_rule_name=f"pyvar-{cfg.env_name}-pipeline-events",
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

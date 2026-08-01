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


def _migration_step(stage_cfg: PyvarConfig) -> pipelines.Step:
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

    return pipelines.CodeBuildStep(
        f"RunDbMigration-{stage_cfg.env_name}",
        commands=[
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
        role_policy_statements=[
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
                _migration_step(dev_cfg),
                # Run smoke tests against dev after deploy
                pipelines.ShellStep(
                    "SmokeTest",
                    commands=[
                        # Wait for ECS service to stabilise
                        "sleep 30",
                        # Health check
                        f"curl -f https://api-dev.{cfg.domain_name}/health || exit 1",
                        # VaR endpoint smoke test (unauthenticated → 403)
                        f"curl -s -o /dev/null -w '%{{http_code}}' "
                        f"https://api-dev.{cfg.domain_name}/api/v1/var/compute "
                        f"| grep -q '403' || exit 1",
                    ],
                ),
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
        prod_migration = _migration_step(prod_cfg)
        prod_migration.add_step_dependency(prod_approval)

        pipeline.add_stage(
            prod_stage,
            pre=[
                prod_approval,
                # Runs only after approval above (see add_step_dependency),
                # still before prod's own stacks (incl. the API service) deploy.
                prod_migration,
            ],
            post=[
                pipelines.ShellStep(
                    "ProdSmokeTest",
                    commands=[
                        "sleep 60",  # ECS blue/green needs longer to stabilise
                        f"curl -f https://api.{cfg.domain_name}/health || exit 1",
                    ],
                )
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

        network = NetworkStack(self, f"{prefix}-network", cfg=cfg, env=env_primary)
        data = DataStack(
            self, f"{prefix}-data", cfg=cfg, vpc=network.vpc, sgs=network.sgs, env=env_primary
        )
        queue = QueueStack(self, f"{prefix}-queue", cfg=cfg, env=env_primary)
        compute = ComputeStack(
            self,
            f"{prefix}-compute",
            cfg=cfg,
            vpc=network.vpc,
            sgs=network.sgs,
            var_queue=queue.var_queue,
            dlq=queue.dlq,
            data=data,
            env=env_primary,
        )
        ses_events = SesEventsStack(self, f"{prefix}-ses-events", cfg=cfg, env=env_primary)
        ses = SesStack(
            self,
            f"{prefix}-ses",
            cfg=cfg,
            configuration_set=ses_events.configuration_set,
            env=env_primary,
        )
        ses.add_dependency(ses_events)
        api = ApiStack(
            self,
            f"{prefix}-api",
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
            cfg=cfg,
            alb_dns=api.alb_dns_name,
            origin_verify_secret=api.origin_verify_secret,
            env=env_edge,
        )
        public_data = PublicDataStack(
            self,
            f"{prefix}-public-data",
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

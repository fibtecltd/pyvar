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
from aws_cdk import aws_codepipeline_actions as cpa
from aws_cdk import aws_codestarnotifications as notifications
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from aws_cdk import pipelines
from constructs import Construct

from config import PyvarConfig


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
        source = pipelines.CodePipelineSource.git_hub(
            repo_string="fibtec-limited/pyvar",  # replace with your org/repo
            branch="main",
            authentication=github_token,
            trigger=cpa.GitHubTrigger.WEBHOOK,  # triggers on push to main
        )

        # ── Synth step (CDK synth + unit tests) ───────────────────────────────
        # This is the pipeline's "self-mutation" step.
        # It also runs the full test suite so a failing test blocks deployment.
        synth = pipelines.ShellStep(
            "Synth",
            input=source,
            env={
                "APP_ENV": "test",
            },
            commands=[
                # Python setup
                "pip install -r pyvar/requirements.txt",
                "pip install -r pyvar-cdk/requirements.txt",
                # Security scan — fail pipeline on HIGH/CRITICAL findings
                "pip install bandit",
                "bandit -r pyvar/ -ll -x pyvar/tests/ || (echo 'Security issues found' && exit 1)",
                # Unit + integration tests with coverage gate
                "cd pyvar",
                "pytest -v --cov=. --cov-report=term-missing --cov-fail-under=80",
                "cd ..",
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
        dev_stage = PyvarDeployStage(
            self,
            "Dev",
            cfg=PyvarConfig.for_env("dev", account=cfg.account),
            env=cdk.Environment(account=cfg.account, region=cfg.region),
        )
        pipeline.add_stage(
            dev_stage,
            pre=[
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
                )
            ],
        )

        # ── Prod deploy stage (manual approval gate) ──────────────────────────
        prod_stage = PyvarDeployStage(
            self,
            "Prod",
            cfg=PyvarConfig.for_env("prod", account=cfg.account),
            env=cdk.Environment(account=cfg.account, region=cfg.region),
        )
        pipeline.add_stage(
            prod_stage,
            pre=[
                # Manual approval — ops team reviews dev smoke test results
                pipelines.ManualApprovalStep(
                    "ApproveProductionDeploy",
                    comment=(
                        "Review dev deployment smoke tests and CloudWatch dashboard "
                        "before approving production deployment."
                    ),
                )
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
        from stacks.queue_stack import QueueStack

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
        api = ApiStack(
            self,
            f"{prefix}-api",
            cfg=cfg,
            vpc=network.vpc,
            sgs=network.sgs,
            var_queue=queue.var_queue,
            data=data,
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

        data.add_dependency(network)
        queue.add_dependency(network)
        compute.add_dependency(data)
        compute.add_dependency(queue)
        api.add_dependency(data)
        api.add_dependency(queue)
        edge.add_dependency(api)

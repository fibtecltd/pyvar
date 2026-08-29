"""
stacks/local_package_stack.py — manually-triggered "pyvar Local" build pipeline

Reasoning:
- P11 item 2 (docs/p11-pre-launch-hardening.md §2): builds the offline
  pyvar-local/ Docker image (see that directory's own README) and publishes
  it, on demand only, never on every push -- the opposite of pipeline_stack.py's
  self-mutating, auto-deploy-on-push pipeline, which is the wrong tool for
  "build this one specific artifact when someone asks for it."
- Manual-only triggering: CodeStarConnectionsSourceAction's own
  trigger_on_push=False disables the automatic webhook trigger a GitHub
  source normally registers. The pipeline only starts via an explicit
  `aws codepipeline start-pipeline-execution` call or the console's
  "Release change" button -- no EventBridge rule, no webhook, no schedule.
- Distribution channel is a GitHub Release asset, NOT a new S3/CloudFront
  origin: tests/test_data_residency.py enforces that customer/financial
  data stays in eu-west-1, and public_data_stack.py's own docstring records
  a prior design mistake (an earlier revision put small public JSON files
  behind a CloudFront->S3 origin in us-east-1 and failed that suite's
  check5/check6, no S3 origin may exist in the us-east-1 EdgeStack). A
  multi-hundred-MB local-package artifact is exactly the shape of thing
  that temptation recurs for -- publishing to GitHub instead sidesteps the
  question entirely: GitHub's infrastructure serves the bytes, not pyvar's
  AWS footprint, and it reuses the GitHub token secret pipeline_stack.py's
  own module docstring already confirms exists in Secrets Manager, rather
  than provisioning new AWS storage/CDN cost for large binaries.
- Two CodeBuild stages, not one: Build+Test (docker build, pre-warm the
  Numba cache the same way ami_stack.py's warmup script does for the AMI,
  then run tests/test_engine.py inside the built image as a release gate)
  and Publish (docker save -> scripts/publish_local_package_release.sh).
  Splitting them means a failed test never reaches the publish step, and
  each stage's CodeBuild logs stay focused on one concern.
- Notifications reuse pipeline_stack.py's existing "pyvar-pipeline-notifications"
  SNS topic by deterministic ARN (same avoid-a-cross-stack-cycle pattern
  queue_stack.py already uses for alerts_stack.py's topic) rather than a new
  topic -- once the Slack workspace is authorized via AWS Chatbot (the same
  pending one-time console step pipeline_stack.py's own chatbot_role
  comment already documents), this pipeline's success/failure notifications
  appear in the same Slack channel automatically, with no new IAM role or
  Chatbot wiring needed here.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_codebuild as cb
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as cpa
from aws_cdk import aws_codestarnotifications as notifications
from aws_cdk import aws_iam as iam
from aws_cdk import aws_sns as sns
from constructs import Construct

from config import PyvarConfig

# Same topic pipeline_stack.py's PipelineStack creates -- referenced by
# deterministic name/ARN here, not a live construct reference, to avoid a
# cross-stack dependency cycle (this stack doesn't otherwise need anything
# else from PipelineStack, and shouldn't have to depend on the whole thing
# just to publish a notification).
_PIPELINE_NOTIFICATIONS_TOPIC_NAME = "pyvar-pipeline-notifications"


class LocalPackageStack(Stack):
    """Manually-triggered pipeline: build, test, and publish pyvar Local."""

    def __init__(self, scope: Construct, id: str, *, cfg: PyvarConfig, **kwargs):
        super().__init__(scope, id, **kwargs)

        source_output = codepipeline.Artifact("Source")
        built_output = codepipeline.Artifact("Built")

        source_action = cpa.CodeStarConnectionsSourceAction(
            action_name="Source",
            owner="fibtecltd",
            repo="pyvar",
            branch="master",
            connection_arn=cfg.github_connection_arn,
            output=source_output,
            trigger_on_push=False,
        )

        # ── Build + test ─────────────────────────────────────────────────────
        # privileged=True is required for `docker build`/`docker save` inside
        # CodeBuild (Docker-in-Docker) -- same requirement as pipeline_stack.py's
        # own image-build step.
        build_project = cb.PipelineProject(
            self,
            "BuildProject",
            project_name=f"pyvar-{cfg.env_name}-local-package-build",
            description="pyvar Local: docker build + pre-warm Numba cache + run tests/test_engine.py",
            environment=cb.BuildEnvironment(
                build_image=cb.LinuxBuildImage.STANDARD_7_0,
                privileged=True,
                compute_type=cb.ComputeType.MEDIUM,
            ),
            timeout=Duration.minutes(30),
            build_spec=cb.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "build": {
                            "commands": [
                                # export, not a plain assignment: CodeBuild
                                # only carries a variable across the phase
                                # boundary into post_build below if it was
                                # exported in this phase.
                                "export IMAGE_TAG=pyvar-local:$CODEBUILD_RESOLVED_SOURCE_VERSION",
                                "docker build -f pyvar-local/Dockerfile -t $IMAGE_TAG .",
                                "echo $IMAGE_TAG > image_tag.txt",
                            ]
                        },
                        "post_build": {
                            "commands": [
                                # Release gate: a failing test here fails this
                                # CodeBuild phase, which fails the pipeline
                                # stage, which blocks the Publish stage below
                                # from ever running.
                                "docker run --rm --entrypoint pytest $IMAGE_TAG /app/tests/test_engine.py -v",
                                "docker save $IMAGE_TAG | gzip > pyvar-local.tar.gz",
                            ]
                        },
                    },
                    "artifacts": {"files": ["pyvar-local.tar.gz", "image_tag.txt"]},
                }
            ),
        )

        # ── Publish (GitHub Release asset) ──────────────────────────────────
        # GITHUB_TOKEN_VALUE is injected via the CodeBuildAction's own
        # environment_variables below (SECRETS_MANAGER type) -- CodeBuild
        # resolves pyvar/github-token to a plain env var at build time, never
        # written to this stack's own CloudFormation template.
        publish_project = cb.PipelineProject(
            self,
            "PublishProject",
            project_name=f"pyvar-{cfg.env_name}-local-package-publish",
            description="pyvar Local: publish the built image as a GitHub Release asset",
            environment=cb.BuildEnvironment(
                build_image=cb.LinuxBuildImage.STANDARD_7_0,
                compute_type=cb.ComputeType.SMALL,
            ),
            timeout=Duration.minutes(15),
            build_spec=cb.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "install": {"commands": ["apt-get update -y && apt-get install -y jq"]},
                        "build": {
                            "commands": [
                                # CODEBUILD_SRC_DIR is the primary input (Built:
                                # pyvar-local.tar.gz, image_tag.txt).
                                # CODEBUILD_SRC_DIR_Source is the extra input
                                # (the full repo checkout) -- the publish
                                # script lives there, not in Built.
                                "SHORT_SHA=${CODEBUILD_RESOLVED_SOURCE_VERSION:0:8}",
                                "export TAG=pyvar-local-v0-$SHORT_SHA",
                                "export ASSET_PATH=$CODEBUILD_SRC_DIR/pyvar-local.tar.gz",
                                "export GITHUB_TOKEN=$GITHUB_TOKEN_VALUE",
                                "bash $CODEBUILD_SRC_DIR_Source/scripts/publish_local_package_release.sh",
                            ]
                        },
                    },
                }
            ),
        )

        pipeline = codepipeline.Pipeline(
            self,
            "Pipeline",
            pipeline_name=f"pyvar-{cfg.env_name}-local-package",
            # V1 explicitly, not the default-if-unset: this pipeline has no
            # need for V2's Git-filter-trigger feature (that's the main
            # pipeline_stack.py pipeline's own reason for V2) -- it doesn't
            # trigger on Git events at all (trigger_on_push=False above).
            pipeline_type=codepipeline.PipelineType.V1,
            stages=[
                codepipeline.StageProps(stage_name="Source", actions=[source_action]),
                codepipeline.StageProps(
                    stage_name="BuildAndTest",
                    actions=[
                        cpa.CodeBuildAction(
                            action_name="BuildAndTest",
                            project=build_project,
                            input=source_output,
                            outputs=[built_output],
                        )
                    ],
                ),
                codepipeline.StageProps(
                    stage_name="Publish",
                    actions=[
                        cpa.CodeBuildAction(
                            action_name="PublishRelease",
                            project=publish_project,
                            input=built_output,
                            extra_inputs=[source_output],
                            environment_variables={
                                "GITHUB_TOKEN_VALUE": cb.BuildEnvironmentVariable(
                                    value="pyvar/github-token",
                                    type=cb.BuildEnvironmentVariableType.SECRETS_MANAGER,
                                ),
                            },
                        )
                    ],
                ),
            ],
        )

        # The publish CodeBuild project needs both artifacts (the built
        # tarball AND scripts/publish_local_package_release.sh from source)
        # -- input is the primary (extracted to CODEBUILD_SRC_DIR),
        # extra_inputs are extracted to CODEBUILD_SRC_DIR_<ArtifactName>.
        # Reading the script from the Built artifact's checkout would miss
        # it (only files [] from the build spec's artifacts block are
        # carried forward) -- it has to come from Source instead, which is
        # why extra_inputs=[source_output] above is not optional.
        publish_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{cfg.region}:{cfg.account}:secret:pyvar/github-token-*"
                ],
            )
        )

        # ── Notifications ────────────────────────────────────────────────────
        # Referenced by deterministic ARN -- see module docstring for why not
        # a live cross-stack construct reference.
        ops_topic = sns.Topic.from_topic_arn(
            self,
            "PipelineOpsTopic",
            f"arn:aws:sns:{self.region}:{self.account}:{_PIPELINE_NOTIFICATIONS_TOPIC_NAME}",
        )
        notifications.NotificationRule(
            self,
            "LocalPackagePipelineNotificationRule",
            source=pipeline,
            events=[
                "codepipeline-pipeline-pipeline-execution-failed",
                "codepipeline-pipeline-pipeline-execution-succeeded",
            ],
            targets=[ops_topic],
            notification_rule_name=f"pyvar-{cfg.env_name}-local-package-events",
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "PipelineName",
            value=pipeline.pipeline_name,
            description=(
                "Manual trigger: aws codepipeline start-pipeline-execution "
                f"--name {pipeline.pipeline_name} --region {cfg.region}"
            ),
        )

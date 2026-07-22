"""
stacks/public_data_stack.py — Shared public-data publisher: status.json + demo-result.json

Reasoning:
- P8 Task 1 (Option B: pre-computed, periodically-refreshed terminal demo) and
  P8 Task 2 (live status indicator) share one small piece of new
  infrastructure rather than two nearly-identical ones: a Lambda that writes
  small public JSON files into a bucket, served to the browser by the API
  itself (see api/routes/public_data.py) — NOT through a CloudFront/S3
  origin at the edge.
- This stack deploys to eu-west-1 (env_primary in app.py), alongside every
  other application stack — NOT us-east-1 alongside EdgeStack. An earlier
  version of this design put the bucket behind a CloudFront Origin Access
  Control origin and co-located this stack with EdgeStack in us-east-1; that
  violated tests/test_data_residency.py check5 (no S3 origin may exist in the
  us-east-1 EdgeStack — GDPR Art. 44 / CLAUDE.md §3.4, the edge is metadata/
  routing only) and check6 (only the cf-origin-verify routing token may
  replicate to us-east-1 — the JWT secret must not). Serving these files
  through the API (an ordinary eu-west-1 ALB response, exactly like every
  other endpoint) keeps this data on the EU side of that boundary end to end,
  and CloudFront's existing default_behavior already respects Cache-Control
  from the origin (edge_stack.py's own docstring) — no new CloudFront
  behavior or cache policy was needed after all.
- The bucket is a separate resource from data_stack.py's result bucket
  (private, retention-governed) rather than folded into it: this one holds
  only small, regenerable, non-sensitive JSON rewritten every cycle
  (removal_policy=DESTROY, auto_delete_objects=True) — a different lifecycle
  than data_stack.py's carefully-retained resources.
- api_stack.py grants its ECS task role read access to this bucket by
  DETERMINISTIC NAME (not a live construct reference) specifically to avoid
  a cycle: this stack depends on api_stack.py for jwt_secret, so api_stack.py
  cannot also depend on this stack's bucket construct. Both stacks compute
  the identical name from cfg.env_name + self.account.
- The Lambda calls the API through the public CloudFront domain — the exact
  same call a browser makes — rather than the ALB directly. Now that both
  stacks are eu-west-1, there is no cross-region reason to bypass CloudFront,
  and going through the public URL needs nothing beyond the JWT: no
  origin-verify header, no ALB DNS, no extra secret grant.
- reserved_concurrent_executions=1 prevents overlapping invocations if a
  demo-result refresh (which polls for up to 4.5 minutes to absorb a cold
  Spot worker scale-up) is still running when the next scheduled trigger
  fires.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

from config import PyvarConfig


class PublicDataStack(Stack):
    """Bucket + scheduled Lambda publisher for status.json / demo-result.json."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        jwt_secret: secretsmanager.Secret,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── Public data bucket (private; the API — not CloudFront — reads it) ──
        # Name MUST match api_stack.py's independently-computed public_data_bucket_name.
        self.bucket = s3.Bucket(
            self,
            "PublicDataBucket",
            bucket_name=f"pyvar-{cfg.env_name}-public-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # ── Lambda execution role ──────────────────────────────────────────────
        fn_role = iam.Role(
            self,
            "PublisherRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        self.bucket.grant_write(fn_role, "public/*")
        jwt_secret.grant_read(fn_role)
        fn_role.add_to_policy(
            iam.PolicyStatement(
                # DescribeAlarms is a Describe-class CloudWatch action and does
                # not support resource-level ARN scoping in IAM — "*" is the
                # only resource value AWS accepts here. Alarms live in this
                # same region (eu-west-1), so no cross-region client needed.
                actions=["cloudwatch:DescribeAlarms"],
                resources=["*"],
            )
        )

        # ── Lambda: publishes status.json + demo-result.json on a schedule ────
        log_group = logs.LogGroup(
            self,
            "PublisherLogGroup",
            log_group_name=f"/aws/lambda/pyvar-{cfg.env_name}-public-data-publisher",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        self.function = lambda_.Function(
            self,
            "PublisherFunction",
            function_name=f"pyvar-{cfg.env_name}-public-data-publisher",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("lambda/public_data_publisher"),
            role=fn_role,
            timeout=Duration.minutes(5),
            memory_size=256,
            reserved_concurrent_executions=1,
            log_group=log_group,
            environment={
                "ENV_NAME": cfg.env_name,
                "PUBLIC_BUCKET": self.bucket.bucket_name,
                "JWT_SECRET_ARN": jwt_secret.secret_arn,
            },
        )

        # ── Schedule: every 15 minutes ─────────────────────────────────────────
        # Deliberately not sub-minute: compute workers scale to zero
        # (worker_min_capacity=0, config.py), so a refresh can hit a cold Spot
        # ASG scale-up (~1-3 min). 15 minutes bounds that to at most 4 possible
        # scale-up events/hour rather than one every minute.
        events.Rule(
            self,
            "PublisherSchedule",
            schedule=events.Schedule.rate(Duration.minutes(15)),
            targets=[targets.LambdaFunction(self.function)],
        )

        # ── Outputs ─────────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "PublicDataBucketName", value=self.bucket.bucket_name)

"""
stacks/public_data_stack.py — Shared public-data publisher: status.json + demo-result.json

Reasoning:
- P8 Task 1 (Option B: pre-computed, periodically-refreshed terminal demo) and
  P8 Task 2 (live status indicator) share one small piece of new
  infrastructure rather than two nearly-identical ones: a Lambda that writes
  small public JSON files into a bucket, served to the browser only through
  CloudFront (see edge_stack.py's new /public/* behavior + OAC).
- The bucket itself is owned by edge_stack.py, NOT this stack, even though
  the Lambda that writes into it lives here. Origin Access Control requires a
  bucket policy referencing the CloudFront distribution's ID, and the
  distribution requires the bucket as an origin — a genuine mutual reference
  that only resolves within a single stack. This stack just receives the
  already-built bucket and grants its Lambda write access to it.
- This stack deploys to us-east-1 (env_edge in app.py), alongside EdgeStack,
  for the same reason. Every cross-region need this stack has (the JWT
  secret, the origin-verify secret, the CloudWatch alarms) is resolved by
  NAME/region-parameter instead of by direct construct reference — the same
  "resolve by name" pattern edge_stack.py already uses for
  origin_verify_secret, for the identical reason (CDK cross-region construct
  references don't compose cleanly here).
- The Lambda calls the ALB directly (HTTP:80 + X-Origin-Verify), not through
  CloudFront: going through CloudFront for a background job hitting a
  mutating (Cache-Control: no-store) endpoint would gain nothing, and this
  mirrors the exact bypass-prevention mechanism CloudFront itself already
  uses (see api_stack.py). The ALB lives in eu-west-1 — a normal cross-region
  HTTPS-egress call, no different from CloudFront itself calling the same ALB
  today. See lambda/public_data_publisher/handler.py for the full rationale.
- CloudWatch alarms (ApiLatencyP95Alarm, Api5xxAlarm, WorkerErrorAlarm) live
  in eu-west-1 (alerts_stack.py, wherever api.alb lives) — the Lambda's
  CloudWatch client is therefore explicitly pinned to cfg.region, regardless
  of which region the Lambda itself executes in.
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
    """Lambda publisher for status.json / demo-result.json, writing into EdgeStack's bucket."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        alb_dns_name: str,
        public_data_bucket: s3.Bucket,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── JWT + origin-verify secrets, resolved BY NAME (see module docstring
        #    — avoids a cross-region construct reference to api_stack.py, which
        #    lives in cfg.region, not this stack's us-east-1). Both secrets are
        #    replicated to us-east-1 (api_stack.py) so these names resolve here.
        jwt_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "ImportedJwtSecret", f"pyvar/{cfg.env_name}/jwt-secret"
        )
        origin_verify_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "ImportedOriginVerifySecret", f"pyvar/{cfg.env_name}/cf-origin-verify"
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
        public_data_bucket.grant_write(fn_role, "public/*")
        jwt_secret.grant_read(fn_role)
        origin_verify_secret.grant_read(fn_role)
        fn_role.add_to_policy(
            iam.PolicyStatement(
                # DescribeAlarms is a Describe-class CloudWatch action and does
                # not support resource-level ARN scoping in IAM — "*" is the
                # only resource value AWS accepts here.
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
                "PUBLIC_BUCKET": public_data_bucket.bucket_name,
                "ALB_DNS_NAME": alb_dns_name,
                "ALARMS_REGION": cfg.region,  # alarms live where the ALB lives, not here
                "JWT_SECRET_NAME": f"pyvar/{cfg.env_name}/jwt-secret",
                "ORIGIN_VERIFY_SECRET_NAME": f"pyvar/{cfg.env_name}/cf-origin-verify",
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

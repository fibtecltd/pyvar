"""
stacks/token_report_stack.py — daily JWT-issuance email report (per-env)

Reasoning:
- Modeled directly on public_data_stack.py: a small scheduled Lambda with no
  VPC attachment, calling this environment's own API over CloudFront. Takes
  jwt_secret as a live construct reference (like public_data_stack.py, not
  ses_events_stack.py's by-name import) — there's no dependency cycle here,
  so the simpler form is used.
- Deliberately per-environment, not shared: see
  lambda/token_report_publisher/handler.py's own module docstring for why
  dev and prod each send their own separate email rather than combining
  into one (this codebase has no existing cross-environment shared stack,
  and building the first one wasn't judged worth it for a daily count).
- ses_identity.grant_send_email is the exact grant api_stack.py already uses
  for the ECS task role — same identity, same permission, just a second
  principal (this Lambda's role) added to it.
- No reserved_concurrent_executions — same account-wide Lambda concurrency
  ceiling (10, all must stay UNRESERVED) documented in
  public_data_stack.py's own docstring applies here too; a single
  once-a-day invocation has no realistic overlap risk regardless.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_ses as ses
from constructs import Construct

from config import PyvarConfig

NOTIFICATION_RECIPIENT = "info@pyvar.com"


class TokenReportStack(Stack):
    """Scheduled Lambda: emails a daily JWT-issuance report to info@pyvar.com."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        jwt_secret: secretsmanager.Secret,
        ses_identity: ses.EmailIdentity,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── Lambda execution role ──────────────────────────────────────────────
        fn_role = iam.Role(
            self,
            "TokenReportRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        jwt_secret.grant_read(fn_role)
        ses_identity.grant_send_email(fn_role)

        # ── Lambda: fetches the report from the API and emails it ─────────────
        log_group = logs.LogGroup(
            self,
            "TokenReportLogGroup",
            log_group_name=f"/aws/lambda/pyvar-{cfg.env_name}-token-report-publisher",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        self.function = lambda_.Function(
            self,
            "TokenReportFunction",
            function_name=f"pyvar-{cfg.env_name}-token-report-publisher",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("lambda/token_report_publisher"),
            role=fn_role,
            timeout=Duration.seconds(30),
            memory_size=128,
            log_group=log_group,
            environment={
                "ENV_NAME": cfg.env_name,
                "JWT_SECRET_ARN": jwt_secret.secret_arn,
                "API_BASE_URL": cfg.api_base_url,
                "SES_DOMAIN": cfg.ses_domain_name,
                "NOTIFICATION_RECIPIENT": NOTIFICATION_RECIPIENT,
            },
        )

        # ── Schedule: once daily at 07:00 UTC ──────────────────────────────────
        events.Rule(
            self,
            "TokenReportSchedule",
            schedule=events.Schedule.cron(minute="0", hour="7"),
            targets=[targets.LambdaFunction(self.function)],
        )

"""
stacks/ses_events_stack.py — SES bounce/complaint -> SNS -> suppression Lambda

Reasoning:
- Dedicated SNS topic (pyvar-{env}-ses-events), NOT the shared
  pyvar-{env}-alerts topic (alerts_stack.py): that topic's own docstring is
  explicit — no PII, human/PagerDuty subscribers only, zero code-managed
  subscriptions. A bounce/complaint payload carries an actual recipient
  email address; that's exactly what the alerts topic was kept free of.
  The alerting *signal* still reaches the shared topic, via the CloudWatch
  metric this stack exports (see alerts_stack.py's new SesSuppressionAlarm)
  — the raw payload with the email address stays contained to this stack's
  own topic + the Lambda's CloudWatch Logs.
- jwt_secret is imported BY DETERMINISTIC NAME
  (Secret.from_secret_name_v2), not as a live constructor reference from
  api_stack — the exact same idiom compute_stack.py already uses for
  GithubTokenSecret. This is load-bearing: api_stack depends on ses_stack
  (for the EmailIdentity, to grant ses:SendEmail); if THIS stack also
  needed a live api_stack reference, and ses_stack needed a live reference
  to THIS stack (for the configuration set), that closes a cycle
  (api -> ses -> ses_events -> api). The deterministic-name import breaks
  it, so this stack has zero CDK dependency edge back to api_stack.
- The Lambda never touches Aurora/the VPC directly — it calls the API over
  the public CloudFront domain instead, the only established pattern for a
  Lambda in this codebase (lambda/public_data_publisher/handler.py).
- No manual SNS topic policy for SES here — UNLIKE alerts_stack.py's AWS
  Budgets grant. ConfigurationSet.add_event_destination(...,
  EventDestination.sns_topic(topic), ...) already grants ses.amazonaws.com
  sns:Publish on this topic itself (confirmed by synthesizing with no manual
  grant present: the resulting AWS::SNS::TopicPolicy, scoped by SourceArn to
  this exact configuration set, appears on its own). A hand-added
  sns.TopicPolicy construct alongside it doesn't compose with that — SNS
  topics accept exactly one resource policy, and two separate
  AWS::SNS::TopicPolicy CloudFormation resources targeting the same topic
  race to overwrite each other's Policy attribute on deploy, silently
  discarding whichever applied first. Budgets has no equivalent built-in
  grant (hence the manual policy there); this construct does.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_ses as ses
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from constructs import Construct

from config import PyvarConfig


class SesEventsStack(Stack):
    """SNS topic + SES configuration set + suppression Lambda."""

    def __init__(self, scope: Construct, id: str, *, cfg: PyvarConfig, **kwargs):
        super().__init__(scope, id, **kwargs)

        jwt_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "JwtSecretImported", f"pyvar/{cfg.env_name}/jwt-secret"
        )

        # ── SNS topic (dedicated -- see module docstring) ───────────────────────
        self.topic = sns.Topic(
            self,
            "SesEventsTopic",
            topic_name=f"pyvar-{cfg.env_name}-ses-events",
            display_name=f"pyvar {cfg.env_name} SES bounce/complaint events",
        )
        # No manual TopicPolicy here — see module docstring. The
        # ConfigurationSet's SNS event destination below grants
        # ses.amazonaws.com sns:Publish on this topic itself, precisely
        # scoped to this configuration set.

        # ── SES configuration set -> this topic, Bounce+Complaint only ─────────
        self.configuration_set = ses.ConfigurationSet(
            self,
            "SesEventsConfigSet",
            configuration_set_name=f"pyvar-{cfg.env_name}-events",
        )
        self.configuration_set.add_event_destination(
            "SnsDestination",
            destination=ses.EventDestination.sns_topic(self.topic),
            events=[ses.EmailSendingEvent.BOUNCE, ses.EmailSendingEvent.COMPLAINT],
        )

        # ── Lambda: parses the event, calls the API, emits a CloudWatch metric ──
        log_group = logs.LogGroup(
            self,
            "SuppressionLogGroup",
            log_group_name=f"/aws/lambda/pyvar-{cfg.env_name}-ses-suppression",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        fn_role = iam.Role(
            self,
            "SuppressionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        jwt_secret.grant_read(fn_role)
        fn_role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],  # PutMetricData does not support resource-level ARN scoping
                conditions={"StringEquals": {"cloudwatch:namespace": "pyvar"}},
            )
        )
        # No reserved_concurrent_executions -- this account's total Lambda
        # concurrency quota is exactly 10 (see public_data_stack.py's module
        # docstring for the confirmed account-level constraint); any positive
        # reservation would make deployment fail the same way it did there.
        self.function = lambda_.Function(
            self,
            "SuppressionFunction",
            function_name=f"pyvar-{cfg.env_name}-ses-suppression",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("lambda/ses_suppression_handler"),
            role=fn_role,
            timeout=Duration.minutes(1),
            memory_size=128,
            log_group=log_group,
            environment={
                "ENV_NAME": cfg.env_name,
                # secret_name, NOT secret_arn -- see handler.py's
                # JWT_SECRET_ID comment for why the ARN from a
                # name-based import is unusable at runtime here.
                "JWT_SECRET_ID": jwt_secret.secret_name,
                "API_BASE_URL": cfg.api_base_url,
            },
        )
        self.topic.add_subscription(subscriptions.LambdaSubscription(self.function))

        # Plain namespace/name metric -- no CFN token, same shape as
        # compute_stack.py's worker_error_metric -- so alerts_stack.py can
        # reference it as a normal live cross-stack construct attribute.
        self.suppression_metric = cloudwatch.Metric(
            namespace="pyvar",
            metric_name=f"ses-suppressions-{cfg.env_name}",
            statistic="Sum",
            period=Duration.minutes(5),
            label="SES bounce/complaint suppressions",
        )

        cdk.CfnOutput(self, "SesEventsTopicArn", value=self.topic.topic_arn)
        cdk.CfnOutput(
            self, "SesEventsConfigSetName", value=self.configuration_set.configuration_set_name
        )

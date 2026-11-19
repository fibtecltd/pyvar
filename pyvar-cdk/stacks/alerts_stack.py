"""
stacks/alerts_stack.py — Centralised alerting: SNS topic, CloudWatch alarms, cost budget

Reasoning:
- One SNS topic ("pyvar-{env}-alerts") is the single fan-out point for every
  operational and cost alert. CDK creates the topic ONLY — no subscriptions.
  Subscribers (email, Slack webhook, PagerDuty) are added manually post-deploy
  against the exported ARN, so the alerting fabric carries no per-person address
  or PII in source control and can grow to any number of endpoints without a
  code change or redeploy.
- Alarms live here (rather than scattered across the resource stacks) so on-call
  has one file to read for the alerting policy. The one exception is the SQS
  queue-age alarm: it is owned by queue_stack (P4) and stays there. Wiring it to
  THIS topic via a normal cross-stack reference would create a CloudFormation
  cycle — api depends on queue (queue ARN), this stack depends on api (ALB), so
  queue depending on this stack's topic closes the loop. queue_stack therefore
  references this topic by its deterministic ARN (no Fn::ImportValue, no cycle);
  see the "AlertsTopicImported" reference in queue_stack.py.
- The cost budget uses the L1 CfnBudget: aws_budgets ships no L2 construct in
  aws-cdk-lib (only CfnBudget / CfnBudgetsAction). Budgets natively supports an
  SNS subscriber, so the same topic receives cost alerts and no email address
  has to be hardcoded. Unlike CloudWatch alarms, Budgets needs an explicit SNS
  resource-policy grant to publish — added via the topic policy below.

Worker-error alarm:
- compute_stack now ships the EC2/Celery worker stdout/stderr to a CloudWatch
  log group (/pyvar/{env}/worker) via the CloudWatch agent, and owns an
  ERROR/CRITICAL metric filter on it, exposed as compute.worker_error_metric.
  The worker-error alarm below pages when that metric exceeds 5 in 5 minutes.
  (Earlier revisions could not create this alarm because the workers logged to
  journald only, with no CloudWatch log group to attach a metric filter to.)

No-sign-up trial lane alarms (docs/plan-trial-lane-throttle.md "Operations"):
- Nothing in AWS scrapes the API's Prometheus counters, so the lane writes one JSON log line per issued
  ticket, per refusal and per breaker change (api/middleware/trial.py::record_event and hourly_check), and the
  metric filters below count them by the JSON key `event`. TRIAL_LOG_EVENTS is the list of those names;
  tests/test_cdk_trial_lane.py fails if it drifts from the lane's own.
- The alarms: two consecutive empty hourly checks (the breaker's strikes, one step before it trips); more than
  50 issuance refusals in an hour; any network at its share cap; proof-of-work failures above 20% of ticket
  attempts (with at least 20 attempts, so one bad request cannot trip it); any breaker state change. The
  sixth, WAF blocks of the trial rate rules, is in edge_stack.py because it must live in us-east-1.
- The filters hang off the API container's log group (api.api_log_group). The metric names carry the
  environment, as the worker-error metric does, because dev and prod share one account and one namespace.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sns as sns
from constructs import Construct
from stacks.api_stack import ApiStack
from stacks.compute_stack import ComputeStack
from stacks.ses_events_stack import SesEventsStack

from config import PyvarConfig

# Monthly cost cap for the environment. Kept as a module constant so the budget
# figure is discoverable in one place rather than buried in the tree. Denominated
# in USD: AWS Budgets rejects other units in this account (billing currency USD).
#
# Raised 250 -> 400 (P7 Task 7 follow-up, docs/p7-cost-review.md) -> 1400
# (this revision, docs/p9-scenario-volume-cost-audit.md "Real invoice update"):
# the 400 figure was a dev-environment, near-zero-traffic, 17-day extrapolation --
# never cross-checked against a real bill. A real prod invoice has since confirmed
# actual monthly spend of $900-1000, more than double that estimate. 1400 gives
# ~40-55% headroom above the confirmed $900-1000 range so the 80%-actual alarm
# (below) sits above normal observed spend and doesn't fire on routine billing,
# while still catching a genuine cost blow-out early. Revisit once more than one
# real invoice cycle is available -- one data point is a start, not a trend.
MONTHLY_BUDGET_USD = 1400
# Both thresholds are PERCENTAGE-based (see notifications_with_subscribers below),
# so they rescale automatically with MONTHLY_BUDGET_USD -- no separate edit needed.
BUDGET_ACTUAL_THRESHOLD_PCT = 80  # notify when ACTUAL spend crosses 80% ($1,120)
BUDGET_FORECAST_THRESHOLD_PCT = 100  # notify when spend is FORECAST to exceed $1,400

# Log lines the no-sign-up trial lane writes (JSON key `event`) -> the suffix of the metric that counts them.
# Keep in step with api/middleware/trial.py: tests/test_cdk_trial_lane.py compares the two.
TRIAL_LOG_EVENTS = {
    "trial_issued": "issued",
    "trial_refused_pow": "refused-pow",
    "trial_refused_issuance": "refused-issuance",
    "trial_refused_asn": "refused-asn",
    "trial_breaker_strike": "breaker-strike",
    "trial_breaker_attack": "breaker-attack",
    "trial_breaker_pause": "breaker-pause",
}
TRIAL_ISSUANCE_REFUSALS_PER_HOUR = 50  # more than this in an hour raises the alarm
TRIAL_POW_FAILURE_PERCENT = 20  # more than this share of ticket attempts failing the proof of work
TRIAL_POW_FAILURE_MIN_ATTEMPTS = (
    20  # ...but only once there are at least this many attempts in the hour
)


class AlertsStack(Stack):
    """SNS alert topic, CloudWatch alarms, and a monthly AWS cost budget.

    Args:
        scope: CDK construct scope.
        id: Stack id.
        cfg: Per-environment pyvar configuration.
        api: The API stack, referenced for its Application Load Balancer
            (``api.alb``) so latency and 5xx alarms can target it.
        compute: The compute stack, referenced for its worker error metric
            (``compute.worker_error_metric``) so the worker-error alarm can
            target it.
        ses_events: The SES events stack, referenced for its suppression
            metric (``ses_events.suppression_metric``) so the SES
            bounce/complaint alarm can target it.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        api: ApiStack,
        compute: ComputeStack,
        ses_events: SesEventsStack,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── SNS alerts topic (no subscriptions created here) ────────────────────
        # Subscribers are added manually after deploy against the exported ARN.
        # The topic name is deterministic so queue_stack can reference it by ARN
        # (see module docstring) without forming a cross-stack dependency cycle.
        self.topic = sns.Topic(
            self,
            "AlertsTopic",
            topic_name=f"pyvar-{cfg.env_name}-alerts",
            display_name=f"pyvar {cfg.env_name} alerts",
        )

        alb_dimensions = {"LoadBalancer": api.alb.load_balancer_full_name}

        # ── (a) API latency alarm — ALB p95 TargetResponseTime > 5s ─────────────
        # Extended statistic p95 over 1-minute periods; alarm only when 3 of 3
        # consecutive periods breach, so a single slow minute does not page.
        latency_p95 = cloudwatch.Metric(
            namespace="AWS/ApplicationELB",
            metric_name="TargetResponseTime",
            dimensions_map=alb_dimensions,
            statistic="p95",
            period=Duration.minutes(1),
            label="ALB p95 target response time",
        )
        cloudwatch.Alarm(
            self,
            "ApiLatencyP95Alarm",
            alarm_name=f"pyvar-{cfg.env_name}-api-latency-p95",
            alarm_description=(
                "ALB p95 TargetResponseTime > 5s for 3 consecutive minutes — "
                "API is slow (worker/DB backpressure or cold Fargate tasks)"
            ),
            metric=latency_p95,
            threshold=5,  # seconds
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=3,
            datapoints_to_alarm=3,  # 3-of-3 => consecutive
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        ).add_alarm_action(cw_actions.SnsAction(self.topic))

        # ── (b) API 5xx error-rate alarm — > 10 target 5xx in 5 minutes ─────────
        errors_5xx = cloudwatch.Metric(
            namespace="AWS/ApplicationELB",
            metric_name="HTTPCode_Target_5XX_Count",
            dimensions_map=alb_dimensions,
            statistic="Sum",
            period=Duration.minutes(5),
            label="ALB target 5xx count (5m)",
        )
        cloudwatch.Alarm(
            self,
            "Api5xxAlarm",
            alarm_name=f"pyvar-{cfg.env_name}-api-5xx",
            alarm_description=(
                "More than 10 target 5xx responses in 5 minutes — API errors " "reaching clients"
            ),
            metric=errors_5xx,
            threshold=10,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        ).add_alarm_action(cw_actions.SnsAction(self.topic))

        # ── (c) Worker error alarm — > 5 ERROR/CRITICAL log lines in 5 minutes ──
        # The worker log group and its ERROR/CRITICAL metric filter are owned by
        # compute_stack (workers now ship logs to CloudWatch via the CloudWatch
        # agent). compute.worker_error_metric is a plain namespace/name metric —
        # no CloudFormation token — so referencing it here adds no cross-stack
        # import; app.py declares an explicit dependency for deploy ordering.
        cloudwatch.Alarm(
            self,
            "WorkerErrorAlarm",
            alarm_name=f"pyvar-{cfg.env_name}-worker-errors",
            alarm_description=(
                "More than 5 worker ERROR/CRITICAL log lines in 5 minutes — "
                "workers are failing to process jobs"
            ),
            metric=compute.worker_error_metric,
            threshold=5,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        ).add_alarm_action(cw_actions.SnsAction(self.topic))

        # ── (d) SES suppression alarm — any bounce/complaint, threshold 0 ───────
        # Mirrors queue_stack.py's DlqDepthAlarm pattern (threshold=0), not this
        # file's own worker-error alarm's threshold-5 burst pattern: at the
        # expected <50 emails/day volume, a single permanent bounce or
        # complaint is itself the signal worth surfacing, not a burst.
        cloudwatch.Alarm(
            self,
            "SesSuppressionAlarm",
            alarm_name=f"pyvar-{cfg.env_name}-ses-suppressions",
            alarm_description=(
                "One or more recipient addresses were just suppressed (permanent "
                "bounce or complaint) — SES's own suppression list is silent by "
                "default; this makes it visible."
            ),
            metric=ses_events.suppression_metric,
            threshold=0,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        ).add_alarm_action(cw_actions.SnsAction(self.topic))

        # ── (f) No-sign-up trial lane alarms (see the module docstring) ────────
        def trial_metric(event: str, period: Duration) -> cloudwatch.IMetric:
            """A metric counting the lane's log lines named `event`, in the API's log group."""
            metric_name = f"trial-{TRIAL_LOG_EVENTS[event]}-{cfg.env_name}"
            logs.MetricFilter(
                self,
                "TrialFilter" + "".join(part.title() for part in event.split("_")),
                log_group=api.api_log_group,
                filter_pattern=logs.FilterPattern.string_value("$.event", "=", event),
                metric_namespace="pyvar",
                metric_name=metric_name,
                metric_value="1",
                default_value=0,
            )
            return cloudwatch.Metric(
                namespace="pyvar", metric_name=metric_name, statistic="Sum", period=period
            )

        def trial_alarm(
            alarm_id: str,
            name: str,
            description: str,
            metric: cloudwatch.IMetric,
            threshold: float,
            *,
            evaluation_periods: int = 1,
            comparison: cloudwatch.ComparisonOperator = (
                cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
            ),
        ) -> None:
            cloudwatch.Alarm(
                self,
                alarm_id,
                alarm_name=f"pyvar-{cfg.env_name}-trial-{name}",
                alarm_description=description
                + " See docs/plan-trial-lane-throttle.md (Operations).",
                metric=metric,
                threshold=threshold,
                comparison_operator=comparison,
                evaluation_periods=evaluation_periods,
                datapoints_to_alarm=evaluation_periods,  # all of them: consecutive
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            ).add_alarm_action(cw_actions.SnsAction(self.topic))

        hour, five_minutes = Duration.hours(1), Duration.minutes(5)
        # One strike is written at each hourly check that finds the compute or issuance budget empty; the
        # breaker starts attack mode at three and pauses issuance at six, so two in a row is the early word.
        trial_alarm(
            "TrialEmptyBudgetAlarm",
            "budget-empty",
            "The trial lane's budget was empty at two consecutive hourly checks.",
            trial_metric("trial_breaker_strike", hour),
            1,
            evaluation_periods=2,
            comparison=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        )
        trial_alarm(
            "TrialIssuanceRefusalsAlarm",
            "issuance-refusals",
            f"More than {TRIAL_ISSUANCE_REFUSALS_PER_HOUR} ticket requests were refused for the issuance "
            "budget in an hour.",
            trial_metric("trial_refused_issuance", hour),
            TRIAL_ISSUANCE_REFUSALS_PER_HOUR,
        )
        trial_alarm(
            "TrialAsnCapAlarm",
            "asn-cap",
            "A network reached its share of the trial lane's hourly budget and was refused.",
            trial_metric("trial_refused_asn", five_minutes),
            0,
        )
        pow_failed = trial_metric("trial_refused_pow", hour)
        pow_issued = trial_metric("trial_issued", hour)
        trial_alarm(
            "TrialPowFailureRatioAlarm",
            "pow-failures",
            f"More than {TRIAL_POW_FAILURE_PERCENT}% of ticket attempts failed the proof of work "
            f"(counted from {TRIAL_POW_FAILURE_MIN_ATTEMPTS} attempts an hour).",
            cloudwatch.MathExpression(
                expression=(
                    f"IF(failed + issued >= {TRIAL_POW_FAILURE_MIN_ATTEMPTS}, "
                    "100 * failed / (failed + issued), 0)"
                ),
                using_metrics={"failed": pow_failed, "issued": pow_issued},
                label="Trial proof-of-work failures (% of attempts)",
                period=hour,
            ),
            TRIAL_POW_FAILURE_PERCENT,
        )
        trial_alarm(
            "TrialBreakerStateAlarm",
            "breaker-state",
            "The trial lane's breaker set attack mode or paused ticket issuance.",
            cloudwatch.MathExpression(
                expression="attack + pause",
                using_metrics={
                    "attack": trial_metric("trial_breaker_attack", five_minutes),
                    "pause": trial_metric("trial_breaker_pause", five_minutes),
                },
                label="Trial breaker state changes",
                period=five_minutes,
            ),
            0,
        )

        # ── (e) Queue-age alarm — owned by queue_stack, NOT recreated here ──────
        # The pyvar-{env}-queue-age alarm already exists (P4) in queue_stack and
        # is (as of this change) wired to THIS topic by deterministic ARN there,
        # avoiding the cross-stack dependency cycle described in the docstring.
        # Nothing to create in this stack for it.

        # ── SNS topic policy: allow Budgets (and account) to publish ────────────
        # CloudWatch alarm actions publish under the account's own identity, which
        # the account-owner statement below preserves (defining any explicit topic
        # policy replaces SNS's implicit owner-access default, so we restate it).
        # AWS Budgets publishes as the budgets.amazonaws.com service principal and
        # requires an explicit grant — without it CfnBudget creation fails.
        topic_policy = sns.TopicPolicy(
            self,
            "AlertsTopicPolicy",
            topics=[self.topic],
        )
        topic_policy.document.add_statements(
            iam.PolicyStatement(
                sid="AllowAccountOwnerPublish",
                effect=iam.Effect.ALLOW,
                principals=[iam.AccountRootPrincipal()],
                actions=["sns:Publish"],
                resources=[self.topic.topic_arn],
            ),
            iam.PolicyStatement(
                sid="AllowBudgetsPublish",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("budgets.amazonaws.com")],
                actions=["sns:Publish"],
                resources=[self.topic.topic_arn],
                conditions={"StringEquals": {"aws:SourceAccount": self.account}},
            ),
        )

        # ── AWS Budgets: $250/month, alert at 80% ACTUAL and 100% FORECASTED ────
        # Both notifications publish to the SNS topic (no hardcoded email — add
        # subscribers manually to the topic post-deploy). Budget creation validates
        # the topic policy, so it must run after the topic policy exists.
        sns_subscriber = budgets.CfnBudget.SubscriberProperty(
            subscription_type="SNS",
            address=self.topic.topic_arn,
        )
        cost_budget = budgets.CfnBudget(
            self,
            "MonthlyCostBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=f"pyvar-{cfg.env_name}-monthly",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=MONTHLY_BUDGET_USD,
                    unit="USD",
                ),
            ),
            notifications_with_subscribers=[
                # ACTUAL spend crosses 80% ($320)
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold=BUDGET_ACTUAL_THRESHOLD_PCT,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[sns_subscriber],
                ),
                # FORECAST to exceed 100% ($400) by month end
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="FORECASTED",
                        comparison_operator="GREATER_THAN",
                        threshold=BUDGET_FORECAST_THRESHOLD_PCT,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[sns_subscriber],
                ),
            ],
        )
        cost_budget.node.add_dependency(topic_policy)

        # ── Outputs ─────────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "AlertsTopicArn",
            value=self.topic.topic_arn,
            description=(
                "SNS topic for all pyvar alerts. No subscriptions are created by "
                "CDK — subscribe endpoints manually, e.g.: aws sns subscribe "
                "--topic-arn <this> --protocol email --notification-endpoint "
                "ops@example.com --region " + cfg.region
            ),
        )

"""
stacks/queue_stack.py — SQS FIFO queue, DLQ, and CloudWatch alarms

Reasoning:
- SQS FIFO replaces Redis as the Celery broker on AWS.
  Benefits: serverless (no broker instances), native CloudWatch metrics
  for auto-scaling, exactly-once delivery, and built-in DLQ support.
- FIFO queues guarantee ordering per MessageGroupId. Celery uses the
  task name as the group ID, so same-type tasks are ordered but
  different task types can execute in parallel.
- visibility_timeout must EXCEED the maximum simulation runtime.
  If a worker holds a message beyond the timeout, SQS makes it visible
  again and another worker picks it up (double execution). Set to 60s —
  well above the ~10s for a 100k-path Monte Carlo on c7i.xlarge.
- DLQ captures messages that fail 3+ times. CloudWatch alarm on the
  DLQ depth triggers a PagerDuty/SNS notification to the ops team.
- A separate high-priority queue (future) could be added for enterprise
  SLA tiers — route via Celery's `task_routes` config.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from config import PyvarConfig


class QueueStack(Stack):

    def __init__(self, scope: Construct, id: str, *, cfg: PyvarConfig, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── Dead Letter Queue ──────────────────────────────────────────────────
        self.dlq = sqs.Queue(
            self,
            "VarDlq",
            queue_name=f"pyvar-{cfg.env_name}-var-dlq.fifo",
            fifo=True,
            content_based_deduplication=True,
            retention_period=Duration.days(14),  # keep failed jobs for 2 weeks
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )

        # ── Main VaR job queue ────────────────────────────────────────────────
        self.var_queue = sqs.Queue(
            self,
            "VarQueue",
            queue_name=f"pyvar-{cfg.env_name}-var-jobs.fifo",
            fifo=True,
            content_based_deduplication=True,
            # CRITICAL: visibility timeout > max simulation runtime
            # If a worker takes longer than this, SQS re-queues the message
            visibility_timeout=Duration.seconds(cfg.queue_visibility_timeout_seconds),
            # Keep messages for 4 days — covers weekends + on-call response time
            retention_period=Duration.days(4),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=cfg.queue_dlq_max_receive_count,
                queue=self.dlq,
            ),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )

        # ── CloudWatch alarms ─────────────────────────────────────────────────
        # Ops SNS topic for alarm notifications
        ops_topic = sns.Topic(
            self,
            "OpsTopic",
            topic_name=f"pyvar-{cfg.env_name}-ops-alerts",
            display_name=f"pyvar {cfg.env_name} ops alerts",
        )

        # DLQ depth alarm — any message in DLQ = a job has failed permanently
        cloudwatch.Alarm(
            self,
            "DlqDepthAlarm",
            metric=self.dlq.metric_approximate_number_of_messages_visible(
                period=Duration.minutes(1),
            ),
            alarm_name=f"pyvar-{cfg.env_name}-dlq-depth",
            alarm_description="VaR job has exhausted retries and landed in DLQ",
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            threshold=0,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        ).add_alarm_action(cw_actions.SnsAction(ops_topic))

        # Queue age alarm — jobs sitting in queue for > 5 minutes = workers are stuck
        cloudwatch.Alarm(
            self,
            "QueueAgeAlarm",
            metric=self.var_queue.metric_approximate_age_of_oldest_message(
                period=Duration.minutes(1),
            ),
            alarm_name=f"pyvar-{cfg.env_name}-queue-age",
            alarm_description="Jobs waiting > 5 minutes — workers may be insufficient or stuck",
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            threshold=300,  # 5 minutes in seconds
            evaluation_periods=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        ).add_alarm_action(cw_actions.SnsAction(ops_topic))

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "VarQueueUrl", value=self.var_queue.queue_url)
        cdk.CfnOutput(self, "VarQueueArn", value=self.var_queue.queue_arn)
        cdk.CfnOutput(self, "DlqUrl", value=self.dlq.queue_url)

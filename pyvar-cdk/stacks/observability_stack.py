"""
stacks/observability_stack.py — CloudWatch operational dashboard (pyvar-{env}-overview)

Reasoning:
- A single at-a-glance dashboard for on-call: traffic, errors, latency, queue
  backlog, worker fleet size, cache efficiency, and cost. Alarms (alerts_stack)
  page; this dashboard is where you look once paged, or during a review.
- Coupling is deliberately loose. A dashboard is display-only and must never
  block a change to the resource it observes, so widgets reference metrics by
  their (namespace, dimension) — using the resources' deterministic physical
  names from cfg — rather than importing every stack. The ONE exception is the
  ALB: its physical "full name" carries an AWS-generated suffix
  (app/pyvar-{env}-alb/<hash>) that cannot be reconstructed as a static string,
  so we take the api stack and read api.alb.load_balancer_full_name. That is the
  same cross-stack reference alb_waf_stack and alerts_stack already use.

Gaps (reported, not fabricated):
- Widget 6 (job counts) reads custom CloudWatch metrics pyvar/JobCount and
  pyvar/JobErrors, now emitted from the Celery task path (tasks/var_task.py) via
  boto3 put_metric_data. This is the INTERIM job-observability measure per Path B
  — CloudWatch stands in so P6 does not ship with zero observability. It is NOT
  the final architecture: the proper Grafana Cloud / Amazon Managed Prometheus
  pipeline is a dedicated task before P9 launch. (Earlier this widget was a
  placeholder because no code published these metrics.)
- Widget 8 (monthly cost to date) is specified as Cost Explorer -> Lambda ->
  CloudWatch: a scheduled Lambda calling ce:GetCostAndUsage and publishing a
  custom metric the dashboard reads. That Lambda (code, role with ce:*, an
  EventBridge schedule, a log group) is a non-trivial addition out of scope for
  this dashboard task, so widget 8 is a text placeholder describing the intended
  pipeline as a follow-up. (Native AWS/Billing EstimatedCharges is not used: it
  is account-wide, us-east-1 only, and not scoped to this project.)
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from constructs import Construct
from stacks.api_stack import ApiStack

from config import PyvarConfig


class ObservabilityStack(Stack):
    """CloudWatch dashboard summarising API, queue, worker, and cache health.

    Args:
        scope: CDK construct scope.
        id: Stack id.
        cfg: Per-environment pyvar configuration.
        api: The API stack, referenced for its ALB (``api.alb``) — the only
            resource whose CloudWatch dimension value (load-balancer full name)
            cannot be derived from cfg as a static string.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        api: ApiStack,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        period_5m = Duration.minutes(5)
        alb_full_name = api.alb.load_balancer_full_name
        alb_dims = {"LoadBalancer": alb_full_name}
        # Deterministic physical names (see module docstring — loose coupling).
        queue_name = f"pyvar-{cfg.env_name}-var-jobs.fifo"
        asg_name = f"pyvar-{cfg.env_name}-workers"
        cache_cluster_id = f"pyvar-{cfg.env_name}"

        # ── (1) API request rate ────────────────────────────────────────────────
        request_rate = cloudwatch.Metric(
            namespace="AWS/ApplicationELB",
            metric_name="RequestCount",
            dimensions_map=alb_dims,
            statistic="Sum",
            period=period_5m,
        )
        w_requests = cloudwatch.GraphWidget(
            title="API request rate (ALB RequestCount, 5m)",
            left=[request_rate],
            width=12,
            height=6,
            region=self.region,
        )

        # ── (2) API error rate — target 5xx ──────────────────────────────────────
        errors_5xx = cloudwatch.Metric(
            namespace="AWS/ApplicationELB",
            metric_name="HTTPCode_Target_5XX_Count",
            dimensions_map=alb_dims,
            statistic="Sum",
            period=period_5m,
        )
        w_errors = cloudwatch.GraphWidget(
            title="API error rate (ALB target 5xx, 5m)",
            left=[errors_5xx],
            width=12,
            height=6,
            region=self.region,
        )

        # ── (3) API p95 latency ──────────────────────────────────────────────────
        latency_p95 = cloudwatch.Metric(
            namespace="AWS/ApplicationELB",
            metric_name="TargetResponseTime",
            dimensions_map=alb_dims,
            statistic="p95",
            period=period_5m,
            label="p95 target response time (s)",
        )
        w_latency = cloudwatch.GraphWidget(
            title="API p95 latency (ALB TargetResponseTime)",
            left=[latency_p95],
            width=12,
            height=6,
            region=self.region,
        )

        # ── (4) SQS queue depth ──────────────────────────────────────────────────
        queue_depth = cloudwatch.Metric(
            namespace="AWS/SQS",
            metric_name="ApproximateNumberOfMessagesVisible",
            dimensions_map={"QueueName": queue_name},
            statistic="Maximum",
            period=period_5m,
        )
        w_queue = cloudwatch.GraphWidget(
            title="SQS queue depth (visible messages)",
            left=[queue_depth],
            width=12,
            height=6,
            region=self.region,
        )

        # ── (5) Worker ASG in-service instance count ─────────────────────────────
        asg_instances = cloudwatch.Metric(
            namespace="AWS/AutoScaling",
            metric_name="GroupInServiceInstances",
            dimensions_map={"AutoScalingGroupName": asg_name},
            statistic="Maximum",
            period=period_5m,
        )
        w_workers = cloudwatch.GraphWidget(
            title="Worker ASG in-service instances",
            left=[asg_instances],
            width=12,
            height=6,
            region=self.region,
        )

        # ── (6) Job counts — INTERIM CloudWatch metrics (Path B) ─────────────────
        # tasks/var_task.py emits pyvar/JobCount (every completion) and
        # pyvar/JobErrors (on exception), dimensioned by TaskName. This is the
        # INTERIM job-observability measure per Path B — NOT the final architecture.
        # The proper Grafana Cloud / Amazon Managed Prometheus pipeline (per the
        # release plan, "dashboards ready before launch — not retrofitted") is a
        # dedicated task before P9 launch. TaskName is pinned to the VaR task's
        # registered Celery name (renaming it would also break API dispatch, so it
        # is stable). Future refinements, kept out to stay simple: a SEARCH
        # expression to aggregate across task types, and a computed
        # (JobCount-JobErrors)/JobCount success-rate percentage.
        job_task_name = "pyvar.tasks.compute_var"  # == compute_var_task registered name
        job_count = cloudwatch.Metric(
            namespace="pyvar",
            metric_name="JobCount",
            dimensions_map={"TaskName": job_task_name},
            statistic="Sum",
            period=period_5m,
        )
        job_errors = cloudwatch.Metric(
            namespace="pyvar",
            metric_name="JobErrors",
            dimensions_map={"TaskName": job_task_name},
            statistic="Sum",
            period=period_5m,
        )
        w_jobs = cloudwatch.GraphWidget(
            title="Job counts — JobCount / JobErrors (interim, Path B)",
            left=[job_count, job_errors],
            width=12,
            height=6,
            region=self.region,
        )

        # ── (7) ElastiCache hits / misses ────────────────────────────────────────
        # Serverless Redis publishes under AWS/ElastiCache with dimension clusterId.
        cache_hits = cloudwatch.Metric(
            namespace="AWS/ElastiCache",
            metric_name="CacheHits",
            dimensions_map={"clusterId": cache_cluster_id},
            statistic="Sum",
            period=period_5m,
        )
        cache_misses = cloudwatch.Metric(
            namespace="AWS/ElastiCache",
            metric_name="CacheMisses",
            dimensions_map={"clusterId": cache_cluster_id},
            statistic="Sum",
            period=period_5m,
        )
        w_cache = cloudwatch.GraphWidget(
            title="ElastiCache hits / misses (if published)",
            left=[cache_hits, cache_misses],
            width=12,
            height=6,
            region=self.region,
        )

        # ── (8) Monthly cost to date — GAP / follow-up ───────────────────────────
        # Cost Explorer -> Lambda -> CloudWatch pipeline is out of scope here.
        w_cost = cloudwatch.TextWidget(
            markdown=(
                "### Monthly cost to date — FOLLOW-UP\n"
                "Intended source: a scheduled **Lambda** calling Cost Explorer "
                "(`ce:GetCostAndUsage`) and publishing a `pyvar/MonthlyCostToDate` "
                "custom metric that this widget graphs.\n\n"
                "Not built in this task (Lambda + `ce:*` role + EventBridge schedule "
                "+ log group is a non-trivial addition). Tracked as a follow-up. "
                "The `pyvar-{env}-monthly` AWS Budget already alerts on 80%/100% "
                "spend via SNS in the meantime.".replace("{env}", cfg.env_name)
            ),
            width=12,
            height=6,
        )

        # ── Assemble dashboard ───────────────────────────────────────────────────
        self.dashboard = cloudwatch.Dashboard(
            self,
            "Dashboard",
            dashboard_name=f"pyvar-{cfg.env_name}-overview",
        )
        self.dashboard.add_widgets(w_requests, w_errors)
        self.dashboard.add_widgets(w_latency, w_queue)
        self.dashboard.add_widgets(w_workers, w_cache)
        self.dashboard.add_widgets(w_jobs, w_cost)

        # ── Outputs ──────────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "DashboardName",
            value=self.dashboard.dashboard_name,
        )
        cdk.CfnOutput(
            self,
            "DashboardUrl",
            value=(
                f"https://{self.region}.console.aws.amazon.com/cloudwatch/home"
                f"?region={self.region}#dashboards:name={self.dashboard.dashboard_name}"
            ),
        )

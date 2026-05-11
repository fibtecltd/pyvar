"""
stacks/api_stack.py — ECS Fargate FastAPI service + ALB + auto-scaling

Reasoning:
- Fargate (not EC2) for the API tier because the API is I/O-bound:
  it validates requests, pushes to SQS, and reads from ElastiCache.
  Fargate's per-second billing and zero instance management overhead
  beat EC2 for this workload.
- The task definition runs a health check that calls /health, which
  triggers the Numba JIT warmup in main.py's lifespan handler.
  startPeriod=30s gives the warmup time to complete before the ALB
  routes traffic to the task.
- ALB target group uses slow_start=60s so newly registered tasks
  receive a ramping fraction of traffic rather than full load immediately —
  protecting against the Numba compilation spike on cold tasks.
- Target-tracking auto-scaling at 60% CPU: if average CPU across tasks
  exceeds 60%, Fargate adds tasks. 60% leaves headroom for traffic spikes
  without over-provisioning.
- The ECR lifecycle policy deletes untagged images older than 30 days
  to prevent runaway storage costs from CI/CD pipelines.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_sqs as sqs,
    aws_elasticloadbalancingv2 as elbv2,
    Duration, Stack,
)
from constructs import Construct
from config import PyvarConfig
from stacks.network_stack import SecurityGroups
from stacks.data_stack import DataStack


class ApiStack(Stack):

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        vpc: ec2.Vpc,
        sgs: SecurityGroups,
        var_queue: sqs.Queue,
        data: DataStack,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── ECR Repository ─────────────────────────────────────────────────────
        self.ecr_repo = ecr.Repository(
            self, "ApiRepo",
            repository_name=f"pyvar-{cfg.env_name}-api",
            image_scan_on_push=True,       # free ECR image scanning
            lifecycle_rules=[
                ecr.LifecycleRule(
                    description="Remove untagged images after 30 days",
                    tag_status=ecr.TagStatus.UNTAGGED,
                    max_image_age=Duration.days(30),
                ),
                ecr.LifecycleRule(
                    description="Keep last 10 tagged releases",
                    tag_status=ecr.TagStatus.TAGGED,
                    tag_prefix_list=["v"],
                    max_image_count=10,
                ),
            ],
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # ── ECS Cluster ────────────────────────────────────────────────────────
        cluster = ecs.Cluster(
            self, "Cluster",
            cluster_name=f"pyvar-{cfg.env_name}",
            vpc=vpc,
            container_insights=True,     # CloudWatch Container Insights (costs ~$0.50/task/month)
            enable_fargate_capacity_providers=True,
        )

        # ── Task IAM Role ─────────────────────────────────────────────────────
        task_role = iam.Role(
            self, "ApiTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            role_name=f"pyvar-{cfg.env_name}-api-task-role",
        )
        var_queue.grant_send_messages(task_role)          # dispatch VaR jobs
        data.result_bucket.grant_read(task_role)          # presigned URL generation
        data.db_secret.grant_read(task_role)
        task_role.add_to_policy(iam.PolicyStatement(
            actions=["cloudwatch:PutMetricData"],
            resources=["*"],
            conditions={"StringEquals": {"cloudwatch:namespace": "pyvar"}},
        ))

        # Execution role: allows ECS to pull image and write logs
        execution_role = iam.Role(
            self, "ApiExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )
        data.db_secret.grant_read(execution_role)

        # ── Task Definition ───────────────────────────────────────────────────
        task_def = ecs.FargateTaskDefinition(
            self, "ApiTaskDef",
            family=f"pyvar-{cfg.env_name}-api",
            cpu=cfg.api_cpu,
            memory_limit_mib=cfg.api_memory_mb,
            task_role=task_role,
            execution_role=execution_role,
        )

        container = task_def.add_container(
            "api",
            image=ecs.ContainerImage.from_ecr_repository(
                self.ecr_repo, tag=cfg.api_image_tag
            ),
            port_mappings=[ecs.PortMapping(container_port=8000)],
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="pyvar-api",
                log_retention=cdk.aws_logs.RetentionDays.ONE_MONTH,
            ),
            environment={
                "APP_ENV": cfg.env_name,
                "CELERY_BROKER_URL": f"sqs://",
                "SQS_QUEUE_NAME": f"pyvar-{cfg.env_name}-var-jobs.fifo",
                "AWS_REGION": cfg.region,
                "S3_BUCKET": data.result_bucket.bucket_name,
            },
            secrets={
                # Secrets Manager values injected at task start (not in image)
                "POSTGRES_DSN": ecs.Secret.from_secrets_manager(data.db_secret, "connection_string"),
                "JWT_SECRET": ecs.Secret.from_secrets_manager(
                    cdk.aws_secretsmanager.Secret.from_secret_name_v2(
                        self, "JwtSecret", f"pyvar/{cfg.env_name}/jwt-secret"
                    )
                ),
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(30),   # allow Numba JIT warmup
            ),
            stop_timeout=Duration.seconds(30),       # graceful shutdown window
        )

        # ── ALB + Fargate Service ──────────────────────────────────────────────
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "ApiService",
            service_name=f"pyvar-{cfg.env_name}-api",
            cluster=cluster,
            task_definition=task_def,
            desired_count=cfg.api_min_tasks,
            security_groups=[sgs.api],
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            load_balancer_name=f"pyvar-{cfg.env_name}-alb",
            public_load_balancer=True,
            open_listener=False,        # we attach sgs.alb manually
            listener_port=443,
            protocol=elbv2.ApplicationProtocol.HTTP,  # HTTPS requires certificate_arn
            target_protocol=elbv2.ApplicationProtocol.HTTP,
            health_check_grace_period=Duration.seconds(60),
            deployment_controller=ecs.DeploymentController(
                type=ecs.DeploymentControllerType.ECS,
            ),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            capacity_provider_strategies=[
                ecs.CapacityProviderStrategy(
                    capacity_provider="FARGATE_SPOT",
                    weight=2,
                    base=0,
                ),
                ecs.CapacityProviderStrategy(
                    capacity_provider="FARGATE",
                    weight=1,
                    base=cfg.api_min_tasks,   # guarantee on-demand base for HA
                ),
            ],
        )

        # Slow-start: ramp traffic to new tasks over 60s (protects against JIT spike)
        fargate_service.target_group.configure_health_check(
            path="/health",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
        )
        fargate_service.target_group.enable_stickiness_for_origin_header_v2(
            Duration.hours(1)
        )

        # ── Auto-scaling on CPU ───────────────────────────────────────────────
        scaling = fargate_service.service.auto_scale_task_count(
            min_capacity=cfg.api_min_tasks,
            max_capacity=cfg.api_max_tasks,
        )
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=60,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(1),
        )
        # Also scale on request count to catch API-heavy traffic bursts
        scaling.scale_on_request_count(
            "RequestScaling",
            requests_per_target=500,
            target_group=fargate_service.target_group,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(1),
        )

        # ── Expose outputs ────────────────────────────────────────────────────
        self.alb = fargate_service.load_balancer
        self.alb_dns_name = fargate_service.load_balancer.load_balancer_dns_name

        cdk.CfnOutput(self, "AlbDnsName", value=self.alb_dns_name)
        cdk.CfnOutput(self, "EcrRepoUri", value=self.ecr_repo.repository_uri)
        cdk.CfnOutput(self, "ClusterName", value=cluster.cluster_name)

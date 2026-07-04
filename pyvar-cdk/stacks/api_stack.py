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
- Two ALB listeners:
    • HTTPS:443 — ACM cert for pyvar.com; TLS termination for direct clients.
      Default-denies all traffic (403) since CloudFront, not browsers, is the
      intended entry point. Keeps the ALB cert valid and prevents plaintext
      direct access.
    • HTTP:80 — CloudFront origin path. CloudFront sends HTTP on port 80 with
      the X-Origin-Verify secret header; requests without the header get 403.
      HTTP_ONLY on port 80 avoids the CloudFront↔ALB cert-hostname mismatch
      (CloudFront uses the ALB DNS name, which is not in the pyvar.com cert).
  The origin-verify secret is exposed as self.origin_verify_secret for EdgeStack.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_sqs as sqs
from constructs import Construct
from stacks.data_stack import DataStack
from stacks.network_stack import SecurityGroups

from config import PyvarConfig


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
        # Referenced (not created) by this stack. The repo is provisioned and
        # populated out-of-band before the app stack deploys (CI/CD pipeline or
        # manual push), and is RETAIN'd across stack lifecycles — so a fixed-name
        # create would collide with the existing repo on any stack recreate.
        # Lifecycle rules / scan-on-push are managed on the repo itself, not here.
        self.ecr_repo = ecr.Repository.from_repository_name(
            self,
            "ApiRepo",
            f"pyvar-{cfg.env_name}-api",
        )

        # ── ECS Cluster ────────────────────────────────────────────────────────
        cluster = ecs.Cluster(
            self,
            "Cluster",
            cluster_name=f"pyvar-{cfg.env_name}",
            vpc=vpc,
            container_insights=True,  # CloudWatch Container Insights (costs ~$0.50/task/month)
            enable_fargate_capacity_providers=True,
        )

        # ── Task IAM Role ─────────────────────────────────────────────────────
        task_role = iam.Role(
            self,
            "ApiTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            role_name=f"pyvar-{cfg.env_name}-api-task-role",
        )
        var_queue.grant_send_messages(task_role)  # dispatch VaR jobs
        data.result_bucket.grant_read(task_role)  # presigned URL generation
        data.db_secret.grant_read(task_role)
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={"StringEquals": {"cloudwatch:namespace": "pyvar"}},
            )
        )

        # Execution role: allows ECS to pull image and write logs
        execution_role = iam.Role(
            self,
            "ApiExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )
        data.db_secret.grant_read(execution_role)

        # JWT signing secret — CDK-managed (auto-generated), same pattern as the
        # cf-origin-verify secret below. Created here (not imported by name) so the
        # secret actually exists; injected into the API task at start.
        jwt_secret = cdk.aws_secretsmanager.Secret(
            self,
            "JwtSecret",
            secret_name=f"pyvar/{cfg.env_name}/jwt-secret",
            generate_secret_string=cdk.aws_secretsmanager.SecretStringGenerator(
                exclude_punctuation=True,
                password_length=64,
            ),
        )
        jwt_secret.grant_read(execution_role)

        # ── Task Definition ───────────────────────────────────────────────────
        task_def = ecs.FargateTaskDefinition(
            self,
            "ApiTaskDef",
            family=f"pyvar-{cfg.env_name}-api",
            cpu=cfg.api_cpu,
            memory_limit_mib=cfg.api_memory_mb,
            task_role=task_role,
            execution_role=execution_role,
        )

        _container = task_def.add_container(
            "api",
            image=ecs.ContainerImage.from_ecr_repository(self.ecr_repo, tag=cfg.api_image_tag),
            port_mappings=[ecs.PortMapping(container_port=8000)],
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="pyvar-api",
                log_retention=cdk.aws_logs.RetentionDays.ONE_MONTH,
            ),
            environment={
                "APP_ENV": cfg.env_name,
                "CELERY_BROKER_URL": "sqs://",
                "SQS_QUEUE_NAME": f"pyvar-{cfg.env_name}-var-jobs.fifo",
                "AWS_REGION": cfg.region,
                "S3_BUCKET": data.result_bucket.bucket_name,
                "CELERY_RESULT_BACKEND": f"rediss://{data.cache.attr_endpoint_address}:6379/0?ssl_cert_reqs=CERT_NONE",
            },
            secrets={
                # Secrets Manager values injected at task start (not in image).
                # DB credentials are injected as individual fields from the Aurora
                # secret; the app assembles POSTGRES_DSN from them (see config.py).
                # ECS cannot compose a multi-field DSN from one secret key.
                "DB_HOST": ecs.Secret.from_secrets_manager(data.db_secret, "host"),
                "DB_PORT": ecs.Secret.from_secrets_manager(data.db_secret, "port"),
                "DB_NAME": ecs.Secret.from_secrets_manager(data.db_secret, "dbname"),
                "DB_USER": ecs.Secret.from_secrets_manager(data.db_secret, "username"),
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(data.db_secret, "password"),
                "JWT_SECRET": ecs.Secret.from_secrets_manager(jwt_secret),
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(30),  # allow Numba JIT warmup
            ),
            stop_timeout=Duration.seconds(30),  # graceful shutdown window
        )

        # ── ACM Certificate ───────────────────────────────────────────────────
        # DNS-validated TLS certificate for pyvar.com (HTTPS:443 on the ALB).
        # On first deploy CloudFormation blocks here until the CNAME record(s)
        # are added to the pyvar.com DNS zone. After "cdk deploy" starts,
        # retrieve the required records with:
        #
        #   aws acm describe-certificate \
        #     --certificate-arn <CfnOutput: AlbCertificateArn> \
        #     --region eu-west-1 \
        #     --query "Certificate.DomainValidationOptions[*].{Name:ResourceRecord.Name,Value:ResourceRecord.Value}"
        #
        # Note: CloudFront connects to the ALB via HTTP on port 80 (not this
        # HTTPS listener) because CloudFront cert-verification uses the ALB DNS
        # hostname which is not in this certificate. See module docstring.
        alb_certificate = acm.Certificate(
            self,
            "AlbCertificate",
            domain_name="pyvar.com",
            subject_alternative_names=["www.pyvar.com"],
            validation=acm.CertificateValidation.from_dns(),
        )

        # ── ALB + Fargate Service ──────────────────────────────────────────────
        # Build the ALB explicitly with the network-stack ALB security group so
        # that NO new (api-stack-owned) load-balancer SG is created. If we let the
        # pattern auto-create the LB SG, CDK adds an ingress rule onto the network-
        # owned task SG (sgs.api) that references the api-owned LB SG — producing a
        # network -> api dependency and a synth-time DependencyCycle (api already
        # depends on network via the VPC and SGs). Reusing sgs.alb keeps every
        # SG-to-SG rule inside the network stack.
        alb = elbv2.ApplicationLoadBalancer(
            self,
            "Alb",
            vpc=vpc,
            internet_facing=True,
            security_group=sgs.alb,
            load_balancer_name=f"pyvar-{cfg.env_name}-alb",
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "ApiService",
            service_name=f"pyvar-{cfg.env_name}-api",
            cluster=cluster,
            task_definition=task_def,
            desired_count=cfg.api_min_tasks,
            security_groups=[sgs.api],
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            load_balancer=alb,
            open_listener=False,  # ingress is governed by sgs.alb (network stack)
            listener_port=443,
            protocol=elbv2.ApplicationProtocol.HTTPS,
            certificate=alb_certificate,
            target_protocol=elbv2.ApplicationProtocol.HTTP,
            health_check_grace_period=Duration.seconds(60),
            min_healthy_percent=100,  # W4: zero-downtime rolling deploys
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
                    base=cfg.api_min_tasks,  # guarantee on-demand base for HA
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
        fargate_service.target_group.enable_cookie_stickiness(Duration.hours(1))

        # ── Origin-verify secret + listener enforcement ────────────────────────
        # SEC-1 fix: this secret (not a hardcoded literal) is read by CloudFront
        # as a custom origin header (see edge_stack.py) and enforced here at the
        # ALB listener, so a direct request to the ALB — bypassing CloudFront/WAF
        # entirely — is rejected with 403 unless it carries the correct header.
        origin_verify_secret = cdk.aws_secretsmanager.Secret(
            self,
            "OriginVerifySecret",
            secret_name=f"pyvar/{cfg.env_name}/cf-origin-verify",
            generate_secret_string=cdk.aws_secretsmanager.SecretStringGenerator(
                exclude_punctuation=True,
                password_length=32,
            ),
            # Replicate to us-east-1 so the EdgeStack (CloudFront, us-east-1) can
            # resolve the SAME value for the X-Origin-Verify header. Secrets Manager
            # dynamic references are region-local, so a single-region secret here is
            # unresolvable from the edge stack.
            replica_regions=[cdk.aws_secretsmanager.ReplicaRegion(region="us-east-1")],
        )
        # Exposed for EdgeStack — same cross-region mechanism as self.alb_dns_name
        self.origin_verify_secret = origin_verify_secret

        listener = fargate_service.listener

        # Default: reject any request not carrying the correct header
        listener.add_action(
            "DefaultDenyDirectAccess",
            action=elbv2.ListenerAction.fixed_response(
                status_code=403,
                content_type="text/plain",
                message_body="Forbidden",
            ),
        )
        # Only CloudFront (which sets the header) reaches the service
        listener.add_action(
            "OriginVerifyAllow",
            priority=1,
            conditions=[
                elbv2.ListenerCondition.http_header(
                    "X-Origin-Verify",
                    [origin_verify_secret.secret_value.unsafe_unwrap()],
                ),
            ],
            action=elbv2.ListenerAction.forward([fargate_service.target_group]),
        )

        # ── HTTP:80 listener — CloudFront origin path ──────────────────────────
        # CloudFront connects to the ALB via HTTP on port 80 (not HTTPS:443)
        # because CloudFront verifies origin certs against the ALB DNS hostname,
        # which is not in the pyvar.com ACM certificate.  HTTP on port 80 keeps
        # the connection within the AWS backbone (not public internet) while
        # avoiding the hostname/cert mismatch.  The origin-verify header provides
        # the same bypass-prevention as on the HTTPS listener.
        http_listener = alb.add_listener(
            "HttpCfListener",
            port=80,
            open=False,  # port 80 already open on sgs.alb in network_stack
            default_action=elbv2.ListenerAction.fixed_response(
                status_code=403,
                content_type="text/plain",
                message_body="Forbidden",
            ),
        )
        http_listener.add_action(
            "OriginVerifyAllowHttp",
            priority=1,
            conditions=[
                elbv2.ListenerCondition.http_header(
                    "X-Origin-Verify",
                    [origin_verify_secret.secret_value.unsafe_unwrap()],
                ),
            ],
            action=elbv2.ListenerAction.forward([fargate_service.target_group]),
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
        cdk.CfnOutput(
            self,
            "AlbCertificateArn",
            value=alb_certificate.certificate_arn,
            description=(
                "ACM certificate ARN — after deploy starts, run: "
                "aws acm describe-certificate --certificate-arn <arn> --region eu-west-1 "
                '--query "Certificate.DomainValidationOptions[*].{Name:ResourceRecord.Name,Value:ResourceRecord.Value}"'
            ),
        )

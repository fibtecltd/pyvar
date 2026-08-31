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
  The JWT signing secret is exposed as self.jwt_secret for PublicDataStack's
  Lambda (P8 Task 1/2), which mints a short-lived internal service token to
  call this API the same way any other client would.
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
from aws_cdk import aws_ses as ses
from aws_cdk import aws_sqs as sqs
from constructs import Construct
from stacks.data_stack import DataStack
from stacks.network_stack import SecurityGroups

from config import PyvarConfig

# infra/172: mirrors pipeline_stack.py's stack_name= pinning. Without an
# explicit policy_name=, CDK derives one from the FULL construct path
# (including any Stage/Pipeline nesting above this stack), so wrapping this
# stack in PyvarDeployStage changes it even though the stack's own
# stack_name= is unchanged. AWS Application Auto Scaling refuses to have
# two TargetTrackingScaling policies on the same scalable target + metric
# at once, so CloudFormation's create-new-before-delete-old replacement for
# a renamed policy fails outright ("Only one TargetTrackingScaling policy
# for a given metric specification is allowed") instead of just being
# churn — confirmed live against pyvar-dev-api. The dev names below are
# copied verbatim from the policies AWS Application Auto Scaling already
# has live (`aws application-autoscaling describe-scaling-policies
# --service-namespace ecs`) so this is a true no-op update for the
# existing dev deployment, not just a different-but-still-colliding
# rename. Any env with no pre-pipeline deployment (e.g. prod, which has
# never been deployed outside this pipeline) has no live policy to
# collide with, so a plain deterministic name is fine there.
_LEGACY_SCALING_POLICY_NAMES = {
    "dev": {
        "cpu": "pyvardevapiApiServiceTaskCountTargetCpuScaling1843CDE7",
        "request": "pyvardevapiApiServiceTaskCountTargetRequestScaling005FA4CF",
    },
}


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
        ses_identity: ses.EmailIdentity,
        configuration_set: ses.IConfigurationSet,
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
        # Celery SQS broker requires additional queue operations beyond SendMessage:
        # ListQueues (queue discovery), ReceiveMessage + DeleteMessage + ChangeMessageVisibility
        # (result backend polling). grant_send_messages only covers SendMessage.
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sqs:ListQueues",
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:ChangeMessageVisibility",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                ],
                resources=[
                    var_queue.queue_arn,
                    f"arn:aws:sqs:{self.region}:{self.account}:*",  # ListQueues is account-level
                ],
            )
        )
        data.result_bucket.grant_read(task_role)  # presigned URL generation
        data.db_secret.grant_read(task_role)
        # SendEmail/SendRawEmail scoped to this one verified identity (#149) —
        # api/routes/auth.py::send_verification_email is the only caller.
        ses_identity.grant_send_email(task_role)
        # AWS additionally authorizes SendEmail against the CONFIGURATION SET
        # resource itself whenever the identity has one attached as its
        # default (see ses_stack.py) — granting only the identity ARN above
        # is not sufficient once that's set. Discovered live: SendEmail 403'd
        # with "not authorized to perform ses:SendEmail on resource
        # arn:...:configuration-set/..." even though the identity grant was
        # in place. ConfigurationSet has no .arn property (see api_stack.py
        # git history) — built manually, same idiom as the SQS ListQueues
        # ARN below.
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=[
                    f"arn:aws:ses:{self.region}:{self.account}:configuration-set/"
                    f"{configuration_set.configuration_set_name}"
                ],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={"StringEquals": {"cloudwatch:namespace": "pyvar"}},
            )
        )

        # Public data bucket (status.json / demo-result.json — P8 Task 1/2).
        # Referenced by DETERMINISTIC NAME, not a live construct reference:
        # public_data_stack.py depends on THIS stack (for jwt_secret, below) —
        # if this stack also depended on public_data_stack.py's bucket
        # construct, that would be a cycle. Both stacks independently compute
        # the identical name from cfg.env_name + self.account, the same
        # avoid-a-cycle-via-deterministic-naming pattern alerts_stack.py
        # already uses for the queue-age alarm.
        public_data_bucket_name = f"pyvar-{cfg.env_name}-public-{self.account}"
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[f"arn:aws:s3:::{public_data_bucket_name}/public/*"],
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
        # secret actually exists; injected into the API task at start. Stays
        # eu-west-1-only — no us-east-1 replica (unlike cf-origin-verify) —
        # per tests/test_data_residency.py check6: only a routing-only token may
        # cross the region boundary, not the JWT signing secret. PublicDataStack
        # lives in eu-west-1 alongside this stack for the same reason, and reads
        # this secret via a normal same-region grant, not a replica.
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
        self.jwt_secret = jwt_secret

        # Sentry DSN — externally managed (not CDK-generated), same
        # from_secret_name_v2 import pattern as GithubTokenSecret in
        # compute_stack.py. Single shared DSN across dev/prod, differentiated
        # by the `environment` tag observability/setup.py's setup_sentry()
        # already sets from APP_ENV.
        #
        # Deliberately NOT injected via ECS's native `secrets={}` mechanism
        # below (unlike JWT_SECRET/DB_*) -- that mechanism has no "optional"
        # mode: if this secret ever becomes unreadable (deleted, rotated, IAM
        # policy changed), EVERY new Fargate task launch fails outright at
        # secret resolution, and with the deployment's circuit_breaker
        # (rollback=True) + min_healthy_percent=100 (below, for HA), that
        # would block every future prod deploy entirely over an
        # observability nice-to-have. Instead the app fetches this one
        # secret for itself at startup (observability/setup.py's
        # setup_sentry(), via _resolve_sentry_dsn()) where a failure can be
        # caught and degraded gracefully instead of failing ECS task launch
        # -- so it needs read access via the TASK role (the app's own
        # runtime identity), not the execution role (only used by the ECS
        # agent at launch time, e.g. for `secrets={}` resolution and ECR
        # pull).
        sentry_secret = cdk.aws_secretsmanager.Secret.from_secret_name_v2(
            self, "SentrySecret", f"pyvar/{cfg.env_name}/sentry-dsn"
        )
        sentry_secret.grant_read(task_role)

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
                "PUBLIC_DATA_BUCKET": public_data_bucket_name,
                "CELERY_RESULT_BACKEND": f"rediss://{data.cache.attr_endpoint_address}:6379/0?ssl_cert_reqs=CERT_NONE",
                # Was missing entirely -- config.py's ses_sender_email default
                # ("noreply@pyvar.com") was silently used in every environment,
                # including prod, which is granted SendEmail on a DIFFERENT SES
                # identity (cfg.ses_domain_name == "mail.pyvar.com" -- ses_stack.py
                # -- chosen specifically because dev already owns the pyvar.com
                # identity). Every prod registration therefore 403'd on SES with
                # "not authorized to perform ses:SendEmail on resource
                # .../identity/pyvar.com" (send_verification_email's own
                # deliberately-non-fatal except swallowed it, so /auth/register
                # still returned 202 with no email ever sent). Deriving this from
                # cfg.ses_domain_name -- the SAME field ses_stack.py/api_stack.py's
                # IAM grant already key off -- instead of hardcoding a second
                # "mail.pyvar.com" literal here ties sender address and granted
                # identity together permanently; they cannot drift apart again.
                # "noreply@" needs no real inbox to exist -- SES's identity grant
                # authorizes the DOMAIN for sending, not any particular mailbox,
                # and outbound-only transactional mail was never going to accept
                # replies anyway (dev has sent successfully from noreply@pyvar.com
                # this whole time with no real inbox behind it either).
                "SES_SENDER_EMAIL": f"noreply@{cfg.ses_domain_name}",
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
                # SENTRY_DSN deliberately NOT here -- see the comment above
                # sentry_secret's construction for why.
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
        legacy_policy_names = _LEGACY_SCALING_POLICY_NAMES.get(cfg.env_name, {})
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=60,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(1),
            policy_name=legacy_policy_names.get("cpu", f"pyvar-{cfg.env_name}-api-cpu-scaling"),
        )
        # Also scale on request count to catch API-heavy traffic bursts
        scaling.scale_on_request_count(
            "RequestScaling",
            requests_per_target=500,
            target_group=fargate_service.target_group,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(1),
            policy_name=legacy_policy_names.get(
                "request", f"pyvar-{cfg.env_name}-api-request-scaling"
            ),
        )

        # ── Migration task (issue #119: automated DB migration on deploy) ─────
        # A dedicated one-off Fargate task — no ALB, no service, no health
        # check, it runs `scripts/db.py upgrade` to completion and stops.
        # pipeline_stack.py's pre-deploy step launches it via `aws ecs
        # run-task` BEFORE this stack's own API service update rolls out, so
        # a failed migration blocks the deploy instead of shipping a
        # schema-mismatched API.
        #
        # Reuses the SAME ECR image as the API task (command override only,
        # no second image build) — scripts/, migrations/, alembic.ini, and
        # every dependency the migration needs (alembic, psycopg2-binary)
        # are already baked into it (see Dockerfile / requirements.txt).
        #
        # Dedicated task + execution roles (not the API's task_role /
        # execution_role above) rather than reusing them: least-privilege —
        # this task only ever needs to read the DB secret, nothing else the
        # API task role grants (SQS, S3, CloudWatch) — and giving both
        # roles their own explicit, deterministic role_name means
        # pipeline_stack.py's IAM policy for the migration step (iam:PassRole)
        # can reference a fixed ARN rather than needing another cross-stack
        # CfnOutput.
        migration_execution_role = iam.Role(
            self,
            "MigrationExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            role_name=f"pyvar-{cfg.env_name}-migration-execution-role",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )
        data.db_secret.grant_read(migration_execution_role)

        migration_task_role = iam.Role(
            self,
            "MigrationTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            role_name=f"pyvar-{cfg.env_name}-migration-task-role",
        )
        data.db_secret.grant_read(migration_task_role)

        migration_task_def = ecs.FargateTaskDefinition(
            self,
            "MigrationTaskDef",
            family=f"pyvar-{cfg.env_name}-migrate",
            cpu=256,
            memory_limit_mib=512,
            task_role=migration_task_role,
            execution_role=migration_execution_role,
        )
        migration_task_def.add_container(
            "migrate",
            image=ecs.ContainerImage.from_ecr_repository(self.ecr_repo, tag=cfg.api_image_tag),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="pyvar-migrate",
                log_retention=cdk.aws_logs.RetentionDays.ONE_MONTH,
            ),
            environment={"APP_ENV": cfg.env_name},
            secrets={
                # Same five-field DB secret injection as the API task above —
                # migrations/env.py's get_sync_url() assembles postgres_dsn
                # from these via config.py, identically to the app.
                "DB_HOST": ecs.Secret.from_secrets_manager(data.db_secret, "host"),
                "DB_PORT": ecs.Secret.from_secrets_manager(data.db_secret, "port"),
                "DB_NAME": ecs.Secret.from_secrets_manager(data.db_secret, "dbname"),
                "DB_USER": ecs.Secret.from_secrets_manager(data.db_secret, "username"),
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(data.db_secret, "password"),
            },
            command=["python", "scripts/db.py", "upgrade"],
        )

        # The migration task runs in the same subnets/security group as the
        # API task (sgs.api already has an Aurora ingress rule — see
        # network_stack.py), so no new security-group wiring is needed here.
        # pipeline_stack.py's migration step discovers those subnet/SG IDs
        # itself at pipeline run time via tag-filtered EC2 API calls (a
        # same-stage CfnOutput would create a dependency cycle against this
        # stack's own deploy — see that module's _migration_step docstring),
        # which is why sgs.api carries an explicit Name tag for it to filter
        # on (network_stack.py).

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

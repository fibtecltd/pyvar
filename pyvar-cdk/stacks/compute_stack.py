"""
stacks/compute_stack.py — EC2 Spot Auto Scaling Group for Celery workers

Reasoning:
- c7i.xlarge (4 vCPU, 8 GB) is AWS's latest compute-optimised generation.
  Numba JIT Monte Carlo saturates all 4 cores via prange — no memory pressure.
  c7i beats c6i by ~15% on compute at similar price. c7i.2xlarge would double
  cost but only give 2x throughput — not better per-£.
- PRICE_CAPACITY_OPTIMIZED spot strategy picks the pool least likely to be
  interrupted (not just cheapest). For financial workloads, avoiding
  mid-simulation interruption is worth a few extra cents/hour.
- min_capacity=0: when SQS is empty (nights, weekends) zero workers run.
  This is the single biggest cost saving — workers only cost money when
  there are jobs to process.
- Lifecycle hook on TERMINATING gives workers 60 seconds to drain before
  the instance is terminated. Combined with task_acks_late=True in Celery,
  in-flight tasks complete gracefully or return to the queue.
- UserData installs the pyvar worker from a pre-built S3 wheel and starts
  the Celery systemd service. In production, bake an AMI with dependencies
  pre-installed to reduce startup time from ~90s to ~20s.
- Target-tracking scaling (not step scaling) holds queue depth at
  target_value messages per worker, continuously adjusting capacity —
  replaced the earlier step-scaling approach (W2 fix) which overshot
  on sudden demand drops.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sqs as sqs
from constructs import Construct
from stacks.data_stack import DataStack
from stacks.network_stack import SecurityGroups

from config import PyvarConfig


class ComputeStack(Stack):

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        vpc: ec2.Vpc,
        sgs: SecurityGroups,
        var_queue: sqs.Queue,
        dlq: sqs.Queue,
        data: DataStack,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── IAM Role for EC2 workers ─────────────────────────────────────────────
        worker_role = iam.Role(
            self,
            "WorkerRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            role_name=f"pyvar-{cfg.env_name}-worker-role",
            managed_policies=[
                # SSM Session Manager — no SSH keys, no bastion hosts needed
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )

        # SQS — poll jobs from main queue, send to DLQ on failure
        var_queue.grant_consume_messages(worker_role)
        # sqs:ListQueues is required by Celery's SQS transport on startup
        # (grant_consume_messages does not include it)
        worker_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sqs:ListQueues"],
                resources=[f"arn:aws:sqs:{self.region}:{self.account}:*"],
            )
        )
        dlq.grant_send_messages(worker_role)

        # S3 — write Parquet simulation results
        data.result_bucket.grant_put(worker_role)

        # Secrets Manager — read DB credentials and JWT secret
        data.db_secret.grant_read(worker_role)
        # GitHub token — needed by Hypothesis B (git clone) to pull pyvar source
        # TODO: remove when Hypothesis C (AMI bake) replaces git clone
        cdk.aws_secretsmanager.Secret.from_secret_name_v2(
            self, "GithubTokenSecret", "pyvar/github-token"
        ).grant_read(worker_role)
        # Sentry DSN — externally managed, optional (fetch-config.sh degrades
        # gracefully if missing/denied; see its own comment for why this must
        # never block worker startup).
        cdk.aws_secretsmanager.Secret.from_secret_name_v2(
            self, "SentrySecret", f"pyvar/{cfg.env_name}/sentry-dsn"
        ).grant_read(worker_role)

        # CloudWatch — publish custom metrics (computation duration, sim count)
        worker_role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={"StringEquals": {"cloudwatch:namespace": "pyvar"}},
            )
        )

        # ── CloudWatch Logs — worker log group ─────────────────────────────────
        # EC2/Celery workers previously logged to journald only, which is invisible
        # to CloudWatch. Ship the Celery service's stdout/stderr here via the
        # CloudWatch agent (configured in UserData below) so operational alarms —
        # e.g. the worker-error metric filter — have a data source. Retention
        # matches the API log group (30 days). These are operational logs, not the
        # regulatory audit trail (that is the VaRJob table), so DESTROY on stack
        # removal is fine and avoids orphaned log groups.
        worker_log_group_name = f"/pyvar/{cfg.env_name}/worker"
        self.worker_log_group = logs.LogGroup(
            self,
            "WorkerLogGroup",
            log_group_name=worker_log_group_name,
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        # The agent creates the per-instance log stream and puts events; the group
        # itself is CDK-managed. grant_write covers CreateLogStream + PutLogEvents;
        # add the describe/create-group calls the agent makes on startup. Scoped to
        # this log group only.
        self.worker_log_group.grant_write(worker_role)
        worker_role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:CreateLogGroup", "logs:DescribeLogStreams"],
                resources=[
                    self.worker_log_group.log_group_arn,
                    f"{self.worker_log_group.log_group_arn}:*",
                ],
            )
        )

        # ── Worker error metric filter ─────────────────────────────────────────
        # Count ERROR/CRITICAL lines in the worker logs. alerts_stack (P6) builds
        # the alarm that pages on this metric; exposing the metric (not just the
        # log group) keeps the namespace/name an implementation detail of this
        # stack. default_value=0 emits a zero data point in periods that have logs
        # but no matches, so the alarm evaluates cleanly while workers are healthy.
        worker_error_filter = self.worker_log_group.add_metric_filter(
            "WorkerErrorFilter",
            filter_pattern=logs.FilterPattern.any_term("ERROR", "CRITICAL"),
            metric_namespace="pyvar",
            metric_name=f"worker-errors-{cfg.env_name}",
            metric_value="1",
            default_value=0,
        )
        self.worker_error_metric = worker_error_filter.metric(
            statistic="Sum",
            period=Duration.minutes(5),
        )

        # ── EC2 Launch Template ────────────────────────────────────────────────
        instance_type = ec2.InstanceType(cfg.worker_instance_type)

        # Shared systemd fragments used by both Hypothesis B and C paths.
        # plain "export VAR=val" in user data only affects the bash process;
        # systemctl start spawns a new process that does not inherit exports.
        celery_env_block = (
            "mkdir -p /opt/pyvar\n"
            "cat > /opt/pyvar/celery.env << 'ENVEOF'\n"
            "CELERY_BROKER_URL=sqs://\n"
            "CELERY_WORKER_POOL=prefork\n"
            f"CELERY_RESULT_BACKEND=rediss://{data.cache.attr_endpoint_address}:6379/0?ssl_cert_reqs=CERT_NONE\n"
            f"SQS_QUEUE_NAME=pyvar-{cfg.env_name}-var-jobs.fifo\n"
            f"AWS_DEFAULT_REGION={cfg.region}\n"
            "NUMBA_CACHE_DIR=/opt/numba_cache\n"
            f"PYVAR_ENV_NAME={cfg.env_name}\n"
            # P7 Task 3: benchmarked concurrency 1/2/4 on c5.xlarge (10 VaR jobs,
            # n_simulations=100_000 each, submitted through the real API). 1->2
            # cut total wall-clock ~26% (5.76s -> 4.28s); 2->4 gave no further
            # gain (4.28s vs 4.25s, within noise) while peak CPU jumped from
            # ~16% to ~84% and the worker's memory delta roughly doubled — each
            # Celery worker process's Numba parallel=True kernels already
            # spread across all 4 vCPUs, so concurrency=4 means 4x
            # oversubscription of the same 4 cores for zero measured benefit.
            # See docs/p7-celery-concurrency-results.md for the full data.
            "CELERY_CONCURRENCY=2\n"
            "ENVEOF"
        )
        # EnvironmentFile=-/opt/pyvar/secrets.env: '-' prefix makes it optional so
        # systemd doesn't fail on first reload before ExecStartPre has written it.
        # UserData also calls fetch-config.sh directly before systemctl start, since
        # systemd loads EnvironmentFile before running ExecStartPre — the file must
        # already exist on first boot.
        celery_unit_block = (
            "cat > /etc/systemd/system/celery-worker.service << 'EOF'\n"
            "[Unit]\nDescription=pyvar Celery Worker\nAfter=network.target\n\n"
            "[Service]\nType=simple\nWorkingDirectory=/opt/pyvar\n"
            "EnvironmentFile=/opt/pyvar/celery.env\n"
            "EnvironmentFile=-/opt/pyvar/secrets.env\n"
            "ExecStartPre=/opt/pyvar/scripts/fetch-config.sh\n"
            "ExecStart=/usr/bin/python3.11 worker.py\n"
            # Ship stdout+stderr to a file the CloudWatch agent tails — journald
            # alone is not forwarded to CloudWatch. /var/log/pyvar is created by
            # cloudwatch_agent_block below, before the service starts.
            "StandardOutput=append:/var/log/pyvar/worker.log\n"
            "StandardError=append:/var/log/pyvar/worker.log\n"
            "Restart=always\nRestartSec=10\n\n"
            "[Install]\nWantedBy=multi-user.target\nEOF"
        )

        # CloudWatch agent: tail the worker log file into the CloudWatch log group.
        # Config is written inline (no SSM parameter dependency). {instance_id} is
        # substituted by the agent at runtime to give each worker its own stream.
        cloudwatch_agent_block = (
            "mkdir -p /var/log/pyvar\n"
            "mkdir -p /opt/aws/amazon-cloudwatch-agent/etc\n"
            "cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json"
            " << 'CWEOF'\n"
            "{\n"
            '  "agent": {"run_as_user": "root"},\n'
            '  "logs": {\n'
            '    "logs_collected": {\n'
            '      "files": {\n'
            '        "collect_list": [\n'
            "          {\n"
            '            "file_path": "/var/log/pyvar/worker.log",\n'
            f'            "log_group_name": "{worker_log_group_name}",\n'
            '            "log_stream_name": "{instance_id}",\n'
            '            "timezone": "UTC"\n'
            "          }\n"
            "        ]\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}\n"
            "CWEOF"
        )
        # Install the agent if the AMI doesn't already ship it (baked AMIs should),
        # then load the config and start it. Idempotent across both boot paths.
        cloudwatch_agent_start = (
            "command -v amazon-cloudwatch-agent-ctl >/dev/null 2>&1 || "
            "dnf install -y amazon-cloudwatch-agent\n"
            "/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl "
            "-a fetch-config -m ec2 -s "
            "-c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json"
        )

        user_data = ec2.UserData.for_linux()

        if cfg.worker_use_baked_ami:
            # Hypothesis C: pre-baked AMI — dependencies + Numba cache already on disk.
            # UserData only clones the latest pyvar source and wires up systemd.
            # Cold start: ~25s (OS boot + git clone + service start).
            # AMI is looked up dynamically by name pattern rather than a hardcoded
            # ID — every cdk deploy picks up whichever AMI the Image Builder
            # pipeline most recently produced, no manual config.py edit needed.
            # CAVEAT: CDK caches lookup results in cdk.context.json. After a new
            # AMI bake, clear the stale entry before deploying:
            #   cdk context --clear
            # or remove just the ami-lookup key from cdk.context.json.
            machine_image: ec2.IMachineImage = ec2.MachineImage.lookup(
                name=f"pyvar-{cfg.env_name}-worker-*",
                owners=[self.account],
            )
            user_data.add_commands(
                "#!/bin/bash",
                "set -euo pipefail",
                f"export AWS_DEFAULT_REGION={cfg.region}",
                f"export PYVAR_ENV_NAME={cfg.env_name}",
                "GH_TOKEN=$(aws secretsmanager get-secret-value "
                f"--secret-id pyvar/github-token --region {cfg.region} "
                "--query SecretString --output text)",
                "git clone https://x-access-token:${GH_TOKEN}@github.com/fibtecltd/pyvar.git /opt/pyvar",
                "chmod +x /opt/pyvar/scripts/fetch-config.sh",
                celery_env_block,
                # Populate secrets.env before systemctl start — systemd loads
                # EnvironmentFile before ExecStartPre so the file must exist on first boot.
                "/opt/pyvar/scripts/fetch-config.sh",
                celery_unit_block,
                cloudwatch_agent_block,
                cloudwatch_agent_start,
                "systemctl daemon-reload",
                "systemctl enable celery-worker",
                "systemctl start celery-worker",
            )
        else:
            # Hypothesis B: stock AL2023 — runtime pip install at boot.
            # Cold start: ~5min (yum + pip + git clone).
            # TODO: replace with Hypothesis C once AMI pipeline (P6/P7) is ready.
            machine_image = ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.X86_64,
            )
            user_data.add_commands(
                "#!/bin/bash",
                "set -euo pipefail",
                # System dependencies
                "yum update -y",
                "yum install -y python3.11 python3.11-pip git",
                # Do NOT change system python3 — aws CLI and yum depend on python3.9
                # Use python3.11 and pip3.11 explicitly throughout
                "GH_TOKEN=$(aws secretsmanager get-secret-value "
                f"--secret-id pyvar/github-token --region {cfg.region} "
                "--query SecretString --output text)",
                "git clone https://x-access-token:${GH_TOKEN}@github.com/fibtecltd/pyvar.git /opt/pyvar",
                "yum install -y libcurl-devel",
                "pip3.11 install -r /opt/pyvar/requirements-heavy.txt",
                "pip3.11 install -r /opt/pyvar/requirements.txt",
                f"export AWS_DEFAULT_REGION={cfg.region}",
                f"export PYVAR_ENV_NAME={cfg.env_name}",
                "chmod +x /opt/pyvar/scripts/fetch-config.sh",
                celery_env_block,
                # Populate secrets.env before systemctl start — systemd loads
                # EnvironmentFile before ExecStartPre so the file must exist on first boot.
                "/opt/pyvar/scripts/fetch-config.sh",
                celery_unit_block,
                cloudwatch_agent_block,
                cloudwatch_agent_start,
                "systemctl daemon-reload",
                "systemctl enable celery-worker",
                "systemctl start celery-worker",
            )

        launch_template = ec2.LaunchTemplate(
            self,
            "WorkerLaunchTemplate",
            launch_template_name=f"pyvar-{cfg.env_name}-worker",
            instance_type=instance_type,
            machine_image=machine_image,
            role=worker_role,
            security_group=sgs.worker,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        20,  # GB — enough for pip cache + Numba compiled objects
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                )
            ],
            require_imdsv2=True,  # security: block IMDSv1 credential theft
            http_put_response_hop_limit=1,  # defense-in-depth: 1 hop prevents container SSRF reaching IMDS
            nitro_enclave_enabled=False,
        )
        # Tier 3 (independent strategic assessment): Cost Explorer's service-
        # level breakdown groups NAT Gateway usage under "EC2 - Other" — the
        # same top-level "EC2" service Spot worker instances bill under —
        # with no way to tell the two apart. The generic Project/Environment/
        # ManagedBy/Owner tags (applied stage-wide, see pipeline_stack.py's
        # PyvarDeployStage) don't help here either: NAT Gateway gets the
        # exact same tag values, since it sits in the same stage. A tag
        # naming the SPECIFIC cost component is what's actually needed.
        # cdk.Tags.of() on a LaunchTemplate construct — verified via cdk
        # synth — generates TagSpecifications for both the "instance" and
        # "volume" resource types, so this reaches the real running EC2
        # instances (and their EBS volumes), not just the LaunchTemplate
        # resource's own CloudFormation-level tags.
        cdk.Tags.of(launch_template).add("CostComponent", "spot-worker-compute")

        # ── Auto Scaling Group ────────────────────────────────────────────────
        # Spot vs on-demand controlled by cfg.worker_use_spot (Option B).
        # Set worker_use_spot=False in config.py for guaranteed on-demand capacity.
        # Set worker_instance_type in config.py to switch instance family (Option C).
        _asg_kwargs: dict = {}
        if cfg.worker_use_spot:
            _asg_kwargs["mixed_instances_policy"] = autoscaling.MixedInstancesPolicy(
                instances_distribution=autoscaling.InstancesDistribution(
                    on_demand_percentage_above_base_capacity=0,  # 100% Spot
                    spot_max_price=cfg.worker_spot_max_price,
                    spot_allocation_strategy=autoscaling.SpotAllocationStrategy.PRICE_CAPACITY_OPTIMIZED,
                ),
                launch_template=launch_template,
            )
        else:
            # On-demand only — guaranteed capacity, no Spot interruptions
            _asg_kwargs["launch_template"] = launch_template

        self.asg = autoscaling.AutoScalingGroup(
            self,
            "WorkerAsg",
            auto_scaling_group_name=f"pyvar-{cfg.env_name}-workers",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            **_asg_kwargs,
            min_capacity=cfg.worker_min_capacity,
            max_capacity=cfg.worker_max_capacity,
            # Must be >= min_capacity (CDK/CloudFormation both enforce this) —
            # was a hardcoded 0 until PR #227 raised prod's worker_min_capacity
            # to 1 (temporary launch-window mitigation), which broke synth
            # outright ("Should have minCapacity (1) <= desiredCapacity (0)")
            # since 0 no longer satisfies that constraint for prod. Tracking
            # worker_min_capacity keeps every environment's actual starting
            # point consistent with its own floor instead of a separate
            # hardcoded value that has to be remembered and kept in sync by
            # hand; SQS target-tracking still takes over scaling from there.
            desired_capacity=cfg.worker_min_capacity,
            # Health check: if instance fails 2 consecutive EC2 status checks, replace it
            health_check=autoscaling.HealthCheck.ec2(grace=Duration.seconds(120)),
            update_policy=autoscaling.UpdatePolicy.rolling_update(
                max_batch_size=2,
                min_instances_in_service=0,
            ),
        )

        # Warm pool (pre-initialise stopped instances so scale-out is ~30s
        # instead of ~90s) was attempted here for prod, but AWS rejects it
        # outright: "You can't add a warm pool to an Auto Scaling group that
        # has a mixed instances policy or a launch template or launch
        # configuration that requests Spot Instances." Confirmed live against
        # pyvar-prod-compute's first-ever deploy — CREATE_FAILED, not a
        # config issue. Warm pools and Spot-based mixed_instances_policy
        # (above) are mutually exclusive on the same ASG; Spot is the
        # deliberate cost strategy for this workload (see module docstring
        # and CLAUDE.md), so the warm pool is dropped rather than the other
        # way around. Scale-from-zero is ~90s instead of ~30s as a result.

        # Lifecycle hook: give workers 60s to drain before termination
        # Celery's task_acks_late=True means in-flight tasks return to queue if killed
        self.asg.add_lifecycle_hook(
            "DrainOnTermination",
            lifecycle_transition=autoscaling.LifecycleTransition.INSTANCE_TERMINATING,
            heartbeat_timeout=Duration.seconds(60),
            default_result=autoscaling.DefaultResult.CONTINUE,
        )

        # ── Target-tracking on SQS queue depth (W2 fix) ─────────────────────────
        # Target tracking continuously adjusts capacity to keep ≤5 messages per
        # worker, removing the step-scaling cooldown interaction that produced W2.
        # With min_capacity=0, ASG scales to zero when the queue is empty.
        queue_depth_metric = cloudwatch.Metric(
            namespace="AWS/SQS",
            metric_name="ApproximateNumberOfMessagesVisible",
            dimensions_map={"QueueName": var_queue.queue_name},
            period=Duration.minutes(1),
            statistic="Average",
        )
        autoscaling.TargetTrackingScalingPolicy(
            self,
            "ScaleOnQueueDepth",
            auto_scaling_group=self.asg,
            target_value=5.0,
            custom_metric=queue_depth_metric,
            estimated_instance_warmup=Duration.seconds(90),
        )

        # ── Step-scaling zero→one kickstart ─────────────────────────────────────
        # Target tracking cannot scale out from 0 capacity — the backlog-per-instance
        # ratio is undefined/never evaluated when there are 0 running instances,
        # regardless of target_value. This is a documented AWS limitation, not a
        # tuning problem. This step policy handles just the 0→1 transition; target
        # tracking above takes over for all scaling once at least 1 instance is up.
        # EXACT_CAPACITY is idempotent (always sets to a fixed value rather than
        # incrementing), so repeated alarm breaches during a sustained burst can't
        # compound into runaway scale-out the way CHANGE_IN_CAPACITY could.
        # If both policies propose conflicting capacities in the same evaluation,
        # AWS resolves it by taking the larger scale-out / less aggressive scale-in
        # — so this can never fight target tracking's own decisions once running.
        #
        # Deliberately NOT queue_depth_metric (unlike ScaleOnQueueDepth above) —
        # task #38, Day -3 smoke test finding: SQS stops publishing ANY CloudWatch
        # metric for a queue after 6+ hours of zero activity, and delivery resumes
        # with UP TO A 15-MINUTE LAG once activity resumes. That's a platform-level
        # behavior of SQS's own CloudWatch integration, not specific to
        # ApproximateNumberOfMessagesVisible — switching to e.g. NumberOfMessagesSent
        # (an earlier, incorrect hypothesis) would hit the identical delay, since
        # that metric is subject to the same "queue must be active" gating. A
        # custom, app-published metric has no such gating: api/routes/var.py
        # publishes this the instant a job is enqueued, via a plain put_metric_data
        # call that's always accepted immediately regardless of how long the queue
        # was idle — bypassing SQS's own metrics pipeline entirely for just this
        # 0->1 kickstart.
        job_submitted_metric = cloudwatch.Metric(
            namespace="pyvar",
            metric_name=f"job-submitted-{cfg.env_name}",
            period=Duration.minutes(1),
            statistic="Sum",
        )
        self.asg.scale_on_metric(
            "ScaleFromZero",
            metric=job_submitted_metric,
            scaling_steps=[
                autoscaling.ScalingInterval(upper=1, change=0),
                autoscaling.ScalingInterval(lower=1, change=1),
            ],
            adjustment_type=autoscaling.AdjustmentType.EXACT_CAPACITY,
            cooldown=Duration.minutes(2),
        )

        # ── Outputs ───────────────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "AsgName", value=self.asg.auto_scaling_group_name)
        cdk.CfnOutput(self, "WorkerLogGroupName", value=self.worker_log_group.log_group_name)

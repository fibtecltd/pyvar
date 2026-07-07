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
- Step scaling uses EXACT_CAPACITY (set workers to N) not CHANGE_IN_CAPACITY
  (add/remove N). EXACT_CAPACITY is more predictable for queue-depth scaling
  because it avoids overshoot when demand drops suddenly.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
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
        dlq.grant_send_messages(worker_role)

        # S3 — write Parquet simulation results
        data.result_bucket.grant_put(worker_role)

        # Secrets Manager — read DB credentials and JWT secret
        data.db_secret.grant_read(worker_role)

        # CloudWatch — publish custom metrics (computation duration, sim count)
        worker_role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={"StringEquals": {"cloudwatch:namespace": "pyvar"}},
            )
        )

        # ── EC2 Launch Template ────────────────────────────────────────────────
        instance_type = ec2.InstanceType(cfg.worker_instance_type)

        # UserData: install pyvar worker and start Celery via systemd
        # In production: replace with a pre-baked AMI to cut startup from ~90s to ~20s
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "#!/bin/bash",
            "set -euo pipefail",
            # System dependencies
            "yum update -y",
            "yum install -y python3.11 python3.11-pip git",
            "update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 2>/dev/null || true",
            # Clone pyvar from GitHub and install dependencies.
            # Hypothesis B (dev): replaces S3 artifact — always in sync with master.
            # TODO (P6/P7 Hypothesis C): replace with pre-baked AMI via Image Builder
            #   to eliminate runtime install and reduce cold-start from ~5min to ~20s.
            "GH_TOKEN=$(aws secretsmanager get-secret-value "
            f"--secret-id pyvar/github-token --region {cfg.region} "
            "--query SecretString --output text)",
            "git clone https://x-access-token:${GH_TOKEN}@github.com/fibtecltd/pyvar.git /opt/pyvar",
            "pip3 install -r /opt/pyvar/requirements.txt",
            # Pull secrets from Secrets Manager and export as env vars
            f"export AWS_REGION={cfg.region}",
            "SECRET=$(aws secretsmanager get-secret-value "
            f"--secret-id pyvar/{cfg.env_name}/aurora-credentials "
            "--query SecretString --output text)",
            "export DB_HOST=$(echo $SECRET | python3 -c \"import sys,json; print(json.load(sys.stdin)['host'])\")",
            "export DB_PASS=$(echo $SECRET | python3 -c \"import sys,json; print(json.load(sys.stdin)['password'])\")",
            # Configure Celery to use SQS broker
            "export CELERY_BROKER_URL=sqs://",
            f"export CELERY_RESULT_BACKEND=rediss://{data.cache.attr_endpoint_address}:6379/0?ssl_cert_reqs=CERT_NONE",
            f"export SQS_QUEUE_NAME=pyvar-{cfg.env_name}-var-jobs.fifo",
            f"export AWS_DEFAULT_REGION={cfg.region}",
            # Write env vars to EnvironmentFile so systemd service inherits them.
            # plain "export VAR=val" in user data only affects the bash process;
            # systemctl start spawns a new process that does not inherit exports.
            "mkdir -p /opt/pyvar",
            "cat > /opt/pyvar/celery.env << 'ENVEOF'\n"
            "CELERY_BROKER_URL=sqs://\n"
            f"CELERY_RESULT_BACKEND=rediss://{data.cache.attr_endpoint_address}:6379/0?ssl_cert_reqs=CERT_NONE\n"
            f"SQS_QUEUE_NAME=pyvar-{cfg.env_name}-var-jobs.fifo\n"
            f"AWS_DEFAULT_REGION={cfg.region}\n"
            "ENVEOF",
            # Install Celery as a systemd service
            "cat > /etc/systemd/system/celery-worker.service << 'EOF'\n"
            "[Unit]\nDescription=pyvar Celery Worker\nAfter=network.target\n\n"
            "[Service]\nType=forking\nWorkingDirectory=/opt/pyvar\n"
            "EnvironmentFile=/opt/pyvar/celery.env\n"
            "ExecStart=/usr/bin/python3 worker.py\n"
            "Restart=always\nRestartSec=10\n\n"
            "[Install]\nWantedBy=multi-user.target\nEOF",
            "systemctl daemon-reload",
            "systemctl enable celery-worker",
            "systemctl start celery-worker",
        )

        launch_template = ec2.LaunchTemplate(
            self,
            "WorkerLaunchTemplate",
            launch_template_name=f"pyvar-{cfg.env_name}-worker",
            instance_type=instance_type,
            machine_image=ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.X86_64,
            ),
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
            desired_capacity=0,  # start with 0; SQS scaling takes over
            # Health check: if instance fails 2 consecutive EC2 status checks, replace it
            health_check=autoscaling.HealthCheck.ec2(grace=Duration.seconds(120)),
            update_policy=autoscaling.UpdatePolicy.rolling_update(
                max_batch_size=2,
                min_instances_in_service=0,
            ),
        )

        # Warm pool: pre-initialise stopped instances so scale-out is faster (~30s vs ~90s).
        # Warm pool costs ~30% of running instance price while stopped — prod only.
        # NOTE: warm pools are attached via add_warm_pool(), not an ASG constructor kwarg.
        if cfg.env_name == "prod":
            self.asg.add_warm_pool(
                min_size=1,
                pool_state=autoscaling.PoolState.STOPPED,
            )

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
            target_value=1.0,
            custom_metric=queue_depth_metric,
            estimated_instance_warmup=Duration.seconds(90),
        )

        # ── Outputs ───────────────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "AsgName", value=self.asg.auto_scaling_group_name)

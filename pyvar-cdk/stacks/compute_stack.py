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

        # ── IAM Role for EC2 workers ───────────────────────────────────────────
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
            "yum install -y python3.11 python3.11-pip",
            "alternatives --set python3 /usr/bin/python3.11",
            # Pull application wheel from S3 (version baked into AMI in production)
            f"aws s3 cp s3://pyvar-{cfg.env_name}-deploy/pyvar-latest.tar.gz /opt/pyvar.tar.gz",
            "mkdir -p /opt/pyvar && tar -xzf /opt/pyvar.tar.gz -C /opt/pyvar",
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
            f"export CELERY_RESULT_BACKEND=redis://$(aws ssm get-parameter "
            f"--name /pyvar/{cfg.env_name}/cache-endpoint --query Parameter.Value --output text):6379/0",
            f"export SQS_QUEUE_NAME=pyvar-{cfg.env_name}-var-jobs.fifo",
            # Install Celery as a systemd service
            "cat > /etc/systemd/system/celery-worker.service << 'EOF'\n"
            "[Unit]\nDescription=pyvar Celery Worker\nAfter=network.target\n\n"
            "[Service]\nType=forking\nWorkingDirectory=/opt/pyvar\n"
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
            nitro_enclave_enabled=False,
        )

        # ── Auto Scaling Group ────────────────────────────────────────────────
        self.asg = autoscaling.AutoScalingGroup(
            self,
            "WorkerAsg",
            auto_scaling_group_name=f"pyvar-{cfg.env_name}-workers",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            # Use MixedInstancesPolicy for Spot with capacity-optimised allocation
            mixed_instances_policy=autoscaling.MixedInstancesPolicy(
                instances_distribution=autoscaling.InstancesDistribution(
                    on_demand_percentage_above_base_capacity=0,  # 100% Spot
                    spot_max_price=cfg.worker_spot_max_price,
                    spot_allocation_strategy=autoscaling.SpotAllocationStrategy.PRICE_CAPACITY_OPTIMIZED,
                ),
                launch_template=autoscaling.LaunchTemplateOverrides(
                    launch_template=launch_template,
                ),
            ),
            min_capacity=cfg.worker_min_capacity,
            max_capacity=cfg.worker_max_capacity,
            desired_capacity=0,  # start with 0; SQS scaling takes over
            # Health check: if instance fails 2 consecutive EC2 status checks, replace it
            health_check=autoscaling.HealthCheck.ec2(grace=Duration.seconds(120)),
            # Warm pool: pre-initialise stopped instances so scale-out is faster (~30s vs ~90s)
            # Warm pool costs ~30% of running instance price while stopped
            warm_pool=(
                autoscaling.WarmPool(
                    min_size=1,
                    pool_state=autoscaling.PoolState.STOPPED,
                )
                if cfg.env_name == "prod"
                else None
            ),
            update_policy=autoscaling.UpdatePolicy.rolling_update(
                max_batch_size=2,
                min_instances_in_service=0,
            ),
        )

        # Lifecycle hook: give workers 60s to drain before termination
        # Celery's task_acks_late=True means in-flight tasks return to queue if killed
        self.asg.add_lifecycle_hook(
            "DrainOnTermination",
            lifecycle_transition=autoscaling.LifecycleTransition.INSTANCE_TERMINATING,
            heartbeat_timeout=Duration.seconds(60),
            default_result=autoscaling.DefaultResult.CONTINUE,
        )

        # ── Step scaling on SQS queue depth ───────────────────────────────────
        # Queue depth metric: ApproximateNumberOfMessagesVisible
        queue_depth_metric = cloudwatch.Metric(
            namespace="AWS/SQS",
            metric_name="ApproximateNumberOfMessagesVisible",
            dimensions_map={"QueueName": var_queue.queue_name},
            period=Duration.minutes(1),
            statistic="Average",
        )

        # scale_on_metric with EXACT_CAPACITY:
        # - 0 messages  → 0 workers  (scale to zero)
        # - 1-5 msgs    → 1 worker
        # - 6-20 msgs   → 3 workers
        # - 21-50 msgs  → 6 workers
        # - 51+ msgs    → 12 workers
        self.asg.scale_on_metric(
            "ScaleOnQueueDepth",
            metric=queue_depth_metric,
            scaling_steps=[
                autoscaling.ScalingInterval(upper=0, change=0),
                autoscaling.ScalingInterval(lower=1, upper=5, change=1),
                autoscaling.ScalingInterval(lower=6, upper=20, change=3),
                autoscaling.ScalingInterval(lower=21, upper=50, change=6),
                autoscaling.ScalingInterval(lower=51, change=min(12, cfg.worker_max_capacity)),
            ],
            adjustment_type=autoscaling.AdjustmentType.EXACT_CAPACITY,
            cooldown=Duration.minutes(2),  # fast scale-out
            estimated_instance_warmup=Duration.seconds(90),  # time for instance to be ready
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "AsgName", value=self.asg.auto_scaling_group_name)

"""
config.py — Per-environment configuration for the pyvar CDK project.

Reasoning:
- A single dataclass drives all stack parameters.
- Switching environments is a single --context env=prod flag.
- Keeping sizing/capacity outside the stack code means stacks
  are readable policies, not a mix of logic and constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PyvarConfig:
    env_name: str
    account: str
    region: str = "eu-west-1"  # Dublin — closest to EU financial market data

    # ── Domain ────────────────────────────────────────────────────────────────
    domain_name: str = "pyvar.com"
    hosted_zone_id: str = ""  # fill in after creating the zone
    certificate_arn: str = ""  # ACM cert in us-east-1 for CloudFront

    # ── VPC ───────────────────────────────────────────────────────────────────
    vpc_max_azs: int = 2
    vpc_nat_gateways: int = 1  # 1 NAT GW saves ~£27/month vs 2 (no HA tradeoff for non-prod)

    # ── ECS Fargate (FastAPI) ─────────────────────────────────────────────────
    api_cpu: int = 512  # 0.5 vCPU — API is I/O-bound, not CPU-bound
    api_memory_mb: int = 1024
    api_min_tasks: int = 2  # 1 per AZ for HA
    api_max_tasks: int = 10
    api_image_tag: str = "latest"

    # ── EC2 Spot ASG (Celery workers) ─────────────────────────────────────────
    worker_instance_type: str = (
        "c5.xlarge"  # 4 vCPU, 8GB — compute-optimised, better Spot availability
    )
    worker_min_capacity: int = 0  # scale to zero when idle
    worker_max_capacity: int = 20
    worker_spot_max_price: str = "0.11"  # on-demand ~$0.17/hr — cap at ~65%, above c5.xlarge market
    ami_s3_logging: bool = False  # enable once pyvar-{env}-build-logs S3 bucket exists (P7)
    worker_use_spot: bool = (
        True  # False = on-demand only (Option B: guaranteed capacity, higher cost)
    )
    # Hypothesis C: pre-baked worker AMI (pyvar-dev-ami Image Builder pipeline).
    # When set, ComputeStack uses this AMI and skips the runtime pip install —
    # dependencies + Numba cache are already baked, so cold start drops to <90s.
    # Empty string = Hypothesis B (stock AL2023 + git clone + pip install at boot).
    worker_ami_id: str = ""

    # ── Aurora Serverless v2 ──────────────────────────────────────────────────
    aurora_min_acu: float = 0.5  # minimum — ~$45/month; 0 would need Aurora SV2 pause
    aurora_max_acu: float = 8.0  # scales to handle batch audit log writes

    # ── ElastiCache Serverless ────────────────────────────────────────────────
    cache_max_ecpu_per_second: int = 5_000  # cap to prevent runaway costs

    # ── S3 ────────────────────────────────────────────────────────────────────
    result_retention_days: int = 90  # delete old Parquet results after 90 days

    # ── SQS ───────────────────────────────────────────────────────────────────
    queue_visibility_timeout_seconds: int = 60  # must exceed max simulation runtime
    queue_dlq_max_receive_count: int = 3  # retry 3 times before DLQ

    # ── Scaling thresholds (SQS messages → desired workers) ──────────────────
    scale_steps: list = field(
        default_factory=lambda: [
            # (lower, upper, desired_workers)
            (0, 0, 0),
            (1, 5, 1),
            (6, 20, 3),
            (21, 50, 6),
            (51, None, 12),
        ]
    )

    @classmethod
    def for_env(cls, env_name: str, account: str = "") -> "PyvarConfig":
        base = dict(env_name=env_name, account=account or "347228921290")
        overrides = {
            "dev": dict(
                vpc_nat_gateways=1,
                api_min_tasks=1,
                api_max_tasks=3,
                worker_max_capacity=5,
                aurora_min_acu=0.5,
                aurora_max_acu=2.0,
                result_retention_days=14,
                # Option B: set worker_use_spot=False for guaranteed on-demand capacity
                # Option C: override worker_instance_type e.g. "t3.xlarge" for different quota pool
            ),
            "staging": dict(
                api_min_tasks=2,
                worker_max_capacity=10,
            ),
            "prod": dict(
                vpc_nat_gateways=2,  # 2 NAT GWs for full AZ independence
                api_min_tasks=2,
                api_max_tasks=20,
                worker_max_capacity=20,
                aurora_min_acu=1.0,
                aurora_max_acu=16.0,
                result_retention_days=365,  # compliance retention
            ),
        }
        return cls(**{**base, **overrides.get(env_name, {})})

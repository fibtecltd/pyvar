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

    # SES EmailIdentity domain. Defaults to the bare domain (dev already
    # verified this one — see ses_stack.py). SES allows only one identity
    # per literal domain per account+region, so any other environment that
    # also runs SesStack needs a distinct value (prod override below) or its
    # deploy fails with "EmailIdentity ... already exists".
    ses_domain_name: str = "pyvar.com"

    # CloudFront alternate domain names (aliases) for EdgeStack's distribution.
    # Defaults to the bare domain + www — this is what dev's distribution
    # serves today (the live pyvar.com / www.pyvar.com traffic) and must not
    # change. CloudFront enforces alias uniqueness account-wide, not per
    # distribution, so no other environment's distribution can also claim
    # these same aliases until a deliberate domain cutover happens (tracked
    # separately — see prod override below, which claims none at all).
    edge_domain_names: list[str] = field(default_factory=lambda: ["pyvar.com", "www.pyvar.com"])

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
    worker_use_spot: bool = (
        True  # False = on-demand only (Option B: guaranteed capacity, higher cost)
    )
    worker_ami_id: str = "ami-053d838c9735b7a03"  # Hypothesis C — baked AMI (P6), version 1.0.251
    worker_use_baked_ami: bool = (
        False  # False = Hypothesis B (stock AL2023, runtime pip install).
        # True = Hypothesis C — dynamically looks up the latest pyvar-{env}-worker-*
        # AMI produced by the Image Builder pipeline. No AMI ID to maintain here.
    )
    ami_s3_logging: bool = False  # gate until pyvar-{env}-build-logs bucket exists (P7)

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
    def for_env(
        cls, env_name: str, account: str = "", api_image_tag: str | None = None
    ) -> "PyvarConfig":
        base = dict(env_name=env_name, account=account or "347228921290")
        if api_image_tag:
            # #119: pipeline_stack.py's Synth step resolves this to the
            # short git SHA it just built and pushed, so the ECS task
            # definition's image reference actually changes between
            # deploys instead of staying pinned to the base "latest"
            # default below (which never triggers a CloudFormation diff,
            # so ECS never redeploys — the bug this override exists to fix).
            base["api_image_tag"] = api_image_tag
        overrides = {
            "dev": dict(
                vpc_nat_gateways=1,
                api_min_tasks=1,
                api_max_tasks=3,
                worker_max_capacity=5,
                aurora_min_acu=0.5,
                aurora_max_acu=2.0,
                result_retention_days=14,
                worker_use_baked_ami=True,  # AMI pipeline live — use baked AMI (P6)
                # Option B: set worker_use_spot=False for guaranteed on-demand capacity
                # Option C: override worker_instance_type e.g. "t3.xlarge" for different quota pool
                # Domain cutover Stage C: pyvar.com/www.pyvar.com move to prod
                # (see prod override below and docs/domain-cutover-stage-b-c-plan.md).
                # Stage B (above, historical) gave dev dev.pyvar.com as an
                # ADDITIONAL alias alongside the live pyvar.com/www.pyvar.com
                # specifically so dev could give those two up now without
                # losing its own stable domain. dev.pyvar.com is the only
                # alias dev keeps. This DOES replace the inline-created cert
                # (edge_domain_names[0] becomes the cert's primary domain_name,
                # "pyvar.com" -> "dev.pyvar.com" -- ACM certs are immutable
                # w.r.t. their domain list) -- but dev.pyvar.com's DNS
                # validation CNAME is already on file at Aruba from Stage B,
                # so this is expected to validate near-instantly with no new
                # manual DNS action, same as prod's out-of-band cert reusing
                # its own already-present validation records.
                edge_domain_names=["dev.pyvar.com"],
            ),
            "staging": dict(
                api_min_tasks=2,
                worker_max_capacity=10,
                # Same alias-collision reasoning as prod above: pyvar.com/
                # www.pyvar.com are already claimed account-wide by dev's live
                # CloudFront distribution, so no other environment can claim
                # them too. Without this override, deploying pyvar-staging-edge
                # would hit the exact same ACM cert / distribution collision
                # the prod override exists to avoid.
                edge_domain_names=[],
            ),
            "prod": dict(
                vpc_nat_gateways=2,  # 2 NAT GWs for full AZ independence
                api_min_tasks=2,
                api_max_tasks=20,
                # worker_min_capacity intentionally omitted -- base class
                # default of 0 (scale-to-zero) applies. PR #227/#228 had
                # temporarily set this to 1 as a launch-window mitigation for
                # the Day -3 smoke test's 401.5s cold-start finding (SQS's
                # ApproximateNumberOfMessagesVisible alarm sitting in
                # INSUFFICIENT_DATA on an idle queue). Task #38's root-cause
                # fix (compute_stack.py's ScaleFromZero policy now watches a
                # custom pyvar/job-submitted-{env} metric published by
                # api/routes/var.py at submission time, bypassing SQS's own
                # CloudWatch pipeline entirely) was verified live against
                # prod on 2026-08-15: scaled the ASG to 0, submitted a real
                # job, instance InService at t+63s, job succeeded at t+145s
                # end-to-end (vs. 401.5s before) -- reverted here now that the
                # mitigation is no longer needed.
                worker_max_capacity=20,
                aurora_min_acu=1.0,
                aurora_max_acu=16.0,
                result_retention_days=365,  # compliance retention
                ses_domain_name="mail.pyvar.com",  # bare domain already owned by dev's SES identity
                # Domain cutover Stage C (live cutover): pyvar.com/www.pyvar.com
                # move here from dev now that dev has its own dev.pyvar.com
                # (Stage B, above). Bare-apex alias kept for parity with dev's
                # historical setup, per explicit confirmation — costs nothing
                # extra and the cert already covers it; Aruba's own forwarding
                # proxy handles the real apex redirect independently of
                # CloudFront either way (see docs/domain-cutover-stage-b-c-plan.md).
                edge_domain_names=["pyvar.com", "www.pyvar.com"],
                # Pre-validated out-of-band cert (docs/domain-cutover-stage-b-c-plan.md,
                # "Cert strategy — resolved"), imported by ARN instead of created
                # inline (edge_stack.py's cfg.certificate_arn branch, PR #237) --
                # decouples DNS validation timing from this live cutover window
                # entirely, since it was already ISSUED well ahead of time.
                certificate_arn="arn:aws:acm:us-east-1:347228921290:certificate/a18950da-05cc-49fa-81d9-78828e512f3e",
                worker_use_baked_ami=True,  # CLAUDE.md §11: "in production, pre-bake AMI"
                # PRECONDITION — not yet automated (no post-deploy trigger wires up
                # AmiStack's pipeline, see pipeline_stack.py): before the next `cdk
                # deploy --context env=prod`, a pyvar-prod-worker-* AMI must already
                # exist, or compute_stack.py's ec2.MachineImage.lookup(...) fails at
                # synth time. Trigger it manually first:
                #   aws imagebuilder start-image-pipeline-execution \
                #     --image-pipeline-arn <pyvar-prod-worker-pipeline ARN>
                # and wait for it to complete (check the Image Builder console or
                # CloudWatch Logs /aws/imagebuilder/pyvar-prod-worker) before deploying.
            ),
        }
        return cls(**{**base, **overrides.get(env_name, {})})

"""
app.py — Updated CDK application entry point with pipeline and AMI stacks.

Deploy order:
  1. Bootstrap (once per account/region):
       cdk bootstrap aws://ACCOUNT/eu-west-1 aws://ACCOUNT/us-east-1

  2. Deploy pipeline (self-manages everything after this):
       cdk deploy pyvar-pipeline --context account=ACCOUNT

  3. Push to main — pipeline handles all subsequent deploys automatically.

  To deploy application stacks directly (dev only, bypass pipeline):
       cdk deploy pyvar-dev-* --context env=dev --context account=ACCOUNT --all
"""

import aws_cdk as cdk
from stacks.alb_waf_stack import AlbWafStack
from stacks.alerts_stack import AlertsStack
from stacks.ami_stack import AmiStack
from stacks.api_stack import ApiStack
from stacks.compute_stack import ComputeStack
from stacks.data_stack import DataStack
from stacks.edge_stack import EdgeStack
from stacks.local_package_stack import LocalPackageStack
from stacks.network_stack import NetworkStack
from stacks.observability_stack import ObservabilityStack
from stacks.pipeline_stack import PipelineStack
from stacks.public_data_stack import PublicDataStack
from stacks.queue_stack import QueueStack
from stacks.ses_events_stack import SesEventsStack
from stacks.ses_stack import SesStack

from config import PyvarConfig

app = cdk.App()

env_name = app.node.try_get_context("env") or "dev"
account = app.node.try_get_context("account") or ""
cfg = PyvarConfig.for_env(env_name, account=account)

env_primary = cdk.Environment(account=cfg.account, region=cfg.region)
env_edge = cdk.Environment(account=cfg.account, region="us-east-1")

prefix = f"pyvar-{env_name}"

# ── CI/CD Pipeline (deploys itself and all app stacks) ───────────────────────
# Deploy this stack once manually; it takes over from there.
pipeline = PipelineStack(
    app,
    "pyvar-pipeline",
    cfg=cfg,
    env=env_primary,
    description="pyvar: CodePipeline CI/CD — self-mutating, deploys dev + prod",
)

# ── AMI baking pipeline (pre-compiles Numba for Spot workers) ────────────────
ami = AmiStack(
    app,
    f"{prefix}-ami",
    cfg=cfg,
    env=env_primary,
    description="pyvar: EC2 Image Builder — pre-baked Numba worker AMI",
)

# ── Local-package build pipeline (manually triggered, never on push) ─────────
local_package = LocalPackageStack(
    app,
    f"{prefix}-local-package",
    cfg=cfg,
    env=env_primary,
    description="pyvar: manually-triggered pyvar Local build + GitHub Release publish",
)

# ── Application stacks (managed by pipeline in normal operation) ─────────────
# These can also be deployed directly for local dev iteration.
network = NetworkStack(
    app,
    f"{prefix}-network",
    cfg=cfg,
    env=env_primary,
    description="pyvar: VPC, subnets, security groups, VPC endpoints",
)

data = DataStack(
    app,
    f"{prefix}-data",
    cfg=cfg,
    vpc=network.vpc,
    sgs=network.sgs,
    env=env_primary,
    description="pyvar: Aurora SV2, ElastiCache Serverless, S3",
)

queue = QueueStack(
    app,
    f"{prefix}-queue",
    cfg=cfg,
    env=env_primary,
    description="pyvar: SQS FIFO job queue + DLQ + CloudWatch alarms",
)

compute = ComputeStack(
    app,
    f"{prefix}-compute",
    cfg=cfg,
    vpc=network.vpc,
    sgs=network.sgs,
    var_queue=queue.var_queue,
    dlq=queue.dlq,
    data=data,
    env=env_primary,
    description="pyvar: EC2 Spot ASG Celery workers + step scaling",
)

ses_events = SesEventsStack(
    app,
    f"{prefix}-ses-events",
    cfg=cfg,
    env=env_primary,
    description="pyvar: SES bounce/complaint SNS topic + suppression Lambda",
)

ses = SesStack(
    app,
    f"{prefix}-ses",
    cfg=cfg,
    configuration_set=ses_events.configuration_set,
    env=env_primary,
    description="pyvar: SES domain identity for transactional email (#149)",
)
ses.add_dependency(ses_events)

api = ApiStack(
    app,
    f"{prefix}-api",
    cfg=cfg,
    vpc=network.vpc,
    sgs=network.sgs,
    var_queue=queue.var_queue,
    data=data,
    ses_identity=ses.email_identity,
    configuration_set=ses_events.configuration_set,
    env=env_primary,
    description="pyvar: ECS Fargate FastAPI + ALB + auto-scaling",
)

edge = EdgeStack(
    app,
    f"{prefix}-edge",
    cfg=cfg,
    alb_dns=api.alb_dns_name,
    origin_verify_secret=api.origin_verify_secret,
    env=env_edge,
    description="pyvar: CloudFront + WAF + Route53 (us-east-1)",
)

public_data = PublicDataStack(
    app,
    f"{prefix}-public-data",
    cfg=cfg,
    jwt_secret=api.jwt_secret,
    # eu-west-1, alongside api/data/compute — see public_data_stack.py
    # module docstring (data residency: no S3 origin/replica may sit in
    # the us-east-1 edge region).
    env=env_primary,
    description="pyvar: status.json + demo-result.json publisher (P8 Task 1/2)",
)

alb_waf = AlbWafStack(
    app,
    f"{prefix}-alb-waf",
    cfg=cfg,
    alb=api.alb,
    env=env_primary,
    description="pyvar: Regional WAF on ALB — Option 1 fallback (no CloudFront)",
)

alerts = AlertsStack(
    app,
    f"{prefix}-alerts",
    cfg=cfg,
    api=api,
    compute=compute,
    ses_events=ses_events,
    env=env_primary,
    description="pyvar: SNS alerts topic + CloudWatch alarms + monthly cost budget",
)

observability = ObservabilityStack(
    app,
    f"{prefix}-observability",
    cfg=cfg,
    api=api,
    env=env_primary,
    description="pyvar: CloudWatch operational dashboard (pyvar-{env}-overview)",
)

# Dependency declarations
data.add_dependency(network)
queue.add_dependency(network)
compute.add_dependency(data)
compute.add_dependency(queue)
api.add_dependency(data)
api.add_dependency(queue)
api.add_dependency(ses)
api.add_dependency(ses_events)  # references ses_events.configuration_set for SendEmail grant
edge.add_dependency(api)
public_data.add_dependency(api)  # references api.jwt_secret
alb_waf.add_dependency(api)
alerts.add_dependency(api)  # references api.alb for latency/5xx alarms
alerts.add_dependency(compute)  # references compute.worker_error_metric for worker alarm
alerts.add_dependency(ses_events)  # references ses_events.suppression_metric for SES alarm
observability.add_dependency(api)  # references api.alb for dashboard ALB widgets

cdk.Tags.of(app).add("Project", "pyvar")
cdk.Tags.of(app).add("Environment", env_name)
cdk.Tags.of(app).add("ManagedBy", "cdk")
cdk.Tags.of(app).add("Owner", "fibtec-limited")

app.synth()

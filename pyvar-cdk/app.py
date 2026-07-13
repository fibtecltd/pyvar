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
from stacks.network_stack import NetworkStack
from stacks.pipeline_stack import PipelineStack
from stacks.queue_stack import QueueStack

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

api = ApiStack(
    app,
    f"{prefix}-api",
    cfg=cfg,
    vpc=network.vpc,
    sgs=network.sgs,
    var_queue=queue.var_queue,
    data=data,
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
    env=env_primary,
    description="pyvar: SNS alerts topic + CloudWatch alarms + monthly cost budget",
)

# Dependency declarations
data.add_dependency(network)
queue.add_dependency(network)
compute.add_dependency(data)
compute.add_dependency(queue)
api.add_dependency(data)
api.add_dependency(queue)
edge.add_dependency(api)
alb_waf.add_dependency(api)
alerts.add_dependency(api)  # references api.alb for latency/5xx alarms

cdk.Tags.of(app).add("Project", "pyvar")
cdk.Tags.of(app).add("Environment", env_name)
cdk.Tags.of(app).add("ManagedBy", "cdk")
cdk.Tags.of(app).add("Owner", "fibtec-limited")

app.synth()

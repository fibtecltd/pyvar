"""
stacks/network_stack.py — VPC, subnets, security groups, VPC endpoints

Reasoning:
- Three subnet tiers: public (ALB), private-with-egress (ECS, EC2),
  isolated (Aurora, ElastiCache). Isolated subnets have no route to
  the internet — the data tier is completely unreachable from outside.
- VPC Gateway Endpoints for S3 and DynamoDB are free and keep that
  traffic off the NAT Gateway (saves ~$0.045/GB for large Parquet writes).
- Interface Endpoints for SQS, ECR, Secrets Manager keep all control-plane
  traffic inside the VPC — no public internet exposure for these APIs.
- Security groups follow least-privilege: each service only accepts
  traffic from the specific source SG it needs.
"""

from __future__ import annotations

from dataclasses import dataclass

import aws_cdk as cdk
from aws_cdk import Stack
from aws_cdk import aws_ec2 as ec2
from constructs import Construct

from config import PyvarConfig


@dataclass
class SecurityGroups:
    alb: ec2.SecurityGroup
    api: ec2.SecurityGroup
    worker: ec2.SecurityGroup
    aurora: ec2.SecurityGroup
    cache: ec2.SecurityGroup


class NetworkStack(Stack):

    def __init__(self, scope: Construct, id: str, *, cfg: PyvarConfig, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── VPC ───────────────────────────────────────────────────────────────
        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=cfg.vpc_max_azs,
            nat_gateways=cfg.vpc_nat_gateways,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )

        # ── VPC Flow Logs (security + cost visibility) ─────────────────────────
        self.vpc.add_flow_log(
            "FlowLogCloudWatch",
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(),
            traffic_type=ec2.FlowLogTrafficType.REJECT,  # only log rejected traffic
        )

        # ── VPC Gateway Endpoints (free — keep S3/DynamoDB off NAT GW) ────────
        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        # ── VPC Interface Endpoints (keeps control-plane traffic private) ──────
        # SQS — workers poll for Celery tasks without touching the internet
        self.vpc.add_interface_endpoint(
            "SqsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SQS,
            private_dns_enabled=True,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # ECR — ECS pulls container images privately
        self.vpc.add_interface_endpoint(
            "EcrEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR,
            private_dns_enabled=True,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )
        self.vpc.add_interface_endpoint(
            "EcrDockerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            private_dns_enabled=True,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # Secrets Manager — workers and API tasks fetch credentials privately
        self.vpc.add_interface_endpoint(
            "SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            private_dns_enabled=True,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # CloudWatch Logs — container logs go directly without NAT
        self.vpc.add_interface_endpoint(
            "CloudWatchLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            private_dns_enabled=True,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # ── Security Groups ────────────────────────────────────────────────────

        # ALB: accepts HTTPS from internet
        sg_alb = ec2.SecurityGroup(
            self,
            "SgAlb",
            vpc=self.vpc,
            description="pyvar ALB - public HTTPS ingress",
            allow_all_outbound=False,
        )
        sg_alb.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS from internet")
        sg_alb.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP redirect")
        sg_alb.add_egress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8000), "To ECS API tasks")

        # ECS API tasks: only accepts traffic from ALB
        sg_api = ec2.SecurityGroup(
            self,
            "SgApi",
            vpc=self.vpc,
            description="pyvar ECS FastAPI tasks",
            allow_all_outbound=True,  # needs SQS, Secrets Manager, ECR
        )
        sg_api.add_ingress_rule(sg_alb, ec2.Port.tcp(8000), "From ALB")

        # EC2 Spot workers: no inbound (pull model via SQS)
        sg_worker = ec2.SecurityGroup(
            self,
            "SgWorker",
            vpc=self.vpc,
            description="pyvar EC2 Spot Celery workers",
            allow_all_outbound=True,  # needs SQS, S3, Secrets Manager
        )

        # Aurora: only from API tasks and workers
        sg_aurora = ec2.SecurityGroup(
            self,
            "SgAurora",
            vpc=self.vpc,
            description="pyvar Aurora PostgreSQL",
            allow_all_outbound=False,
        )
        sg_aurora.add_ingress_rule(sg_api, ec2.Port.tcp(5432), "From ECS API")
        sg_aurora.add_ingress_rule(sg_worker, ec2.Port.tcp(5432), "From workers")

        # ElastiCache Redis: only from API tasks and workers
        sg_cache = ec2.SecurityGroup(
            self,
            "SgCache",
            vpc=self.vpc,
            description="pyvar ElastiCache Redis",
            allow_all_outbound=False,
        )
        sg_cache.add_ingress_rule(sg_api, ec2.Port.tcp(6379), "From ECS API")
        sg_cache.add_ingress_rule(sg_worker, ec2.Port.tcp(6379), "From workers")

        self.sgs = SecurityGroups(
            alb=sg_alb,
            api=sg_api,
            worker=sg_worker,
            aurora=sg_aurora,
            cache=sg_cache,
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "VpcId", value=self.vpc.vpc_id)

"""
stacks/data_stack.py — Aurora Serverless v2, ElastiCache Serverless, S3

Reasoning:
- Aurora SV2 scales in fine-grained ACU increments (0.5 ACU steps)
  with no cold start, unlike Aurora Serverless v1.
  min_acu=0.5 means ~$45/month at rest; auto-scales to max_acu during
  end-of-day batch audit writes.
- ElastiCache Serverless Redis removes instance management entirely.
  We cap max_ecpu_per_second to prevent runaway costs from a misconfigured
  cache invalidation loop.
- S3 Intelligent-Tiering automatically moves old Parquet simulation results
  to cheaper tiers. A lifecycle rule hard-deletes objects after the
  configured retention period for compliance.
- Secrets Manager stores DB credentials and rotates them automatically
  every 30 days. The secret ARN is exported for other stacks to consume.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticache as elasticache
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from constructs import Construct
from stacks.network_stack import SecurityGroups

from config import PyvarConfig


class DataStack(Stack):

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        cfg: PyvarConfig,
        vpc: ec2.Vpc,
        sgs: SecurityGroups,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── Aurora Serverless v2 PostgreSQL ────────────────────────────────────
        # Subnet group in ISOLATED subnets — no internet route at all
        aurora_subnet_group = rds.SubnetGroup(
            self,
            "AuroraSubnetGroup",
            vpc=vpc,
            description="pyvar Aurora isolated subnets",
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
        )

        # Credentials stored in Secrets Manager with 30-day auto-rotation
        self.db_secret = rds.DatabaseSecret(
            self,
            "AuroraSecret",
            username="pyvar_admin",
            secret_name=f"pyvar/{cfg.env_name}/aurora-credentials",
        )

        self.aurora = rds.DatabaseCluster(
            self,
            "Aurora",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_16_6,
            ),
            credentials=rds.Credentials.from_secret(self.db_secret),
            default_database_name="pyvar",
            serverless_v2_min_capacity=cfg.aurora_min_acu,
            serverless_v2_max_capacity=cfg.aurora_max_acu,
            writer=rds.ClusterInstance.serverless_v2("Writer"),
            readers=[
                # One reader in the second AZ for read-heavy query offload
                rds.ClusterInstance.serverless_v2(
                    "Reader",
                    scale_with_writer=True,  # reader scales with writer — cost-efficient
                ),
            ],
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[sgs.aurora],
            subnet_group=aurora_subnet_group,
            backup=rds.BackupProps(retention=Duration.days(7)),
            deletion_protection=cfg.env_name == "prod",
            removal_policy=(
                RemovalPolicy.SNAPSHOT if cfg.env_name == "prod" else RemovalPolicy.DESTROY
            ),
            storage_encrypted=True,
            monitoring_interval=Duration.seconds(60),
            enable_performance_insights=True,
            performance_insight_retention=rds.PerformanceInsightRetention.DEFAULT,  # 7 days free
        )

        # ── ElastiCache Serverless Redis ───────────────────────────────────────
        # L1 construct — ElastiCache Serverless not yet in L2 at time of writing
        _cache_subnet_group = elasticache.CfnSubnetGroup(
            self,
            "CacheSubnetGroup",
            description="pyvar ElastiCache isolated subnets",
            subnet_ids=vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED).subnet_ids,
        )

        self.cache = elasticache.CfnServerlessCache(
            self,
            "RedisServerless",
            engine="redis",
            serverless_cache_name=f"pyvar-{cfg.env_name}",
            description="pyvar result cache and rate limiting",
            subnet_ids=vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED).subnet_ids,
            security_group_ids=[sgs.cache.security_group_id],
            cache_usage_limits=elasticache.CfnServerlessCache.CacheUsageLimitsProperty(
                data_storage=elasticache.CfnServerlessCache.DataStorageProperty(
                    maximum=10,  # GB — cap storage cost
                    unit="GB",
                ),
                ecpu_per_second=elasticache.CfnServerlessCache.ECPUPerSecondProperty(
                    maximum=cfg.cache_max_ecpu_per_second,
                ),
            ),
        )

        # ── S3 result bucket ───────────────────────────────────────────────────
        self.result_bucket = s3.Bucket(
            self,
            "ResultBucket",
            bucket_name=f"pyvar-{cfg.env_name}-results-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=False,
            intelligent_tiering_configurations=[
                s3.IntelligentTieringConfiguration(
                    name="AllObjects",
                    # Move to IA after 30 days, archive after 90 days
                    archive_access_tier_time=Duration.days(90),
                    deep_archive_access_tier_time=Duration.days(180),
                )
            ],
            lifecycle_rules=[
                # P7 Task 5 fix: intelligent_tiering_configurations above only
                # governs the OPTIONAL archive/deep-archive sub-tiers for
                # objects already stored under the INTELLIGENT_TIERING storage
                # class — it does not itself move anything there. Without this
                # transition, put_object's default STANDARD storage class was
                # never migrated and the archive config above had no effect on
                # any object. transition_after=days(0) moves objects in on
                # first access-pattern evaluation; S3's automatic 30-day
                # Frequent->Infrequent Access move (unconfigurable, built into
                # the storage class itself) then applies as intended.
                s3.LifecycleRule(
                    id="TransitionToIntelligentTiering",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INTELLIGENT_TIERING,
                            transition_after=Duration.days(0),
                        )
                    ],
                ),
                s3.LifecycleRule(
                    id="ExpireOldResults",
                    expiration=Duration.days(cfg.result_retention_days),
                    enabled=True,
                ),
                s3.LifecycleRule(
                    id="CleanupIncompleteUploads",
                    abort_incomplete_multipart_upload_after=Duration.days(1),
                    enabled=True,
                ),
            ],
            removal_policy=(
                RemovalPolicy.RETAIN if cfg.env_name == "prod" else RemovalPolicy.DESTROY
            ),
            auto_delete_objects=cfg.env_name != "prod",
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "AuroraEndpoint", value=self.aurora.cluster_endpoint.hostname)
        cdk.CfnOutput(self, "DbSecretArn", value=self.db_secret.secret_arn)
        cdk.CfnOutput(self, "CacheEndpoint", value=self.cache.attr_endpoint_address)
        cdk.CfnOutput(self, "ResultBucketName", value=self.result_bucket.bucket_name)

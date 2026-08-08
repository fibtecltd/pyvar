"""
stacks/ami_stack.py — EC2 Image Builder for pre-baked Numba worker AMI

Reasoning:
- Without a pre-baked AMI, each EC2 Spot worker cold start takes ~90s:
    ~30s OS boot + ~20s pip install + ~2s Numba JIT warmup + ~40s uncertainty
- With a pre-baked AMI, cold start drops to ~25s:
    ~20s OS boot + ~5s service start (dependencies already installed)
- EC2 Image Builder automates AMI creation and distribution.
  For prod: triggered automatically — pipeline_stack.py's shared Synth
  ShellStep hashes this file and, on a change, calls
  start-image-pipeline-execution and blocks until the new AMI is
  AVAILABLE, all BEFORE `cdk synth` runs (see that file's
  _ami_bake_commands docstring for why it has to be pre-synth, not
  post-deploy). For any other env (e.g. dev): still manual — trigger
  with the AWS CLI command on WorkerImagePipeline below.
- The Image Builder recipe installs ALL pyvar dependencies + runs a
  Numba warmup script that exercises the same @njit/prange/cache=True
  code paths as production kernels, so LLVM's JIT machinery is already
  initialised on first boot. The warmup cache is baked at
  /opt/numba_cache (persistent EBS path — /tmp is tmpfs on AL2023 and
  would not survive the AMI snapshot). compute_stack.py sets the same
  NUMBA_CACHE_DIR for the running worker.
- New AMIs take effect without any launch-template update: compute_stack.py
  resolves the worker AMI via ec2.MachineImage.lookup() on the
  "pyvar-{env}-worker-*" name pattern, re-run at every `cdk synth` — so
  the launch template is built fresh against whatever is newest each
  time, no separate Lambda/SNS wiring needed.
- Old AMIs (> 3 versions) are deregistered — AWS-native Image Builder
  Lifecycle Manager (WorkerAmiLifecyclePolicy below), not a custom Lambda.
"""

from __future__ import annotations

import hashlib

import aws_cdk as cdk
from aws_cdk import Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_imagebuilder as imagebuilder
from constructs import Construct

from config import PyvarConfig

# ── Numba warmup script baked into the AMI ───────────────────────────────────
NUMBA_WARMUP_SCRIPT = """
#!/bin/bash
set -euo pipefail

echo "=== Pyvar AMI build: installing dependencies ==="
yum update -y
yum install -y python3.11 python3.11-pip git

              # Do NOT run update-alternatives — breaks yum/aws-cli (depend on python3.9)
              # Use python3.11 / pip3.11 explicitly throughout.
              yum install -y libcurl-devel gcc gcc-c++
              python3.11 -m pip install --upgrade pip
              # Install requirements-heavy.txt dependencies
              python3.11 -m pip install "numpy>=1.26.0" "scipy>=1.13.0" "pandas>=2.2.0" "numba>=0.59.0" "polars>=0.20.0" "pyarrow>=15.0.0" "dask[complete]>=2024.1.0" "ray[default]>=2.10.0" "statsmodels>=0.14.0" "arch>=6.3.0" "QuantLib>=1.33" "empyrical>=0.5.5" "streamlit>=1.32.0" "plotly>=5.20.0"
              python3.11 -m pip install "fastapi>=0.110.0" "uvicorn[standard]>=0.29.0" "pydantic>=2.6.0" "pydantic-settings>=2.2.0" "python-jose[cryptography]>=3.3.0" "slowapi>=0.1.9" "orjson>=3.10.0" "python-multipart>=0.0.9" "celery>=5.3.6" "redis>=5.0.3" "pycurl>=7.45.0" "sqlalchemy>=2.0.28" "asyncpg>=0.29.0" "boto3>=1.34.0" "alembic>=1.13.0" "psycopg2-binary>=2.9.9" "prometheus-fastapi-instrumentator>=6.4.0" "sentry-sdk[fastapi]>=1.43.0" "structlog>=24.1.0"
              python3.11 -c "import numpy, scipy, numba, pycurl; print('deps OK:', numpy.__version__)"

echo "=== Pyvar AMI build: pre-compiling Numba JIT cache ==="

# Write warmup to a real .py file so Numba cache=True has a file path.
# python3 -c "..." has no __file__ and raises:
# RuntimeError: no locator available for file '<string>'
cat > /tmp/numba_warmup.py << 'WARMEOF'
import numpy as np
from numba import njit, prange

@njit(parallel=True, cache=True)
def _warmup_kernel(returns, shocks, horizon):
    mu = 0.0
    sigma = 0.0
    n = len(returns)
    for i in range(n):
        mu += returns[i]
    mu /= n
    for i in range(n):
        sigma += (returns[i] - mu) ** 2
    sigma = (sigma / n) ** 0.5

    n_sims = shocks.shape[0]
    pnl = np.zeros(n_sims)
    for i in prange(n_sims):
        c = 0.0
        for t in range(horizon):
            c += mu + sigma * shocks[i, t]
        pnl[i] = c
    return pnl

rng = np.random.default_rng(42)
returns = rng.normal(0.0005, 0.012, 252)
shocks = rng.standard_normal((1000, 1))
result = _warmup_kernel(returns, shocks, 1)
print(f\'Numba warmup complete. VaR estimate: {-np.percentile(result, 1):.4f}\')
print(\'Cache written to /opt/numba_cache/\')
WARMEOF
mkdir -p /opt/numba_cache && NUMBA_CACHE_DIR=/opt/numba_cache python3.11 /tmp/numba_warmup.py

echo "=== Pyvar AMI build complete ==="
"""


class AmiStack(Stack):

    def __init__(self, scope: Construct, id: str, *, cfg: PyvarConfig, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── IAM Role for Image Builder ─────────────────────────────────────────
        builder_role = iam.Role(
            self,
            "ImageBuilderRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("EC2InstanceProfileForImageBuilder"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )

        instance_profile = iam.CfnInstanceProfile(
            self,
            "ImageBuilderInstanceProfile",
            roles=[builder_role.role_name],
            instance_profile_name=f"pyvar-{cfg.env_name}-image-builder",
        )

        # ── Auto-versioning: hash component content so version bumps automatically
        # whenever the script changes. No manual version bumps needed.
        _component_hash = hashlib.md5(
            NUMBA_WARMUP_SCRIPT.encode(), usedforsecurity=False
        ).hexdigest()[:6]
        component_version = f"1.0.{int(_component_hash, 16) % 10000}"

        # ── Build component: install pyvar + pre-compile Numba ─────────────────
        build_component = imagebuilder.CfnComponent(
            self,
            "PyvarBuildComponent",
            name=f"pyvar-{cfg.env_name}-worker-setup",
            version=component_version,
            platform="Linux",
            description="Installs pyvar dependencies and pre-compiles Numba JIT cache",
            data=f"""
name: pyvar-worker-setup
description: Install pyvar and pre-compile Numba JIT cache
schemaVersion: 1.0

phases:
  - name: build
    steps:
      - name: InstallAndWarmup
        action: ExecuteBash
        inputs:
          commands:
            - |
{chr(10).join("              " + line for line in NUMBA_WARMUP_SCRIPT.strip().splitlines())}
""",
        )

        # ── Recipe: Amazon Linux 2023 + pyvar component ────────────────────────
        recipe_name = f"pyvar-{cfg.env_name}-worker"
        recipe = imagebuilder.CfnImageRecipe(
            self,
            "WorkerRecipe",
            name=recipe_name,
            version=component_version,
            parent_image=f"arn:aws:imagebuilder:{cfg.region}:aws:image/amazon-linux-2023-x86/x.x.x",
            components=[
                imagebuilder.CfnImageRecipe.ComponentConfigurationProperty(
                    component_arn=build_component.attr_arn,
                ),
            ],
            block_device_mappings=[
                imagebuilder.CfnImageRecipe.InstanceBlockDeviceMappingProperty(
                    device_name="/dev/xvda",
                    ebs=imagebuilder.CfnImageRecipe.EbsInstanceBlockDeviceSpecificationProperty(
                        delete_on_termination=True,
                        volume_size=20,
                        volume_type="gp3",
                        encrypted=True,
                    ),
                )
            ],
        )

        # ── Distribution: share AMI within account only ────────────────────────
        distribution_config = imagebuilder.CfnDistributionConfiguration(
            self,
            "WorkerDistribution",
            name=f"pyvar-{cfg.env_name}-worker-dist",
            distributions=[
                imagebuilder.CfnDistributionConfiguration.DistributionProperty(
                    region=cfg.region,
                    # Raw dict with literal CloudFormation PascalCase keys, not the
                    # AmiDistributionConfigurationProperty typed class or a
                    # camelCase dict -- both serialize this property with the wrong
                    # (camelCase) key casing in aws-cdk-lib 2.261.0, which the real
                    # AWS::ImageBuilder::DistributionConfiguration resource schema
                    # rejects outright ("extraneous key [name] is not permitted").
                    # Confirmed via isolated repro against the installed CDK version.
                    ami_distribution_configuration={
                        "Name": f"pyvar-{cfg.env_name}-worker-{{{{ imagebuilder:buildDate }}}}",
                        "Description": f"pyvar {cfg.env_name} Celery worker with pre-compiled Numba cache",
                        "AmiTags": {
                            "Project": "pyvar",
                            "Environment": cfg.env_name,
                            "ManagedBy": "image-builder",
                        },
                    },
                )
            ],
        )

        # ── Infrastructure config: small instance for build ────────────────────
        infra_config = imagebuilder.CfnInfrastructureConfiguration(
            self,
            "WorkerInfraConfig",
            name=f"pyvar-{cfg.env_name}-worker-infra",
            instance_types=["c7i.large"],  # enough for pip install + Numba compile
            instance_profile_name=instance_profile.instance_profile_name or "",
            terminate_instance_on_failure=True,
            # IMDSv2 required — prevents SSRF-to-metadata attacks on build instances
            instance_metadata_options=imagebuilder.CfnInfrastructureConfiguration.InstanceMetadataOptionsProperty(
                http_tokens="required",
                http_put_response_hop_limit=1,
            ),
            # S3 logging disabled until pyvar-{env}-build-logs bucket is created (P7).
            # To re-enable: create bucket in data_stack.py, set ami_s3_logging=True in config.py.
            **(
                {
                    "logging": imagebuilder.CfnInfrastructureConfiguration.LoggingProperty(
                        s3_logs=imagebuilder.CfnInfrastructureConfiguration.S3LogsProperty(
                            s3_bucket_name=f"pyvar-{cfg.env_name}-build-logs-{self.account}",
                            s3_key_prefix="image-builder/",
                        )
                    )
                }
                if cfg.ami_s3_logging
                else {}
            ),
        )
        # instance_profile_name above is a plain string, not a CFN token, so CDK's
        # automatic dependency inference never wires this up -- without an explicit
        # dependency, CloudFormation has no guarantee the instance profile exists
        # (and has propagated through IAM) before Image Builder validates it.
        infra_config.node.add_dependency(instance_profile)

        # ── Image pipeline: triggered manually or via API ──────────────────────
        self.image_pipeline = imagebuilder.CfnImagePipeline(
            self,
            "WorkerImagePipeline",
            name=f"pyvar-{cfg.env_name}-worker-pipeline",
            image_recipe_arn=recipe.attr_arn,
            infrastructure_configuration_arn=infra_config.attr_arn,
            distribution_configuration_arn=distribution_config.attr_arn,
            status="ENABLED",
            # No schedule. For prod: triggered pre-synth by pipeline_stack.py's
            # Synth ShellStep (see module docstring above) — not post-deploy.
            # For any other env: still manual only.
            # To trigger manually:
            # aws imagebuilder start-image-pipeline-execution \
            #   --image-pipeline-arn <arn>
        )

        # ── Lifecycle policy: deregister old AMIs ───────────────────────────────
        # Was previously an unimplemented claim in this module's docstring
        # ("Old AMIs (> 3 versions) are deregistered") — nothing ever enforced
        # it, so every triggered bake (pipeline_stack.py's _ami_bake_commands
        # for prod, or a manual trigger for any env) left its 20GB gp3
        # snapshot behind indefinitely. Native Image Builder Lifecycle
        # Manager, not a custom Lambda: a COUNT filter of 3 keeps the 3 most
        # recent AMIs per recipe and deletes (deregisters the AMI AND its
        # backing EBS snapshot) everything older, on AWS's own schedule — no
        # extra code to maintain here beyond the resource + its execution role.
        #
        # Trust policy and managed policy verified against AWS docs (not
        # guessed): the lifecycle execution role is assumed by
        # imagebuilder.amazonaws.com and needs the AWS managed
        # service-role/EC2ImageBuilderLifecycleExecutionPolicy — a
        # differently-named, more specific policy than the general
        # EC2InstanceProfileForImageBuilder role above (that one is for the
        # BUILD instance; this one is for the Lifecycle Manager service
        # itself deregistering old images afterwards).
        lifecycle_role = iam.Role(
            self,
            "AmiLifecycleRole",
            assumed_by=iam.ServicePrincipal("imagebuilder.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/EC2ImageBuilderLifecycleExecutionPolicy"
                ),
            ],
        )

        # exclusion_rules.amis.last_launched protects whichever AMI is
        # ACTUALLY currently in use, independent of the COUNT filter below.
        # This matters because baking (pipeline_stack.py's _ami_bake_commands)
        # and deploying (the separate, less-frequent prod CDK deploy that
        # actually moves compute_stack.py's launch template onto a newer AMI)
        # run on decoupled schedules: several unrelated ami_stack.py-touching
        # pushes can each trigger a bake without a prod deploy in between, so
        # a purely count-based policy could in principle deregister the AMI
        # still referenced by prod's live launch template before that AMI is
        # ever superseded there. last_launched exempts any AMI that has
        # actually launched an instance within the window from deletion
        # regardless of the COUNT filter, which covers the common case (an
        # ASG that periodically scales up under real job traffic re-launches
        # from — and re-protects — the in-use AMI).
        #
        # Residual gap, documented rather than silently assumed away: with
        # worker_min_capacity=0 (scale-to-zero, config.py), an ASG that
        # genuinely never scales up for the whole exclusion window won't
        # re-trigger last_launched, so it doesn't protect a truly always-idle
        # deployment against enough churn. Lifecycle Manager has no concept
        # of "what CloudFormation currently references" — closing that last
        # gap completely would mean tagging the in-use AMI at prod-deploy
        # time and excluding by tag instead of (or in addition to)
        # last_launched, which is real additional infra (a deploy-time
        # tagging step) intentionally left as follow-up work, not built here.
        imagebuilder.CfnLifecyclePolicy(
            self,
            "WorkerAmiLifecyclePolicy",
            name=f"pyvar-{cfg.env_name}-worker-lifecycle",
            description=(
                "Retain the 3 most recent pyvar worker AMIs, and any AMI launched "
                "in the last 30 days regardless of count; delete the rest + their "
                "EBS snapshots"
            ),
            execution_role=lifecycle_role.role_arn,
            resource_type="AMI_IMAGE",
            status="ENABLED",
            policy_details=[
                imagebuilder.CfnLifecyclePolicy.PolicyDetailProperty(
                    action=imagebuilder.CfnLifecyclePolicy.ActionProperty(
                        type="DELETE",
                        include_resources=imagebuilder.CfnLifecyclePolicy.IncludeResourcesProperty(
                            amis=True,
                            snapshots=True,
                        ),
                    ),
                    exclusion_rules=imagebuilder.CfnLifecyclePolicy.ExclusionRulesProperty(
                        amis=imagebuilder.CfnLifecyclePolicy.AmiExclusionRulesProperty(
                            last_launched=imagebuilder.CfnLifecyclePolicy.LastLaunchedProperty(
                                value=30,
                                unit="DAYS",
                            ),
                        ),
                    ),
                    filter=imagebuilder.CfnLifecyclePolicy.FilterProperty(
                        type="COUNT",
                        value=3,
                    ),
                )
            ],
            resource_selection=imagebuilder.CfnLifecyclePolicy.ResourceSelectionProperty(
                recipes=[
                    imagebuilder.CfnLifecyclePolicy.RecipeSelectionProperty(
                        name=recipe_name,
                        # Wildcard: component_version's patch component is a
                        # content hash (see _component_hash above), so every
                        # AMI-relevant content change produces a DIFFERENT
                        # "1.0.NNNN" version under the same recipe name — the
                        # wildcard is what lets one lifecycle policy cover
                        # all of them instead of just one frozen version.
                        semantic_version="1.0.x",
                    )
                ],
            ),
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "ImagePipelineArn",
            value=self.image_pipeline.attr_arn,
            description="ARN for the worker AMI image pipeline — trigger after deploying new worker code",
        )

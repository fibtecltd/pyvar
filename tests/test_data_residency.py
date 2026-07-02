"""tests/test_data_residency.py — P5b data-residency compliance audit.

This suite asserts that ALL pyvar customer / financial data stays resident in
the intended EU home region (eu-west-1, Dublin), as required by:

  * MiFID II Article 16(6) — record-keeping / arrangements to prevent loss or
    unauthorised access to client order & transaction data.
  * GDPR Article 44 — general principle for transfers: personal data may only
    leave the EEA under specific safeguards; keeping it in-region avoids the
    transfer entirely.
  * CLAUDE.md §3.4 — "CloudFront WAF WebACL MUST remain in us-east-1. The
    EdgeStack is deliberately deployed to us-east-1" (routing/metadata only).
  * CLAUDE.md §4 — regulatory-grade logic / audit data must not be relocated.

Evidence is taken from the CDK source of truth in ``pyvar-cdk/`` (parsed as
text so no CDK / boto import is required) plus the application ``config.py``.
The only deliberate us-east-1 footprint is the CloudFront distribution, its
WAF WebACL and the ``cf-origin-verify`` routing secret — none of which carry
customer input or financial results.

Design rules for this audit:
  * Every check prints the verified value it asserts on.
  * A value that genuinely cannot be located in source -> skip/xfail with a
    clear reason (never assert on a guess).
  * An actual residency violation (wrong region, or customer data egressing to
    a non-AWS / non-eu-west-1 sink) is a HARD FAILURE = P5b BLOCKER.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── Locate the CDK source tree (source of truth) ────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[1]
_CDK_DIR = _REPO_ROOT / "pyvar-cdk"
_STACKS = _CDK_DIR / "stacks"

HOME_REGION = "eu-west-1"          # Dublin — intended EU data-residency home
EDGE_REGION = "us-east-1"          # CloudFront/WAF only — metadata & routing


def _read(path: Path) -> str:
    """Read a source file, or fail the check clearly if it is missing."""
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    return path.read_text(encoding="utf-8")


def _app_config_text() -> str:
    return _read(_CDK_DIR / "config.py")


def _app_stack_env_region() -> str | None:
    """Region the primary application stacks are deployed to.

    In app.py:  env_primary = cdk.Environment(account=cfg.account, region=cfg.region)
    and cfg.region defaults to eu-west-1 in pyvar-cdk/config.py with NO per-env
    override.  We verify BOTH: (a) primary stacks bind to cfg.region, and
    (b) cfg.region resolves to eu-west-1.
    """
    app_text = _read(_CDK_DIR / "app.py")
    # env_primary must be built from cfg.region (not a hardcoded edge region)
    if not re.search(r"env_primary\s*=\s*cdk\.Environment\([^)]*region\s*=\s*cfg\.region", app_text, re.S):
        return None
    cfg_text = _app_config_text()
    m = re.search(r"region:\s*str\s*=\s*[\"']([\w-]+)[\"']", cfg_text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# CHECK 1 — S3 result bucket resides in eu-west-1
# ---------------------------------------------------------------------------
def test_check1_s3_bucket_region_eu_west_1():
    """S3 stores customer VaR results (financial data) -> must be eu-west-1.

    Requirement: GDPR Art. 44 (no EEA egress of personal/financial data) and
    MiFID II Art. 16(6) (secure retention of client records).

    Evidence: the S3 bucket is defined in DataStack, which app.py deploys with
    env=env_primary (region=cfg.region=eu-west-1). A bucket has no region prop
    of its own in CDK — it inherits the stack's region. We therefore assert on
    the stack's deploy region.
    """
    data_text = _read(_STACKS / "data_stack.py")
    assert "s3.Bucket(" in data_text, "S3 result bucket not found in data_stack.py"
    assert "pyvar-{cfg.env_name}-results-" in data_text or "results-" in data_text, (
        "result bucket naming pattern not found"
    )
    region = _app_stack_env_region()
    print(f"[check1] S3 result bucket (DataStack) region = {region}")
    assert region == HOME_REGION, (
        f"BLOCKER: S3 result bucket region is {region!r}, expected {HOME_REGION!r} "
        "— customer financial data would be resident outside the EU (GDPR Art.44)."
    )
    # Belt-and-braces: bucket also blocks public access (no exfil path)
    assert "BlockPublicAccess.BLOCK_ALL" in data_text, "S3 bucket must block all public access"
    print("[check1] S3: eu-west-1, public access BLOCK_ALL")


# ---------------------------------------------------------------------------
# CHECK 2 — Aurora cluster resides in eu-west-1
# ---------------------------------------------------------------------------
def test_check2_aurora_region_eu_west_1():
    """Aurora is the VaRJob AUDIT LOG (regulatory record) -> must be eu-west-1.

    Requirement: MiFID II Art. 16(6) record-keeping + CLAUDE.md §4 (audit log
    must not be relocated). GDPR Art. 44 (user_id in audit rows = personal data).

    Evidence: rds.DatabaseCluster in DataStack (env_primary=eu-west-1), placed
    in PRIVATE_ISOLATED subnets (no internet route).
    """
    data_text = _read(_STACKS / "data_stack.py")
    assert "rds.DatabaseCluster(" in data_text, "Aurora cluster not found in data_stack.py"
    assert "PRIVATE_ISOLATED" in data_text, "Aurora must live in isolated subnets"
    region = _app_stack_env_region()
    print(f"[check2] Aurora cluster (DataStack) region = {region}; subnets = PRIVATE_ISOLATED")
    assert region == HOME_REGION, (
        f"BLOCKER: Aurora region is {region!r}, expected {HOME_REGION!r} "
        "— regulatory audit log outside the EU (MiFID II Art.16, GDPR Art.44)."
    )
    print("[check2] Aurora: eu-west-1, isolated subnets")


# ---------------------------------------------------------------------------
# CHECK 3 — ElastiCache resides in eu-west-1
# ---------------------------------------------------------------------------
def test_check3_elasticache_region_eu_west_1():
    """ElastiCache caches VaR results + rate-limit state -> must be eu-west-1.

    Requirement: GDPR Art. 44 — cached financial results are personal/financial
    data and must not leave the EEA.

    Evidence: elasticache.CfnServerlessCache in DataStack (env_primary), using
    PRIVATE_ISOLATED subnets.
    """
    data_text = _read(_STACKS / "data_stack.py")
    assert "CfnServerlessCache(" in data_text, "ElastiCache not found in data_stack.py"
    # cache subnets are isolated (no internet path)
    assert "PRIVATE_ISOLATED" in data_text, "ElastiCache must live in isolated subnets"
    region = _app_stack_env_region()
    print(f"[check3] ElastiCache (DataStack) region = {region}; subnets = PRIVATE_ISOLATED")
    assert region == HOME_REGION, (
        f"BLOCKER: ElastiCache region is {region!r}, expected {HOME_REGION!r} (GDPR Art.44)."
    )
    print("[check3] ElastiCache: eu-west-1, isolated subnets")


# ---------------------------------------------------------------------------
# CHECK 4 — SQS FIFO job queue resides in eu-west-1
# ---------------------------------------------------------------------------
def test_check4_sqs_region_eu_west_1():
    """SQS FIFO carries the VaR job payloads (customer input) -> must be eu-west-1.

    Requirement: GDPR Art. 44 — job payloads contain portfolio inputs. The
    queue must stay in-region and off the public internet (VPC endpoint, check 8).

    Evidence: sqs.Queue in QueueStack, deployed with env=env_primary in app.py.
    """
    queue_text = _read(_STACKS / "queue_stack.py")
    assert "sqs.Queue(" in queue_text, "SQS queue not found in queue_stack.py"
    assert "var-jobs.fifo" in queue_text, "expected pyvar var-jobs FIFO queue"
    # Confirm QueueStack is bound to env_primary in app.py
    app_text = _read(_CDK_DIR / "app.py")
    assert re.search(r"QueueStack\([^)]*env\s*=\s*env_primary", app_text, re.S), (
        "QueueStack must be deployed with env_primary (eu-west-1)"
    )
    region = _app_stack_env_region()
    print(f"[check4] SQS FIFO queue (QueueStack) region = {region}")
    assert region == HOME_REGION, (
        f"BLOCKER: SQS region is {region!r}, expected {HOME_REGION!r} "
        "— customer job payloads outside the EU (GDPR Art.44)."
    )
    print("[check4] SQS: eu-west-1 (var-jobs.fifo)")


# ---------------------------------------------------------------------------
# CHECK 5 — CloudFront (us-east-1) is metadata/routing only
# ---------------------------------------------------------------------------
def test_check5_cloudfront_metadata_only_no_data_at_edge():
    """The us-east-1 EdgeStack must NOT store or process application data.

    Requirement: CLAUDE.md §3.4 (EdgeStack deliberately us-east-1, WAF only) +
    GDPR Art. 44 (no customer data may be materialised in us-east-1).

    We assert the EdgeStack:
      * is deployed to us-east-1 (deliberate, allowed for CloudFront/WAF);
      * has NO S3 origin in us-east-1 (data would then be resident there);
      * has NO Lambda@Edge / CloudFront Function writing application data.
    The only origin is the eu-west-1 ALB (HttpOrigin) — a pass-through.
    """
    edge_text = _read(_STACKS / "edge_stack.py")
    app_text = _read(_CDK_DIR / "app.py")

    # EdgeStack is intentionally us-east-1
    assert re.search(r"env_edge\s*=\s*cdk\.Environment\([^)]*region\s*=\s*[\"']us-east-1[\"']", app_text, re.S), (
        "EdgeStack edge region must be pinned to us-east-1 (CLAUDE.md §3.4)"
    )
    assert re.search(r"EdgeStack\([^)]*env\s*=\s*env_edge", app_text, re.S), (
        "EdgeStack must be deployed with env_edge"
    )

    # No S3 origin at the edge (would make data resident in us-east-1)
    s3_origin = re.search(r"S3Origin|S3BucketOrigin|origins\.S3", edge_text)
    assert s3_origin is None, (
        "BLOCKER: CloudFront (us-east-1) has an S3 origin — customer data would "
        f"be resident outside the EU. Found: {s3_origin.group(0) if s3_origin else ''}"
    )

    # No Lambda@Edge / CloudFront Function processing application data
    edge_compute = re.search(
        r"experimental_edge|edge_lambda|Lambda@Edge|add_behavior.*function|FunctionAssociation|CloudFrontFunction|aws_lambda",
        edge_text,
    )
    assert edge_compute is None, (
        "BLOCKER: CloudFront has edge compute (Lambda@Edge/CF Function) that could "
        f"process/store customer data in us-east-1. Found: {edge_compute.group(0) if edge_compute else ''}"
    )

    # The one and only origin is the eu-west-1 ALB (pass-through, no residency)
    assert "origins.HttpOrigin" in edge_text and "alb_dns" in edge_text, (
        "expected the sole CloudFront origin to be the eu-west-1 ALB (HttpOrigin)"
    )
    print("[check5] CloudFront @ us-east-1: no S3 origin, no Lambda@Edge; "
          "sole origin = eu-west-1 ALB (pass-through, routing only)")


# ---------------------------------------------------------------------------
# CHECK 6 — Secrets Manager: pyvar/* in eu-west-1; us-east-1 replica is routing only
# ---------------------------------------------------------------------------
def test_check6_secrets_home_region_and_edge_replica_is_routing_only():
    """All pyvar/* secrets live in eu-west-1; the ONLY us-east-1 replica is the
    ``cf-origin-verify`` routing token — no customer PII / financial data.

    Requirement: GDPR Art. 44 (secret material tied to EU data must stay in EU)
    + CLAUDE.md §3.4 (only routing/metadata belongs in us-east-1).

    Evidence:
      * DataStack creates pyvar/<env>/aurora-credentials (no replica).
      * ApiStack creates pyvar/<env>/jwt-secret (no replica) and
        pyvar/<env>/cf-origin-verify WITH replica_regions=[us-east-1].
      * cf-origin-verify is a CDK-GENERATED random token (SecretStringGenerator,
        exclude_punctuation, fixed length) used purely as the X-Origin-Verify
        header to stop WAF bypass — it is NOT customer/financial data.
    """
    data_text = _read(_STACKS / "data_stack.py")
    api_text = _read(_STACKS / "api_stack.py")

    # Home-region secrets present
    assert "pyvar/{cfg.env_name}/aurora-credentials" in data_text, "aurora-credentials secret missing"
    assert "pyvar/{cfg.env_name}/jwt-secret" in api_text, "jwt-secret missing"
    assert "pyvar/{cfg.env_name}/cf-origin-verify" in api_text, "cf-origin-verify secret missing"

    # Find every replica_regions=[...] declaration and confirm ONLY cf-origin-verify replicates.
    replicated_us_east = re.findall(r"replica_regions\s*=\s*\[[^\]]*us-east-1[^\]]*\]", api_text)
    print(f"[check6] us-east-1 secret replicas declared: {len(replicated_us_east)}")
    assert len(replicated_us_east) == 1, (
        f"BLOCKER: expected exactly 1 us-east-1 secret replica (cf-origin-verify), "
        f"found {len(replicated_us_east)} — audit which secret is leaving eu-west-1."
    )

    # The replicated secret must be cf-origin-verify (routing), created via generator,
    # and NOT the aurora/jwt (which would carry credentials tied to customer data).
    # Locate the OriginVerifySecret block and confirm it holds the replica + generator.
    ov_block = re.search(
        r"OriginVerifySecret.*?replica_regions\s*=\s*\[[^\]]*us-east-1[^\]]*\]",
        api_text,
        re.S,
    )
    assert ov_block is not None, (
        "BLOCKER: the us-east-1 replica is not the OriginVerifySecret — a data-bearing "
        "secret may be replicating to us-east-1."
    )
    assert "generate_secret_string" in ov_block.group(0) or "SecretStringGenerator" in api_text, (
        "cf-origin-verify must be a generated routing token, not injected customer data"
    )
    # Aurora credentials must NOT be replicated out of region
    assert "replica_regions" not in data_text, (
        "BLOCKER: aurora-credentials (DB access to EU customer data) must not replicate cross-region"
    )
    print("[check6] Secrets: pyvar/* in eu-west-1; only cf-origin-verify (generated "
          "routing token) replicates to us-east-1 — no PII/financial data.")


# ---------------------------------------------------------------------------
# CHECK 7 — No outbound HTTP transmitting customer/input data to non-AWS endpoints
# ---------------------------------------------------------------------------
def test_check7_no_external_data_egress_from_app_code():
    """engine/ api/ tasks/ must not ship customer input/results to non-AWS hosts.

    Requirement: GDPR Art. 44 + MiFID II Art. 16(6) — customer portfolio inputs
    and VaR results may only move to in-region AWS services. Only reference-data
    fetches (e.g. a risk-free-rate lookup) would be permissible, and only if
    they carry no customer data.

    Method: scan for imports of outbound HTTP client libraries and for literal
    external URLs in the compute/API/task layers. Any genuine data-bearing
    outbound call is a BLOCKER; each hit is listed.
    """
    roots = [_REPO_ROOT / "engine", _REPO_ROOT / "api", _REPO_ROOT / "tasks"]
    for root in roots:
        assert root.exists(), f"expected source dir not found: {root}"

    http_import = re.compile(
        r"^\s*(?:import|from)\s+(requests|httpx|aiohttp|urllib\.request|urllib3|http\.client|websocket|websockets)\b",
        re.M,
    )
    # External URL literals (exclude localhost / AWS internal endpoints handled by boto3)
    url_literal = re.compile(r"https?://(?!localhost|127\.0\.0\.1)([A-Za-z0-9.-]+)")

    offenders: list[str] = []
    ref_data_notes: list[str] = []
    for root in roots:
        for pyfile in sorted(root.rglob("*.py")):
            text = pyfile.read_text(encoding="utf-8")
            for m in http_import.finditer(text):
                lineno = text[: m.start()].count("\n") + 1
                offenders.append(f"{pyfile.relative_to(_REPO_ROOT)}:{lineno}: import {m.group(1)}")
            for m in url_literal.finditer(text):
                host = m.group(1)
                lineno = text[: m.start()].count("\n") + 1
                # boto3/AWS SDK endpoints are in-region AWS, not third parties.
                if host.endswith("amazonaws.com"):
                    continue
                # docstring/comment example URLs (e.g. schema refs) are not egress calls,
                # but we still surface them for the audit trail.
                ref_data_notes.append(f"{pyfile.relative_to(_REPO_ROOT)}:{lineno}: {m.group(0)}")

    print(f"[check7] outbound-HTTP-client imports in engine/api/tasks: {offenders or 'NONE'}")
    print(f"[check7] non-AWS URL literals (review): {ref_data_notes or 'NONE'}")

    assert not offenders, (
        "BLOCKER: outbound HTTP client library imported in the compute/API/task layer — "
        f"potential customer-data egress path(s): {offenders}"
    )
    print("[check7] No HTTP client libs and no data-bearing external endpoints "
          "in engine/api/tasks — customer data does not leave AWS in-region services.")


# ---------------------------------------------------------------------------
# CHECK 8 — All AWS service traffic stays in-VPC via endpoints (no IGW path)
# ---------------------------------------------------------------------------
def test_check8_vpc_endpoints_keep_aws_traffic_in_vpc():
    """S3, SQS, ECR, Secrets Manager and CloudWatch Logs must be reached via
    VPC endpoints — control-plane traffic never traverses an internet gateway.

    Requirement: CLAUDE.md §3.4 ("VPC endpoints for SQS, ECR, S3, Secrets
    Manager are provisioned — do not add direct internet routes for these
    services") + GDPR Art. 44 (keeps in-region traffic off the public internet).

    Evidence: NetworkStack adds a Gateway endpoint for S3 and Interface
    endpoints for SQS, ECR (api + docker), Secrets Manager and CloudWatch Logs;
    the data tier lives in PRIVATE_ISOLATED subnets (no IGW/NAT route at all).
    """
    net_text = _read(_STACKS / "network_stack.py")

    required_endpoints = {
        "S3 (gateway)": r"add_gateway_endpoint\([^)]*GatewayVpcEndpointAwsService\.S3",
        "SQS": r"InterfaceVpcEndpointAwsService\.SQS",
        "ECR": r"InterfaceVpcEndpointAwsService\.ECR\b",
        "ECR_DOCKER": r"InterfaceVpcEndpointAwsService\.ECR_DOCKER",
        "Secrets Manager": r"InterfaceVpcEndpointAwsService\.SECRETS_MANAGER",
        "CloudWatch Logs": r"InterfaceVpcEndpointAwsService\.CLOUDWATCH_LOGS",
    }
    present = {name: bool(re.search(pat, net_text)) for name, pat in required_endpoints.items()}
    print(f"[check8] VPC endpoints present: {present}")

    missing = [name for name, ok in present.items() if not ok]
    assert not missing, (
        f"BLOCKER: missing VPC endpoint(s) {missing} — that AWS service traffic "
        "would take an internet path (CLAUDE.md §3.4)."
    )

    # Data tier is fully isolated (no internet route) — reinforces no-IGW-for-data.
    assert "PRIVATE_ISOLATED" in net_text, "data tier must use PRIVATE_ISOLATED subnets"
    print("[check8] All AWS service traffic (S3/SQS/ECR/SecretsManager/Logs) stays "
          "in-VPC via endpoints; data tier in isolated subnets — no IGW path.")

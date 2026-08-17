"""
lambda/public_data_publisher/handler.py — status.json + demo-result.json publisher

Reasoning:
- One Lambda serves both P8 Task 1 (Option B: pre-computed, periodically
  refreshed terminal demo) and P8 Task 2 (live status indicator) because they
  share the same trigger cadence, the same public S3 bucket, and the same
  "poll something operational, write a small public JSON file" shape — two
  near-identical Lambdas would just double the schedule/IAM/cold-start
  surface for no benefit.
- No third-party dependencies (no requests, no python-jose): this is deployed
  as a plain zip asset with zero bundling step. HS256 JWT signing is
  hand-rolled with stdlib hmac/hashlib/base64 — it produces a token
  byte-for-byte compatible with python-jose's HS256 output, since JWT
  verification only re-hashes the received "header.payload" string, never the
  original claim dict.
- Calls hit the public CloudFront domain — the exact same call a browser
  makes — not the ALB directly. There's no longer a reason to bypass
  CloudFront (this Lambda lives in eu-west-1, same region as everything else,
  see public_data_stack.py's module docstring for why), so this needs nothing
  beyond the JWT: no origin-verify header, no ALB DNS. The domain comes from
  API_BASE_URL (env var, set per-environment by public_data_stack.py from
  cfg.api_base_url) -- was a hardcoded dev-only literal until task #41 found
  it made every environment's Lambda call dev's API regardless of which
  environment it ran in, which failed outright for prod (see API_BASE_URL's
  own comment below for the full mechanism).
- Compute workers scale to zero (worker_min_capacity=0, config.py). A demo
  refresh can therefore hit a cold Spot ASG scale-up (~1-3 min) if no worker
  is currently running. This is accepted deliberately: the schedule is 15
  minutes (public_data_stack.py), the Lambda timeout is 5 minutes to absorb
  it, and a timed-out cycle leaves the previous demo-result.json in place
  rather than overwriting it with a failure — the portal always shows the
  last *real* result, never a synthetic fallback.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

ENV_NAME = os.environ["ENV_NAME"]
PUBLIC_BUCKET = os.environ["PUBLIC_BUCKET"]
JWT_SECRET_ARN = os.environ["JWT_SECRET_ARN"]

# task #41 -- was a hardcoded literal (dev's CloudFront domain,
# unconditionally) until every environment's own Lambda called DEV's API
# regardless of which environment it ran in. Prod's calls failed outright
# with 401: the JWT this Lambda signs is verified against whichever
# environment actually receives the request, and dev/prod have deliberately
# separate JWT secrets (confirmed via distinct Secrets Manager ARNs), so a
# prod-signed token sent to dev's API is a guaranteed signature mismatch.
# Now set per-environment by public_data_stack.py from cfg.api_base_url
# (config.py) -- see that field's own comment for the full story.
API_BASE_URL = os.environ["API_BASE_URL"]

secretsmanager = boto3.client("secretsmanager")
cloudwatch = boto3.client("cloudwatch")  # alarms live in this Lambda's own region
s3 = boto3.client("s3")

ALARM_NAMES = [
    f"pyvar-{ENV_NAME}-api-latency-p95",
    f"pyvar-{ENV_NAME}-api-5xx",
    f"pyvar-{ENV_NAME}-worker-errors",
]

# Fixed synthetic daily log-returns for the homepage demo (60 obs, ~1.8% daily
# vol) — deterministic so the *shape* of the demo input is stable run-to-run;
# only the VaR/CVaR/runtime numbers in the published JSON change, and they
# always come from a real compute run against this fixed series.
DEMO_RETURNS: list[float] = [
    0.0041, -0.0128, 0.0056, -0.0203, 0.0089, -0.0034, 0.0112, -0.0067,
    0.0023, -0.0145, 0.0078, -0.0019, 0.0034, -0.0087, 0.0156, -0.0042,
    0.0009, -0.0176, 0.0063, -0.0028, 0.0091, -0.0114, 0.0047, -0.0059,
    0.0128, -0.0033, 0.0016, -0.0092, 0.0074, -0.0151, 0.0038, -0.0021,
    0.0105, -0.0068, 0.0029, -0.0184, 0.0053, -0.0011, 0.0087, -0.0126,
    0.0042, -0.0037, 0.0119, -0.0079, 0.0025, -0.0163, 0.0061, -0.0044,
    0.0098, -0.0102, 0.0033, -0.0018, 0.0071, -0.0139, 0.0046, -0.0026,
    0.0113, -0.0084, 0.0031, -0.0057,
]  # fmt: skip

DEMO_PAYLOAD: dict[str, Any] = {
    "portfolio_value": 1_000_000.0,
    "returns": DEMO_RETURNS,
    "confidence_level": 0.99,
    "horizon_days": 1,
    "n_simulations": 1_000,
    "seed": 42,
}

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 270  # 4.5 min — stays inside the 5 min Lambda timeout


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign_service_jwt(secret: str) -> str:
    """Hand-rolled HS256 JWT — see module docstring for why.

    tier="internal" (not "free"): this Lambda calls POST /var/compute every
    15 minutes (96x/day) to refresh demo-result.json. Under the tier-based
    rate limiting added in #146, a "free" tier claim would exhaust the
    free-tier daily quota in ~2.5 hours and silently stop the demo from
    refreshing. api/middleware/auth.py::TokenPayload and
    api/middleware/rate_limit.py both recognise "internal" as an unlimited,
    unthrottled tier — kept distinct from "enterprise" so this scheduled
    job's calls don't pollute real customer-tier usage analytics.
    """
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    claims = {
        "sub": "internal-demo-publisher",
        "tier": "internal",
        "exp": int(expire.timestamp()),
    }
    payload = _b64url(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(signature)}"


def _get_secret(secret_arn: str) -> str:
    return secretsmanager.get_secret_value(SecretId=secret_arn)["SecretString"]


def _api_request(
    method: str,
    path: str,
    token: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{API_BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(
        req, timeout=15
    ) as resp:  # nosec B310  # fixed, hardcoded API domain
        return json.loads(resp.read())


def publish_status() -> dict[str, Any]:
    resp = cloudwatch.describe_alarms(AlarmNames=ALARM_NAMES)
    states = {a["AlarmName"]: a["StateValue"] for a in resp.get("MetricAlarms", [])}
    alarm_count = sum(1 for v in states.values() if v == "ALARM")

    if alarm_count == 0:
        overall = "operational"
    elif alarm_count == 1:
        overall = "degraded"
    else:
        overall = "down"

    status = {
        "status": overall,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "alarms": states,
    }
    s3.put_object(
        Bucket=PUBLIC_BUCKET,
        Key="public/status.json",
        Body=json.dumps(status).encode(),
        ContentType="application/json",
        CacheControl="public, max-age=60",
    )
    return status


def publish_demo_result(jwt_secret: str) -> dict[str, Any] | None:
    token = _sign_service_jwt(jwt_secret)
    started = time.monotonic()

    submit = _api_request("POST", "/api/v1/var/compute", token, DEMO_PAYLOAD)
    task_id = submit["task_id"]

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    result_body = None
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        polled = _api_request("GET", f"/api/v1/var/result/{task_id}", token)
        if polled["status"] == "success":
            result_body = polled["result"]
            break
        if polled["status"] == "failure":
            return None  # leave the previous good demo-result.json in place

    if result_body is None:
        return None  # timed out (likely cold Spot scale-up) — skip this cycle

    runtime_ms = int((time.monotonic() - started) * 1000)
    demo = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "request": {
            "portfolio_value": DEMO_PAYLOAD["portfolio_value"],
            "confidence_level": DEMO_PAYLOAD["confidence_level"],
            "horizon_days": DEMO_PAYLOAD["horizon_days"],
            "n_simulations": DEMO_PAYLOAD["n_simulations"],
        },
        "result": {
            "var_abs": result_body["var_abs"],
            "var_pct": result_body["var_pct"],
            "cvar_abs": result_body["cvar_abs"],
            "cvar_pct": result_body["cvar_pct"],
            "mu": result_body["mu"],
            "sigma": result_body["sigma"],
        },
        "runtime_ms": runtime_ms,
    }
    s3.put_object(
        Bucket=PUBLIC_BUCKET,
        Key="public/demo-result.json",
        Body=json.dumps(demo).encode(),
        ContentType="application/json",
        CacheControl="public, max-age=60",
    )
    return demo


def handler(event, context):  # noqa: ANN001, ANN201 — Lambda entrypoint signature is fixed
    status = publish_status()

    demo = None
    try:
        jwt_secret = _get_secret(JWT_SECRET_ARN)
        demo = publish_demo_result(jwt_secret)
    except (urllib.error.URLError, KeyError, OSError) as exc:
        # Best-effort: a failed demo refresh must never fail the whole
        # invocation — status.json (the operationally important artifact)
        # has already been written above.
        print(f"demo-result publish failed, keeping previous result: {exc}")

    return {"status": status["status"], "demo_published": demo is not None}

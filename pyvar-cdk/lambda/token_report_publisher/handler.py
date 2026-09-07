"""
lambda/token_report_publisher/handler.py — daily JWT-issuance email report

Reasoning:
- Scheduled once per environment (stacks/token_report_stack.py, 07:00 UTC),
  same shape as public_data_publisher and ses_suppression_handler: no VPC
  attachment, no direct DB access. Calls the API's own
  GET /internal/token-report (api/routes/internal.py) over the public
  CloudFront domain, the exact same call a browser makes, and lets the
  ECS task's existing DB connection do the real work — see either of those
  Lambdas' own module docstrings for why this shape (hand-rolled HS256 JWT,
  API_BASE_URL env var) is used instead of a VPC-attached Lambda with its
  own DB credentials.
- Deliberately two separate per-environment emails, not one combined
  dev+prod email: dev and prod are fully isolated (separate VPCs, separate
  SES identities per ses_stack.py — pyvar.com for dev, mail.pyvar.com for
  prod, split apart after sharing one identity broke prod's first deploy).
  Combining into one email would mean building this codebase's first
  cross-environment shared stack; not worth it for a daily count.
- Source address is f"reports@{SES_DOMAIN}" (SES_DOMAIN = cfg.ses_domain_name,
  same value api_stack.py uses to build SES_SENDER_EMAIL) — a domain
  identity can send from any local part, so this doesn't need its own
  identity or DNS record, just the existing per-env one.
- No error swallowing here (unlike public_data_publisher's demo-refresh,
  which deliberately keeps the previous good result on failure): this
  Lambda does exactly one thing per invocation, so a real failure should
  raise and surface as a Lambda error / CloudWatch metric rather than
  silently skip a day's report.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.request import Request, urlopen

import boto3

ENV_NAME = os.environ["ENV_NAME"]
JWT_SECRET_ARN = os.environ["JWT_SECRET_ARN"]
API_BASE_URL = os.environ["API_BASE_URL"]
SES_DOMAIN = os.environ["SES_DOMAIN"]
NOTIFICATION_RECIPIENT = os.environ["NOTIFICATION_RECIPIENT"]

SENDER_EMAIL = f"reports@{SES_DOMAIN}"

secretsmanager = boto3.client("secretsmanager")
ses = boto3.client("ses")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign_service_jwt(secret: str) -> str:
    """Hand-rolled HS256 JWT — see module docstring for why (copied verbatim
    from ses_suppression_handler/public_data_publisher's own helper)."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    claims = {
        "sub": "internal-token-report-publisher",
        "tier": "internal",
        "exp": int(expire.timestamp()),
    }
    payload = _b64url(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(signature)}"


def _get_secret(secret_arn: str) -> str:
    return secretsmanager.get_secret_value(SecretId=secret_arn)["SecretString"]


def _fetch_token_report(token: str) -> dict[str, Any]:
    url = f"{API_BASE_URL}/api/v1/internal/token-report"
    req = Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    with urlopen(req, timeout=15) as resp:  # nosec B310  # fixed, hardcoded API domain
        return json.loads(resp.read())


def _send_report_email(report: dict[str, Any]) -> None:
    subject = f"[{ENV_NAME}] pyvar daily token report — {report['date']}"
    body = (
        f"pyvar daily JWT-issuance report — {ENV_NAME}\n"
        f"Date: {report['date']}\n\n"
        f"Tokens issued today: {report['issued_today']}\n"
        f"Tokens issued cumulative (since inception): {report['issued_cumulative']}\n"
    )
    ses.send_email(
        Source=SENDER_EMAIL,
        Destination={"ToAddresses": [NOTIFICATION_RECIPIENT]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body}},
        },
    )


def handler(event, context):  # noqa: ANN001, ANN201 — Lambda entrypoint signature is fixed
    jwt_secret = _get_secret(JWT_SECRET_ARN)
    token = _sign_service_jwt(jwt_secret)
    report = _fetch_token_report(token)
    _send_report_email(report)
    return {"env": ENV_NAME, "date": report["date"], "issued_today": report["issued_today"]}

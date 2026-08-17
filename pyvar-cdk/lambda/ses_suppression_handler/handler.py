"""
lambda/ses_suppression_handler/handler.py — SES bounce/complaint -> suppression

Reasoning:
- SES production-access review follow-up: AWS asked how bounce/complaint
  handling works. SES already maintains its own account-level suppression
  list (SuppressedReasons: [BOUNCE, COMPLAINT], confirmed via
  `aws sesv2 get-account`) and will already silently refuse to re-send to a
  permanently-bounced or complained address. This Lambda exists so (a) our
  own users table reflects that reality and (b) the event is operationally
  visible (a CloudWatch metric feeding the existing pyvar-{env}-alerts
  topic) — SES's own suppression is otherwise invisible unless you go
  looking for it.
- No third-party dependencies, hand-rolled HS256 JWT signing — copied
  verbatim from lambda/public_data_publisher/handler.py (see that file's
  own docstring for the full "why" on both). tier="internal" for the same
  reason: unlimited/unthrottled, kept distinct from "enterprise" so these
  calls don't pollute real customer-tier usage analytics.
- Calls hit the public CloudFront domain, not the ALB directly — same
  reasoning as public_data_publisher (no cross-region/origin-verify need
  once both stacks are eu-west-1). Domain comes from API_BASE_URL (env var,
  set per-environment by ses_events_stack.py from cfg.api_base_url) — was a
  hardcoded dev-only literal in lockstep with the other Lambda until task
  #41 found it made every environment's Lambda call dev's API regardless of
  which environment it ran in (see public_data_publisher/handler.py's own
  API_BASE_URL comment for the full mechanism — this Lambda had the
  identical bug, just never yet observed here since prod had zero real
  bounce/complaint events to trigger it).
- Bounce subtype matters: only a Permanent bounce or a Complaint suppresses
  the address. Transient bounces (mailbox full, message too large, content
  rejected) and Undetermined bounces are retryable/ambiguous by AWS's own
  definition — suppressing on those would burn a real address on what may
  be a temporary condition, and SES already retries transient bounces on
  its own. The recipient list is read from bounce.bouncedRecipients /
  complaint.complainedRecipients specifically, not mail.destination — the
  latter is the full original recipient list, which can differ from who
  actually bounced/complained on a multi-recipient send (not that this
  system ever sends to more than one recipient today, but the distinction
  is what the SES event schema itself makes, so honour it).
- One CloudWatch metric data point per actual suppression, not per raw
  bounce/complaint event, so a transient bounce (correctly not suppressed)
  never moves the alerting metric — it stays a clean "an address is now
  known-bad" signal, not a general bounce-rate counter.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

ENV_NAME = os.environ["ENV_NAME"]
# The secret's NAME, not its ARN: ses_events_stack.py imports the secret by
# deterministic name (Secret.from_secret_name_v2, to avoid a CDK dependency
# cycle — see that stack's docstring), and an imported-by-name secret's
# .secret_arn is a synth-time placeholder MISSING the random 6-char suffix
# Secrets Manager appends to every real secret ARN. Passing that placeholder
# as SecretId here would 403 (it doesn't match any real secret). The name
# has no such suffix problem — Secrets Manager resolves it to the real ARN
# server-side, which does match the IAM grant's `-??????` wildcard resource.
JWT_SECRET_ID = os.environ["JWT_SECRET_ID"]

# See module docstring — task #41.
API_BASE_URL = os.environ["API_BASE_URL"]

METRIC_NAMESPACE = "pyvar"
METRIC_NAME = f"ses-suppressions-{ENV_NAME}"

secretsmanager = boto3.client("secretsmanager")
cloudwatch = boto3.client("cloudwatch")

_PERMANENT_BOUNCE = "Permanent"
_SUPPRESSABLE_EVENT_TYPES = {"Bounce", "Complaint"}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign_service_jwt(secret: str) -> str:
    """Hand-rolled HS256 JWT — see module docstring for why."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    claims = {
        "sub": "internal-ses-suppression-handler",
        "tier": "internal",
        "exp": int(expire.timestamp()),
    }
    payload = _b64url(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(signature)}"


def _get_secret(secret_id: str) -> str:
    return secretsmanager.get_secret_value(SecretId=secret_id)["SecretString"]


def _api_request(method: str, path: str, token: str, body: dict[str, Any]) -> dict[str, Any]:
    url = f"{API_BASE_URL}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310  # fixed, hardcoded domain
        return json.loads(resp.read())


def suppression_reason_for(ses_event: dict[str, Any]) -> str | None:
    """Pure decision function — no boto3/network calls, so it's spot-checkable
    via `python -c` before deploy without any AWS credentials.

    Returns the suppression reason string to record, or None if this event
    should not suppress the address (transient/undetermined bounce, or an
    event type this handler doesn't act on).
    """
    event_type = ses_event.get("eventType") or ses_event.get("notificationType")
    if event_type not in _SUPPRESSABLE_EVENT_TYPES:
        return None

    if event_type == "Complaint":
        return "complaint"

    bounce = ses_event.get("bounce", {})
    if bounce.get("bounceType") == _PERMANENT_BOUNCE:
        return "bounce_permanent"
    return None  # Transient / Undetermined — retryable/ambiguous, don't suppress


def _recipients_for(ses_event: dict[str, Any], reason: str) -> list[str]:
    if reason == "complaint":
        recipients = ses_event.get("complaint", {}).get("complainedRecipients", [])
    else:
        recipients = ses_event.get("bounce", {}).get("bouncedRecipients", [])
    return [r["emailAddress"] for r in recipients if "emailAddress" in r]


def handler(event, context):  # noqa: ANN001, ANN201 — Lambda entrypoint signature is fixed
    jwt_secret = _get_secret(JWT_SECRET_ID)
    suppressed_count = 0

    for record in event.get("Records", []):
        try:
            ses_event = json.loads(record["Sns"]["Message"])
            reason = suppression_reason_for(ses_event)
            if reason is None:
                print(f"ses_event_not_suppressed: {ses_event.get('eventType')}")
                continue

            for email in _recipients_for(ses_event, reason):
                token = _sign_service_jwt(jwt_secret)
                _api_request(
                    "POST",
                    "/api/v1/internal/suppress-email",
                    token,
                    {"email": email, "reason": reason},
                )
                suppressed_count += 1
        except (KeyError, json.JSONDecodeError, urllib.error.URLError) as exc:
            # One malformed/failed record must not abort the whole batch —
            # an unhandled exception here would make SNS retry the entire
            # invocation, replaying already-processed records.
            print(f"ses_suppression_record_failed: {exc}")

    if suppressed_count:
        cloudwatch.put_metric_data(
            Namespace=METRIC_NAMESPACE,
            MetricData=[
                {"MetricName": METRIC_NAME, "Value": float(suppressed_count), "Unit": "Count"}
            ],
        )

    return {"suppressed_count": suppressed_count}

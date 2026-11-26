"""
api/assistant/key.py — the typed route's Anthropic key, read from Secrets Manager at call time

Reasoning:
- The key is NOT injected through ECS's native `secrets={}`. That mechanism has no "optional" mode: a secret that is
  missing or unreadable stops every new task from launching, and the whole API (every compute route) with it, for a
  feature that is off. api/routes/billing.py::_resolve_stripe_secrets and observability/setup.py::_resolve_sentry_dsn
  work the same way for the same reason. The task role reads the secret at run time instead (pyvar-cdk api_stack.py
  grants it), so a missing key means one thing only: "the assistant is not set up" (503 assistant_unavailable).
- It is read at call time and cached for CACHE_TTL_SECONDS, as fibtec-etlgen does (api/lib/secret_value.py):
  `put-secret-value` is then the whole rotation, effective within a minute with no deploy, and rolling back is
  moving AWSCURRENT back. api/assistant/deps.py::get_model_client rebuilds its client when the value changes.
- A key already in settings (a local `.env`, a test) wins and never touches AWS, and outside an ECS task nothing is
  read (CI and a laptop have no Secrets Manager): the same two rules as the Stripe resolver.
- A failed read never returns an empty or stale key: after CACHE_TTL_SECONDS without a good read the answer is None.
  A failure is remembered for FAILURE_RETRY_SECONDS only, so a missing secret costs one AWS call every 15 seconds
  however many questions arrive, and a secret created a moment later is picked up quickly.
- Nothing here logs the value. The log lines carry the secret's short name, the exception's class and the AWS error
  code, never `exc_info` or the message (an AWS message can name the secret's ARN but never its content; the class and
  code are what anyone acts on).
"""

from __future__ import annotations

import time
from collections.abc import Callable

import structlog

from config import get_settings
from observability.redact import aws_error_code

cfg = get_settings()
logger = structlog.get_logger()

SECRET_SUFFIX = "anthropic-api-key"
CACHE_TTL_SECONDS = 60.0
FAILURE_RETRY_SECONDS = 15.0

# (monotonic time the entry expires, the key or None for a failed read), module-level so a warm task keeps it
_cache: tuple[float, str | None] | None = None


def secret_id() -> str:
    """The Secrets Manager name for this environment, as the CDK stack grants it: pyvar/<app_env>/anthropic-api-key."""
    return f"pyvar/{cfg.app_env}/{SECRET_SUFFIX}"


def reset_cache() -> None:
    """Forget what was read (a test; or an operator's restart does the same)."""
    global _cache
    _cache = None


def _read() -> str | None:
    """One Secrets Manager read. None on any failure or an empty secret; the reason is logged without content."""
    import boto3

    try:
        value = (
            boto3.client("secretsmanager")
            .get_secret_value(SecretId=secret_id())
            .get("SecretString")
        )
    except Exception as exc:  # noqa: BLE001 — degrade to "not set up", never raise into a request
        logger.warning(
            "assistant_key_read_failed",
            secret=SECRET_SUFFIX,
            error=type(exc).__name__,
            error_code=aws_error_code(exc),
        )
        return None
    key = (value or "").strip()
    if not key:
        # A secret created as SecretBinary has no SecretString: not an exception, so say why it stayed unset.
        logger.warning("assistant_key_empty", secret=SECRET_SUFFIX)
        return None
    return key


def resolve_key(*, clock: Callable[[], float] = time.monotonic) -> str | None:
    """The Anthropic key to use now, or None if there is none.

    Order: a key in settings; else (only inside an ECS task) the secret, cached for CACHE_TTL_SECONDS and, if the
    read failed, retried after FAILURE_RETRY_SECONDS.
    """
    global _cache
    configured = cfg.anthropic_api_key
    if configured is not None and configured.get_secret_value():
        return configured.get_secret_value()
    if not cfg.ecs_container_metadata_uri_v4:
        return None
    now = clock()
    if _cache is not None and now < _cache[0]:
        return _cache[1]
    key = _read()
    _cache = (now + (CACHE_TTL_SECONDS if key else FAILURE_RETRY_SECONDS), key)
    return key

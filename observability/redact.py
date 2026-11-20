"""observability/redact.py — keeping e-mail addresses out of logs and Sentry events.

Reasoning:
- An address reaches a third party (Sentry) or a month of CloudWatch logs in three ways: a log line that
  carries it, a stack frame whose local variable holds it (the SDK sends locals by default), and an exception
  message that echoes it (SES error text can quote the recipient). docs/plan-education-tier.md section 12 records
  how this was found (2026-11-20) and the tests that pin it (tests/test_tier_email_privacy.py,
  tests/test_sentry_privacy.py).
- The first defence is not to write the address: callers log `email_domain(address)` and, where they have it, the
  account id, and on a failed send `aws_error_code(exc)` and the exception's class, never its text. The second is a
  net: `scrub_event` and `scrub_breadcrumb` replace anything shaped like an address in everything Sentry is about
  to send. A pattern can miss an unusual address, which is why it is the net and not the plan.
- The scrubber never raises and never lets an unscrubbed event through: if it fails, the event or breadcrumb is
  dropped (losing one report is cheaper than sending an address).
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# user@host.tld, and the same with the "@" URL-encoded (a query string or a form body).
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+(?:@|%40)[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.IGNORECASE)
REDACTED = "[email]"


def email_domain(email: str) -> str:
    """The part after the last "@", lower-cased: enough to tell which institution a failing send was for,
    without naming the person. "unknown" if there is no "@" or nothing after it."""
    if "@" not in email:
        return "unknown"
    return email.rpartition("@")[2].strip().lower() or "unknown"


def aws_error_code(exc: BaseException) -> str | None:
    """The AWS error code of a botocore ClientError ("Throttling", "MessageRejected", ...), else None."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        return str(code) if code else None
    return None


def scrub_text(text: str) -> str:
    """`text` with every address-shaped substring replaced by "[email]". A cheap prefilter keeps the common case
    (no "@" and no "%40") out of the regular expression altogether."""
    if "@" not in text and "%40" not in text.lower():
        return text
    return _EMAIL.sub(REDACTED, text)


def scrub(value: Any) -> Any:
    """A copy of `value` with every string inside dicts, lists and tuples passed through `scrub_text`.
    Anything else (numbers, None, the SDK's own annotated values) is returned unchanged."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub(item) for item in value)
    return value


def scrub_event(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Sentry `before_send`: the event with no address in it, or None (drop it) if scrubbing failed."""
    try:
        scrubbed = scrub(event)
        return scrubbed if isinstance(scrubbed, dict) else None
    except (
        Exception
    ):  # noqa: BLE001 — never let an unscrubbed event through, never raise into the SDK
        logger.warning("sentry_scrub_failed_event_dropped")
        return None


def scrub_breadcrumb(
    crumb: dict[str, Any], hint: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Sentry `before_breadcrumb`: the breadcrumb with no address in it, or None (drop it) if scrubbing failed."""
    try:
        scrubbed = scrub(crumb)
        return scrubbed if isinstance(scrubbed, dict) else None
    except Exception:  # noqa: BLE001 — as scrub_event
        logger.warning("sentry_scrub_failed_breadcrumb_dropped")
        return None

"""tests/test_tier_email_privacy.py — a tier e-mail never puts the holder's address in a log line or in Sentry.

Reasoning:
- The address of a person who applied for education access (or any tier change) must not travel to
  CloudWatch or Sentry (docs/plan-education-tier.md section 12). Before this test, `send_tier_change_email` logged
  `email=...` and, on failure, a traceback: with Sentry's default logging integration a failed send became an
  error event carrying the address, and a successful send a breadcrumb on any later error in the same scope
  (found 2026-11-20 by running the real code against a capturing transport).
- SES error text can echo the recipient ("Email address is not verified: ..."), so the failure line carries the
  exception's class and AWS error code only, never its message or a traceback.
- The end date in the grant and extension e-mails is part of the same function and is pinned here: the Terms say
  we tell the holder how long access lasts.
- No network and no real AWS: the SES client is a fake. tests/conftest.py patches `sentry_sdk.init` for the whole
  session on purpose (the suite must never reach a real Sentry project), so these tests build a
  `sentry_sdk.Client` directly, with a transport that only records what it would send, and bind it to the
  global scope. That is the same client the app would have, with the same default integrations.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
import structlog
from botocore.exceptions import ClientError
from structlog.testing import capture_logs

import api.middleware.billing_lifecycle as lifecycle
from observability.redact import email_domain

ADDRESS = "zz-sentinel-holder@example.invalid"
DOMAIN = "example.invalid"


class FakeSes:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[dict[str, Any]] = []

    def send_email(self, **kwargs: Any) -> dict[str, str]:
        if self.error is not None:
            raise self.error
        self.sent.append(kwargs)
        return {"MessageId": "x"}


def ses_error() -> ClientError:
    """What SES really does: the message names the recipient."""
    return ClientError(
        {
            "Error": {
                "Code": "MessageRejected",
                "Message": f"Email address is not verified: {ADDRESS}",
            }
        },
        "SendEmail",
    )


def send(ses: FakeSes, event: str = lifecycle.EVENT_UPGRADED, **kwargs: Any) -> None:
    with patch.object(lifecycle, "_get_ses_client", return_value=ses):
        lifecycle.send_tier_change_email(ADDRESS, event, **kwargs)


# ── what is logged ───────────────────────────────────────────────────────────────────────────────────────────


def test_a_successful_send_logs_the_domain_and_never_the_address() -> None:
    with capture_logs() as logs:
        send(FakeSes(), lifecycle.EVENT_EDUCATION_GRANTED, account_id="ext-ada")
    assert ADDRESS not in repr(logs) and "zz-sentinel" not in repr(logs)
    (line,) = logs
    assert line["event"] == "tier_change_email_sent"
    assert line["email_domain"] == DOMAIN and line["account_id"] == "ext-ada"


def test_a_failed_send_logs_the_class_and_code_never_the_address_or_the_text() -> None:
    with capture_logs() as logs:
        send(FakeSes(ses_error()), account_id="ext-ada")  # must not raise
    assert "zz-sentinel" not in repr(logs) and "not verified" not in repr(logs)
    (line,) = logs
    assert line["event"] == "tier_change_email_send_failed" and line["log_level"] == "error"
    assert (line["error_type"], line["error_code"]) == ("ClientError", "MessageRejected")
    assert line["email_domain"] == DOMAIN
    assert "exc_info" not in line  # a traceback carries the exception text


def test_a_failure_that_is_not_an_aws_error_has_no_code() -> None:
    with capture_logs() as logs:
        send(FakeSes(RuntimeError(f"cannot reach {ADDRESS}")))
    assert "zz-sentinel" not in repr(logs)
    assert logs[0]["error_type"] == "RuntimeError" and logs[0]["error_code"] is None


def test_the_domain_of_an_address_without_an_at_sign_is_unknown() -> None:
    assert email_domain("nobody") == "unknown"
    assert email_domain("A@Uni.AC.uk") == "uni.ac.uk"
    assert email_domain("trailing@") == "unknown"


# ── what the holder is told ──────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("event", "end", "wanted"),
    [
        (lifecycle.EVENT_EDUCATION_GRANTED, date(2027, 5, 20), "ends on 20 May 2027"),
        (
            lifecycle.EVENT_EDUCATION_GRANTED,
            datetime(2027, 1, 3, 9, 30, tzinfo=timezone.utc),
            "ends on 3 January 2027",
        ),
        (lifecycle.EVENT_EDUCATION_EXTENDED, date(2027, 11, 2), "now ends on 2 November 2027"),
    ],
)
def test_the_grant_and_extension_e_mails_state_the_end_date(
    event: str, end: Any, wanted: str
) -> None:
    ses = FakeSes()
    send(ses, event, end_date=end)
    body = ses.sent[0]["Message"]["Body"]["Text"]["Data"]
    assert wanted in body and "{" not in body


def test_without_a_date_the_old_wording_is_used_not_a_raw_placeholder() -> None:
    ses = FakeSes()
    send(ses, lifecycle.EVENT_EDUCATION_GRANTED)
    body = ses.sent[0]["Message"]["Body"]["Text"]["Data"]
    assert "ends on the date agreed" in body and "{end_date}" not in body


def test_no_message_leaves_a_placeholder_behind() -> None:
    for event in lifecycle._NOTIFICATION_COPY:
        ses = FakeSes()
        send(ses, event, end_date=date(2027, 5, 20))
        assert "{" not in ses.sent[0]["Message"]["Body"]["Text"]["Data"], event


# ── what Sentry would receive (the real logging set-up, a recording transport) ───────────────────────────────


@pytest.fixture
def sentry_events() -> Iterator[list[bytes]]:
    sentry_sdk = pytest.importorskip("sentry_sdk")
    from sentry_sdk.transport import Transport

    from observability.setup import setup_logging

    captured: list[bytes] = []

    class Recording(Transport):
        def capture_envelope(self, envelope: Any) -> None:
            captured.append(envelope.serialize())

        def flush(self, timeout: float, callback: Any = None) -> None:
            return None

    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    saved_structlog = structlog.get_config()
    setup_logging()  # the real route: structlog -> stdlib logging -> Sentry's default logging integration
    client = sentry_sdk.Client(
        dsn="https://public@o0.ingest.sentry.io/0",
        transport=Recording,
        # no send_default_pii: its default (off) is what observability/setup.py sets explicitly
        traces_sample_rate=0.0,
    )
    sentry_sdk.get_global_scope().set_client(client)
    try:
        yield captured
    finally:
        client.flush(timeout=1)
        client.close()
        sentry_sdk.get_global_scope().set_client(None)
        for scope in (
            sentry_sdk.get_isolation_scope(),
            sentry_sdk.get_current_scope(),
            sentry_sdk.get_global_scope(),
        ):
            scope.clear()
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        structlog.configure(**saved_structlog)


def received(captured: list[bytes]) -> str:
    return b"".join(captured).decode("utf-8", "replace")


def test_a_failed_send_puts_no_address_in_what_sentry_would_receive(
    sentry_events: list[bytes],
) -> None:
    import sentry_sdk

    send(FakeSes(ses_error()), lifecycle.EVENT_EDUCATION_GRANTED, account_id="ext-ada")
    sentry_sdk.flush()
    blob = received(sentry_events)
    assert (
        blob
    ), "the failure line should still reach Sentry as an event (so we notice a broken sender)"
    assert "zz-sentinel" not in blob and "not verified" not in blob


def test_a_successful_send_leaves_no_address_in_a_later_error_breadcrumb(
    sentry_events: list[bytes],
) -> None:
    import sentry_sdk

    send(FakeSes(), lifecycle.EVENT_EDUCATION_GRANTED, account_id="ext-ada")
    sentry_sdk.capture_message("an unrelated error later in the same request")
    sentry_sdk.flush()
    blob = received(sentry_events)
    assert "unrelated error" in blob and "zz-sentinel" not in blob

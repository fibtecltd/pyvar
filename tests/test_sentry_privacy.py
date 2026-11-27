"""tests/test_sentry_privacy.py — what Sentry is sent never contains an e-mail address.

Reasoning:
- The privacy policy tells people Sentry receives error reports; for education applicants it is also read as
  "no e-mail addresses". Found on 2026-11-20 (docs/plan-education-tier.md section 12): by default the SDK sends
  the local variables of every stack frame, an ERROR log line becomes an event, INFO lines become breadcrumbs,
  and exception text (SES echoes the recipient) goes in the message. `max_request_body_size="never"` alone does
  not stop the locals path.
- observability/setup.py builds the options in one function, `sentry_options()`, so these tests run the exact
  options production runs. The suite never initialises the SDK for real (tests/conftest.py patches
  `sentry_sdk.init`), so the client is built directly, with a transport that only records.
- Only the logging integration is kept from the real options: the FastAPI, Celery and SQLAlchemy integrations
  patch third-party libraries for the rest of the process and have nothing to do with what is asserted here.
- The first line of defence is not writing addresses (tests/test_tier_email_privacy.py, tests/test_auth.py); this
  file tests the net under it, plus the settings that keep whole classes of data out.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
import structlog

import observability.redact as redact
from observability.redact import (
    REDACTED,
    aws_error_code,
    email_domain,
    scrub,
    scrub_breadcrumb,
    scrub_event,
    scrub_text,
)
from observability.sentry_filters import before_send
from observability.setup import cfg, sentry_options, setup_logging, setup_sentry

# `send_default_pii` is still passed (it works on every SDK 1.x/2.x, the worker image installs an unpinned one);
# the newest SDK deprecates it in favour of `data_collection`, which older SDKs reject.
pytestmark = pytest.mark.filterwarnings("ignore:The send_default_pii option is deprecated")

ADDRESS = "zz-sentinel-holder@example.invalid"
DSN = "https://public@o0.ingest.sentry.io/0"

# ── the scrubber ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        f"failed for {ADDRESS}",
        f"Email address is not verified: {ADDRESS}.",
        f"<{ADDRESS}>",
        "ZZ-SENTINEL-HOLDER@EXAMPLE.INVALID",
        "first.last+tag@sub.uni.ac.uk",
        "GET /auth?email=zz-sentinel-holder%40example.invalid&x=1",
        "a@b.co and c@d.eu in one line",
    ],
)
def test_scrub_text_replaces_every_address_shaped_substring(text: str) -> None:
    out = scrub_text(text)
    assert REDACTED in out
    assert "sentinel" not in out.lower() and "@" not in out and "%40" not in out.lower()


@pytest.mark.parametrize(
    "text",
    ["", "no address here", "100% sure", "build 40 passed", "user at example dot com", "@mention"],
)
def test_scrub_text_leaves_other_text_alone(text: str) -> None:
    assert scrub_text(text) == text


def test_scrub_walks_dicts_lists_and_tuples_and_keeps_everything_else() -> None:
    value = {
        "message": f"to {ADDRESS}",
        "frames": [{"vars": {"email": ADDRESS, "n": 3, "ok": True, "none": None}}],
        "pair": (ADDRESS, 1.5),
    }
    out = scrub(value)
    assert ADDRESS not in repr(out) and "sentinel" not in repr(out)
    assert out["frames"][0]["vars"]["n"] == 3 and out["frames"][0]["vars"]["ok"] is True
    assert out["frames"][0]["vars"]["none"] is None and out["pair"][1] == 1.5
    assert isinstance(out["pair"], tuple)
    assert value["message"].endswith(ADDRESS), "the input is not modified"


def test_scrub_event_and_scrub_breadcrumb_return_scrubbed_copies() -> None:
    event = {"message": f"x {ADDRESS}", "level": "error"}
    crumb = {"category": "log", "message": f"sent to {ADDRESS}"}
    assert scrub_event(event) == {"message": f"x {REDACTED}", "level": "error"}
    assert scrub_breadcrumb(crumb) == {"category": "log", "message": f"sent to {REDACTED}"}


def test_if_scrubbing_fails_the_event_and_the_breadcrumb_are_dropped_not_sent() -> None:
    with patch.object(redact, "scrub", side_effect=RuntimeError("boom")):
        assert scrub_event({"message": ADDRESS}) is None
        assert scrub_breadcrumb({"message": ADDRESS}) is None


def test_email_domain_names_the_institution_not_the_person() -> None:
    assert email_domain("A@Uni.AC.uk") == "uni.ac.uk"
    assert email_domain("a@b@c.org") == "c.org"
    assert email_domain("trailing@") == "unknown"
    assert email_domain("") == "unknown"
    # a bare word may be a name, so it is never echoed
    assert email_domain("nobody") == "unknown"


def test_aws_error_code_is_read_from_a_client_error_only() -> None:
    from botocore.exceptions import ClientError

    err = ClientError({"Error": {"Code": "Throttling", "Message": ADDRESS}}, "SendEmail")
    assert aws_error_code(err) == "Throttling"
    assert aws_error_code(RuntimeError(ADDRESS)) is None


# ── the options production runs ──────────────────────────────────────────────────────────────────────────────


def test_options_keep_locals_bodies_and_pii_out_and_install_the_scrubbers() -> None:
    opts = sentry_options(DSN)
    assert opts["dsn"] == DSN
    assert opts["include_local_variables"] is False
    assert opts["max_request_body_size"] == "never"
    assert opts["send_default_pii"] is False
    assert (
        opts["before_send"] is before_send
    )  # scrub_event, after dropping the assistant's expected refusals
    assert opts["before_breadcrumb"] is scrub_breadcrumb


def test_options_state_the_logging_integration_instead_of_relying_on_a_default() -> None:
    from sentry_sdk.integrations.logging import LoggingIntegration

    (logging_integration,) = [
        i for i in sentry_options(DSN)["integrations"] if isinstance(i, LoggingIntegration)
    ]
    assert (
        logging_integration._handler is not None
        and logging_integration._breadcrumb_handler is not None
    )
    assert logging_integration._handler.level == logging.ERROR
    assert logging_integration._breadcrumb_handler.level == logging.INFO


@pytest.mark.parametrize(("app_env", "rate"), [("dev", 1.0), ("staging", 1.0), ("prod", 0.1)])
def test_trace_sampling_is_unchanged(app_env: str, rate: float) -> None:
    with patch.object(cfg, "app_env", app_env):
        assert sentry_options(DSN)["traces_sample_rate"] == rate


def test_setup_sentry_passes_exactly_these_options(_no_sentry_in_tests: Any) -> None:
    with patch.object(cfg, "sentry_dsn", DSN):
        setup_sentry()
    kwargs = _no_sentry_in_tests.call_args.kwargs
    assert kwargs["include_local_variables"] is False
    assert kwargs["before_send"] is before_send and kwargs["before_breadcrumb"] is scrub_breadcrumb


# ── what a real client would send ────────────────────────────────────────────────────────────────────────────


@contextmanager
def recording_client(*extra_integrations: Any) -> Iterator[list[bytes]]:
    """A real client built from `sentry_options()` (its logging integration, plus any extra), bound to the global
    scope and recording what it would send."""
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.transport import Transport

    captured: list[bytes] = []

    class Recording(Transport):
        def capture_envelope(self, envelope: Any) -> None:
            captured.append(envelope.serialize())

        def flush(self, timeout: float, callback: Any = None) -> None:
            return None

    options = sentry_options(DSN)
    options["integrations"] = [
        i for i in options["integrations"] if isinstance(i, LoggingIntegration)
    ] + list(extra_integrations)
    options["transport"] = Recording
    options["traces_sample_rate"] = 0.0

    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    saved_structlog = structlog.get_config()
    setup_logging()  # the real route: structlog -> stdlib logging -> Sentry's logging integration
    client = sentry_sdk.Client(**options)
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


@pytest.fixture
def sent() -> Iterator[list[bytes]]:
    with recording_client() as captured:
        yield captured


def received(sent: list[bytes]) -> str:
    return b"\n".join(sent).decode("utf-8", errors="replace")


def events_in(sent: list[bytes]) -> list[dict[str, Any]]:
    """The error/message events inside the recorded envelopes (every third line is a payload)."""
    found: list[dict[str, Any]] = []
    for envelope in sent:
        for line in envelope.decode("utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and (
                "exception" in item or "logentry" in item or "message" in item
            ):
                found.append(item)
    return found


def keys_anywhere(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for item in value.values() for k in keys_anywhere(item)}
    if isinstance(value, list):
        return {k for item in value for k in keys_anywhere(item)}
    return set()


def _route_that_holds_an_address(address: str, body: dict[str, Any]) -> None:
    """Stands in for a route that crashes while its locals hold the applicant's address and the request body."""
    recipient = address  # noqa: F841 — present in the frame on purpose
    payload = body  # noqa: F841
    raise RuntimeError("downstream failure")


def test_a_crash_sends_no_local_variables_and_so_no_address_or_request_body(
    sent: list[bytes],
) -> None:
    import sentry_sdk

    try:
        # the series is computed, so its digits are not in this file's source (which Sentry sends as context)
        series = [1 / 7, 2 / 7, 3 / 7]
        _route_that_holds_an_address(ADDRESS, {"email": ADDRESS, "returns": series})
    except RuntimeError:
        sentry_sdk.capture_exception()
    sentry_sdk.flush()
    blob = received(sent)
    assert "downstream failure" in blob, "the error itself must still be reported"
    assert "zz-sentinel" not in blob and ADDRESS not in blob
    (event,) = events_in(sent)
    assert "vars" not in keys_anywhere(event), "no stack frame carries its local variables"
    assert (
        "0.142857" not in blob and "0.2857" not in blob
    ), "the request body held in a local is not sent"


def test_an_exception_message_that_echoes_the_address_is_scrubbed(sent: list[bytes]) -> None:
    import sentry_sdk

    try:
        raise RuntimeError(f"Email address is not verified: {ADDRESS}")
    except RuntimeError:
        sentry_sdk.capture_exception()
    sentry_sdk.flush()
    blob = received(sent)
    assert "Email address is not verified" in blob and REDACTED in blob
    assert "zz-sentinel" not in blob


def test_an_old_style_error_log_line_with_an_address_is_scrubbed_in_the_event(
    sent: list[bytes],
) -> None:
    import sentry_sdk

    logging.getLogger("legacy").error("verification_email_send_failed for %s", ADDRESS)
    sentry_sdk.flush()
    blob = received(sent)
    assert "verification_email_send_failed" in blob, "an error log line must still become an event"
    assert "zz-sentinel" not in blob


def test_a_breadcrumb_that_carried_an_address_is_scrubbed(sent: list[bytes]) -> None:
    import sentry_sdk

    logging.getLogger("legacy").info("sent to %s", ADDRESS)
    sentry_sdk.capture_message("an unrelated error later in the same request")
    sentry_sdk.flush()
    blob = received(sent)
    assert "unrelated error" in blob and "sent to" in blob
    assert "zz-sentinel" not in blob


def test_an_address_url_encoded_in_a_message_is_scrubbed(sent: list[bytes]) -> None:
    import sentry_sdk

    sentry_sdk.capture_message("GET /auth?email=zz-sentinel-holder%40example.invalid failed")
    sentry_sdk.flush()
    blob = received(sent)
    assert "failed" in blob and "zz-sentinel" not in blob


def test_an_info_line_is_a_breadcrumb_not_an_event(sent: list[bytes]) -> None:
    logging.getLogger("legacy").info("just information")
    import sentry_sdk

    sentry_sdk.flush()
    assert received(sent) == ""


def test_a_crashing_post_route_sends_neither_the_body_nor_the_locals() -> None:
    """A real FastAPI app with the FastAPI integration and the production options: the request body is a
    sign-up form with an address and a returns series, and the route raises."""
    import sentry_sdk
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    app = FastAPI()

    @app.post("/register")
    async def register(payload: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    with recording_client(FastApiIntegration(transaction_style="endpoint")) as sent:
        body = {"email": ADDRESS, "returns": [1 / 7, 2 / 7]}
        TestClient(app, raise_server_exceptions=False).post("/register", json=body)
        sentry_sdk.flush()
        blob = received(sent)
        assert "boom" in blob, "the error itself must still be reported"
        assert "zz-sentinel" not in blob and "0.142857" not in blob
        (event,) = events_in(sent)
        assert "vars" not in keys_anywhere(event)
        assert not event["request"].get(
            "data"
        ), "the request body is not attached (None or removed)"

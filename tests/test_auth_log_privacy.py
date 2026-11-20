"""tests/test_auth_log_privacy.py — the sign-in and e-mail-suppression routes never write an address to a log line.

Reasoning:
- Server logs reach CloudWatch and, through the logging integration, Sentry (an error line becomes an event, an
  INFO line a breadcrumb on any later error). The privacy policy does not list e-mail addresses among what Sentry
  receives, and education applicants sign up with their institution's address (docs/plan-education-tier.md
  section 12). So these routes log the address's domain and the account id, and a failed send logs the
  exception's class and AWS error code, never its text (SES echoes the recipient) or a traceback.
- Same mocking boundary as tests/test_auth.py and tests/test_internal.py: a fake session, a fake SES client.
  Logs are read with structlog's `capture_logs`, the same way tests/test_tier_email_privacy.py reads them.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from httpx import ASGITransport, AsyncClient
from structlog.testing import capture_logs

from api.middleware.auth import create_access_token
from api.routes.auth import cfg as auth_cfg
from api.routes.auth import send_verification_email
from main import create_app
from storage.models import User
from tests.test_auth import FakeAsyncSession
from tests.test_auth import patch_sessionmaker as patch_auth_sessionmaker
from tests.test_internal import patch_sessionmaker as patch_internal_sessionmaker

ADDRESS = "zz-sentinel-signin@example.com"
DOMAIN = "example.com"


def ses_error() -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": "MessageRejected",
                "Message": f"Email address is not verified: {ADDRESS}",
            }
        },
        "SendEmail",
    )


@pytest.fixture
def app() -> Any:
    return create_app()


def no_address(logs: list[dict[str, Any]]) -> None:
    text = repr(logs)
    assert "zz-sentinel" not in text and ADDRESS not in text and "not verified" not in text


# ── sending the link ─────────────────────────────────────────────────────────────────────────────────────────


def test_a_sent_link_logs_the_domain_and_the_account_not_the_address() -> None:
    with patch("api.routes.auth.get_ses_client", return_value=MagicMock()), capture_logs() as logs:
        send_verification_email(ADDRESS, "tok", account_id="ext-ada")
    no_address(logs)
    (line,) = logs
    assert line["event"] == "verification_email_sent"
    assert (line["email_domain"], line["account_id"], line["signin"]) == (DOMAIN, "ext-ada", False)


@pytest.mark.parametrize("app_env", ["dev", "staging", "prod"])
def test_a_failed_send_in_a_deployed_environment_logs_class_and_code_only(app_env: str) -> None:
    fake = MagicMock()
    fake.send_email.side_effect = ses_error()
    with (
        patch.object(auth_cfg, "app_env", app_env),
        patch("api.routes.auth.get_ses_client", return_value=fake),
        capture_logs() as logs,
    ):
        send_verification_email(
            ADDRESS, "secret-token-value", account_id="ext-ada"
        )  # must not raise
    no_address(logs)
    assert "secret-token-value" not in repr(
        logs
    ), "a live bearer token is never logged outside development"
    (line,) = logs
    assert line["event"] == "verification_email_send_failed" and line["log_level"] == "error"
    assert (line["error_type"], line["error_code"]) == ("ClientError", "MessageRejected")
    assert (line["email_domain"], line["account_id"]) == (DOMAIN, "ext-ada")
    assert "exc_info" not in line, "a traceback carries the exception text"


def test_the_local_development_branch_still_has_the_token_but_not_the_address_key() -> None:
    """Local development has no SES: the token is logged on purpose so sign-up can be tried by hand. The address
    is still not a field of the line."""
    fake = MagicMock()
    fake.send_email.side_effect = RuntimeError("no credentials")
    with (
        patch.object(auth_cfg, "app_env", "development"),
        patch("api.routes.auth.get_ses_client", return_value=fake),
        capture_logs() as logs,
    ):
        send_verification_email(ADDRESS, "dev-token", account_id="ext-ada")
    (line,) = logs
    assert line["token"] == "dev-token" and "email" not in line
    assert line["email_domain"] == DOMAIN


# ── register() ───────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_hands_the_new_account_id_to_the_sender(app: Any) -> None:
    session = FakeAsyncSession(lookup_result=None)
    with patch_auth_sessionmaker(session), patch("api.routes.auth.send_verification_email") as send:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/register", json={"email": ADDRESS})
    assert resp.status_code == 202
    (created,) = session.added
    assert send.call_args.kwargs["account_id"] == created.external_id


@pytest.mark.asyncio
async def test_a_blocked_or_suppressed_registration_logs_the_domain_only(app: Any) -> None:
    suppressed = User(
        external_id="ext-bounced",
        email=ADDRESS,
        email_suppressed=True,
        suppression_reason="bounce_permanent",
    )
    with capture_logs() as logs:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch_auth_sessionmaker(FakeAsyncSession(lookup_result=suppressed)):
                await client.post("/api/v1/auth/register", json={"email": ADDRESS})
            await client.post("/api/v1/auth/register", json={"email": "someone@mailinator.com"})
    no_address(logs)
    assert "someone@mailinator.com" not in repr(logs) and "someone" not in repr(logs)
    events = {
        line["event"]: line for line in logs if line["event"].startswith("registration_skipped")
    }
    assert events["registration_skipped_suppressed_email"]["email_domain"] == DOMAIN
    assert events["registration_skipped_suppressed_email"]["account_id"] == "ext-bounced"
    assert events["registration_skipped_disposable_email"]["email_domain"] == "mailinator.com"


# ── POST /internal/suppress-email ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("known", [True, False])
async def test_suppressing_an_address_logs_the_domain_only(app: Any, known: bool) -> None:
    existing = User(external_id="ext-1", email=ADDRESS, email_suppressed=False) if known else None
    token = create_access_token(user_id="internal-svc", tier="internal")
    with (
        capture_logs() as logs,
        patch_internal_sessionmaker(FakeAsyncSession(lookup_result=existing)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/internal/suppress-email",
                json={"email": ADDRESS, "reason": "bounce_permanent"},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 200
    no_address(logs)
    (line,) = [
        entry for entry in logs if entry["event"].startswith(("email_suppressed", "suppress_email"))
    ]
    assert line["email_domain"] == DOMAIN
    if known:
        assert line["account_id"] == "ext-1"

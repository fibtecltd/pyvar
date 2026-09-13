"""
tests/test_billing_lifecycle.py — unit tests for
api/middleware/billing_lifecycle.py (item 5 §8 follow-on).

Reasoning:
- Same FakeAsyncSession/patch_sessionmaker pattern as tests/test_billing.py —
  the DB session is mocked at api.middleware.billing_lifecycle.get_sessionmaker,
  never a real Postgres.
- boto3.client is patched directly (never a real SES call), same boundary as
  tests/test_auth.py's send_verification_email coverage.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.middleware import billing_lifecycle
from storage.models import BillingEvent, User

# ── Fakes ──────────────────────────────────────────────────────────────────────


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeAsyncSession:
    def __init__(self, lookup_result=None):
        self._lookup_result = lookup_result
        self.added: list = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        return FakeResult(self._lookup_result)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def patch_sessionmaker(fake_session: FakeAsyncSession):
    return patch(
        "api.middleware.billing_lifecycle.get_sessionmaker", return_value=lambda: fake_session
    )


def make_user(*, tier: str = "pro", email: str | None = "user@example.com") -> User:
    return User(external_id="user-123", tier=tier, email=email)


# ── record_billing_event ─────────────────────────────────────────────────────


def test_record_billing_event_adds_to_session_without_committing():
    session = FakeAsyncSession()
    billing_lifecycle.record_billing_event(
        session,
        user_id="user-123",
        event_type="upgraded",
        old_tier="free",
        new_tier="pro",
    )
    assert len(session.added) == 1
    event = session.added[0]
    assert isinstance(event, BillingEvent)
    assert event.user_id == "user-123"
    assert event.event_type == "upgraded"
    assert event.old_tier == "free"
    assert event.new_tier == "pro"
    assert session.committed is False


# ── send_tier_change_email ────────────────────────────────────────────────────


def test_send_tier_change_email_noop_without_address():
    with patch("boto3.client") as mock_boto_client:
        billing_lifecycle.send_tier_change_email(None, billing_lifecycle.EVENT_UPGRADED)
    mock_boto_client.assert_not_called()


def test_send_tier_change_email_noop_on_unknown_event_type():
    with patch("boto3.client") as mock_boto_client:
        billing_lifecycle.send_tier_change_email("user@example.com", "not_a_real_event")
    mock_boto_client.assert_not_called()


def test_send_tier_change_email_sends_via_ses():
    mock_client = MagicMock()
    with patch("boto3.client", return_value=mock_client) as mock_boto_client:
        billing_lifecycle.send_tier_change_email("user@example.com", billing_lifecycle.EVENT_UPGRADED)

    mock_boto_client.assert_called_once_with("ses", region_name=billing_lifecycle.cfg.ses_region)
    mock_client.send_email.assert_called_once()
    kwargs = mock_client.send_email.call_args.kwargs
    assert kwargs["Destination"] == {"ToAddresses": ["user@example.com"]}
    assert "Pro" in kwargs["Message"]["Subject"]["Data"]


def test_send_tier_change_email_degrades_on_ses_failure():
    mock_client = MagicMock()
    mock_client.send_email.side_effect = Exception("SES unavailable")
    with patch("boto3.client", return_value=mock_client):
        billing_lifecycle.send_tier_change_email(
            "user@example.com", billing_lifecycle.EVENT_UPGRADED
        )  # must not raise


# ── downgrade_for_monthly_limit ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_downgrade_for_monthly_limit_flips_tier_and_notifies():
    user = make_user(tier="pro")
    session = FakeAsyncSession(lookup_result=user)

    with (
        patch_sessionmaker(session),
        patch("api.middleware.billing_lifecycle.send_tier_change_email") as mock_send,
    ):
        await billing_lifecycle.downgrade_for_monthly_limit(
            user_id="user-123",
            downgrade_reason=billing_lifecycle.DOWNGRADE_MONTHLY_REQUEST_LIMIT,
            event_type=billing_lifecycle.EVENT_DOWNGRADED_MONTHLY_REQUEST_LIMIT,
            detail="Exceeded 5,000 requests this billing period.",
        )

    assert user.tier == "free"
    assert user.tier_downgrade_reason == billing_lifecycle.DOWNGRADE_MONTHLY_REQUEST_LIMIT
    assert session.committed is True
    assert len(session.added) == 1
    event = session.added[0]
    assert event.event_type == billing_lifecycle.EVENT_DOWNGRADED_MONTHLY_REQUEST_LIMIT
    assert event.old_tier == "pro"
    assert event.new_tier == "free"
    mock_send.assert_called_once_with(
        "user@example.com", billing_lifecycle.EVENT_DOWNGRADED_MONTHLY_REQUEST_LIMIT
    )


@pytest.mark.asyncio
async def test_downgrade_for_monthly_limit_noop_when_user_not_found():
    session = FakeAsyncSession(lookup_result=None)

    with (
        patch_sessionmaker(session),
        patch("api.middleware.billing_lifecycle.send_tier_change_email") as mock_send,
    ):
        await billing_lifecycle.downgrade_for_monthly_limit(
            user_id="ghost-user",
            downgrade_reason=billing_lifecycle.DOWNGRADE_MONTHLY_REQUEST_LIMIT,
            event_type=billing_lifecycle.EVENT_DOWNGRADED_MONTHLY_REQUEST_LIMIT,
            detail="irrelevant",
        )

    assert session.committed is False
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_downgrade_for_monthly_limit_idempotent_when_already_free():
    """A stale JWT still claiming 'pro' keeps hitting the calling dependency
    on every request until refreshed — this must not re-write an audit row
    or resend the notification email on every one of those repeat hits."""
    user = make_user(tier="free")
    user.tier_downgrade_reason = billing_lifecycle.DOWNGRADE_MONTHLY_REQUEST_LIMIT
    session = FakeAsyncSession(lookup_result=user)

    with (
        patch_sessionmaker(session),
        patch("api.middleware.billing_lifecycle.send_tier_change_email") as mock_send,
    ):
        await billing_lifecycle.downgrade_for_monthly_limit(
            user_id="user-123",
            downgrade_reason=billing_lifecycle.DOWNGRADE_MONTHLY_REQUEST_LIMIT,
            event_type=billing_lifecycle.EVENT_DOWNGRADED_MONTHLY_REQUEST_LIMIT,
            detail="irrelevant",
        )

    assert session.committed is False
    assert len(session.added) == 0
    mock_send.assert_not_called()


# ── restore_after_payment_succeeded ──────────────────────────────────────────


def test_restore_after_payment_succeeded_flips_free_to_pro():
    session = FakeAsyncSession()
    user = make_user(tier="free")
    user.tier_downgrade_reason = billing_lifecycle.DOWNGRADE_MONTHLY_REQUEST_LIMIT

    result = billing_lifecycle.restore_after_payment_succeeded(
        session, user, stripe_event_id="evt_123"
    )

    assert result == billing_lifecycle.EVENT_RESTORED_AFTER_PAYMENT_SUCCEEDED
    assert user.tier == "pro"
    assert user.tier_downgrade_reason is None
    assert len(session.added) == 1
    event = session.added[0]
    assert event.old_tier == "free"
    assert event.new_tier == "pro"
    assert event.stripe_event_id == "evt_123"
    assert session.committed is False  # caller commits


def test_restore_after_payment_succeeded_noop_when_already_pro():
    session = FakeAsyncSession()
    user = make_user(tier="pro")

    result = billing_lifecycle.restore_after_payment_succeeded(session, user)

    assert result is None
    assert len(session.added) == 0
    assert user.tier == "pro"

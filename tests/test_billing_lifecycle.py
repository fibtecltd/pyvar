"""
tests/test_billing_lifecycle.py — unit tests for
api/middleware/billing_lifecycle.py (item 5 §8 follow-on).

Reasoning:
- The DB session is a fake that only records what is added; no real Postgres.
- The downgrade-for-a-monthly-cap and restore-after-payment paths were removed on 2026-11-21 (docs/plan-pro-tier-stripe.md);
  the last tests here pin that they are gone.
- boto3.client is patched directly (never a real SES call), same boundary as
  tests/test_auth.py's send_verification_email coverage.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.middleware import billing_lifecycle
from storage.models import BillingEvent

# ── Fakes ──────────────────────────────────────────────────────────────────────


class FakeAsyncSession:
    def __init__(self):
        self.added: list = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


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
        billing_lifecycle.send_tier_change_email(
            "user@example.com", billing_lifecycle.EVENT_UPGRADED
        )

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


# ── what no longer exists ─────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "downgrade_for_monthly_limit",
        "restore_after_payment_succeeded",
        "DOWNGRADE_PAYMENT_FAILED",
        "DOWNGRADE_MONTHLY_REQUEST_LIMIT",
        "DOWNGRADE_MONTHLY_SIMULATION_LIMIT",
        "EVENT_DOWNGRADED_PAYMENT_FAILED",
        "EVENT_DOWNGRADED_MONTHLY_REQUEST_LIMIT",
        "EVENT_DOWNGRADED_MONTHLY_SIMULATION_LIMIT",
        "EVENT_RESTORED_AFTER_PAYMENT_SUCCEEDED",
    ],
)
def test_the_paths_that_moved_a_pro_account_to_free_are_gone(name):
    """A monthly cap and a failed payment no longer change a tier (docs/plan-pro-tier-stripe.md): a cap is a
    429 and Stripe retries a failed payment. If one of these names comes back, a Pro account can be moved to Free
    by something other than the end of its Stripe subscription."""
    assert not hasattr(billing_lifecycle, name)


def test_the_only_event_that_moves_pro_to_free_has_an_email():
    copy = billing_lifecycle._NOTIFICATION_COPY[
        billing_lifecycle.EVENT_DOWNGRADED_SUBSCRIPTION_CANCELLED
    ]
    assert "cancelled" in copy[1] and "Free plan" in copy[1]
    assert "failed" not in copy[0].lower()


def test_the_welcome_email_says_what_cancelling_does():
    _, body = billing_lifecycle._NOTIFICATION_COPY[billing_lifecycle.EVENT_UPGRADED]
    assert "cancel" in body and "end of the period you have paid for" in body

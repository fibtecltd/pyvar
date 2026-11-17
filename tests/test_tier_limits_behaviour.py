"""tests/test_tier_limits_behaviour.py — what each tier gets today, pinned before the tier-policy refactor (A1).

Reasoning:
- api/tiers.py puts every tier's limits in one table that the auth, rate-limit, VaR and assistant code read. The
  refactor must change nothing for the four tiers that exist ("free", "pro", "enterprise", "internal") nor for an
  unknown tier, which gets the free tier's limits. These tests were written and run against the code BEFORE the
  refactor and pass unchanged after it.
- The configured numbers are replaced by distinct sentinels, so a test fails if a limit is read from the wrong
  setting, not only if a number changes.
- No backing service is used: the rate limiter is replaced by a recorder of the items it is asked to hit.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.middleware import rate_limit as rate_limit_module
from api.middleware.auth import TokenPayload
from api.middleware.rate_limit import (
    cfg,
    enforce_assistant_rate_limit,
    enforce_compute_rate_limit,
)

SENTINELS = {
    "rate_limit_free_daily": 7,
    "rate_limit_pro_daily": 70,
    "rate_limit_pro_monthly_requests": 700,
    "rate_limit_pro_monthly_simulations": 7_000_000,
    "assistant_quota_free_daily": 3,
    "assistant_quota_pro_daily": 30,
    "assistant_quota_enterprise_daily": 300,
    "assistant_quota_anon_per_hour": 11,
}


class FakeRequest:
    headers: dict = {}
    client = MagicMock(host="10.0.0.1")


@pytest.fixture
def sentinels():
    with patch.multiple(cfg, **SENTINELS):
        yield


@pytest.fixture
def hits():
    """Every (amount, granularity, identifiers) the limiter is asked to hit."""
    recorded: list[tuple[int, str, tuple]] = []

    def hit(item, *identifiers, **kwargs):
        recorded.append((item.amount, item.GRANULARITY.name, identifiers))
        return True

    fake = MagicMock()
    fake.limiter.hit.side_effect = hit
    with patch.object(rate_limit_module, "_limiter", fake):
        yield recorded


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        ("free", 10_000),
        ("pro", 100_000),
        ("enterprise", 500_000),
        ("internal", 500_000),
        ("mystery", 10_000),
    ],
)
def test_the_simulation_cap_per_tier(tier: str, expected: int) -> None:
    assert TokenPayload("u", tier).max_simulations == expected


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        ("free", [(7, "day", ("u", "compute"))]),
        ("pro", [(70, "day", ("u", "compute")), (700, "month", ("u", "compute-monthly"))]),
        ("enterprise", []),
        ("internal", []),
        ("mystery", [(7, "day", ("u", "compute"))]),
    ],
)
@pytest.mark.asyncio
async def test_the_compute_quota_per_tier(sentinels, hits, tier, expected) -> None:
    await enforce_compute_rate_limit(FakeRequest(), TokenPayload("u", tier))
    assert hits == expected


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        ("free", (3, "day")),
        ("pro", (30, "day")),
        ("enterprise", (300, "day")),
        ("internal", (300, "day")),
        ("mystery", (3, "day")),
    ],
)
@pytest.mark.asyncio
async def test_the_assistant_quota_per_tier(sentinels, hits, tier, expected) -> None:
    await enforce_assistant_rate_limit(FakeRequest(), TokenPayload("u", tier))
    assert hits == [(*expected, ("u", "assistant"))]


@pytest.mark.asyncio
async def test_the_anonymous_assistant_quota_is_per_ip_per_hour(sentinels, hits) -> None:
    await enforce_assistant_rate_limit(FakeRequest(), None)
    assert hits == [(11, "hour", ("10.0.0.1", "assistant-anon"))]

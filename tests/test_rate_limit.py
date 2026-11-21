"""
tests/test_rate_limit.py — unit tests for api/middleware/rate_limit.py (#146)

Reasoning:
- Never hit a real backing service in tests (project rule, see
  tests/test_auth.py's own docstring): tests/conftest.py's autouse
  `_isolated_rate_limiter` fixture already swaps the module-level `_limiter`
  singleton for a fresh, per-test slowapi Limiter backed by `limits`' own
  in-memory storage (storage_uri="memory://") — `memory_limiter` below is
  just a locally-named alias onto that same fixture. This exercises the
  exact same `.limiter.hit()` / `.limiter.get_window_stats()` call path as
  production — only the storage backend differs — and needs no new test
  dependency.
- get_trusted_client_ip is tested against a minimal fake Request (only
  `.headers` and `.client.host` are ever touched) rather than constructing
  a real Starlette Request from an ASGI scope, which would be much more
  code for the same coverage.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.middleware.auth import TokenPayload
from api.middleware.rate_limit import (
    cfg,
    enforce_compute_rate_limit,
    enforce_public_rate_limit,
    enforce_register_rate_limit,
    get_trusted_client_ip,
)

# ── Fakes ──────────────────────────────────────────────────────────────────────


class FakeClient:
    def __init__(self, host: str | None):
        self.host = host


class FakeRequest:
    """Only what get_trusted_client_ip / get_remote_address touch."""

    def __init__(self, headers: dict | None = None, client_host: str | None = "10.0.0.1"):
        self.headers = headers or {}
        self.client = FakeClient(client_host) if client_host is not None else None


@pytest.fixture
def memory_limiter(_isolated_rate_limiter):
    """Local name for tests/conftest.py's autouse, per-test in-memory limiter."""
    return _isolated_rate_limiter


# ── get_trusted_client_ip ────────────────────────────────────────────────────


def test_get_trusted_client_ip_no_xff_falls_back_to_direct_peer():
    request = FakeRequest(headers={}, client_host="203.0.113.5")
    assert get_trusted_client_ip(request) == "203.0.113.5"


def test_get_trusted_client_ip_single_hop_falls_back_to_direct_peer():
    """One entry isn't enough to trust — could be entirely client-supplied."""
    request = FakeRequest(headers={"x-forwarded-for": "1.2.3.4"}, client_host="10.0.0.7")
    assert get_trusted_client_ip(request) == "10.0.0.7"


def test_get_trusted_client_ip_two_hops_picks_second_to_last():
    """CloudFront's own appended hop (real client) — not the ALB's (last)."""
    request = FakeRequest(headers={"x-forwarded-for": "9.9.9.9, 203.0.113.5, 10.0.0.99"})
    assert get_trusted_client_ip(request) == "203.0.113.5"


def test_get_trusted_client_ip_exactly_two_hops():
    request = FakeRequest(headers={"x-forwarded-for": "203.0.113.5, 10.0.0.99"})
    assert get_trusted_client_ip(request) == "203.0.113.5"


# ── enforce_compute_rate_limit ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compute_rate_limit_allows_under_quota(memory_limiter):
    with patch.object(cfg, "rate_limit_free_daily", 3):
        user = TokenPayload(sub="user-a", tier="free")
        request = FakeRequest()
        for _ in range(3):
            await enforce_compute_rate_limit(request, user)  # must not raise


@pytest.mark.asyncio
async def test_compute_rate_limit_blocks_over_quota(memory_limiter):
    with patch.object(cfg, "rate_limit_free_daily", 2):
        user = TokenPayload(sub="user-b", tier="free")
        request = FakeRequest()
        await enforce_compute_rate_limit(request, user)
        await enforce_compute_rate_limit(request, user)
        with pytest.raises(Exception) as exc_info:
            await enforce_compute_rate_limit(request, user)
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers


@pytest.mark.asyncio
async def test_compute_rate_limit_pro_uses_pro_quota(memory_limiter):
    with (
        patch.object(cfg, "rate_limit_free_daily", 1),
        patch.object(cfg, "rate_limit_pro_daily", 5),
    ):
        user = TokenPayload(sub="user-c", tier="pro")
        request = FakeRequest()
        for _ in range(5):
            await enforce_compute_rate_limit(request, user)  # would fail at free's cap of 1


@pytest.mark.asyncio
async def test_compute_rate_limit_free_and_pro_are_separate_buckets(memory_limiter):
    """Different users, same tier-appropriate cap — one user's usage must not
    consume another user's quota (keyed by user_id, not just tier)."""
    with patch.object(cfg, "rate_limit_free_daily", 1):
        request = FakeRequest()
        await enforce_compute_rate_limit(request, TokenPayload(sub="user-d", tier="free"))
        await enforce_compute_rate_limit(request, TokenPayload(sub="user-e", tier="free"))


@pytest.mark.parametrize("tier", ["enterprise", "internal"])
@pytest.mark.asyncio
async def test_compute_rate_limit_exempt_tiers_unlimited(memory_limiter, tier):
    with patch.object(cfg, "rate_limit_free_daily", 1):
        user = TokenPayload(sub="user-f", tier=tier)
        request = FakeRequest()
        for _ in range(10):
            await enforce_compute_rate_limit(request, user)  # never throttled


@pytest.mark.asyncio
async def test_compute_rate_limit_fails_open_on_storage_error(memory_limiter):
    """An ElastiCache outage must never block a compute request."""
    with patch.object(memory_limiter.limiter, "hit", side_effect=RuntimeError("redis down")):
        user = TokenPayload(sub="user-g", tier="free")
        await enforce_compute_rate_limit(FakeRequest(), user)  # must not raise


# ── Monthly request-count cap, Pro (docs/plan-pro-tier-stripe.md) ────────────


@pytest.mark.asyncio
async def test_compute_rate_limit_pro_monthly_cap_is_a_429_that_names_the_cap(memory_limiter):
    """Breaching the monthly cap is a refusal until the window resets: a 429 with Retry-After and a message that
    names the plan and the cap. The account's tier is not touched."""
    with (
        patch.object(cfg, "rate_limit_pro_daily", 100),
        patch.object(cfg, "rate_limit_pro_monthly_requests", 2),
    ):
        user = TokenPayload(sub="user-i", tier="pro")
        request = FakeRequest()
        await enforce_compute_rate_limit(request, user)
        await enforce_compute_rate_limit(request, user)
        with pytest.raises(HTTPException) as exc_info:
            await enforce_compute_rate_limit(request, user)

    error = exc_info.value
    assert error.status_code == 429
    assert "Pro plan allows 2 requests in each 30-day window" in error.detail
    assert "refused until the window resets" in error.detail
    assert int(error.headers["Retry-After"]) > 0


@pytest.mark.asyncio
async def test_a_pro_account_stays_refused_for_the_rest_of_the_window(memory_limiter):
    with (
        patch.object(cfg, "rate_limit_pro_daily", 100),
        patch.object(cfg, "rate_limit_pro_monthly_requests", 1),
    ):
        user = TokenPayload(sub="user-i2", tier="pro")
        await enforce_compute_rate_limit(FakeRequest(), user)
        for _ in range(3):
            with pytest.raises(HTTPException) as exc_info:
                await enforce_compute_rate_limit(FakeRequest(), user)
            assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_two_keys_of_one_account_share_one_daily_and_one_monthly_counter(memory_limiter):
    """Both counters are keyed by the account, never the key: a second key (or a re-created one) is not a fresh
    allowance. A key resolves to the same TokenPayload.sub as the session that made it."""
    with (
        patch.object(cfg, "rate_limit_pro_daily", 100),
        patch.object(cfg, "rate_limit_pro_monthly_requests", 3),
    ):
        key_one = TokenPayload(sub="account-one", tier="pro")
        key_two = TokenPayload(sub="account-one", tier="pro")  # another key, the same account
        other_account = TokenPayload(sub="account-two", tier="pro")
        await enforce_compute_rate_limit(FakeRequest(), key_one)
        await enforce_compute_rate_limit(FakeRequest(), key_two)
        await enforce_compute_rate_limit(FakeRequest(), key_one)
        with pytest.raises(HTTPException) as exc_info:
            await enforce_compute_rate_limit(FakeRequest(), key_two)
        assert exc_info.value.status_code == 429
        await enforce_compute_rate_limit(
            FakeRequest(), other_account
        )  # a different account is unaffected


@pytest.mark.asyncio
async def test_compute_rate_limit_free_tier_not_subject_to_monthly_cap(memory_limiter):
    """Free has no monthly cap: the Pro setting must not reach it."""
    with (
        patch.object(cfg, "rate_limit_free_daily", 100),
        patch.object(cfg, "rate_limit_pro_monthly_requests", 1),
    ):
        user = TokenPayload(sub="user-j", tier="free")
        request = FakeRequest()
        for _ in range(5):
            await enforce_compute_rate_limit(request, user)  # never throttled


@pytest.mark.asyncio
async def test_compute_rate_limit_monthly_check_fails_open_on_storage_error(memory_limiter):
    """An ElastiCache outage on the monthly check specifically must not block the request."""
    real_hit = memory_limiter.limiter.hit

    def flaky_hit(item, *identifiers, cost=1):
        if "compute-monthly" in identifiers:
            raise RuntimeError("redis down")
        return real_hit(item, *identifiers, cost=cost)

    with (
        patch.object(cfg, "rate_limit_pro_daily", 100),
        patch.object(memory_limiter.limiter, "hit", side_effect=flaky_hit),
    ):
        user = TokenPayload(sub="user-k", tier="pro")
        await enforce_compute_rate_limit(FakeRequest(), user)  # must not raise


# ── enforce_public_rate_limit ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_public_rate_limit_allows_under_quota(memory_limiter):
    with patch.object(cfg, "rate_limit_unauth_per_hour", 2):
        request = FakeRequest(client_host="198.51.100.1")
        await enforce_public_rate_limit(request)
        await enforce_public_rate_limit(request)


@pytest.mark.asyncio
async def test_public_rate_limit_blocks_over_quota(memory_limiter):
    with patch.object(cfg, "rate_limit_unauth_per_hour", 1):
        request = FakeRequest(client_host="198.51.100.2")
        await enforce_public_rate_limit(request)
        with pytest.raises(Exception) as exc_info:
            await enforce_public_rate_limit(request)
        assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_public_rate_limit_keyed_by_trusted_ip_not_alb_peer(memory_limiter):
    """Two different real clients behind the same ALB peer must not share a bucket."""
    with patch.object(cfg, "rate_limit_unauth_per_hour", 1):
        request_a = FakeRequest(
            headers={"x-forwarded-for": "1.1.1.1, 10.0.0.9"}, client_host="10.0.0.9"
        )
        request_b = FakeRequest(
            headers={"x-forwarded-for": "2.2.2.2, 10.0.0.9"}, client_host="10.0.0.9"
        )
        await enforce_public_rate_limit(request_a)
        await enforce_public_rate_limit(request_b)  # different real IP — not throttled


# ── enforce_register_rate_limit ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_rate_limit_allows_under_quota(memory_limiter):
    with patch.object(cfg, "rate_limit_register_per_hour", 2):
        request = FakeRequest(client_host="198.51.100.10")
        await enforce_register_rate_limit(request)
        await enforce_register_rate_limit(request)


@pytest.mark.asyncio
async def test_register_rate_limit_blocks_over_quota(memory_limiter):
    with patch.object(cfg, "rate_limit_register_per_hour", 1):
        request = FakeRequest(client_host="198.51.100.11")
        await enforce_register_rate_limit(request)
        with pytest.raises(Exception) as exc_info:
            await enforce_register_rate_limit(request)
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers


@pytest.mark.asyncio
async def test_register_rate_limit_keyed_by_trusted_ip_not_alb_peer(memory_limiter):
    """Two different real clients behind the same ALB peer must not share a bucket."""
    with patch.object(cfg, "rate_limit_register_per_hour", 1):
        request_a = FakeRequest(
            headers={"x-forwarded-for": "3.3.3.3, 10.0.0.9"}, client_host="10.0.0.9"
        )
        request_b = FakeRequest(
            headers={"x-forwarded-for": "4.4.4.4, 10.0.0.9"}, client_host="10.0.0.9"
        )
        await enforce_register_rate_limit(request_a)
        await enforce_register_rate_limit(request_b)  # different real IP — not throttled


@pytest.mark.asyncio
async def test_register_rate_limit_separate_bucket_from_public_rate_limit(memory_limiter):
    """Register and /public/* share an IP-keyed limiter instance but must not
    share a quota bucket — a client shouldn't be able to exhaust one via the
    other."""
    with (
        patch.object(cfg, "rate_limit_register_per_hour", 1),
        patch.object(cfg, "rate_limit_unauth_per_hour", 1),
    ):
        request = FakeRequest(client_host="198.51.100.12")
        await enforce_register_rate_limit(request)
        await enforce_public_rate_limit(request)  # separate scope — not throttled


@pytest.mark.asyncio
async def test_register_rate_limit_fails_open_on_storage_error(memory_limiter):
    """An ElastiCache outage must never block registration."""
    with patch.object(memory_limiter.limiter, "hit", side_effect=RuntimeError("redis down")):
        await enforce_register_rate_limit(FakeRequest())  # must not raise

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

from api.middleware.auth import TokenPayload
from api.middleware.rate_limit import (
    cfg,
    enforce_compute_rate_limit,
    enforce_public_rate_limit,
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

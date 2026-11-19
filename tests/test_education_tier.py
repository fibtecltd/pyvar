"""tests/test_education_tier.py — what an education account may do, and when it stops counting as one (A2 PR 1).

Reasoning:
- docs/plan-education-tier.md sets the limits (100 requests a day, 2,000 a month, 20 a minute, 100,000
  simulations a request, 1,000,000 VaR simulations a month, a shared pool of 5,000 education VaR jobs a month) and
  two rules that are easy to break quietly: a monthly breach is a 429 that changes nothing about the account (Pro's
  breach downgrades it), and an education account whose grant has lapsed is a free account everywhere a tier
  leaves the database. Both are pinned here against the real limiter (in-memory storage, from tests/conftest.py)
  and the real routes.
- The numbers of other tiers are pinned elsewhere (tests/test_tier_limits_behaviour.py); this file adds the
  education row and the three ways it differs from every other row.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from api import tiers
from api.middleware import rate_limit as rate_limit_module
from api.middleware.auth import TokenPayload, create_access_token
from api.middleware.rate_limit import enforce_compute_rate_limit
from api.tiers import effective_tier, policy_for, seconds_until_expiry
from config import get_settings
from main import create_app
from tests.test_api import FakeAsyncSession, patch_sessionmaker

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
cfg = get_settings()


@pytest.fixture
def enabled():
    with patch.object(cfg, "education_tier_enabled", True):
        yield


class FakeRequest:
    headers: dict = {}
    client = MagicMock(host="10.0.0.1")


def education_user(user_id: str = "edu-1") -> TokenPayload:
    return TokenPayload(sub=user_id, tier="education")


async def call(user: TokenPayload) -> None:
    await enforce_compute_rate_limit(FakeRequest(), user)


# ── effective_tier: one place turns (tier, expiry) into a tier ─────────────────────────────────────────────


@pytest.mark.parametrize("tier", ["free", "pro", "enterprise", "internal", "trial", "anything"])
def test_a_tier_other_than_education_is_returned_as_stored(enabled, tier: str) -> None:
    assert effective_tier(tier, None, NOW) == tier
    assert effective_tier(tier, NOW - timedelta(days=400), NOW) == tier  # an old date means nothing


def test_education_counts_only_while_the_expiry_is_in_the_future(enabled) -> None:
    assert effective_tier("education", NOW + timedelta(seconds=1), NOW) == "education"
    assert effective_tier("education", NOW, NOW) == "free"  # at the instant, it has ended
    assert effective_tier("education", NOW - timedelta(days=1), NOW) == "free"


def test_education_with_no_expiry_is_free(enabled) -> None:
    assert effective_tier("education", None, NOW) == "free"


def test_a_naive_expiry_is_read_as_utc(enabled) -> None:
    future = (NOW + timedelta(days=3)).replace(tzinfo=None)
    assert effective_tier("education", future, NOW) == "education"
    assert (
        effective_tier("education", (NOW - timedelta(days=3)).replace(tzinfo=None), NOW) == "free"
    )


def test_with_the_flag_off_every_education_account_is_free() -> None:
    assert cfg.education_tier_enabled is False  # the shipped default
    assert effective_tier("education", NOW + timedelta(days=100), NOW) == "free"


def test_a_stripe_upgrade_survives_the_old_expiry(enabled) -> None:
    # The expiry applies only while the tier is "education": a checkout that sets "pro" needs no cleanup.
    assert effective_tier("pro", NOW - timedelta(days=1), NOW) == "pro"


def test_seconds_until_expiry_is_only_for_an_education_grant() -> None:
    assert seconds_until_expiry("education", NOW + timedelta(seconds=90), NOW) == 90
    assert seconds_until_expiry("education", NOW - timedelta(seconds=90), NOW) == 0
    assert seconds_until_expiry("education", None, NOW) is None
    assert seconds_until_expiry("pro", NOW + timedelta(days=1), NOW) is None


# ── the row ────────────────────────────────────────────────────────────────────────────────────────────────


def test_the_education_row_is_the_plans_numbers() -> None:
    row = policy_for("education")
    assert (row.max_simulations, row.daily_requests, row.monthly_requests) == (100_000, 100, 2_000)
    assert (row.monthly_simulations, row.burst_per_minute) == (1_000_000, 20)
    assert row.monthly_breach == "refuse"
    assert (row.assistant_group, row.assistant_daily) == ("free", cfg.assistant_quota_free_daily)


def test_only_pro_downgrades_on_a_monthly_breach() -> None:
    assert {name: policy_for(name).monthly_breach for name in tiers.KNOWN_TIERS} == {
        "free": "downgrade",
        "pro": "downgrade",
        "enterprise": "downgrade",
        "internal": "downgrade",
        "trial": "downgrade",
        "education": "refuse",
    }
    assert [n for n in tiers.KNOWN_TIERS if policy_for(n).burst_per_minute is not None] == [
        "education"
    ]


def test_the_shipped_defaults_are_off_and_the_plans_caps() -> None:
    assert cfg.education_tier_enabled is False
    assert (cfg.education_cohort_cap, cfg.education_domain_cap) == (25, 10)
    assert (cfg.education_default_months, cfg.education_max_months) == (6, 12)
    assert cfg.education_var_pool_monthly == 5_000
    assert cfg.admin_token_ttl_seconds == 600


# ── limits: a breach is a refusal, never a downgrade ──────────────────────────────────────────────────────


async def test_the_daily_limit_is_a_429() -> None:
    with patch.object(cfg, "rate_limit_education_daily", 3):
        for _ in range(3):
            await call(education_user())
        with pytest.raises(HTTPException) as refused:
            await call(education_user())
    assert refused.value.status_code == 429


async def test_the_burst_limit_is_a_429_and_does_not_use_up_the_days_quota() -> None:
    with patch.object(cfg, "rate_limit_education_burst_per_minute", 2):
        await call(education_user())
        await call(education_user())
        with pytest.raises(HTTPException) as refused:
            await call(education_user())
    assert refused.value.status_code == 429
    limiter = rate_limit_module._limiter.limiter
    import limits

    _, remaining = limiter.get_window_stats(limits.parse("100/day"), "edu-1", "compute")
    assert remaining == 98  # two requests counted; the refused burst was not


async def test_a_monthly_breach_is_a_429_and_never_calls_the_pro_downgrade() -> None:
    downgrade = AsyncMock()
    with (
        patch.object(cfg, "rate_limit_education_monthly_requests", 2),
        patch.object(cfg, "rate_limit_education_burst_per_minute", 50),
        patch.object(rate_limit_module, "downgrade_for_monthly_limit", downgrade),
    ):
        await call(education_user())
        await call(education_user())
        with pytest.raises(HTTPException) as refused:
            await call(education_user())
    assert refused.value.status_code == 429  # Pro's breach is a 403 with the "moved to Free" text
    assert "downgrad" not in str(refused.value.detail).lower()
    downgrade.assert_not_called()


async def test_a_pro_monthly_breach_still_downgrades() -> None:
    downgrade = AsyncMock()
    with (
        patch.object(cfg, "rate_limit_pro_monthly_requests", 1),
        patch.object(rate_limit_module, "downgrade_for_monthly_limit", downgrade),
    ):
        await call(TokenPayload(sub="pro-1", tier="pro"))
        with pytest.raises(HTTPException) as refused:
            await call(TokenPayload(sub="pro-1", tier="pro"))
    assert refused.value.status_code == 403
    downgrade.assert_awaited_once()


# ── the pool of education VaR jobs ────────────────────────────────────────────────────────────────────────


def test_the_pool_is_shared_and_runs_out() -> None:
    with patch.object(cfg, "education_var_pool_monthly", 2):
        assert rate_limit_module.limits_tier_for("education") == "education"
        assert rate_limit_module.take_education_pool_job() is True
        assert rate_limit_module.take_education_pool_job() is True
        assert rate_limit_module.take_education_pool_job() is False
        assert rate_limit_module.limits_tier_for("education") == "free"
        assert rate_limit_module.limits_tier_for("pro") == "pro"  # nobody else is affected
        assert rate_limit_module.limits_tier_for("free") == "free"


def test_reading_the_pool_takes_nothing_from_it() -> None:
    with patch.object(cfg, "education_var_pool_monthly", 1):
        for _ in range(5):
            assert rate_limit_module.education_pool_has_room() is True
        assert rate_limit_module.take_education_pool_job() is True
        assert rate_limit_module.education_pool_has_room() is False


async def test_once_the_pool_is_spent_every_education_request_gets_the_free_daily_quota() -> None:
    with (
        patch.object(cfg, "education_var_pool_monthly", 1),
        patch.object(cfg, "rate_limit_free_daily", 2),
    ):
        assert rate_limit_module.take_education_pool_job() is True
        await call(education_user("pooled"))
        await call(education_user("pooled"))
        with pytest.raises(HTTPException) as refused:
            await call(education_user("pooled"))  # free's 2 a day, not education's 100
    assert refused.value.status_code == 429


def test_a_storage_error_leaves_the_pool_open() -> None:
    broken = MagicMock()
    broken.limiter.test.side_effect = RuntimeError("redis is down")
    broken.limiter.hit.side_effect = RuntimeError("redis is down")
    with patch.object(rate_limit_module, "_limiter", broken):
        assert rate_limit_module.education_pool_has_room() is True
        assert rate_limit_module.take_education_pool_job() is True
        assert rate_limit_module.limits_tier_for("education") == "education"


# ── POST /var/compute ─────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def payload() -> dict:
    from ingestion.fixtures import generate_gbm_returns

    return {
        "portfolio_value": 1_000_000.0,
        "returns": generate_gbm_returns(n_obs=252, seed=42).tolist(),
        "confidence_level": 0.99,
        "horizon_days": 1,
        "n_simulations": 100_000,
        "seed": 42,
    }


async def submit(payload: dict, n_simulations: int, token: str, user_tier: str = "education"):
    body = {**payload, "n_simulations": n_simulations}
    task = MagicMock()
    task.id = "task-1"
    with (
        patch_sessionmaker(FakeAsyncSession()),
        patch("api.routes.var.compute_var_task.apply_async", return_value=task) as apply,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/var/compute", json=body, headers={"Authorization": f"Bearer {token}"}
            )
    return response, apply


async def test_an_education_var_job_may_use_100000_simulations(payload) -> None:
    token = create_access_token("edu-var", "education")
    response, apply = await submit(payload, 100_000, token)
    assert response.status_code == 202
    apply.assert_called_once()


async def test_one_more_simulation_than_the_education_cap_is_a_403(payload) -> None:
    token = create_access_token("edu-var", "education")
    response, apply = await submit(payload, 100_001, token)
    assert response.status_code == 403  # the route's tier cap, not the schema's own ceiling
    assert "100,000" in response.json()["detail"]
    apply.assert_not_called()


async def test_when_the_pool_is_spent_a_var_job_gets_the_free_simulation_cap(payload) -> None:
    token = create_access_token("edu-var", "education")
    with patch.object(cfg, "education_var_pool_monthly", 1):
        first, _ = await submit(payload, 50_000, token)  # takes the one job in the pool
        second, apply = await submit(payload, 50_000, token)  # the pool is spent: free's 10,000
        third, apply_ok = await submit(payload, 10_000, token)
    assert first.status_code == 202
    assert second.status_code == 403
    assert "'free'" in second.json()["detail"] and "10,000" in second.json()["detail"]
    apply.assert_not_called()
    assert third.status_code == 202
    apply_ok.assert_called_once()


async def test_a_var_job_of_another_tier_never_touches_the_pool(payload) -> None:
    token = create_access_token("pro-var", "pro")
    with patch.object(cfg, "education_var_pool_monthly", 1):
        response, _ = await submit(payload, 50_000, token, user_tier="pro")
        assert rate_limit_module.education_pool_has_room() is True
    assert response.status_code == 202


async def test_the_monthly_simulation_breach_is_a_429_and_never_a_downgrade(payload) -> None:
    token = create_access_token("edu-sims", "education")
    downgrade = AsyncMock()
    with (
        patch.object(cfg, "rate_limit_education_monthly_simulations", 120_000),
        patch("api.routes.var.downgrade_for_monthly_limit", downgrade),
    ):
        first, _ = await submit(payload, 100_000, token)
        second, apply = await submit(payload, 100_000, token)  # 200,000 > 120,000
    assert first.status_code == 202
    assert second.status_code == 429
    apply.assert_not_called()
    downgrade.assert_not_called()

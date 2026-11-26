"""The typed assistant's allowlist, and the switches that keep a whole audience out (docs/assistant-runbook.md).

Reasoning:
- While `assistant_allowlist_enabled` is on (the first weeks in prod), only signed-in accounts in the Redis set
  `pyvar:assistant:allow` may ask. The promises pinned here: it is OFF by default and then the set is never read;
  an anonymous visitor and an unlisted account are refused with 503 `assistant_closed` BEFORE the model key, the
  concurrency slot and the quota, so a refusal calls no model and uses no quota; the kill switch and the spend cap
  are still checked first; an unreadable set FAILS CLOSED (503 `assistant_unavailable`, logged as
  `assistant_store_unavailable`, the line the CDK alarm counts); a bad credential is a 401, never a quiet downgrade
  to "anonymous"; and the dependency order in routes.py is the one CLAUDE.md 3.7 describes.
- The second half is the other way to keep an audience out without a deploy of new code: a quota of 0. Anonymous
  visitors are closed out with `assistant_quota_anon_per_hour = 0`, and one tier with `assistant_quota_<tier>_daily
  = 0` (enterprise, whose answers are not audited, stays off this way). These go through the real route and the real
  limiter, not the `limits` library alone: a 0 quota is a 429, calls no model, and leaves every other caller alone.
- Same harness as tests/test_assistant_gateway.py (the real app, the model client and the store replaced through
  `dependency_overrides`, the in-memory rate limiter tests/conftest.py installs); the Redis stand-in gains the one
  set command the allowlist uses.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import structlog.testing

from api.assistant import deps
from api.assistant.routes import router
from api.assistant.store import ALLOW_KEY, KILL_KEY, AssistantStore, StoreUnavailable, spend_key
from api.middleware.auth import create_access_token
from config import get_settings
from tests.test_assistant_gateway import FakeRedis, Gateway, counter, ok_reply

cfg = get_settings()


class AllowRedis(FakeRedis):
    """The gateway's Redis stand-in plus the one set command the allowlist uses (and a record of its reads)."""

    def __init__(self) -> None:
        super().__init__()
        self.sets: dict[str, set[str]] = {}
        self.fail_allow = False
        self.reads: list[tuple[str, str]] = []

    async def sismember(self, key: str, member: str) -> bool:
        self.reads.append((key, member))
        if self.fail_allow:
            raise ConnectionError("redis is down")
        return member in self.sets.get(key, set())

    def allow(self, *accounts: str) -> None:
        self.sets.setdefault(ALLOW_KEY, set()).update(accounts)


@pytest.fixture
def gw(monkeypatch: pytest.MonkeyPatch) -> Iterator[Gateway]:
    monkeypatch.setattr(cfg, "assistant_enabled", True)
    monkeypatch.setattr(cfg, "assistant_typed_enabled", True)
    monkeypatch.setattr(deps, "_inflight", 0)
    monkeypatch.setattr(deps, "_client", None)
    gateway = Gateway()
    gateway.redis = AllowRedis()  # the app's store override reads `gateway.redis` at call time
    yield gateway


def redis_of(gateway: Gateway) -> AllowRedis:
    assert isinstance(gateway.redis, AllowRedis)
    return gateway.redis


@pytest.fixture
def closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "assistant_allowlist_enabled", True)


def code_of(response: Any) -> str:
    return response.json()["detail"]["code"]


# ── off by default ──────────────────────────────────────────────────────────────


async def test_the_allowlist_is_off_by_default_and_the_set_is_never_read(gw: Gateway) -> None:
    assert cfg.assistant_allowlist_enabled is False  # the committed default
    client = gw.use(ok_reply(), ok_reply())
    assert (await gw.post()).status_code == 200  # anonymous
    assert (await gw.post(token=create_access_token("user-a", "free"))).status_code == 200
    assert len(client.calls) == 2 and redis_of(gw).reads == []


# ── on: who is let in ───────────────────────────────────────────────────────────


async def test_an_anonymous_visitor_is_closed_out_and_nothing_is_called(
    gw: Gateway, closed: None
) -> None:
    client = gw.use(ok_reply())
    before = counter("pyvar_assistant_refused_total", reason="closed", tier="anon")
    response = await gw.post()
    assert response.status_code == 503 and code_of(response) == "assistant_closed"
    assert response.json()["detail"]["hint"].startswith("The buttons")
    assert (
        client.calls == [] and redis_of(gw).reads == []
    )  # an anonymous caller has no account to look up
    assert counter("pyvar_assistant_refused_total", reason="closed", tier="anon") == before + 1


async def test_an_account_that_is_not_listed_is_closed_out(gw: Gateway, closed: None) -> None:
    redis_of(gw).allow("someone-else")
    client = gw.use(ok_reply())
    before = counter("pyvar_assistant_refused_total", reason="closed", tier="free")
    response = await gw.post(token=create_access_token("user-a", "free"))
    assert response.status_code == 503 and code_of(response) == "assistant_closed"
    assert client.calls == []
    assert redis_of(gw).reads == [(ALLOW_KEY, "user-a")]
    assert counter("pyvar_assistant_refused_total", reason="closed", tier="free") == before + 1


@pytest.mark.parametrize("tier", ["free", "pro", "enterprise"])
async def test_a_listed_account_is_answered_whatever_its_tier(
    gw: Gateway, closed: None, tier: str
) -> None:
    redis_of(gw).allow("user-a")
    client = gw.use(ok_reply())
    response = await gw.post(token=create_access_token("user-a", tier))
    assert response.status_code == 200 and len(client.calls) == 1


async def test_the_set_is_per_account_not_per_tier(gw: Gateway, closed: None) -> None:
    redis_of(gw).allow("user-a")
    gw.use(ok_reply(), ok_reply())
    assert (await gw.post(token=create_access_token("user-a", "pro"))).status_code == 200
    other = await gw.post(token=create_access_token("user-b", "pro"))
    assert other.status_code == 503 and code_of(other) == "assistant_closed"


async def test_a_removed_account_is_closed_out_at_once(gw: Gateway, closed: None) -> None:
    redis_of(gw).allow("user-a")
    gw.use(ok_reply(), ok_reply())
    token = create_access_token("user-a", "free")
    assert (await gw.post(token=token)).status_code == 200
    redis_of(gw).sets[ALLOW_KEY].discard("user-a")  # what `assistant_allow.py remove` does
    assert (await gw.post(token=token)).status_code == 503


# ── a refusal costs nothing ─────────────────────────────────────────────────────


async def test_a_closed_refusal_uses_no_quota_and_calls_no_model(
    gw: Gateway, closed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_quota_free_daily", 1)
    client = gw.use(ok_reply(), ok_reply())
    token = create_access_token("user-a", "free")
    for _ in range(
        3
    ):  # a quota of 1 would answer 429 from the second refusal on if a refusal used it
        refused = await gw.post(token=token)
        assert refused.status_code == 503 and code_of(refused) == "assistant_closed"
    assert client.calls == []
    redis_of(gw).allow("user-a")
    assert (await gw.post(token=token)).status_code == 200  # the one question the quota allows
    assert (await gw.post(token=token)).status_code == 429
    assert len(client.calls) == 1


# ── the order: switches, spend and kill switch come first ───────────────────────


async def test_the_kill_switch_beats_the_allowlist(gw: Gateway, closed: None) -> None:
    redis_of(gw).data[KILL_KEY] = "1"
    response = await gw.post(token=create_access_token("user-a", "free"))
    assert response.status_code == 503 and code_of(response) == "assistant_disabled"
    assert redis_of(gw).reads == []  # refused before the set was looked at


async def test_the_spend_cap_beats_the_allowlist(
    gw: Gateway, closed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import datetime as dt

    monkeypatch.setattr(cfg, "assistant_daily_budget_usd", 1.0)
    now = dt.datetime.now(dt.timezone.utc)
    redis_of(gw).data[spend_key(now)] = str(2_000_000)  # $2 spent against a $1 cap
    response = await gw.post(token=create_access_token("user-a", "free"))
    assert response.status_code == 503 and code_of(response) == "assistant_budget"
    assert redis_of(gw).reads == []


def test_the_route_runs_the_checks_in_the_order_claude_md_describes() -> None:
    route = next(r for r in router.routes if r.path.endswith("/ask"))
    names = [d.dependency.__name__ for d in route.dependencies]  # type: ignore[attr-defined]
    order = [
        "require_available",
        "require_allowed",
        "get_model_client",
        "limit_concurrency",
        "enforce_assistant_rate_limit",
    ]
    assert [n for n in names if n in order] == order


# ── failing closed, and bad credentials ─────────────────────────────────────────


async def test_an_unreadable_set_fails_closed_and_is_logged_for_the_alarm(
    gw: Gateway, closed: None
) -> None:
    redis_of(gw).allow("user-a")
    redis_of(gw).fail_allow = True
    client = gw.use(ok_reply())
    with structlog.testing.capture_logs() as logs:
        response = await gw.post(token=create_access_token("user-a", "free"))
    assert response.status_code == 503 and code_of(response) == "assistant_unavailable"
    assert client.calls == []
    assert [e["event"] for e in logs if e["event"] == "assistant_store_unavailable"] == [
        "assistant_store_unavailable"
    ]
    assert "user-a" not in repr(logs)  # no account id in the line


async def test_a_bad_credential_is_a_401_not_a_quiet_anonymous_refusal(
    gw: Gateway, closed: None
) -> None:
    response = await gw.post(headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401


async def test_the_store_reads_the_set_and_fails_closed() -> None:
    redis = AllowRedis()
    store = AssistantStore(redis)
    redis.allow("user-a")
    assert await store.is_allowed("user-a") is True
    assert await store.is_allowed("user-b") is False
    redis.fail_allow = True
    with pytest.raises(StoreUnavailable):
        await store.is_allowed("user-a")


# ── keeping an audience out with a quota of 0 (the allowlist off) ───────────────


async def test_an_anonymous_quota_of_0_closes_anonymous_visitors_and_only_them(
    gw: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_quota_anon_per_hour", 0)
    client = gw.use(ok_reply())
    before = counter("pyvar_assistant_refused_total", reason="quota", tier="anon")
    refused = await gw.post(ip="203.0.113.50")
    assert refused.status_code == 429 and client.calls == []
    assert counter("pyvar_assistant_refused_total", reason="quota", tier="anon") == before + 1
    # a signed-in account, from the same address, is unaffected
    assert (
        await gw.post(token=create_access_token("user-a", "free"), ip="203.0.113.50")
    ).status_code == 200
    assert len(client.calls) == 1


@pytest.mark.parametrize("tier", ["free", "pro", "enterprise"])
async def test_a_daily_quota_of_0_closes_that_tier_and_no_other(
    gw: Gateway, monkeypatch: pytest.MonkeyPatch, tier: str
) -> None:
    monkeypatch.setattr(cfg, f"assistant_quota_{tier}_daily", 0)
    others = [t for t in ("free", "pro", "enterprise") if t != tier]
    client = gw.use(ok_reply(), ok_reply())
    refused = await gw.post(token=create_access_token("user-a", tier))
    assert refused.status_code == 429 and client.calls == []
    for other in others:
        assert (await gw.post(token=create_access_token(f"user-{other}", other))).status_code == 200
    assert len(client.calls) == 2

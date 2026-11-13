"""POST /api/v1/assistant/ask: who may ask, how much, what is refused first, and what is never written down.

Reasoning:
- The route is the door in front of assistant/guardrails.py::answer_question, which has its own tests with the
  same scripted client. So these tests do not re-prove the answer checks; they pin the gateway's own promises:
  off by default; the kill switch and the daily spend cap, read before any model call and failing CLOSED when the
  store is down; the per-caller quota, taken only after those, so a refused question uses none; the concurrency
  slots; the model chosen by tier; anonymous callers allowed and a bad credential not downgraded; the model id
  never in a response; and no question or answer text in any log line.
- Everything outside the process is replaced through `app.dependency_overrides` (the model client and the store),
  the same seams production uses. The Redis stand-in is an in-memory object with the three calls the store makes;
  the rate limiter is the in-memory one tests/conftest.py already installs for every test.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import threading
from collections.abc import Iterator
from typing import Any

import pytest
import structlog.testing
from httpx import ASGITransport, AsyncClient
from prometheus_client import REGISTRY

from api.assistant import deps
from api.assistant import store as store_module
from api.assistant.store import KILL_KEY, AssistantStore, spend_key
from api.middleware.auth import create_access_token
from api.middleware.rate_limit import assistant_tier
from assistant import tools
from config import get_settings
from main import create_app
from tests.assistant_typed_fakes import ScriptedClient, text_reply, tool_reply

cfg = get_settings()
FUNCTION = "historical_simulation_var"
URL = "/api/v1/assistant/ask"
BAD_DRAFT = "You should hold more capital against this exposure."
# The stock decline passes every check with no tool call, so a test that is not about the answer's content
# can script a single cheap reply.
STOCK = "I can only help with pyvar's functions. Ask me what one of them does or needs."


def ok_reply(**kwargs: Any) -> Any:
    """A one-reply script that is served live."""
    return text_reply(STOCK, **kwargs)


# ── stand-ins ────────────────────────────────────────────────────────────────────────────────────────────


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis, self.ops = redis, []

    async def __aenter__(self) -> FakePipeline:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def incrby(self, key: str, amount: int) -> FakePipeline:
        self.ops.append(("incrby", key, amount))
        return self

    def expire(self, key: str, seconds: int) -> FakePipeline:
        self.ops.append(("expire", key, seconds))
        return self

    async def execute(self) -> list[Any]:
        if self.redis.fail_write:
            raise ConnectionError("redis is down")
        for op, key, value in self.ops:
            if op == "incrby":
                self.redis.data[key] = str(int(self.redis.data.get(key, 0)) + value)
            else:
                self.redis.ttls[key] = value
        return [True] * len(self.ops)


class FakeRedis:
    """The calls AssistantStore makes: mget, and a pipeline of incrby and expire."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.fail_read = False
        self.fail_write = False

    async def mget(self, keys: list[str]) -> list[str | None]:
        if self.fail_read:
            raise ConnectionError("redis is down")
        return [self.data.get(key) for key in keys]

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)


class Gateway:
    """An app with the two seams replaced, and a helper to post to it."""

    def __init__(self) -> None:
        self.redis = FakeRedis()
        self.app = create_app()
        self.client = ScriptedClient()
        self.app.dependency_overrides[deps.get_model_client] = lambda: self.client
        self.app.dependency_overrides[store_module.get_store] = lambda: AssistantStore(self.redis)

    def use(self, *script: Any) -> ScriptedClient:
        self.client = ScriptedClient(*script)
        return self.client

    async def post(
        self,
        body: dict[str, Any] | None = None,
        *,
        token: str | None = None,
        ip: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        sent = dict(headers or {})
        if token:
            sent["Authorization"] = f"Bearer {token}"
        if ip:
            sent["X-Forwarded-For"] = f"{ip}, 10.0.0.1"
        payload = (
            body if body is not None else {"question": "What does it do?", "function": FUNCTION}
        )
        async with AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://test"
        ) as http:
            return await http.post(URL, json=payload, headers=sent)


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> Iterator[Gateway]:
    monkeypatch.setattr(cfg, "assistant_enabled", True)
    monkeypatch.setattr(cfg, "assistant_typed_enabled", True)
    monkeypatch.setattr(deps, "_inflight", 0)
    monkeypatch.setattr(deps, "_client", None)
    yield Gateway()


@pytest.fixture(scope="module")
def by_name() -> dict[str, dict[str, Any]]:
    return {e["name"]: e for e in tools.load_catalogue()}


def good_answer(by_name: dict[str, dict[str, Any]], name: str = FUNCTION) -> str:
    """An answer built from the tool result alone: it passes every check."""
    record = tools.trim_record(by_name[name])
    inputs = ", ".join(f"`{p['name']}`" for p in record["parameters"][:3])
    return (
        f"`{record['name']}` ({record['display_name']}) is a pyvar function: {record['summary']} "
        f"It takes the inputs {inputs}."
    )


def good_script(
    by_name: dict[str, dict[str, Any]], *, cost: float = 0.002, model: str = ""
) -> list:
    kwargs = {"model": model} if model else {}
    return [
        tool_reply(("get_function", {"name": FUNCTION}), **kwargs),
        text_reply(good_answer(by_name), cost=cost, **kwargs),
    ]


def counter(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


# ── off by default ───────────────────────────────────────────────────────────────────────────────────────


async def test_the_route_is_off_by_default_and_calls_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert cfg.assistant_typed_enabled is False  # the committed default
    gw = Gateway()
    client = gw.use(text_reply("never sent"))
    response = await gw.post()
    assert response.status_code == 503 and client.calls == []
    detail = response.json()["detail"]
    assert detail["code"] == "assistant_disabled" and detail["hint"].startswith("The buttons")
    assert gw.redis.data == {}  # not even the store was touched


@pytest.mark.parametrize("menu_on, typed_on", [(True, False), (False, True)])
async def test_both_switches_must_be_on(
    monkeypatch: pytest.MonkeyPatch, menu_on: bool, typed_on: bool
) -> None:
    monkeypatch.setattr(cfg, "assistant_enabled", menu_on)
    monkeypatch.setattr(cfg, "assistant_typed_enabled", typed_on)
    gw = Gateway()
    response = await gw.post()
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "assistant_disabled"


# ── the answer ───────────────────────────────────────────────────────────────────────────────────────────


async def test_an_anonymous_question_gets_a_live_answer_and_its_cost_is_recorded(
    gateway: Gateway, by_name: dict[str, dict[str, Any]]
) -> None:
    client = gateway.use(*good_script(by_name))
    response = await gateway.post()
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "answer", "source", "model_tier", "functions", "suggested_parameters", "request_id",
    }  # fmt: skip
    assert body["source"] == "live" and body["answer"] == good_answer(by_name)
    assert body["model_tier"] == "haiku" and body["functions"] == [FUNCTION]
    assert re.fullmatch(r"[0-9a-f]{32}", body["request_id"])
    assert "claude-" not in response.text  # the model id is never returned
    assert client.calls[0][0] == cfg.assistant_model_free
    assert gateway.redis.data[spend_key(dt.datetime.now(dt.timezone.utc))] == "3000"  # $0.003
    assert next(iter(gateway.redis.ttls.values())) == store_module.SPEND_TTL_SECONDS


async def test_the_checked_example_is_attached_and_the_model_text_has_no_object(
    gateway: Gateway, by_name: dict[str, dict[str, Any]]
) -> None:
    import json

    values = {
        "returns": [0.01, -0.02, 0.005, 0.0],
        "portfolio_value": 1000000,
        "confidence_level": 0.99,
    }
    written = (
        good_answer(by_name)
        + f" Example:\n```json\n{json.dumps({**values, 'confidence_level': 0.98})}\n```"
    )
    gateway.use(
        tool_reply(
            ("get_function", {"name": FUNCTION}),
            ("propose_parameters", {"name": FUNCTION, "values": values}),
        ),
        text_reply(written, cost=0.002),
    )
    body = (await gateway.post()).json()
    assert body["source"] == "live" and "{" not in body["answer"] and "0.98" not in body["answer"]
    assert body["suggested_parameters"] == {
        "function": FUNCTION,
        "values": values,
    }  # what the tool accepted


async def test_a_failed_draft_is_served_as_static_text(
    gateway: Gateway, by_name: dict[str, dict[str, Any]]
) -> None:
    gateway.use(
        tool_reply(("get_function", {"name": FUNCTION})),
        text_reply(BAD_DRAFT),
        text_reply(BAD_DRAFT),
    )
    body = (await gateway.post()).json()
    assert body["source"] == "static" and BAD_DRAFT not in body["answer"]
    assert body["functions"] == [] and body["suggested_parameters"] is None


async def test_the_model_follows_the_callers_tier(
    gateway: Gateway, by_name: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_model_free", "claude-haiku-5-5")
    monkeypatch.setattr(cfg, "assistant_model_pro", "claude-sonnet-5-5")
    monkeypatch.setattr(cfg, "assistant_model_enterprise", "claude-opus-5-5")
    seen = {}
    for tier, expected_family in (("free", "haiku"), ("pro", "sonnet"), ("enterprise", "opus")):
        model = f"claude-{expected_family}-5-5"
        client = gateway.use(*good_script(by_name, model=model))
        response = await gateway.post(token=create_access_token(f"user-{tier}", tier))
        assert response.status_code == 200, response.text
        seen[tier] = (client.calls[0][0], response.json()["model_tier"])
    assert seen == {
        "free": ("claude-haiku-5-5", "haiku"),
        "pro": ("claude-sonnet-5-5", "sonnet"),
        "enterprise": ("claude-opus-5-5", "opus"),
    }


async def test_a_function_name_that_is_not_in_the_catalogue_is_ignored(gateway: Gateway) -> None:
    client = gateway.use(ok_reply())
    response = await gateway.post({"question": "hi", "function": "no_such_function"})
    assert response.status_code == 200
    assert "<page_function>" not in client.calls[0][1]["messages"][0]["content"]


async def test_a_key_and_an_email_in_the_question_never_reach_the_model(gateway: Gateway) -> None:
    client = gateway.use(ok_reply())
    key = "pyvar_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0"
    question = f"my key is {key} and my email is jane.doe@example.com, what is VaR?"
    response = await gateway.post({"question": question})
    assert response.status_code == 200
    sent = client.calls[0][1]["messages"][0]["content"]
    assert key not in sent and "jane.doe" not in sent
    assert "[removed: looks like a key or token]" in sent and "[removed: email address]" in sent


async def test_earlier_turns_are_passed_as_data(gateway: Gateway) -> None:
    client = gateway.use(ok_reply())
    history = [{"q": f"question {i}", "a": f"answer {i}"} for i in range(3)]
    response = await gateway.post({"question": "and now?", "history": history})
    assert response.status_code == 200
    content = client.calls[0][1]["messages"][0]["content"]
    assert content.count("<earlier_turn>") == 3 and [
        m["role"] for m in client.calls[0][1]["messages"]
    ] == ["user"]


# ── bad input ────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"question": ""},
        {"question": "   "},
        {"question": "x" * 501},
        {"question": "ok", "history": [{"q": "a", "a": "b"}] * 4},
        {"question": "ok", "history": [{"q": "a"}]},
        {"question": "ok", "history": [{"q": "x" * 501, "a": "b"}]},
        {"question": "ok", "extra": 1},
        {"question": 5},
    ],
)
async def test_a_malformed_body_is_a_422_and_calls_nothing(
    gateway: Gateway, body: dict[str, Any]
) -> None:
    client = gateway.use(text_reply("never sent"))
    assert (await gateway.post(body)).status_code == 422
    assert client.calls == []


async def test_a_question_of_exactly_500_characters_is_accepted(gateway: Gateway) -> None:
    gateway.use(ok_reply())
    assert (await gateway.post({"question": "x" * 500})).status_code == 200


# ── credentials ──────────────────────────────────────────────────────────────────────────────────────────


async def test_a_bad_token_is_a_401_not_an_anonymous_question(gateway: Gateway) -> None:
    client = gateway.use(text_reply("never sent"))
    response = await gateway.post(token="not-a-jwt")
    assert response.status_code == 401 and client.calls == []


async def test_a_credential_other_than_bearer_is_anonymous(gateway: Gateway) -> None:
    gateway.use(ok_reply())
    response = await gateway.post(headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 200


async def test_a_stream_token_is_not_accepted_here(gateway: Gateway) -> None:
    from api.middleware.auth import create_stream_token

    client = gateway.use(text_reply("never sent"))
    response = await gateway.post(token=create_stream_token("user-1", "task-1"))
    assert response.status_code == 401 and client.calls == []


# ── quotas ───────────────────────────────────────────────────────────────────────────────────────────────


async def test_anonymous_callers_are_limited_per_ip_per_hour(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_quota_anon_per_hour", 2)
    client = gateway.use(*[ok_reply() for _ in range(6)])
    codes = [(await gateway.post(ip="203.0.113.7")).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    other = await gateway.post(ip="203.0.113.8")  # another address has its own count
    assert other.status_code == 200 and len(client.calls) == 3
    refused = await gateway.post(ip="203.0.113.7")
    assert refused.status_code == 429 and int(refused.headers["Retry-After"]) >= 1


@pytest.mark.parametrize("tier", ["free", "pro", "enterprise"])
async def test_signed_in_callers_are_limited_per_user_per_day_by_tier_enterprise_too(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch, tier: str
) -> None:
    monkeypatch.setattr(cfg, f"assistant_quota_{tier}_daily", 2)
    gateway.use(*[ok_reply() for _ in range(6)])
    mine, theirs = create_access_token("user-a", tier), create_access_token("user-b", tier)
    codes = [(await gateway.post(token=mine)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert (await gateway.post(token=theirs)).status_code == 200


async def test_a_signed_in_user_is_not_counted_against_the_anonymous_quota(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_quota_anon_per_hour", 1)
    gateway.use(*[ok_reply() for _ in range(4)])
    token = create_access_token("user-a", "free")
    assert (await gateway.post(ip="198.51.100.1")).status_code == 200
    assert (await gateway.post(ip="198.51.100.1")).status_code == 429
    assert (await gateway.post(token=token, ip="198.51.100.1")).status_code == 200


async def test_a_quota_refusal_is_counted_and_costs_no_model_call(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_quota_anon_per_hour", 1)
    client = gateway.use(ok_reply())
    before = counter("pyvar_assistant_refused_total", reason="quota", tier="anon")
    await gateway.post(ip="192.0.2.9")
    await gateway.post(ip="192.0.2.9")
    assert counter("pyvar_assistant_refused_total", reason="quota", tier="anon") == before + 1
    assert len(client.calls) == 1


async def test_a_limiter_outage_fails_open(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.middleware import rate_limit

    class Broken:
        class limiter:  # noqa: N801 — mimics slowapi.Limiter.limiter
            @staticmethod
            def hit(*args: object) -> bool:
                raise ConnectionError("redis is down")

    monkeypatch.setattr(rate_limit, "_limiter", Broken)
    gateway.use(ok_reply())
    assert (await gateway.post()).status_code == 200


# ── the kill switch and the spend cap ────────────────────────────────────────────────────────────────────


async def test_the_kill_switch_stops_the_route_without_a_deploy(gateway: Gateway) -> None:
    client = gateway.use(ok_reply())
    gateway.redis.data[KILL_KEY] = "1"
    response = await gateway.post()
    assert response.status_code == 503 and client.calls == []
    assert response.json()["detail"]["code"] == "assistant_disabled"
    del gateway.redis.data[KILL_KEY]
    assert (await gateway.post()).status_code == 200


async def test_a_question_refused_before_the_quota_uses_none_of_it(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_quota_anon_per_hour", 2)
    gateway.use(*[ok_reply() for _ in range(4)])
    gateway.redis.data[KILL_KEY] = "1"
    assert [(await gateway.post(ip="192.0.2.50")).status_code for _ in range(5)] == [503] * 5
    del gateway.redis.data[KILL_KEY]
    assert [(await gateway.post(ip="192.0.2.50")).status_code for _ in range(3)] == [200, 200, 429]


async def test_the_daily_budget_opens_the_breaker_and_says_when_it_resets(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_daily_budget_usd", 5.0)
    client = gateway.use(ok_reply())
    gateway.redis.data[spend_key(dt.datetime.now(dt.timezone.utc))] = str(5_000_000)
    response = await gateway.post()
    assert response.status_code == 503 and client.calls == []
    assert response.json()["detail"]["code"] == "assistant_budget"
    assert 1 <= int(response.headers["Retry-After"]) <= 86_400


async def test_spend_under_the_budget_still_answers_and_a_pushed_over_budget_closes_it(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_daily_budget_usd", 0.005)
    gateway.use(ok_reply(cost=0.004), ok_reply(cost=0.004), ok_reply())
    assert (await gateway.post()).status_code == 200  # 0.004 spent, under 0.005
    assert (await gateway.post()).status_code == 200  # the cap is checked before, not during
    third = await gateway.post()  # 0.008 spent: closed
    assert third.status_code == 503 and third.json()["detail"]["code"] == "assistant_budget"


async def test_yesterdays_spend_does_not_count_today(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_daily_budget_usd", 1.0)
    yesterday = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    gateway.redis.data[spend_key(yesterday)] = str(99_000_000)
    gateway.use(ok_reply())
    assert (await gateway.post()).status_code == 200


async def test_the_budget_gauge_follows_the_spend(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_daily_budget_usd", 4.0)
    gateway.redis.data[spend_key(dt.datetime.now(dt.timezone.utc))] = str(1_000_000)
    gateway.use(ok_reply())
    await gateway.post()
    assert counter("pyvar_assistant_budget_used_ratio") == pytest.approx(0.25)


async def test_an_unreadable_store_fails_closed(gateway: Gateway) -> None:
    client = gateway.use(text_reply("never sent"))
    gateway.redis.fail_read = True
    response = await gateway.post()
    assert response.status_code == 503 and client.calls == []
    assert response.json()["detail"]["code"] == "assistant_unavailable"


async def test_an_unwritable_store_still_delivers_the_answer_and_counts_the_miss(
    gateway: Gateway,
) -> None:
    gateway.use(ok_reply(cost=0.002))
    gateway.redis.fail_write = True
    before = counter("pyvar_assistant_spend_not_recorded_total")
    response = await gateway.post()
    assert response.status_code == 200
    assert counter("pyvar_assistant_spend_not_recorded_total") == before + 1


# ── concurrency ──────────────────────────────────────────────────────────────────────────────────────────


class BlockingClient(ScriptedClient):
    """Holds its first call until released, so a test can ask a second question meanwhile."""

    def __init__(self, *script: Any) -> None:
        super().__init__(*script)
        self.entered, self.release = threading.Event(), threading.Event()

    def complete(self, model: str, request: dict[str, Any]) -> Any:
        self.entered.set()
        assert self.release.wait(10), "the test never released the first call"
        return super().complete(model, request)


async def test_questions_past_the_slot_count_get_busy_and_the_slot_is_released(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "assistant_max_concurrent", 1)
    monkeypatch.setattr(cfg, "assistant_quota_anon_per_hour", 2)
    blocking = BlockingClient(ok_reply(), ok_reply())
    gateway.client = blocking
    first = asyncio.create_task(gateway.post(ip="192.0.2.77"))
    assert await asyncio.to_thread(blocking.entered.wait, 10)
    busy = await gateway.post(ip="192.0.2.77")
    assert busy.status_code == 503 and busy.headers["Retry-After"] == "5"
    assert busy.json()["detail"]["code"] == "assistant_busy"
    blocking.release.set()
    assert (await first).status_code == 200
    assert deps._inflight == 0
    assert (
        await gateway.post(ip="192.0.2.77")
    ).status_code == 200  # the busy one used none of the 2 quota


# ── a bug, a missing key, and what is never written down ───────────────────────────────────────────────────


async def test_an_unexpected_exception_becomes_the_static_hint_not_a_bare_500(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.assistant import routes

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("a bug that quotes the secret question text")

    monkeypatch.setattr(routes, "answer_question", boom)
    before = counter("pyvar_assistant_unexpected_errors_total")
    with structlog.testing.capture_logs() as logs:
        response = await gateway.post({"question": "UNIQUE-QUESTION-TEXT-7731"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "assistant_unavailable"
    assert counter("pyvar_assistant_unexpected_errors_total") == before + 1
    assert any(event["event"] == "assistant_ask_failed" for event in logs)
    assert deps._inflight == 0


async def test_a_missing_key_is_unavailable_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "assistant_enabled", True)
    monkeypatch.setattr(cfg, "assistant_typed_enabled", True)
    monkeypatch.setattr(cfg, "anthropic_api_key", None)
    monkeypatch.setattr(deps, "_client", None)
    gw = Gateway()
    del gw.app.dependency_overrides[deps.get_model_client]  # use the real builder
    response = await gw.post()
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "assistant_unavailable"


async def test_a_missing_key_is_refused_before_the_quota_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "assistant_enabled", True)
    monkeypatch.setattr(cfg, "assistant_typed_enabled", True)
    monkeypatch.setattr(cfg, "anthropic_api_key", None)
    monkeypatch.setattr(cfg, "assistant_quota_anon_per_hour", 1)
    monkeypatch.setattr(deps, "_client", None)
    gw = Gateway()
    del gw.app.dependency_overrides[deps.get_model_client]  # use the real builder
    assert [(await gw.post(ip="192.0.2.99")).status_code for _ in range(3)] == [503, 503, 503]
    gw.app.dependency_overrides[deps.get_model_client] = lambda: gw.use(ok_reply())
    assert (
        await gw.post(ip="192.0.2.99")
    ).status_code == 200  # the one allowed question is still there


async def test_no_question_or_answer_text_reaches_any_log_line(
    gateway: Gateway, by_name: dict[str, dict[str, Any]]
) -> None:
    secret_question = "UNIQUE-QUESTION-TEXT-9182 what does it do?"
    gateway.use(*good_script(by_name))
    with structlog.testing.capture_logs() as logs:
        response = await gateway.post({"question": secret_question, "function": FUNCTION})
    assert response.status_code == 200
    events = {event["event"] for event in logs}
    assert {"assistant_ask", "typed_answer"} <= events
    flat = repr(logs)
    assert "UNIQUE-QUESTION-TEXT-9182" not in flat
    assert good_answer(by_name)[:60] not in flat
    ask_line = next(event for event in logs if event["event"] == "assistant_ask")
    assert set(ask_line) == {
        "event", "log_level", "request_id", "tier", "auth", "source", "outcome", "model_tier",
        "cost_usd", "seconds", "functions",
    }  # fmt: skip


async def test_the_answer_metrics_carry_only_bounded_labels(
    gateway: Gateway, by_name: dict[str, dict[str, Any]]
) -> None:
    labels = {"source": "live", "outcome": "live", "tier": "anon", "model_tier": "haiku"}
    before = counter("pyvar_assistant_answers_total", **labels)
    gateway.use(*good_script(by_name))
    await gateway.post()
    assert counter("pyvar_assistant_answers_total", **labels) == before + 1
    assert counter("pyvar_assistant_cost_usd_total", model_tier="haiku") >= 0.003


def test_the_route_is_in_the_openapi_schema() -> None:
    schema = create_app().openapi()
    assert "post" in schema["paths"][URL]


# ── small pieces ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "served, label",
    [
        ("claude-haiku-5-5", "haiku"),
        ("claude-sonnet-5-5", "sonnet"),
        ("claude-opus-5-5", "opus"),
        ("claude-fable-5-2", "fable"),
        ("some-other-model", "other"),
        ("", "none"),
    ],
)
def test_tier_label_names_the_family_not_the_id(served: str, label: str) -> None:
    assert deps.tier_label(served) == label


def test_assistant_tier_maps_every_caller() -> None:
    from api.middleware.auth import TokenPayload

    assert assistant_tier(None) == "anon"
    assert assistant_tier(TokenPayload("u", "free")) == "free"
    assert assistant_tier(TokenPayload("u", "pro")) == "pro"
    assert assistant_tier(TokenPayload("u", "enterprise")) == "enterprise"
    assert assistant_tier(TokenPayload("u", "internal")) == "enterprise"
    assert assistant_tier(TokenPayload("u", "mystery")) == "free"


def test_the_spend_key_and_the_reset_time_follow_utc() -> None:
    late = dt.datetime(2026, 11, 12, 23, 59, 30, tzinfo=dt.timezone.utc)
    assert spend_key(late) == "pyvar:assistant:spend:2026-11-12"
    assert store_module.seconds_until_utc_midnight(late) == 30
    plus_one = dt.timezone(dt.timedelta(hours=1))
    assert (
        spend_key(late.astimezone(plus_one)) == "pyvar:assistant:spend:2026-11-12"
    )  # still the UTC day
    assert (
        store_module.seconds_until_utc_midnight(late.replace(hour=0, minute=0, second=0)) == 86_400
    )


async def test_the_store_reads_both_keys_in_one_call_and_records_integer_micro_dollars() -> None:
    redis = FakeRedis()
    store = AssistantStore(redis)
    now = dt.datetime(2026, 11, 12, 10, 0, tzinfo=dt.timezone.utc)
    assert (await store.gate(now)).spent_usd == 0.0 and not (await store.gate(now)).killed
    await store.add_spend(0.1234567, now)
    await store.add_spend(0.0000004, now)  # rounds to zero: nothing written
    await store.add_spend(-1.0, now)  # a negative amount is ignored
    assert redis.data == {"pyvar:assistant:spend:2026-11-12": "123457"}
    redis.data[KILL_KEY] = "x"
    gate = await store.gate(now)
    assert gate.killed and gate.spent_usd == pytest.approx(0.123457, abs=1e-9)


async def test_a_garbled_spend_value_is_unavailable_not_zero() -> None:
    redis = FakeRedis()
    redis.data["pyvar:assistant:spend:2026-11-12"] = "not-a-number"
    now = dt.datetime(2026, 11, 12, 10, 0, tzinfo=dt.timezone.utc)
    with pytest.raises(store_module.StoreUnavailable):
        await AssistantStore(redis).gate(now)

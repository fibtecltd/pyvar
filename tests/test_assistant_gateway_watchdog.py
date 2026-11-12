"""POST /api/v1/assistant/ask with the watchdog on: pins, the degrade flag, the background audit, and fail-open.

Reasoning:
- tests/test_assistant_gateway.py pins the route with the watchdog OFF (its default) and still passes unchanged;
  these tests turn `assistant_watchdog_enabled` on and check what the watchdog adds around the same door: a pinned
  function or a degraded writer is answered with fixed text and no model call, an answer that cites a pinned
  function is replaced but still billed, a healthy live answer is audited after the response with the gate
  model and the verdict is recorded as a boolean, enterprise answers are not audited, and no failure of Redis or
  of the judge ever changes what the visitor receives.
- The model client is the scripted one: the writer's replies come first, then (for an audit) the judge's. Redis
  is the in-memory fake, shared by the spend store and the watchdog. httpx's ASGI transport returns after the
  background tasks have run, so a test reads their effects straight away.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from typing import Any

import pytest
import structlog.testing

from api.assistant import deps
from api.assistant import store as store_module
from api.assistant import watchdog as service
from api.assistant.store import AssistantStore, spend_key
from api.assistant.watchdog import AuditRunner, Watchdog, WatchdogConfig
from api.middleware.auth import create_access_token
from assistant import tools
from config import get_settings
from tests.assistant_typed_fakes import text_reply, tool_reply
from tests.assistant_watchdog_fakes import FakeWatchRedis
from tests.test_assistant_gateway import (  # helpers shared with the base suite
    FUNCTION,
    Gateway,
    counter,
    good_answer,
    good_script,
)

cfg = get_settings()
OTHER = "component_var"
JUDGE_MODEL = "claude-opus-5-5"
AMPLE = WatchdogConfig(budget_usd=1000.0)


def key(*parts: str) -> str:
    return service.PREFIX + ":".join(parts)


def fn_key(function: str, part: str) -> str:
    return key("fn", deps.bank_namespace(), function, part)


def today() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def spent_micro(redis: FakeWatchRedis) -> int:
    """Everything the assistant spent today (writer calls and audits), in millionths of a dollar."""
    return int(redis.strings[spend_key(today())])


def judge_reply(**fields: Any) -> Any:
    verdict = {"faithful": True, "useful": True, "plausible_values": None, "issues": []}
    return text_reply(json.dumps({**verdict, **fields}), cost=0.0081, model=JUDGE_MODEL)


class WatchGateway(Gateway):
    """The base gateway with one Redis for the spend store and the watchdog, and a watchdog we control."""

    def __init__(self) -> None:
        super().__init__()
        self.redis = FakeWatchRedis()  # type: ignore[assignment]
        self.draw = 0.99
        self.app.dependency_overrides[store_module.get_store] = lambda: AssistantStore(self.redis)
        self.app.dependency_overrides[deps.get_watchdog] = self.make_watchdog
        self.runner = AuditRunner(2)
        self.app.dependency_overrides[deps.get_audit_runner] = lambda: self.runner
        self.watchdog_redis: Any = self.redis

    def make_watchdog(self) -> Watchdog:
        return Watchdog(
            lambda: self.watchdog_redis, AMPLE, deps.bank_namespace(), draw=lambda: self.draw
        )

    def plan(self, tau: int = 0, p: float = 0.0, writer: str = "haiku") -> None:
        self.redis.strings[key("plan")] = json.dumps({"tau": tau, "p": {writer: p}})


@pytest.fixture(scope="module")
def by_name() -> dict[str, dict[str, Any]]:
    return {e["name"]: e for e in tools.load_catalogue()}


@pytest.fixture
def wd(monkeypatch: pytest.MonkeyPatch) -> Iterator[WatchGateway]:
    monkeypatch.setattr(cfg, "assistant_enabled", True)
    monkeypatch.setattr(cfg, "assistant_typed_enabled", True)
    monkeypatch.setattr(cfg, "assistant_watchdog_enabled", True)
    monkeypatch.setattr(deps, "_inflight", 0)
    monkeypatch.setattr(deps, "_client", None)
    yield WatchGateway()


# ── off by default ───────────────────────────────────────────────────────────────────────────────────────


async def test_the_watchdog_is_off_by_default_and_the_route_touches_no_watchdog_key(
    monkeypatch: pytest.MonkeyPatch, by_name: dict[str, dict[str, Any]]
) -> None:
    assert cfg.assistant_watchdog_enabled is False  # the committed default
    monkeypatch.setattr(cfg, "assistant_enabled", True)
    monkeypatch.setattr(cfg, "assistant_typed_enabled", True)
    gw = WatchGateway()
    gw.app.dependency_overrides.pop(deps.get_watchdog)  # the real dependency, which reads the flag
    client = gw.use(*good_script(by_name))
    response = await gw.post()
    assert response.status_code == 200 and len(client.calls) == 2  # no judge call
    assert not [k for k in gw.redis.all_keys() if k.startswith(service.PREFIX)]


# ── a healthy live answer is audited after the response ──────────────────────────────────────────────────


async def test_a_live_answer_is_audited_in_the_background_with_the_gate_model(
    wd: WatchGateway, by_name: dict[str, dict[str, Any]]
) -> None:
    wd.plan(tau=5)
    client = wd.use(*good_script(by_name), judge_reply())
    response = await wd.post()
    body = response.json()
    assert response.status_code == 200 and body["source"] == "live"
    assert set(body) == {
        "answer",
        "source",
        "model_tier",
        "functions",
        "suggested_parameters",
        "request_id",
    }  # nothing about the audit reaches the visitor
    assert len(client.calls) == 3
    model, request = client.calls[2]
    assert model == cfg.assistant_gate_model == JUDGE_MODEL
    assert (
        body["answer"] in request["messages"][0]["content"]
    )  # the judge read what the visitor read
    assert wd.redis.lists[fn_key(FUNCTION, "hist")] == ["0"]  # a boolean, not a verdict
    assert spent_micro(wd.redis) >= round(
        (0.002 + 0.001 + 0.0081) * 1_000_000
    )  # writer calls + audit


async def test_a_flagged_audit_feeds_the_functions_history(
    wd: WatchGateway, by_name: dict[str, dict[str, Any]]
) -> None:
    wd.plan(tau=5)
    wd.use(*good_script(by_name), judge_reply(faithful=False, issues=["invents a parameter"]))
    await wd.post()
    assert wd.redis.lists[fn_key(FUNCTION, "hist")] == ["1"]
    assert "invents" not in json.dumps(wd.redis.lists) + json.dumps(wd.redis.strings)


async def test_four_flagged_answers_pin_the_function_and_the_fifth_question_is_not_sent_to_the_model(
    wd: WatchGateway, by_name: dict[str, dict[str, Any]]
) -> None:
    wd.plan(tau=99)
    for _ in range(4):
        wd.use(*good_script(by_name), judge_reply(faithful=False))
        await wd.post()
    assert fn_key(FUNCTION, "pin") in wd.redis.strings
    client = wd.use(text_reply("never sent"))
    before = counter("pyvar_assistant_pinned_served_total", when="pre")
    response = await wd.post()
    body = response.json()
    assert response.status_code == 200 and client.calls == []
    assert body["source"] == "static" and FUNCTION in body["answer"]
    assert body["model_tier"] == "none" and body["suggested_parameters"] is None
    assert counter("pyvar_assistant_pinned_served_total", when="pre") == before + 1


async def test_a_static_answer_is_never_audited(wd: WatchGateway) -> None:
    wd.plan(tau=99)
    wd.redis.strings[fn_key(FUNCTION, "pin")] = "1"
    client = wd.use(text_reply("never sent"))
    await wd.post()
    assert client.calls == []
    assert fn_key(FUNCTION, "hist") not in wd.redis.lists


# ── a pinned function the answer cites ───────────────────────────────────────────────────────────────────


async def test_an_answer_that_cites_a_pinned_function_is_replaced_and_still_billed(
    wd: WatchGateway, by_name: dict[str, dict[str, Any]]
) -> None:
    wd.plan(tau=0)
    wd.redis.strings[fn_key(OTHER, "pin")] = "1"
    entry = by_name[OTHER]
    wd.use(
        tool_reply(("get_function", {"name": OTHER})),
        text_reply(good_answer(by_name, OTHER), cost=0.003),
    )
    before = counter("pyvar_assistant_pinned_served_total", when="post")
    response = await wd.post({"question": "tell me about component var"})
    body = response.json()
    assert body["source"] == "static" and entry["display_name"] in body["answer"]
    assert counter("pyvar_assistant_pinned_served_total", when="post") == before + 1
    assert spent_micro(wd.redis) >= round(
        0.004 * 1_000_000
    )  # the model calls were made and are paid for


# ── a degraded writer ────────────────────────────────────────────────────────────────────────────────────


async def test_a_degraded_writer_answers_with_fixed_text_and_search_results_and_no_model_call(
    wd: WatchGateway,
) -> None:
    wd.redis.strings[key("degrade", "haiku")] = "1"
    wd.draw = 0.5  # above the probe share
    client = wd.use(text_reply("never sent"))
    before = counter("pyvar_assistant_degraded_served_total", writer="haiku", kind="static")
    response = await wd.post({"question": "what is value at risk"})
    body = response.json()
    assert response.status_code == 200 and client.calls == []
    assert body["source"] == "static"
    assert "can't answer typed questions reliably" in body["answer"]
    assert "look closest" in body["answer"] and body["functions"]
    assert "value at risk" not in body["answer"]  # the question is never echoed
    assert (
        counter("pyvar_assistant_degraded_served_total", writer="haiku", kind="static")
        == before + 1
    )


async def test_a_degraded_writers_probe_traffic_is_answered_live_and_audited_into_the_probe_window(
    wd: WatchGateway, by_name: dict[str, dict[str, Any]]
) -> None:
    wd.redis.strings[key("degrade", "haiku")] = "1"
    wd.plan(tau=0, p=1.0)
    wd.draw = 0.05  # below the probe share of 0.10
    client = wd.use(*good_script(by_name), judge_reply())
    body = (await wd.post()).json()
    assert body["source"] == "live" and len(client.calls) == 3
    assert wd.redis.lists[key("probewin", "haiku")] == ["0"]
    assert key("win", "haiku") not in wd.redis.lists  # probes never enter the exposure window


# ── who is audited ───────────────────────────────────────────────────────────────────────────────────────


async def test_enterprise_answers_are_not_audited(
    wd: WatchGateway, by_name: dict[str, dict[str, Any]]
) -> None:
    wd.plan(tau=99, p=1.0)
    client = wd.use(*good_script(by_name))
    response = await wd.post(token=create_access_token("user-e", "enterprise"))
    assert response.status_code == 200 and len(client.calls) == 2
    assert fn_key(FUNCTION, "hist") not in wd.redis.lists


@pytest.mark.parametrize("tier", ["free", "pro"])
async def test_signed_in_free_and_pro_answers_are_audited(
    wd: WatchGateway, by_name: dict[str, dict[str, Any]], tier: str
) -> None:
    wd.plan(tau=5)
    client = wd.use(*good_script(by_name), judge_reply())
    await wd.post(token=create_access_token(f"user-{tier}", tier))
    assert len(client.calls) == 3


# ── nothing the watchdog does can change the visitor's answer ────────────────────────────────────────────


async def test_a_judge_that_fails_changes_nothing_for_the_visitor_and_refunds_the_reservation(
    wd: WatchGateway, by_name: dict[str, dict[str, Any]]
) -> None:
    wd.plan(tau=5)
    wd.use(*good_script(by_name), RuntimeError("judge down"))
    response = await wd.post()
    assert response.status_code == 200 and response.json()["source"] == "live"
    assert int(wd.redis.strings[key("spent", service.day_of(today()), "coverage")]) == 0
    assert fn_key(FUNCTION, "hist") not in wd.redis.lists


async def test_a_watchdog_whose_redis_is_down_never_changes_the_answer(
    wd: WatchGateway, by_name: dict[str, dict[str, Any]]
) -> None:
    broken = FakeWatchRedis()
    broken.fail = True
    wd.watchdog_redis = broken  # the spend store is healthy; only the watchdog's Redis is down
    client = wd.use(*good_script(by_name))
    response = await wd.post()
    assert response.status_code == 200 and response.json()["source"] == "live"
    assert len(client.calls) == 2  # nothing pinned, nothing degraded, nothing audited


async def test_an_unreadable_verdict_is_dropped_not_recorded(
    wd: WatchGateway, by_name: dict[str, dict[str, Any]]
) -> None:
    wd.plan(tau=5)
    wd.use(*good_script(by_name), text_reply("looks fine to me", cost=0.0081, model=JUDGE_MODEL))
    response = await wd.post()
    assert response.status_code == 200
    assert fn_key(FUNCTION, "hist") not in wd.redis.lists


async def test_no_question_or_answer_text_is_written_to_redis_or_any_log_line(
    wd: WatchGateway, by_name: dict[str, dict[str, Any]]
) -> None:
    wd.plan(tau=5, p=1.0)
    question = "UNIQUE-QUESTION-MARKER what does it do?"
    wd.use(*good_script(by_name), judge_reply(faithful=False, issues=["UNIQUE-ISSUE-MARKER"]))
    with structlog.testing.capture_logs() as logs:
        response = await wd.post({"question": question, "function": FUNCTION})
    answer = response.json()["answer"]
    stored = json.dumps(
        [wd.redis.strings, wd.redis.hashes, wd.redis.lists, sorted(wd.redis.ttls)], default=str
    )
    logged = json.dumps(logs, default=str)
    for secret in ("UNIQUE-QUESTION-MARKER", "UNIQUE-ISSUE-MARKER", answer[:40]):
        assert secret not in stored and secret not in logged

"""scripts/assistant_ctl.py: the operator's switches for the typed assistant's kill switch and spend counter.

Reasoning:
- The two emergency controls of the typed route are Redis keys the route reads before every question and fails
  closed on (api/assistant/store.py). This script is the one tool that writes them without a Redis client of one's own
  (it runs in an ECS one-off of the API task, like scripts/trial_ctl.py), so what it promises is pinned: it writes
  exactly the keys the application reads and no others; stopping (`kill on`) never asks anything, while anything that
  could let the route spend more (`kill off`, `spend set`, `spend clear`) is a dry run unless `--yes` and, in a
  deployed prod environment, also needs `--yes-prod`; a bad request changes nothing; an unreachable cache is exit 3
  and no traceback; and the output carries numbers and the environment's name, never the cache address.
- The drills the dev run depends on (docs/assistant-dev-run-prompt.txt) are run here against the REAL route: the script
  and the gateway share one fake Redis, so "kill on" is shown to make the route answer 503 assistant_disabled, "spend
  set" to make it answer 503 assistant_budget, and a value read with `status --json` to be restorable exactly.
- No real server is touched; the Redis stand-in is in memory.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from api.assistant import deps
from api.assistant import store as store_module
from api.assistant.store import ALLOW_KEY, KILL_KEY, SPEND_TTL_SECONDS, spend_key
from api.middleware.auth import create_access_token
from config import get_settings
from tests.test_assistant_gateway import FakeRedis, Gateway, ok_reply

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assistant_ctl.py"
NOW = dt.datetime(2026, 11, 27, 10, 30, tzinfo=dt.timezone.utc)
cfg = get_settings()


def _script() -> ModuleType:
    name = "assistant_ctl_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ctl = _script()


class Shared(FakeRedis):
    """The gateway's async Redis stand-in plus the synchronous calls the script makes, on the same data."""

    def __init__(self) -> None:
        super().__init__()
        self.sets: dict[str, set[str]] = {}
        self.down = False
        self.calls: list[tuple[str, str]] = []

    def _up(self, op: str, key: str) -> None:
        if self.down:
            raise RedisConnectionError("unreachable")
        self.calls.append((op, key))

    def get(self, key: str) -> str | None:
        self._up("get", key)
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._up("set", key)
        self.data[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def delete(self, key: str) -> int:
        self._up("delete", key)
        existed = key in self.data
        self.data.pop(key, None)
        self.ttls.pop(key, None)
        return int(existed)

    def scard(self, key: str) -> int:
        self._up("scard", key)
        return len(self.sets.get(key, set()))


def run(shared: Shared, *argv: str, now: dt.datetime | None = NOW) -> int:
    return int(ctl.run(list(argv), client=shared, now=now))


@pytest.fixture
def shared(monkeypatch: pytest.MonkeyPatch) -> Shared:
    monkeypatch.setattr(cfg, "app_env", "dev")
    monkeypatch.setattr(cfg, "assistant_daily_budget_usd", 5.0)
    return Shared()


@pytest.fixture
def prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "app_env", "prod")


# ── it writes what the application reads, and nothing else ──────────────────────


def test_the_script_uses_the_applications_own_keys() -> None:
    assert ctl.KILL_KEY == store_module.KILL_KEY == "pyvar:assistant:kill"
    assert ctl.ALLOW_KEY == store_module.ALLOW_KEY == "pyvar:assistant:allow"
    assert ctl.spend_key is store_module.spend_key
    assert ctl.MICRO == store_module.MICRO == 1_000_000
    assert ctl.SPEND_TTL_SECONDS == store_module.SPEND_TTL_SECONDS


def test_only_the_three_keys_are_ever_touched(shared: Shared) -> None:
    for argv in (
        ["status"],
        ["kill", "on"],
        ["kill", "off", "--yes"],
        ["spend", "set", "--usd", "2.5", "--yes"],
        ["spend", "clear", "--yes"],
    ):
        assert run(shared, *argv) == 0
    assert {key for _, key in shared.calls} <= {KILL_KEY, ALLOW_KEY, spend_key(NOW)}


# ── status ──────────────────────────────────────────────────────────────────────


def test_status_reads_the_state_and_prints_exact_millionths(
    shared: Shared, capsys: pytest.CaptureFixture[str]
) -> None:
    shared.data[spend_key(NOW)] = "1234567"
    shared.data[KILL_KEY] = "1"
    shared.sets[ALLOW_KEY] = {"a", "b"}
    assert run(shared, "status", "--json") == 0
    info = json.loads(capsys.readouterr().out)
    assert info["environment"] == "dev" and info["date_utc"] == "2026-11-27"
    assert info["kill_switch"] is True and info["spend_micro_usd"] == 1234567
    assert info["spend_usd"] == pytest.approx(1.234567)
    assert info["daily_budget_usd"] == 5.0 and info["spend_ratio"] == pytest.approx(
        0.2469, abs=1e-4
    )
    assert info["allowlist_members"] == 2
    assert set(info["settings_of_this_task"]) == {
        "assistant_enabled",
        "typed_enabled",
        "watchdog_enabled",
        "allowlist_enabled",
    }
    assert run(shared, "status") == 0
    text = capsys.readouterr().out
    assert "kill switch     ON" in text and "exactly 1234567 millionths" in text
    assert "2 account(s)" in text and "environment     dev" in text


def test_status_of_an_idle_day(shared: Shared, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(shared, "status", "--json") == 0
    info = json.loads(capsys.readouterr().out)
    assert info["kill_switch"] is False and info["spend_micro_usd"] == 0
    assert info["allowlist_members"] == 0


def test_status_with_no_cap_does_not_divide_by_zero(
    shared: Shared, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cfg, "assistant_daily_budget_usd", 0.0)
    assert run(shared, "status") == 0
    assert "no cap set" in capsys.readouterr().out


# ── the kill switch ─────────────────────────────────────────────────────────────


def test_kill_on_sets_the_key_without_expiry_and_asks_nothing(shared: Shared) -> None:
    assert run(shared, "kill", "on") == 0
    assert shared.data[KILL_KEY] == "1" and KILL_KEY not in shared.ttls


def test_kill_on_needs_no_confirmation_even_in_prod(shared: Shared, prod: None) -> None:
    assert run(shared, "kill", "on") == 0 and KILL_KEY in shared.data


def test_kill_off_is_a_dry_run_unless_yes(
    shared: Shared, capsys: pytest.CaptureFixture[str]
) -> None:
    shared.data[KILL_KEY] = "1"
    assert run(shared, "kill", "off") == 0
    assert KILL_KEY in shared.data and "dry run" in capsys.readouterr().out
    assert run(shared, "kill", "off", "--yes") == 0
    assert KILL_KEY not in shared.data


def test_kill_off_in_prod_also_needs_yes_prod(
    shared: Shared, prod: None, capsys: pytest.CaptureFixture[str]
) -> None:
    shared.data[KILL_KEY] = "1"
    assert run(shared, "kill", "off", "--yes") == 2
    assert KILL_KEY in shared.data and "--yes-prod" in capsys.readouterr().err
    assert run(shared, "kill", "off", "--yes", "--yes-prod") == 0
    assert KILL_KEY not in shared.data


# ── the spend counter ───────────────────────────────────────────────────────────


def test_spend_set_writes_exact_millionths_with_the_applications_expiry(shared: Shared) -> None:
    assert run(shared, "spend", "set", "--usd", "5", "--yes") == 0
    assert (
        shared.data[spend_key(NOW)] == "5000000"
        and shared.ttls[spend_key(NOW)] == SPEND_TTL_SECONDS
    )
    assert run(shared, "spend", "set", "--micro", "1234567", "--yes") == 0
    assert shared.data[spend_key(NOW)] == "1234567"  # exact, not rounded through dollars


def test_dollars_are_rounded_to_the_nearest_millionth_not_cut(shared: Shared) -> None:
    # 2.01 * 1_000_000 is 2009999.9999999998 in floating point: cutting it would store one millionth too little.
    assert run(shared, "spend", "set", "--usd", "2.01", "--yes") == 0
    assert shared.data[spend_key(NOW)] == "2010000"


def test_spend_set_and_clear_are_dry_runs_unless_yes(shared: Shared) -> None:
    shared.data[spend_key(NOW)] = "42"
    assert run(shared, "spend", "set", "--usd", "9") == 0
    assert run(shared, "spend", "clear") == 0
    assert shared.data[spend_key(NOW)] == "42"
    assert not any(op in ("set", "delete") for op, _ in shared.calls)


def test_spend_changes_in_prod_need_yes_prod(shared: Shared, prod: None) -> None:
    shared.data[spend_key(NOW)] = "42"
    assert run(shared, "spend", "set", "--usd", "9", "--yes") == 2
    assert run(shared, "spend", "clear", "--yes") == 2
    assert shared.data[spend_key(NOW)] == "42"
    assert run(shared, "spend", "clear", "--yes", "--yes-prod") == 0
    assert spend_key(NOW) not in shared.data


def test_spend_clear_removes_only_todays_key(shared: Shared) -> None:
    yesterday = spend_key(NOW - dt.timedelta(days=1))
    shared.data[yesterday] = "7"
    shared.data[spend_key(NOW)] = "42"
    assert run(shared, "spend", "clear", "--yes") == 0
    assert spend_key(NOW) not in shared.data and shared.data[yesterday] == "7"


@pytest.mark.parametrize(
    "argv",
    [
        ["spend", "set", "--yes"],  # no amount
        ["spend", "set", "--usd", "1", "--micro", "1", "--yes"],  # two amounts
        ["spend", "set", "--usd", "-1", "--yes"],
        ["spend", "set", "--micro", "-5", "--yes"],
        ["spend", "set", "--usd", "1000001", "--yes"],  # a typo guard
        ["spend", "clear", "--usd", "1", "--yes"],  # clear takes no amount
    ],
)
def test_a_bad_spend_request_changes_nothing(shared: Shared, argv: list[str]) -> None:
    shared.data[spend_key(NOW)] = "42"
    assert run(shared, *argv) == 2
    assert shared.data[spend_key(NOW)] == "42"
    assert not any(op in ("set", "delete") for op, _ in shared.calls)


def test_a_refused_connection_is_exit_3_too(
    shared: Shared, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(key: str) -> str:
        raise ConnectionRefusedError("[Errno 111]")  # a plain OSError, as a connect can fail

    monkeypatch.setattr(shared, "get", refuse)
    assert run(shared, "status") == 3
    assert "cannot reach the cache: ConnectionRefusedError" in capsys.readouterr().err


def test_the_usage_lines_in_the_docstring_all_parse(shared: Shared) -> None:
    lines = re.findall(r"^    python scripts/assistant_ctl\.py (.+)$", ctl.__doc__, flags=re.M)
    assert len(lines) >= 6
    for line in lines:
        argv = re.sub(r"\[.*?\]", "", line.split("#")[0]).split()  # "[--json]" is optional
        assert run(shared, *argv) == 0, line


# ── failure ─────────────────────────────────────────────────────────────────────


def test_an_unreachable_cache_is_exit_3_with_no_traceback_and_no_address(
    shared: Shared, capsys: pytest.CaptureFixture[str]
) -> None:
    shared.down = True
    for argv in (["status"], ["kill", "on"], ["spend", "clear", "--yes"]):
        assert run(shared, *argv) == 3
    captured = capsys.readouterr()
    assert "cannot use the cache: ConnectionError" in captured.err
    assert "Traceback" not in captured.err
    assert "redis://" not in captured.out + captured.err


# ── the drills, against the real route ──────────────────────────────────────────


@pytest.fixture
def gw(monkeypatch: pytest.MonkeyPatch) -> Iterator[Gateway]:
    monkeypatch.setattr(cfg, "assistant_enabled", True)
    monkeypatch.setattr(cfg, "assistant_typed_enabled", True)
    monkeypatch.setattr(cfg, "app_env", "dev")
    monkeypatch.setattr(deps, "_inflight", 0)
    monkeypatch.setattr(deps, "_client", None)
    gateway = Gateway()
    gateway.redis = Shared()  # the app's store override reads `gateway.redis` at call time
    yield gateway


def drill(gateway: Gateway, *argv: str) -> int:
    assert isinstance(gateway.redis, Shared)
    return int(ctl.run(list(argv), client=gateway.redis))


async def test_the_kill_switch_drill_stops_and_restarts_the_real_route(gw: Gateway) -> None:
    client = gw.use(ok_reply(), ok_reply())
    token = create_access_token("user-a", "free")
    assert (await gw.post(token=token)).status_code == 200
    assert drill(gw, "kill", "on") == 0
    refused = await gw.post(token=token)
    assert refused.status_code == 503 and refused.json()["detail"]["code"] == "assistant_disabled"
    assert len(client.calls) == 1  # the refusal called no model
    assert drill(gw, "kill", "off", "--yes") == 0
    assert (await gw.post(token=token)).status_code == 200


async def test_the_spend_cap_drill_refuses_with_no_model_call_and_restores_exactly(
    gw: Gateway, capsys: pytest.CaptureFixture[str]
) -> None:
    client = gw.use(ok_reply(), ok_reply(), ok_reply())
    token = create_access_token("user-a", "free")
    assert (await gw.post(token=token)).status_code == 200  # spends a little
    capsys.readouterr()
    assert drill(gw, "status", "--json") == 0
    found = json.loads(capsys.readouterr().out)["spend_micro_usd"]
    assert drill(gw, "spend", "set", "--usd", "50", "--yes") == 0
    refused = await gw.post(token=token)
    assert refused.status_code == 503 and refused.json()["detail"]["code"] == "assistant_budget"
    assert int(refused.headers["Retry-After"]) >= 1 and len(client.calls) == 1
    # put back exactly what was found
    assert drill(gw, "spend", "set", "--micro", str(found), "--yes") == 0
    capsys.readouterr()  # the two "set" lines
    assert drill(gw, "status", "--json") == 0
    assert json.loads(capsys.readouterr().out)["spend_micro_usd"] == found
    assert (await gw.post(token=token)).status_code == 200


async def test_clearing_the_counter_reopens_a_route_that_was_over_its_cap(gw: Gateway) -> None:
    gw.use(ok_reply())
    token = create_access_token("user-a", "free")
    assert drill(gw, "spend", "set", "--usd", "6", "--yes") == 0
    assert (await gw.post(token=token)).status_code == 503
    assert drill(gw, "spend", "clear", "--yes") == 0
    assert (await gw.post(token=token)).status_code == 200


def test_the_script_does_not_depend_on_the_event_loop_or_the_application_clients() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("asyncio", "aioredis", "redis.asyncio", "get_store("):
        assert forbidden not in source, forbidden
    assert "def _client(url" in source  # the one place a connection is made
    assert source.count("redis.from_url(") == 1

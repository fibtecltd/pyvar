"""tests/test_trial_ctl.py — scripts/trial_ctl.py: the operator's switches for the trial lane.

Reasoning:
- The lane is switched by Redis keys (api/middleware/trial.py), and this script is the one tool that writes them, so
  its promises are pinned: `on` and `off` are the master switch, `attack` and `pause` set and clear their flags
  (clearing also clears the breaker's strike count), `budget` can only lower, a bad request changes nothing, and an
  unreachable cache is exit code 3 and not a traceback.
- A small in-memory stand-in for the synchronous Redis client is used; no real server is touched.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from api.middleware import trial as lane

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "trial_ctl.py"
NOW = 1_800_000_000.0


def _script() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.skip(f"source file not found (cannot audit): {_SCRIPT}")
    name = "trial_ctl_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SyncFake:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise RedisConnectionError("unreachable")

    def get(self, key: str) -> str | None:
        self._check()
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._check()
        self.data[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def delete(self, *keys: str) -> int:
        self._check()
        removed = 0
        for key in keys:
            removed += int(self.data.pop(key, None) is not None)
            self.ttls.pop(key, None)
        return removed

    def ttl(self, key: str) -> int:
        self._check()
        return self.ttls.get(key, -1) if key in self.data else -2


@pytest.fixture
def ctl() -> tuple[ModuleType, SyncFake]:
    return _script(), SyncFake()


def _run(ctl_parts: tuple[ModuleType, SyncFake], *argv: str) -> int:
    module, fake = ctl_parts
    return int(module.run(list(argv), client=fake, now=NOW))


def test_on_opens_the_lane_and_off_closes_it(ctl, capsys) -> None:
    assert _run(ctl, "on") == 0
    assert (
        ctl[1].data[lane.KEY_ON] == "1" and lane.KEY_ON not in ctl[1].ttls
    )  # no expiry: a person set it
    assert _run(ctl, "off") == 0
    assert lane.KEY_ON not in ctl[1].data
    assert "closed" in capsys.readouterr().out


def test_attack_and_pause_expire_on_their_own_and_clearing_resets_the_breaker(ctl) -> None:
    fake = ctl[1]
    fake.data[lane.KEY_STRIKES] = "4"
    assert _run(ctl, "attack", "on") == 0
    assert fake.ttls[lane.KEY_ATTACK] == lane.ATTACK_TTL_SECONDS == 24 * 3600
    assert _run(ctl, "pause", "on") == 0
    assert fake.ttls[lane.KEY_PAUSE] == lane.PAUSE_TTL_SECONDS == 12 * 3600
    assert lane.KEY_STRIKES in fake.data  # setting a flag leaves the count alone
    assert _run(ctl, "attack", "off") == 0
    assert lane.KEY_ATTACK not in fake.data and lane.KEY_STRIKES not in fake.data
    assert lane.KEY_PAUSE in fake.data  # clearing one flag does not clear the other
    assert _run(ctl, "pause", "off") == 0
    assert lane.KEY_PAUSE not in fake.data


def test_a_budget_override_merges_and_clears(ctl) -> None:
    fake = ctl[1]
    assert _run(ctl, "budget", "--compute-daily", "500") == 0
    assert _run(ctl, "budget", "--issue-hourly", "3", "--compute-daily", "400") == 0
    assert json.loads(fake.data[lane.KEY_BUDGET]) == {"compute_daily": 400, "issue_hourly": 3}
    assert _run(ctl, "budget", "--clear") == 0
    assert lane.KEY_BUDGET not in fake.data


@pytest.mark.parametrize(
    "argv",
    [
        ("budget",),
        ("budget", "--clear", "--compute-daily", "5"),
        ("budget", "--compute-daily", "-1"),
    ],
)
def test_a_bad_budget_request_changes_nothing_and_exits_2(ctl, argv, capsys) -> None:
    ctl[1].data[lane.KEY_BUDGET] = '{"issue_daily": 7}'
    assert _run(ctl, *argv) == 2
    assert ctl[1].data[lane.KEY_BUDGET] == '{"issue_daily": 7}'
    assert capsys.readouterr().err


def test_status_reports_the_switches_and_the_budgets(ctl, capsys) -> None:
    fake = ctl[1]
    fake.data.update({lane.KEY_ON: "1", lane.KEY_ATTACK: "1", lane.KEY_STRIKES: "2"})
    fake.ttls[lane.KEY_ATTACK] = 3 * 3600
    fake.data[f"{lane.PREFIX_DAY}compute:{lane.utc_date(NOW)}"] = "340"
    # 36 units of debt in the compute bucket: 64 of 100 available
    fake.data[lane.KEY_COMPUTE] = str(int(NOW * 1000) + 36 * 36_000)
    assert _run(ctl, "status", "--json") == 0
    info = json.loads(capsys.readouterr().out)
    assert info["on"] and info["attack"] and not info["paused"]
    assert info["pow_bits"] == 24
    assert info["compute_units_available"] == 64
    assert (info["compute_units_today"], info["compute_daily_cap"]) == (340, 2500)
    assert info["tickets_available"] == 20 and info["breaker_strikes"] == 2
    assert _run(ctl, "status") == 0
    text = capsys.readouterr().out
    assert "ON (clears itself in 3 h 0 min)" in text and "64/100 units" in text


def test_a_closed_lane_says_what_every_caller_is_told(ctl, capsys) -> None:
    assert _run(ctl, "status") == 0
    assert "429 trial_exhausted" in capsys.readouterr().out


def test_an_unreachable_cache_is_exit_3_not_a_traceback(ctl, capsys) -> None:
    ctl[1].down = True
    assert _run(ctl, "status") == 3
    assert "cannot use the cache" in capsys.readouterr().err
    assert _run(ctl, "off") == 3


def test_the_script_is_the_only_writer_of_the_control_keys() -> None:
    """The API only reads the switches; the one write it makes is the breaker's own (api/middleware/trial.py)."""
    import ast

    source = (Path(__file__).resolve().parents[1] / "api" / "routes" / "trial.py").read_text()
    names: list[Any] = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Name)]
    assert not [n for n in names if n.id in {"KEY_ON", "KEY_BUDGET"}]

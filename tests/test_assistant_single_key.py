"""The typed route and its watchdog name ONE key per Redis command, because the cache is in cluster mode.

The first live run of the typed route in dev (2026-11-27) answered 503 `assistant_unavailable` on every request:
the gate read the kill switch and the day's spend with one MGET, ElastiCache Serverless refused it with CROSSSLOT
(the two keys hash to different slots), and the route fails closed. No test saw it because the doubles accepted any
command. Now the doubles refuse a command over keys in different slots (tests/redis_slots.py), the helpers read and
delete one key per command (api/assistant/single_key.py), and a scan of the package fails on the commands that take
several keys.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest
from redis.exceptions import ClusterCrossSlotError

from api.assistant.single_key import delete_each, get_each
from api.assistant.store import KILL_KEY, AssistantStore, StoreUnavailable, spend_key
from tests.assistant_watchdog_fakes import FakeWatchRedis
from tests.redis_slots import crc16, hash_slot, require_one_slot
from tests.test_assistant_gateway import FakeRedis

ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 11, 27, 12, 0, tzinfo=dt.timezone.utc)

# ── the slot arithmetic is the one Redis Cluster uses ──────────────────────────────────────────────────


def test_the_checksum_and_the_documented_slots_are_the_clusters() -> None:
    assert crc16(b"123456789") == 0x31C3  # the check value in the Redis Cluster specification
    assert hash_slot("foo") == 12182 and hash_slot("somekey") == 11058  # CLUSTER KEYSLOT's answers
    assert hash_slot("{user1000}.following") == hash_slot("{user1000}.followers")  # a hash tag
    assert hash_slot("a{}b") == crc16(b"a{}b") % 16384  # an empty tag hashes the whole key


def test_the_kill_switch_and_the_days_spend_are_in_different_slots() -> None:
    """The premise of the 503: if these ever shared a slot, the gate's old MGET would have worked."""
    assert hash_slot(KILL_KEY) != hash_slot(spend_key(NOW))


# ── the doubles refuse what the cache refuses ──────────────────────────────────────────────────────────


async def test_the_gateway_double_refuses_the_old_two_key_read() -> None:
    with pytest.raises(ClusterCrossSlotError):
        await FakeRedis().mget([KILL_KEY, spend_key(NOW)])


async def test_the_watchdog_double_refuses_multi_key_reads_and_deletes_across_slots() -> None:
    redis = FakeWatchRedis()
    with pytest.raises(ClusterCrossSlotError):
        await redis.mget(["a:one", "b:two"])
    with pytest.raises(ClusterCrossSlotError):
        await redis.delete("a:one", "b:two")
    assert await redis.mget(["{t}:one", "{t}:two"]) == [None, None]  # the same tag is one slot


def test_require_one_slot_accepts_one_key_and_a_shared_tag() -> None:
    require_one_slot([])
    require_one_slot([KILL_KEY])
    require_one_slot(["{x}:a", "{x}:b"])


# ── the gate and the helpers work through them ─────────────────────────────────────────────────────────


async def test_the_gate_reads_each_key_separately_and_sees_both_values() -> None:
    redis = FakeRedis()
    store = AssistantStore(redis)
    gate = await store.gate(NOW)
    assert (gate.killed, gate.spent_usd) == (False, 0.0)
    redis.data[KILL_KEY] = "1"
    redis.data[spend_key(NOW)] = "1500000"
    gate = await store.gate(NOW)
    assert (gate.killed, gate.spent_usd) == (True, 1.5)


async def test_the_gate_still_fails_closed_when_a_read_fails() -> None:
    redis = FakeRedis()
    redis.fail_read = True
    with pytest.raises(StoreUnavailable) as raised:
        await AssistantStore(redis).gate(NOW)
    assert str(raised.value) == "ConnectionError"  # the class only, which deps.py now logs


async def test_a_cross_slot_error_surfaces_as_its_class_name_in_the_store_error() -> None:
    """What the live Sentry event shows: StoreUnavailable("ClusterCrossSlotError") from the gate's read."""

    class Refusing(FakeRedis):
        async def get(self, key: str) -> str | None:
            raise ClusterCrossSlotError(ClusterCrossSlotError.message)

    with pytest.raises(StoreUnavailable) as raised:
        await AssistantStore(Refusing()).gate(NOW)
    assert str(raised.value) == "ClusterCrossSlotError"


async def test_get_each_keeps_the_order_and_marks_missing_keys() -> None:
    redis = FakeWatchRedis()
    redis.strings.update({"k:1": "one", "k:3": "three"})
    assert await get_each(redis, ["k:3", "k:2", "k:1"]) == ["three", None, "one"]
    assert await get_each(redis, []) == []
    assert set(redis.commands) == {"get"}  # never an mget


async def test_delete_each_removes_every_key_and_counts_those_that_existed() -> None:
    redis = FakeWatchRedis()
    redis.strings.update({"k:1": "1", "k:2": "2"})
    assert await delete_each(redis, "k:1", "k:2", "k:missing") == 2
    assert redis.strings == {}
    assert set(redis.commands) == {"delete"}


# ── nothing in the package can reach for a multi-key command again ─────────────────────────────────────

MULTI_KEY_METHODS = {
    "mget",
    "mset",
    "msetnx",
    "sunion",
    "sunionstore",
    "sinter",
    "sinterstore",
    "sdiff",
    "sdiffstore",
    "smove",
    "rename",
    "renamenx",
    "eval",
    "evalsha",
    "unlink",
}
SCANNED = [
    *sorted((ROOT / "api" / "assistant").glob("*.py")),
    ROOT / "api" / "middleware" / "trial.py",
]


def _multi_key_calls(path: Path) -> list[str]:
    label = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.name
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            name = node.func.attr
            args = len(node.args) + (1 if any(isinstance(a, ast.Starred) for a in node.args) else 0)
            if name in MULTI_KEY_METHODS or (name == "delete" and args > 1):
                found.append(f"{label}:{node.lineno} .{name}(")
    return found


def test_no_command_in_the_typed_route_or_the_trial_lane_names_several_keys() -> None:
    assert SCANNED, "the scan found no files"
    offenders = [line for path in SCANNED for line in _multi_key_calls(path)]
    assert offenders == [], f"a cluster-mode cache refuses these with CROSSSLOT: {offenders}"


def test_the_scan_sees_a_multi_key_call_when_there_is_one(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(
        "async def f(r):\n    await r.mget(['a', 'b'])\n    await r.delete('a', 'b')\n"
    )
    assert len(_multi_key_calls(probe)) == 2
    clean = tmp_path / "clean.py"
    clean.write_text("async def f(r):\n    await r.get('a')\n    await r.delete('a')\n")
    assert _multi_key_calls(clean) == []

"""tests/test_trial_events.py — the lane's log lines are what its CloudWatch alarms count.

Reasoning:
- The trial lane's alarms (pyvar-cdk/stacks/alerts_stack.py) are CloudWatch metric filters on the API's JSON
  log lines, because nothing in AWS scrapes the Prometheus counters. A filter matches the JSON key `event`, so
  the event names are a contract between this code and the CDK. This file pins the lane's side: which outcomes
  write a line, what the line's `event` is, and that the breaker writes one line per state change. The CDK's
  side (the same names in the filter patterns) is pinned in tests/test_cdk_trial_lane.py.
- The lines are rendered by the real `setup_logging()` in its JSON mode, not by a stand-in, because the point
  is what CloudWatch will see: this app's structlog set-up renders a stdlib record's message as `event` and does
  not render `extra=`, so the name has to carry the fact.
- Nothing is logged for a call that ran or failed on input: an allowed call already has an `api_usage` row.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from api.middleware import trial as lane
from api.middleware.trial import KEY_ATTACK, KEY_PAUSE, TrialStore, record_event
from observability.setup import cfg, setup_logging
from tests.trial_fakes import FakeClock, FakeTrialRedis


@pytest.fixture
def json_lines() -> Iterator[io.StringIO]:
    """The root logger as a deployed API configures it (JSON), writing to a buffer."""
    root = logging.getLogger()
    level = root.level
    handler_count = len(root.handlers)
    with patch.object(cfg, "app_env", "dev"):
        setup_logging()
    handler = root.handlers[-1]
    assert isinstance(handler, logging.StreamHandler)
    stream = io.StringIO()
    handler.setStream(stream)
    root.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        del root.handlers[handler_count:]
        root.setLevel(level)


def _events(stream: io.StringIO) -> list[str]:
    return [json.loads(line)["event"] for line in stream.getvalue().splitlines() if line.strip()]


def _count(event: str) -> float:
    return float(lane.EVENTS.labels(event=event)._value.get())  # noqa: SLF001


def test_an_issued_ticket_and_every_refusal_reason_write_one_json_line(json_lines) -> None:
    reasons = sorted(lane.RETRY_AFTER_SECONDS)
    assert {"asn", "issuance", "pow", "off", "paused"} <= set(reasons)
    record_event("issued")
    for reason in reasons:
        record_event(f"refused_{reason}")
    assert _events(json_lines) == ["trial_issued"] + [f"trial_refused_{r}" for r in reasons]


def test_the_line_names_the_logger_and_carries_a_timestamp_and_level(json_lines) -> None:
    record_event("refused_asn")
    (line,) = [json.loads(x) for x in json_lines.getvalue().splitlines()]
    assert line["event"] == "trial_refused_asn"
    assert line["level"] == "info"
    assert line["logger"] == "api.middleware.trial"
    assert line["timestamp"]


@pytest.mark.parametrize(
    "event",
    ["ran", "input_error", "timeout", "ticket_invalid", "function_unavailable", "too_large"],
)
def test_per_call_outcomes_are_counted_but_not_logged(json_lines, event: str) -> None:
    before = _count(event)
    record_event(event)
    assert _count(event) == before + 1
    assert json_lines.getvalue() == ""


def test_a_logged_event_is_also_counted(json_lines) -> None:
    before = _count("refused_asn")
    record_event("refused_asn")
    assert _count("refused_asn") == before + 1


@pytest.fixture
def parts() -> tuple[FakeClock, FakeTrialRedis, TrialStore]:
    clock = FakeClock(1_800_000_000.0)
    redis = FakeTrialRedis(clock)
    return clock, redis, TrialStore(redis, clock)


async def test_the_breaker_writes_a_strike_line_each_empty_hour_and_a_line_per_flag_it_sets(
    json_lines, parts
) -> None:
    clock, redis, store = parts
    limits = lane.effective_limits(await store.controls())
    seen: list[list[str]] = []
    for _ in range(6):
        await store.charge_compute(300, limits)  # empty the compute bucket
        before = len(_events(json_lines))
        await store.hourly_check(limits)
        seen.append(_events(json_lines)[before:])
        clock.advance(3600)
    assert seen[0] == ["trial_breaker_strike"]
    assert seen[1] == ["trial_breaker_strike"]
    assert seen[2] == ["trial_breaker_strike", "trial_breaker_attack"]  # the third empty hour
    assert seen[3] == ["trial_breaker_strike", "trial_breaker_attack"]  # the flag is set again
    assert seen[5] == ["trial_breaker_strike", "trial_breaker_pause", "trial_breaker_attack"]
    assert KEY_ATTACK in redis.data and KEY_PAUSE in redis.data


async def test_a_healthy_hour_writes_no_breaker_line(json_lines, parts) -> None:
    _, _, store = parts
    limits = lane.effective_limits(await store.controls())
    await store.hourly_check(limits)  # a full bucket
    assert _events(json_lines) == []

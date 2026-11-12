"""api/assistant/watchdog.py: the Redis state, the decisions around one answer, and the background audit.

Reasoning:
- The rules are tested in test_assistant_watchdog_rules.py. These tests check that the service applies them in
  the order the plan gives and keeps to its own rules: it keeps only counts and booleans, every key expires, a
  pin happens once however many audits finish together, a reservation is refunded when the judge fails, and
  every Redis failure leaves the answer path untouched (fail open).
- A fake Redis (tests/assistant_watchdog_fakes.py) replaces the server; the clock and the random draw are
  injected, so each test says exactly what happens and nothing is left to chance. The judge is a stub that
  returns a scripted verdict, so no model is called.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from collections.abc import Callable
from typing import Any

import pytest

from api.assistant import metrics
from api.assistant import watchdog as service
from api.assistant.watchdog import AuditPlan, AuditRunner, Watchdog, WatchdogConfig
from assistant import watchdog as rules_module
from assistant.audit import AuditVerdict
from assistant.guardrails import Evidence
from assistant.watchdog import Rules
from tests.assistant_watchdog_fakes import FakeWatchRedis

NOW = dt.datetime(2026, 11, 12, 10, 0, tzinfo=dt.timezone.utc)
DAY = "2026-11-12"
NS = "v4-test"
FN = "asset_encumbrance_ratio"
OTHER = "component_var"
MICRO = service.MICRO
AMPLE = WatchdogConfig(budget_usd=1000.0)  # the budget is not what most of these tests are about


def key(*parts: str) -> str:
    return service.PREFIX + ":".join(parts)


def fn_key(function: str, part: str, ns: str = NS) -> str:
    return key("fn", ns, function, part)


def make(
    *,
    config: WatchdogConfig | None = None,
    draw: float = 0.99,
    tau: int = 0,
    p: float = 0.0,
    redis: FakeWatchRedis | None = None,
) -> tuple[Watchdog, FakeWatchRedis]:
    """A watchdog on a fake Redis whose cached plan says `tau` and `p` for the writer "haiku"."""
    redis = redis or FakeWatchRedis()
    redis.strings[key("plan")] = json.dumps({"tau": tau, "p": {"haiku": p}})
    dog = Watchdog(lambda: redis, config or AMPLE, NS, clock=lambda: NOW, draw=lambda: draw)
    return dog, redis


def verdict(flagged: bool = False, *, parsed: bool = True, cost: float = 0.0081) -> AuditVerdict:
    return AuditVerdict(flagged=flagged, parsed=parsed, cost=cost, model="claude-opus-5-5")


async def plan_for(
    dog: Watchdog, *functions: str, writer: str = "haiku", writer_probe: bool = False
) -> AuditPlan:
    plan = await dog.plan(functions=functions, writer=writer, writer_probe=writer_probe)
    assert plan is not None
    return plan


def counter(metric: Any, **labels: str) -> float:
    return float(metric.labels(**labels)._value.get()) if labels else float(metric._value.get())


# ── before the model call ────────────────────────────────────────────────────────────────────────────────


async def test_nothing_is_pinned_or_degraded_until_redis_says_so() -> None:
    dog, redis = make()
    assert await dog.standing(FN, "haiku") == service.Standing()
    redis.strings[fn_key(FN, "pin")] = "1"
    assert await dog.standing(FN, "haiku") == service.Standing(pinned=(FN,))
    redis.strings[key("degrade", "haiku")] = "1"
    assert await dog.standing(FN, "haiku") == service.Standing(pinned=(FN,), degraded=True)
    assert (await dog.standing(None, "haiku")).pinned == ()  # no page, no pin to check
    assert (await dog.standing(FN, "sonnet")).degraded is False  # another writer


async def test_a_pin_belongs_to_one_bank_version() -> None:
    dog, redis = make()
    redis.strings[fn_key(FN, "pin", ns="v3-old")] = "1"
    assert (await dog.standing(FN, "haiku")).pinned == ()  # a new catalogue release starts clean


async def test_pinned_among_returns_the_pinned_functions_in_order() -> None:
    dog, redis = make()
    redis.strings[fn_key(OTHER, "pin")] = "1"
    assert await dog.pinned_among([FN, OTHER, FN]) == (OTHER,)
    assert await dog.pinned_among([]) == ()


async def test_a_redis_failure_before_the_model_call_changes_nothing() -> None:
    dog, redis = make()
    redis.fail = True
    before = counter(metrics.WATCHDOG_ERRORS, op="standing")
    assert await dog.standing(FN, "haiku") == service.Standing()
    assert await dog.pinned_among([FN]) == ()
    assert counter(metrics.WATCHDOG_ERRORS, op="standing") == before + 1


def test_probe_traffic_is_the_configured_share() -> None:
    dog, _ = make(config=WatchdogConfig(probe_share=0.1), draw=0.05)
    assert dog.probe_traffic()
    dog, _ = make(config=WatchdogConfig(probe_share=0.1), draw=0.5)
    assert not dog.probe_traffic()


# ── deciding to audit ────────────────────────────────────────────────────────────────────────────────────


async def test_an_answer_is_counted_even_when_it_is_not_audited() -> None:
    dog, redis = make(tau=0, p=0.0)
    assert await dog.plan(functions=[FN], writer="haiku") is None
    assert redis.hashes[key("vol", DAY)] == {FN: 1}
    assert redis.hashes[key("elig", DAY)] == {"haiku": 1}


async def test_coverage_audits_the_first_tau_answers_of_a_function_each_day() -> None:
    dog, _ = make(tau=2)
    first = await plan_for(dog, FN)
    second = await plan_for(dog, FN)
    assert first.pool == second.pool == service.POOL_COVERAGE
    assert await dog.plan(functions=[FN], writer="haiku") is None  # the third answer of the day
    other = await plan_for(dog, OTHER)  # another function has its own count
    assert other.functions == (OTHER,)


async def test_exposure_audits_the_draws_below_the_writers_probability() -> None:
    dog, _ = make(tau=0, p=0.25, draw=0.2)
    plan = await plan_for(dog, FN)
    assert (plan.pool, plan.exposure, plan.writer_probe) == (service.POOL_EXPOSURE, True, False)
    dog, _ = make(tau=0, p=0.25, draw=0.3)
    assert await dog.plan(functions=[FN], writer="haiku") is None


async def test_a_writer_the_plan_does_not_know_is_audited_until_the_budget_stops_it() -> None:
    dog, redis = make(tau=0, draw=0.9)
    redis.strings[key("plan")] = json.dumps(
        {"tau": 0, "p": {}}
    )  # cold start: no history for any writer
    plan = await plan_for(dog, FN, writer="newcomer")
    assert plan.exposure


async def test_an_answer_that_cites_no_function_can_still_be_chosen_for_exposure() -> None:
    dog, _ = make(tau=3, p=1.0)
    plan = await plan_for(dog)
    assert plan.functions == () and plan.exposure


async def test_a_function_in_probe_is_audited_whatever_the_water_level() -> None:
    dog, redis = make(tau=0, p=0.0)
    redis.strings[fn_key(FN, "level")] = "1"  # pinned before, and the pin has expired
    plan = await plan_for(dog, FN)
    assert plan.probing == (FN,) and plan.pool == service.POOL_COVERAGE


async def test_a_pinned_function_is_not_in_probe() -> None:
    dog, redis = make(tau=0, p=0.0)
    redis.strings[fn_key(FN, "level")] = "1"
    redis.strings[fn_key(FN, "pin")] = "1"
    assert await dog.plan(functions=[FN], writer="haiku") is None


async def test_probe_traffic_of_a_degraded_writer_is_always_audited_and_not_exposure() -> None:
    dog, _ = make(tau=0, p=1.0)
    plan = await plan_for(dog, FN, writer_probe=True)
    assert plan.writer_probe and not plan.exposure and plan.pool == service.POOL_PROBE


# ── the budget ───────────────────────────────────────────────────────────────────────────────────────────


async def test_each_pool_stops_at_its_own_share_of_the_budget() -> None:
    # $0.0154 a day at 50%: one verdict ($0.0077) for each pool
    config = WatchdogConfig(budget_usd=0.0154, coverage_share=0.5, verdict_usd=0.0077)
    dog, redis = make(config=config, tau=5, p=1.0, draw=0.0)
    first = await plan_for(dog, FN)
    assert (
        first.pool == service.POOL_COVERAGE
    )  # covered, and chosen for exposure too: charged to coverage
    second = await plan_for(dog, FN)
    assert second.pool == service.POOL_EXPOSURE  # coverage is spent; exposure still has room
    assert await dog.plan(functions=[FN], writer="haiku") is None  # both spent
    assert int(redis.strings[key("spent", DAY, "coverage")]) == round(0.0077 * MICRO)
    assert int(redis.strings[key("spent", DAY, "exposure")]) == round(
        0.0077 * MICRO
    )  # refusals refunded


async def test_a_zero_budget_audits_nothing() -> None:
    dog, _ = make(config=WatchdogConfig(budget_usd=0.0), tau=5, p=1.0)
    assert await dog.plan(functions=[FN], writer="haiku") is None


async def test_the_reservation_is_settled_at_the_real_price() -> None:
    dog, redis = make(tau=1)
    plan = await plan_for(dog, FN)
    spent = key("spent", DAY, "coverage")
    assert int(redis.strings[spent]) == plan.reserved_micro == round(0.0077 * MICRO)
    await dog.record(plan, verdict(cost=0.0100))
    assert int(redis.strings[spent]) == round(0.0100 * MICRO)


async def test_a_released_reservation_is_given_back() -> None:
    dog, redis = make(tau=1)
    plan = await plan_for(dog, FN)
    await dog.release(plan)
    assert int(redis.strings[key("spent", DAY, "coverage")]) == 0


async def test_an_unreadable_verdict_costs_what_it_cost_and_changes_nothing_else() -> None:
    dog, redis = make(tau=1)
    plan = await plan_for(dog, FN)
    effects = await dog.record(plan, verdict(parsed=False, cost=0.0090))
    assert effects == service.Effects()
    assert int(redis.strings[key("spent", DAY, "coverage")]) == round(0.0090 * MICRO)
    assert fn_key(FN, "hist") not in redis.lists  # not a pass and not a flag


# ── pins ─────────────────────────────────────────────────────────────────────────────────────────────────


async def audit_flags(
    dog: Watchdog, flags: list[bool], *functions: str, **kwargs: Any
) -> list[Any]:
    effects = []
    for flag in flags:
        plan = await plan_for(dog, *functions, **kwargs)
        effects.append(await dog.record(plan, verdict(flag)))
    return effects


async def test_four_flagged_audits_in_a_row_pin_the_function_for_seven_days_once() -> None:
    dog, redis = make(tau=99)
    effects = await audit_flags(dog, [True] * 4, FN)
    assert [e.pinned for e in effects] == [[], [], [], [FN]]
    assert redis.ttls[fn_key(FN, "pin")] == 7 * 86_400
    assert redis.strings[fn_key(FN, "level")] == "1"
    assert fn_key(FN, "hist") not in redis.lists  # the window starts afresh after a pin
    assert (await dog.standing(FN, "haiku")).pinned == (FN,)


async def test_one_flag_in_ten_audits_never_pins() -> None:
    dog, redis = make(tau=999)
    await audit_flags(
        dog, ([True] + [False] * 9) * 12, FN
    )  # +0.9 then -0.9: the CUSUM never accumulates
    assert fn_key(FN, "pin") not in redis.strings and fn_key(FN, "level") not in redis.strings


async def test_audits_finishing_together_pin_once() -> None:
    dog, redis = make(tau=99)
    plans = [await plan_for(dog, FN) for _ in range(6)]
    await asyncio.gather(*(dog.record(plan, verdict(True)) for plan in plans))
    assert redis.strings[fn_key(FN, "level")] == "1"  # SET NX: one pin, one level step


async def test_one_audit_feeds_every_function_the_answer_fetched() -> None:
    dog, redis = make(tau=99)
    await audit_flags(dog, [True, False], FN, OTHER)
    assert redis.lists[fn_key(FN, "hist")] == ["1", "0"]
    assert redis.lists[fn_key(OTHER, "hist")] == ["1", "0"]


async def test_a_probe_with_two_flags_unpins_for_good() -> None:
    dog, redis = make(tau=0)
    redis.strings[fn_key(FN, "level")] = "1"
    effects = await audit_flags(dog, [True, True] + [False] * 18, FN)
    assert effects[-1].unpinned == [FN] and all(not e.unpinned for e in effects[:-1])
    assert fn_key(FN, "level") not in redis.strings and fn_key(FN, "probe") not in redis.lists


async def test_a_probe_with_three_flags_pins_again_for_twice_as_long() -> None:
    dog, redis = make(tau=0)
    redis.strings[fn_key(FN, "level")] = "1"
    effects = await audit_flags(dog, [True, True, True] + [False] * 17, FN)
    assert effects[-1].repinned == [FN]
    assert redis.ttls[fn_key(FN, "pin")] == 14 * 86_400
    assert redis.strings[fn_key(FN, "level")] == "2"
    assert fn_key(FN, "probe") not in redis.lists  # the next probe starts from nothing


async def test_pin_durations_double_to_four_weeks() -> None:
    dog, redis = make(tau=0)
    for level, days in [(0, 7), (1, 14), (2, 28), (3, 28)]:
        redis.strings.pop(fn_key(FN, "pin"), None)
        if level:
            redis.strings[fn_key(FN, "level")] = str(level)
        assert await dog._pin(FN)
        assert redis.ttls[fn_key(FN, "pin")] == days * 86_400
    assert not await dog._pin(FN)  # already pinned


# ── writers ──────────────────────────────────────────────────────────────────────────────────────────────


async def feed_window(dog: Watchdog, flags: list[bool], **kwargs: Any) -> list[service.Effects]:
    return await audit_flags(dog, flags, **kwargs)


async def test_a_full_exposure_window_above_eight_percent_degrades_the_writer() -> None:
    dog, redis = make(tau=0, p=1.0, draw=0.0)
    flags = [True] * 17 + [False] * 183
    effects = await feed_window(dog, flags)
    assert effects[-1].degraded and not any(e.degraded for e in effects[:-1])
    assert key("degrade", "haiku") in redis.strings
    assert key("win", "haiku") not in redis.lists  # tumbling: judged once, emptied
    assert (await dog.standing(None, "haiku")).degraded


async def test_a_full_window_at_eight_percent_or_less_does_not_degrade_and_starts_over() -> None:
    dog, redis = make(tau=0, p=1.0, draw=0.0)
    effects = await feed_window(dog, [True] * 16 + [False] * 184)
    assert not any(e.degraded for e in effects)
    assert key("degrade", "haiku") not in redis.strings
    assert key("win", "haiku") not in redis.lists


async def test_a_window_that_is_not_full_never_alerts() -> None:
    dog, redis = make(tau=0, p=1.0, draw=0.0)
    effects = await feed_window(dog, [True] * 199)
    assert not any(e.degraded for e in effects)
    assert len(redis.lists[key("win", "haiku")]) == 199


async def test_probes_of_a_degraded_writer_lift_the_degrade_at_five_percent_or_less() -> None:
    dog, redis = make(tau=0, p=1.0, draw=0.0)
    redis.strings[key("degrade", "haiku")] = "1"
    effects = await feed_window(dog, [True] * 10 + [False] * 190, writer_probe=True)
    assert effects[-1].recovered
    assert key("degrade", "haiku") not in redis.strings
    assert not (await dog.standing(None, "haiku")).degraded


async def test_probes_above_five_percent_keep_the_degrade_and_start_a_new_window() -> None:
    dog, redis = make(tau=0, p=1.0, draw=0.0)
    redis.strings[key("degrade", "haiku")] = "1"
    effects = await feed_window(dog, [True] * 11 + [False] * 189, writer_probe=True)
    assert not any(e.recovered for e in effects)
    assert key("degrade", "haiku") in redis.strings
    assert key("probewin", "haiku") not in redis.lists  # the next 200 decide again


async def test_probe_traffic_never_enters_the_exposure_window() -> None:
    dog, redis = make(tau=0, p=1.0, draw=0.0)
    redis.strings[key("degrade", "haiku")] = "1"
    await feed_window(dog, [True] * 5, writer_probe=True)
    assert (
        key("win", "haiku") not in redis.lists and len(redis.lists[key("probewin", "haiku")]) == 5
    )


# ── the hourly plan ──────────────────────────────────────────────────────────────────────────────────────


async def test_the_plan_is_computed_from_the_trailing_week_and_cached_for_an_hour() -> None:
    redis = FakeWatchRedis()
    for back in range(1, 8):
        day = (NOW - dt.timedelta(days=back)).date().isoformat()
        redis.hashes[key("vol", day)] = {FN: 10, OTHER: 1}  # 10 and 1 answers a day, every day
        redis.hashes[key("elig", day)] = {"haiku": 110}
    config = WatchdogConfig(budget_usd=2.0, coverage_share=0.6, verdict_usd=0.0077)
    dog = Watchdog(lambda: redis, config, NS, clock=lambda: NOW, draw=lambda: 0.99)
    data = await dog._plan_data(NOW)
    # coverage: $1.20 = 155 verdicts for 10 + 1 answers a day: every answer is affordable, tau = 10
    assert data["tau"] == 10
    # exposure: $0.80 over 110 eligible answers a day at $0.0077: 0.8 / (0.0077 x 110) = 0.94
    assert data["p"]["haiku"] == pytest.approx(0.8 / (0.0077 * 110), rel=1e-6)
    assert redis.ttls[key("plan")] == service.PLAN_TTL
    redis.hashes.clear()  # the cache, not Redis history, answers the next call
    assert await dog._plan_data(NOW) == data


# ── what is kept ─────────────────────────────────────────────────────────────────────────────────────────


async def test_every_key_is_namespaced_expires_and_holds_only_counts_and_booleans() -> None:
    dog, redis = make(tau=99, p=1.0, draw=0.0)
    await audit_flags(dog, [True, False, True, True, True], FN, OTHER)
    await audit_flags(dog, [False] * 3, FN, writer="haiku", writer_probe=True)
    keys = redis.all_keys()
    assert keys and all(k.startswith(service.PREFIX) for k in keys)
    plan = key("plan")
    assert all(k in redis.ttls or k == plan for k in keys if k != plan)
    for values in redis.lists.values():
        assert set(values) <= {"0", "1"}  # booleans
    for fields in redis.hashes.values():
        assert all(isinstance(v, int) for v in fields.values())  # counts
    assert not any(c in "".join(keys) for c in ("question", "answer"))


# ── the background audit ─────────────────────────────────────────────────────────────────────────────────


class Recorder:
    def __init__(self) -> None:
        self.spent: list[float] = []

    async def add_spend(self, usd: float) -> None:
        self.spent.append(usd)


def runner(audit: Callable[..., AuditVerdict], limit: int = 2) -> AuditRunner:
    return AuditRunner(limit, audit=audit)


async def run_audit(
    run: AuditRunner, plan: AuditPlan, dog: Watchdog, recorder: Recorder
) -> service.Effects | None:
    return await run.run(
        plan,
        watchdog=dog,
        add_spend=recorder.add_spend,
        client=object(),  # type: ignore[arg-type]  # the stub audit never calls it
        model="claude-opus-5-5",
        question="q",
        page_function=FN,
        answer="a",
        evidence=Evidence(records=(FN,)),
        attached=None,
        by_name={},
    )


async def test_a_background_audit_judges_records_and_adds_the_price_to_the_days_spend() -> None:
    dog, redis = make(tau=99)
    recorder = Recorder()
    plan = await plan_for(dog, FN)
    seen: dict[str, Any] = {}

    def audit(client: Any, model: str, **kwargs: Any) -> AuditVerdict:
        seen.update(model=model, **kwargs)
        return verdict(True, cost=0.0082)

    effects = await run_audit(runner(audit), plan, dog, recorder)
    assert effects is not None and recorder.spent == [0.0082]
    assert redis.lists[fn_key(FN, "hist")] == ["1"]
    assert seen["model"] == "claude-opus-5-5" and seen["answer"] == "a"


async def test_a_judge_that_fails_refunds_the_reservation_and_records_nothing() -> None:
    dog, redis = make(tau=99)
    recorder = Recorder()
    plan = await plan_for(dog, FN)

    def audit(*args: Any, **kwargs: Any) -> AuditVerdict:
        raise RuntimeError("provider down")

    before = counter(metrics.AUDITS, result="error", pool="coverage")
    assert await run_audit(runner(audit), plan, dog, recorder) is None
    assert int(redis.strings[key("spent", DAY, "coverage")]) == 0
    assert recorder.spent == [] and fn_key(FN, "hist") not in redis.lists
    assert counter(metrics.AUDITS, result="error", pool="coverage") == before + 1


async def test_audits_beyond_the_per_task_limit_are_skipped_and_refunded_not_queued() -> None:
    dog, redis = make(tau=99)
    recorder = Recorder()

    def slow(*args: Any, **kwargs: Any) -> AuditVerdict:
        import time

        time.sleep(0.05)
        return verdict(False)

    run = runner(slow, limit=1)
    first, second = await plan_for(dog, FN), await plan_for(dog, FN)
    task = asyncio.create_task(run_audit(run, first, dog, recorder))
    await asyncio.sleep(0.01)  # the first audit is now in its worker thread
    skipped = await run_audit(run, second, dog, recorder)
    await task
    assert skipped is None
    assert int(redis.strings[key("spent", DAY, "coverage")]) == round(
        0.0081 * MICRO
    )  # only the first


async def test_the_audit_never_raises_into_the_answer_path_when_redis_is_down() -> None:
    dog, redis = make(tau=99)
    recorder = Recorder()
    plan = await plan_for(dog, FN)
    redis.fail = True
    effects = await run_audit(runner(lambda *a, **k: verdict(True)), plan, dog, recorder)
    assert effects == service.Effects()  # record() failed open; the judge's price was still added
    assert recorder.spent == [0.0081]


def test_the_rules_the_service_uses_are_the_defaults() -> None:
    assert WatchdogConfig().rules == Rules() == rules_module.DEFAULT_RULES

"""
api/assistant/watchdog.py — the watchdog's state in Redis, and the steps the route takes around an answer

Reasoning:
- The rules are assistant/watchdog.py (pure, tested by simulation); the judge is assistant/audit.py. This module
  is the part that touches Redis and the clock, in the order the plan's section 8 gives:
  * BEFORE the model call, `standing()`: is the page's function pinned, is the writer degraded. One MGET;
  * AFTER the answer, `plan()`: count the answer, decide whether to audit it, and reserve its price from
    the day's audit budget; then, in the background, `record()` the verdict (or `release()` the reservation);
  * `pinned_among()` once more on the functions the answer cited, because the page is not the only way a
    pinned function reaches an answer.
- WHAT IS KEPT. Counts, function names, writer families, hours and booleans. No question, no answer, no verdict
  text, no user or IP: nothing here can be turned back into what a visitor typed. The question and the answer
  live in the memory of the background task that audits them, and end with it.
- FAILURE POLICY: the opposite of the spend gate. The gate fails closed because it guards money; the watchdog is
  a safety net for answer QUALITY, and a Redis blip must not take the assistant down, so every operation here
  fails OPEN (nothing pinned, nothing degraded, nothing audited), is logged without text and counted in
  `pyvar_assistant_watchdog_errors`. The money side stays closed: an audit is reserved against the budget before
  it is run, and the reservation is refunded if the judge call fails.
- STATE (prefix `pyvar:assistant:wd:`), every key expiring:
  * `vol:{day}` hash function -> answers today (9 days). The HINCRBY that counts an answer also tells the
    coverage rule "this is the n-th answer of the function today": audit it iff n <= tau;
  * `elig:{day}` hash writer -> eligible answers today (9 days); the trailing 7-day means feed tau and the
    exposure probabilities, recomputed at most once an hour into `plan` (JSON, 1 hour);
  * `spent:{day}:coverage|exposure` micro-dollars reserved against each pool (9 days);
  * per function and bank version: `fn:{ns}:{function}:hist` (list of the last 200 audited flags, 0/1),
    `:pin` (set with a TTL of 7, 14 or 28 days), `:level` (pins so far, 90 days) and `:probe` (flags of the
    probe). A new bank version is a new `ns`, so a catalogue release starts every function's window afresh
    instead of pinning the long tail together;
  * per writer family: `win:{writer}` (the last 200 exposure flags), `degrade:{writer}` and
    `probewin:{writer}` (the last 200 probe flags while degraded).
- ATOMICITY WITHOUT SCRIPTS. Every write is a single atomic command (RPUSH, HINCRBY, INCRBY, SET NX). The
  decisions that must happen once are keyed to a command's return value: the audit whose RPUSH returns length 20
  decides the probe; `SET pin NX` pins once however many audits finish together; the audit whose window push
  fills it evaluates it.
- A degraded writer serves static text (plus search results) except for `assistant_degrade_probe_share` of its
  questions, which are answered live and audited at 100%; 200 of those at 5% or less lift the degrade (else
  the next 200 decide again). Writer windows are tumbling: judged once when they hold 200 flags, then emptied.
  A pinned
  function receives no audits, so after its pin expires a probe of 20 audited answers decides.
- Enterprise answers are not audited here. The plan audits them at 1% as "gate misses" of a synchronous second
  reader (plan section 8); that reader is not built, so there is nothing to audit against yet.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog

from api.assistant import metrics
from assistant import watchdog as rules_module
from assistant.audit import AuditVerdict, audit_answer
from assistant.client import ModelClient
from assistant.guardrails import Evidence
from assistant.watchdog import Rules

logger = structlog.get_logger()

PREFIX = "pyvar:assistant:wd:"
MICRO = 1_000_000
DAY_TTL = 9 * 86_400
LEVEL_TTL = 90 * 86_400
PLAN_TTL = 3_600
TRAILING_DAYS = 7
POOL_COVERAGE = "coverage"
POOL_EXPOSURE = "exposure"
POOL_PROBE = "probe"


@dataclass(frozen=True)
class WatchdogConfig:
    """The numbers the service needs (from config.py; a test passes its own).

    Attributes:
        budget_usd: audit dollars a UTC day.
        coverage_share: share of the budget for the coverage pool; the rest is the exposure pool.
        verdict_usd: planning price of one verdict (the reservation, and the denominator of the probabilities).
        probe_share: share of a degraded writer's questions that are answered live as probes.
        rules: the watchdog rules (assistant/watchdog.py).
    """

    budget_usd: float = 2.0
    coverage_share: float = 0.6
    verdict_usd: float = 0.0077
    probe_share: float = 0.10
    rules: Rules = field(default_factory=Rules)

    @property
    def coverage_usd(self) -> float:
        return self.budget_usd * self.coverage_share

    @property
    def exposure_usd(self) -> float:
        return self.budget_usd * (1.0 - self.coverage_share)


@dataclass(frozen=True)
class Standing:
    """What Redis says about a question before the model is called.

    Attributes:
        pinned: the page's function if it is pinned, else empty.
        degraded: the writer is degraded.
    """

    pinned: tuple[str, ...] = ()
    degraded: bool = False


@dataclass(frozen=True)
class AuditPlan:
    """A decision to audit one answer, with the dollars reserved for it.

    Attributes:
        functions: the functions whose histories this audit feeds (those the answer fetched, not pinned).
        probing: the subset in probe state (their flags go to the probe, not the history).
        exposure: the verdict also feeds the writer's exposure window.
        writer_probe: the answer is probe traffic of a degraded writer (feeds the probe window instead).
        writer: the writer family.
        pool: the pool the reservation was taken from (coverage|exposure|probe).
        reserved_micro: micro-dollars reserved.
        day: the UTC day of the reservation (refund and correction go to the same day's key).
    """

    functions: tuple[str, ...]
    probing: tuple[str, ...]
    exposure: bool
    writer_probe: bool
    writer: str
    pool: str
    reserved_micro: int
    day: str


@dataclass
class Effects:
    """What a recorded verdict changed (for logs and tests; never text)."""

    pinned: list[str] = field(default_factory=list)
    repinned: list[str] = field(default_factory=list)
    unpinned: list[str] = field(default_factory=list)
    degraded: bool = False
    recovered: bool = False


def day_of(now: dt.datetime) -> str:
    """The UTC day of `now` as YYYY-MM-DD."""
    return now.astimezone(dt.timezone.utc).date().isoformat()


def _key(*parts: str) -> str:
    return PREFIX + ":".join(parts)


def _fn_key(ns: str, function: str, part: str) -> str:
    return _key("fn", ns, function, part)


class Watchdog:
    """Redis-backed watchdog state, with the clock and the random draw injectable for tests."""

    def __init__(
        self,
        redis: Callable[[], Any],
        config: WatchdogConfig,
        namespace: str,
        *,
        clock: Callable[[], dt.datetime] | None = None,
        draw: Callable[[], float] | None = None,
    ) -> None:
        self._redis = redis
        self.config = config
        self.ns = namespace or "none"
        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self._draw = draw or random.random

    # ── before the model call ────────────────────────────────────────────────────────────────────────

    async def standing(self, page_function: str | None, writer: str) -> Standing:
        """Whether the page's function is pinned and whether the writer is degraded. Fails open."""
        try:
            keys = [_key("degrade", writer)]
            if page_function:
                keys.append(_fn_key(self.ns, page_function, "pin"))
            values = await self._redis().mget(keys)
            degraded = values[0] is not None
            pinned = (page_function,) if page_function and values[1] is not None else ()
            metrics.WRITER_DEGRADED.labels(writer=writer).set(1 if degraded else 0)
            return Standing(pinned=pinned, degraded=degraded)
        except Exception as exc:  # noqa: BLE001 — fail open, see the module docstring
            self._failed("standing", exc)
            return Standing()

    def probe_traffic(self) -> bool:
        """True for the share of a degraded writer's questions that are answered live as probes."""
        return self._draw() < self.config.probe_share

    async def pinned_among(self, functions: Sequence[str]) -> tuple[str, ...]:
        """The functions in `functions` that are pinned, in order. Fails open."""
        names = list(dict.fromkeys(functions))
        if not names:
            return ()
        try:
            values = await self._redis().mget([_fn_key(self.ns, n, "pin") for n in names])
            return tuple(n for n, v in zip(names, values, strict=True) if v is not None)
        except Exception as exc:  # noqa: BLE001
            self._failed("pinned_among", exc)
            return ()

    async def not_pinned(self, functions: Sequence[str]) -> tuple[str, ...]:
        """`functions` without the pinned ones, in order and without repeats. Fails open (all are kept)."""
        names = tuple(dict.fromkeys(functions))
        pinned = set(await self.pinned_among(names))
        return tuple(n for n in names if n not in pinned)

    # ── after the answer: count it, decide, reserve ──────────────────────────────────────────────────

    async def plan(
        self, *, functions: Sequence[str], writer: str, writer_probe: bool = False
    ) -> AuditPlan | None:
        """Count one eligible live answer and decide whether to audit it.

        Args:
            functions: the functions the agent fetched with `get_function` (not pinned ones).
            writer: the writer's model family.
            writer_probe: the answer is probe traffic of a degraded writer: always audited, and it feeds
                the probe window, not the exposure window.

        Returns:
            The plan with its reservation, or None (not chosen, the pools are spent, or Redis failed).
        """
        now = self._clock()
        day = day_of(now)
        names = tuple(dict.fromkeys(functions))
        try:
            redis = self._redis()
            await redis.hincrby(_key("elig", day), writer, 1)
            await redis.expire(_key("elig", day), DAY_TTL)
            counts = {}
            for name in names:
                counts[name] = int(await redis.hincrby(_key("vol", day), name, 1))
            if names:
                await redis.expire(_key("vol", day), DAY_TTL)
            data = await self._plan_data(now)
            tau, p_writer = int(data["tau"]), float(data["p"].get(writer, 1.0))
            probing = [n for n in names if await self._in_probe(n)]
            covered = [n for n in names if rules_module.covered(counts[n] - 1, tau)]
            exposed = (not writer_probe) and self._draw() < p_writer
            if not (probing or covered or exposed or writer_probe):
                return None
            order = self._pools(bool(probing or covered), exposed, writer_probe)
            reserved = await self._reserve(order, day)
            if reserved is None:
                metrics.AUDITS.labels(result="skipped_budget", pool=order[0]).inc()
                return None
            pool, micro = reserved
            return AuditPlan(
                functions=names,
                probing=tuple(probing),
                exposure=exposed,
                writer_probe=writer_probe,
                writer=writer,
                pool=pool,
                reserved_micro=micro,
                day=day,
            )
        except Exception as exc:  # noqa: BLE001
            self._failed("plan", exc)
            return None

    @staticmethod
    def _pools(by_coverage: bool, exposed: bool, writer_probe: bool) -> list[str]:
        """The pools an audit may be charged to, best first."""
        if writer_probe:
            return [POOL_PROBE]
        order = [POOL_COVERAGE] if by_coverage else []
        if exposed:
            order.append(POOL_EXPOSURE)
        return order

    async def _reserve(self, order: Sequence[str], day: str) -> tuple[str, int] | None:
        """Reserve one verdict's planning price from the first pool in `order` that still has room.

        The probe traffic of a degraded writer is charged to the exposure pool's key but is not held to its cap:
        it is how the writer gets better, and it is at most `assistant_degrade_probe_share` of its traffic.
        """
        redis = self._redis()
        micro = round(self.config.verdict_usd * MICRO)
        for pool in order:
            funded = POOL_EXPOSURE if pool == POOL_PROBE else pool
            usd = self.config.coverage_usd if funded == POOL_COVERAGE else self.config.exposure_usd
            cap = round(usd * MICRO)
            key = _key("spent", day, funded)
            total = int(await redis.incrby(key, micro))
            await redis.expire(key, DAY_TTL)
            if cap > 0:
                metrics.AUDIT_BUDGET_RATIO.labels(pool=funded).set(total / cap)
            if pool == POOL_PROBE or total <= cap:
                return pool, micro
            await redis.decrby(key, micro)
        return None

    async def _plan_data(self, now: dt.datetime) -> dict[str, Any]:
        """tau and each writer's exposure probability, from the trailing 7 days; cached for an hour."""
        redis = self._redis()
        raw = await redis.get(_key("plan"))
        if raw:
            return json.loads(raw)  # type: ignore[no-any-return]
        expected: dict[str, float] = {}
        eligible: dict[str, float] = {}
        for back in range(1, TRAILING_DAYS + 1):
            day = day_of(now - dt.timedelta(days=back))
            for name, count in (await redis.hgetall(_key("vol", day))).items():
                expected[name] = expected.get(name, 0.0) + int(count) / TRAILING_DAYS
            for writer, count in (await redis.hgetall(_key("elig", day))).items():
                eligible[writer] = eligible.get(writer, 0.0) + int(count) / TRAILING_DAYS
        tau = rules_module.coverage_level(
            expected, self.config.coverage_usd, self.config.verdict_usd
        )
        shares = rules_module.writer_shares(eligible, self.config.rules)
        probabilities = {
            writer: rules_module.exposure_probability(
                eligible[writer],
                self.config.exposure_usd,
                self.config.verdict_usd,
                share=shares[writer],
            )
            for writer in shares
        }
        data = {"tau": tau, "p": probabilities}
        await redis.set(_key("plan"), json.dumps(data), ex=PLAN_TTL)
        return data

    async def _in_probe(self, function: str) -> bool:
        """True while the function has been pinned before, its pin has expired, and the probe is not over."""
        redis = self._redis()
        level, pin = await redis.mget(
            [_fn_key(self.ns, function, "level"), _fn_key(self.ns, function, "pin")]
        )
        return level is not None and pin is None

    # ── after the audit ──────────────────────────────────────────────────────────────────────────────

    async def release(self, plan: AuditPlan) -> None:
        """Give back a reservation whose audit did not run or failed. Fails open."""
        try:
            await self._adjust(plan, -plan.reserved_micro)
        except Exception as exc:  # noqa: BLE001
            self._failed("release", exc)

    async def _adjust(self, plan: AuditPlan, delta_micro: int) -> None:
        pool = POOL_EXPOSURE if plan.pool == POOL_PROBE else plan.pool
        if delta_micro:
            await self._redis().incrby(_key("spent", plan.day, pool), delta_micro)

    async def record(self, plan: AuditPlan, verdict: AuditVerdict) -> Effects:
        """Settle the reservation at the real price and feed the verdict into the histories and windows.

        An unreadable verdict settles the price and changes nothing else. Fails open.
        """
        effects = Effects()
        try:
            await self._adjust(plan, round(verdict.cost * MICRO) - plan.reserved_micro)
            if not verdict.parsed:
                metrics.AUDITS.labels(result="unparsed", pool=plan.pool).inc()
                return effects
            metrics.AUDITS.labels(
                result="flagged" if verdict.flagged else "passed", pool=plan.pool
            ).inc()
            for function in plan.functions:
                await self._feed_function(plan, function, verdict.flagged, effects)
            if plan.writer_probe:
                await self._feed_probe_window(plan.writer, verdict.flagged, effects)
            elif plan.exposure:
                await self._feed_window(plan.writer, verdict.flagged, effects)
        except Exception as exc:  # noqa: BLE001
            self._failed("record", exc)
        return effects

    async def _feed_function(
        self, plan: AuditPlan, function: str, flagged: bool, effects: Effects
    ) -> None:
        redis, rules = self._redis(), self.config.rules
        flag = "1" if flagged else "0"
        if function in plan.probing:
            probe = _fn_key(self.ns, function, "probe")
            length = int(await redis.rpush(probe, flag))
            await redis.expire(probe, LEVEL_TTL)
            if (
                length != rules.probe_audits
            ):  # exactly the audit that completes the probe decides it
                return
            outcome = rules_module.probe_outcome(
                [v == "1" for v in await redis.lrange(probe, 0, -1)], rules
            )
            if outcome == "unpin":
                await redis.delete(
                    probe,
                    _fn_key(self.ns, function, "level"),
                    _fn_key(self.ns, function, "hist"),
                )
                effects.unpinned.append(function)
                metrics.PIN_EVENTS.labels(event="unpin").inc()
                logger.info("assistant_unpinned", function=function)
            elif outcome == "repin":
                await redis.delete(probe)
                if await self._pin(function):
                    effects.repinned.append(function)
                    metrics.PIN_EVENTS.labels(event="repin").inc()
            return
        history = _fn_key(self.ns, function, "hist")
        await redis.rpush(history, flag)
        await redis.ltrim(history, -rules_module.HISTORY_KEEP, -1)
        await redis.expire(history, LEVEL_TTL)
        flags = [v == "1" for v in await redis.lrange(history, 0, -1)]
        reason = rules_module.pin_reason(flags, rules)
        if reason and await self._pin(function):
            await redis.delete(history)
            effects.pinned.append(function)
            metrics.PIN_EVENTS.labels(event=f"set_{reason}").inc()

    async def _pin(self, function: str) -> bool:
        """Pin `function` for the next duration; False if another audit pinned it first."""
        redis = self._redis()
        level_key = _fn_key(self.ns, function, "level")
        level = int(await redis.get(level_key) or 0)
        days = rules_module.pin_days(level, self.config.rules)
        if not await redis.set(_fn_key(self.ns, function, "pin"), "1", ex=days * 86_400, nx=True):
            return False
        await redis.set(level_key, str(level + 1), ex=LEVEL_TTL)
        logger.warning("assistant_pinned", function=function, level=level, days=days)
        return True

    async def _feed_window(self, writer: str, flagged: bool, effects: Effects) -> None:
        """One exposure flag into the writer's window.

        The window is TUMBLING: when it holds 200 flags it is judged once and emptied, whatever the verdict.
        (Judging a sliding window after every audit would look at the same data thousands of times a month and
        raise the false alarm well above the plan's 0.07% per window.) A rate above the alert rate degrades the
        writer; `SET NX` makes that happen once however many audits finish together.
        """
        redis, rules = self._redis(), self.config.rules
        window = _key("win", writer)
        length = int(await redis.rpush(window, "1" if flagged else "0"))
        await redis.expire(window, LEVEL_TTL)
        if length < rules.window_audits:
            return
        flags = [v == "1" for v in await redis.lrange(window, 0, -1)][-rules.window_audits :]
        await redis.delete(window)
        rate = rules_module.flag_rate(flags)
        metrics.WINDOW_FLAG_RATE.labels(writer=writer, window="exposure").set(rate)
        if rules_module.window_alert(flags, rules) and await redis.set(
            _key("degrade", writer), "1", nx=True
        ):
            await redis.delete(_key("probewin", writer))
            effects.degraded = True
            metrics.WRITER_DEGRADED.labels(writer=writer).set(1)
            logger.error("assistant_writer_degraded", writer=writer, flag_rate=round(rate, 4))

    async def _feed_probe_window(self, writer: str, flagged: bool, effects: Effects) -> None:
        """One probe flag of a degraded writer; 200 of them at 5% or less lift the degrade, else restart."""
        redis, rules = self._redis(), self.config.rules
        window = _key("probewin", writer)
        length = int(await redis.rpush(window, "1" if flagged else "0"))
        await redis.expire(window, LEVEL_TTL)
        if length < rules.window_audits:
            return
        flags = [v == "1" for v in await redis.lrange(window, 0, -1)][-rules.window_audits :]
        await redis.delete(window)
        metrics.WINDOW_FLAG_RATE.labels(writer=writer, window="probe").set(
            rules_module.flag_rate(flags)
        )
        if rules_module.window_recovered(flags, rules):
            await redis.delete(_key("degrade", writer), _key("win", writer))
            effects.recovered = True
            metrics.WRITER_DEGRADED.labels(writer=writer).set(0)
            logger.warning("assistant_writer_recovered", writer=writer)

    def _failed(self, op: str, exc: BaseException) -> None:
        metrics.WATCHDOG_ERRORS.labels(op=op).inc()
        logger.warning("assistant_watchdog_error", op=op, error=type(exc).__name__)


class AuditRunner:
    """Runs audits in the background, a few at a time per API task, holding the text only in memory.

    One instance per process: it only counts how many audits are running, so the per-request watchdog and the
    spend recorder are passed to `run`.
    """

    def __init__(
        self, max_concurrent: int, *, audit: Callable[..., AuditVerdict] = audit_answer
    ) -> None:
        self._limit = max(1, max_concurrent)
        self._running = 0
        self._audit = audit

    async def run(
        self,
        plan: AuditPlan,
        *,
        watchdog: Watchdog,
        add_spend: Callable[[float], Awaitable[Any]],
        client: ModelClient,
        model: str,
        question: str,
        page_function: str | None,
        answer: str,
        evidence: Evidence,
        attached: Mapping[str, Any] | None,
        by_name: Mapping[str, dict[str, Any]],
    ) -> Effects | None:
        """Judge one answer and record the verdict. Never raises; the reservation is refunded on any failure.

        Returns:
            What the verdict changed, or None if the audit was skipped or failed.
        """
        if self._running >= self._limit:
            metrics.AUDITS.labels(result="skipped_busy", pool=plan.pool).inc()
            await watchdog.release(plan)
            return None
        self._running += 1
        try:
            verdict = await asyncio.to_thread(
                self._audit,
                client,
                model,
                question=question,
                page_function=page_function,
                answer=answer,
                evidence=evidence,
                attached=attached,
                by_name=by_name,
            )
        except Exception as exc:  # noqa: BLE001 — the judge failed; the visitor never knows
            metrics.AUDITS.labels(result="error", pool=plan.pool).inc()
            logger.warning("assistant_audit_failed", error=type(exc).__name__)
            await watchdog.release(plan)
            return None
        finally:
            self._running -= 1
        metrics.AUDIT_COST_USD.inc(verdict.cost)
        try:
            await add_spend(verdict.cost)
        except (
            Exception
        ) as exc:  # noqa: BLE001 — AssistantStore.add_spend fails open itself; belt and braces
            logger.warning("assistant_audit_spend_not_recorded", error=type(exc).__name__)
        return await watchdog.record(plan, verdict)


async def audit_after(
    *,
    watchdog: Watchdog,
    runner: AuditRunner,
    add_spend: Callable[[float], Awaitable[Any]],
    client: ModelClient,
    model: str,
    question: str,
    page_function: str | None,
    answer_text: str,
    evidence: Evidence,
    attached: Mapping[str, Any] | None,
    writer: str,
    writer_probe: bool,
    by_name: Mapping[str, dict[str, Any]],
) -> None:
    """The background task of one live answer: decide, then audit. Never raises.

    The decision is taken here, a moment after the response left, from the same counts and draws it would use
    in the request path; the question and the answer live only in this call.
    """
    try:
        fetched = await watchdog.not_pinned(evidence.records)
        plan = await watchdog.plan(functions=fetched, writer=writer, writer_probe=writer_probe)
        if plan is None:
            return
        await runner.run(
            plan,
            watchdog=watchdog,
            add_spend=add_spend,
            client=client,
            model=model,
            question=question,
            page_function=page_function,
            answer=answer_text,
            evidence=evidence,
            attached=attached,
            by_name=by_name,
        )
    except Exception as exc:  # noqa: BLE001 — a background task must not surface anywhere
        metrics.WATCHDOG_ERRORS.labels(op="audit_after").inc()
        logger.warning("assistant_watchdog_error", op="audit_after", error=type(exc).__name__)

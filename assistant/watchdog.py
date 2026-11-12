"""The watchdog's rules: when to audit an answer, when a function is pinned, when a writer is degraded.

Reasoning:
- The plan is docs/assistant-plan-implementation.md section 8. This module holds only the arithmetic: no Redis, no
  network, no clock, no randomness of its own (a caller passes the draw), so every rule is tested exactly and
  the seeded simulations in tests/test_assistant_watchdog_rules.py reproduce the plan's numbers.
- What the watchdog is for: a daily audit budget (about $2) buys a few hundred Opus verdicts on live typed
  answers. That cannot measure a per-function rate near 3.5%; it is a TRIPWIRE for gross, sustained failure of
  one function, and a global alert for a writer that got worse. A false pin degrades the experience (static
  text), never safety, so the rules lean towards few false pins.
- Pin rule (CUSUM confirmed 2026-11-11): CUSUM on the audited flags of one function. S starts at 0; each audit
  adds `flag - CUSUM_ALLOWANCE` (flag is 1 or 0) and S never goes below 0; S >= CUSUM_THRESHOLD pins. The
  arithmetic is in thousandths (integers), so a sequence that lands exactly on the threshold is decided the
  same way on every platform. The numbers are the allowance 0.10 and the threshold **3.0**. The plan wrote
  2.5; measured with exact arithmetic (docs/assistant-phase0-results.md 9.34), 2.5 falsely pins a healthy
  function (3.5%) about 0.10 times a month at 7 audits a day, which is more than the plan's own table (0.04) and
  its acceptance limit (under 0.05), while 3.0 gives 0.038 and the rest of the plan's table (0.004, 0.015,
  0.038, 0.108 a month at 0.7, 2.8, 7 and 20 audits a day; 0.9% of days pinned at 7 a day; the first pin of a
  15% function after 5.4 days at 7 audits a day and 13.6 at 2.8). The plan's line "31, 12, 6 audited answers
  to pin at 15%, 30%, 50%" belonged to 2.5; at 3.0 the medians are 38, 14 and 7, and a function whose answers
  are all flagged is pinned at its 4th audit. "Reference 3.5%" in the plan is the healthy rate the allowance is
  set against; it is not subtracted. The plan's fast trigger, 4 flags in the last 8 audited answers, is kept as
  a guard for a retuned allowance or threshold: with the default numbers it never fires first (4 flags in 8
  audits push S to at least 4 - 8 x 0.10 = 3.2, above the threshold; a test checks all 256 patterns).
- A pin lasts 7 days, doubling on a repeat to at most 28. While pinned the function serves static text and
  receives no audits, so when the pin expires a PROBE follows: the next 20 audited answers are taken at
  100%; fewer than 3 flags unpin it for good, otherwise it is pinned again with the doubled time.
- Audit selection (two pools of one daily budget, 60% coverage and 40% exposure):
  * coverage: water-filling. Audit an answer iff the function has fewer than `tau` audits today. `tau` is the
    largest integer k with sum over functions of min(k, expected answers a day) x verdict cost within the
    pool. The choice depends on counts, never on outcomes, so a function's audited sample is unbiased;
  * exposure: uniform random sampling at probability pool / (verdict cost x eligible answers a day), per
    writer. It gives an unbiased traffic-weighted rate and fills the writer windows. Every writer that has any
    traffic gets at least 25% of the exposure pool, so a small tier's window fills in days, not weeks.
- Writer window: the flags of the last 200 exposure audits of one writer. A full window above 8% degrades the
  writer (its answers become static text plus search results); while degraded 10% of its questions are still
  answered live and audited at 100%, and 200 of those at 5% or less lift the degrade. No human step.
- Only booleans are ever kept. An audit whose verdict could not be read is not a flag and not a pass: it is
  dropped (and counted by the caller), never turned into a pin.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

CUSUM_ALLOWANCE = 0.10
CUSUM_THRESHOLD = 3.0
FAST_FLAGS = 4
FAST_WINDOW = 8
PIN_DAYS = 7
PIN_DAYS_MAX = 28
PROBE_AUDITS = 20
PROBE_MAX_FLAGS = 2  # fewer than 3 flags in the probe unpin the function
WINDOW_AUDITS = 200
ALERT_RATE = 0.08
RECOVER_RATE = 0.05
WRITER_FLOOR = 0.25
HISTORY_KEEP = (
    200  # audited flags kept per function; far more than a CUSUM run needs to reach the threshold
)

PIN_CUSUM = "cusum"
PIN_FAST = "fast"


@dataclass(frozen=True)
class Rules:
    """The tunable numbers, so a test can vary them and the settings can override them.

    Attributes:
        allowance: CUSUM allowance subtracted per audit (a flag adds 1).
        threshold: CUSUM level at which a function is pinned.
        fast_flags, fast_window: the fast trigger, flags in the last audited answers.
        pin_days, pin_days_max: first pin duration in days, and the cap after doublings.
        probe_audits, probe_max_flags: audits taken after a pin expires, and the flags that still allow unpin.
        window_audits: exposure audits in a writer window.
        alert_rate, recover_rate: window flag rate above which a writer is degraded, and at or below which it
            recovers.
        writer_floor: share of the exposure pool each writer with traffic is guaranteed.
    """

    allowance: float = CUSUM_ALLOWANCE
    threshold: float = CUSUM_THRESHOLD
    fast_flags: int = FAST_FLAGS
    fast_window: int = FAST_WINDOW
    pin_days: int = PIN_DAYS
    pin_days_max: int = PIN_DAYS_MAX
    probe_audits: int = PROBE_AUDITS
    probe_max_flags: int = PROBE_MAX_FLAGS
    window_audits: int = WINDOW_AUDITS
    alert_rate: float = ALERT_RATE
    recover_rate: float = RECOVER_RATE
    writer_floor: float = WRITER_FLOOR


DEFAULT_RULES = Rules()


# ── pins ──────────────────────────────────────────────────────────────────────────────────────────────────


def _milli(value: float) -> int:
    return round(value * 1000)


def _step_milli(level: int, flag: bool, allowance: int) -> int:
    return max(0, level + (1000 if flag else 0) - allowance)


def cusum_step(level: float, flag: bool, rules: Rules = DEFAULT_RULES) -> float:
    """One audit later: max(0, level + flag - allowance), computed in thousandths so it is exact."""
    return _step_milli(_milli(level), flag, _milli(rules.allowance)) / 1000


def cusum(flags: Sequence[bool], rules: Rules = DEFAULT_RULES) -> float:
    """The CUSUM level after `flags` (oldest first): S = max(0, S + flag - allowance) over the sequence."""
    allowance, level = _milli(rules.allowance), 0
    for flag in flags:
        level = _step_milli(level, flag, allowance)
    return level / 1000


def pin_reason(flags: Sequence[bool], rules: Rules = DEFAULT_RULES) -> str | None:
    """Why a function with these audited flags (oldest first) should be pinned, or None.

    Returns:
        "cusum" when the CUSUM level reached the threshold, "fast" when the last `fast_window` audits hold at
        least `fast_flags` flags, else None. The CUSUM reason wins when both hold.
    """
    if _milli(cusum(flags, rules)) >= _milli(rules.threshold):
        return PIN_CUSUM
    recent = flags[-rules.fast_window :]
    if len(recent) >= rules.fast_window and sum(1 for f in recent if f) >= rules.fast_flags:
        return PIN_FAST
    return None


def pin_days(level: int, rules: Rules = DEFAULT_RULES) -> int:
    """Pin duration in days for the `level`-th pin of one function (0 is the first): 7, 14, 28, 28, ..."""
    return min(rules.pin_days * (2 ** max(0, level)), rules.pin_days_max)


def probe_outcome(flags: Sequence[bool], rules: Rules = DEFAULT_RULES) -> str:
    """The state of a probe after `flags` (oldest first): "pending", "unpin" or "repin".

    A probe decides on exactly `probe_audits` audits: fewer than `probe_max_flags` + 1 flags unpin the function
    for good, otherwise it is pinned again.
    """
    if len(flags) < rules.probe_audits:
        return "pending"
    taken = flags[: rules.probe_audits]
    return "unpin" if sum(1 for f in taken if f) <= rules.probe_max_flags else "repin"


# ── which answers to audit ────────────────────────────────────────────────────────────────────────────────


def coverage_level(
    expected_per_day: Mapping[str, float], pool_usd: float, verdict_cost: float
) -> int:
    """The water level `tau`: the largest integer k with sum of min(k, expected a day) x cost <= the pool.

    Args:
        expected_per_day: each function's expected answers a day (its trailing 7-day mean).
        pool_usd: dollars of the coverage pool for one day.
        verdict_cost: dollars of one verdict.

    Returns:
        0 when the pool buys nothing; otherwise at most the largest expected count (more would spend nothing).
    """
    if pool_usd <= 0 or verdict_cost <= 0:
        return 0
    counts = sorted(max(0.0, v) for v in expected_per_day.values())
    ceiling = max(1, math.ceil(counts[-1])) if counts else 0
    best = 0
    for k in range(1, ceiling + 1):
        if sum(min(float(k), v) for v in counts) * verdict_cost <= pool_usd:
            best = k
        else:
            break
    return best


def covered(audits_today: int, tau: int) -> bool:
    """True if a function with `audits_today` audits so far today is below the water level and gets this one."""
    return audits_today < tau


def writer_shares(
    eligible_per_day: Mapping[str, float], rules: Rules = DEFAULT_RULES
) -> dict[str, float]:
    """Each writer's share of the exposure pool: at least the floor, the rest in proportion to traffic.

    Writers with no traffic get nothing. If the floors alone exceed the pool the shares are equal.
    """
    active = {w: v for w, v in eligible_per_day.items() if v > 0}
    if not active:
        return {}
    floor = rules.writer_floor
    if floor * len(active) >= 1.0:
        return {w: 1.0 / len(active) for w in active}
    spare = 1.0 - floor * len(active)
    total = sum(active.values())
    return {w: floor + spare * v / total for w, v in active.items()}


def exposure_probability(
    eligible_per_day: float, pool_usd: float, verdict_cost: float, *, share: float = 1.0
) -> float:
    """Probability of auditing one eligible answer of a writer: pool x share / (cost x eligible a day), at most 1.

    With no traffic history (`eligible_per_day` under 1) the denominator is 1 answer, so a cold start audits
    until the budget stops it.
    """
    if pool_usd <= 0 or verdict_cost <= 0 or share <= 0:
        return 0.0
    return min(1.0, pool_usd * share / (verdict_cost * max(1.0, eligible_per_day)))


def budget_allows(spent_usd: float, budget_usd: float, estimate_usd: float) -> bool:
    """True if one more verdict at the estimated cost still fits in the day's audit budget."""
    return spent_usd + estimate_usd <= budget_usd


# ── writers ───────────────────────────────────────────────────────────────────────────────────────────────


def flag_rate(flags: Sequence[bool]) -> float:
    """The share of True in `flags` (0.0 for none)."""
    return sum(1 for f in flags if f) / len(flags) if flags else 0.0


def window_alert(flags: Sequence[bool], rules: Rules = DEFAULT_RULES) -> bool:
    """True if a FULL window of exposure audits has a flag rate above the alert rate.

    A window that is not full never alerts: 40 audits cannot tell 3.5% from 8%, and the plan's false-alarm
    figure (0.07% at a true 3.5%) is for a full window of 200.
    """
    window = flags[-rules.window_audits :]
    return len(window) >= rules.window_audits and flag_rate(window) > rules.alert_rate


def window_recovered(flags: Sequence[bool], rules: Rules = DEFAULT_RULES) -> bool:
    """True if a full window of probe audits has a flag rate at or below the recovery rate."""
    window = flags[-rules.window_audits :]
    return len(window) >= rules.window_audits and flag_rate(window) <= rules.recover_rate


def window_full(flags: Sequence[bool], rules: Rules = DEFAULT_RULES) -> bool:
    """True once `window_audits` audits are in the window."""
    return len(flags) >= rules.window_audits

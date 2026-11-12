"""assistant/watchdog.py: the watchdog's rules, and the plan's section 8 numbers reproduced by seeded simulation.

Reasoning:
- The rules are pure functions, so each is tested exactly. The simulations then check the claims the plan makes
  about them (docs/assistant-plan-implementation.md section 8 and the acceptance criteria of section 12): the
  number of audited answers a failing function needs to be pinned, the rate of false pins on a healthy one, and
  the days a healthy function spends pinned. They use `random.Random` with fixed seeds, so they are
  deterministic; the tolerances are set against the sampling noise of the stated trial counts, not fitted.
- The fast trigger (4 flags in the last 8) is kept as a guard; a test shows it never fires before the CUSUM
  with the default numbers, so the plan's table is the CUSUM's alone.
- The plan wrote the CUSUM threshold as 2.5. Measured with exact arithmetic that setting falsely pins a healthy
  function about 0.10 times a month at 7 audits a day, against the plan's table (0.04) and acceptance limit
  (under 0.05); 3.0 reproduces the table (results 9.34). The assertions below are the exact-arithmetic figures
  for 3.0; the test of the old setting is kept so the difference stays visible.
"""

from __future__ import annotations

import itertools
import random
import statistics

import pytest

from assistant import watchdog as wd
from assistant.watchdog import Rules

# ── pins: CUSUM and the fast trigger ──────────────────────────────────────────────────────────────────────


def test_cusum_adds_a_flag_subtracts_the_allowance_and_never_goes_below_zero() -> None:
    assert wd.cusum([]) == 0.0
    assert wd.cusum([False] * 50) == 0.0
    assert wd.cusum([True]) == pytest.approx(0.9)
    assert wd.cusum([True, False]) == pytest.approx(0.8)
    assert wd.cusum([False, False, True]) == pytest.approx(
        0.9
    )  # the clean ones did not bank credit
    assert wd.cusum([True, True, True]) == pytest.approx(2.7)


def test_four_flags_in_a_row_pin_three_do_not() -> None:
    assert wd.pin_reason([True, True, True]) is None  # 2.7, below the threshold of 3.0
    assert wd.pin_reason([True, True, True, True]) == wd.PIN_CUSUM  # 3.6
    assert wd.pin_reason([False, True, True, True, True]) == wd.PIN_CUSUM


def test_spread_out_flags_pin_only_when_they_come_often_enough() -> None:
    every_other = [True, False] * 4  # 0.9 0.8 1.7 1.6 2.5 2.4 3.3 -> pinned at the seventh audit
    assert wd.pin_reason(every_other[:6]) is None
    assert wd.pin_reason(every_other[:7]) == wd.PIN_CUSUM
    one_in_ten = ([True] + [False] * 9) * 6  # +0.9 then -0.9: never accumulates
    assert wd.pin_reason(one_in_ten) is None


def test_a_sequence_that_lands_exactly_on_the_threshold_pins_on_every_platform() -> None:
    # 0.9 1.8 1.7 1.6 1.5 2.4 2.3 2.2 2.1 3.0: floats can land on 2.9999999999999996; thousandths cannot
    exact = [True, True, False, False, False, True, False, False, False, True]
    assert wd.cusum(exact) == 3.0
    assert wd.pin_reason(exact) == wd.PIN_CUSUM
    assert wd.pin_reason(exact[:-1]) is None


def test_the_fast_trigger_fires_on_its_own_when_the_rules_are_retuned() -> None:
    lenient = Rules(allowance=0.60)  # CUSUM drifts down so slowly it would not catch 4 in 8
    pattern = [True, False, True, False, True, False, True, False]
    assert wd.cusum(pattern, lenient) < lenient.threshold
    assert wd.pin_reason(pattern, lenient) == wd.PIN_FAST
    assert wd.pin_reason(pattern[:7], lenient) is None  # needs the full window of 8


def test_with_the_default_numbers_the_fast_trigger_never_fires_before_the_cusum() -> None:
    for pattern in itertools.product([False, True], repeat=wd.FAST_WINDOW):
        if sum(pattern) >= wd.FAST_FLAGS:
            assert wd.pin_reason(list(pattern)) == wd.PIN_CUSUM, pattern


def test_pin_days_double_to_the_cap() -> None:
    assert [wd.pin_days(level) for level in range(5)] == [7, 14, 28, 28, 28]
    assert wd.pin_days(-3) == 7


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ([False] * 19, "pending"),
        ([False] * 20, "unpin"),
        ([True, True] + [False] * 18, "unpin"),  # two flags still unpin
        ([True, True, True] + [False] * 17, "repin"),  # three do not
        (
            [False] * 20 + [True] * 10,
            "unpin",
        ),  # audits after the twentieth are not part of the probe
        ([], "pending"),
    ],
)
def test_a_probe_decides_on_exactly_twenty_audits(flags: list[bool], expected: str) -> None:
    assert wd.probe_outcome(flags) == expected


# ── pins: the plan's numbers, by seeded simulation ────────────────────────────────────────────────────────


def audits_to_pin(rate: float, rng: random.Random, limit: int = 5000) -> int:
    level, history = 0.0, []
    for n in range(1, limit + 1):
        flag = rng.random() < rate
        level = wd.cusum_step(level, flag)
        history.append(flag)
        if level >= wd.CUSUM_THRESHOLD or wd.pin_reason(history[-wd.FAST_WINDOW :]) is not None:
            return n
    return limit


@pytest.mark.parametrize(("rate", "median"), [(0.15, 38), (0.30, 14), (0.50, 7)])
def test_a_failing_function_needs_this_many_audited_answers_to_be_pinned(
    rate: float, median: int
) -> None:
    # exact arithmetic, threshold 3.0 (the plan's 31, 12, 6 were for 2.5; see results 9.34)
    rng = random.Random(20261112)
    runs = [audits_to_pin(rate, rng) for _ in range(3000)]
    assert abs(statistics.median(runs) - median) <= 2


def test_a_function_whose_answers_are_all_flagged_is_pinned_at_its_fourth_audit() -> None:
    # the deliberately injected failure of section 12: 4 audits, so 0.6 days at 7 a day, 1.4 at 2.8, 5.7 at 0.7
    flags: list[bool] = []
    for audit in range(1, 10):
        flags.append(True)
        if wd.pin_reason(flags):
            break
    assert audit == 4
    assert 4 / 7 < 1 and 4 / 2.8 < 2 and 4 / 0.7 < 6


def test_a_function_failing_15_percent_is_pinned_in_about_five_days_at_seven_audits_a_day() -> None:
    # the plan's table: 5 days at 7 a day, 14 at 2.8 (median runs; exact figures 5.4 and 13.6)
    rng = random.Random(20261113)
    runs = [audits_to_pin(0.15, rng) for _ in range(3000)]
    assert statistics.median(runs) / 7 <= 6.0
    assert statistics.median(runs) / 2.8 <= 14.5


def false_pins_a_month(
    rules: wd.Rules, audits_a_day: float, seed: int, audits: int = 600_000
) -> float:
    rng = random.Random(seed)
    level, pins = 0.0, 0
    for _ in range(audits):
        level = wd.cusum_step(level, rng.random() < 0.035, rules)
        if level >= rules.threshold:
            pins += 1
            level = 0.0
    return pins / (audits / (audits_a_day * 30))


def test_a_healthy_function_is_falsely_pinned_under_five_times_in_a_hundred_months_at_seven_a_day() -> (
    None
):
    # section 8 table: CUSUM at 7 audits a day, true 3.5%: 0.04 false pins a month; acceptance: under 0.05
    rate = false_pins_a_month(wd.DEFAULT_RULES, 7, 20261114)
    assert 0.028 <= rate <= 0.049  # exact figure 0.038
    # the table's other rows follow from the same per-audit rate: 0.004, 0.015, 0.108 a month
    assert rate * 20 / 7 == pytest.approx(0.108, abs=0.02)
    assert rate * 2.8 / 7 == pytest.approx(0.015, abs=0.004)


def test_the_plans_original_threshold_of_2_5_pins_a_healthy_function_twice_as_often() -> None:
    rate = false_pins_a_month(Rules(threshold=2.5), 7, 20261114)
    assert (
        rate > 0.07
    )  # exact figure about 0.10: more than the plan's own table and acceptance limit


def test_a_healthy_function_spends_about_one_day_in_a_hundred_pinned_at_seven_a_day() -> None:
    # 0.038 pins a month x 7 days each is 0.9% of the days (section 8); the pin length is the only cost
    pins_a_month = 0.038
    assert pins_a_month * wd.pin_days(0) / 30 == pytest.approx(0.009, abs=0.0006)


# ── which answers to audit ────────────────────────────────────────────────────────────────────────────────


def test_the_coverage_level_is_the_largest_k_the_pool_pays_for() -> None:
    expected = {"busy": 10.0, "middling": 2.0, "rare": 0.5}
    # k audits cost min(k, 10) + min(k, 2) + min(k, 0.5) verdicts: 9.5 at k=7, 10.5 at k=8
    assert wd.coverage_level(expected, pool_usd=1.0, verdict_cost=0.1) == 7
    assert wd.coverage_level(expected, pool_usd=0.0, verdict_cost=0.1) == 0
    assert wd.coverage_level(expected, pool_usd=1.0, verdict_cost=0.0) == 0
    assert wd.coverage_level({}, pool_usd=1.0, verdict_cost=0.1) == 0
    assert (
        wd.coverage_level(expected, pool_usd=100.0, verdict_cost=0.1) == 10
    )  # nothing left to buy


def test_a_pool_too_small_for_one_audit_each_gives_level_zero() -> None:
    assert wd.coverage_level({"a": 5.0, "b": 5.0}, pool_usd=0.01, verdict_cost=0.0077) == 0


def test_the_plans_budget_covers_each_function_a_few_times_a_day_at_the_plans_traffic() -> None:
    # $2 a day, 60% coverage, $0.0077 a verdict: 155 verdicts; 385 functions at 1 answer a day each need 385 for k=1
    assert wd.coverage_level({f"f{i}": 1.0 for i in range(385)}, 1.2, 0.0077) == 0
    # 60 active functions at 20 answers a day: 155 verdicts / 60 = 2 audits each
    assert wd.coverage_level({f"f{i}": 20.0 for i in range(60)}, 1.2, 0.0077) == 2


def test_an_answer_is_covered_only_below_the_level() -> None:
    assert wd.covered(0, 2) and wd.covered(1, 2)
    assert not wd.covered(2, 2) and not wd.covered(0, 0)


def test_one_writer_gets_the_whole_exposure_pool() -> None:
    assert wd.writer_shares({"haiku": 50.0}) == {"haiku": 1.0}
    assert wd.writer_shares({}) == {}
    assert wd.writer_shares({"haiku": 0.0}) == {}


def test_a_small_writer_keeps_a_quarter_of_the_pool_and_the_rest_follows_traffic() -> None:
    shares = wd.writer_shares({"haiku": 900.0, "sonnet": 100.0})
    assert shares["sonnet"] == pytest.approx(0.25 + 0.5 * 0.1)
    assert shares["haiku"] == pytest.approx(0.25 + 0.5 * 0.9)
    assert sum(shares.values()) == pytest.approx(1.0)


def test_too_many_writers_for_the_floor_share_the_pool_equally() -> None:
    shares = wd.writer_shares({w: float(i + 1) for i, w in enumerate("abcde")})
    assert set(shares.values()) == {0.2}


def test_the_exposure_probability_spends_the_pool_over_the_days_traffic() -> None:
    # pool $0.80 (40% of $2), $0.0077 a verdict, 1000 eligible answers a day: about 104 audits, p = 0.104
    assert wd.exposure_probability(1000, 0.8, 0.0077) == pytest.approx(0.8 / (0.0077 * 1000))
    assert wd.exposure_probability(1000, 0.8, 0.0077, share=0.5) == pytest.approx(0.052, abs=1e-3)


def test_with_no_history_the_probability_is_one_until_the_budget_stops_it() -> None:
    assert wd.exposure_probability(0, 0.8, 0.0077) == 1.0
    assert wd.exposure_probability(0.3, 0.8, 0.0077) == 1.0
    assert wd.exposure_probability(10, 0.8, 0.0077) == 1.0  # 10 answers cost less than the pool


def test_the_exposure_probability_is_zero_without_a_pool_a_price_or_a_share() -> None:
    assert wd.exposure_probability(100, 0.0, 0.0077) == 0.0
    assert wd.exposure_probability(100, 0.8, 0.0) == 0.0
    assert wd.exposure_probability(100, 0.8, 0.0077, share=0.0) == 0.0


def test_the_daily_budget_stops_the_audit_that_would_overshoot_it() -> None:
    assert wd.budget_allows(1.995, 2.0, 0.0077) is False
    assert wd.budget_allows(1.99, 2.0, 0.0077) is True  # 1.9977: the last verdict that fits
    assert wd.budget_allows(0.0, 2.0, 0.0077)


def test_the_exposure_sample_spends_about_the_pool_in_a_simulated_day() -> None:
    rng = random.Random(20261115)
    eligible, pool, cost = 3000, 0.8, 0.0077
    p = wd.exposure_probability(eligible, pool, cost)
    audits = sum(1 for _ in range(eligible) if rng.random() < p)
    assert audits * cost == pytest.approx(pool, rel=0.15)


# ── writers ───────────────────────────────────────────────────────────────────────────────────────────────


def test_a_window_alerts_only_when_full_and_above_eight_percent() -> None:
    assert not wd.window_alert([True] * 199)  # not full: no alert, whatever the rate
    assert not wd.window_alert([True] * 16 + [False] * 184)  # exactly 8%: not above
    assert wd.window_alert([True] * 17 + [False] * 183)  # 8.5%
    assert wd.window_alert([False] * 500 + [True] * 17 + [False] * 183)  # only the last 200 count


def test_a_window_recovers_only_when_full_and_at_five_percent_or_less() -> None:
    assert not wd.window_recovered([False] * 199)
    assert wd.window_recovered([True] * 10 + [False] * 190)  # exactly 5%
    assert not wd.window_recovered([True] * 11 + [False] * 189)


def test_the_flag_rate_and_the_full_window() -> None:
    assert wd.flag_rate([]) == 0.0
    assert wd.flag_rate([True, False, False, False]) == 0.25
    assert wd.window_full([False] * 200) and not wd.window_full([False] * 199)


def test_a_healthy_writer_almost_never_alerts_and_a_writer_at_twice_the_rate_almost_always_does() -> (
    None
):
    # section 8: false alarm 0.07% at a true 3.5% (exact binomial); 8% true alerts 43%, 12% true alerts 95%
    rng = random.Random(20261116)

    def alert_rate(true_rate: float, trials: int = 4000) -> float:
        hits = 0
        for _ in range(trials):
            window = [rng.random() < true_rate for _ in range(wd.WINDOW_AUDITS)]
            hits += wd.window_alert(window)
        return hits / trials

    assert alert_rate(0.035) <= 0.005
    assert alert_rate(0.08) == pytest.approx(0.434, abs=0.04)
    assert alert_rate(0.12) == pytest.approx(0.954, abs=0.02)

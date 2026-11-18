"""tests/test_trial_store.py — the lane's budgets, counters, proof of work and breaker, against an in-process Redis.

Reasoning:
- api/middleware/trial.py holds every number that bounds an anonymous caller, so each is pinned with the
  commands the lane really issues, run on the double of tests/trial_fakes.py (a real server is not used in
  tests). The double implements WATCH, so the retry path of the token bucket is exercised, and keys expire
  against the test's clock, so "refills over time" is a fact, not an assumption.
- The properties that matter: a bucket allows its capacity at once and then one unit per interval; an idle
  bucket stores no credit; a charge after a call may put it into debt; the daily cap and the bucket both bind;
  a refused request gives back what it counted; two tasks can never both take the last unit; and any Redis
  failure on a read means "cannot tell", which the lane treats as off.
"""

from __future__ import annotations

import hashlib
import time

import pytest

from api.middleware import trial as lane
from api.middleware.trial import (
    KEY_ATTACK,
    KEY_BUDGET,
    KEY_COMPUTE,
    KEY_ISSUE,
    KEY_ON,
    KEY_PAUSE,
    KEY_STRIKES,
    Limits,
    StoreUnavailable,
    TrialRefused,
    TrialStore,
)
from tests.trial_fakes import FakeClock, FakeTrialRedis


@pytest.fixture
def parts() -> tuple[FakeClock, FakeTrialRedis, TrialStore]:
    clock = FakeClock(1_800_000_000.0)
    redis = FakeTrialRedis(clock)
    return clock, redis, TrialStore(redis, clock)


async def _limits(store: TrialStore) -> Limits:
    return lane.effective_limits(await store.controls())


# ── controls ──────────────────────────────────────────────────────────────────────────────────────────────


async def test_the_switches_read_as_off_when_their_keys_are_absent(parts) -> None:
    _, redis, store = parts
    controls = await store.controls()
    assert (controls.on, controls.attack, controls.paused, controls.budget) == (
        False,
        False,
        False,
        {},
    )
    redis.data.update({KEY_ON: "1", KEY_ATTACK: "1", KEY_PAUSE: "1"})
    controls = await store.controls()
    assert (controls.on, controls.attack, controls.paused) == (True, True, True)


async def test_an_unreadable_redis_raises_instead_of_answering(parts) -> None:
    _, redis, store = parts
    redis.fail = True
    with pytest.raises(StoreUnavailable):
        await store.controls()
    with pytest.raises(StoreUnavailable):
        await store.compute_ready(lane.effective_limits(lane.Controls(True, False, False, {})))
    with pytest.raises(StoreUnavailable):
        await store.take_issue(lane.effective_limits(lane.Controls(True, False, False, {})))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"compute_daily": 10, "issue_hourly": 3}', {"compute_daily": 10, "issue_hourly": 3}),
        ('{"compute_daily": -5}', {"compute_daily": 0}),
        ('{"compute_daily": "10", "unknown": 1, "issue_daily": true}', {}),
        ("not json", {}),
        ("[1, 2]", {}),
        ("", {}),
        (None, {}),
    ],
)
def test_the_budget_override_keeps_only_whole_numbers_for_known_fields(raw, expected) -> None:
    assert lane.parse_budget_override(raw) == expected


def test_an_override_lowers_a_budget_and_never_raises_it() -> None:
    controls = lane.Controls(True, False, False, {"compute_hourly": 40, "compute_daily": 999_999})
    limits = lane.effective_limits(controls)
    assert (limits.compute_capacity, limits.compute_refill_hour) == (40, 40)
    assert limits.compute_daily == lane.cfg.trial_compute_daily_units


def test_attack_mode_lengthens_the_proof_and_shrinks_the_network_share() -> None:
    normal = lane.effective_limits(lane.Controls(True, False, False, {}))
    attack = lane.effective_limits(lane.Controls(True, True, False, {}))
    assert (normal.pow_bits, normal.asn_share) == (20, 0.25)
    assert (attack.pow_bits, attack.asn_share) == (24, 0.10)


# ── the compute bucket ────────────────────────────────────────────────────────────────────────────────────


async def test_the_compute_bucket_starts_full_and_refills_a_unit_every_36_seconds(parts) -> None:
    clock, redis, store = parts
    limits = await _limits(store)
    assert await store.compute_ready(limits)
    await store.charge_compute(81, limits)  # 19 left: below the 20 needed to start
    assert not await store.compute_ready(limits)
    clock.advance(36)  # one unit back: 20
    assert await store.compute_ready(limits)
    await store.charge_compute(
        100, limits
    )  # overdraft: 180 units of debt against a capacity of 100
    clock.advance(36 * 60)  # an hour repays 60 units: 120 of debt remain, so the level is zero
    assert not await store.compute_ready(limits)
    clock.advance(36 * 39)  # 81 of debt left: level 19, still below the 20 needed
    assert not await store.compute_ready(limits)
    clock.advance(36)  # 80 of debt left: level 20
    assert await store.compute_ready(limits)


async def test_an_idle_bucket_stores_no_credit(parts) -> None:
    clock, redis, store = parts
    limits = await _limits(store)
    await store.charge_compute(1, limits)
    clock.advance(10 * 24 * 3600)  # ten idle days
    await store.charge_compute(100, limits)
    # Capacity is 100: after a full-bucket spend only the refill since remains, not ten days of credit.
    assert not await store.compute_ready(limits)


async def test_the_daily_compute_cap_binds_even_with_a_full_bucket(parts) -> None:
    clock, redis, store = parts
    limits = await _limits(store)
    redis.data[f"{lane.PREFIX_DAY}compute:{lane.utc_date(clock())}"] = "2481"  # 19 left of 2,500
    assert not await store.compute_ready(limits)
    redis.data[f"{lane.PREFIX_DAY}compute:{lane.utc_date(clock())}"] = "2480"
    assert await store.compute_ready(limits)


async def test_a_bucket_key_expires_when_its_debt_is_repaid(parts) -> None:
    clock, redis, store = parts
    limits = await _limits(store)
    await store.charge_compute(10, limits)
    ttl = redis.ttl_seconds(KEY_COMPUTE)
    assert (
        ttl is not None and 360 < ttl <= 360 + 60 + 1
    )  # ten units of 36 s, plus a minute of slack


async def test_a_failed_charge_is_counted_and_never_raised(parts) -> None:
    _, redis, store = parts
    limits = await _limits(store)
    redis.fail = True
    before = lane.UNRECORDED._value.get()
    await store.charge_compute(5, limits)
    assert lane.UNRECORDED._value.get() == before + 1


# ── contention: two API tasks, one unit ───────────────────────────────────────────────────────────────────


async def test_a_concurrent_write_makes_the_watching_transaction_retry(parts) -> None:
    clock, redis, store = parts
    limits = await _limits(store)

    def another_task_takes_a_ticket() -> None:
        redis.data[KEY_ISSUE] = str(int(clock() * 1000) + limits.issue_interval_ms)
        redis._touch(KEY_ISSUE)

    redis.on_execute = another_task_takes_a_ticket
    assert await store.take_issue(limits) == "ok"
    # The retry saw the other task's write: two tickets' worth of debt, not one.
    debt = int(redis.data[KEY_ISSUE]) - int(clock() * 1000)
    assert debt == 2 * limits.issue_interval_ms


async def test_endless_contention_ends_in_unavailable_not_a_pass(parts) -> None:
    clock, redis, store = parts
    limits = await _limits(store)

    original = redis.pipeline

    def always_conflicting(transaction: bool = True):
        pipe = original(transaction)
        real_execute = pipe.execute

        async def execute():
            redis._touch(KEY_ISSUE)
            return await real_execute()

        pipe.execute = execute  # type: ignore[method-assign]
        return pipe

    redis.pipeline = always_conflicting  # type: ignore[method-assign]
    with pytest.raises(StoreUnavailable):
        await store.take_issue(limits)


# ── the issuance bucket ───────────────────────────────────────────────────────────────────────────────────


async def test_twenty_tickets_at_once_then_one_every_six_minutes(parts) -> None:
    clock, _, store = parts
    limits = await _limits(store)
    assert [await store.take_issue(limits) for _ in range(20)] == ["ok"] * 20
    assert await store.take_issue(limits) == "bucket"
    clock.advance(359)
    assert await store.take_issue(limits) == "bucket"
    clock.advance(2)
    assert await store.take_issue(limits) == "ok"


async def test_a_refused_ticket_costs_nothing_the_day_or_the_bucket_can_see(parts) -> None:
    clock, redis, store = parts
    limits = await _limits(store)
    for _ in range(20):
        await store.take_issue(limits)
    day_key = f"{lane.PREFIX_DAY}issue:{lane.utc_date(clock())}"
    used = int(redis.data[day_key])
    assert await store.take_issue(limits) == "bucket"
    assert int(redis.data[day_key]) == used  # the day's count was given back


async def test_the_daily_ticket_cap_is_exact(parts) -> None:
    clock, _, store = parts
    limits = Limits(**{**vars(await _limits(store)), "issue_daily": 5, "issue_capacity": 50})
    assert [await store.take_issue(limits) for _ in range(6)] == ["ok"] * 5 + ["daily"]
    clock.advance(86_400)
    assert await store.take_issue(limits) == "ok"


# ── counters ──────────────────────────────────────────────────────────────────────────────────────────────


async def test_a_counter_refuses_over_its_limit_and_leaves_the_count_at_the_limit(parts) -> None:
    _, redis, store = parts
    results = [await store.take_count("k", 3, 60) for _ in range(5)]
    assert results == [True, True, True, False, False]
    assert redis.data["k"] == "3"
    await store.release_count("k")
    assert await store.take_count("k", 3, 60)


async def test_a_challenge_id_can_be_used_once_and_forgotten_after_its_life(parts) -> None:
    clock, _, store = parts
    assert await store.consume_challenge("abc")
    assert not await store.consume_challenge("abc")
    clock.advance(lane.cfg.trial_pow_ttl_seconds + 11)
    assert await store.consume_challenge("abc")  # expired challenges cannot be replayed anyway


def test_the_network_share_is_a_quarter_of_an_hour_and_at_least_one(parts) -> None:
    _, _, store = parts
    normal = lane.effective_limits(lane.Controls(True, False, False, {}))
    attack = lane.effective_limits(lane.Controls(True, True, False, {}))
    assert (store.asn_cap("issue", normal), store.asn_cap("compute", normal)) == (2, 25)
    assert (store.asn_cap("issue", attack), store.asn_cap("compute", attack)) == (1, 10)


def test_the_asn_header_is_a_number_or_nothing() -> None:
    assert lane.asn_from_headers({"cloudfront-viewer-asn": "64500"}) == "64500"
    for bad in ("", "AS64500", "64500; drop", "1" * 11, "-1"):
        assert lane.asn_from_headers({"cloudfront-viewer-asn": bad}) is None
    assert lane.asn_from_headers({}) is None


# ── the per-IP counter ────────────────────────────────────────────────────────────────────────────────────


def test_an_address_becomes_hashed_keys_with_no_readable_prefix() -> None:
    now = 1_800_000_000.0
    v4 = lane.ip_keys("203.0.113.9", now)
    v6 = lane.ip_keys("2001:db8:1234:5678:aaaa:bbbb:cccc:dddd", now)
    assert [limit for _, limit in v4] == [2]
    assert [limit for _, limit in v6] == [2, 4]  # the /64 and the /48
    for key, _ in v4 + v6:
        assert key.startswith(lane.PREFIX_IP)
        assert "203.0.113" not in key and "2001" not in key.replace(lane.PREFIX_IP, "")


def test_addresses_in_one_slash_64_share_a_counter_and_the_key_changes_daily() -> None:
    now = 1_800_000_000.0
    a = lane.ip_keys("2001:db8:1:2::1", now)
    b = lane.ip_keys("2001:db8:1:2:ffff::9", now)
    other_64 = lane.ip_keys("2001:db8:1:3::1", now)
    assert a == b
    assert a[0] != other_64[0] and a[1] == other_64[1]  # the same /48, a different /64
    tomorrow = lane.ip_keys("2001:db8:1:2::1", now + 86_400)
    assert tomorrow[0][0] != a[0][0]  # the secret rotates with the date


def test_a_value_that_is_not_an_address_is_an_error_not_a_shared_bucket() -> None:
    with pytest.raises(ValueError):
        lane.ip_keys("testclient", 1_800_000_000.0)


# ── proof of work ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("digest", "bits"),
    [
        (b"\xff", 0),
        (b"\x7f", 1),
        (b"\x0f", 4),
        (b"\x00\x80", 8),
        (b"\x00\x01", 15),
        (b"\x00\x00", 16),
    ],
)
def test_leading_zero_bits(digest: bytes, bits: int) -> None:
    assert lane.leading_zero_bits(digest) == bits


def test_a_solved_challenge_verifies_and_returns_its_id() -> None:
    challenge = lane.new_challenge(8)
    nonce = lane.solve(challenge, 8)
    assert lane.check_solution(challenge, nonce, 8) == challenge.split(".")[0]


def test_a_challenge_cannot_be_forged_stretched_or_lowered() -> None:
    challenge = lane.new_challenge(8)
    nonce = lane.solve(challenge, 8)
    cid, expiry, bits, signature = challenge.split(".")
    tampered = [
        f"{cid}.{int(expiry) + 10_000}.{bits}.{signature}",  # a longer life
        f"{cid}.{expiry}.1.{signature}",  # fewer bits
        f"{cid}.{expiry}.{bits}.{'0' * 32}",  # a made-up signature
        f"{cid[:-1]}{'1' if cid[-1] == '0' else '0'}.{expiry}.{bits}.{signature}",  # another id
        "garbage",
    ]
    for forged in tampered:
        with pytest.raises(TrialRefused):
            lane.check_solution(forged, nonce, 1)


def test_a_wrong_nonce_a_bad_nonce_and_an_expired_challenge_are_refused() -> None:
    now = time.time()
    challenge = lane.new_challenge(10, now)
    right = lane.solve(challenge, 10)
    wrong = next(
        n
        for n in (format(i, "x") for i in range(10**6))
        if lane.leading_zero_bits(hashlib.sha256(f"{challenge}:{n}".encode()).digest()) < 10
    )
    for bad in (wrong, "", "x" * 33, "no spaces", right + "!"):
        with pytest.raises(TrialRefused):
            lane.check_solution(challenge, bad, 10, now)
    with pytest.raises(TrialRefused):
        lane.check_solution(challenge, right, 10, now + lane.cfg.trial_pow_ttl_seconds + 1)


def test_a_challenge_for_fewer_bits_than_now_required_is_refused() -> None:
    challenge = lane.new_challenge(8)
    nonce = lane.solve(challenge, 8)
    with pytest.raises(TrialRefused):
        lane.check_solution(challenge, nonce, 12)  # attack mode started after it was issued


def test_the_default_proof_is_twenty_bits_and_twenty_four_in_attack_mode() -> None:
    from config import Settings

    assert Settings.model_fields["trial_pow_bits"].default == 20
    assert Settings.model_fields["trial_pow_bits_attack"].default == 24


# ── the breaker ───────────────────────────────────────────────────────────────────────────────────────────


async def _empty_the_budget(store: TrialStore, limits: Limits) -> None:
    await store.charge_compute(300, limits)


async def test_only_the_first_task_of_the_hour_counts_the_check(parts) -> None:
    clock, redis, store = parts
    second = TrialStore(redis, clock)
    limits = await _limits(store)
    await _empty_the_budget(store, limits)
    await store.hourly_check(limits)
    await second.hourly_check(limits)  # another task, same hour: the Redis key says it is taken
    await store.hourly_check(limits)  # the same task again: remembered in memory
    assert redis.data[KEY_STRIKES] == "1"


async def test_three_empty_hours_start_attack_and_six_pause_and_a_healthy_hour_resets(
    parts,
) -> None:
    clock, redis, store = parts
    limits = await _limits(store)
    for hour in range(1, 7):
        await _empty_the_budget(store, limits)
        await store.hourly_check(limits)
        assert (KEY_ATTACK in redis.data) == (hour >= 3), hour
        assert (KEY_PAUSE in redis.data) == (hour >= 6), hour
        clock.advance(3600)
    redis.data.pop(KEY_COMPUTE)
    redis.data.pop(KEY_ATTACK)
    redis.data.pop(KEY_PAUSE)
    clock.advance(3600)
    await store.hourly_check(limits)  # full bucket, not empty
    assert KEY_STRIKES not in redis.data


async def test_the_flags_expire_on_their_own_so_a_forgotten_one_cannot_lock_the_lane(parts) -> None:
    clock, redis, store = parts
    limits = await _limits(store)
    for hour in range(6):
        await _empty_the_budget(store, limits)
        await store.hourly_check(limits)
        if hour < 5:
            clock.advance(3600)
    assert redis.ttl_seconds(KEY_ATTACK) == pytest.approx(lane.ATTACK_TTL_SECONDS, abs=1)
    assert redis.ttl_seconds(KEY_PAUSE) == pytest.approx(lane.PAUSE_TTL_SECONDS, abs=1)
    clock.advance(lane.ATTACK_TTL_SECONDS + 1)
    assert not (await store.controls()).attack


async def test_a_failing_breaker_check_never_raises_into_the_request(parts) -> None:
    _, redis, store = parts
    limits = await _limits(store)
    redis.fail = True
    await store.hourly_check(limits)  # must not raise


async def test_a_gap_of_three_hours_without_a_check_forgets_the_strikes(parts) -> None:
    clock, redis, store = parts
    limits = await _limits(store)
    await _empty_the_budget(store, limits)
    await store.hourly_check(limits)
    assert redis.data[KEY_STRIKES] == "1"
    clock.advance(lane.STRIKES_TTL_SECONDS + 1)
    assert await redis.get(KEY_STRIKES) is None


def test_the_override_and_switch_key_names_are_the_ones_the_runbook_uses() -> None:
    assert (KEY_ON, KEY_ATTACK, KEY_PAUSE, KEY_BUDGET) == (
        "pyvar:trial:on",
        "pyvar:trial:attack",
        "pyvar:trial:pause",
        "pyvar:trial:budget",
    )

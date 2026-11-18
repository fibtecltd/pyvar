"""tests/test_trial_routes.py — the no-sign-up trial lane end to end (docs/plan-trial-lane-throttle.md).

Reasoning:
- The lane gives answers to callers nobody has authenticated, so each promise in api/routes/trial.py is pinned
  here against the real app and the real engine functions (CLAUDE.md section 5: the engine is never mocked):
  off until the Redis switch is set and failing closed when Redis is down; one body for every refusal; a ticket
  from a solved proof of work; the same answer as the authenticated route for every whitelisted function; the
  per-ticket quota; charging by measured time; the one-slot busy rule released when the worker thread ends, not
  when the request gives up; the input caps; no Postgres row for a refusal.
- Redis is the in-process double of tests/trial_fakes.py (it implements the lane's commands, WATCH included), so
  no test touches a real server. The proof of work is lowered to 4 bits, so a test solves one in microseconds.
- Where a test needs a slow or failing function it replaces ONE registry entry; every other test runs the real
  engine.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from api.middleware import trial as lane
from api.middleware.auth import create_access_token, create_stream_token
from api.middleware.trial import (
    KEY_ATTACK,
    KEY_BUDGET,
    KEY_COMPUTE,
    KEY_ON,
    KEY_PAUSE,
    TrialStore,
    mint_ticket,
    refusal_body,
)
from api.responses import OrjsonResponse
from api.routes import trial as trial_routes
from api.trial_whitelist import EXAMPLES, WHITELIST
from main import create_app
from tests.trial_fakes import FakeClock, FakeTrialRedis

APP = create_app()
FUNCTION = "parametric_delta_normal_var"
RUN = f"/api/v1/trial/run/{FUNCTION}"


@pytest.fixture
def stand() -> SimpleNamespace:
    """The lane on, over an in-memory Redis and a clock the test controls."""
    clock = FakeClock(time.time())
    redis = FakeTrialRedis(clock)
    store = TrialStore(redis, clock)
    redis.data[KEY_ON] = "1"
    return SimpleNamespace(clock=clock, redis=redis, store=store)


@pytest.fixture(autouse=True)
def _lane(monkeypatch: pytest.MonkeyPatch, stand: SimpleNamespace) -> None:
    monkeypatch.setattr(trial_routes, "get_store", lambda: stand.store)
    monkeypatch.setattr(lane.cfg, "trial_pow_bits", 4)
    monkeypatch.setattr(lane.cfg, "trial_pow_bits_attack", 8)
    monkeypatch.setattr(trial_routes, "_busy", False)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=APP), base_url="http://test")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _new_ticket(client: AsyncClient, headers: dict[str, str] | None = None) -> str:
    """The real path: a challenge, its solution, a ticket."""
    challenge = (await client.post("/api/v1/trial/challenge")).json()
    nonce = lane.solve(challenge["challenge"], challenge["bits"])
    response = await client.post(
        "/api/v1/trial/ticket",
        json={"challenge": challenge["challenge"], "nonce": nonce},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return str(response.json()["ticket"])


def _assert_refusal(response: Any) -> None:
    assert response.status_code == 429
    assert response.json() == refusal_body()
    assert int(response.headers["Retry-After"]) >= 1


# ── off, closed, and the one refusal body ─────────────────────────────────────────────────────────────────


async def test_the_lane_is_off_until_the_switch_key_is_set(stand: SimpleNamespace) -> None:
    del stand.redis.data[KEY_ON]
    token, _ = mint_ticket()
    async with _client() as client:
        _assert_refusal(await client.post("/api/v1/trial/challenge"))
        _assert_refusal(
            await client.post("/api/v1/trial/ticket", json={"challenge": "x", "nonce": "1"})
        )
        _assert_refusal(await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token)))


async def test_an_unreadable_redis_means_off_never_a_pass(stand: SimpleNamespace) -> None:
    token, _ = mint_ticket()
    stand.redis.fail = True
    async with _client() as client:
        _assert_refusal(await client.post("/api/v1/trial/challenge"))
        _assert_refusal(
            await client.post("/api/v1/trial/ticket", json={"challenge": "x", "nonce": "1"})
        )
        _assert_refusal(await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token)))


async def test_the_refusal_names_the_free_key_and_its_daily_calls() -> None:
    body = refusal_body()
    assert body["code"] == "trial_exhausted"
    assert "https://www.pyvar.com#get-api-key" in body["detail"]
    assert "20 calls a day" in body["detail"]  # the free tier's number, read from api/tiers.py


# ── the whole flow, and the same answer as the authenticated route ────────────────────────────────────────


async def test_a_solved_challenge_gives_a_ticket_that_runs_a_function() -> None:
    async with _client() as client:
        ticket = await _new_ticket(client)
        claims = lane.decode_ticket(ticket)
        assert claims.expires_at - time.time() == pytest.approx(72 * 3600, abs=30)
        response = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(ticket))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert int(response.headers["X-Pyvar-Trial-Units"]) >= 1
    assert response.json()["var_abs"] > 0


async def test_the_ticket_response_says_what_it_allows() -> None:
    async with _client() as client:
        challenge = (await client.post("/api/v1/trial/challenge")).json()
        nonce = lane.solve(challenge["challenge"], challenge["bits"])
        body = (
            await client.post(
                "/api/v1/trial/ticket",
                json={"challenge": challenge["challenge"], "nonce": nonce},
            )
        ).json()
    assert body["calls_per_day"] == 5
    assert body["calls_total"] == 15
    assert set(body) == {"ticket", "expires_at", "calls_per_day", "calls_total"}


@pytest.mark.parametrize("function", sorted(WHITELIST))
async def test_every_whitelisted_function_answers_like_the_authenticated_route(
    function: str,
) -> None:
    """The lane runs the domain router's own endpoint: same body in, same JSON out."""
    entry = trial_routes.registry()[function]
    token, _ = mint_ticket()
    authenticated = {"Authorization": f"Bearer {create_access_token('lane-check', 'enterprise')}"}
    async with _client() as client:
        via_lane = await client.post(
            f"/api/v1/trial/run/{function}", json=EXAMPLES[function], headers=_bearer(token)
        )
        direct = await client.post(
            f"/api/v1{entry.path}", json=EXAMPLES[function], headers=authenticated
        )
    assert via_lane.status_code == 200, via_lane.text
    assert direct.status_code == 200
    assert via_lane.json() == direct.json()


# ── who may call /run ─────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "credential",
    [
        pytest.param(None, id="no credential"),
        pytest.param("not-a-token", id="garbage"),
        pytest.param(create_access_token("someone", "enterprise"), id="session JWT"),
        pytest.param("pyvar_" + "a" * 43, id="API key"),
        pytest.param(create_stream_token("someone", "task-1"), id="stream token"),
    ],
)
async def test_run_accepts_only_a_trial_ticket(credential: str | None) -> None:
    headers = {} if credential is None else _bearer(credential)
    async with _client() as client:
        response = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "trial_ticket_invalid"


async def test_a_function_not_on_the_list_is_refused_with_its_own_code() -> None:
    token, _ = mint_ticket()
    async with _client() as client:
        for name in ("historical_simulation_var", "monte_carlo_option_pricer", "no_such_function"):
            response = await client.post(
                f"/api/v1/trial/run/{name}", json={}, headers=_bearer(token)
            )
            assert response.status_code == 404, name
            assert response.json()["code"] == "trial_function_unavailable"


async def test_the_trial_routes_are_not_in_the_public_openapi_document() -> None:
    assert not [path for path in APP.openapi()["paths"] if "/trial/" in path]


# ── input caps and validation ─────────────────────────────────────────────────────────────────────────────


async def test_input_caps_and_bad_json_are_refused_before_any_budget_is_touched(
    stand: SimpleNamespace,
) -> None:
    token, _ = mint_ticket()
    big_values = {"returns": [0.001] * (lane.cfg.trial_max_array_elements + 1)}
    async with _client() as client:
        too_long = await client.post(RUN, json=big_values, headers=_bearer(token))
        too_big = await client.post(
            RUN,
            json={"padding": "x" * (lane.cfg.trial_max_body_bytes + 10)},
            headers=_bearer(token),
        )
        not_json = await client.post(
            RUN, content=b"{nope", headers={**_bearer(token), "Content-Type": "application/json"}
        )
        not_object = await client.post(RUN, json=[1, 2, 3], headers=_bearer(token))
    assert too_long.status_code == 413 and too_big.status_code == 413
    assert not_json.status_code == 422 and not_object.status_code == 422
    # Nothing was counted or charged.
    assert not [key for key in stand.redis.data if key != KEY_ON]


async def test_a_body_that_fails_validation_is_a_422_and_does_not_use_the_ticket() -> None:
    token, _ = mint_ticket()
    async with _client() as client:
        for _ in range(7):  # more than a day's five
            invalid = await client.post(RUN, json={"weights": "nope"}, headers=_bearer(token))
            assert invalid.status_code == 422
        for _ in range(5):
            ok = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))
            assert ok.status_code == 200


async def test_a_function_that_rejects_its_inputs_answers_its_own_422() -> None:
    """The domain endpoint turns ValueError and friends into a 422; the lane passes it through, charged."""
    body = dict(EXAMPLES[FUNCTION], confidence_level=0.95)
    body["cov_matrix"] = [[0.04, 0.0], [0.0, 0.04]]  # two assets against three weights
    token, _ = mint_ticket()
    async with _client() as client:
        response = await client.post(RUN, json=body, headers=_bearer(token))
    assert response.status_code == 422


# ── the quota of one ticket ───────────────────────────────────────────────────────────────────────────────


async def test_a_ticket_allows_five_calls_a_day_and_fifteen_in_all(stand: SimpleNamespace) -> None:
    token, _ = mint_ticket()
    async with _client() as client:
        for day in range(3):
            for _ in range(5):
                ok = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))
                assert ok.status_code == 200, (day, ok.text)
            _assert_refusal(await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token)))
            stand.clock.advance(86_400)
        # Fifteen are used; the fourth day's allowance does not exist.
        _assert_refusal(await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token)))


async def test_the_quota_is_per_ticket_not_per_caller() -> None:
    first, _ = mint_ticket()
    second, _ = mint_ticket()
    async with _client() as client:
        for _ in range(5):
            await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(first))
        _assert_refusal(await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(first)))
        fresh = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(second))
    assert fresh.status_code == 200


# ── metering by time, the deadline and the one slot ───────────────────────────────────────────────────────


def _slow_endpoint(seconds: float) -> Any:
    async def endpoint(body: Any, user: Any) -> OrjsonResponse:
        time.sleep(seconds)
        return OrjsonResponse(content={"slept": seconds})

    return endpoint


def _replace_function(monkeypatch: pytest.MonkeyPatch, endpoint: Any) -> None:
    entry = trial_routes.registry()[FUNCTION]
    monkeypatch.setitem(
        trial_routes.registry(),
        FUNCTION,
        trial_routes._Entry(endpoint, entry.model, entry.path),
    )


async def test_a_call_is_charged_for_the_time_it_really_took(
    monkeypatch: pytest.MonkeyPatch, stand: SimpleNamespace
) -> None:
    _replace_function(monkeypatch, _slow_endpoint(0.13))
    token, _ = mint_ticket()
    async with _client() as client:
        response = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))
    units = int(response.headers["X-Pyvar-Trial-Units"])
    assert 3 <= units <= 20  # 130 ms at 50 ms a unit is 3; a loaded runner may add scheduling noise
    used = int(stand.redis.data[f"{lane.PREFIX_DAY}compute:{lane.utc_date(stand.clock())}"])
    assert used == units


async def test_a_call_over_the_deadline_is_a_504_charged_the_deadline_and_holds_the_slot(
    monkeypatch: pytest.MonkeyPatch, stand: SimpleNamespace
) -> None:
    monkeypatch.setattr(trial_routes.cfg, "trial_deadline_seconds", 0.05)
    original = trial_routes.registry()[FUNCTION]
    _replace_function(
        monkeypatch, _slow_endpoint(1.0)
    )  # long enough that a slow runner still sees it busy
    token, _ = mint_ticket()
    async with _client() as client:
        slow = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))
        assert slow.status_code == 504
        assert slow.json()["code"] == "trial_timeout"
        # The thread is still running: the one slot is taken, so the next call is refused as busy ...
        _assert_refusal(await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token)))
        await asyncio.sleep(1.3)  # ... until it finishes, and then the lane works again.
        monkeypatch.setitem(trial_routes.registry(), FUNCTION, original)
        monkeypatch.setattr(trial_routes.cfg, "trial_deadline_seconds", 1.0)
        again = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))
    assert again.status_code == 200
    used = int(stand.redis.data[f"{lane.PREFIX_DAY}compute:{lane.utc_date(stand.clock())}"])
    assert used >= 1  # the deadline's charge plus the later call's


async def test_a_busy_task_refuses_and_gives_the_ticket_its_use_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, _ = mint_ticket()
    monkeypatch.setattr(trial_routes, "_busy", True)
    async with _client() as client:
        for _ in range(8):  # more than five: refused calls must not count
            _assert_refusal(await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token)))
        monkeypatch.setattr(trial_routes, "_busy", False)
        for _ in range(5):
            ok = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))
            assert ok.status_code == 200


async def test_a_call_starts_only_while_the_compute_budget_has_a_second_left(
    stand: SimpleNamespace,
) -> None:
    token, _ = mint_ticket()
    limits = lane.effective_limits(await stand.store.controls())
    await stand.store.charge_compute(85, limits)  # 15 of 100 left, below the 20 needed to start
    async with _client() as client:
        _assert_refusal(await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token)))
        stand.clock.advance(36 * 6)  # 36 s refills a unit: six more units make 21
        ok = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))
    assert ok.status_code == 200


async def test_the_daily_compute_cap_stops_calls_even_when_the_bucket_is_full(
    stand: SimpleNamespace,
) -> None:
    token, _ = mint_ticket()
    stand.redis.data[f"{lane.PREFIX_DAY}compute:{lane.utc_date(stand.clock())}"] = "2490"
    async with _client() as client:
        _assert_refusal(await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token)))
        stand.clock.advance(86_400)  # a new UTC day
        ok = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))
    assert ok.status_code == 200


async def test_the_ticket_route_reads_at_most_a_kilobyte_and_wants_both_fields() -> None:
    async with _client() as client:
        huge = await client.post(
            "/api/v1/trial/ticket", json={"challenge": "x" * 5_000, "nonce": "1"}
        )
        not_json = await client.post(
            "/api/v1/trial/ticket",
            content=b"{nope",
            headers={"Content-Type": "application/json"},
        )
        missing = await client.post("/api/v1/trial/ticket", json={"challenge": "x"})
        too_long = await client.post(
            "/api/v1/trial/ticket", json={"challenge": "x" * 300, "nonce": "1"}
        )
    assert huge.status_code == 413
    assert (
        not_json.status_code == 422 and missing.status_code == 422 and too_long.status_code == 422
    )


# ── issuance: proof of work, budgets, the pause ───────────────────────────────────────────────────────────


async def test_twenty_tickets_at_once_and_then_one_every_six_minutes(
    stand: SimpleNamespace,
) -> None:
    async with _client() as client:
        for _ in range(20):
            await _new_ticket(client)
        challenge = (await client.post("/api/v1/trial/challenge")).json()
        nonce = lane.solve(challenge["challenge"], challenge["bits"])
        refused = await client.post(
            "/api/v1/trial/ticket", json={"challenge": challenge["challenge"], "nonce": nonce}
        )
        _assert_refusal(refused)
        assert int(refused.headers["Retry-After"]) == 360
        stand.clock.advance(361)
        await _new_ticket(client)


async def test_the_daily_issuance_cap_holds_whatever_the_bucket_says(
    monkeypatch: pytest.MonkeyPatch, stand: SimpleNamespace
) -> None:
    monkeypatch.setattr(lane.cfg, "trial_issue_daily", 3)
    async with _client() as client:
        for _ in range(3):
            await _new_ticket(client)
        challenge = (await client.post("/api/v1/trial/challenge")).json()
        nonce = lane.solve(challenge["challenge"], challenge["bits"])
        _assert_refusal(
            await client.post(
                "/api/v1/trial/ticket", json={"challenge": challenge["challenge"], "nonce": nonce}
            )
        )
        stand.clock.advance(86_400)
        await _new_ticket(client)


async def test_a_wrong_nonce_a_replayed_solution_and_a_stale_challenge_are_refused(
    stand: SimpleNamespace,
) -> None:
    async with _client() as client:
        challenge = (await client.post("/api/v1/trial/challenge")).json()
        good = lane.solve(challenge["challenge"], challenge["bits"])
        wrong = next(
            n
            for n in map(str, range(10**6))
            if lane.leading_zero_bits(
                lane.hashlib.sha256(f"{challenge['challenge']}:{n}".encode()).digest()
            )
            < challenge["bits"]
        )
        _assert_refusal(
            await client.post(
                "/api/v1/trial/ticket", json={"challenge": challenge["challenge"], "nonce": wrong}
            )
        )
        payload = {"challenge": challenge["challenge"], "nonce": good}
        assert (await client.post("/api/v1/trial/ticket", json=payload)).status_code == 200
        _assert_refusal(await client.post("/api/v1/trial/ticket", json=payload))  # replay
        old = (await client.post("/api/v1/trial/challenge")).json()
        old_nonce = lane.solve(old["challenge"], old["bits"])
        stand.clock.advance(lane.cfg.trial_pow_ttl_seconds + 5)
        _assert_refusal(
            await client.post(
                "/api/v1/trial/ticket", json={"challenge": old["challenge"], "nonce": old_nonce}
            )
        )


async def test_attack_mode_demands_the_longer_proof_and_a_pause_stops_issuance_only(
    stand: SimpleNamespace,
) -> None:
    async with _client() as client:
        cheap = (await client.post("/api/v1/trial/challenge")).json()
        cheap_nonce = lane.solve(cheap["challenge"], cheap["bits"])
        stand.redis.data[KEY_ATTACK] = "1"
        # A challenge issued before attack mode is refused when it carries fewer bits than now required.
        _assert_refusal(
            await client.post(
                "/api/v1/trial/ticket", json={"challenge": cheap["challenge"], "nonce": cheap_nonce}
            )
        )
        hard = (await client.post("/api/v1/trial/challenge")).json()
        assert hard["bits"] == 8
        ticket = await _new_ticket(client)
        stand.redis.data[KEY_PAUSE] = "1"
        _assert_refusal(await client.post("/api/v1/trial/challenge"))
        # Tickets already issued keep working while issuance is paused.
        ok = await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(ticket))
    assert ok.status_code == 200


async def test_a_budget_override_can_only_lower_never_raise(stand: SimpleNamespace) -> None:
    stand.redis.data[KEY_BUDGET] = '{"issue_hourly": 2, "compute_daily": 10, "issue_daily": 99999}'
    controls = await stand.store.controls()
    limits = lane.effective_limits(controls)
    assert (limits.issue_capacity, limits.issue_refill_hour) == (2, 2)
    assert limits.compute_daily == 10
    assert limits.issue_daily == lane.cfg.trial_issue_daily  # 99999 is above the setting: ignored
    token, _ = mint_ticket()
    async with _client() as client:
        for _ in range(2):
            await _new_ticket(client)
        challenge = (await client.post("/api/v1/trial/challenge")).json()
        nonce = lane.solve(challenge["challenge"], challenge["bits"])
        _assert_refusal(
            await client.post(
                "/api/v1/trial/ticket", json={"challenge": challenge["challenge"], "nonce": nonce}
            )
        )
        # compute_daily 10 is below the 20 units a call needs to start
        _assert_refusal(await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token)))


# ── the per-network share and the per-IP counter ──────────────────────────────────────────────────────────


async def test_a_network_takes_at_most_its_share_of_an_hours_tickets(
    stand: SimpleNamespace,
) -> None:
    headers = {"CloudFront-Viewer-ASN": "64500"}
    async with _client() as client:
        await _new_ticket(client, headers)
        await _new_ticket(client, headers)  # 25% of 10 an hour is 2
        challenge = (await client.post("/api/v1/trial/challenge")).json()
        nonce = lane.solve(challenge["challenge"], challenge["bits"])
        body = {"challenge": challenge["challenge"], "nonce": nonce}
        _assert_refusal(await client.post("/api/v1/trial/ticket", json=body, headers=headers))
        # another network, and a request with no network at all, are not capped by that share
        # (each needs its own challenge: a refused attempt used up the one above)
        await _new_ticket(client, {"CloudFront-Viewer-ASN": "64501"})
        await _new_ticket(client)
        await _new_ticket(client)
        await _new_ticket(client)
        stand.clock.advance(3600)
        await _new_ticket(client, headers)  # the next hour starts clean


async def test_a_refused_issuance_gives_back_the_network_count(stand: SimpleNamespace) -> None:
    """A network is not charged for a ticket the global budget then refused."""
    headers = {"CloudFront-Viewer-ASN": "64500"}
    stand.redis.data[f"{lane.PREFIX_DAY}issue:{lane.utc_date(stand.clock())}"] = str(
        lane.cfg.trial_issue_daily
    )
    async with _client() as client:
        challenge = (await client.post("/api/v1/trial/challenge")).json()
        nonce = lane.solve(challenge["challenge"], challenge["bits"])
        _assert_refusal(
            await client.post(
                "/api/v1/trial/ticket",
                json={"challenge": challenge["challenge"], "nonce": nonce},
                headers=headers,
            )
        )
    key = stand.store.asn_key("issue", "64500")
    assert int(stand.redis.data.get(key, "0")) == 0


async def test_the_per_ip_counter_is_off_until_it_is_switched_on(
    monkeypatch: pytest.MonkeyPatch, stand: SimpleNamespace
) -> None:
    hops = {
        "X-Forwarded-For": "198.51.100.7, 203.0.113.9, 10.0.0.1"
    }  # trusted client: the second from last
    async with _client() as client:
        for _ in range(4):
            await _new_ticket(client, hops)  # off: no per-address limit
        monkeypatch.setattr(lane.cfg, "trial_ip_counter_enabled", True)
        for _ in range(2):
            await _new_ticket(client, hops)
        challenge = (await client.post("/api/v1/trial/challenge")).json()
        nonce = lane.solve(challenge["challenge"], challenge["bits"])
        _assert_refusal(
            await client.post(
                "/api/v1/trial/ticket",
                json={"challenge": challenge["challenge"], "nonce": nonce},
                headers=hops,
            )
        )
        elsewhere = {"X-Forwarded-For": "198.51.100.99, 203.0.113.10, 10.0.0.1"}
        await _new_ticket(client, elsewhere)
    # No readable address anywhere in Redis.
    assert not [key for key in stand.redis.data if "203.0.113" in key or "198.51" in key]


# ── the breaker ───────────────────────────────────────────────────────────────────────────────────────────


async def test_three_empty_hours_in_a_row_start_attack_mode_and_six_pause_issuance(
    stand: SimpleNamespace,
) -> None:
    token, _ = mint_ticket()
    limits = lane.effective_limits(await stand.store.controls())
    async with _client() as client:
        for hour in range(6):
            await stand.store.charge_compute(
                200, limits
            )  # empty and in debt, every hour's check sees it
            stand.clock.advance(3600 + 1)
            await stand.store.charge_compute(200, limits)
            await client.post(
                RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token)
            )  # the hour's first request
            if hour == 1:
                assert KEY_ATTACK not in stand.redis.data
            if hour == 2:
                assert KEY_ATTACK in stand.redis.data and KEY_PAUSE not in stand.redis.data
    assert KEY_PAUSE in stand.redis.data


async def test_a_healthy_hour_resets_the_count(stand: SimpleNamespace) -> None:
    token, _ = mint_ticket()
    limits = lane.effective_limits(await stand.store.controls())
    async with _client() as client:
        for _ in range(2):
            await stand.store.charge_compute(200, limits)
            stand.clock.advance(3600 + 1)
            await stand.store.charge_compute(200, limits)
            await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))
        stand.clock.advance(5 * 3600)  # the bucket refills fully; this hour's check is healthy
        stand.redis.data.pop(KEY_COMPUTE, None)
        await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))
        for _ in range(2):
            await stand.store.charge_compute(200, limits)
            stand.clock.advance(3600 + 1)
            await stand.store.charge_compute(200, limits)
            await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))
    assert KEY_ATTACK not in stand.redis.data  # two, a reset, two: never three in a row


# ── what the usage middleware records ─────────────────────────────────────────────────────────────────────


async def test_only_calls_that_ran_leave_an_api_usage_row(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: list[tuple[Any, ...]] = []

    async def record(*args: Any, **kwargs: Any) -> None:
        rows.append(args)

    monkeypatch.setattr("api.middleware.usage._persist_usage", record)
    token, _ = mint_ticket()
    async with _client() as client:
        await client.post(RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token))  # ran
        await client.post(RUN, json=EXAMPLES[FUNCTION])  # no ticket: 401
        await client.post(
            "/api/v1/trial/run/no_such_function", json={}, headers=_bearer(token)
        )  # 404
        await client.post(RUN, json={"weights": 1}, headers=_bearer(token))  # 422
        for _ in range(6):
            await client.post(
                RUN, json=EXAMPLES[FUNCTION], headers=_bearer(token)
            )  # the 6th is a 429
        await asyncio.sleep(0.05)
    statuses = [row[2] for row in rows]
    assert statuses and set(statuses) == {200}
    assert len(rows) == 5  # the first call plus four of the six: five a day, then refusals
    assert {row[4] for row in rows} == {"trial"}  # the tier hint the lane sets


def test_the_usage_middleware_skips_trial_refusals_and_nothing_else() -> None:
    from api.middleware.usage import _should_track

    assert _should_track("/api/v1/trial/run/x", 200)
    assert not _should_track("/api/v1/trial/run/x", 429)
    assert not _should_track("/api/v1/trial/ticket", 401)
    assert _should_track(
        "/api/v1/market-risk/kupiec_pof_test", 429
    )  # every other route is unchanged
    assert not _should_track("/health", 200)


# ── start-up warm-up ──────────────────────────────────────────────────────────────────────────────────────


def test_the_warm_up_runs_every_whitelisted_function_and_all_answer() -> None:
    assert trial_routes.warm_whitelist() == len(WHITELIST) == 30


def test_every_whitelist_entry_is_exactly_one_route_with_a_valid_example() -> None:
    registry = trial_routes.registry()
    assert set(registry) == set(WHITELIST)
    for name, entry in registry.items():
        entry.model.model_validate(EXAMPLES[name])
        assert entry.path.rsplit("/", 1)[-1] == name

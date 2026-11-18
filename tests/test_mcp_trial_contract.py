"""tests/test_mcp_trial_contract.py — the plugin's trial client against the real trial routes.

Reasoning:
- plugins/mcp (pyvar-mcp 0.3.0) and the API (api/routes/trial.py) are released separately, and a change to either
  that breaks the other is invisible to each side's own tests: the client's tests script the network, the server's
  tests use their own helpers. This file runs the CLIENT's real code (pyvar_mcp.trial) against the SERVER's real code,
  in process, with no socket: the client's one network seam (`_open`) is replaced by an adapter that hands each request
  to the real app through Starlette's TestClient, over the in-memory Redis of tests/trial_fakes.py.
- What it pins: the client's list of trial functions equals the server's whitelist; its proof-of-work solver satisfies
  the server's check; bootstrap, reuse, the quota, a busy task, a replaced ticket and a switched-off lane behave as the
  client's messages promise; and every whitelisted function answers the same through the client as through the
  authenticated route. The plugin's wire label is accepted by the usage allowlist.
- pyvar_mcp is importable here without the `mcp` SDK: pyvar_mcp.client and pyvar_mcp.trial use only the standard library.
"""

from __future__ import annotations

import io
import json
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import pytest
from starlette.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "plugins" / "mcp"))

from api.middleware import trial as lane  # noqa: E402
from api.middleware.auth import create_access_token  # noqa: E402
from api.middleware.trial import KEY_ON, TrialStore  # noqa: E402
from api.routes import trial as trial_routes  # noqa: E402
from api.trial_whitelist import EXAMPLES, WHITELIST  # noqa: E402
from main import create_app  # noqa: E402
from pyvar_mcp import trial as client_trial  # noqa: E402
from pyvar_mcp.trial import Ticket, TicketStore, TrialError, TrialSession  # noqa: E402
from pyvar_mcp.trial_functions import TRIAL_FUNCTIONS  # noqa: E402
from tests.trial_fakes import FakeClock, FakeTrialRedis  # noqa: E402

BASE = "http://testserver"
FUNCTION = "parametric_delta_normal_var"
APP = create_app()


class _Wire:
    """What urllib hands back for a 2xx answer."""

    def __init__(self, response: Any) -> None:
        self.status = response.status_code
        self.headers = response.headers
        self._content = response.content

    def __enter__(self) -> _Wire:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return bytes(self._content)


@pytest.fixture
def lane_on(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The real app with the lane on, over an in-memory Redis, reachable through the client's seam."""
    clock = FakeClock(time.time())
    redis = FakeTrialRedis(clock)
    redis.data[KEY_ON] = "1"
    store = TrialStore(redis, clock)
    monkeypatch.setattr(trial_routes, "get_store", lambda: store)
    monkeypatch.setattr(lane.cfg, "trial_pow_bits", 6)
    monkeypatch.setattr(trial_routes, "_busy", False)
    http = TestClient(APP, base_url=BASE)
    requests: list[tuple[str, str, dict[str, str]]] = []

    def fake_open(request: urllib.request.Request, timeout: float) -> _Wire:
        path = urlsplit(request.full_url).path
        headers = {key: value for key, value in request.header_items()}
        requests.append((request.get_method(), path, headers))
        response = http.request(request.get_method(), path, content=request.data, headers=headers)
        if response.status_code >= 400:
            raise urllib.error.HTTPError(
                request.full_url,
                response.status_code,
                "",
                response.headers,  # type: ignore[arg-type]
                io.BytesIO(response.content),
            )
        return _Wire(response)

    monkeypatch.setattr(client_trial, "_open", fake_open)
    return SimpleNamespace(clock=clock, redis=redis, store=store, requests=requests, http=http)


def _session(tmp_path: Path, sleep: Any = lambda seconds: None) -> TrialSession:
    return TrialSession(BASE, TicketStore(tmp_path / "data", BASE), sleep=sleep)


def _authenticated(http: TestClient, function: str, body: dict[str, Any]) -> Any:
    entry = trial_routes.registry()[function]
    token = create_access_token("contract", "enterprise")
    response = http.post(
        f"/api/v1{entry.path}", json=body, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    return response.json()


# ── the two sides agree on what is shared ─────────────────────────────────────────────────────────────────


def test_the_clients_function_list_is_the_servers_whitelist() -> None:
    assert TRIAL_FUNCTIONS == WHITELIST


@pytest.mark.parametrize("bits", [4, 8, 12])
def test_the_clients_solver_satisfies_the_servers_check(bits: int) -> None:
    challenge = lane.new_challenge(bits)
    nonce = client_trial.solve(challenge, bits)
    assert lane.check_solution(challenge, nonce, bits) == challenge.split(".")[0]


def test_the_clients_limit_covers_the_servers_hardest_setting() -> None:
    """Attack mode asks for the settings' attack bits; the client must be willing to solve exactly that."""
    assert client_trial.MAX_POW_BITS >= lane.cfg.trial_pow_bits_attack >= lane.cfg.trial_pow_bits


def test_the_wire_label_is_on_the_usage_allowlist() -> None:
    from api.middleware.usage import _client_name

    assert _client_name(client_trial.CLIENT_ID) == "pyvar-mcp"


# ── the whole path, against the real routes ───────────────────────────────────────────────────────────────


def test_a_first_call_gets_a_ticket_runs_the_function_and_keeps_the_ticket_privately(
    lane_on: SimpleNamespace, tmp_path: Path
) -> None:
    session = _session(tmp_path)
    result = session.call(FUNCTION, EXAMPLES[FUNCTION])

    assert result == _authenticated(lane_on.http, FUNCTION, EXAMPLES[FUNCTION])
    paths = [path for _, path, _ in lane_on.requests]
    assert paths == [
        "/api/v1/trial/challenge",
        "/api/v1/trial/ticket",
        f"/api/v1/trial/run/{FUNCTION}",
    ]
    stored = json.loads((tmp_path / "data" / "install.json").read_text())
    assert lane.decode_ticket(stored["ticket"]).expires_at == stored["expires_at"]
    assert stored["base_url"] == BASE
    if sys.platform != "win32":
        mode = stat.S_IMODE((tmp_path / "data" / "install.json").stat().st_mode)
        assert mode == 0o600


def test_later_calls_reuse_the_ticket_and_the_label_reaches_the_server(
    lane_on: SimpleNamespace, tmp_path: Path
) -> None:
    session = _session(tmp_path)
    for _ in range(3):
        session.call(FUNCTION, EXAMPLES[FUNCTION])
    paths = [path for _, path, _ in lane_on.requests]
    assert paths.count("/api/v1/trial/challenge") == 1 and paths.count("/api/v1/trial/ticket") == 1
    labels = {headers.get("X-pyvar-client", "") for _, _, headers in lane_on.requests}
    assert all(label.startswith("pyvar-mcp/") for label in labels)


def test_a_new_process_with_the_same_data_directory_does_not_ask_again(
    lane_on: SimpleNamespace, tmp_path: Path
) -> None:
    _session(tmp_path).call(FUNCTION, EXAMPLES[FUNCTION])
    before = len(lane_on.requests)
    _session(tmp_path).call(FUNCTION, EXAMPLES[FUNCTION])
    assert [path for _, path, _ in lane_on.requests[before:]] == [f"/api/v1/trial/run/{FUNCTION}"]


def test_the_sixth_call_of_a_day_is_refused_with_the_servers_words_and_not_retried(
    lane_on: SimpleNamespace, tmp_path: Path
) -> None:
    slept: list[float] = []
    session = _session(tmp_path, sleep=slept.append)
    for _ in range(5):
        session.call(FUNCTION, EXAMPLES[FUNCTION])
    sent = len(lane_on.requests)
    with pytest.raises(TrialError) as caught:
        session.call(FUNCTION, EXAMPLES[FUNCTION])
    assert "https://www.pyvar.com#get-api-key" in caught.value.message
    assert "20 calls a day" in caught.value.message
    assert slept == [] and len(lane_on.requests) == sent + 1  # one request: the wait was too long


def test_a_busy_task_is_waited_out_once_and_then_succeeds(
    lane_on: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _session(tmp_path)
    session.call(FUNCTION, EXAMPLES[FUNCTION])  # gets the ticket
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        monkeypatch.setattr(trial_routes, "_busy", False)  # the slot frees while the client waits

    session._sleep = sleep
    monkeypatch.setattr(trial_routes, "_busy", True)
    assert session.call(FUNCTION, EXAMPLES[FUNCTION])
    assert waits == [2.0]  # the server's Retry-After for "busy"


def test_a_ticket_the_server_no_longer_accepts_is_replaced_once(
    lane_on: SimpleNamespace, tmp_path: Path
) -> None:
    from jose import jwt

    expired = jwt.encode(
        {
            "aud": lane.TRIAL_AUDIENCE,
            "jti": "abcdefghijklmnopqrstuv",
            "iat": int(time.time()) - 400_000,
            "exp": int(time.time()) - 100_000,
        },
        lane.cfg.jwt_secret,
        algorithm=lane.cfg.jwt_algorithm,
    )
    store = TicketStore(tmp_path / "data", BASE)
    store.save(Ticket(str(expired), int(time.time()) + 7200, BASE))  # the file says it is fine
    result = TrialSession(BASE, store).call(FUNCTION, EXAMPLES[FUNCTION])
    assert result == _authenticated(lane_on.http, FUNCTION, EXAMPLES[FUNCTION])
    paths = [path for _, path, _ in lane_on.requests]
    assert paths[0] == f"/api/v1/trial/run/{FUNCTION}" and paths[1:3] == [
        "/api/v1/trial/challenge",
        "/api/v1/trial/ticket",
    ]
    assert store.load().ticket != str(expired)  # type: ignore[union-attr]


def test_a_switched_off_lane_gives_the_servers_words_and_stores_nothing(
    lane_on: SimpleNamespace, tmp_path: Path
) -> None:
    del lane_on.redis.data[KEY_ON]
    with pytest.raises(TrialError, match="free key"):
        _session(tmp_path).call(FUNCTION, EXAMPLES[FUNCTION])
    assert not (tmp_path / "data" / "install.json").exists()


def test_a_paused_issuance_refuses_a_new_ticket_but_not_the_one_in_hand(
    lane_on: SimpleNamespace, tmp_path: Path
) -> None:
    session = _session(tmp_path)
    session.call(FUNCTION, EXAMPLES[FUNCTION])
    lane_on.redis.data[lane.KEY_PAUSE] = "1"
    assert session.call(FUNCTION, EXAMPLES[FUNCTION])  # the ticket in hand keeps working
    other = _session(tmp_path / "second")
    with pytest.raises(TrialError, match="free key"):
        other.call(FUNCTION, EXAMPLES[FUNCTION])


def test_attack_mode_asks_for_a_longer_puzzle_and_the_client_solves_it(
    lane_on: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lane.cfg, "trial_pow_bits_attack", 10)
    lane_on.redis.data[lane.KEY_ATTACK] = "1"
    assert _session(tmp_path).call(FUNCTION, EXAMPLES[FUNCTION])


# ── every whitelisted function, through the client ────────────────────────────────────────────────────────


@pytest.mark.parametrize("function", sorted(WHITELIST))
def test_every_whitelisted_function_answers_through_the_client_like_the_authenticated_route(
    lane_on: SimpleNamespace, tmp_path: Path, function: str
) -> None:
    token, minted = lane.mint_ticket()
    store = TicketStore(tmp_path / "data", BASE)
    store.save(
        Ticket(token, minted.expires_at, BASE)
    )  # a ticket per function: five calls a day each
    result = TrialSession(BASE, store).call(function, EXAMPLES[function])
    assert result == _authenticated(lane_on.http, function, EXAMPLES[function])

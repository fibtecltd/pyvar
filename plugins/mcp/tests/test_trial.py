"""tests/test_trial.py — the no-sign-up trial: ticket file, proof of work, retries, where it may run.

Reasoning:
- The ticket file is the one thing this plugin writes, so what it holds, who may read it, where it lives and when
  it is replaced are pinned here: install.json in CLAUDE_PLUGIN_DATA, mode 0600, replaced atomically, ignored if
  it is corrupt, from another API address, or about to expire; a lock file keeps two processes from asking for two
  tickets; nothing is written until a call actually needs a ticket.
- The network is replaced at one seam (`pyvar_mcp.trial._post`, which returns status, headers and body), so no test
  reaches pyvar.com. The contract against the real server code is tested in the main repository
  (tests/test_mcp_trial_contract.py), where both sides exist.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pyvar_mcp import trial
from pyvar_mcp.trial import (
    LOCK_FILE,
    TICKET_FILE,
    Ticket,
    TicketStore,
    TrialError,
    TrialHttpError,
    TrialSession,
)
from pyvar_mcp.trial_functions import TRIAL_FUNCTIONS

BASE = "https://www.pyvar.com"
FUNCTION = "parametric_delta_normal_var"
NOW = 1_800_000_000.0


class Script:
    """A scripted `_post`: answers in order and records what was asked."""

    def __init__(self, *answers: tuple[int, dict[str, str], str]) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, dict[str, Any], str | None]] = []

    def __call__(self, url: str, payload: dict[str, Any], bearer: str | None = None):
        self.calls.append((url, payload, bearer))
        if not self.answers:
            raise AssertionError(f"unexpected request to {url}")
        return self.answers.pop(0)

    @property
    def paths(self) -> list[str]:
        return [url.removeprefix(BASE) for url, _, _ in self.calls]


def _challenge(bits: int = 4) -> tuple[int, dict[str, str], str]:
    return 200, {}, json.dumps({"challenge": f"abcd.{int(NOW) + 120}.{bits}.sig", "bits": bits})


def _ticket(token: str = "ticket-1", life: int = 72 * 3600) -> tuple[int, dict[str, str], str]:
    return 200, {}, json.dumps({"ticket": token, "expires_at": int(NOW) + life})


def _ok(result: dict[str, Any] | None = None) -> tuple[int, dict[str, str], str]:
    return 200, {}, json.dumps(result or {"var_abs": 1.5})


def _refusal(retry_after: str = "360") -> tuple[int, dict[str, str], str]:
    body = {
        "code": "trial_exhausted",
        "detail": "The no-sign-up trial is busy. A free key gives 20 calls a day: register at X.",
    }
    return 429, {"retry-after": retry_after}, json.dumps(body)


@pytest.fixture
def store(tmp_path: Path) -> TicketStore:
    return TicketStore(tmp_path / "data", BASE, clock=lambda: NOW)


@pytest.fixture
def session(store: TicketStore) -> TrialSession:
    slept: list[float] = []
    made = TrialSession(BASE, store, sleep=slept.append)
    made.slept = slept  # type: ignore[attr-defined]
    return made


# ── where the trial may run ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["true", "1", "yes", "TRUE", "anything"])
def test_a_set_ci_variable_means_no_trial(value: str) -> None:
    message = trial.unavailable_message({"CI": value, "CLAUDE_PLUGIN_DATA": "/x"})
    assert message and "CI is set" in message and "PYVAR_API_KEY" in message


@pytest.mark.parametrize("value", ["", "0", "false", "no", " "])
def test_an_unset_or_false_ci_variable_does_not_block_the_trial(value: str) -> None:
    assert trial.unavailable_message({"CI": value, "CLAUDE_PLUGIN_DATA": "/x"}) is None


def test_without_a_plugin_data_directory_there_is_no_trial() -> None:
    message = trial.unavailable_message({})
    assert message and "plugin settings" in message and "Claude Code" in message


def test_the_session_refuses_to_start_where_the_trial_is_unavailable() -> None:
    with pytest.raises(TrialError, match="CI is set"):
        TrialSession.from_env(BASE, {"CI": "true", "CLAUDE_PLUGIN_DATA": "/x"})
    with pytest.raises(TrialError):
        TrialSession.from_env(BASE, {})


def test_the_trial_list_is_thirty_names() -> None:
    assert len(TRIAL_FUNCTIONS) == 30 and FUNCTION in TRIAL_FUNCTIONS


def test_the_client_label_matches_the_one_the_key_path_sends() -> None:
    from pyvar_mcp.client import CLIENT_ID

    assert trial.CLIENT_ID == CLIENT_ID


# ── the ticket file ───────────────────────────────────────────────────────────────────────────────────────


def test_saving_writes_one_small_file_in_the_data_directory_only(store: TicketStore) -> None:
    store.save(Ticket("tkn", int(NOW) + 7200, BASE))
    names = sorted(p.name for p in store.directory.iterdir())
    assert names == [TICKET_FILE]  # no temporary file, no lock file left behind
    data = json.loads(store.path.read_text())
    assert data == {
        "version": 1,
        "ticket": "tkn",
        "expires_at": int(NOW) + 7200,
        "issued_at": int(NOW),
        "base_url": BASE,
    }


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_the_ticket_file_is_readable_by_its_owner_only(store: TicketStore) -> None:
    previous = os.umask(0)  # a permissive umask must not widen the mode
    try:
        store.save(Ticket("tkn", int(NOW) + 7200, BASE))
    finally:
        os.umask(previous)
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_a_saved_ticket_is_loaded_back(store: TicketStore) -> None:
    store.save(Ticket("tkn", int(NOW) + 7200, BASE))
    assert store.load() == Ticket("tkn", int(NOW) + 7200, BASE)


def test_saving_replaces_the_old_file_in_one_step(store: TicketStore) -> None:
    store.save(Ticket("old", int(NOW) + 7200, BASE))
    with patch("pyvar_mcp.trial.os.replace", wraps=os.replace) as replace:
        store.save(Ticket("new", int(NOW) + 7200, BASE))
    assert replace.call_count == 1
    assert store.load() == Ticket("new", int(NOW) + 7200, BASE)


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        "{}",
        '{"ticket": "", "expires_at": 1900000000, "base_url": "https://www.pyvar.com"}',
        '{"ticket": "t", "expires_at": "soon", "base_url": "https://www.pyvar.com"}',
        '{"ticket": "t", "expires_at": true, "base_url": "https://www.pyvar.com"}',
        '{"ticket": 5, "expires_at": 1900000000, "base_url": "https://www.pyvar.com"}',
        '{"ticket": "t", "expires_at": 1900000000}',
    ],
)
def test_a_damaged_file_is_ignored_not_trusted(store: TicketStore, content: str) -> None:
    store.directory.mkdir(parents=True)
    store.path.write_text(content)
    assert store.load() is None


def test_an_oversized_file_is_ignored(store: TicketStore) -> None:
    store.directory.mkdir(parents=True)
    store.path.write_text('{"ticket": "' + "x" * 20_000 + '"}')
    assert store.load() is None


def test_a_ticket_from_another_address_is_not_used(store: TicketStore) -> None:
    store.save(Ticket("tkn", int(NOW) + 7200, "https://dev.pyvar.com"))
    assert store.load() is None


def test_a_ticket_close_to_its_end_is_replaced_rather_than_used(store: TicketStore) -> None:
    store.save(Ticket("tkn", int(NOW) + trial.REUSE_MARGIN_SECONDS - 1, BASE))
    assert store.load() is None
    store.save(Ticket("tkn", int(NOW) + trial.REUSE_MARGIN_SECONDS + 1, BASE))
    assert store.load() is not None


def test_clearing_a_missing_file_is_fine(store: TicketStore) -> None:
    store.clear()
    store.save(Ticket("tkn", int(NOW) + 7200, BASE))
    store.clear()
    assert not store.path.exists()


# ── the lock ──────────────────────────────────────────────────────────────────────────────────────────────


def test_a_second_holder_waits_and_then_gives_up_with_a_clear_message(store: TicketStore) -> None:
    with store.lock():
        with pytest.raises(TrialError, match="Another pyvar-mcp process"):
            with store.lock(wait_seconds=0.15):
                raise AssertionError("must not get in")
    with store.lock(wait_seconds=0.15):
        pass  # released on exit
    assert not (store.directory / LOCK_FILE).exists()


def test_a_stale_lock_from_a_dead_process_is_taken_over(store: TicketStore) -> None:
    store.directory.mkdir(parents=True)
    lock_path = store.directory / LOCK_FILE
    lock_path.write_text("")
    old = time.time() - trial.LOCK_STALE_SECONDS - 5
    os.utime(lock_path, (old, old))
    with store.lock(wait_seconds=0.15):
        pass


def test_the_lock_is_released_when_the_work_raises(store: TicketStore) -> None:
    with pytest.raises(RuntimeError):
        with store.lock():
            raise RuntimeError("boom")
    assert not (store.directory / LOCK_FILE).exists()


# ── the proof of work ─────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bits", [1, 8, 12, 16])
def test_the_solution_has_the_required_leading_zero_bits(bits: int) -> None:
    import hashlib

    challenge = "someid.1900000000.%d.signature" % bits
    nonce = trial.solve(challenge, bits)
    digest = hashlib.sha256(f"{challenge}:{nonce}".encode()).digest()
    assert int.from_bytes(digest, "big") >> (256 - bits) == 0


def test_solving_gives_up_when_the_budget_runs_out() -> None:
    with pytest.raises(TrialError, match="took too long"):
        trial.solve("x.1.40.sig", 40, budget_seconds=0.0)


# ── nothing happens until a call needs a ticket ───────────────────────────────────────────────────────────


def test_creating_a_session_touches_no_file_and_no_network(store: TicketStore) -> None:
    with patch("pyvar_mcp.trial._post", side_effect=AssertionError("no network")):
        TrialSession(BASE, store)
    assert not store.directory.exists()


def test_a_function_not_on_the_list_is_refused_without_a_request_or_a_file(
    session: TrialSession,
) -> None:
    script = Script()
    with patch("pyvar_mcp.trial._post", script):
        with pytest.raises(TrialError, match="free pyvar API key") as caught:
            session.call("historical_simulation_var", {})
    assert script.calls == [] and not session.store.directory.exists()
    assert "30 functions" in caught.value.message and trial.REGISTER_URL in caught.value.message


# ── bootstrap and reuse ───────────────────────────────────────────────────────────────────────────────────


def test_the_first_call_asks_for_a_ticket_then_runs_the_function(session: TrialSession) -> None:
    script = Script(_challenge(4), _ticket("tkn"), _ok({"var_abs": 9.5}))
    with patch("pyvar_mcp.trial._post", script):
        result = session.call(FUNCTION, {"weights": [1.0]})
    assert result == {"var_abs": 9.5}
    assert script.paths == [
        "/api/v1/trial/challenge",
        "/api/v1/trial/ticket",
        f"/api/v1/trial/run/{FUNCTION}",
    ]
    ticket_request = script.calls[1][1]
    assert set(ticket_request) == {"challenge", "nonce"}  # a solved puzzle and nothing else
    assert script.calls[2][2] == "tkn" and script.calls[2][1] == {"weights": [1.0]}
    assert session.store.load() is not None


def test_the_second_call_reuses_the_stored_ticket(session: TrialSession) -> None:
    script = Script(_challenge(), _ticket("tkn"), _ok(), _ok())
    with patch("pyvar_mcp.trial._post", script):
        session.call(FUNCTION, {})
        session.call(FUNCTION, {})
    assert script.paths.count("/api/v1/trial/challenge") == 1
    assert [bearer for _, _, bearer in script.calls[2:]] == ["tkn", "tkn"]


def test_a_new_process_reuses_the_file_without_asking_again(store: TicketStore) -> None:
    store.save(Ticket("kept", int(NOW) + 7200, BASE))
    script = Script(_ok())
    with patch("pyvar_mcp.trial._post", script):
        TrialSession(BASE, store).call(FUNCTION, {})
    assert script.paths == [f"/api/v1/trial/run/{FUNCTION}"] and script.calls[0][2] == "kept"


def test_two_processes_starting_together_ask_for_one_ticket(tmp_path: Path) -> None:
    """The second waits on the lock, then finds the first one's ticket instead of asking again."""
    directory = tmp_path / "data"
    challenges = 0
    gate = threading.Event()

    def server(url: str, payload: dict[str, Any], bearer: str | None = None):
        nonlocal challenges
        if url.endswith("/challenge"):
            challenges += 1
            gate.wait(0.3)  # keep the first one inside the lock for a moment
            return _challenge(4)
        if url.endswith("/ticket"):
            return _ticket("shared")
        return _ok()

    results: list[Any] = []

    def worker() -> None:
        made = TrialSession(BASE, TicketStore(directory, BASE, clock=lambda: NOW))
        results.append(made.call(FUNCTION, {}))

    with patch("pyvar_mcp.trial._post", server):
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        time.sleep(0.1)
        gate.set()
        for thread in threads:
            thread.join(10)
    assert len(results) == 2 and challenges == 1


# ── one retry, no more ────────────────────────────────────────────────────────────────────────────────────


def test_a_refused_ticket_is_deleted_and_replaced_once(session: TrialSession) -> None:
    session.store.save(Ticket("stale", int(NOW) + 7200, BASE))
    invalid = (401, {}, json.dumps({"code": "trial_ticket_invalid", "detail": "expired"}))
    script = Script(invalid, _challenge(), _ticket("fresh"), _ok({"var_abs": 2.0}))
    with patch("pyvar_mcp.trial._post", script):
        assert session.call(FUNCTION, {}) == {"var_abs": 2.0}
    assert [bearer for _, _, bearer in script.calls if bearer] == ["stale", "fresh"]
    assert session.store.load().ticket == "fresh"  # type: ignore[union-attr]


def test_a_second_refusal_after_the_replacement_is_returned_not_retried(
    session: TrialSession,
) -> None:
    session.store.save(Ticket("stale", int(NOW) + 7200, BASE))
    invalid = (401, {}, json.dumps({"code": "trial_ticket_invalid", "detail": "expired"}))
    script = Script(invalid, _challenge(), _ticket("fresh"), invalid)
    with patch("pyvar_mcp.trial._post", script):
        with pytest.raises(TrialHttpError) as caught:
            session.call(FUNCTION, {})
    assert caught.value.status_code == 401 and len(script.calls) == 4


def test_a_busy_refusal_with_a_short_wait_is_waited_out_once(session: TrialSession) -> None:
    script = Script(_challenge(), _ticket(), _refusal("2"), _ok({"var_abs": 3.0}))
    with patch("pyvar_mcp.trial._post", script):
        assert session.call(FUNCTION, {}) == {"var_abs": 3.0}
    assert session.slept == [2.0]  # type: ignore[attr-defined]


def test_two_busy_refusals_in_a_row_give_the_servers_words(session: TrialSession) -> None:
    script = Script(_challenge(), _ticket(), _refusal("2"), _refusal("2"))
    with patch("pyvar_mcp.trial._post", script):
        with pytest.raises(TrialError, match="free key"):
            session.call(FUNCTION, {})
    assert session.slept == [2.0]  # type: ignore[attr-defined]  # one wait, not two


def test_a_long_wait_is_reported_not_slept(session: TrialSession) -> None:
    script = Script(_challenge(), _ticket(), _refusal("3600"))
    with patch("pyvar_mcp.trial._post", script):
        with pytest.raises(TrialError) as caught:
            session.call(FUNCTION, {})
    assert session.slept == []  # type: ignore[attr-defined]
    assert "register at X" in caught.value.message and "about 60 minutes" in caught.value.message


def test_a_refused_challenge_gives_the_servers_words_and_writes_nothing(
    session: TrialSession,
) -> None:
    script = Script(_refusal("300"))
    with patch("pyvar_mcp.trial._post", script):
        with pytest.raises(TrialError, match="free key") as caught:
            session.call(FUNCTION, {})
    assert "about 5 minutes" in caught.value.message
    assert not (session.store.directory / TICKET_FILE).exists()
    assert not (session.store.directory / LOCK_FILE).exists()


def test_a_puzzle_that_is_too_hard_or_malformed_is_not_solved(session: TrialSession) -> None:
    for bad in (
        _challenge(trial.MAX_POW_BITS + 1),
        _challenge(0),
        (200, {}, json.dumps({"challenge": 5, "bits": 4})),
        (200, {}, "not json"),
    ):
        script = Script(bad)
        with patch("pyvar_mcp.trial._post", script):
            with pytest.raises(TrialError):
                session.call(FUNCTION, {})
        assert len(script.calls) == 1  # no ticket request after an unsolvable puzzle


def test_a_malformed_ticket_answer_is_an_error_and_is_not_stored(session: TrialSession) -> None:
    script = Script(_challenge(), (200, {}, json.dumps({"ticket": "t"})))
    with patch("pyvar_mcp.trial._post", script):
        with pytest.raises(TrialError):
            session.call(FUNCTION, {})
    assert not (session.store.directory / TICKET_FILE).exists()


@pytest.mark.parametrize("code", [404, 413, 422, 504])
def test_function_level_answers_pass_through_with_their_status(
    session: TrialSession, code: int
) -> None:
    session.store.save(Ticket("tkn", int(NOW) + 7200, BASE))
    body = json.dumps({"detail": "x"})
    with patch("pyvar_mcp.trial._post", Script((code, {}, body))):
        with pytest.raises(TrialHttpError) as caught:
            session.call(FUNCTION, {})
    assert (caught.value.status_code, caught.value.body) == (code, body)


def test_a_result_that_is_not_json_is_an_error(session: TrialSession) -> None:
    session.store.save(Ticket("tkn", int(NOW) + 7200, BASE))
    with patch("pyvar_mcp.trial._post", Script((200, {}, "<html>"))):
        with pytest.raises(TrialError, match="not JSON"):
            session.call(FUNCTION, {})


def test_the_ticket_never_appears_in_an_error_message(session: TrialSession) -> None:
    secret = "tkn-very-secret"
    session.store.save(Ticket(secret, int(NOW) + 7200, BASE))
    for answer in (_refusal("3600"), (500, {}, "boom"), (404, {}, json.dumps({"detail": "no"}))):
        with patch("pyvar_mcp.trial._post", Script(answer)):
            with pytest.raises(TrialError) as caught:
                session.call(FUNCTION, {})
        assert secret not in caught.value.message


# ── the network seam ──────────────────────────────────────────────────────────────────────────────────────


class _Response:
    status = 200
    headers = {"Retry-After": "7"}

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return b'{"ok": true}'


def test_post_sends_the_label_the_ticket_and_json_and_lowercases_headers() -> None:
    captured: dict[str, Any] = {}

    def fake_open(request: urllib.request.Request, timeout: float) -> _Response:
        captured["headers"] = {k.lower(): v for k, v in request.header_items()}
        captured["data"] = request.data
        captured["method"] = request.get_method()
        return _Response()

    with patch("pyvar_mcp.trial._open", fake_open):
        status, headers, body = trial._post(f"{BASE}/x", {"a": 1}, bearer="tkn")
    assert (status, body) == (200, '{"ok": true}') and headers == {"retry-after": "7"}
    assert captured["method"] == "POST" and json.loads(captured["data"]) == {"a": 1}
    assert captured["headers"]["authorization"] == "Bearer tkn"
    assert captured["headers"]["x-pyvar-client"].startswith("pyvar-mcp/")
    assert captured["headers"]["content-type"] == "application/json"


def test_post_without_a_ticket_sends_no_authorization_header() -> None:
    captured: dict[str, Any] = {}

    def fake_open(request: urllib.request.Request, timeout: float) -> _Response:
        captured["headers"] = {k.lower() for k, _ in request.header_items()}
        return _Response()

    with patch("pyvar_mcp.trial._open", fake_open):
        trial._post(f"{BASE}/x", {})
    assert "authorization" not in captured["headers"]


def test_post_returns_an_http_error_as_a_result() -> None:
    error = urllib.error.HTTPError(
        f"{BASE}/x", 429, "Too Many", {"Retry-After": "9"}, __import__("io").BytesIO(b'{"a":1}')
    )
    with patch("pyvar_mcp.trial._open", side_effect=error):
        assert trial._post(f"{BASE}/x", {}) == (429, {"retry-after": "9"}, '{"a":1}')


def test_post_turns_a_network_failure_into_a_clear_error() -> None:
    with patch("pyvar_mcp.trial._open", side_effect=urllib.error.URLError("refused")):
        with pytest.raises(TrialError, match="Cannot reach pyvar.com: refused"):
            trial._post(f"{BASE}/x", {})


def test_a_redirect_is_never_followed_so_a_ticket_cannot_be_forwarded() -> None:
    handler = trial._NoRedirect()
    assert (
        handler.redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example") is None
    )
    assert any(isinstance(h, trial._NoRedirect) for h in trial._OPENER.handlers)

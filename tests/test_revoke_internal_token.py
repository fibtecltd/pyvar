"""scripts/revoke_internal_token.py: listing outstanding internal tokens and recording revocations.

Reasoning:
- The API has no revocation list for JWTs, so this command's most important property is that it never
  claims more than it does. The tests pin that: `revoke` exits 4 ("recorded, not enforced") while
  any matching token is still valid, writes only appended ledger lines, and prints the warning; it
  exits 0 only when nothing valid was left.
- The ledger is built the way real use builds it (with scripts/mint_internal_token.py), plus
  hand-written lines for the cases that need a past expiry or a colliding prefix.
- The runbook is text for a person; the tests check it names the real secret, cluster and service
  and the details that bite (no trailing newline in the new secret), and that it holds no secret.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mint = load("mint_internal_token")
revoke = load("revoke_internal_token")
tools = sys.modules["token_tools"]

SECRET = "dummy-secret-for-tests-only-0123456789abcdefghijklmnopqrstuvwxyz"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv(tools.LEDGER_ENV, raising=False)


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "ledger.jsonl"


def mint_one(ledger, monkeypatch, capsys, *extra):
    """Mint a real token into `ledger`; return its claims."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(SECRET))
    args = ["--secret-stdin", "--ledger", str(ledger), *extra]
    assert mint.main(args if "--env" in args else ["--env", "dev", *args]) == 0
    return mint.decode_unverified(capsys.readouterr().out.strip())


def line(ledger, **fields):
    """Append a hand-written minted record (for a past expiry or a chosen fingerprint)."""
    record = {
        "event": "minted",
        "minted_at": tools.iso(int(time.time()) - 200_000),
        "env": "dev",
        "tier": "internal",
        "sub": "hand-made",
        "expires_at": tools.iso(int(time.time()) - 100_000),
        "jti": "0" * 16,
        "fingerprint": "f" * 12,
        **fields,
    }
    tools.append_ledger(ledger, record)


def call(argv, capsys):
    code = revoke.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ── list ────────────────────────────────────────────────────────────────────────


def test_list_shows_outstanding_tokens_and_when_the_last_one_stops(ledger, monkeypatch, capsys):
    mint_one(ledger, monkeypatch, capsys, "--sub", "list-1", "--days", "2")
    code, out, err = call(["--ledger", str(ledger), "list"], capsys)
    assert code == 0 and "outstanding" in out and "list-1" in out
    assert "1 outstanding" in err and "stops working at" in err


def test_list_hides_expired_tokens_unless_asked_and_filters_by_env(ledger, monkeypatch, capsys):
    mint_one(ledger, monkeypatch, capsys, "--sub", "live-dev")
    line(ledger, sub="old-dev", fingerprint="a" * 12)
    line(ledger, sub="old-prod", env="prod", fingerprint="b" * 12)
    _, out, _ = call(["--ledger", str(ledger), "list"], capsys)
    assert "live-dev" in out and "old-dev" not in out
    _, out, _ = call(["--ledger", str(ledger), "list", "--all"], capsys)
    assert "old-dev" in out and "old-prod" in out and "expired" in out
    _, out, _ = call(["--ledger", str(ledger), "list", "--all", "--env", "prod"], capsys)
    assert "old-prod" in out and "old-dev" not in out


def test_list_without_a_ledger_says_none_and_succeeds(tmp_path, capsys):
    code, out, _ = call(["--ledger", str(tmp_path / "missing.jsonl"), "list"], capsys)
    assert code == 0 and out.strip() == "(none)"


def test_list_counts_unreadable_lines(ledger, monkeypatch, capsys):
    mint_one(ledger, monkeypatch, capsys)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n[1, 2]\n")
    code, _, err = call(["--ledger", str(ledger), "list"], capsys)
    assert code == 0 and "2 unreadable ledger line(s) skipped" in err


# ── revoke: never claims more than it does ──────────────────────────────────────


def test_revoking_a_valid_token_is_recorded_but_not_enforced(ledger, monkeypatch, capsys):
    claims = mint_one(ledger, monkeypatch, capsys, "--sub", "rev-1")
    record = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    before = ledger.read_text(encoding="utf-8")
    code, out, err = call(
        [
            "--ledger",
            str(ledger),
            "revoke",
            "--fingerprint",
            record["fingerprint"][:8],
            "--reason",
            "test over",
        ],
        capsys,
    )
    assert code == 4 and "rev-1" in out
    assert "RECORDED, NOT ENFORCED" in err and "still work until" in err and "runbook" in err
    after = ledger.read_text(encoding="utf-8")
    assert after.startswith(before) and len(after.splitlines()) == 2  # appended, nothing rewritten
    revoked = json.loads(after.splitlines()[1])
    assert revoked["event"] == "revoked" and revoked["reason"] == "test over"
    assert revoked["fingerprint"] == record["fingerprint"] and revoked["jti"] == claims["jti"]


def test_the_listing_marks_a_recorded_token_as_revoked_but_still_counts_it_as_valid(
    ledger, monkeypatch, capsys
):
    mint_one(ledger, monkeypatch, capsys, "--sub", "rev-2")
    call(["--ledger", str(ledger), "revoke", "--sub", "rev-2"], capsys)
    _, out, err = call(["--ledger", str(ledger), "list", "--all"], capsys)
    assert "revoked" in out
    assert "1 recorded as revoked but still valid (not enforced)" in err


def test_revoking_twice_adds_no_second_record_and_still_exits_4(ledger, monkeypatch, capsys):
    mint_one(ledger, monkeypatch, capsys, "--sub", "rev-3")
    call(["--ledger", str(ledger), "revoke", "--sub", "rev-3"], capsys)
    code, _, _ = call(["--ledger", str(ledger), "revoke", "--sub", "rev-3"], capsys)
    assert code == 4 and len(ledger.read_text(encoding="utf-8").splitlines()) == 2


def test_an_expired_token_has_nothing_to_revoke_and_exits_0(ledger, capsys):
    line(ledger, sub="gone", fingerprint="c" * 12)
    code, _, err = call(["--ledger", str(ledger), "revoke", "--sub", "gone"], capsys)
    assert code == 0 and "already expired" in err and len(ledger.read_text().splitlines()) == 1


def test_revoke_by_label_takes_every_token_with_it(ledger, monkeypatch, capsys):
    mint_one(ledger, monkeypatch, capsys, "--sub", "shared-label")
    mint_one(ledger, monkeypatch, capsys, "--sub", "shared-label")
    call(["--ledger", str(ledger), "revoke", "--sub", "shared-label"], capsys)
    revoked = [json.loads(x) for x in ledger.read_text().splitlines() if '"revoked"' in x]
    assert len(revoked) == 2


def test_revoke_by_jti_prefix(ledger, monkeypatch, capsys):
    claims = mint_one(ledger, monkeypatch, capsys)
    code, _, _ = call(["--ledger", str(ledger), "revoke", "--jti", claims["jti"][:8]], capsys)
    assert code == 4


def test_all_outstanding_needs_an_env_and_touches_only_that_env(ledger, monkeypatch, capsys):
    mint_one(ledger, monkeypatch, capsys, "--sub", "in-dev")
    mint_one(ledger, monkeypatch, capsys, "--env", "prod", "--yes-prod", "--sub", "in-prod")
    code, _, err = call(["--ledger", str(ledger), "revoke", "--all-outstanding"], capsys)
    assert code == 2 and "needs --env" in err
    call(["--ledger", str(ledger), "revoke", "--all-outstanding", "--env", "dev"], capsys)
    revoked = [json.loads(x) for x in ledger.read_text().splitlines() if '"revoked"' in x]
    assert [r["sub"] for r in revoked] == ["in-dev"]


@pytest.mark.parametrize(
    "argv, message",
    [
        (["revoke", "--fingerprint", "abc"], "at least 6 characters"),
        (["revoke", "--fingerprint", "aaaaaa"], "several tokens"),
        (["revoke", "--fingerprint", "zzzzzz"], "no matching token"),
        (["revoke", "--sub", "nobody"], "no matching token"),
    ],
    ids=["short-prefix", "ambiguous", "no-match", "no-such-sub"],
)
def test_revoke_refuses_what_it_cannot_pin_down(argv, message, ledger, capsys):
    line(
        ledger, sub="one", fingerprint="aaaaaa111111", expires_at=tools.iso(int(time.time()) + 999)
    )
    line(
        ledger, sub="two", fingerprint="aaaaaa222222", expires_at=tools.iso(int(time.time()) + 999)
    )
    code, out, err = call(["--ledger", str(ledger), *argv], capsys)
    assert code == 2 and out == "" and message in err
    assert len(ledger.read_text().splitlines()) == 2  # nothing written


# ── the runbook ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("env", ["dev", "prod"])
def test_the_runbook_names_the_real_secret_cluster_and_service(env, capsys):
    code, out, _ = call(["runbook", "--env", env], capsys)
    assert code == 0
    assert f"pyvar/{env}/jwt-secret" in out
    assert f"--cluster pyvar-{env} --service pyvar-{env}-api" in out
    assert "force-new-deployment" in out and "wait services-stable" in out
    assert "Not rehearsed" in out


def test_the_runbook_generates_the_new_secret_without_a_trailing_newline(capsys):
    _, out, _ = call(["runbook", "--env", "dev"], capsys)
    assert 'end=""' in out and "file:///dev/stdin" in out  # a newline would break signing
    assert "--secret-string file://" in out and SECRET not in out


def test_the_runbook_needs_an_environment():
    with pytest.raises(SystemExit) as exc:
        revoke.main(["runbook"])
    assert exc.value.code == 2


# ── as a command ────────────────────────────────────────────────────────────────


def test_it_runs_as_a_command(tmp_path):
    done = subprocess.run(  # noqa: S603 - fixed arguments, a temporary ledger
        [
            sys.executable,
            str(SCRIPTS / "revoke_internal_token.py"),
            "--ledger",
            str(tmp_path / "none.jsonl"),
            "list",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0 and done.stdout.strip() == "(none)"

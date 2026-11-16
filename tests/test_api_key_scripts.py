"""scripts/mint_api_key.py and scripts/revoke_api_key.py: creating and revoking API keys from the shell.

Reasoning:
- The commands are clients of three real routes (POST, GET and DELETE under /api/v1/auth/api-keys). The
  behaviour tested here is the client's: which session token it presents, what it prints and where,
  what it records, and that it only says "revoked" after the API confirms it.
- The API is a small local fake that follows the real routes' contract (status codes and JSON fields as
  in api/routes/auth.py and schemas/auth.py), including the failure answers. A separate contract test
  reads the REAL application's OpenAPI document and checks the routes and fields the scripts rely on
  are still there, so the fake cannot drift from the API unnoticed.
- No key, secret or token may appear anywhere but where it is meant to (a key on stdout once; nothing
  in the ledger or on stderr): the tests look for them.
"""

from __future__ import annotations

import importlib.util
import io
import json
import secrets
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from jose import JWTError, jwt

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mint_key = load("mint_api_key")
revoke_key = load("revoke_api_key")
tools = sys.modules["token_tools"]

SECRET = "dummy-secret-for-tests-only-0123456789abcdefghijklmnopqrstuvwxyz"
ACCOUNT = "11111111-2222-3333-4444-555555555555"
PATH = "/api/v1/auth/api-keys"


class FakeApi:
    """State of the fake API, shared with its request handler."""

    def __init__(self) -> None:
        self.accounts = {ACCOUNT}  # verified accounts
        self.keys: dict[str, list[dict]] = {}
        self.secret = SECRET
        self.revoke_does_nothing = False
        self.seen: list[dict] = []

    def iso_now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_handler(api: FakeApi):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the test output quiet
            pass

        def reply(self, status: int, body=None):
            raw = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def account(self):
            """Mimic require_session: a valid HS256 session token, then a verified account."""
            header = self.headers.get("Authorization", "")
            token = header[7:] if header.startswith("Bearer ") else ""
            try:
                claims = jwt.decode(token, api.secret, algorithms=["HS256"])
            except JWTError:
                self.reply(401, {"detail": "Invalid or expired token"})
                return None
            api.seen.append(claims)
            if claims.get("sub") not in api.accounts:
                self.reply(403, {"detail": "No verified account for this session."})
                return None
            return claims["sub"]

        def do_POST(self):
            account = self.account()
            if account is None:
                return
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            rows = api.keys.setdefault(account, [])
            if sum(1 for r in rows if not r["revoked_at"]) >= 5:
                return self.reply(409, {"detail": "You already have 5 active API keys."})
            secret = "pyvar_" + secrets.token_urlsafe(32)
            row = {
                "id": str(uuid.uuid4()),
                "name": body.get("name", "default"),
                "prefix": secret[:14],
                "created_at": api.iso_now(),
                "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3e7)),
                "last_used_at": None,
                "revoked_at": None,
                "_secret": secret,
            }
            rows.insert(0, row)
            self.reply(201, {**{k: v for k, v in row.items() if k != "_secret"}, "key": secret})

        def do_GET(self):
            account = self.account()
            if account is None:
                return
            rows = [
                {k: v for k, v in r.items() if k != "_secret"} for r in api.keys.get(account, [])
            ]
            self.reply(200, {"keys": rows})

        def do_DELETE(self):
            account = self.account()
            if account is None:
                return
            key_id = self.path.rsplit("/", 1)[-1]
            for row in api.keys.get(account, []):
                if row["id"] == key_id:
                    if not api.revoke_does_nothing and not row["revoked_at"]:
                        row["revoked_at"] = api.iso_now()
                    return self.reply(204)
            self.reply(404, {"detail": "No such API key."})

    return Handler


@pytest.fixture
def api():
    state = FakeApi()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.base = f"http://127.0.0.1:{server.server_address[1]}"
    yield state
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv(tools.KEY_LEDGER_ENV, raising=False)


def run(module, argv, monkeypatch, capsys, api, stdin=SECRET):
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    code = module.main([*argv, "--base-url", api.base]) if api else module.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def mint(api, monkeypatch, capsys, *extra, ledger=None):
    argv = ["--env", "dev", "--secret-stdin", "--account-id", ACCOUNT, *extra]
    if ledger:
        argv += ["--ledger", str(ledger)]
    return run(mint_key, argv, monkeypatch, capsys, api)


def revoke_argv(sub, *extra, ledger=None):
    argv = [sub, "--env", "dev", "--secret-stdin", "--account-id", ACCOUNT, *extra]
    return argv + (["--ledger", str(ledger)] if ledger else [])


# ── mint_api_key ────────────────────────────────────────────────────────────────


def test_a_key_is_created_and_printed_once_on_stdout_alone(api, monkeypatch, capsys, tmp_path):
    ledger = tmp_path / "keys.jsonl"
    code, out, err = mint(api, monkeypatch, capsys, "--name", "ci-dev", ledger=ledger)
    key = out.strip()
    assert code == 0 and out == key + "\n" and key.startswith("pyvar_")
    assert "prefix=" + key[:14] in err and "name=ci-dev" in err and "Shown once" in err
    assert key not in err
    record = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert record["event"] == "minted" and record["prefix"] == key[:14]
    assert record["account_id"] == ACCOUNT and record["name"] == "ci-dev"
    assert key not in ledger.read_text(encoding="utf-8") and SECRET not in ledger.read_text()


def test_the_session_token_it_presents_is_short_lived_and_names_the_account(
    api, monkeypatch, capsys
):
    mint(api, monkeypatch, capsys, "--no-ledger")
    claims = api.seen[0]
    assert claims["sub"] == ACCOUNT and claims["exp"] - claims["iat"] == 600


def test_the_key_it_makes_is_listed_by_the_other_command(api, monkeypatch, capsys):
    _, out, _ = mint(api, monkeypatch, capsys, "--name", "listed", "--no-ledger")
    code, listing, _ = run(revoke_key, revoke_argv("list"), monkeypatch, capsys, api)
    assert code == 0 and out.strip()[:14] in listing and "listed" in listing and "active" in listing


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--secret-stdin", "--account-id", ACCOUNT], "--env is required"),
        (["--env", "prod", "--secret-stdin", "--account-id", ACCOUNT], "--yes-prod"),
        (["--env", "dev", "--secret-stdin"], "exactly one of"),
        (
            ["--env", "dev", "--secret-stdin", "--account-id", ACCOUNT, "--session-token-env", "X"],
            "exactly one of",
        ),
        (["--env", "dev", "--secret-stdin", "--account-id", "a b"], "--account-id must be"),
        (
            ["--env", "dev", "--secret-stdin", "--account-id", ACCOUNT, "--name", "x" * 65],
            "--name must be",
        ),
    ],
    ids=["no-env", "prod-no-flag", "no-auth", "two-auths", "bad-account-id", "long-name"],
)
def test_guards_refuse_before_any_call(argv, message, api, monkeypatch, capsys):
    code, out, err = run(mint_key, argv, monkeypatch, capsys, api)
    assert code == 2 and out == "" and message in err and api.seen == []


def test_prod_with_the_flag_goes_to_the_given_loopback_address(api, monkeypatch, capsys):
    argv = ["--env", "prod", "--yes-prod", "--secret-stdin", "--account-id", ACCOUNT, "--no-ledger"]
    code, out, _ = run(mint_key, argv, monkeypatch, capsys, api)
    assert code == 0 and out.startswith("pyvar_")


@pytest.mark.parametrize(
    "stdin", ["short", tools.PUBLIC_DEFAULT_SECRET, ""], ids=["short", "default", "empty"]
)
def test_an_unusable_secret_is_refused_with_exit_3(stdin, api, monkeypatch, capsys):
    code, out, _ = run(
        mint_key,
        ["--env", "dev", "--secret-stdin", "--account-id", ACCOUNT],
        monkeypatch,
        capsys,
        api,
        stdin=stdin,
    )
    assert code == 3 and out == "" and api.seen == []


@pytest.mark.parametrize(
    "setup, status, words",
    [
        ("other-secret", 401, "expired, or signed with another environment"),
        ("no-account", 403, "no verified account"),
        ("full", 409, "key limit"),
    ],
)
def test_api_refusals_are_explained_with_exit_5(setup, status, words, api, monkeypatch, capsys):
    if setup == "other-secret":
        api.secret = SECRET + "different"
    elif setup == "no-account":
        api.accounts.clear()
    else:
        for _ in range(5):
            assert mint(api, monkeypatch, capsys, "--no-ledger")[0] == 0
    code, out, err = mint(api, monkeypatch, capsys, "--no-ledger")
    assert code == 5 and out == "" and f"HTTP {status}" in err and words in err


def test_an_unreachable_api_gives_exit_5_without_the_token(monkeypatch, capsys):
    argv = [
        "--env",
        "dev",
        "--secret-stdin",
        "--account-id",
        ACCOUNT,
        "--base-url",
        "http://127.0.0.1:9",
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO(SECRET))
    code = mint_key.main(argv)
    err = capsys.readouterr().err
    assert code == 5 and "could not reach 127.0.0.1" in err
    assert "eyJ" not in err and SECRET not in err  # no token text in the message


def test_a_base_url_that_is_not_loopback_is_refused(monkeypatch, capsys):
    argv = [
        "--env",
        "dev",
        "--secret-stdin",
        "--account-id",
        ACCOUNT,
        "--base-url",
        "http://example.com",
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO(SECRET))
    assert mint_key.main(argv) == 2
    assert "only accepted for http://127.0.0.1" in capsys.readouterr().err


def test_a_token_is_never_sent_over_plain_http_to_a_real_host():
    with pytest.raises(tools.ToolError) as exc:
        tools.api_request("GET", "http://example.com/x", "token")
    assert exc.value.code == 5 and "https" in str(exc.value)


def test_a_session_token_from_the_environment_is_used_as_is(api, monkeypatch, capsys):
    token = tools.sign_token(SECRET, sub=ACCOUNT, tier="free", ttl_seconds=3600)
    monkeypatch.setenv("MY_SESSION", token)
    argv = ["--env", "dev", "--session-token-env", "MY_SESSION", "--no-ledger"]
    code, out, _ = run(mint_key, argv, monkeypatch, capsys, api)
    assert (
        code == 0 and out.startswith("pyvar_") and api.seen[0]["exp"] - api.seen[0]["iat"] == 3600
    )


def test_an_expired_or_missing_session_token_is_refused(api, monkeypatch, capsys):
    old = tools.sign_token(SECRET, sub=ACCOUNT, tier="free", ttl_seconds=60, now=1_000)
    monkeypatch.setenv("OLD_SESSION", old)
    for variable, words in (("OLD_SESSION", "has expired"), ("NOT_SET_AT_ALL", "empty or not set")):
        argv = ["--env", "dev", "--session-token-env", variable]
        code, _, err = run(mint_key, argv, monkeypatch, capsys, api)
        assert code == 2 and words in err
    assert api.seen == []


# ── revoke_api_key ──────────────────────────────────────────────────────────────


def make_keys(api, monkeypatch, capsys, count, base="k"):
    return [
        mint(api, monkeypatch, capsys, "--name", f"{base}{i}", "--no-ledger")[1].strip()
        for i in range(count)
    ]


def test_list_shows_active_keys_only_unless_all(api, monkeypatch, capsys):
    first, second = make_keys(api, monkeypatch, capsys, 2)
    run(revoke_key, revoke_argv("revoke", "--prefix", first[:14]), monkeypatch, capsys, api)
    _, out, _ = run(revoke_key, revoke_argv("list"), monkeypatch, capsys, api)
    assert second[:14] in out and first[:14] not in out
    _, out, _ = run(revoke_key, revoke_argv("list", "--all"), monkeypatch, capsys, api)
    assert first[:14] in out and "revoked" in out


def test_revoke_by_prefix_is_confirmed_recorded_and_the_key_is_gone(
    api, monkeypatch, capsys, tmp_path
):
    ledger = tmp_path / "keys.jsonl"
    (key,) = make_keys(api, monkeypatch, capsys, 1)
    code, out, _ = run(
        revoke_key,
        revoke_argv("revoke", "--prefix", key[:14], "--reason", "done", ledger=ledger),
        monkeypatch,
        capsys,
        api,
    )
    assert code == 0 and "confirmed by the API" in out
    row = api.keys[ACCOUNT][0]
    assert row["revoked_at"]
    record = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert (
        record["event"] == "revoked" and record["prefix"] == key[:14] and record["reason"] == "done"
    )
    assert key not in ledger.read_text(encoding="utf-8")


def test_revoke_by_id(api, monkeypatch, capsys):
    make_keys(api, monkeypatch, capsys, 1)
    key_id = api.keys[ACCOUNT][0]["id"]
    code, _, _ = run(revoke_key, revoke_argv("revoke", "--id", key_id), monkeypatch, capsys, api)
    assert code == 0 and api.keys[ACCOUNT][0]["revoked_at"]


def test_revoking_a_revoked_key_is_a_quiet_success(api, monkeypatch, capsys):
    (key,) = make_keys(api, monkeypatch, capsys, 1)
    argv = revoke_argv("revoke", "--prefix", key[:14])
    run(revoke_key, argv, monkeypatch, capsys, api)
    code, _, err = run(revoke_key, argv, monkeypatch, capsys, api)
    assert code == 0 and "already revoked" in err and "Nothing active" in err


def test_all_active_needs_the_confirmation_flag_then_revokes_every_active_key(
    api, monkeypatch, capsys
):
    make_keys(api, monkeypatch, capsys, 3)
    code, _, err = run(revoke_key, revoke_argv("revoke", "--all-active"), monkeypatch, capsys, api)
    assert code == 2 and "--yes-all" in err
    assert not any(r["revoked_at"] for r in api.keys[ACCOUNT])
    code, _, _ = run(
        revoke_key, revoke_argv("revoke", "--all-active", "--yes-all"), monkeypatch, capsys, api
    )
    assert code == 0 and all(r["revoked_at"] for r in api.keys[ACCOUNT])


@pytest.mark.parametrize(
    "extra, message",
    [
        (["--prefix", "pyvar_a"], "at least 8 characters"),
        (["--prefix", "pyvar_zzzzzzzz"], "no such key"),
        (["--id", "not-a-uuid"], "must be a uuid"),
        (["--id", str(uuid.uuid4())], "no such key"),
    ],
    ids=["short-prefix", "unknown-prefix", "bad-id", "unknown-id"],
)
def test_revoke_refuses_what_it_cannot_pin_down(extra, message, api, monkeypatch, capsys):
    make_keys(api, monkeypatch, capsys, 1)
    code, _, err = run(revoke_key, revoke_argv("revoke", *extra), monkeypatch, capsys, api)
    assert code == 2 and message in err and not api.keys[ACCOUNT][0]["revoked_at"]


def test_an_ambiguous_prefix_revokes_nothing(api, monkeypatch, capsys):
    make_keys(api, monkeypatch, capsys, 2)
    for row in api.keys[ACCOUNT]:  # force a shared prefix
        row["prefix"] = "pyvar_samepre"
    code, _, err = run(
        revoke_key, revoke_argv("revoke", "--prefix", "pyvar_samepre"), monkeypatch, capsys, api
    )
    assert (
        code == 2 and "several keys" in err and not any(r["revoked_at"] for r in api.keys[ACCOUNT])
    )


def test_it_does_not_say_revoked_unless_the_api_confirms(api, monkeypatch, capsys, tmp_path):
    ledger = tmp_path / "keys.jsonl"
    (key,) = make_keys(api, monkeypatch, capsys, 1)
    api.revoke_does_nothing = True  # DELETE answers 204 but nothing changes
    code, out, err = run(
        revoke_key,
        revoke_argv("revoke", "--prefix", key[:14], ledger=ledger),
        monkeypatch,
        capsys,
        api,
    )
    assert code == 5 and "could not confirm" in err and "revoked" not in out
    assert not ledger.exists()  # nothing recorded as done


def test_revoke_needs_the_prod_flag_and_a_known_account(api, monkeypatch, capsys):
    code, _, err = run(
        revoke_key,
        ["list", "--env", "prod", "--account-id", ACCOUNT, "--secret-stdin"],
        monkeypatch,
        capsys,
        api,
    )
    assert code == 2 and "--yes-prod" in err
    api.accounts.clear()
    code, _, err = run(revoke_key, revoke_argv("list"), monkeypatch, capsys, api)
    assert code == 5 and "HTTP 403" in err


# ── the fake follows the real API ───────────────────────────────────────────────


def test_the_routes_and_fields_the_scripts_rely_on_exist_in_the_real_api():
    from main import create_app

    spec = create_app().openapi()
    paths = spec["paths"]
    assert "post" in paths[PATH] and "get" in paths[PATH]
    assert "delete" in paths[PATH + "/{key_id}"]
    assert "204" in paths[PATH + "/{key_id}"]["delete"]["responses"]
    assert "201" in paths[PATH]["post"]["responses"]
    schemas = spec["components"]["schemas"]
    created = schemas["ApiKeyCreated"]["properties"]
    for field in (
        "id",
        "name",
        "prefix",
        "created_at",
        "expires_at",
        "last_used_at",
        "revoked_at",
        "key",
    ):
        assert field in created, field
    assert "keys" in schemas["ApiKeyList"]["properties"]
    assert "name" in schemas["CreateApiKeyRequest"]["properties"]

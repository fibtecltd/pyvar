"""scripts/mint_internal_token.py: the on-demand token minting command.

Reasoning:
- The point of the script is that the tokens it signs are the ones the API accepts, so the main
  tests feed its output to the API's own decoder (api.middleware.auth.decode_token_payload) with
  a dummy secret, and check tier, caps and expiry from what the API reports.
- The guards (no default environment, a flag for prod, a ceiling on lifetime, a refusal to sign
  with a short or public-default secret) and the two things the script promises never to leak
  (the secret, the token itself in the ledger) are each tested on their own.
- The AWS path is exercised with a fake `aws` program on PATH, so the real CLI, the real account and
  the real secret are never touched; the fake records its arguments so the test can show the secret
  is not among them.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
from jose import JWTError, jwt

from api.middleware import auth

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "mint_internal_token.py"
_spec = importlib.util.spec_from_file_location("mint_internal_token", SCRIPT)
assert _spec is not None and _spec.loader is not None
mint = importlib.util.module_from_spec(_spec)
sys.modules["mint_internal_token"] = mint
_spec.loader.exec_module(mint)

SECRET = "dummy-secret-for-tests-only-0123456789abcdefghijklmnopqrstuvwxyz"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep every run away from the real home folder and ledger."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv(mint.LEDGER_ENV, raising=False)
    monkeypatch.setattr(auth.cfg, "jwt_secret", SECRET)


def run(argv, monkeypatch, capsys, stdin=SECRET):
    """Run main() with the secret on stdin; return (exit code, stdout, stderr)."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    code = mint.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ── the token is what the API accepts ───────────────────────────────────────────


def test_an_internal_token_is_accepted_by_the_api_with_internal_caps():
    token = mint.sign_token(SECRET, sub="t-1", tier="internal", ttl_seconds=3600)
    payload = auth.decode_token_payload(token)
    assert (payload.user_id, payload.tier, payload.max_simulations) == ("t-1", "internal", 500_000)


def test_a_free_token_gets_the_free_cap_and_a_wrong_secret_is_refused():
    token = mint.sign_token(SECRET, sub="t-2", tier="free", ttl_seconds=3600)
    assert auth.decode_token_payload(token).max_simulations == 10_000
    with pytest.raises(JWTError):
        jwt.decode(token, SECRET + "x", algorithms=["HS256"])


def test_the_expiry_is_exactly_the_requested_lifetime():
    token = mint.sign_token(SECRET, sub="t-3", tier="internal", ttl_seconds=86_400, now=1_000)
    claims = jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False})
    assert (claims["iat"], claims["exp"]) == (1_000, 87_400)


def test_an_expired_token_is_refused_by_the_api():
    long_ago = int(time.time()) - 10 * 86_400
    token = mint.sign_token(SECRET, sub="t-4", tier="internal", ttl_seconds=86_400, now=long_ago)
    with pytest.raises(JWTError):
        auth.decode_token_payload(token)


# ── the command ─────────────────────────────────────────────────────────────────


def test_stdout_is_the_token_alone_and_stderr_holds_the_summary(monkeypatch, capsys):
    code, out, err = run(
        ["--env", "dev", "--secret-stdin", "--sub", "load-test-1"], monkeypatch, capsys
    )
    assert code == 0
    token = out.strip()
    assert out == token + "\n" and token.count(".") == 2
    payload = auth.decode_token_payload(token)
    assert (payload.user_id, payload.tier) == ("load-test-1", "internal")
    assert "expires=" in err and "env=dev" in err and "cannot be revoked" in err
    assert token not in err and SECRET not in err and SECRET not in out


def test_the_default_lifetime_is_one_day_and_the_default_label_names_env_and_tier(
    monkeypatch, capsys
):
    _, out, _ = run(["--env", "dev", "--secret-stdin"], monkeypatch, capsys)
    claims = mint.decode_unverified(out.strip())
    assert claims["exp"] - claims["iat"] == 86_400
    assert claims["sub"].startswith("internal-dev-")


def test_a_fractional_lifetime_works(monkeypatch, capsys):
    _, out, _ = run(["--env", "dev", "--secret-stdin", "--days", "0.5"], monkeypatch, capsys)
    claims = mint.decode_unverified(out.strip())
    assert claims["exp"] - claims["iat"] == 43_200


# ── the guards ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "argv",
    [
        ["--secret-stdin"],  # no environment
        ["--env", "dev", "--secret-stdin", "--days", "0"],
        ["--env", "dev", "--secret-stdin", "--days", "-1"],
        ["--env", "dev", "--secret-stdin", "--days", "91"],
        ["--env", "prod", "--secret-stdin"],  # prod without the flag
        ["--env", "dev", "--secret-stdin", "--sub", "Bad Label!"],
        ["--env", "dev", "--secret-stdin", "--sub", "ab"],
    ],
    ids=[
        "no-env",
        "zero-days",
        "negative-days",
        "over-ceiling",
        "prod-no-flag",
        "bad-sub",
        "short-sub",
    ],
)
def test_guards_refuse_with_exit_2_and_print_no_token(argv, monkeypatch, capsys):
    code, out, err = run(argv, monkeypatch, capsys)
    assert code == 2 and out == "" and err.startswith("refused:")


def test_prod_works_with_the_flag(monkeypatch, capsys):
    code, out, _ = run(["--env", "prod", "--secret-stdin", "--yes-prod"], monkeypatch, capsys)
    assert code == 0 and out.strip().count(".") == 2


@pytest.mark.parametrize(
    "secret",
    ["", "short", mint.PUBLIC_DEFAULT_SECRET, "x" * 31],
    ids=["empty", "short", "default", "31"],
)
def test_an_unusable_secret_is_refused_with_exit_3(secret, monkeypatch, capsys):
    code, out, err = run(["--env", "dev", "--secret-stdin"], monkeypatch, capsys, stdin=secret)
    assert code == 3 and out == "" and "refusing" in err


def test_a_32_character_secret_is_enough(monkeypatch, capsys):
    code, out, _ = run(["--env", "dev", "--secret-stdin"], monkeypatch, capsys, stdin="x" * 32)
    assert code == 0 and out.strip()


# ── the ledger ──────────────────────────────────────────────────────────────────


def test_the_ledger_records_the_token_without_holding_it(tmp_path, monkeypatch, capsys):
    ledger = tmp_path / "ledger.jsonl"
    _, out, _ = run(
        ["--env", "dev", "--secret-stdin", "--ledger", str(ledger), "--sub", "ledger-1"],
        monkeypatch,
        capsys,
    )
    token = out.strip()
    text = ledger.read_text(encoding="utf-8")
    record = json.loads(text.splitlines()[0])
    assert record["env"] == "dev" and record["sub"] == "ledger-1" and record["tier"] == "internal"
    assert record["fingerprint"] == mint.fingerprint(token) and len(record["fingerprint"]) == 12
    assert token not in text and SECRET not in text
    assert stat.S_IMODE(os.stat(ledger).st_mode) == 0o600


def test_the_ledger_appends_and_follows_the_environment_variable(tmp_path, monkeypatch, capsys):
    ledger = tmp_path / "from-env.jsonl"
    monkeypatch.setenv(mint.LEDGER_ENV, str(ledger))
    run(["--env", "dev", "--secret-stdin"], monkeypatch, capsys)
    run(["--env", "dev", "--secret-stdin"], monkeypatch, capsys)
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 2


def test_no_ledger_writes_nothing(tmp_path, monkeypatch, capsys):
    ledger = tmp_path / "none.jsonl"
    run(
        ["--env", "dev", "--secret-stdin", "--ledger", str(ledger), "--no-ledger"],
        monkeypatch,
        capsys,
    )
    assert not ledger.exists()


def test_the_default_ledger_is_under_the_home_folder(tmp_path, monkeypatch, capsys):
    run(["--env", "dev", "--secret-stdin"], monkeypatch, capsys)
    assert (tmp_path / "home" / ".pyvar" / "minted-tokens.jsonl").exists()


# ── --decode ────────────────────────────────────────────────────────────────────


def test_decode_prints_the_claims_and_says_the_signature_is_not_checked(monkeypatch, capsys):
    token = mint.sign_token(SECRET, sub="d-1", tier="pro", ttl_seconds=7200)
    code, out, err = run(["--decode", token], monkeypatch, capsys)
    assert code == 0 and json.loads(out)["tier"] == "pro"
    assert "signature NOT checked" in err and "valid for" in err


def test_decode_flags_an_expired_token(monkeypatch, capsys):
    token = mint.sign_token(SECRET, sub="d-2", tier="pro", ttl_seconds=60, now=1_000)
    _, _, err = run(["--decode", token], monkeypatch, capsys)
    assert "EXPIRED" in err


@pytest.mark.parametrize(
    "bad", ["", "abc", "a.b", "a.b.c", "a.e30.c"], ids=["empty", "one", "two", "junk", "not-object"]
)
def test_decode_refuses_what_is_not_a_jwt(bad, monkeypatch, capsys):
    if bad == "a.e30.c":  # e30 is "{}": a valid empty object, so this one is accepted
        code, out, _ = run(["--decode", bad], monkeypatch, capsys)
        assert code == 0 and json.loads(out) == {}
        return
    code, out, err = run(["--decode", bad], monkeypatch, capsys)
    assert code == 2 and out == "" and "not a JWT" in err


# ── the AWS path, with a fake `aws` ─────────────────────────────────────────────


def fake_aws(tmp_path, monkeypatch, *, secret=SECRET, exit_code=0, stderr=""):
    """Put a fake `aws` first on PATH; it records its arguments and prints `secret`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "aws-args.txt"
    program = bin_dir / "aws"
    program.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" > "{record}"\n'
        f'printf "%s" "{stderr}" >&2\n'
        f'printf "%s\\n" "{secret}"\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    program.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    return record


def test_the_secret_is_read_from_the_right_name_and_never_passed_as_an_argument(
    tmp_path, monkeypatch, capsys
):
    record = fake_aws(tmp_path, monkeypatch)
    code, out, _ = run(["--env", "dev"], monkeypatch, capsys, stdin="")
    arguments = record.read_text(encoding="utf-8").split()
    assert code == 0 and auth.decode_token_payload(out.strip()).tier == "internal"
    assert "pyvar/dev/jwt-secret" in arguments and "eu-west-1" in arguments
    assert SECRET not in arguments and "SecretString" in arguments


def test_prod_reads_the_prod_secret(tmp_path, monkeypatch, capsys):
    record = fake_aws(tmp_path, monkeypatch)
    run(["--env", "prod", "--yes-prod", "--region", "eu-west-2"], monkeypatch, capsys, stdin="")
    arguments = record.read_text(encoding="utf-8").split()
    assert "pyvar/prod/jwt-secret" in arguments and "eu-west-2" in arguments


def test_a_failed_aws_call_gives_exit_3_and_no_token(tmp_path, monkeypatch, capsys):
    fake_aws(tmp_path, monkeypatch, exit_code=254, stderr="AccessDeniedException: not allowed")
    code, out, err = run(["--env", "dev"], monkeypatch, capsys, stdin="")
    assert code == 3 and out == "" and "AccessDeniedException" in err


def test_a_missing_aws_cli_gives_exit_3(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    code, out, err = run(["--env", "dev"], monkeypatch, capsys, stdin="")
    assert code == 3 and out == "" and "not installed" in err


# ── as a real command ───────────────────────────────────────────────────────────


def test_the_script_runs_as_a_command_and_prints_only_the_token_on_stdout(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path)}
    done = subprocess.run(  # noqa: S603 - fixed arguments, a dummy secret
        [sys.executable, str(SCRIPT), "--env", "dev", "--secret-stdin", "--no-ledger"],
        input=SECRET,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )
    assert done.returncode == 0
    assert done.stdout.count("\n") == 1 and done.stdout.strip().count(".") == 2
    assert SECRET not in done.stdout + done.stderr

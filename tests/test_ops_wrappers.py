"""tests/test_ops_wrappers.py: the shell wrappers in scripts/ops/ (see scripts/ops/README.md).

Reasoning:
- The wrappers sit in front of scripts that mint credentials, erase accounts and delete audit rows, so what they
  pass on matters as much as what they refuse. These tests run the REAL wrappers under bash with a stub `aws` and
  a stub Python that only record how they were called: no AWS call, no API call, no secret, no network.
- What is pinned: `--yes` and `--yes-prod` reach the Python script only after the typed confirmation; `--yes-all`
  is never added; an e-mail address is masked in the wrapper's own output; nothing the wrapper says goes to
  stdout (the key or token alone is what `KEY=$(...)` must capture); the script's exit code comes back unchanged;
  commands that need no AWS (a decode, the local ledger, a session token already in hand) do not call it.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

OPS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "ops"
SCRIPTS_DIR = OPS_DIR.parent
WRAPPERS = sorted(path for path in OPS_DIR.glob("*.sh") if path.name != "_common.sh")
EMAIL = "ada@uni.example"
STUB_STDOUT = "STDOUT-FROM-THE-SCRIPT\n"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")

STUB_AWS = """#!/usr/bin/env bash
echo "$*" >> "$STUB_AWS_LOG"
if [ -n "${STUB_AWS_FAIL:-}" ]; then
  echo "Unable to locate credentials" >&2
  exit 255
fi
echo 123456789012
"""

STUB_PYTHON = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$STUB_PY_ARGS"
echo "STDOUT-FROM-THE-SCRIPT"
exit "${STUB_PY_EXIT:-0}"
"""


@dataclass
class Outcome:
    code: int
    stdout: str
    stderr: str
    python_args: list[str] | None  # None: the Python script was never called
    aws_calls: list[str]


@pytest.fixture
def run(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("aws", STUB_AWS), ("stub-python", STUB_PYTHON)):
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    counter = {"n": 0}

    def _run(
        wrapper: str,
        *args: str,
        confirm: str | None = None,
        aws_fails: bool = False,
        exit_code: int = 0,
        python: str | None = None,
    ) -> Outcome:
        counter["n"] += 1
        py_args = tmp_path / f"py-args-{counter['n']}"
        aws_log = tmp_path / f"aws-log-{counter['n']}"
        confirm_file = tmp_path / f"confirm-{counter['n']}"
        if confirm is not None:
            confirm_file.write_text(confirm + "\n")
        env = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "PYVAR_OPS_PYTHON": python or str(bin_dir / "stub-python"),
            "PYVAR_OPS_CONFIRM_FILE": str(confirm_file),  # absent unless `confirm` was given
            "STUB_PY_ARGS": str(py_args),
            "STUB_AWS_LOG": str(aws_log),
            "STUB_PY_EXIT": str(exit_code),
        }
        if aws_fails:
            env["STUB_AWS_FAIL"] = "1"
        done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            ["bash", str(OPS_DIR / wrapper), *args],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return Outcome(
            code=done.returncode,
            stdout=done.stdout,
            stderr=done.stderr,
            python_args=py_args.read_text().splitlines() if py_args.exists() else None,
            aws_calls=aws_log.read_text().splitlines() if aws_log.exists() else [],
        )

    return _run


def _flags(outcome: Outcome) -> list[str]:
    """The arguments the Python script got, without the script's own path."""
    assert outcome.python_args is not None, "the Python script was not called"
    return outcome.python_args[1:]


# ── the folder itself ───────────────────────────────────────────────────────────


def test_there_is_a_wrapper_for_each_operator_script() -> None:
    assert [path.name for path in WRAPPERS] == [
        "account-erase.sh",
        "account-export.sh",
        "assistant-allow.sh",
        "audit-cleanup.sh",
        "billing-checkout-allow.sh",
        "education-grant.sh",
        "mint-api-key.sh",
        "mint-internal-token.sh",
        "revoke-api-key.sh",
        "revoke-internal-token.sh",
    ]


@pytest.mark.parametrize("path", sorted(OPS_DIR.glob("*.sh")), ids=lambda p: p.name)
def test_every_file_is_executable_and_parses(path: Path) -> None:
    assert os.access(path, os.X_OK), "the pre-commit hook needs the executable bit"
    assert subprocess.run(["bash", "-n", str(path)], check=False).returncode == 0


@pytest.mark.parametrize("path", WRAPPERS, ids=lambda p: p.name)
def test_every_wrapper_names_a_script_that_exists(path: Path) -> None:
    line = next(x for x in path.read_text().splitlines() if x.startswith("OPS_SCRIPT="))
    assert (SCRIPTS_DIR / line.split("=", 1)[1].strip('"')).is_file()


# ── what a wrapper hands over must be what the script's own parser accepts ──────
# The stub Python in the other tests accepts any arguments, so on its own it cannot tell whether a flag the wrapper
# adds (--yes, --yes-prod) is put where the real script takes it. Each case here runs a wrapper for prod, takes the
# arguments it produced and gives them to the script's real build_parser().

PARSER_CASES: list[tuple[str, str, list[str], dict[str, Any]]] = [
    # wrapper, script (module), what the person types, what the script's parser must then report
    (
        "education-grant.sh",
        "education_grant",
        ["grant", "--env", "prod", "--email", EMAIL, "--months", "6", "--cohort", "c", "--apply"],
        {"yes_prod": True},
    ),
    (
        "education-grant.sh",
        "education_grant",
        ["tidy", "--env", "prod", "--apply"],
        {"yes_prod": True, "yes": True},
    ),
    (
        "education-grant.sh",
        "education_grant",
        ["suspend-all", "--env", "prod", "--yes-all", "--apply"],
        {"yes_prod": True, "yes_all": True},
    ),
    ("education-grant.sh", "education_grant", ["list", "--env", "dev"], {"yes_prod": False}),
    (
        "account-erase.sh",
        "account_erase",
        ["--env", "prod", "--email", EMAIL, "--apply"],
        {"yes": True, "yes_prod": True},
    ),
    (
        "account-export.sh",
        "account_export",
        ["--env", "prod", "--email", EMAIL, "--out", "x.json"],
        {"yes_prod": True},
    ),
    (
        "audit-cleanup.sh",
        "audit_cleanup",
        ["--env", "prod", "--apply"],
        {"yes": True, "yes_prod": True},
    ),
    (
        "mint-api-key.sh",
        "mint_api_key",
        ["--env", "prod", "--account-id", "acct-001", "--apply"],
        {"yes_prod": True},
    ),
    (
        "revoke-api-key.sh",
        "revoke_api_key",
        ["revoke", "--env", "prod", "--account-id", "acct-001", "--id", "k1", "--apply"],
        {"yes_prod": True},
    ),
    (
        "revoke-api-key.sh",
        "revoke_api_key",
        ["list", "--env", "dev", "--account-id", "acct-001"],
        {"yes_prod": False},
    ),
    (
        "mint-internal-token.sh",
        "mint_internal_token",
        ["--env", "prod", "--apply"],
        {"yes_prod": True},
    ),
    ("revoke-internal-token.sh", "revoke_internal_token", ["list"], {}),
    (
        "billing-checkout-allow.sh",
        "billing_checkout_allow",
        ["--env", "prod", "allow", "--email", EMAIL, "--apply"],
        {"yes": True, "yes_prod": True},
    ),
    (
        "billing-checkout-allow.sh",
        "billing_checkout_allow",
        ["--env", "prod", "clear", "--apply"],
        {"yes": True, "yes_prod": True},
    ),
    (
        "billing-checkout-allow.sh",
        "billing_checkout_allow",
        ["--env", "prod", "list"],
        {"yes_prod": True},
    ),
    (
        "assistant-allow.sh",
        "assistant_allow",
        ["--env", "prod", "allow", "--email", EMAIL, "--apply"],
        {"yes": True, "yes_prod": True},
    ),
    (
        "assistant-allow.sh",
        "assistant_allow",
        ["--env", "prod", "clear", "--apply"],
        {"yes": True, "yes_prod": True},
    ),
    (
        "assistant-allow.sh",
        "assistant_allow",
        ["--env", "prod", "list"],
        {"yes_prod": True},
    ),
]


def _script_parser(script: str) -> Any:
    spec = importlib.util.spec_from_file_location(
        f"ops_real_{script}", SCRIPTS_DIR / f"{script}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_parser()


@pytest.mark.parametrize(
    ("wrapper", "script", "typed", "expected"),
    PARSER_CASES,
    ids=[
        f"{case[0]}-{'-'.join(a for a in case[2] if not a.startswith('--'))[:24]}"
        for case in PARSER_CASES
    ],
)
def test_what_a_wrapper_hands_over_is_accepted_by_the_scripts_own_parser(
    run, capsys, wrapper: str, script: str, typed: list[str], expected: dict[str, Any]
) -> None:
    out = run(wrapper, *typed, confirm="prod")
    assert out.code == 0, out.stderr
    try:
        parsed = _script_parser(script).parse_args(_flags(out))
    except SystemExit:
        pytest.fail(f"{script}.py refused {_flags(out)}: {capsys.readouterr().err.strip()[-200:]}")
    for name, value in expected.items():
        assert getattr(parsed, name) is value, (name, _flags(out))


# ── the guards every wrapper shares ─────────────────────────────────────────────


def test_a_dry_run_on_dev_runs_the_script_without_yes_and_asks_nothing(run) -> None:
    out = run("account-erase.sh", "--env", "dev", "--email", EMAIL)
    assert out.code == 0
    assert _flags(out) == ["--env", "dev", "--email", EMAIL]
    assert out.stdout == STUB_STDOUT
    assert out.aws_calls == [
        "sts get-caller-identity --region eu-west-1 --query Account --output text"
    ]


def test_apply_asks_for_the_environment_word_then_adds_yes(run) -> None:
    out = run("account-erase.sh", "--env", "dev", "--email", EMAIL, "--apply", confirm="dev")
    assert out.code == 0
    assert _flags(out) == ["--env", "dev", "--email", EMAIL, "--yes"]
    assert "Type 'dev' to continue" in out.stderr
    assert out.stdout == STUB_STDOUT


def test_the_wrapper_never_shows_the_email_address(run) -> None:
    out = run("account-erase.sh", "--env", "dev", f"--email={EMAIL}", "--apply", confirm="dev")
    assert out.code == 0 and EMAIL in " ".join(_flags(out))
    assert EMAIL not in out.stderr and EMAIL not in out.stdout.replace("STDOUT", "")
    assert "--email=<masked>" in out.stderr
    spaced = run("account-erase.sh", "--env", "dev", "--email", EMAIL, "--apply", confirm="dev")
    assert EMAIL not in spaced.stderr and "--email <masked>" in spaced.stderr


def test_a_wrong_word_runs_nothing(run) -> None:
    out = run("account-erase.sh", "--env", "dev", "--email", EMAIL, "--apply", confirm="prod")
    assert out.code == 2 and out.python_args is None and out.stdout == ""
    assert "nothing was run" in out.stderr


def test_without_a_terminal_a_confirmation_is_refused(run) -> None:
    out = run("account-erase.sh", "--env", "dev", "--email", EMAIL, "--apply")
    assert out.code == 2 and out.python_args is None
    assert "terminal" in out.stderr


def test_prod_asks_even_for_a_dry_run_and_adds_yes_prod_once(run) -> None:
    out = run("audit-cleanup.sh", "--env", "prod", "--yes-prod", "--yes-prod", confirm="prod")
    assert out.code == 0
    assert _flags(out) == ["--env", "prod", "--yes-prod"]  # the person's own flags are dropped
    refused = run("audit-cleanup.sh", "--env", "prod")
    assert refused.code == 2 and refused.python_args is None


def test_a_yes_prod_typed_by_hand_does_not_skip_the_confirmation(run) -> None:
    out = run("audit-cleanup.sh", "--env", "prod", "--yes-prod")
    assert out.code == 2 and out.python_args is None


def test_prod_apply_adds_both_flags_after_the_word(run) -> None:
    out = run("audit-cleanup.sh", "--env", "prod", "--apply", confirm="prod")
    assert _flags(out) == ["--env", "prod", "--yes", "--yes-prod"]


@pytest.mark.parametrize("flag", ["--yes", "--secret-stdin"])
def test_the_flags_the_wrapper_owns_are_refused(run, flag: str) -> None:
    out = run("audit-cleanup.sh", "--env", "dev", flag)
    assert out.code == 2 and out.python_args is None and out.aws_calls == []


@pytest.mark.parametrize("env_args", [[], ["--env", "staging"]])
def test_an_environment_is_required_and_must_be_dev_or_prod(run, env_args: list[str]) -> None:
    out = run("audit-cleanup.sh", *env_args)
    assert out.code == 2 and out.python_args is None and out.aws_calls == []


def test_the_region_the_person_names_is_the_one_checked(run) -> None:
    out = run("audit-cleanup.sh", "--env", "dev", "--region", "us-east-1")
    assert out.aws_calls == [
        "sts get-caller-identity --region us-east-1 --query Account --output text"
    ]
    assert _flags(out) == ["--env", "dev", "--region", "us-east-1"]


def test_an_aws_cli_that_is_not_signed_in_stops_everything(run) -> None:
    out = run("audit-cleanup.sh", "--env", "dev", aws_fails=True)
    assert out.code == 3 and out.python_args is None
    assert "not signed in" in out.stderr and "Unable to locate credentials" in out.stderr


def test_a_missing_python_is_reported(run) -> None:
    out = run("audit-cleanup.sh", "--env", "dev", python="/no/such/python")
    assert out.code == 3 and "not found" in out.stderr


@pytest.mark.parametrize("code", [2, 3, 4, 5])
def test_the_scripts_exit_code_comes_back_unchanged(run, code: int) -> None:
    assert run("audit-cleanup.sh", "--env", "dev", exit_code=code).code == code


def test_help_goes_straight_to_the_script(run) -> None:
    out = run("education-grant.sh", "--help")
    assert out.code == 0 and _flags(out) == ["--help"] and out.aws_calls == []


# ── what each wrapper decides ───────────────────────────────────────────────────


def test_education_list_is_a_read(run) -> None:
    out = run("education-grant.sh", "list", "--env", "dev")
    assert out.code == 0 and _flags(out) == ["list", "--env", "dev"]


@pytest.mark.parametrize("command", ["grant", "extend", "revoke", "suspend-all", "anything-new"])
def test_education_changes_need_apply(run, command: str) -> None:
    out = run("education-grant.sh", command, "--env", "dev", "--email", EMAIL)
    assert out.code == 2 and out.python_args is None
    assert "add --apply" in out.stderr


def test_education_grant_with_apply_gets_no_yes_it_has_none(run) -> None:
    args = ["grant", "--env", "dev", "--email", EMAIL, "--cohort", "ucl-2026", "--apply"]
    out = run("education-grant.sh", *args, confirm="dev")
    assert _flags(out) == ["grant", "--env", "dev", "--email", EMAIL, "--cohort", "ucl-2026"]


def test_education_tidy_counts_first_and_acts_only_with_apply(run) -> None:
    dry = run("education-grant.sh", "tidy", "--env", "dev")
    assert _flags(dry) == ["tidy", "--env", "dev"]
    done = run("education-grant.sh", "tidy", "--env", "dev", "--apply", confirm="dev")
    assert _flags(done) == ["tidy", "--env", "dev", "--yes"]


def test_yes_all_is_never_added_for_the_person(run) -> None:
    out = run("education-grant.sh", "suspend-all", "--env", "dev", "--apply", confirm="dev")
    assert "--yes-all" not in _flags(out)  # the script then refuses it, as it should
    typed = run(
        "education-grant.sh", "suspend-all", "--env", "dev", "--yes-all", "--apply", confirm="dev"
    )
    assert "--yes-all" in _flags(typed)


def test_export_is_a_read_and_has_no_apply(run) -> None:
    out = run("account-export.sh", "--env", "dev", "--email", EMAIL, "--out", "x.json")
    assert out.code == 0 and _flags(out) == ["--env", "dev", "--email", EMAIL, "--out", "x.json"]
    refused = run(
        "account-export.sh", "--env", "dev", "--email", EMAIL, "--out", "x.json", "--apply"
    )
    assert refused.code == 2 and refused.python_args is None


def test_minting_needs_apply_and_keeps_stdout_for_the_token(run) -> None:
    refused = run("mint-internal-token.sh", "--env", "dev")
    assert refused.code == 2 and refused.python_args is None and refused.stdout == ""
    out = run("mint-internal-token.sh", "--env", "dev", "--apply", confirm="dev")
    assert out.code == 0 and out.stdout == STUB_STDOUT  # nothing of the wrapper's on stdout
    assert "Type 'dev' to continue" in out.stderr


def test_decoding_a_token_needs_no_environment_no_aws_and_no_apply(run) -> None:
    out = run("mint-internal-token.sh", "--decode", "a.b.c")
    assert out.code == 0 and _flags(out) == ["--decode", "a.b.c"] and out.aws_calls == []
    assert run("mint-internal-token.sh", "--decode", "a.b.c", "--apply").code == 2


def test_a_session_token_in_hand_needs_no_aws(run) -> None:
    with_token = run(
        "mint-api-key.sh", "--env", "dev", "--session-token-env", "PYVAR_SESSION", "--apply",
        confirm="dev",
    )  # fmt: skip
    assert with_token.code == 0 and with_token.aws_calls == []
    signed = run(
        "mint-api-key.sh", "--env", "dev", "--account-id", "acct-1", "--apply", confirm="dev"
    )
    assert signed.code == 0 and len(signed.aws_calls) == 1
    listing = run("revoke-api-key.sh", "list", "--env", "dev", "--session-token-env", "VAR")
    assert listing.code == 0 and listing.aws_calls == []


def test_revoking_a_key_needs_apply_and_listing_does_not(run) -> None:
    assert run("revoke-api-key.sh", "list", "--env", "dev", "--account-id", "acct-1").code == 0
    refused = run(
        "revoke-api-key.sh", "revoke", "--env", "dev", "--account-id", "acct-1", "--id", "k"
    )
    assert refused.code == 2 and refused.python_args is None


def test_the_local_ledger_commands_need_no_aws_and_no_environment(run) -> None:
    out = run("revoke-internal-token.sh", "revoke", "--sub", "load-test", exit_code=4)
    assert out.code == 4 and out.aws_calls == []  # "recorded, not enforced" comes back as it is
    assert _flags(out) == ["revoke", "--sub", "load-test"]
    assert run("revoke-internal-token.sh", "list", "--env", "prod").aws_calls == []
    assert run("revoke-internal-token.sh", "list", "--apply").code == 2


def test_the_billing_wrapper_puts_yes_prod_before_the_subcommand_and_yes_after_it(run) -> None:
    # In billing_checkout_allow.py --env and --yes-prod belong to the parser before the subcommand and --yes to the
    # subcommand, so the wrapper must not simply append both.
    out = run(
        "billing-checkout-allow.sh",
        "--env",
        "prod",
        "allow",
        "--email",
        EMAIL,
        "--apply",
        confirm="prod",
    )
    assert _flags(out) == ["--yes-prod", "--env", "prod", "allow", "--email", EMAIL, "--yes"]
    assert EMAIL not in out.stderr and "--email <masked>" in out.stderr


def test_the_billing_wrapper_reads_for_list_and_dry_runs_the_rest_without_apply(run) -> None:
    assert _flags(run("billing-checkout-allow.sh", "--env", "dev", "list")) == [
        "--env",
        "dev",
        "list",
    ]
    for action in (["allow", "--email", EMAIL], ["remove", "--email", EMAIL], ["clear"]):
        dry = run("billing-checkout-allow.sh", "--env", "dev", *action)
        assert dry.code == 0 and "--yes" not in _flags(dry)  # the script's own dry run
    assert run("billing-checkout-allow.sh", "--env", "dev", "list", "--apply").code == 2


def test_the_billing_wrapper_asks_before_clearing_the_allow_list(run) -> None:
    refused = run("billing-checkout-allow.sh", "--env", "dev", "clear", "--apply", confirm="no")
    assert refused.code == 2 and refused.python_args is None
    done = run("billing-checkout-allow.sh", "--env", "dev", "clear", "--apply", confirm="dev")
    assert _flags(done) == ["--env", "dev", "clear", "--yes"]


def test_the_assistant_wrapper_puts_yes_prod_before_the_subcommand_and_yes_after_it(run) -> None:
    # assistant_allow.py follows billing_checkout_allow.py: --env and --yes-prod belong to the parser before the
    # subcommand and --yes to the subcommand, so the wrapper must not simply append both.
    out = run(
        "assistant-allow.sh",
        "--env",
        "prod",
        "allow",
        "--email",
        EMAIL,
        "--apply",
        confirm="prod",
    )
    assert _flags(out) == ["--yes-prod", "--env", "prod", "allow", "--email", EMAIL, "--yes"]
    assert EMAIL not in out.stderr and "--email <masked>" in out.stderr


def test_the_assistant_wrapper_reads_for_list_and_dry_runs_the_rest_without_apply(run) -> None:
    assert _flags(run("assistant-allow.sh", "--env", "dev", "list")) == ["--env", "dev", "list"]
    for action in (["allow", "--email", EMAIL], ["remove", "--email", EMAIL], ["clear"]):
        dry = run("assistant-allow.sh", "--env", "dev", *action)
        assert dry.code == 0 and "--yes" not in _flags(dry)  # the script's own dry run
    assert run("assistant-allow.sh", "--env", "dev", "list", "--apply").code == 2


def test_the_assistant_wrapper_asks_before_clearing_the_allowlist(run) -> None:
    refused = run("assistant-allow.sh", "--env", "dev", "clear", "--apply", confirm="no")
    assert refused.code == 2 and refused.python_args is None
    done = run("assistant-allow.sh", "--env", "dev", "clear", "--apply", confirm="dev")
    assert _flags(done) == ["--env", "dev", "clear", "--yes"]

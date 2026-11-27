#!/usr/bin/env python3
"""scripts/assistant_allow.py: who may ask the typed assistant a question while the allowlist is on.

Reasoning:
- While `assistant_allowlist_enabled` is on (the first weeks of the typed assistant in prod, docs/assistant-runbook.md),
  only signed-in accounts in a Redis set may ask a typed question (api/assistant/deps.py::require_allowed); anyone else,
  and every anonymous visitor, is refused before any quota or model call. This is the command that manages that set.
  Like scripts/billing_checkout_allow.py, which it follows, it signs a 10-minute ADMIN token (audience "pyvar-admin",
  no tier) with the environment's secret, read from AWS Secrets Manager by the AWS CLI, and calls
  /internal/admin/assistant/allow. It needs no Redis or database access: the API looks the address up and keeps only
  the account's opaque identifier in the set.
- Four actions. `allow` and `remove` take an `--email`; `list` prints the identifiers in the allowlist; `clear` empties it
  (every account is refused at once, no deploy). allow, remove and clear are DRY RUNS unless `--yes`; prod needs
  `--yes-prod`. `list` only reads.
- The address is sent to the API over https and is never printed or written anywhere here. Output and the ledger
  (default ~/.pyvar/assistant_allow.jsonl, 0600: time, operator, environment, action, account identifier, set size)
  name the account by identifier. No secret or token is ever written or printed.
- It says "allowed" or "removed" only when a second call to the API confirms the account's new state.
- It also says whether the allowlist is ON in that environment: the set does nothing where
  `assistant_allowlist_enabled` is off, because everyone the other switches admit may ask there.

Usage (repo root):
    python scripts/assistant_allow.py --env prod --yes-prod allow  --email a@b.com          # dry run
    python scripts/assistant_allow.py --env prod --yes-prod allow  --email a@b.com --yes
    python scripts/assistant_allow.py --env prod --yes-prod remove --email a@b.com --yes
    python scripts/assistant_allow.py --env prod --yes-prod list
    python scripts/assistant_allow.py --env prod --yes-prod clear --yes

Exit codes: 0 done; 2 refused by a guard or bad arguments; 3 the secret could not be read; 5 the API refused, could not
be reached, or the change could not be confirmed.
"""

from __future__ import annotations

import argparse
import getpass
import sys
import time
from pathlib import Path
from typing import Any, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parent))

from token_tools import (  # noqa: E402
    ACCOUNT_ID_PATTERN,
    DEFAULT_REGION,
    ENVS,
    ToolError,
    api_request,
    append_ledger,
    base_url_for,
    check_secret,
    iso,
    ledger_path,
    read_secret_from_aws,
    require_env,
    sign_admin_token,
)

ADMIN_AUDIENCE = "pyvar-admin"  # api/middleware/auth.py::ADMIN_TOKEN_AUDIENCE
ADMIN_TTL_SECONDS = 600
LEDGER_ENV = "PYVAR_ASSISTANT_ALLOW_LEDGER"
LEDGER_NAME = "assistant_allow.jsonl"
ROUTE = "/api/v1/internal/admin/assistant/allow"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage who may ask the typed assistant a question while the allowlist is on."
    )
    parser.add_argument("--env", choices=ENVS, help="which environment's API to call")
    parser.add_argument("--yes-prod", action="store_true", help="required for prod")
    parser.add_argument(
        "--operator", default=getpass.getuser(), help="your label (the token's sub)"
    )
    parser.add_argument("--region", default=DEFAULT_REGION, help="the secret's region")
    parser.add_argument("--secret-stdin", action="store_true", help="read the secret from stdin")
    parser.add_argument("--base-url", help="loopback only, for tests")
    parser.add_argument("--ledger", help=f"ledger file (else ${LEDGER_ENV}, else ~/.pyvar/...)")
    actions = parser.add_subparsers(dest="action", required=True)
    for name, help_text in (
        ("allow", "let an account ask typed questions"),
        ("remove", "take an account out of the set"),
    ):
        sub = actions.add_parser(name, help=help_text)
        sub.add_argument("--email", required=True, help="the account's e-mail address")
        sub.add_argument("--yes", action="store_true", help="do it (otherwise a dry run)")
    actions.add_parser("list", help="print the account identifiers in the set")
    clear = actions.add_parser("clear", help="empty the set: every account is refused at once")
    clear.add_argument("--yes", action="store_true", help="do it (otherwise a dry run)")
    return parser


def _admin_token(args: argparse.Namespace, env: str) -> str:
    if not ACCOUNT_ID_PATTERN.match(args.operator):
        raise ToolError("--operator must be 3-128 characters of letters, digits and . _ : @ -")
    raw = sys.stdin.read() if args.secret_stdin else read_secret_from_aws(env, args.region)
    secret = check_secret(raw)
    return sign_admin_token(
        secret, operator=args.operator, audience=ADMIN_AUDIENCE, ttl_seconds=ADMIN_TTL_SECONDS
    )


def _post(url: str, token: str, body: dict[str, Any]) -> tuple[int, Any]:
    return api_request("POST", url, token, body)


def _refusal(status: int, data: Any, action: str) -> ToolError:
    reasons = {
        401: "the admin token was refused: wrong environment's secret, or this API is not the new version",
        404: "no account has this address",
        422: "the API rejected the request as invalid",
        503: "the allowlist could not be reached; nothing was changed",
    }
    detail = data.get("detail") if isinstance(data, dict) else None
    text = detail if isinstance(detail, str) else reasons.get(status, "unexpected answer")
    return ToolError(f"{action}: HTTP {status}: {text}", 5)


def _gate_note(data: dict[str, Any], out: TextIO) -> None:
    if not data.get("enabled"):
        print(
            "note: the allowlist is OFF in this environment, so the set has no effect on who may ask",
            file=out,
        )


def _record(args: argparse.Namespace, env: str, action: str, data: dict[str, Any]) -> None:
    append_ledger(
        ledger_path(args.ledger, LEDGER_ENV, LEDGER_NAME),
        {
            "at": iso(int(time.time())),
            "by": args.operator,
            "env": env,
            "action": action,
            "account": data.get("account_id"),
            "members": data.get("members"),
        },
    )


def _run_list(url: str, token: str, out: TextIO) -> int:
    status, data = _post(url, token, {"action": "list"})
    if status != 200:
        raise _refusal(status, data, "list")
    ids = data["account_ids"]
    print(f"{len(ids)} account(s) in the allowlist", file=out)
    for account_id in ids:
        print(f"  {account_id}", file=out)
    _gate_note(data, out)
    return 0


def _run_clear(args: argparse.Namespace, env: str, url: str, token: str, out: TextIO) -> int:
    status, data = _post(url, token, {"action": "clear", "apply": False})
    if status != 200:
        raise _refusal(status, data, "clear (dry run)")
    count = data["members"]
    if not args.yes:
        print(
            f"dry run: {count} account(s) would be removed, so every account is refused. Add --yes to do it.",
            file=out,
        )
        return 0
    status, data = _post(url, token, {"action": "clear", "apply": True})
    if status != 200 or not data.get("applied"):
        raise _refusal(status, data, "clear")
    status, check = _post(url, token, {"action": "list"})
    if status != 200 or check.get("members") != 0:
        raise ToolError("asked to clear the set but it is not empty", 5)
    _record(args, env, "clear", data)
    print(f"cleared: {count} account(s) removed; confirmed by the API (the set is empty)", file=out)
    _gate_note(data, out)
    return 0


def _run_one(args: argparse.Namespace, env: str, url: str, token: str, out: TextIO) -> int:
    action = args.action
    email = args.email.strip().lower()
    status, data = _post(url, token, {"action": action, "email": email, "apply": False})
    if status != 200:
        raise _refusal(status, data, f"{action} (dry run)")
    account, tier, was = data["account_id"], data["tier"], data["was_allowed"]
    state = "is already" if was else "is not yet"
    if action == "remove":
        state = "is" if was else "is not"
    summary = f"account {account} ({tier}) {state} in the allowlist ({data['members']} in total)"
    if not args.yes:
        print(f"dry run: {summary}. Add --yes to {action} it.", file=out)
        _gate_note(data, out)
        return 0
    status, data = _post(url, token, {"action": action, "email": email, "apply": True})
    if status != 200 or not data.get("applied"):
        raise _refusal(status, data, action)
    status, check = _post(url, token, {"action": action, "email": email, "apply": False})
    wanted = action == "allow"
    if status != 200 or check.get("was_allowed") is not wanted:
        raise ToolError(f"asked to {action} the account but the API does not show it", 5)
    _record(args, env, action, data)
    done = "allowed" if wanted else "removed"
    print(
        f"{done}: account {account} ({tier}); {data['members']} in the allowlist; confirmed by the API",
        file=out,
    )
    _gate_note(data, out)
    return 0


def run(args: argparse.Namespace, out: TextIO) -> int:
    env = require_env(args.env, args.yes_prod)
    base = base_url_for(env, args.base_url)
    token = _admin_token(args, env)
    url = f"{base}{ROUTE}"
    if args.action == "list":
        return _run_list(url, token, out)
    if args.action == "clear":
        return _run_clear(args, env, url, token, out)
    return _run_one(args, env, url, token, out)


def main(
    argv: list[str] | None = None, *, stdout: TextIO | None = None, stderr: TextIO | None = None
) -> int:
    """Command entry point. `stdout` and `stderr` default to the process's; tests pass buffers."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    args = build_parser().parse_args(argv)
    try:
        return run(args, out)
    except ToolError as exc:
        print(f"refused: {exc}", file=err)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())

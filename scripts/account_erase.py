#!/usr/bin/env python3
"""scripts/account_erase.py: erase an account at its holder's request (docs/plan-education-tier.md section 12).

Reasoning:
- The privacy policy promises that, on request, we "delete your e-mail address and switch off your API keys", and
  that the records of tier changes then carry only an account identifier we can no longer match to the person.
  There is no button, so this is the command. Like scripts/education_grant.py it signs a 10-minute ADMIN token
  (audience "pyvar-admin", no tier) with the environment's secret, read from AWS Secrets Manager by the AWS CLI,
  and calls /internal/admin/accounts/erase. No database access; no other credential can call the route.
- It does NOT delete rows: `api_keys` rows are never deleted (CLAUDE.md 3.3 and 3.5) and the audit tables name the
  account by its identifier. The API sets the e-mail address to NULL, clears the sign-in tokens, revokes every
  live key and blanks every key's name, resets an education label to free, and writes one `billing_events` row
  (code=erase). See api/account_erasure.py.
- DRY RUN BY DEFAULT: without `--yes` it only says what it would do. With `--yes` it does it, then asks the API
  again and exits 5 unless the address no longer matches any account: it does what it says.
- Only free and education accounts. A pro, enterprise or internal account is refused (exit 5, the API's reason).
- It cannot clear everything, and prints what is left to do by hand: the company mailbox (messages, and the
  webmail bin), Stripe if the account was linked to a Stripe customer, the requests log, and a note that an
  account that signed up with Google cannot sign in with that Google account again (it can register by e-mail).
- The address is never written down: not to the ledger (default ~/.pyvar/erasures.jsonl, 0600: time, operator,
  environment, the account identifier, how many keys), not to stdout, not to a log line. The account identifier
  in the answer is the handle for searching logs and Sentry. No secret or token is ever written or printed.

Usage (repo root):
    python scripts/account_erase.py --env prod --yes-prod --email a@uni.ac.uk          # dry run
    python scripts/account_erase.py --env prod --yes-prod --email a@uni.ac.uk --yes    # does it

Exit codes: 0 done (and confirmed) or dry run shown; 2 refused by a guard or bad arguments; 3 the secret could not
be read; 5 the API refused, could not be reached, or the erasure could not be confirmed.
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
LEDGER_ENV = "PYVAR_ERASURE_LEDGER"
LEDGER_NAME = "erasures.jsonl"
ROUTE = "/api/v1/internal/admin/accounts/erase"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Erase a pyvar account at its holder's request.")
    parser.add_argument("--env", choices=ENVS, help="which environment's API to call")
    parser.add_argument("--yes-prod", action="store_true", help="required for prod")
    parser.add_argument("--email", required=True, help="the account's e-mail address")
    parser.add_argument("--yes", action="store_true", help="do it (otherwise a dry run)")
    parser.add_argument(
        "--operator", default=getpass.getuser(), help="your label (the token's sub)"
    )
    parser.add_argument("--region", default=DEFAULT_REGION, help="the secret's region")
    parser.add_argument("--secret-stdin", action="store_true", help="read the secret from stdin")
    parser.add_argument("--base-url", help="loopback only, for tests")
    parser.add_argument("--ledger", help=f"ledger file (else ${LEDGER_ENV}, else ~/.pyvar/...)")
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
        409: "refused by a rule",
        422: "the API rejected the request as invalid",
    }
    detail = data.get("detail") if isinstance(data, dict) else None
    text = detail if isinstance(detail, str) else reasons.get(status, "unexpected answer")
    return ToolError(f"{action}: HTTP {status}: {text}", 5)


def _by_hand(data: dict[str, Any], out: TextIO) -> None:
    print("Still to do by hand:", file=out)
    print(
        "  - the company mailbox: delete this person's messages, empty the webmail bin",
        file=out,
    )
    if data.get("stripe_linked"):
        print(
            "  - Stripe: this account was linked to a Stripe customer; erase it there too", file=out
        )
    if data.get("google_sign_in"):
        print(
            "  - this account signed up with Google: that Google account cannot sign in again "
            "(it can register by e-mail)",
            file=out,
        )
    print("  - the requests log: one line (date, type, date answered, what was done)", file=out)
    print(
        f"  - search logs and Sentry for the account identifier {data.get('account_id')}", file=out
    )


def run(args: argparse.Namespace, out: TextIO) -> int:
    env = require_env(args.env, args.yes_prod)
    base = base_url_for(env, args.base_url)
    token = _admin_token(args, env)
    url = f"{base}{ROUTE}"
    email = args.email.strip().lower()

    status, data = _post(url, token, {"email": email, "apply": False})
    if status != 200:
        raise _refusal(status, data, "erase (dry run)")
    summary = (
        f"account {data['account_id']} ({data['old_tier']}): {data['keys_revoked']} live key(s) to "
        f"switch off, {data['keys_renamed']} key name(s) to blank, the e-mail address to remove"
    )
    if not args.yes:
        print(f"dry run: {summary}. Add --yes to do it.", file=out)
        return 0

    status, data = _post(url, token, {"email": email, "apply": True})
    if status != 200 or not data.get("applied"):
        raise _refusal(status, data, "erase")
    status, _ = _post(url, token, {"email": email, "apply": False})
    if status != 404:
        raise ToolError("asked to erase the account but the address still matches one", 5)
    append_ledger(
        ledger_path(args.ledger, LEDGER_ENV, LEDGER_NAME),
        {
            "at": iso(int(time.time())),
            "by": args.operator,
            "env": env,
            "action": "erase",
            "account": data["account_id"],
            "keys_revoked": data["keys_revoked"],
        },
    )
    print(f"erased: {summary}; confirmed by the API (the address matches no account)", file=out)
    _by_hand(data, out)
    return 0


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

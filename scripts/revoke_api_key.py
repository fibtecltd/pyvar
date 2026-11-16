#!/usr/bin/env python3
"""scripts/revoke_api_key.py: list an account's pyvar API keys and revoke them for real.

Reasoning:
- Unlike a JWT, an API key (`pyvar_...`) can be revoked: DELETE /api/v1/auth/api-keys/{id} sets
  `revoked_at` (the row is kept: keys are audit records) and drops the key from the Redis cache, so
  it stops working at once (api/routes/auth.py, api/middleware/api_keys.py). This command calls that
  route, then lists the keys again and checks `revoked_at` is set before it says "revoked", and it
  exits 5 if it cannot confirm. It does what it says.
- Like scripts/mint_api_key.py it needs a session for the owning account (an API key cannot manage
  keys: CLAUDE.md section 3.5): `--account-id` (a 10-minute session token is signed with the
  environment's secret) or `--session-token-env VAR` (a session token the account already holds).
- `--all-active` is the incident switch for one account: it needs `--yes-all`.
- The API lists at most the newest 50 keys of an account; a key older than that cannot be found by
  prefix here (the account's own dashboard has the same limit), so use `--id`.
- The ledger (default ~/.pyvar/api-keys.jsonl) gets one `revoked` line per key. No key is ever read
  or stored: only ids and prefixes.

Usage (repo root):
    python scripts/revoke_api_key.py list   --env dev --account-id <external_id>
    python scripts/revoke_api_key.py revoke --env dev --account-id <external_id> --prefix pyvar_ab12cd
    python scripts/revoke_api_key.py revoke --env dev --account-id <external_id> --id <uuid>
    python scripts/revoke_api_key.py revoke --env prod --yes-prod --account-id <id> --all-active --yes-all

Exit codes: 0 done and confirmed (or nothing active to revoke); 2 refused or nothing matched;
3 the secret could not be read; 5 the API refused, could not be reached, or the revocation could
not be confirmed.
"""

from __future__ import annotations

import argparse
import getpass
import sys
import time
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from token_tools import (  # noqa: E402
    DEFAULT_REGION,
    ENVS,
    KEY_LEDGER_ENV,
    ToolError,
    api_request,
    append_ledger,
    base_url_for,
    explain_api_failure,
    iso,
    ledger_path,
    parse_iso,
    require_env,
    session_token,
)

LEDGER_NAME = "api-keys.jsonl"
MIN_PREFIX = 8


def key_status(key: dict[str, Any], now: int) -> str:
    """active, revoked or expired, from one entry of the API's key list."""
    if key.get("revoked_at"):
        return "revoked"
    expires = key.get("expires_at")
    if expires and parse_iso(str(expires)) <= now:
        return "expired"
    return "active"


def fetch_keys(base: str, token: str) -> list[dict[str, Any]]:
    """The account's keys as the API lists them."""
    status, data = api_request("GET", f"{base}/api/v1/auth/api-keys", token)
    if status != 200 or not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        raise explain_api_failure(status, "listing the keys")
    return [item for item in data["keys"] if isinstance(item, dict)]


def show(keys: list[dict[str, Any]], now: int) -> None:
    """Print keys as a table on stdout."""
    if not keys:
        print("(none)")
        return
    print(f"{'STATUS':<8} {'PREFIX':<16} {'NAME':<20} {'EXPIRES':<21} {'LAST USED':<21} ID")
    for key in keys:
        print(
            f"{key_status(key, now):<8} {str(key.get('prefix', '?')):<16} "
            f"{str(key.get('name', ''))[:20]:<20} {str(key.get('expires_at') or '-')[:19]:<21} "
            f"{str(key.get('last_used_at') or '-')[:19]:<21} {key.get('id')}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List and revoke an account's pyvar API keys.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("list", "the account's keys"), ("revoke", "revoke key(s)")):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--env", choices=ENVS, help="which environment's API to call")
        sub.add_argument("--yes-prod", action="store_true", help="required for prod")
        sub.add_argument("--account-id", help="the account's external id")
        sub.add_argument(
            "--session-token-env", metavar="VAR", help="env variable with a session token"
        )
        sub.add_argument("--region", default=DEFAULT_REGION, help="the secret's region")
        sub.add_argument("--secret-stdin", action="store_true", help="read the secret from stdin")
        sub.add_argument("--base-url", help="loopback only, for tests")
        sub.add_argument(
            "--ledger", help=f"ledger file (else ${KEY_LEDGER_ENV}, else ~/.pyvar/...)"
        )
        if name == "list":
            sub.add_argument("--all", action="store_true", help="include revoked and expired")
        else:
            which = sub.add_mutually_exclusive_group(required=True)
            which.add_argument("--id", help="the key's id (uuid)")
            which.add_argument(
                "--prefix", help=f"the key's prefix, at least {MIN_PREFIX} characters"
            )
            which.add_argument("--all-active", action="store_true", help="every active key")
            sub.add_argument("--yes-all", action="store_true", help="confirms --all-active")
            sub.add_argument("--reason", default="", help="why (kept in the ledger)")
    return parser


def choose(keys: list[dict[str, Any]], args: argparse.Namespace, now: int) -> list[dict[str, Any]]:
    """The keys a `revoke` names.

    Raises:
        ToolError: if the id or prefix is malformed, ambiguous or unknown, or --all-active lacks
            --yes-all.
    """
    if args.all_active:
        if not args.yes_all:
            raise ToolError("--all-active revokes every active key of the account: add --yes-all")
        return [k for k in keys if key_status(k, now) == "active"]
    if args.id:
        try:
            wanted = str(uuid.UUID(args.id))
        except ValueError as exc:
            raise ToolError("--id must be a uuid") from exc
        chosen = [k for k in keys if str(k.get("id")) == wanted]
    else:
        if len(args.prefix) < MIN_PREFIX:
            raise ToolError(f"give at least {MIN_PREFIX} characters of the prefix")
        chosen = [k for k in keys if str(k.get("prefix", "")).startswith(args.prefix)]
        if len(chosen) > 1:
            raise ToolError("that prefix matches several keys; give more characters or use --id")
    if not chosen:
        raise ToolError("no such key for this account (the API lists only the newest 50)")
    return chosen


def run(args: argparse.Namespace) -> int:
    env = require_env(args.env, args.yes_prod)
    token = session_token(
        env,
        account_id=args.account_id,
        token_env_var=args.session_token_env,
        region=args.region,
        secret_stdin=args.secret_stdin,
    )
    base = base_url_for(env, args.base_url)
    now = int(time.time())
    keys = fetch_keys(base, token)
    if args.command == "list":
        show(keys if args.all else [k for k in keys if key_status(k, now) == "active"], now)
        return 0

    chosen = choose(keys, args, now)
    targets = [k for k in chosen if key_status(k, now) == "active"]
    for key in chosen:
        if key not in targets:
            print(f"{key.get('prefix')}: already {key_status(key, now)}", file=sys.stderr)
    for key in targets:
        status, _ = api_request("DELETE", f"{base}/api/v1/auth/api-keys/{key['id']}", token)
        if status != 204:
            raise explain_api_failure(status, f"revoking {key.get('prefix')}")
    after = {str(k.get("id")): k for k in fetch_keys(base, token)}
    unconfirmed = [k for k in targets if not after.get(str(k["id"]), {}).get("revoked_at")]
    if unconfirmed:
        names = ", ".join(str(k.get("prefix")) for k in unconfirmed)
        raise ToolError(f"asked to revoke but could not confirm: {names}", 5)
    for key in targets:
        append_ledger(
            ledger_path(args.ledger, KEY_LEDGER_ENV, LEDGER_NAME),
            {
                "event": "revoked",
                "revoked_at": iso(now),
                "revoked_by": getpass.getuser(),
                "env": env,
                "account_id": args.account_id or "(session token)",
                "key_id": key.get("id"),
                "prefix": key.get("prefix"),
                "reason": args.reason,
            },
        )
        print(f"revoked {key.get('prefix')} ({key.get('name')}), confirmed by the API")
    if not targets:
        print("Nothing active to revoke.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Command entry point."""
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except ToolError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())

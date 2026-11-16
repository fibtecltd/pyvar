#!/usr/bin/env python3
"""scripts/mint_api_key.py: create a durable pyvar API key (`pyvar_...`) for an existing account.

Reasoning:
- An API key is the revocable kind of credential: pyvar stores only its SHA-256, the key's tier is
  read from the database on every use, it has an expiry (1 year) and it can be revoked at once
  (docs/plan-durable-api-keys.md). This command creates one through the API's own route,
  POST /api/v1/auth/api-keys, which needs a signed-in session for the account that will own it
  (an API key cannot create keys: CLAUDE.md section 3.5). So the command first obtains a session
  token for that account, then makes the one call; it adds no way into the database.
- Two ways to get the session token: `--account-id`, the account's `external_id` (the `sub` of its
  session tokens), for which a 10-minute session token is signed with the environment's secret (the
  same access scripts/mint_internal_token.py needs); or `--session-token-env VAR`, a session token
  the account already holds (the one the portal keeps after sign-in).
- The key's tier is the ACCOUNT's tier. This command cannot create an account or change a tier, so it
  cannot make an "internal" or "academic" key: that needs the admin routes proposed in
  docs/plan-academic-access.md.
- The key goes to stdout alone, once; pyvar cannot show it again. The ledger (default
  ~/.pyvar/api-keys.jsonl, mode 0600) records the key's id and prefix, never the key.
- Pair: scripts/revoke_api_key.py lists and revokes. Revocation is real: it takes effect at once.

Usage (repo root):
    KEY=$(python scripts/mint_api_key.py --env dev --account-id <external_id> --name ci-dev)
    PYVAR_SESSION=<token from the portal> python scripts/mint_api_key.py --env dev \\
        --session-token-env PYVAR_SESSION --name laptop
    python scripts/mint_api_key.py --env prod --yes-prod --account-id <external_id> --name partner-demo

Exit codes: 0 key created; 2 refused by a guard or bad arguments; 3 the secret could not be read;
5 the API refused or could not be reached.
"""

from __future__ import annotations

import argparse
import getpass
import sys
import time
from pathlib import Path

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
    require_env,
    session_token,
)

LEDGER_NAME = "api-keys.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a pyvar API key for an existing account.",
        epilog="The key is printed to stdout once and alone; everything else goes to stderr.",
    )
    parser.add_argument("--env", choices=ENVS, help="which environment's API to call")
    parser.add_argument("--yes-prod", action="store_true", help="required for prod")
    parser.add_argument("--account-id", help="the account's external id (the sub of its sessions)")
    parser.add_argument(
        "--session-token-env", metavar="VAR", help="env variable with a session token"
    )
    parser.add_argument("--name", default="default", help="label for the key, 1-64 characters")
    parser.add_argument("--region", default=DEFAULT_REGION, help="the secret's region")
    parser.add_argument("--secret-stdin", action="store_true", help="read the secret from stdin")
    parser.add_argument("--base-url", help="loopback only, for tests")
    parser.add_argument("--ledger", help=f"ledger file (else ${KEY_LEDGER_ENV}, else ~/.pyvar/...)")
    parser.add_argument("--no-ledger", action="store_true", help="do not record this key")
    return parser


def run(args: argparse.Namespace) -> int:
    env = require_env(args.env, args.yes_prod)
    name = args.name.strip()
    if not 1 <= len(name) <= 64:
        raise ToolError("--name must be 1 to 64 characters")
    token = session_token(
        env,
        account_id=args.account_id,
        token_env_var=args.session_token_env,
        region=args.region,
        secret_stdin=args.secret_stdin,
    )
    url = f"{base_url_for(env, args.base_url)}/api/v1/auth/api-keys"
    status, data = api_request("POST", url, token, {"name": name})
    if status != 201 or not isinstance(data, dict) or not data.get("key"):
        raise explain_api_failure(status, "creating the key")

    now = int(time.time())
    if not args.no_ledger:
        append_ledger(
            ledger_path(args.ledger, KEY_LEDGER_ENV, LEDGER_NAME),
            {
                "event": "minted",
                "minted_at": iso(now),
                "minted_by": getpass.getuser(),
                "env": env,
                "account_id": args.account_id or "(session token)",
                "key_id": data.get("id"),
                "prefix": data.get("prefix"),
                "name": data.get("name"),
                "expires_at": data.get("expires_at"),
            },
        )
    sys.stdout.write(str(data["key"]) + "\n")
    print(
        f"env={env} key_id={data.get('id')} prefix={data.get('prefix')} name={data.get('name')} "
        f"expires={data.get('expires_at')}",
        file=sys.stderr,
    )
    print(
        "Shown once: pyvar stores only a hash. The key has the tier of its account, read from the "
        "database. Revoke it with scripts/revoke_api_key.py (effective at once).",
        file=sys.stderr,
    )
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

#!/usr/bin/env python3
"""scripts/mint_internal_token.py: sign a pyvar API token (default tier "internal") on demand.

Reasoning:
- A pyvar session token is an HS256 JWT signed with the environment's secret (Secrets Manager
  `pyvar/<env>/jwt-secret`), and the tier is a claim inside it (api/middleware/auth.py). Whoever
  can read that secret can sign a token of any tier; pyvar's own scheduled jobs do exactly this
  (pyvar-cdk/lambda/public_data_publisher/handler.py). This script is that recipe with guard rails
  for a person: the same claims, an expiry that is always present, and a record of what was issued.
- Tier "internal" is exempt from every rate limit, may run 500,000 simulations and may call the
  service-only /internal routes (api/middleware/rate_limit.py, auth.py, api/routes/internal.py). It
  is meant for Fibtec's own tools, tests and load runs. Do not hand one to a third party: it
  cannot be revoked and it is not tied to an account.
- A JWT cannot be revoked by the API. Its expiry is the only limit, so the default is 1 day and the
  ceiling is 90. scripts/revoke_internal_token.py lists what is outstanding and holds the emergency
  runbook (rotating the secret). See docs/internal-tokens-and-signing-secrets.md.
- The secret is read with the AWS CLI (nothing to install), travels through a pipe, never a
  command-line argument, and is never printed or written. The token goes to stdout alone; the
  summary goes to stderr, so `TOKEN=$(...)` captures just the token.
- The ledger (default ~/.pyvar/minted-tokens.jsonl, mode 0600) records who minted what and when it
  expires, with the token's unique id (jti) and a short fingerprint. It never holds the token or
  the secret.

Usage (repo root; needs the AWS CLI signed in with read access to the secret):
    TOKEN=$(python scripts/mint_internal_token.py --env dev)                     # 1 day, internal
    python scripts/mint_internal_token.py --env dev --days 7 --sub load-test-nov
    python scripts/mint_internal_token.py --env prod --days 1 --yes-prod         # prod needs the flag
    python scripts/mint_internal_token.py --env dev --tier free                  # a free-tier test token
    python scripts/mint_internal_token.py --decode "$TOKEN"                      # read a token's claims
    printf %s "$SECRET" | python scripts/mint_internal_token.py --env dev --secret-stdin   # offline

Exit codes: 0 done; 2 refused by a guard or bad arguments; 3 the secret could not be read.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from token_tools import (  # noqa: E402
    DEFAULT_REGION,
    ENVS,
    LEDGER_ENV,
    PUBLIC_DEFAULT_SECRET,
    ToolError,
    append_ledger,
    check_secret,
    decode_unverified,
    fingerprint,
    iso,
    ledger_path,
    read_secret_from_aws,
    require_env,
    sign_token,
)

__all__ = ["LEDGER_ENV", "PUBLIC_DEFAULT_SECRET", "decode_unverified", "fingerprint", "main"]

TIERS = ("internal", "enterprise", "pro", "free")
DEFAULT_DAYS = 1.0
MAX_DAYS = 90.0
SUB_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
LEDGER_NAME = "minted-tokens.jsonl"


def default_sub(env: str, tier: str, now: int) -> str:
    """A label that is unique per run, e.g. internal-dev-20261116-3fa9."""
    stamp = datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%d")
    return f"{tier}-{env}-{stamp}-{secrets.token_hex(2)}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sign a pyvar API token on demand (default tier: internal).",
        epilog="The token is printed to stdout alone; everything else goes to stderr.",
    )
    parser.add_argument("--env", choices=ENVS, help="which environment's secret signs the token")
    parser.add_argument("--days", type=float, default=DEFAULT_DAYS, help="lifetime (default 1)")
    parser.add_argument("--tier", choices=TIERS, default="internal", help="tier claim")
    parser.add_argument(
        "--sub", help="holder label (3-64 chars of a-z 0-9 . _ -); default is generated"
    )
    parser.add_argument(
        "--region", default=DEFAULT_REGION, help=f"secret's region ({DEFAULT_REGION})"
    )
    parser.add_argument("--yes-prod", action="store_true", help="required to sign for prod")
    parser.add_argument("--secret-stdin", action="store_true", help="read the secret from stdin")
    parser.add_argument("--ledger", help=f"ledger file (else ${LEDGER_ENV}, else ~/.pyvar/...)")
    parser.add_argument("--no-ledger", action="store_true", help="do not record this token")
    parser.add_argument("--decode", metavar="TOKEN", help="print a token's claims (unverified)")
    return parser


def run_decode(token: str) -> int:
    claims = decode_unverified(token)
    now = int(time.time())
    expires = claims.get("exp")
    print(json.dumps(claims, indent=2, sort_keys=True))
    if isinstance(expires, int):
        state = (
            "EXPIRED" if expires <= now else f"valid for {(expires - now) / 3600:.1f} more hours"
        )
        print(f"expires {iso(expires)} ({state}); signature NOT checked", file=sys.stderr)
    else:
        print("no exp claim: this token would never expire", file=sys.stderr)
    return 0


def run_mint(args: argparse.Namespace) -> int:
    env = require_env(args.env, args.yes_prod)
    if not 0 < args.days <= MAX_DAYS:
        raise ToolError(f"--days must be above 0 and at most {MAX_DAYS:g}")
    now = int(time.time())
    sub = args.sub or default_sub(env, args.tier, now)
    if not SUB_PATTERN.match(sub):
        raise ToolError("--sub must be 3-64 characters of a-z, 0-9, '.', '_' or '-'")

    raw_secret = sys.stdin.read() if args.secret_stdin else read_secret_from_aws(env, args.region)
    secret = check_secret(raw_secret)
    ttl = int(args.days * 86400)
    jti = secrets.token_hex(8)
    token = sign_token(secret, sub=sub, tier=args.tier, ttl_seconds=ttl, now=now, jti=jti)

    if not args.no_ledger:
        append_ledger(
            ledger_path(args.ledger, LEDGER_ENV, LEDGER_NAME),
            {
                "event": "minted",
                "minted_at": iso(now),
                "minted_by": getpass.getuser(),
                "env": env,
                "sub": sub,
                "tier": args.tier,
                "expires_at": iso(now + ttl),
                "jti": jti,
                "fingerprint": fingerprint(token),
            },
        )
    sys.stdout.write(token + "\n")
    print(
        f"env={env} sub={sub} tier={args.tier} expires={iso(now + ttl)} "
        f"fingerprint={fingerprint(token)} jti={jti}",
        file=sys.stderr,
    )
    print(
        "The API cannot revoke a token before it expires; see scripts/revoke_internal_token.py.",
        file=sys.stderr,
    )
    if args.tier == "internal":
        print(
            "Tier internal bypasses every quota AND may call the service-only /internal routes "
            "(for example suppressing an e-mail address): keep it to Fibtec's own tools.",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Command entry point."""
    args = build_parser().parse_args(argv)
    try:
        # `is not None`: an empty token (a mint that failed, then decode "$TOKEN") must say
        # "not a JWT", not fall through to minting and complain about --env.
        return run_decode(args.decode) if args.decode is not None else run_mint(args)
    except ToolError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())

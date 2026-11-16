#!/usr/bin/env python3
"""scripts/mint_internal_token.py: sign a pyvar API token (default tier "internal") on demand.

Reasoning:
- A pyvar session token is an HS256 JWT signed with the environment's secret (Secrets Manager
  `pyvar/<env>/jwt-secret`), and the tier is a claim inside it (api/middleware/auth.py). Whoever
  can read that secret can sign a token of any tier; pyvar's own scheduled jobs do exactly this
  (pyvar-cdk/lambda/public_data_publisher/handler.py). This script is that recipe with guard rails
  for a person: the same claims, an expiry that is always present, and a record of what was issued.
- Tier "internal" is exempt from every rate limit and may run 500,000 simulations
  (api/middleware/rate_limit.py, auth.py). It is meant for Fibtec's own tools, tests and load
  runs. Do not hand one to a third party: it cannot be revoked and it is not tied to an account.
- A JWT cannot be revoked. Its expiry is the only limit, so the default is 1 day and the ceiling is
  90. Cancelling one early means rotating the secret, which signs every user out (API keys, the
  `pyvar_...` ones, are unaffected). See docs/internal-tokens-and-signing-secrets.md.
- The secret is read with the AWS CLI (nothing to install), travels through a pipe, never a
  command-line argument, and is never printed or written. The token goes to stdout alone; the
  summary goes to stderr, so `TOKEN=$(...)` captures just the token.
- The ledger (default ~/.pyvar/minted-tokens.jsonl, mode 0600) records who minted what and when it
  expires, with a short fingerprint of the token. It never holds the token or the secret.

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
import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENVS = ("dev", "prod")
TIERS = ("internal", "enterprise", "pro", "free")
DEFAULT_REGION = "eu-west-1"
DEFAULT_DAYS = 1.0
MAX_DAYS = 90.0
MIN_SECRET_LENGTH = 32
PUBLIC_DEFAULT_SECRET = "change-me-in-production"  # config.py's fallback; never a real secret
SUB_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
LEDGER_ENV = "PYVAR_TOKEN_LEDGER"


class MintError(Exception):
    """A refusal or failure with the exit code the command should end with."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


def b64url(raw: bytes) -> str:
    """Base64url without padding, as JWTs use."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    """Inverse of b64url."""
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_token(
    secret: str, *, sub: str, tier: str, ttl_seconds: int, now: int | None = None
) -> str:
    """Sign an HS256 JWT with `sub`, `tier`, `iat` and `exp`.

    Args:
        secret: The environment's signing secret.
        sub: Subject claim, a label that identifies the holder in logs and audit rows.
        tier: Tier claim (internal, enterprise, pro or free).
        ttl_seconds: Lifetime in seconds; always becomes an `exp` claim.
        now: Issue time as a Unix timestamp (defaults to the current time).

    Returns:
        The compact token string.
    """
    issued = int(time.time()) if now is None else now
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = {"sub": sub, "tier": tier, "iat": issued, "exp": issued + ttl_seconds}
    body = b64url(json.dumps(claims, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{b64url(signature)}"


def decode_unverified(token: str) -> dict[str, Any]:
    """Read a token's claims WITHOUT checking its signature.

    Raises:
        MintError: if the text is not a three-part JWT with a JSON object as payload.
    """
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise MintError("not a JWT: expected three dot-separated parts")
    try:
        claims = json.loads(b64url_decode(parts[1]))
    except (ValueError, UnicodeDecodeError) as exc:
        raise MintError("not a JWT: the payload is not valid JSON") from exc
    if not isinstance(claims, dict):
        raise MintError("not a JWT: the payload is not a JSON object")
    return claims


def fingerprint(token: str) -> str:
    """First 12 hex characters of the token's SHA-256: enough to tell tokens apart in the ledger."""
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def check_secret(secret: str) -> str:
    """Return the stripped secret, or refuse one that is empty, short or the public default.

    Raises:
        MintError: if the secret is unusable.
    """
    cleaned = secret.strip()
    if cleaned == PUBLIC_DEFAULT_SECRET:
        raise MintError("the secret is the public default; refusing to sign with it", 3)
    if len(cleaned) < MIN_SECRET_LENGTH:
        raise MintError(f"the secret is shorter than {MIN_SECRET_LENGTH} characters; refusing", 3)
    return cleaned


def read_secret_from_aws(env: str, region: str) -> str:
    """Read `pyvar/<env>/jwt-secret` with the AWS CLI; the value never appears in an argument.

    Raises:
        MintError: if the CLI is missing, the call fails or returns nothing.
    """
    command = [
        "aws",
        "secretsmanager",
        "get-secret-value",
        "--secret-id",
        f"pyvar/{env}/jwt-secret",
        "--region",
        region,
        "--query",
        "SecretString",
        "--output",
        "text",
    ]
    try:
        done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            command, capture_output=True, text=True, timeout=60, check=False
        )
    except FileNotFoundError as exc:
        raise MintError("the AWS CLI ('aws') is not installed or not on PATH", 3) from exc
    except subprocess.TimeoutExpired as exc:
        raise MintError("the AWS CLI did not answer within 60 s", 3) from exc
    if done.returncode != 0:
        reason = done.stderr.strip().splitlines()[-1:] or ["no message"]
        raise MintError(f"could not read the secret for {env}: {reason[0][:300]}", 3)
    return done.stdout


def default_sub(env: str, tier: str, now: int) -> str:
    """A label that is unique per run, e.g. internal-dev-20261116-3fa9."""
    stamp = datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%d")
    return f"{tier}-{env}-{stamp}-{secrets.token_hex(2)}"


def ledger_path(explicit: str | None) -> Path:
    """Where the ledger lives: --ledger, else $PYVAR_TOKEN_LEDGER, else ~/.pyvar/minted-tokens.jsonl."""
    chosen = explicit or os.environ.get(LEDGER_ENV)
    return Path(chosen) if chosen else Path.home() / ".pyvar" / "minted-tokens.jsonl"


def append_ledger(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON line; create the folder 0700 and the file 0600. Never holds a token."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def iso(timestamp: int) -> str:
    """UTC time as ISO 8601 with a trailing Z."""
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    if args.env is None:
        raise MintError("--env is required (dev or prod); there is no default")
    if not 0 < args.days <= MAX_DAYS:
        raise MintError(f"--days must be above 0 and at most {MAX_DAYS:g}")
    if args.env == "prod" and not args.yes_prod:
        raise MintError("signing for prod needs --yes-prod (this token will be accepted by prod)")
    now = int(time.time())
    sub = args.sub or default_sub(args.env, args.tier, now)
    if not SUB_PATTERN.match(sub):
        raise MintError("--sub must be 3-64 characters of a-z, 0-9, '.', '_' or '-'")

    raw_secret = (
        sys.stdin.read() if args.secret_stdin else read_secret_from_aws(args.env, args.region)
    )
    secret = check_secret(raw_secret)
    ttl = int(args.days * 86400)
    token = sign_token(secret, sub=sub, tier=args.tier, ttl_seconds=ttl, now=now)

    if not args.no_ledger:
        append_ledger(
            ledger_path(args.ledger),
            {
                "minted_at": iso(now),
                "minted_by": getpass.getuser(),
                "env": args.env,
                "sub": sub,
                "tier": args.tier,
                "expires_at": iso(now + ttl),
                "fingerprint": fingerprint(token),
            },
        )
    sys.stdout.write(token + "\n")
    print(
        f"env={args.env} sub={sub} tier={args.tier} expires={iso(now + ttl)} "
        f"fingerprint={fingerprint(token)}",
        file=sys.stderr,
    )
    print(
        "A token cannot be revoked before it expires (only rotating the secret cancels it).",
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
    except MintError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())

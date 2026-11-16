#!/usr/bin/env python3
"""scripts/revoke_internal_token.py: what is outstanding, and the way to cancel internal tokens.

Reasoning:
- A token signed by scripts/mint_internal_token.py is a JWT, and the API has no revocation list for
  JWTs: it checks the signature and the expiry and nothing else (api/middleware/auth.py). So there is
  no command that can switch one token off. This script says that plainly instead of pretending:
  `revoke` records the decision in the ledger and exits 4, "recorded, NOT enforced", whenever any
  matching token is still valid, so a script that calls it can never mistake it for a real cancel.
- The real controls are the short expiry chosen at minting, and, in an emergency, rotating the
  environment's signing secret, which cancels EVERY token signed with the old value (user sessions
  too). `runbook` prints that procedure with this project's real names. It is printed, not run: it
  changes a shared secret and restarts the API, which belongs in a person's hands.
- `list` shows what the ledger believes is outstanding and how long the worst case lasts. The ledger
  is the operator's own record on one machine; it is not the API's view and cannot see tokens that
  were signed another way (for example by the W4/W5 agent).
- When a revocation list exists in the API (docs/internal-tokens-and-signing-secrets.md, section 5),
  this script is where the call to it goes; each token already carries a unique `jti` for that.

Usage (repo root):
    python scripts/revoke_internal_token.py list                       # outstanding tokens
    python scripts/revoke_internal_token.py list --env prod --all      # include expired and revoked
    python scripts/revoke_internal_token.py revoke --fingerprint 6b3f7f   # record; exit 4 if still valid
    python scripts/revoke_internal_token.py revoke --sub load-test-nov --reason "test finished"
    python scripts/revoke_internal_token.py revoke --all-outstanding --env dev
    python scripts/revoke_internal_token.py runbook --env dev          # the emergency procedure

Exit codes: 0 done and nothing was still valid; 2 refused or nothing matched; 4 recorded, but the
API still accepts the matched token(s) until they expire.
"""

from __future__ import annotations

import argparse
import getpass
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from token_tools import (  # noqa: E402
    DEFAULT_REGION,
    ENVS,
    LEDGER_ENV,
    ToolError,
    append_ledger,
    iso,
    ledger_path,
    parse_iso,
    read_ledger,
)

LEDGER_NAME = "minted-tokens.jsonl"
MIN_PREFIX = 6


def classify(records: list[dict[str, Any]], now: int) -> list[dict[str, Any]]:
    """The minted tokens in a ledger, each with a `status`: outstanding, expired or revoked.

    "revoked" means a revocation was RECORDED, which the API does not enforce. A token that is both
    recorded as revoked and past its expiry shows as expired (nothing is left to cancel).
    """
    revoked: set[str] = set()
    for record in records:
        if record.get("event") == "revoked" and record.get("fingerprint"):
            revoked.add(str(record["fingerprint"]))
    tokens: list[dict[str, Any]] = []
    for record in records:
        if record.get("event", "minted") != "minted" or not record.get("fingerprint"):
            continue
        try:
            expires = parse_iso(str(record["expires_at"]))
        except (KeyError, ValueError):
            continue
        status = "expired" if expires <= now else "outstanding"
        if status == "outstanding" and str(record["fingerprint"]) in revoked:
            status = "revoked"
        tokens.append({**record, "status": status, "expires_ts": expires})
    return tokens


def show(tokens: list[dict[str, Any]]) -> None:
    """Print tokens as a table on stdout."""
    if not tokens:
        print("(none)")
        return
    print(f"{'STATUS':<12} {'ENV':<5} {'TIER':<10} {'EXPIRES':<21} {'FINGERPRINT':<13} SUB")
    for token in sorted(tokens, key=lambda item: item["expires_ts"]):
        print(
            f"{token['status']:<12} {str(token.get('env', '?')):<5} "
            f"{str(token.get('tier', '?')):<10} {token['expires_at']:<21} "
            f"{token['fingerprint']:<13} {token.get('sub', '?')}"
        )


def rotation_runbook(env: str, region: str = DEFAULT_REGION) -> str:
    """The emergency procedure that really cancels every token signed with the environment's secret.

    Returns plain text for a person to read; nothing in it is executed here.
    """
    store_entry = f"pyvar/{env}/jwt-secret"  # the NAME of a Secrets Manager entry, not its value
    cluster, service = f"pyvar-{env}", f"pyvar-{env}-api"
    generate = (
        'python3 -c \'import secrets,string;print("".join(secrets.choice('
        'string.ascii_letters+string.digits) for _ in range(64)),end="")\''
    )
    return f"""EMERGENCY RUNBOOK: cancel every token signed with the {env} secret
Not rehearsed on pyvar yet: do it on dev first, and read each step before running it.

What it does: every session token and every internal token minted with the old secret stops working
(users sign in again). API keys (pyvar_...) are not affected. Between steps 2 and 3 the API still
holds the old secret and the Lambdas read the new one, so the demo publisher and the other scheduled
jobs may fail once; do it in a quiet period.

1. See what is outstanding:
     python scripts/revoke_internal_token.py list --env {env}

2. Put a new 64-character secret in place (generated here, never shown; no trailing newline):
     {generate} \\
       | aws secretsmanager put-secret-value --secret-id {store_entry} --region {region} \\
           --secret-string file:///dev/stdin

3. Make the API read it (the containers take the secret when they start):
     aws ecs update-service --cluster {cluster} --service {service} --force-new-deployment --region {region}
     aws ecs wait services-stable --cluster {cluster} --services {service} --region {region}

4. Check it. An old token must now answer 401 and a freshly minted one must not:
     TOKEN=$(python scripts/mint_internal_token.py --env {env} --days 0.01)
     (call an endpoint that needs a session, for example GET /api/v1/auth/api-keys, with the old
      and the new token: old -> 401; new -> anything but 401, it may be 403 or 404 because its sub
      is a label and not an account)

5. Record it:
     python scripts/revoke_internal_token.py revoke --all-outstanding --env {env} --reason "secret rotated"
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List internal tokens, record a revocation, or print the cancel procedure.",
        epilog="The API cannot revoke a JWT; `revoke` records and exits 4 while a token is valid.",
    )
    parser.add_argument("--ledger", help=f"ledger file (else ${LEDGER_ENV}, else ~/.pyvar/...)")
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="tokens in the ledger")
    listing.add_argument("--env", choices=ENVS)
    listing.add_argument("--all", action="store_true", help="include expired and revoked")

    revoke = commands.add_parser("revoke", help="record a revocation (not enforced by the API)")
    which = revoke.add_mutually_exclusive_group(required=True)
    which.add_argument("--fingerprint", help=f"fingerprint or its first {MIN_PREFIX}+ characters")
    which.add_argument("--jti", help=f"token id or its first {MIN_PREFIX}+ characters")
    which.add_argument("--sub", help="every token minted with this label")
    which.add_argument("--all-outstanding", action="store_true", help="every outstanding token")
    revoke.add_argument("--env", choices=ENVS, help="required with --all-outstanding")
    revoke.add_argument("--reason", default="", help="why (kept in the ledger)")

    runbook = commands.add_parser("runbook", help="print the emergency rotation procedure")
    runbook.add_argument("--env", choices=ENVS, required=True)
    runbook.add_argument("--region", default=DEFAULT_REGION)
    return parser


def select(tokens: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    """The tokens a `revoke` names.

    Raises:
        ToolError: if a prefix is too short or ambiguous, --all-outstanding has no --env, or
            nothing matches.
    """
    if args.all_outstanding:
        if args.env is None:
            raise ToolError("--all-outstanding needs --env (dev or prod)")
        chosen = [t for t in tokens if t.get("env") == args.env]
    elif args.sub:
        chosen = [t for t in tokens if t.get("sub") == args.sub]
    else:
        field, value = ("fingerprint", args.fingerprint) if args.fingerprint else ("jti", args.jti)
        if len(value) < MIN_PREFIX:
            raise ToolError(f"give at least {MIN_PREFIX} characters of the {field}")
        chosen = [t for t in tokens if str(t.get(field, "")).startswith(value)]
        if len({t["fingerprint"] for t in chosen}) > 1:
            raise ToolError(f"that {field} prefix matches several tokens; give more characters")
    if not chosen:
        raise ToolError("no matching token in the ledger")
    return chosen


def run_list(args: argparse.Namespace, path: Path) -> int:
    records, skipped = read_ledger(path)
    now = int(time.time())
    tokens = classify(records, now)
    if args.env:
        tokens = [t for t in tokens if t.get("env") == args.env]
    shown = tokens if args.all else [t for t in tokens if t["status"] == "outstanding"]
    show(shown)
    outstanding = [t for t in tokens if t["status"] == "outstanding"]
    recorded = [t for t in tokens if t["status"] == "revoked"]
    print(
        f"{len(outstanding)} outstanding, {len(recorded)} recorded as revoked but still valid "
        f"(not enforced), {len(tokens) - len(outstanding) - len(recorded)} expired.",
        file=sys.stderr,
    )
    live = outstanding + recorded
    if live:
        latest = max(t["expires_ts"] for t in live)
        print(f"The last of them stops working at {iso(latest)}.", file=sys.stderr)
    if skipped:
        print(f"{skipped} unreadable ledger line(s) skipped.", file=sys.stderr)
    return 0


def run_revoke(args: argparse.Namespace, path: Path) -> int:
    records, _ = read_ledger(path)
    now = int(time.time())
    chosen = select(classify(records, now), args)
    still_valid = [t for t in chosen if t["status"] in ("outstanding", "revoked")]
    new = [t for t in chosen if t["status"] == "outstanding"]
    for token in new:
        append_ledger(
            path,
            {
                "event": "revoked",
                "revoked_at": iso(now),
                "revoked_by": getpass.getuser(),
                "env": token.get("env"),
                "sub": token.get("sub"),
                "fingerprint": token["fingerprint"],
                "jti": token.get("jti"),
                "reason": args.reason,
            },
        )
    show(chosen)
    if not still_valid:
        print("Nothing to do: every matching token has already expired.", file=sys.stderr)
        return 0
    envs = sorted({str(t.get("env")) for t in still_valid})
    latest = max(t["expires_ts"] for t in still_valid)
    print(
        f"RECORDED, NOT ENFORCED: {len(new)} new revocation(s) written to the ledger. The API has no "
        f"revocation list, so {len(still_valid)} token(s) still work until {iso(latest)}.\n"
        f"To cancel them now, rotate the secret: python scripts/revoke_internal_token.py runbook "
        f"--env {envs[0]}",
        file=sys.stderr,
    )
    return 4


def main(argv: list[str] | None = None) -> int:
    """Command entry point."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "runbook":
            sys.stdout.write(rotation_runbook(args.env, args.region))
            return 0
        path = ledger_path(args.ledger, LEDGER_ENV, LEDGER_NAME)
        return run_list(args, path) if args.command == "list" else run_revoke(args, path)
    except ToolError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())

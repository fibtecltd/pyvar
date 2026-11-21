#!/usr/bin/env python3
"""scripts/audit_cleanup.py: delete audit rows that reached six years (docs/plan-education-tier.md section 12).

Reasoning:
- The privacy policy promises that job records (`var_jobs`) and tier-change records (`billing_events`) are kept six
  years from their date and then deleted. CLAUDE.md 3.3 makes both tables append-only audit logs that only a
  clean-up job may delete from, and only rows older than six years. This is that job. It is run by the owner (the
  yearly review in docs/plan-education-tier.md section 12; the first rows reach six years in late 2032), not by a
  timer: a deletion nobody watches is the wrong default for an audit log.
- Like scripts/education_grant.py it signs a 10-minute ADMIN token (audience "pyvar-admin", no tier) with the
  environment's secret, read from AWS Secrets Manager by the AWS CLI, and calls /internal/admin/audit/cleanup. No
  database access; no other credential can call the route.
- THE PERIOD CANNOT BE CHANGED HERE. There is no `--years` option and the API takes none: six years is a constant
  in api/audit_retention.py, pinned to the privacy page. A mistyped argument therefore cannot delete a record the
  policy promises to keep. It never deletes `users`, `api_keys` or any other table.
- DRY RUN BY DEFAULT: without `--yes` it only counts. With `--yes` it deletes in rounds of `--max-rows` per table
  (default 20000, each round committed in small batches, oldest first) until nothing older than the cutoff remains,
  then asks the API again and exits 5 unless the count is zero: it does what it says. A round that deletes nothing
  while rows remain stops it (exit 5) instead of looping.
- Nothing about a person is read or written: counts, the cutoff and the operator's label only. The ledger (default
  ~/.pyvar/audit-cleanups.jsonl, 0600) holds time, operator, environment, cutoff, how many rows went from each
  table. No secret or token is ever written or printed.

Usage (repo root):
    python scripts/audit_cleanup.py --env prod --yes-prod              # dry run: what is older than six years
    python scripts/audit_cleanup.py --env prod --yes-prod --yes        # delete it

Exit codes: 0 done (and confirmed), nothing to do, or dry run shown; 2 refused by a guard or bad arguments; 3 the
secret could not be read; 5 the API refused, could not be reached, or the deletion could not be confirmed.
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
LEDGER_ENV = "PYVAR_AUDIT_CLEANUP_LEDGER"
LEDGER_NAME = "audit-cleanups.jsonl"
ROUTE = "/api/v1/internal/admin/audit/cleanup"
TABLES = ("var_jobs", "billing_events")
DEFAULT_MAX_ROWS = 20000
MAX_ROUNDS = (
    1000  # 1000 rounds of up to 200000 rows per table: far more than the service will ever hold
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete var_jobs and billing_events rows older than six years (the period is fixed)."
    )
    parser.add_argument("--env", choices=ENVS, help="which environment's API to call")
    parser.add_argument("--yes-prod", action="store_true", help="required for prod")
    parser.add_argument("--yes", action="store_true", help="delete (otherwise a dry run)")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=DEFAULT_MAX_ROWS,
        help=f"rows per table per round, 1 to 200000 (default {DEFAULT_MAX_ROWS})",
    )
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
        404: "the API has no such route: it is not the new version",
        422: "the API rejected the request as invalid",
    }
    detail = data.get("detail") if isinstance(data, dict) else None
    text = detail if isinstance(detail, str) else reasons.get(status, "unexpected answer")
    return ToolError(f"{action}: HTTP {status}: {text}", 5)


def _found(data: dict[str, Any]) -> dict[str, int]:
    return {table: int(data[table]["found"]) for table in TABLES}


def _describe(found: dict[str, int]) -> str:
    return ", ".join(f"{table} {found[table]}" for table in TABLES)


def run(args: argparse.Namespace, out: TextIO) -> int:
    env = require_env(args.env, args.yes_prod)
    if not 1 <= args.max_rows <= 200000:
        raise ToolError("--max-rows must be between 1 and 200000")
    base = base_url_for(env, args.base_url)
    token = _admin_token(args, env)
    url = f"{base}{ROUTE}"

    status, data = _post(url, token, {"apply": False})
    if status != 200:
        raise _refusal(status, data, "audit clean-up (dry run)")
    cutoff = str(data["cutoff"])
    found = _found(data)
    if not any(found.values()):
        print(f"nothing to delete: no row is older than {cutoff[:10]} (six years).", file=out)
        return 0
    summary = f"rows older than {cutoff[:10]} (six years): {_describe(found)}"
    if not args.yes:
        print(f"dry run: {summary}. Add --yes to delete them.", file=out)
        return 0

    deleted = {table: 0 for table in TABLES}
    rounds = 0
    while True:
        status, data = _post(url, token, {"apply": True, "max_rows": args.max_rows})
        if status != 200 or not data.get("applied"):
            raise _refusal(status, data, "audit clean-up")
        done = {table: int(data[table]["deleted"]) for table in TABLES}
        for table in TABLES:
            deleted[table] += done[table]
        rounds += 1
        remaining = {table: int(data[table]["remaining"]) for table in TABLES}
        if not any(remaining.values()):
            break
        if not any(done.values()):
            raise ToolError("rows are left but a round deleted none: stopped", 5)
        if rounds >= MAX_ROUNDS:
            raise ToolError(f"stopped after {MAX_ROUNDS} rounds; run it again", 5)
        print(f"round {rounds}: left {_describe(remaining)}", file=out)

    status, data = _post(url, token, {"apply": False})
    if status != 200 or any(_found(data).values()):
        raise ToolError(
            "asked to delete the rows but the API still counts some older than the cutoff: run it again",
            5,
        )
    append_ledger(
        ledger_path(args.ledger, LEDGER_ENV, LEDGER_NAME),
        {
            "at": iso(int(time.time())),
            "by": args.operator,
            "env": env,
            "action": "audit_cleanup",
            "cutoff": cutoff,
            "rounds": rounds,
            **{f"{table}_deleted": deleted[table] for table in TABLES},
        },
    )
    print(
        f"deleted rows older than {cutoff[:10]} in {rounds} round(s): {_describe(deleted)}; "
        "confirmed by the API (none left older than the cutoff)",
        file=out,
    )
    print(
        "Still to do by hand: one line in the requests/routines log (date, what was deleted).",
        file=out,
    )
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

#!/usr/bin/env python3
"""scripts/account_export.py: a copy of the data we hold about one account (docs/plan-education-tier.md section 12).

Reasoning:
- The privacy policy tells people they can ask for a copy of what we hold about them (UK GDPR Article 15; Article 20
  asks for a commonly used, machine-readable form). There is no button, so this is the command. Like
  scripts/account_erase.py it signs a 10-minute ADMIN token (audience "pyvar-admin", no tier) with the
  environment's secret, read from AWS Secrets Manager by the AWS CLI, and calls /internal/admin/accounts/export,
  one page of one section at a time. No database access; no other credential can call the route.
- It READS only: nothing on the server changes, so there is no `--yes`. It writes ONE JSON file, at the path given
  with `--out`: the account row, its API keys, its tier-change records and its computation records, plus a
  `not_included` list saying what the copy does not cover (mailbox, Stripe, logs, result files, credentials).
  Sign-in tokens and key digests are never in it (api/account_export.py).
- The file holds the person's data, so: it is created 0600 and never overwritten (an existing path is refused
  before any call is made), it is written section by section as pages arrive (a heavy user's thousands of jobs are
  not held in memory), and a half-written file is deleted if anything fails. It is checked at the end: the rows
  written for each section must equal the total the API reports, otherwise the file is deleted and the command
  exits 5 (the account changed while it ran; run it again).
- The address is never printed or written anywhere but inside that file's `account` section, where it is the
  person's own data. Not to stdout, not to the ledger (default ~/.pyvar/exports.jsonl, 0600: time, operator,
  environment, account identifier, row counts). No secret or token is ever written or printed.
- It cannot send the file. What is left is said at the end: reply within one month (UK GDPR Article 12(3)), send the
  file to the address on record, add the mailbox messages and Stripe's record by hand, delete the file, log one line.

Usage (repo root):
    python scripts/account_export.py --env prod --yes-prod --email a@uni.ac.uk --out ~/exports/ada-2026-11-21.json

Exit codes: 0 done; 2 refused by a guard or bad arguments; 3 the secret could not be read; 5 the API refused, could
not be reached, or the copy could not be confirmed complete.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
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
LEDGER_ENV = "PYVAR_EXPORT_LEDGER"
LEDGER_NAME = "exports.jsonl"
ROUTE = "/api/v1/internal/admin/accounts/export"
ROW_SECTIONS = ("api_keys", "billing_events", "var_jobs")
DEFAULT_PAGE_SIZE = 500
MAX_PAGES = 100000  # 500 rows each: a guard against a server that never says "last page"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write a JSON copy of the data held about one pyvar account (data-access request)."
    )
    parser.add_argument("--env", choices=ENVS, help="which environment's API to call")
    parser.add_argument("--yes-prod", action="store_true", help="required for prod")
    parser.add_argument("--email", required=True, help="the account's e-mail address")
    parser.add_argument("--out", required=True, help="the file to create (must not exist)")
    parser.add_argument(
        "--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="rows per request, 1 to 1000"
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
        404: "no account has this address (or it was erased)",
        422: "the API rejected the request as invalid",
    }
    detail = data.get("detail") if isinstance(data, dict) else None
    text = detail if isinstance(detail, str) else reasons.get(status, "unexpected answer")
    return ToolError(f"{action}: HTTP {status}: {text}", 5)


def _write_section(
    handle: TextIO, url: str, token: str, email: str, section: str, page_size: int
) -> int:
    """Page through one section, writing its rows as a JSON array; return how many were written."""
    handle.write(f',\n  "{section}": [')
    written = 0
    offset = 0
    total = 0
    for _ in range(MAX_PAGES):
        status, data = _post(
            url, token, {"email": email, "section": section, "offset": offset, "limit": page_size}
        )
        if status != 200:
            raise _refusal(status, data, f"export ({section})")
        total = int(data["total"])
        for row in data["rows"]:
            handle.write(("," if written else "") + "\n    " + json.dumps(row, sort_keys=True))
            written += 1
        following = data["next_offset"]
        if following is None:
            break
        if int(following) <= offset:
            raise ToolError(f"export ({section}): the API did not advance", 5)
        offset = int(following)
    else:
        raise ToolError(f"export ({section}): too many pages", 5)
    handle.write("\n  ]" if written else "]")
    if written != total:
        raise ToolError(
            f"export ({section}): wrote {written} rows but the API counts {total}: "
            "the account changed while this ran; run it again",
            5,
        )
    return written


def run(args: argparse.Namespace, out: TextIO) -> int:
    env = require_env(args.env, args.yes_prod)
    if not 1 <= args.page_size <= 1000:
        raise ToolError("--page-size must be between 1 and 1000")
    path = Path(args.out).expanduser()
    if path.exists():
        raise ToolError(f"{path} already exists: choose a new file name (it is never overwritten)")
    if not path.parent.is_dir():
        raise ToolError(f"{path.parent} is not a folder")
    base = base_url_for(env, args.base_url)
    token = _admin_token(args, env)
    url = f"{base}{ROUTE}"
    email = args.email.strip().lower()

    status, data = _post(url, token, {"email": email, "section": "account"})
    if status != 200:
        raise _refusal(status, data, "export (account)")
    account_id = str(data["account_id"])

    counts = {"account": 1}
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("{\n")
            handle.write(f'  "generated_at": {json.dumps(iso(int(time.time())))},\n')
            handle.write(f'  "environment": {json.dumps(env)},\n')
            handle.write(f'  "account_id": {json.dumps(account_id)},\n')
            handle.write(f'  "not_included": {json.dumps(data["not_included"], indent=2)},\n')
            handle.write(f'  "account": {json.dumps(data["rows"][0], sort_keys=True)}')
            for section in ROW_SECTIONS:
                counts[section] = _write_section(handle, url, token, email, section, args.page_size)
            handle.write("\n}\n")
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    append_ledger(
        ledger_path(args.ledger, LEDGER_ENV, LEDGER_NAME),
        {
            "at": iso(int(time.time())),
            "by": args.operator,
            "env": env,
            "action": "export",
            "account": account_id,
            **{f"{name}_rows": number for name, number in counts.items()},
        },
    )
    print(
        f"wrote {path} (owner-only, 0600) for account {account_id}: "
        + ", ".join(f"{name} {number}" for name, number in counts.items()),
        file=out,
    )
    print("Still to do by hand:", file=out)
    print("  - reply within one month of the request (UK GDPR Article 12(3))", file=out)
    print(
        "  - add what the file does not hold: the person's messages in the company mailbox and, if "
        "linked, Stripe's customer record (the file's not_included list says what else)",
        file=out,
    )
    print("  - send the file to the address on record, then delete it", file=out)
    print("  - the requests log: one line (date, type, date answered, what was sent)", file=out)
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

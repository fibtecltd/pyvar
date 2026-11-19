#!/usr/bin/env python3
"""scripts/education_grant.py: give, extend, end and list education access (docs/plan-education-tier.md).

Reasoning:
- There is no portal form. A teacher or student e-mails from an institutional address; the owner opens the
  institution's staff or course page in their own browser and, if satisfied, runs `grant`. The command signs a
  10-minute ADMIN token (audience "pyvar-admin", no tier) with the environment's signing secret, read from AWS
  Secrets Manager by the AWS CLI as in scripts/mint_internal_token.py, and calls the API's
  /internal/admin/education/* routes. The routes refuse every other kind of token, so a session JWT, an
  "internal" JWT or an API key cannot do this, and an admin token cannot do anything else.
- The API enforces the rules (a verified FREE account only, a cohort of 25 and 10 per e-mail domain, 1 to 12
  months, the feature flag); this command only asks, and prints the answer. A refusal exits 5 with the API's
  reason. After a `grant` or `extend` it lists the accounts again and checks the account is there with the date
  it was told, and exits 5 if not: it does what it says.
- Nothing an applicant wrote is stored: the account is found by its e-mail address, and the one free-form
  value that reaches the audit row is `--cohort`, a short token you choose ("ucl-risk-2026").
- `suspend-all` is the kill switch: every active grant ends now. It needs `--yes-all`. It works with the
  feature flag off, like `revoke` and `list`.
- A ledger line (default ~/.pyvar/education.jsonl, 0600) records each change: who ran it, when, which
  environment, the e-mail address, the action and the cohort. It is a convenience for the operator; the API's
  `billing_events` table is the record. No secret or token is ever written or printed.

Usage (repo root):
    python scripts/education_grant.py grant  --env dev --email a@uni.ac.uk --months 6 --cohort ucl-risk-2026
    python scripts/education_grant.py grant  --env prod --yes-prod --email a@uni.ac.uk --cohort mfe-2026 --allow-domain-over-cap
    python scripts/education_grant.py extend --env prod --yes-prod --email a@uni.ac.uk --months 6 --cohort ucl-risk-2026
    python scripts/education_grant.py revoke --env prod --yes-prod --email a@uni.ac.uk --cohort ucl-risk-2026
    python scripts/education_grant.py list   --env prod --yes-prod
    python scripts/education_grant.py suspend-all --env prod --yes-prod --yes-all

Exit codes: 0 done (and confirmed, for grant and extend); 2 refused by a guard or bad arguments; 3 the secret
could not be read; 5 the API refused, could not be reached, or the change could not be confirmed.
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
LEDGER_ENV = "PYVAR_EDUCATION_LEDGER"
LEDGER_NAME = "education.jsonl"
ROUTE = "/api/v1/internal/admin/education"
MAX_MONTHS = 12


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage pyvar education access.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("grant", "give a verified free account education access"),
        ("extend", "move an education account's end date out"),
        ("revoke", "end an education account's access now"),
        ("list", "every education account"),
        ("suspend-all", "end every active grant now (the kill switch)"),
    ):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--env", choices=ENVS, help="which environment's API to call")
        sub.add_argument("--yes-prod", action="store_true", help="required for prod")
        sub.add_argument(
            "--operator", default=getpass.getuser(), help="your label (the token's sub)"
        )
        sub.add_argument("--region", default=DEFAULT_REGION, help="the secret's region")
        sub.add_argument("--secret-stdin", action="store_true", help="read the secret from stdin")
        sub.add_argument("--base-url", help="loopback only, for tests")
        sub.add_argument("--ledger", help=f"ledger file (else ${LEDGER_ENV}, else ~/.pyvar/...)")
        if name in ("grant", "extend", "revoke"):
            sub.add_argument("--email", required=True, help="the account's e-mail address")
            sub.add_argument(
                "--cohort",
                required=True,
                help="a short label for the audit row, e.g. ucl-risk-2026",
            )
        if name in ("grant", "extend"):
            sub.add_argument("--months", type=int, default=6, help=f"1 to {MAX_MONTHS} (default 6)")
            sub.add_argument(
                "--allow-domain-over-cap",
                action="store_true",
                help="lift the per-domain cap for a class (never the cohort cap)",
            )
        if name == "suspend-all":
            sub.add_argument("--yes-all", action="store_true", help="confirms ending every grant")
    return parser


def _admin_token(args: argparse.Namespace, env: str) -> str:
    if not ACCOUNT_ID_PATTERN.match(args.operator):
        raise ToolError("--operator must be 3-128 characters of letters, digits and . _ : @ -")
    raw = sys.stdin.read() if args.secret_stdin else read_secret_from_aws(env, args.region)
    secret = check_secret(raw)
    return sign_admin_token(
        secret,
        operator=args.operator,
        audience=ADMIN_AUDIENCE,
        ttl_seconds=ADMIN_TTL_SECONDS,
    )


def _explain(status: int, data: Any, action: str) -> ToolError:
    """The API's own reason, in one line, for a refusal."""
    reasons = {
        401: "the admin token was refused: wrong environment's secret, or this API is not the new version",
        404: "no such account or route",
        409: "refused by a rule",
        422: "the API rejected the request as invalid",
        503: "the education tier is switched off in this environment",
    }
    detail = data.get("detail") if isinstance(data, dict) else None
    text = detail if isinstance(detail, str) else reasons.get(status, "unexpected answer")
    return ToolError(f"{action}: HTTP {status}: {text}", 5)


def _call(method: str, url: str, token: str, body: dict[str, Any] | None, action: str) -> Any:
    status, data = api_request(method, url, token, body)
    if status != 200:
        raise _explain(status, data, action)
    return data


def _show(data: dict[str, Any], out: TextIO) -> None:
    accounts = data.get("accounts", [])
    print(
        f"active {data.get('active')} of {data.get('cohort_cap')} "
        f"(at most {data.get('domain_cap')} per domain); the tier is "
        f"{'ON' if data.get('enabled') else 'OFF'} in this environment",
        file=out,
    )
    if not accounts:
        print("(none)", file=out)
        return
    print(f"{'STATE':<8} {'EXPIRES':<21} {'COHORT':<24} EMAIL", file=out)
    for account in accounts:
        state = "active" if account.get("active") else "ended"
        print(
            f"{state:<8} {str(account.get('expires_at') or '-')[:19]:<21} "
            f"{str(account.get('cohort') or '-')[:24]:<24} {account.get('email')}",
            file=out,
        )


def run(args: argparse.Namespace, out: TextIO) -> int:
    env = require_env(args.env, args.yes_prod)
    if args.command == "suspend-all" and not args.yes_all:
        raise ToolError("suspend-all ends every active grant: add --yes-all")
    if args.command in ("grant", "extend") and not 1 <= args.months <= MAX_MONTHS:
        raise ToolError(f"--months must be between 1 and {MAX_MONTHS}")
    base = base_url_for(env, args.base_url)
    token = _admin_token(args, env)
    url = f"{base}{ROUTE}"
    ledger = ledger_path(args.ledger, LEDGER_ENV, LEDGER_NAME)
    record = {
        "at": iso(int(time.time())),
        "by": args.operator,
        "env": env,
        "action": args.command,
    }

    if args.command == "list":
        _show(_call("GET", f"{url}/list", token, None, "listing"), out)
        return 0

    if args.command == "suspend-all":
        data = _call("POST", f"{url}/suspend-all", token, {}, "suspend-all")
        append_ledger(ledger, {**record, "suspended": data.get("suspended")})
        print(
            f"ended {data.get('suspended')} active grant(s); their keys keep working at the Free limits",
            file=out,
        )
        return 0

    email = args.email.strip().lower()
    if args.command == "revoke":
        _call("POST", f"{url}/revoke", token, {"email": email, "cohort": args.cohort}, "revoke")
        append_ledger(ledger, {**record, "email": email, "cohort": args.cohort})
        print(f"{email}: back on the Free tier", file=out)
        return 0

    body = {
        "email": email,
        "months": args.months,
        "cohort": args.cohort,
        "allow_domain_over_cap": bool(args.allow_domain_over_cap),
    }
    data = _call("POST", f"{url}/{args.command}", token, body, args.command)
    expires = data.get("expires_at")
    listing = _call("GET", f"{url}/list", token, None, "confirming")
    found = next((a for a in listing.get("accounts", []) if a.get("email") == email), None)
    if not found or not found.get("active") or found.get("expires_at") != expires:
        raise ToolError(f"asked to {args.command} {email} but could not confirm it in the list", 5)
    append_ledger(
        ledger,
        {
            **record,
            "email": email,
            "cohort": args.cohort,
            "months": args.months,
            "expires": expires,
        },
    )
    print(f"{email}: education access until {str(expires)[:10]}, confirmed by the API", file=out)
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

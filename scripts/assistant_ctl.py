#!/usr/bin/env python3
"""scripts/assistant_ctl.py: the operator's switches for the typed assistant's kill switch and spend counter.

Reasoning:
- The typed route's two emergency controls live in Redis, not in a deploy (api/assistant/store.py): the kill switch
  `pyvar:assistant:kill` (any value turns the route off at once, on every API task) and today's spend in millionths
  of a dollar `pyvar:assistant:spend:<UTC date>` (the circuit breaker that stops the route at the daily cap). Until
  now the only way to touch them was a Redis client inside the VPC. This script is that client, with the same
  keys the application reads and nothing else: it never touches the allowlist (scripts/assistant_allow.py), the
  watchdog's keys or any other key.
- It talks to the same cache the API uses (storage/redis_client.py::redis_url()), so it must run where the API's
  environment is: an ECS one-off of the API task definition, as scripts/trial_ctl.py does (ECS Exec is not
  enabled, and the image carries scripts/ because the Dockerfile copies the repository). The one-off's default
  command is the migration, so the command is overridden:

      aws ecs run-task --cluster pyvar-<env> --launch-type FARGATE --task-definition <the pyvar-<env>-api family> \\
        --network-configuration <copied from the pyvar-<env>-api service> \\
        --overrides '{"containerOverrides":[{"name":"<the api container>","command":
                      ["python","scripts/assistant_ctl.py","status"]}]}'

  then read the task's log lines (the same log group as the API's) and its exit code. `--redis-url` overrides the
  address (redis-py spelling: `ssl_cert_reqs=none`, not `CERT_NONE`). The script's working directory is put on
  sys.path, so `python scripts/assistant_ctl.py` works from the image's working directory.
- Stopping is always one command and never asks anything: `kill on`. Anything that can let the route spend more
  than it was allowed to (`kill off`, `spend set`, `spend clear`) is a DRY RUN unless `--yes`, and in a deployed
  prod environment also needs `--yes-prod`. `spend set` exists for drills and for putting a counter back after one
  (docs/assistant-dev-run-prompt.txt): it takes dollars or exact millionths, and `status --json` prints the exact
  millionths, so a value read before a drill can be restored exactly.
- Nothing visitor-written is in these keys: a flag, one integer per day. The output names the environment
  (APP_ENV) and numbers, never the cache address, a key's value or a secret.

Usage (inside the one-off, from the repo root):
    python scripts/assistant_ctl.py status [--json]
    python scripts/assistant_ctl.py kill on                    # the route answers 503 assistant_disabled at once
    python scripts/assistant_ctl.py kill off --yes             # back on (prod: add --yes-prod)
    python scripts/assistant_ctl.py spend set --usd 50 --yes   # drill: over the cap (prod: add --yes-prod)
    python scripts/assistant_ctl.py spend set --micro 1234567 --yes
    python scripts/assistant_ctl.py spend clear --yes

Exit codes: 0 done; 2 a usage error or a guard refused; 3 the cache could not be reached.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.assistant.store import (  # noqa: E402
    ALLOW_KEY,
    KILL_KEY,
    MICRO,
    SPEND_TTL_SECONDS,
    spend_key,
)
from config import get_settings  # noqa: E402

PROD_NAMES = ("prod", "production")
MAX_USD = 1_000_000  # a typo guard, far above any real cap


def _client(url: str | None) -> Any:
    import redis

    from storage.redis_client import redis_url

    return redis.from_url(url or redis_url(), decode_responses=True, socket_timeout=5)


def _now(now: dt.datetime | None) -> dt.datetime:
    return now or dt.datetime.now(dt.timezone.utc)


def read_status(client: Any, now: dt.datetime | None = None) -> dict[str, Any]:
    """The kill switch, today's spend and the allowlist's size, as one dict."""
    moment = _now(now)
    cfg = get_settings()
    raw = client.get(spend_key(moment))
    micro = int(raw) if raw else 0
    budget = float(cfg.assistant_daily_budget_usd)
    return {
        "environment": cfg.app_env,
        "date_utc": moment.astimezone(dt.timezone.utc).date().isoformat(),
        "kill_switch": client.get(KILL_KEY) is not None,
        "spend_micro_usd": micro,
        "spend_usd": micro / MICRO,
        "daily_budget_usd": budget,
        "spend_ratio": round(micro / MICRO / budget, 4) if budget > 0 else None,
        "allowlist_members": int(client.scard(ALLOW_KEY)),
        "settings_of_this_task": {
            "assistant_enabled": bool(cfg.assistant_enabled),
            "typed_enabled": bool(cfg.assistant_typed_enabled),
            "watchdog_enabled": bool(cfg.assistant_watchdog_enabled),
            "allowlist_enabled": bool(cfg.assistant_allowlist_enabled),
        },
    }


def format_status(info: dict[str, Any]) -> str:
    """The status dict as a few readable lines."""
    kill = (
        "ON   (every question is answered 503 assistant_disabled)"
        if info["kill_switch"]
        else "off  (the route answers, if its flags are on)"
    )
    ratio = f"{info['spend_ratio'] * 100:.1f}%" if info["spend_ratio"] is not None else "no cap set"
    settings = info["settings_of_this_task"]
    flags = ", ".join(f"{name} {'on' if value else 'off'}" for name, value in settings.items())
    return "\n".join(
        [
            f"environment     {info['environment']}",
            f"kill switch     {kill}",
            f"spend today     ${info['spend_usd']:.6f} of ${info['daily_budget_usd']:.2f} ({ratio}), "
            f"UTC {info['date_utc']}; exactly {info['spend_micro_usd']} millionths",
            f"allowlist       {info['allowlist_members']} account(s) in the set",
            f"this task's settings: {flags}",
        ]
    )


def _guard(args: argparse.Namespace, what: str) -> int | None:
    """None when the change may go ahead, else the exit code (with the reason printed)."""
    if not args.yes:
        print(f"dry run: {what}. Add --yes to do it.")
        return 0
    if get_settings().app_env in PROD_NAMES and not args.yes_prod:
        print(
            f"refused: this is {get_settings().app_env}; add --yes-prod to {what}.", file=sys.stderr
        )
        return 2
    return None


def _spend_target(args: argparse.Namespace) -> int | None:
    if (args.usd is None) == (args.micro is None):
        print("give exactly one of --usd or --micro", file=sys.stderr)
        return None
    micro = args.micro if args.micro is not None else round(args.usd * MICRO)
    if micro < 0 or micro > MAX_USD * MICRO:
        print(f"the amount must be between 0 and {MAX_USD} dollars", file=sys.stderr)
        return None
    return int(micro)


def run(argv: list[str], client: Any | None = None, now: dt.datetime | None = None) -> int:
    parser = argparse.ArgumentParser(prog="assistant_ctl.py", description=__doc__.split("\n")[0])
    parser.add_argument("--redis-url", help="override the API's cache address")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser(
        "status", help="show the kill switch, today's spend and the allowlist size"
    )
    status.add_argument("--json", action="store_true")
    kill = sub.add_parser("kill", help="the kill switch")
    kill.add_argument("state", choices=("on", "off"))
    spend = sub.add_parser("spend", help="today's spend counter (drills, and putting it back)")
    spend.add_argument("action", choices=("set", "clear"))
    spend.add_argument("--usd", type=float, help="dollars (set only)")
    spend.add_argument("--micro", type=int, help="millionths of a dollar, exact (set only)")
    for guarded in (kill, spend):
        guarded.add_argument("--yes", action="store_true", help="do it (otherwise a dry run)")
        guarded.add_argument("--yes-prod", action="store_true", help="also required in prod")

    args = parser.parse_args(argv)
    if (
        args.command == "spend"
        and args.action == "clear"
        and (args.usd is not None or args.micro is not None)
    ):
        print("clear takes no amount", file=sys.stderr)
        return 2
    try:
        redis_client = client if client is not None else _client(args.redis_url)
        moment = _now(now)
        if args.command == "status":
            info = read_status(redis_client, moment)
            print(json.dumps(info, indent=2, sort_keys=True) if args.json else format_status(info))
        elif args.command == "kill" and args.state == "on":
            redis_client.set(KILL_KEY, "1")  # no expiry: it stays until someone runs `kill off`
            print(f"{KILL_KEY} set: the route answers 503 assistant_disabled on every API task")
        elif args.command == "kill":
            refused = _guard(args, f"turn the kill switch off ({KILL_KEY} would be removed)")
            if refused is not None:
                return refused
            redis_client.delete(KILL_KEY)
            print(f"{KILL_KEY} removed: the route answers again, if its flags are on")
        else:
            key = spend_key(moment)
            before = redis_client.get(key)
            if args.action == "set":
                micro = _spend_target(args)
                if micro is None:
                    return 2
                refused = _guard(
                    args, f"set today's spend to {micro} millionths (it is {before or 0})"
                )
                if refused is not None:
                    return refused
                redis_client.set(key, str(micro), ex=SPEND_TTL_SECONDS)
                print(f"{key}: {before or 0} -> {micro} millionths of a dollar")
            else:
                refused = _guard(args, f"clear today's spend (it is {before or 0} millionths)")
                if refused is not None:
                    return refused
                redis_client.delete(key)
                print(f"{key}: {before or 0} -> removed")
    except OSError as exc:  # redis.exceptions.ConnectionError is an OSError subclass
        print(f"cannot reach the cache: {type(exc).__name__}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - any redis error (timeouts, auth, a closed pool)
        if type(exc).__module__.startswith("redis"):
            print(f"cannot use the cache: {type(exc).__name__}", file=sys.stderr)
            return 3
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))

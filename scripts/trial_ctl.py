#!/usr/bin/env python3
"""scripts/trial_ctl.py: the operator's switches for the no-sign-up trial lane (docs/plan-trial-lane-throttle.md).

Reasoning:
- The lane is controlled by Redis keys, not by a deploy, so that an incident can be answered in seconds and so
  that "absent or unreadable" can mean OFF (api/middleware/trial.py fails closed). This script is the one tool
  that reads and writes them; it never touches a budget bucket's own state, only the switches, the attack and
  pause flags and the budget override.
- `on` and `off` are the lane's master switch: the lane is off until someone runs `on`, in dev first and then
  prod, with no deploy. `attack` and `pause` are what the automatic breaker sets after three and six empty
  hourly checks (both expire on their own, after 24 and 12 hours); setting them by hand is the same switch, and
  clearing one also clears the breaker's strike count so it does not trip again at once. `budget` writes an
  override that can only LOWER a budget (the API takes the lower of the setting and the override), so a typo
  cannot open the lane wider than its settings.
- It talks to the same cache the API uses (storage/redis_client.py::redis_url()), so run it where the API's
  environment is available (an ECS one-off of the API task, as the other scripts do); `--redis-url` overrides.
  A one-off of the MIGRATE task has no cache address (it exits 3, "connecting to localhost:6379"): add the
  environment variable CELERY_RESULT_BACKEND, copied from the API task definition, which redis_url() reads and
  normalises. `--redis-url` takes the URL as redis-py reads it, so it needs `ssl_cert_reqs=none`, not the
  `CERT_NONE` spelling the API's variable carries.
  Nothing here prints a ticket, an address or a key, because the lane stores none in readable form.

Usage (repo root):
    python scripts/trial_ctl.py status
    python scripts/trial_ctl.py status --json
    python scripts/trial_ctl.py on                       # open the lane
    python scripts/trial_ctl.py off                      # close it (the kill switch)
    python scripts/trial_ctl.py attack on                # 24-bit proof of work, a smaller network share
    python scripts/trial_ctl.py attack off
    python scripts/trial_ctl.py pause on                 # stop issuing tickets; tickets in hand keep working
    python scripts/trial_ctl.py pause off
    python scripts/trial_ctl.py budget --compute-daily 500 --issue-daily 40
    python scripts/trial_ctl.py budget --clear

Exit codes: 0 done; 2 a usage error; 3 the cache could not be reached.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.middleware import trial as lane  # noqa: E402


def _client(url: str | None) -> Any:
    import redis

    from storage.redis_client import redis_url

    return redis.from_url(url or redis_url(), decode_responses=True, socket_timeout=5)


def _int(client: Any, key: str) -> int:
    raw = client.get(key)
    return int(raw) if raw else 0


def read_status(client: Any, now: float | None = None) -> dict[str, Any]:
    """The lane's switches and budgets as one dict."""
    moment = now if now is not None else time.time()
    now_ms = int(moment * 1000)
    on = client.get(lane.KEY_ON) is not None
    attack = client.get(lane.KEY_ATTACK) is not None
    paused = client.get(lane.KEY_PAUSE) is not None
    override = lane.parse_budget_override(client.get(lane.KEY_BUDGET))
    limits = lane.effective_limits(
        lane.Controls(on=on, attack=attack, paused=paused, budget=override)
    )
    cfg = lane.cfg
    return {
        "on": on,
        "attack": attack,
        "attack_ttl_seconds": _ttl(client, lane.KEY_ATTACK),
        "paused": paused,
        "pause_ttl_seconds": _ttl(client, lane.KEY_PAUSE),
        "budget_override": override,
        "compute_units_available": lane.bucket_level(
            _int(client, lane.KEY_COMPUTE),
            limits.compute_interval_ms,
            limits.compute_capacity,
            now_ms,
        ),
        "compute_capacity": limits.compute_capacity,
        "compute_units_needed_to_start": cfg.trial_min_units_to_start,
        "compute_units_today": _int(client, f"{lane.PREFIX_DAY}compute:{lane.utc_date(moment)}"),
        "compute_daily_cap": limits.compute_daily,
        "tickets_available": lane.bucket_level(
            _int(client, lane.KEY_ISSUE),
            limits.issue_interval_ms,
            limits.issue_capacity,
            now_ms,
        ),
        "ticket_capacity": limits.issue_capacity,
        "tickets_today": _int(client, f"{lane.PREFIX_DAY}issue:{lane.utc_date(moment)}"),
        "ticket_daily_cap": limits.issue_daily,
        "breaker_strikes": _int(client, lane.KEY_STRIKES),
        "breaker_attack_after": cfg.trial_breaker_attack_after,
        "breaker_pause_after": cfg.trial_breaker_pause_after,
        "pow_bits": limits.pow_bits,
    }


def _ttl(client: Any, key: str) -> int | None:
    ttl = client.ttl(key)
    return int(ttl) if ttl is not None and int(ttl) >= 0 else None


def _clears(ttl: int | None) -> str:
    return f" (clears itself in {ttl // 3600} h {ttl % 3600 // 60} min)" if ttl else ""


def format_status(info: dict[str, Any]) -> str:
    """The status dict as a few readable lines."""
    lane_line = (
        "ON" if info["on"] else "off   (no key: every request is answered 429 trial_exhausted)"
    )
    attack = ("ON" + _clears(info["attack_ttl_seconds"])) if info["attack"] else "off"
    issuance = ("PAUSED" + _clears(info["pause_ttl_seconds"])) if info["paused"] else "open"
    return "\n".join(
        [
            f"lane            {lane_line}",
            f"attack mode     {attack}   (proof of work {info['pow_bits']} bits)",
            f"issuance        {issuance}",
            f"budget override {info['budget_override'] or 'none'}",
            f"compute bucket  {info['compute_units_available']}/{info['compute_capacity']} units "
            f"(a call needs {info['compute_units_needed_to_start']} to start); "
            f"today {info['compute_units_today']}/{info['compute_daily_cap']}",
            f"ticket bucket   {info['tickets_available']}/{info['ticket_capacity']} tickets; "
            f"today {info['tickets_today']}/{info['ticket_daily_cap']}",
            f"breaker         {info['breaker_strikes']} empty hourly checks in a row "
            f"(attack at {info['breaker_attack_after']}, pause at {info['breaker_pause_after']})",
        ]
    )


def _flag(client: Any, key: str, value: str, ttl: int) -> str:
    if value == "on":
        client.set(key, "1", ex=ttl)
        return f"{key} set (expires in {ttl // 3600} h)"
    client.delete(key, lane.KEY_STRIKES)
    return f"{key} cleared, and the breaker's strike count with it"


def run(argv: list[str], client: Any | None = None, now: float | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trial_ctl.py", description=__doc__.split("\n")[0])
    parser.add_argument("--redis-url", help="override the API's cache address")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="show the switches and the budgets")
    status.add_argument("--json", action="store_true")
    sub.add_parser("on", help="open the lane")
    sub.add_parser("off", help="close the lane (the kill switch)")
    for name in ("attack", "pause"):
        flag = sub.add_parser(name, help=f"set or clear {name} mode")
        flag.add_argument("state", choices=("on", "off"))
    budget = sub.add_parser("budget", help="lower a budget (never raises one above its setting)")
    for field in lane.BUDGET_OVERRIDE_FIELDS:
        budget.add_argument(f"--{field.replace('_', '-')}", type=int, metavar="N")
    budget.add_argument("--clear", action="store_true", help="remove the override")

    args = parser.parse_args(argv)
    try:
        redis_client = client if client is not None else _client(args.redis_url)
        if args.command == "status":
            info = read_status(redis_client, now)
            print(json.dumps(info, indent=2, sort_keys=True) if args.json else format_status(info))
        elif args.command == "on":
            redis_client.set(lane.KEY_ON, "1")
            print(f"{lane.KEY_ON} set: the lane is open")
        elif args.command == "off":
            redis_client.delete(lane.KEY_ON)
            print(f"{lane.KEY_ON} removed: the lane is closed and answers 429 trial_exhausted")
        elif args.command == "attack":
            print(_flag(redis_client, lane.KEY_ATTACK, args.state, lane.ATTACK_TTL_SECONDS))
        elif args.command == "pause":
            print(_flag(redis_client, lane.KEY_PAUSE, args.state, lane.PAUSE_TTL_SECONDS))
        elif args.command == "budget":
            return _budget(redis_client, args)
    except OSError as exc:  # redis.exceptions.ConnectionError is an OSError subclass
        print(f"cannot reach the cache: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - any redis error (timeouts, auth, a closed pool)
        if type(exc).__module__.startswith("redis"):
            print(f"cannot use the cache: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 3
        raise
    return 0


def _budget(client: Any, args: argparse.Namespace) -> int:
    chosen = {
        field: getattr(args, field)
        for field in lane.BUDGET_OVERRIDE_FIELDS
        if getattr(args, field) is not None
    }
    if args.clear == bool(chosen):
        print(
            "give --clear, or at least one of the --*-hourly / --*-daily options", file=sys.stderr
        )
        return 2
    if args.clear:
        client.delete(lane.KEY_BUDGET)
        print(f"{lane.KEY_BUDGET} removed")
        return 0
    if any(value < 0 for value in chosen.values()):
        print("a budget cannot be negative", file=sys.stderr)
        return 2
    current = lane.parse_budget_override(client.get(lane.KEY_BUDGET))
    current.update(chosen)
    client.set(lane.KEY_BUDGET, json.dumps(current, sort_keys=True))
    print(f"{lane.KEY_BUDGET} = {json.dumps(current, sort_keys=True)} (it can only lower a budget)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))

"""Run the portal-assistant eval against a model, or run the harness checks with no model at all.

Reasoning (each rule below is an item of Anthropic's eval health checklist, adapted):
- Infra failures never become model failures: an attempt that produced no scorable output (API error after
  retries, wall-clock ceiling, served-model mismatch) goes to errors.jsonl, not results.jsonl, so it cannot
  occupy a (case, rep) slot or be averaged in as wrong. A reply cut off at max_tokens is status
  "truncated" and a refusal is status "refusal": both are counted and shown, neither is averaged in.
- Cost and tokens come from the API's `usage` block, at the rate of the model that served the call. A hard
  spend cap (--max-usd) stops new work when reached; the cases it skips are counted as skipped, not failed.
- Retries use jittered exponential backoff, are capped, and are recorded per row. Latency is the final
  successful request only (retries and backoff sleeps are excluded).
- The model that served each call must be the model that was asked for; a mismatch is an error.
- Every case keeps its full conversation under traces/, so a surprising score can be traced.
- --oracle and --null run the whole pipeline with no API: an answer built from the record must pass every
  grader, an empty answer must fail every one. Run both before any paid pass.

Usage:
    python scripts/assistant_eval/run_eval.py --cases CASES --out DIR --oracle
    python scripts/assistant_eval/run_eval.py --cases CASES --out DIR --null
    python scripts/assistant_eval/run_eval.py --cases CASES --out DIR --model claude-haiku-5-5 --max-usd 3
    python scripts/assistant_eval/run_eval.py --cases CASES --out DIR --model claude-opus-5-5 \\
        --effort low --only-ids ID1,ID2 --reps 8 --max-usd 1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cost import usage_cost
from graders import grade, oracle_text
from prompts import EFFORT, PROMPT_VERSION, build_request, intent_key

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
RETRYABLE_NAMES = {"APIConnectionError", "APITimeoutError", "ConnectionError", "TimeoutError"}
MAX_API_ATTEMPTS = 4
MAX_EXAMPLE_TRIES = 3
USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
HERE = Path(__file__).resolve().parent
PROVENANCE_FILES = ("prompts.py", "graders.py")


class CaseTimeout(Exception):
    """The per-case wall-clock ceiling was reached."""


class ServedModelMismatch(Exception):
    """The response names a different model from the one requested."""


class Budget:
    """A shared, thread-safe spend counter with a hard cap."""

    def __init__(self, cap_usd: float) -> None:
        self.cap = cap_usd
        self.spent = 0.0
        self._lock = threading.Lock()

    def add(self, amount: float) -> None:
        with self._lock:
            self.spent += amount

    def exhausted(self) -> bool:
        with self._lock:
            return self.spent >= self.cap


def is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    return status in RETRYABLE_STATUS or type(exc).__name__ in RETRYABLE_NAMES


def call_model(
    client: Any,
    model: str,
    request: dict[str, Any],
    *,
    deadline: float,
    sleep: Callable[[float], None],
    rng: random.Random,
    counters: dict[str, int],
) -> dict[str, Any]:
    """One logical call: retried on transient errors, timed on the successful request only."""
    attempt = 0
    while True:
        if time.monotonic() > deadline:
            raise CaseTimeout("case wall-clock ceiling reached")
        started = time.monotonic()
        try:
            response = client.messages.create(model=model, **request)
        except Exception as exc:
            if is_retryable(exc) and attempt < MAX_API_ATTEMPTS - 1:
                attempt += 1
                counters["retries"] += 1
                sleep(min(30.0, 2.0**attempt) * rng.uniform(0.5, 1.5))
                continue
            raise
        latency = time.monotonic() - started
        served = str(getattr(response, "model", ""))
        if not served.startswith(model):
            raise ServedModelMismatch(f"asked for {model}, served by {served!r}")
        text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
        usage = {k: int(getattr(response.usage, k, 0) or 0) for k in USAGE_KEYS}
        return {
            "text": text,
            "usage": usage,
            "stop_reason": response.stop_reason,
            "served": served,
            "latency": latency,
        }


def run_case(
    client: Any,
    case: dict[str, Any],
    model: str,
    rep: int,
    *,
    budget: Budget,
    case_timeout_s: float,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
    effort: str = EFFORT,
) -> tuple[str, dict[str, Any]]:
    """Run one (case, rep). Returns ("result" | "error" | "skipped", row)."""
    rng = rng or random.Random()
    deadline = time.monotonic() + case_timeout_s
    counters = {"retries": 0}
    usage_total = dict.fromkeys(USAGE_KEYS, 0)
    cost = 0.0
    feedback: list[tuple[str, list[str]]] = []
    turns: list[dict[str, Any]] = []
    tries = MAX_EXAMPLE_TRIES if case["intent"] == "example" else 1
    last: dict[str, Any] | None = None
    first_try_passed: bool | None = None
    attempt_count = 0
    status = "ok"
    try:
        for attempt in range(tries):
            if budget.exhausted() and attempt == 0:
                return "skipped", {"case_id": case["id"], "rep": rep, "reason": "spend cap reached"}
            request = build_request(case, feedback, effort)
            if attempt == 0:
                turns.append({"role": "system", "content": request["system"]})
                turns.append({"role": "user", "content": request["messages"][0]["content"]})
            last = call_model(
                client, model, request, deadline=deadline, sleep=sleep, rng=rng, counters=counters
            )
            attempt_count += 1
            call_cost = usage_cost(last["served"], last["usage"])
            cost += call_cost
            budget.add(call_cost)
            for key in USAGE_KEYS:
                usage_total[key] += last["usage"][key]
            turns.append({"role": "assistant", "content": last["text"]})
            if last["stop_reason"] == "refusal":
                status = "refusal"
                break
            if last["stop_reason"] == "max_tokens":
                status = "truncated"
                break
            verdict = grade(case, last["text"])
            if attempt == 0:
                first_try_passed = verdict.passed
            if verdict.passed or case["intent"] != "example":
                break
            feedback.append((last["text"], verdict.flags))
            turns.append({"role": "user", "content": "; ".join(verdict.flags)[:600]})
    except CaseTimeout as exc:
        return "error", _error_row(case, rep, model, "timeout", exc, counters)
    except ServedModelMismatch as exc:
        return "error", _error_row(case, rep, model, "served_model_mismatch", exc, counters)
    except Exception as exc:  # noqa: BLE001
        # Recorded with its class in errors.jsonl; never scored as a model failure.
        return "error", _error_row(case, rep, model, "api_error", exc, counters)

    assert last is not None
    final = grade(case, last["text"]).as_dict() if status == "ok" else None
    row = {
        "case_id": case["id"],
        "rep": rep,
        "intent": intent_key(case),
        "tags": case["tags"],
        "model": model,
        "served_model": last["served"],
        "status": status,
        "stop_reason": last["stop_reason"],
        "text": last["text"],
        "grade": final,
        "model_tries": attempt_count,
        "first_try_passed": first_try_passed,
        "usage": usage_total,
        "cost_usd": cost,
        "latency_s": last["latency"],
        "retries": counters["retries"],
        "trace": turns,
    }
    return "result", row


def run_offline(case: dict[str, Any], rep: int, kind: str) -> tuple[str, dict[str, Any]]:
    """The oracle (answer built from the record) or null (empty answer) baseline: no API call."""
    text = oracle_text(case) if kind == "oracle" else ""
    row = {
        "case_id": case["id"],
        "rep": rep,
        "intent": intent_key(case),
        "tags": case["tags"],
        "model": kind,
        "served_model": kind,
        "status": "ok",
        "stop_reason": "end_turn",
        "text": text,
        "grade": grade(case, text).as_dict(),
        "model_tries": 0,
        "first_try_passed": None,
        "usage": dict.fromkeys(USAGE_KEYS, 0),
        "cost_usd": 0.0,
        "latency_s": 0.0,
        "retries": 0,
        "trace": [{"role": "assistant", "content": text}],
    }
    return "result", row


def _error_row(
    case: dict[str, Any],
    rep: int,
    model: str,
    failure_class: str,
    exc: Exception,
    counters: dict[str, int],
) -> dict[str, Any]:
    return {
        "case_id": case["id"],
        "rep": rep,
        "model": model,
        "failure_class": failure_class,
        "error_type": type(exc).__name__,
        "error": str(exc)[:300],
        "retries": counters["retries"],
    }


def wilson(passes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a pass rate."""
    if n == 0:
        return 0.0, 0.0
    p = passes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def code_provenance(directory: Path = HERE) -> dict[str, Any]:
    """Which prompts.py and graders.py produced a run: git commit, uncommitted edits, content hashes.

    The hashes need no git, so a run copied off the machine still says which text it used. `commit` is
    the last commit that touched either file (None outside a git checkout); `dirty` is True when either
    file differs from it, in which case the commit alone does not identify the code.
    """
    paths = [str(directory / name) for name in PROVENANCE_FILES]

    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
                ["git", "-C", str(directory), *args],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=20,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout.strip()

    commit = git("log", "-1", "--format=%H", "--", *paths) or None
    status = git("status", "--porcelain", "--", *paths)
    return {
        "commit": commit,
        "dirty": bool(status) if status is not None else None,
        "sha256": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in PROVENANCE_FILES
        },
    }


def summarize(
    rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    skipped: int,
    model: str,
    effort: str = EFFORT,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Per-intent pass rates with intervals, plus counts, tokens, cost and latency.

    `model` is the writer model id that was asked for ("oracle" or "null" for the offline baselines);
    the summary also lists the model ids the API reported serving, so a silent swap would show.
    """
    by_intent: dict[str, dict[str, Any]] = {}
    scored = [r for r in rows if r["status"] == "ok"]
    for intent in sorted({r["intent"] for r in rows}):
        group = [r for r in scored if r["intent"] == intent]
        passed = sum(1 for r in group if r["grade"]["passed"])
        low, high = wilson(passed, len(group))
        entry: dict[str, Any] = {
            "n": len(group),
            "pass_rate": passed / len(group) if group else 0.0,
            "ci95": [round(low, 3), round(high, 3)],
        }
        if intent.startswith("example"):
            first = [r for r in group if r["first_try_passed"] is not None]
            entry["first_try_pass_rate"] = (
                sum(1 for r in first if r["first_try_passed"]) / len(first) if first else None
            )
        failed_checks: dict[str, int] = {}
        for r in group:
            for name, ok in r["grade"]["checks"].items():
                if not ok:
                    failed_checks[name] = failed_checks.get(name, 0) + 1
        entry["failed_checks"] = dict(sorted(failed_checks.items(), key=lambda kv: -kv[1]))
        by_intent[intent] = entry
    latencies = [r["latency_s"] for r in rows if r["latency_s"] > 0]
    totals = {k: sum(r["usage"][k] for r in rows) for k in USAGE_KEYS}
    return {
        "model": model,
        "writer_model": model,
        "served_models": sorted({str(r.get("served_model")) for r in rows}),
        "effort": effort,
        "prompt_version": PROMPT_VERSION,
        "code": provenance if provenance is not None else code_provenance(),
        "cases_run": len(rows),
        "scored": len(scored),
        "truncated": sum(1 for r in rows if r["status"] == "truncated"),
        "refusals": sum(1 for r in rows if r["status"] == "refusal"),
        "errors": len(errors),
        "error_classes": sorted({e["failure_class"] for e in errors}),
        "skipped_by_spend_cap": skipped,
        "retries": sum(r["retries"] for r in rows),
        "by_intent": by_intent,
        "tokens": totals,
        "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "cost_per_case_usd": (
            round(statistics.mean([r["cost_usd"] for r in rows]), 6) if rows else 0.0
        ),
        "latency_s": {
            "p50": round(_percentile(latencies, 0.5), 2),
            "p95": round(_percentile(latencies, 0.95), 2),
        },
    }


def load_cases(
    path: Path,
    limit: int | None,
    only: set[str] | None = None,
    only_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """The cases in file order; `only` keeps those whose action is listed and `only_ids` those whose id is
    listed, both before `limit` is applied.

    Raises:
        ValueError: if `only_ids` names an id that is not in the file (a typo would otherwise run nothing).
    """
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if only_ids:
        missing = sorted(only_ids - {c["id"] for c in cases})
        if missing:
            raise ValueError(f"case ids not in {path.name}: {missing}")
        cases = [c for c in cases if c["id"] in only_ids]
    if only:
        cases = [c for c in cases if intent_key(c) in only]
    return cases[:limit] if limit else cases


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None, help="only the first N cases")
    parser.add_argument(
        "--only",
        default=None,
        help="comma-separated actions to run (explain, when, compare, example:typical, example:stress)",
    )
    parser.add_argument(
        "--only-ids",
        default=None,
        help="comma-separated case ids to run (an id that is not in --cases is an error)",
    )
    parser.add_argument(
        "--effort",
        default=EFFORT,
        choices=EFFORT_LEVELS,
        help=f"output_config.effort sent with every writer call (default {EFFORT}, as in every Phase 0 run)",
    )
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--case-timeout", type=float, default=240.0)
    parser.add_argument("--max-usd", type=float, default=5.0, help="hard spend cap for this run")
    parser.add_argument(
        "--oracle", action="store_true", help="no API: answers built from the record"
    )
    parser.add_argument("--null", action="store_true", help="no API: empty answers")
    args = parser.parse_args()

    only = {a.strip() for a in args.only.split(",") if a.strip()} if args.only else None
    only_ids = {i.strip() for i in args.only_ids.split(",") if i.strip()} if args.only_ids else None
    try:
        cases = load_cases(args.cases, args.limit, only, only_ids)
    except ValueError as exc:
        parser.error(str(exc))
    offline = "oracle" if args.oracle else "null" if args.null else None
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "traces").mkdir(exist_ok=True)
    results_path, errors_path = args.out / "results.jsonl", args.out / "errors.jsonl"
    done = set()
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            row = json.loads(line)
            done.add((row["case_id"], row["rep"]))
    jobs = [(c, r) for c in cases for r in range(args.reps) if (c["id"], r) not in done]

    client = None
    if offline is None:
        import anthropic  # imported late: the offline baselines and the tests need no SDK

        client = anthropic.Anthropic(max_retries=0, timeout=90.0)
    budget = Budget(args.max_usd)
    lock = threading.Lock()
    new_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    skipped = 0

    def work(job: tuple[dict[str, Any], int]) -> None:
        nonlocal skipped
        case, rep = job
        kind, row = (
            run_offline(case, rep, offline)
            if offline
            else run_case(
                client,
                case,
                args.model,
                rep,
                budget=budget,
                case_timeout_s=args.case_timeout,
                effort=args.effort,
            )
        )
        with lock:
            if kind == "result":
                trace = row["trace"]
                safe = case["id"].replace(":", "__").replace("/", "_")
                (args.out / "traces" / f"{safe}_rep{rep}.json").write_text(
                    json.dumps(trace, indent=1)
                )
                slim = {k: v for k, v in row.items() if k != "trace"}
                with results_path.open("a") as handle:
                    handle.write(json.dumps(slim) + "\n")
                new_rows.append(slim)
            elif kind == "error":
                with errors_path.open("a") as handle:
                    handle.write(json.dumps(row) + "\n")
                errors.append(row)
            else:
                skipped += 1

    with ThreadPoolExecutor(max_workers=1 if offline else args.workers) as pool:
        list(pool.map(work, jobs))

    all_rows = (
        [json.loads(line) for line in results_path.read_text().splitlines()]
        if results_path.exists()
        else []
    )
    summary = summarize(all_rows, errors, skipped, offline or args.model, args.effort)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if offline == "oracle":
        bad = [r for r in all_rows if not r["grade"]["passed"]]
        print(f"ORACLE: {len(all_rows) - len(bad)}/{len(all_rows)} pass (must be all)")
        return 1 if bad else 0
    if offline == "null":
        good = [r for r in all_rows if r["grade"]["passed"]]
        print(f"NULL: {len(good)}/{len(all_rows)} pass (must be none)")
        return 1 if good else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

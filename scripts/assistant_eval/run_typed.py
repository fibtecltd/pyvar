"""Run the typed-question eval: a model with three read-only tools answers a visitor's typed question.

Reasoning (plan 1, section 3 item 5; the rules are run_eval.py's, applied to a tool loop):
- The agent loop is the one the gateway will run: system prompt, the tools of typed_tools.py, at most
  MAX_TOOL_TURNS rounds of tool calls, then a last call that must answer in words (`tool_choice` none).
  Tools run in-process on portal/functions.json: no network, no AWS.
- Each model call goes through run_eval.call_model, so the retry rule, the served-model check and the
  per-call latency are the ones the menu runs used. Cost comes from each call's `usage` at the rate of the model
  that served it; the same Budget stops new cases at --max-usd (a case in progress is finished, so the cap can
  be overshot by one case).
- The question is scrubbed (scrub.py) before it reaches the model, and a question that still looks like a key
  after scrubbing is never sent: it is an error row, not a model failure.
- Infra failures go to errors.jsonl and never become model failures. A reply cut at max_tokens, a refusal and
  a loop that never answers within the limit are their own statuses, counted and shown, never averaged in.
- Latency is reported per call and end to end (sum of the successful calls plus local tool time); time to
  first token is not measurable with the non-streaming client.

Usage:
    python scripts/assistant_eval/run_typed.py --cases typed_cases.jsonl --out DIR --model claude-haiku-5-5 --max-usd 0.3
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cost import usage_cost
from graders import grade_typed
from prompts import EFFORT
from run_eval import (
    EFFORT_LEVELS,
    USAGE_KEYS,
    Budget,
    CaseTimeout,
    ServedModelMismatch,
    _percentile,
    call_model,
    code_provenance,
)
from scrub import has_secret, scrub_secrets
from typed_prompts import (
    MAX_TOOL_TURNS,
    TYPED_PROMPT_VERSION,
    build_typed_request,
    user_content,
)
from typed_tools import ToolBox, load_catalogue, trim_record

PROVENANCE_FILES = ("typed_prompts.py", "typed_tools.py", "graders.py", "run_typed.py")


def block_to_dict(block: Any) -> dict[str, Any]:
    """A response content block as plain data, for the trace file."""
    kind = getattr(block, "type", None)
    if kind == "text":
        return {"type": "text", "text": block.text}
    if kind == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return {"type": str(kind)}


def _error_row(
    case: dict[str, Any], rep: int, model: str, failure_class: str, exc: Exception, retries: int
) -> dict[str, Any]:
    return {
        "case_id": case["id"],
        "rep": rep,
        "model": model,
        "failure_class": failure_class,
        "error_type": type(exc).__name__,
        "error": str(exc)[:300],
        "retries": retries,
    }


def grade_row(
    case: dict[str, Any], row: dict[str, Any], by_name: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """Grade a finished row with `graders.grade_typed`; None unless the reply is a scorable answer.

    The records the tools returned are rebuilt from the catalogue by name (`get_function` returns exactly
    `trim_record`), so a row stores names, not copies.
    """
    if row["status"] != "ok":
        return None
    records = {n: trim_record(by_name[n]) for n in row["records_seen"] if n in by_name}
    hits = {n: by_name[n]["summary"] for n in row["search_hits"] if n in by_name}
    page = case.get("page_function")
    shown = {n: e["display_name"] for n, e in by_name.items()}
    return grade_typed(
        row["text"],
        records,
        case["question"],
        expect=case["expect"],
        search_hits=hits,
        tool_calls=row["tool_calls"],
        proposals=row["proposals"],
        page_function=page,
        display_names=shown,
    ).as_dict()


class ScrubFailed(Exception):
    """The question still looks like a key after scrubbing: it must not be sent."""


def run_case(
    client: Any,
    case: dict[str, Any],
    model: str,
    rep: int,
    *,
    catalogue: list[dict[str, Any]],
    budget: Budget,
    case_timeout_s: float,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
    effort: str = EFFORT,
) -> tuple[str, dict[str, Any]]:
    """Run one (case, rep). Returns ("result" | "error" | "skipped", row)."""
    rng = rng or random.Random()
    if budget.exhausted():
        return "skipped", {"case_id": case["id"], "rep": rep, "reason": "spend cap reached"}
    started = time.monotonic()
    deadline = started + case_timeout_s
    counters = {"retries": 0}
    usage_total = dict.fromkeys(USAGE_KEYS, 0)
    cost = 0.0
    latencies: list[float] = []
    tool_seconds = 0.0
    toolbox = ToolBox(catalogue)
    trace: list[dict[str, Any]] = []
    status, text, last = "ok", "", None
    tool_turns = 0
    try:
        question, scrubbed = scrub_secrets(case["question"])
        if has_secret(question):
            raise ScrubFailed("a key-like string survived the scrub")
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_content(question, case.get("page_function"))}
        ]
        trace.append({"role": "user", "content": messages[0]["content"]})
        for call_number in range(MAX_TOOL_TURNS + 1):
            tools_allowed = call_number < MAX_TOOL_TURNS
            request = build_typed_request(messages, effort, tools_allowed=tools_allowed)
            last = call_model(
                client, model, request, deadline=deadline, sleep=sleep, rng=rng, counters=counters
            )
            latencies.append(last["latency"])
            call_cost = usage_cost(last["served"], last["usage"])
            cost += call_cost
            budget.add(call_cost)
            for key in USAGE_KEYS:
                usage_total[key] += last["usage"][key]
            messages.append({"role": "assistant", "content": last["content"]})
            trace.append(
                {"role": "assistant", "content": [block_to_dict(b) for b in last["content"]]}
            )
            text = last["text"]
            if last["stop_reason"] == "refusal":
                status = "refusal"
                break
            if last["stop_reason"] == "max_tokens":
                status = "truncated"
                break
            if last["stop_reason"] != "tool_use":
                break
            if not tools_allowed:
                status = "tool_limit"
                break
            results = []
            for block in last["content"]:
                if getattr(block, "type", None) != "tool_use":
                    continue
                began = time.monotonic()
                output = toolbox.run(block.name, block.input)
                tool_seconds += time.monotonic() - began
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
            messages.append({"role": "user", "content": results})
            trace.append({"role": "user", "content": results})
            tool_turns += 1
    except CaseTimeout as exc:
        return "error", _error_row(case, rep, model, "timeout", exc, counters["retries"])
    except ServedModelMismatch as exc:
        return "error", _error_row(
            case, rep, model, "served_model_mismatch", exc, counters["retries"]
        )
    except ScrubFailed as exc:
        return "error", _error_row(case, rep, model, "scrub_failed", exc, counters["retries"])
    except (
        Exception
    ) as exc:  # noqa: BLE001 - recorded with its class, never scored as a model failure
        return "error", _error_row(case, rep, model, "api_error", exc, counters["retries"])

    assert last is not None
    row: dict[str, Any] = {
        "case_id": case["id"],
        "rep": rep,
        "category": case["category"],
        "in_scope": case["in_scope"],
        "model": model,
        "served_model": last["served"],
        "status": status,
        "stop_reason": last["stop_reason"],
        "text": text,
        "grade": None,
        "scrubbed": scrubbed,
        "tool_turns": tool_turns,
        "tool_calls": toolbox.calls,
        "records_seen": sorted(toolbox.records),
        "search_hits": sorted(toolbox.search_hits),
        "proposals": toolbox.proposals,
        "model_calls": len(latencies),
        "usage": usage_total,
        "cost_usd": cost,
        "call_latencies_s": [round(x, 3) for x in latencies],
        "latency_s": sum(latencies) + tool_seconds,
        "wall_s": time.monotonic() - started,
        "retries": counters["retries"],
        "trace": trace,
    }
    row["grade"] = grade_row(case, row, {e["name"]: e for e in catalogue})
    return "result", row


def summarize(
    rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    skipped: int,
    model: str,
    effort: str = EFFORT,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Counts by category and status, tokens and cost per case, tool turns and latency."""
    by_category: dict[str, dict[str, Any]] = {}
    for category in sorted({r["category"] for r in rows}):
        group = [r for r in rows if r["category"] == category]
        graded = [r for r in group if r["grade"]]
        failed: dict[str, int] = {}
        for r in graded:
            for name, ok in r["grade"]["checks"].items():
                if not ok:
                    failed[name] = failed.get(name, 0) + 1
        by_category[category] = {
            "n": len(group),
            "graded": len(graded),
            "grader_pass": sum(1 for r in graded if r["grade"]["passed"]),
            "failed_checks": dict(sorted(failed.items(), key=lambda kv: -kv[1])),
            "status": {
                s: sum(1 for r in group if r["status"] == s)
                for s in sorted({r["status"] for r in group})
            },
            "tool_turns_mean": round(statistics.mean(r["tool_turns"] for r in group), 2),
            "cost_per_case_usd": round(statistics.mean(r["cost_usd"] for r in group), 6),
        }
    latencies = [r["latency_s"] for r in rows if r["latency_s"] > 0]
    calls = [x for r in rows for x in r["call_latencies_s"]]
    totals = {k: sum(r["usage"][k] for r in rows) for k in USAGE_KEYS}
    return {
        "kind": "typed",
        "model": model,
        "writer_model": model,
        "served_models": sorted({str(r.get("served_model")) for r in rows}),
        "effort": effort,
        "typed_prompt_version": TYPED_PROMPT_VERSION,
        "code": provenance if provenance is not None else code_provenance(files=PROVENANCE_FILES),
        "cases_run": len(rows),
        "errors": len(errors),
        "error_classes": sorted({e["failure_class"] for e in errors}),
        "skipped_by_spend_cap": skipped,
        "retries": sum(r["retries"] for r in rows),
        "by_category": by_category,
        "tokens": totals,
        "tokens_per_case": {k: round(v / len(rows), 1) for k, v in totals.items()} if rows else {},
        "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "cost_per_case_usd": (
            round(statistics.mean(r["cost_usd"] for r in rows), 6) if rows else 0.0
        ),
        "latency_end_to_end_s": {
            "p50": round(_percentile(latencies, 0.5), 2),
            "p95": round(_percentile(latencies, 0.95), 2),
        },
        "latency_per_call_s": {
            "p50": round(_percentile(calls, 0.5), 2),
            "p95": round(_percentile(calls, 0.95), 2),
        },
    }


def load_cases(
    path: Path,
    limit: int | None = None,
    only_ids: set[str] | None = None,
    categories: set[str] | None = None,
    in_scope_only: bool = False,
) -> list[dict[str, Any]]:
    """The typed cases in file order, filtered before `limit` is applied.

    Raises:
        ValueError: if `only_ids` names an id that is not in the file.
    """
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if only_ids:
        missing = sorted(only_ids - {c["id"] for c in cases})
        if missing:
            raise ValueError(f"case ids not in {path.name}: {missing}")
        cases = [c for c in cases if c["id"] in only_ids]
    if categories:
        cases = [c for c in cases if c["category"] in categories]
    if in_scope_only:
        cases = [c for c in cases if c["in_scope"]]
    return cases[:limit] if limit else cases


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-ids", default=None, help="comma-separated case ids")
    parser.add_argument("--categories", default=None, help="comma-separated, from A to I")
    parser.add_argument("--effort", default=EFFORT, choices=EFFORT_LEVELS)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--case-timeout", type=float, default=240.0)
    parser.add_argument("--max-usd", type=float, default=5.0, help="hard spend cap for this run")
    args = parser.parse_args()

    only_ids = {i.strip() for i in args.only_ids.split(",") if i.strip()} if args.only_ids else None
    categories = (
        {c.strip() for c in args.categories.split(",") if c.strip()} if args.categories else None
    )
    try:
        cases = load_cases(args.cases, args.limit, only_ids, categories)
    except ValueError as exc:
        parser.error(str(exc))
    catalogue = load_catalogue()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "traces").mkdir(exist_ok=True)
    results_path, errors_path = args.out / "results.jsonl", args.out / "errors.jsonl"
    done = set()
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            row = json.loads(line)
            done.add((row["case_id"], row["rep"]))
    jobs = [(c, r) for c in cases for r in range(args.reps) if (c["id"], r) not in done]

    import anthropic  # imported late: the tests and the offline baselines need no SDK

    client = anthropic.Anthropic(max_retries=0, timeout=90.0)
    budget = Budget(args.max_usd)
    lock = threading.Lock()
    errors: list[dict[str, Any]] = []
    skipped = 0

    def work(job: tuple[dict[str, Any], int]) -> None:
        nonlocal skipped
        case, rep = job
        kind, row = run_case(
            client,
            case,
            args.model,
            rep,
            catalogue=catalogue,
            budget=budget,
            case_timeout_s=args.case_timeout,
            effort=args.effort,
        )
        with lock:
            if kind == "result":
                safe = case["id"].replace(":", "__").replace("/", "_")
                (args.out / "traces" / f"{safe}_rep{rep}.json").write_text(
                    json.dumps(row["trace"], indent=1)
                )
                slim = {k: v for k, v in row.items() if k != "trace"}
                with results_path.open("a") as handle:
                    handle.write(json.dumps(slim) + "\n")
            elif kind == "error":
                with errors_path.open("a") as handle:
                    handle.write(json.dumps(row) + "\n")
                errors.append(row)
            else:
                skipped += 1

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, jobs))

    all_rows = (
        [json.loads(line) for line in results_path.read_text().splitlines()]
        if results_path.exists()
        else []
    )
    summary = summarize(all_rows, errors, skipped, args.model, args.effort)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

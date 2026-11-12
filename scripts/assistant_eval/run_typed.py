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

Two ways to run a case against a model:
- the PIPELINE (the default, `run_case_pipeline`): each question goes through
  `assistant.guardrails.answer_question`, the function the gateway calls, with the production client, caps
  (`DEFAULT_MAX_USD`, `DEFAULT_MAX_SECONDS`), checks, one retry and static fallback. Nothing about the answer
  path is re-implemented here, so the run measures the shipped code. A served answer is "live" (the model's
  text, which passed the production checks) or "static" (fixed text). Only live answers are graded against the
  case's expectation and judged; static answers are counted, by outcome. An infrastructure failure (the client
  gave up, a served-model mismatch, an auth or billing error) is an error row, never a static answer that
  would hide it.
- the RAW loop (`--raw`, `run_case`): the first run's harness (no guardrails, no retry), kept so its numbers can be
  reproduced.

Usage:
    python scripts/assistant_eval/run_typed.py --cases typed_cases.jsonl --out DIR --oracle   # no API
    python scripts/assistant_eval/run_typed.py --cases typed_cases.jsonl --out DIR --null     # no API
    python scripts/assistant_eval/run_typed.py --cases typed_cases.jsonl --out DIR --model claude-haiku-5-5 --max-usd 0.4
    python scripts/assistant_eval/run_typed.py --cases typed_cases.jsonl --out DIR --raw --model claude-haiku-5-5 --max-usd 0.4
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
from prompts import EFFORT
from run_eval import (
    EFFORT_LEVELS,
    REPO,
    USAGE_KEYS,
    Budget,
    CaseTimeout,
    ServedModelMismatch,
    _percentile,
    call_model,
    code_provenance,
)
from scrub import has_secret, scrub_secrets
from typed_oracle import oracle_run
from typed_prompts import (
    MAX_TOOL_TURNS,
    TYPED_PROMPT_VERSION,
    build_typed_request,
    user_content,
)
from typed_tools import ToolBox, load_catalogue, trim_record

from assistant.agent import DEFAULT_MAX_SECONDS, DEFAULT_MAX_USD
from assistant.client import (
    DEFAULT_TIMEOUT_S,
    AnthropicClient,
    ModelCallError,
    ModelClient,
    Reply,
)
from assistant.guardrails import answer_question
from assistant.typed_graders import bare_denial, empty_required_values, grade_typed

# the kernel files are read from assistant/ (run_eval.code_provenance); run_typed.py from this directory
PROVENANCE_FILES = (
    "typed_prompts.py",
    "tools.py",
    "typed_graders.py",
    "graders.py",
    "agent.py",
    "guardrails.py",
    "scrub.py",
    "client.py",
    "cost.py",
    "run_typed.py",
)
BANK_DIR = REPO / "portal" / "assistant" / "bank"
STATIC_STATUS = "static"


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


class RecordingClient:
    """Wraps a `ModelClient` and remembers what the pipeline did with it, for one case.

    The pipeline (`answer_question`) turns a client failure into static text, which is right for a visitor and
    wrong for a measurement: an outage must not look like a model that declined. So the harness keeps the
    exception that ended a call, the replies (latency per call) and the last request, from which the trace is
    rebuilt. One instance per case; not shared between threads.
    """

    def __init__(self, inner: ModelClient) -> None:
        self.inner = inner
        self.replies: list[Reply] = []
        self.last_request: dict[str, Any] | None = None
        self.error: ModelCallError | None = None

    def complete(self, model: str, request: dict[str, Any]) -> Reply:
        self.last_request = request
        try:
            reply = self.inner.complete(model, request)
        except ModelCallError as exc:
            self.error = exc
            raise
        self.replies.append(reply)
        return reply

    def trace(self) -> list[dict[str, Any]]:
        """The conversation of the last call (every earlier turn is in its request) plus its reply."""
        if self.last_request is None:
            return []
        turns = [
            {"role": m["role"], "content": m["content"]} for m in self.last_request["messages"]
        ]
        if self.replies and self.replies[-1].content:
            turns.append({"role": "assistant", "content": list(self.replies[-1].content)})
        return turns


def error_class(client: RecordingClient) -> str:
    """Why a client gave up: auth_or_billing (401, 403, a credit or billing message), served_model_mismatch,
    or api_error (anything else, after the client's own retries)."""
    exc = client.error
    if type(exc).__name__ == "ServedModelMismatch":  # assistant.client's class, not run_eval's
        return "served_model_mismatch"
    cause = exc.__cause__ if exc is not None else None
    status = getattr(cause, "status_code", None)
    text = str(cause).lower()
    if status in (401, 402, 403) or "credit" in text or "billing" in text:
        return "auth_or_billing"
    return "api_error"


ClientFactory = Callable[[Callable[[float], None]], ModelClient]


def run_case_pipeline(
    make_client: ClientFactory,
    case: dict[str, Any],
    model: str,
    rep: int,
    *,
    catalogue: list[dict[str, Any]],
    budget: Budget,
    bank_dir: Path | None = BANK_DIR,
    max_usd: float = DEFAULT_MAX_USD,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    effort: str = EFFORT,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, dict[str, Any]]:
    """Run one (case, rep) through `answer_question`. Returns ("result" | "error" | "skipped", row).

    Args:
        make_client: builds the model client for this case, given the sleeper to use between retries (the
            harness passes one that counts them); a test passes a scripted client.
        case, model, rep: as in `run_case`.
        catalogue, budget: as in `run_case`; the budget is charged the whole answer's cost afterwards.
        bank_dir: the bank the static text is read from (the committed one by default).
        max_usd, max_seconds: the per-question caps; the production defaults, so the run measures them.
        effort: the `output_config.effort` level.
        sleep: the real sleeper that the counting sleeper calls.

    A "result" row has `status` "ok" for a live answer (graded against the case) and "static" for fixed
    text (not graded: it is not model text). An error row means the provider failed for good.
    """
    if budget.exhausted():
        return "skipped", {"case_id": case["id"], "rep": rep, "reason": "spend cap reached"}
    started = time.monotonic()
    retries = [0]

    def counting_sleep(seconds: float) -> None:
        retries[0] += 1
        sleep(seconds)

    client = RecordingClient(make_client(counting_sleep))
    try:
        answer = answer_question(
            client,
            model,
            case["question"],
            catalogue=catalogue,
            page_function=case.get("page_function"),
            bank_dir=bank_dir,
            max_usd=max_usd,
            max_seconds=max_seconds,
            effort=effort,
        )
    except (
        Exception
    ) as exc:  # noqa: BLE001 - recorded with its class, never scored as a model failure
        return "error", _error_row(case, rep, model, "api_error", exc, retries[0])
    budget.add(answer.cost)
    if answer.outcome == "static_error":  # the client gave up: an outage, not an answer
        exc = client.error or ModelCallError("model call failed")
        error = _error_row(case, rep, model, error_class(client), exc, retries[0])
        cause = exc.__cause__
        # what the provider said, by class and HTTP status only (its message is not kept): a 400 on a replayed
        # thinking or tool-call block, the one thing nothing offline can test, shows up here
        error["cause_type"] = type(cause).__name__ if cause is not None else None
        error["http_status"] = getattr(cause, "status_code", None)
        return "error", error

    live = answer.source == "live"
    last = client.replies[-1] if client.replies else None
    wall = time.monotonic() - started
    row: dict[str, Any] = {
        "case_id": case["id"],
        "rep": rep,
        "category": case["category"],
        "in_scope": case["in_scope"],
        "model": model,
        "served_model": answer.served or model,
        "status": "ok" if live else STATIC_STATUS,
        "stop_reason": last.stop_reason if last else None,
        "text": answer.text,
        "grade": None,
        "source": answer.source,
        "outcome": answer.outcome,
        "tries": answer.tries,
        "failures": list(answer.failures),
        "functions": list(answer.functions),
        "suggested_parameters": answer.suggested_parameters,
        "removed_objects": answer.removed_objects,
        "scrubbed": answer.scrubbed,
        "tool_turns": answer.tool_turns,
        "tool_calls": [dict(c) for c in answer.evidence.tool_calls],
        "records_seen": list(answer.evidence.records),
        "search_hits": list(answer.evidence.search_hits),
        "proposals": [dict(p) for p in answer.evidence.proposals],
        "model_calls": answer.model_calls,
        "usage": {k: int(answer.usage.get(k, 0)) for k in USAGE_KEYS},
        "cost_usd": answer.cost,
        "call_latencies_s": [round(r.latency, 3) for r in client.replies],
        "latency_s": wall,  # what a visitor waits: retries and sleeps included
        "wall_s": wall,
        "retries": retries[0],
        "trace": client.trace(),
    }
    if live:
        row["grade"] = grade_row(case, row, {e["name"]: e for e in catalogue})
    return "result", row


def run_offline(
    case: dict[str, Any], rep: int, kind: str, catalogue: list[dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    """The oracle (the answer of a correct agent, built from the tool results) or null (an empty answer,
    no tool calls): no API call, no cost."""
    if kind == "oracle":
        done = oracle_run(case, catalogue)
    else:
        done = {
            "text": "",
            "tool_calls": [],
            "records_seen": [],
            "search_hits": [],
            "proposals": [],
        }
    row: dict[str, Any] = {
        "case_id": case["id"],
        "rep": rep,
        "category": case["category"],
        "in_scope": case["in_scope"],
        "model": kind,
        "served_model": kind,
        "status": "ok",
        "stop_reason": "end_turn",
        "scrubbed": 0,
        "tool_turns": len({c["name"] for c in done["tool_calls"]}),
        "model_calls": 0,
        "usage": dict.fromkeys(USAGE_KEYS, 0),
        "cost_usd": 0.0,
        "call_latencies_s": [],
        "latency_s": 0.0,
        "wall_s": 0.0,
        "retries": 0,
        "trace": [{"role": "assistant", "content": done["text"]}],
        **done,
    }
    row["grade"] = grade_row(case, row, {e["name"]: e for e in catalogue})
    return "result", row


def pipeline_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """What only a pipeline run has: how answers were served, and why some fell back to static text.

    Empty for a raw or offline run (their rows have no `source`). `checks_failed_on_the_way` counts, by check
    name, the checks that failed on the way (the first draft, and the retry if there was one), over all rows.
    `examples_attached` is the answers that carry a validated example for the widget;
    `category_d_bare_denials` is the category D live answers that open with an ungrounded flat denial (the mode
    of results 9.27, counted with `typed_graders.bare_denial`, which is not a gate);
    `answers_with_objects_removed` is the answers where the model wrote a JSON object anyway;
    `examples_with_empty_required_values` is the case ids whose attached example gives a required parameter an
    empty object, list or string or a bare placeholder word (results 9.32, F3; a diagnostic, not a check).
    """
    piped = [r for r in rows if "source" in r]
    if not piped:
        return {}
    entries = {e["name"]: e for e in load_catalogue()}
    in_scope = [r for r in piped if r["in_scope"]]
    failures: dict[str, int] = {}
    for r in piped:
        for name in r["failures"]:
            failures[name] = failures.get(name, 0) + 1

    def counts(group: list[dict[str, Any]], key: str) -> dict[str, int]:
        return {v: sum(1 for r in group if r[key] == v) for v in sorted({r[key] for r in group})}

    return {
        "pipeline": True,
        "served": counts(piped, "source"),
        "served_in_scope": counts(in_scope, "source"),
        "outcomes": counts(piped, "outcome"),
        "outcomes_in_scope": counts(in_scope, "outcome"),
        "static_rate": round(sum(1 for r in piped if r["source"] == "static") / len(piped), 4),
        "static_rate_in_scope": (
            round(sum(1 for r in in_scope if r["source"] == "static") / len(in_scope), 4)
            if in_scope
            else 0.0
        ),
        "second_try_rate": round(sum(1 for r in piped if r["tries"] >= 2) / len(piped), 4),
        "examples_attached": sum(1 for r in piped if r.get("suggested_parameters")),
        "category_d_live": sum(1 for r in piped if r["category"] == "D" and r["source"] == "live"),
        "category_d_bare_denials": sorted(
            r["case_id"]
            for r in piped
            if r["category"] == "D" and r["source"] == "live" and bare_denial(r["text"])
        ),
        "answers_with_objects_removed": sum(1 for r in piped if r.get("removed_objects")),
        "examples_with_empty_required_values": sorted(
            r["case_id"]
            for r in piped
            if r.get("suggested_parameters")
            and r["suggested_parameters"]["function"] in entries
            and empty_required_values(
                entries[r["suggested_parameters"]["function"]], r["suggested_parameters"]["values"]
            )
        ),
        "checks_failed_on_the_way": dict(sorted(failures.items(), key=lambda kv: -kv[1])),
    }


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
        **pipeline_block(rows),
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
    parser.add_argument("--case-timeout", type=float, default=240.0, help="raw loop only")
    parser.add_argument("--max-usd", type=float, default=5.0, help="hard spend cap for this run")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="the first run's loop (no guardrails, no retry) instead of the shipped pipeline",
    )
    parser.add_argument(
        "--case-max-usd",
        type=float,
        default=DEFAULT_MAX_USD,
        help="pipeline: dollars one question may spend (default: the production cap)",
    )
    parser.add_argument(
        "--case-max-seconds",
        type=float,
        default=DEFAULT_MAX_SECONDS,
        help="pipeline: seconds one question may take (default: the production cap)",
    )
    parser.add_argument(
        "--oracle",
        action="store_true",
        help="no API: the answer of a correct agent, from the tools",
    )
    parser.add_argument("--null", action="store_true", help="no API: empty answers")
    args = parser.parse_args()
    offline = "oracle" if args.oracle else "null" if args.null else None

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

    client = None
    if offline is None:
        import anthropic  # imported late: the tests and the offline baselines need no SDK

        client = anthropic.Anthropic(max_retries=0, timeout=90.0 if args.raw else DEFAULT_TIMEOUT_S)

    def make_client(sleep: Callable[[float], None]) -> ModelClient:
        # the production client over the one SDK client: same retries, served-model check and cost
        return AnthropicClient(sdk_client=client, sleep=sleep)

    budget = Budget(args.max_usd)
    lock = threading.Lock()
    errors: list[dict[str, Any]] = []
    skipped = 0
    stop = (
        threading.Event()
    )  # set on an auth or billing error: every later case is skipped, not retried

    def work(job: tuple[dict[str, Any], int]) -> None:
        nonlocal skipped
        case, rep = job
        if offline:
            kind, row = run_offline(case, rep, offline, catalogue)
        elif stop.is_set():
            kind, row = "skipped", {"case_id": case["id"], "rep": rep, "reason": "stopped"}
        elif args.raw:
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
        else:
            kind, row = run_case_pipeline(
                make_client,
                case,
                args.model,
                rep,
                catalogue=catalogue,
                budget=budget,
                max_usd=args.case_max_usd,
                max_seconds=args.case_max_seconds,
                effort=args.effort,
            )
        if kind == "error" and row["failure_class"] == "auth_or_billing":
            stop.set()
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

"""The guarded answer to one typed question: scrub, agent, grade, one retry, static fallback (plan 7).

Reasoning:
- `answer_question` is the whole production path below the HTTP route. It never raises for a model problem and
  never returns an answer that failed its checks: either the agent's text passed `typed_graders.grade_typed`
  (the first try, or after one retry that shows the model its failed checks), or the visitor gets static text
  built from the catalogue and the committed bank, marked `source: "static"`. So an outage, a refusal, a cap
  or a bad draft all end in the same place, an honest answer from fixed text, with no stack trace and no
  unchecked model output.
- Order, as in the plan: scrub the question (a key never reaches a model) -> the agent's tool loop -> the
  typed grader (identifiers known, numbers supported, no advice or verdict, visitor wording, no absence claims,
  no source claims, no key-like string, shown example values accepted by the validator, length, and English
  only, decided 2026-11-12) -> optionally one more check from the caller (`extra_check`, the enterprise gate: a
  different model reads question, tool results and answer) -> if anything failed, one revision that tells the
  model the failed checks -> graded again -> static.
- Example values are the gateway's job, not the model's (results 9.28). The model is told not to write them; if it
  writes a JSON object anyway the object is taken out of the text BEFORE the text is graded, so what is graded is
  what is served, and the validated example (the last `propose_parameters` call that was accepted) is attached as
  `suggested_parameters` for the widget to show. A model that wrote values without ever getting them accepted has
  promised an example that does not exist: that is a failed check ("example_without_check"), and the retry says
  so. This replaces the old requirement that the model copy accepted values into its text exactly, which failed
  in all nine static answers of run D.
- Static text comes first from the bank (the function's `explain` answer, a complete manifest only), else from
  the catalogue's summary, plus a catalogue link; the function is the page the visitor is on, else the first
  function the agent read, else the first it found. The text never claims more than the catalogue says.
- Counted, never recorded: the structured log line carries the outcome, tries, calls, tool turns, dollars,
  seconds and the names of failed checks. It never carries the question, the answer or a tool result.
- Not here: quotas, auth, the daily token cap and pins (the gateway and the watchdog), and the harness
  measurement (the next run drives this function with `AnthropicClient`).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from assistant import bank
from assistant.agent import (
    DEFAULT_MAX_SECONDS,
    DEFAULT_MAX_USD,
    MAX_HISTORY_TURNS,
    AgentRun,
    TypedAgent,
)
from assistant.client import ModelCallError, ModelClient
from assistant.prompts import EFFORT
from assistant.scrub import has_secret, scrub_secrets
from assistant.tools import ToolBox
from assistant.typed_graders import grade_typed, strip_example_objects

logger = structlog.get_logger()

# What the production grader expects of every answer (grade_typed's generic checks always run).
EXPECT: dict[str, Any] = {"english": True}

LIVE = "live"
STATIC = "static"
OUTCOME_LIVE = "live"
OUTCOME_LIVE_AFTER_RETRY = "live_after_retry"
OUTCOME_STATIC_GRADER = "static_grader"
OUTCOME_STATIC_ERROR = "static_error"
OUTCOME_STATIC_SECRET = "static_secret"

# What to tell the model when a run did not end on a usable answer.
STATUS_FLAGS = {
    "truncated": "the reply was cut off at the token limit: write a shorter answer",
    "refusal": "the reply was a refusal: answer from the tool results, or decline in words",
    "empty": "the reply was empty: write the answer",
}
NO_RETRY = frozenset({"budget", "timeout", "tool_limit"})
EXAMPLE_WITHOUT_CHECK = "example_without_check"
EXAMPLE_WITHOUT_CHECK_FLAG = (
    "you wrote example values without a propose_parameters call that accepted them: call propose_parameters, "
    "and the portal will show the checked example under your answer; never write the values yourself"
)

SECRET_TEXT = (
    "Your message looked like it contained a key or token, so it was not sent anywhere. "
    "Remove it and ask again."
)
GENERIC_TEXT = (
    "I couldn't give you a reliable answer to that. You can browse every pyvar function by domain on "
    "the portal (/), or ask about one function by name."
)

ExtraCheck = Callable[[str, str, ToolBox], list[str]]


@dataclass(frozen=True)
class Evidence:
    """What the tools returned for one question, as names and the model's own calls, never tool text.

    The measurement harness (scripts/assistant_eval/run_typed.py) grades and judges the served answer against
    exactly this evidence, so it needs it without re-running anything. The gateway ignores it. Nothing here is
    logged.

    Attributes:
        tool_calls: every tool call as {"name", "input", "ok"}.
        records: names of the functions `get_function` returned.
        search_hits: names of the functions `search_functions` returned.
        proposals: every `propose_parameters` call as {"name", "values", "ok"}.
    """

    tool_calls: tuple[dict[str, Any], ...] = ()
    records: tuple[str, ...] = ()
    search_hits: tuple[str, ...] = ()
    proposals: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Answer:
    """The guarded answer to one question.

    Attributes:
        text: what the visitor sees.
        source: "live" (the model's text, checked) or "static" (fixed text from the catalogue and the bank).
        outcome: "live", "live_after_retry", "static_grader" (or "static_<status>" when the last run ended
            on a refusal, a cut-off, an empty reply, a cap or the tool limit), "static_error" (the provider
            failed for good) or "static_secret".
        functions: catalogue names the answer is about, at most five, in order of appearance.
        suggested_parameters: {"function", "values"} of the last validated example (an accepted
            `propose_parameters` call) for a live answer, else None; the widget shows it under the answer.
        tries: agent passes made (0 when no model was called).
        model_calls, tool_turns: totals over all passes.
        cost: dollars, all calls.
        latency_s: seconds of model calls.
        served: the model id that served the last call ("" if none).
        failures: names of the checks that failed on the way (never text).
        scrubbed: key-like strings removed from the question.
        usage: token counts, all calls.
        evidence: what the tools returned (names and calls); empty when no model was called.
        removed_objects: JSON objects the model wrote that were taken out of `text` (the validated example is
            attached as `suggested_parameters` instead).
    """

    text: str
    source: str
    outcome: str
    functions: tuple[str, ...]
    suggested_parameters: dict[str, Any] | None
    tries: int
    model_calls: int
    tool_turns: int
    cost: float
    latency_s: float
    served: str
    failures: tuple[str, ...]
    scrubbed: int
    usage: dict[str, int]
    evidence: Evidence = Evidence()
    removed_objects: int = 0


def bank_text(bank_dir: Path | None, function: str) -> str | None:
    """The committed bank's `explain` answer for `function`, or None (no bank, incomplete, or no entry)."""
    if bank_dir is None:
        return None
    manifest = bank.read_manifest(bank_dir)
    if not manifest or manifest.get("complete") is not True:
        return None
    version = str(manifest.get("bank_version", ""))
    if not version or not set(version) <= bank.SAFE_VERSION_CHARS:
        return None
    entry = bank.read_function_file(bank_dir / version, function).get((function, "explain", None))
    text = entry.get("text") if entry else None
    return text if isinstance(text, str) and text.strip() else None


def static_text(
    by_name: dict[str, dict[str, Any]], function: str | None, bank_dir: Path | None
) -> str:
    """Fixed text for a question that got no checked live answer."""
    if function is None or function not in by_name:
        return GENERIC_TEXT
    entry = by_name[function]
    body = bank_text(bank_dir, function) or f"{entry['display_name']}: {entry['summary']}"
    return (
        f"I couldn't give you a reliable answer to that, so here is what pyvar says about "
        f"`{function}`.\n\n{body}\n\nSee it in the catalogue: /{entry['domain_page']}#{function}"
    )


def _clean_history(history: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """Valid (question, answer) pairs only, scrubbed, the last MAX_HISTORY_TURNS of them."""
    turns: list[tuple[str, str]] = []
    for item in history:
        if (
            isinstance(item, (tuple, list))
            and len(item) == 2
            and isinstance(item[0], str)
            and isinstance(item[1], str)
        ):
            turns.append((scrub_secrets(item[0])[0], scrub_secrets(item[1])[0]))
    return turns[-MAX_HISTORY_TURNS:]


@dataclass(frozen=True)
class Verdict:
    """The outcome of checking one run.

    Attributes:
        failures: names of the checks that failed (empty for a good answer).
        flags: what to tell the model if it gets a second try.
        text: the text that was graded and, if the run is good, the text that is served: the model's text with
            any JSON object it wrote taken out.
        removed: how many objects were taken out.
    """

    failures: list[str]
    flags: list[str]
    text: str
    removed: int = 0


def _verdict(
    agent: TypedAgent,
    run: AgentRun,
    question: str,
    page: str | None,
    display_names: dict[str, str],
    extra_check: ExtraCheck | None,
) -> Verdict:
    """Check one run: strip example objects, grade the stripped text, ask the optional second reader."""
    if run.status != "ok":
        return Verdict(
            [run.status], [STATUS_FLAGS.get(run.status, f"the run ended: {run.status}")], run.text
        )
    box = agent.toolbox
    text, removed = strip_example_objects(run.text)
    grade = grade_typed(
        text,
        box.records,
        question,
        expect=EXPECT,
        search_hits=box.search_hits,
        tool_calls=box.calls,
        proposals=box.proposals,
        page_function=page,
        display_names=display_names,
    )
    failures = [name for name, ok in grade.checks.items() if not ok]
    flags = list(grade.flags)
    if removed and _suggestion(box) is None:
        failures.append(EXAMPLE_WITHOUT_CHECK)
        flags.append(EXAMPLE_WITHOUT_CHECK_FLAG)
    if extra_check is not None:
        extra = extra_check(question, text, box)
        if extra:
            failures.append("gate")
            flags += extra
    return Verdict(failures, flags, text, removed)


def _cited(text: str, box: ToolBox, page: str | None) -> tuple[str, ...]:
    """Catalogue names `text` is about (a function the agent read, found or was asked on), in order."""
    names = {*box.records, *box.search_views, *([page] if page else [])}
    lower = text.lower()
    found: list[tuple[int, str]] = []
    for name in names:
        display = box.entries[name]["display_name"].lower() if name in box.entries else ""
        spots = [i for i in (text.find(name), lower.find(display) if display else -1) if i >= 0]
        if spots:
            found.append((min(spots), name))
    return tuple(name for _, name in sorted(found))[:5]


def _suggestion(box: ToolBox) -> dict[str, Any] | None:
    """The last example `propose_parameters` accepted: {"function", "values"}, or None.

    Validated by the tool (the bounds and types the catalogue states), so the widget can offer it as it is.
    """
    for proposal in reversed(box.proposals):
        if proposal.get("ok"):
            return {"function": proposal["name"], "values": proposal["values"]}
    return None


def answer_question(
    client: ModelClient,
    model: str,
    question: str,
    *,
    catalogue: list[dict[str, Any]],
    page_function: str | None = None,
    history: Sequence[tuple[str, str]] = (),
    bank_dir: Path | None = None,
    max_usd: float = DEFAULT_MAX_USD,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    effort: str = EFFORT,
    extra_check: ExtraCheck | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Answer:
    """Answer one visitor question, live if the answer passes its checks, otherwise from static text.

    Args:
        client: the model client.
        model: the model id for this visitor's tier.
        question: the visitor's question as typed (the caller has bounded its length).
        catalogue: the entries of portal/functions.json.
        page_function: the catalogue name of the function page the visitor is on; anything else is ignored.
        history: up to three earlier (question, answer) pairs from the browser; scrubbed and treated as data.
        bank_dir: the answer bank's root (portal/assistant/bank) for static text, or None.
        max_usd: dollars this question may spend in all.
        max_seconds: wall-clock seconds this question may take.
        effort: the `output_config.effort` level.
        extra_check: an optional second reader (the enterprise gate): given the scrubbed question, the answer
            and the ToolBox, it returns problems to fix, or an empty list.
        clock: monotonic seconds; a test passes a fake.

    Returns:
        An Answer. It is never a model failure: those become static text with `source: "static"`.

    Raises:
        ValueError: the question is empty after trimming.
    """
    cleaned, scrubbed = scrub_secrets(question.strip())
    if not cleaned:
        raise ValueError("the question is empty")
    by_name = {e["name"]: e for e in catalogue}
    display_names = {n: e["display_name"] for n, e in by_name.items()}
    page = page_function if isinstance(page_function, str) and page_function in by_name else None

    def finish(
        text: str,
        source: str,
        outcome: str,
        *,
        agent: TypedAgent | None = None,
        run: AgentRun | None = None,
        tries: int = 0,
        failures: list[str] | None = None,
        tool_turns: int = 0,
        removed: int = 0,
    ) -> Answer:
        box = agent.toolbox if agent else None
        functions = _cited(text, box, page) if box and source == LIVE else ()
        answer = Answer(
            text=text,
            source=source,
            outcome=outcome,
            functions=functions,
            suggested_parameters=_suggestion(box) if box and source == LIVE else None,
            tries=tries,
            model_calls=agent.model_calls if agent else 0,
            tool_turns=tool_turns,
            cost=round(agent.cost, 6) if agent else 0.0,
            latency_s=round(agent.latency_s, 3) if agent else 0.0,
            served=run.served if run else "",
            failures=tuple(dict.fromkeys(failures or [])),
            scrubbed=scrubbed,
            usage=dict(agent.usage) if agent else {},
            evidence=(
                Evidence(
                    tool_calls=tuple(dict(c) for c in box.calls),
                    records=tuple(sorted(box.records)),
                    search_hits=tuple(sorted(box.search_hits)),
                    proposals=tuple(dict(p) for p in box.proposals),
                )
                if box
                else Evidence()
            ),
            removed_objects=removed if source == LIVE else 0,
        )
        logger.info(
            "typed_answer",
            outcome=outcome,
            source=source,
            tries=tries,
            model_calls=answer.model_calls,
            tool_turns=tool_turns,
            cost_usd=answer.cost,
            latency_s=answer.latency_s,
            failures=list(answer.failures),
            functions=len(functions),
            scrubbed=scrubbed,
            removed_objects=answer.removed_objects,
            model=answer.served,
        )
        return answer

    if has_secret(cleaned):  # a safety net: scrub_secrets removes everything this looks for
        return finish(SECRET_TEXT, STATIC, OUTCOME_STATIC_SECRET)

    agent = TypedAgent(
        client,
        model,
        catalogue,
        effort=effort,
        max_usd=max_usd,
        max_seconds=max_seconds,
        clock=clock,
    )
    tries, tool_turns = 0, 0
    failures: list[str] = []
    run: AgentRun | None = None

    def fallback(outcome: str) -> Answer:
        box = agent.toolbox
        function = page or next(iter(box.records), None) or next(iter(box.search_views), None)
        return finish(
            static_text(by_name, function, bank_dir),
            STATIC,
            outcome,
            agent=agent,
            run=run,
            tries=tries,
            failures=failures,
            tool_turns=tool_turns,
        )

    try:
        run = agent.ask(cleaned, page, _clean_history(history))
        tries, tool_turns = 1, run.tool_turns
        verdict = _verdict(agent, run, cleaned, page, display_names, extra_check)
        outcome = OUTCOME_LIVE
        if verdict.failures:
            failures += verdict.failures
            if run.status in NO_RETRY:
                return fallback(f"static_{run.status}")
            run = agent.revise(run, verdict.flags)
            tries, tool_turns = 2, tool_turns + run.tool_turns
            verdict = _verdict(agent, run, cleaned, page, display_names, extra_check)
            outcome = OUTCOME_LIVE_AFTER_RETRY
            if verdict.failures:
                failures += verdict.failures
                return fallback(
                    OUTCOME_STATIC_GRADER if run.status == "ok" else f"static_{run.status}"
                )
    except ModelCallError as exc:  # the client has already retried a transient error
        logger.warning("typed_answer_model_error", error=type(exc).__name__)
        failures.append("model_error")
        return fallback(OUTCOME_STATIC_ERROR)
    assert run is not None  # a pass that ended in a good answer
    return finish(
        verdict.text,
        LIVE,
        outcome,
        agent=agent,
        run=run,
        tries=tries,
        failures=failures,
        tool_turns=tool_turns,
        removed=verdict.removed,
    )


__all__ = [
    "Answer",
    "Evidence",
    "ExtraCheck",
    "Verdict",
    "answer_question",
    "bank_text",
    "static_text",
]

"""The answer bank: every menu answer (explain, when, compare) written once, checked, and committed as files.

Reasoning:
- The portal's menus have a fixed set of questions, so the answers are written ahead of time and served as
  static files; no model is called when a visitor clicks. This module builds those files and checks them.
  The design and the measurements behind it: docs/assistant-plan-implementation.md (sections 5 and 6) and
  docs/assistant-phase0-results.md 9.17 to 9.19.
- Pipeline per answer, as measured in run C: the writer (Sonnet 5.5) writes; the programmatic graders check; a
  failure sends the failing checks back to the writer, up to three calls in all; then the gate (Opus 5.5) reads
  the text against the record. A gate flag is rewritten once by the escalation model (Opus), with the gate's
  issues as feedback, graded again and gated again. Whatever still fails becomes static text built from the
  record (static_text.py), marked `source: "static"`, so the bank has an answer for every question and no
  answer is unchecked.
- Files: <out>/<bank_version>/<function>.json holds {"explain", "when", "compare": {<sibling>: entry}} and
  <out>/manifest.json says what built them. bank_version is "<prompt_version>-<first 8 of catalogue_sha256>",
  so a catalogue edit starts a new directory and the old one stays for rollback. An entry carries the sha256 of
  the part of the record it was written from, so a single edited function is found by name.
- A build is incremental and resumable: an entry whose record hash, prompt version and grader hash are unchanged
  is kept (from the previous version's directory or from an interrupted build of this one), so a catalogue edit
  costs pennies and a crashed build loses nothing. Every function file and the manifest are written atomically
  (temp file, then os.replace).
- The money cap is hard: before each call the worst-case cost of that call (the prompt at a deliberately high
  token estimate plus max_tokens at the output price) is reserved against --max-usd; a call that does not fit
  is not made, the build stops with complete=false and a later run resumes. (The answer being written at that
  moment may have paid for a draft whose gate call then did not fit; that one draft is written again later.)
- The order is deterministic (functions by name, actions explain, when, compare). With one worker a run is fully
  reproducible; with more, the output of each function is the same but the point where a budget stop falls is not.
- `--redo-ids FILE` rewrites named answers once, in place: the file maps an answer id (function:action or
  function:compare:sibling) to the notes a reader or the gate made about it. The writer is shown its old answer
  and the notes (the way the escalation step is), then the usual graders, gate and escalation run. A redo never
  makes an answer worse: if the rewrite would end as static text, or a call fails, or the budget stops, the old
  entry stays. Nothing else in the bank is touched.
- `check` needs no API: manifest and record hashes against the live catalogue, every served answer re-graded,
  size bounds, and a static share under 3%.
- Nothing in a log line or on stdout is answer text: events carry function names, actions, counts and dollars.
- Run: python -m assistant.bank build --max-usd 20 | check. The bank files are written by this CLI only; never
  edit one by hand (CLAUDE.md section 3.6).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib
import json
import os
import sys
import tempfile
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from assistant import graders, prompts
from assistant.client import ModelCallError, ModelClient, Reply, ServedModelMismatch
from assistant.cost import PRICES
from assistant.gate import Verdict, gate
from assistant.static_text import static_answer

logger = structlog.get_logger()

REPO = Path(__file__).resolve().parents[1]
CATALOGUE_PATH = REPO / "portal" / "functions.json"
DEFAULT_BANK_DIR = REPO / "portal" / "assistant" / "bank"
ACTIONS = ("explain", "when", "compare")
MAX_WRITER_TRIES = 3
MAX_CALL_FAILURES = 10  # entries that failed on a model-call error before a build gives up
MAX_FILE_BYTES = 16_384
MAX_BANK_BYTES = 4_000_000
MAX_STATIC_SHARE = 0.03
SAFE_VERSION_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
UNSUPPORTED_NOTE = "a claim the function's documentation does not support"

# (function, action, sibling or None): the address of one answer
Key = tuple[str, str, str | None]


class BudgetExhausted(Exception):
    """The next model call does not fit inside --max-usd."""


# ── provenance ───────────────────────────────────────────────────────────────────────────────────────────


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def catalogue_sha256(path: Path = CATALOGUE_PATH) -> str:
    """sha256 of portal/functions.json, byte for byte."""
    return _sha256_bytes(path.read_bytes())


def grader_sha256() -> str:
    """sha256 of assistant/graders.py: any edit to the graders invalidates a built bank."""
    return _sha256_bytes((REPO / "assistant" / "graders.py").read_bytes())


def prompt_sha256() -> str:
    """sha256 of the model-facing text (system prompt, task sentences, character budgets).

    PROMPT_VERSION is bumped by hand; this hash catches an edit that forgot to bump it.
    """
    material = {
        "system": prompts.SYSTEM_PROMPT,
        "tasks": prompts.TASKS,
        "char_budget": prompts.CHAR_BUDGET,
    }
    return _sha256_bytes(json.dumps(material, sort_keys=True).encode())


def bank_version(catalogue_hash: str) -> str:
    """ "<prompt_version>-<first 8 of the catalogue hash>": the directory name and the cache key."""
    return f"{prompts.PROMPT_VERSION}-{catalogue_hash[:8]}"


def record_sha256(case: dict[str, Any]) -> str:
    """sha256 of the material an answer is written from: the record, plus the sibling list for `when`
    and `compare`, plus the compared record for `compare` (exactly what the writer is shown)."""
    material: dict[str, Any] = {"record": case["record"]}
    if case["intent"] in ("when", "compare"):
        material["siblings"] = case.get("siblings") or []
    if case["intent"] == "compare":
        material["other"] = case["other"]
    return _sha256_bytes(json.dumps(material, sort_keys=True, ensure_ascii=False).encode())


# ── cases ────────────────────────────────────────────────────────────────────────────────────────────────


class _AnySchema(dict[str, Any]):
    """The case builder wants a request schema per function for the example action; the bank has none."""

    def __missing__(self, key: str) -> dict[str, Any]:
        return {}


def case_key(case: dict[str, Any]) -> Key:
    """(function, action, sibling) of a text case; sibling is the compared function for `compare`."""
    other = case["other"]["name"] if case["intent"] == "compare" else None
    return (case["record"]["name"], case["intent"], other)


def case_id(key: Key) -> str:
    """The id of an answer as the redo file and the reports write it: function:action[:sibling]."""
    function, action, sibling = key
    return f"{function}:{action}:{sibling}" if sibling else f"{function}:{action}"


def load_redo(path: Path) -> dict[str, list[str]]:
    """Read a redo file: a JSON object mapping an answer id to a non-empty list of notes.

    Args:
        path: the JSON file.

    Returns:
        {answer id: [note, ...]}.

    Raises:
        ValueError: the file is not an object, is empty, or an id has no notes.
    """
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or not raw:
        raise ValueError(
            "a redo file is a JSON object {answer id: [note, ...]} with at least one id"
        )
    notes: dict[str, list[str]] = {}
    for answer_id, value in raw.items():
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(n, str) and n.strip() for n in value)
        ):
            raise ValueError(f"redo {answer_id!r}: give a non-empty list of notes")
        notes[str(answer_id)] = [n.strip() for n in value]
    return notes


def load_text_cases(catalogue_path: Path = CATALOGUE_PATH) -> list[dict[str, Any]]:
    """The 1,154 text cases of `cases.py --all` (explain, when, compare), in build order.

    Args:
        catalogue_path: the catalogue to build from (portal/functions.json).

    Returns:
        Case dicts sorted by function name, then explain, when, compare.
    """
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    builder = importlib.import_module("scripts.assistant_eval.cases")
    catalogue = json.loads(catalogue_path.read_text())
    built = builder.build_cases(
        catalogue, builder.load_specs(), _AnySchema(), per_domain=None, pairs=10_000
    )
    text = [c for c in built if c["intent"] in ACTIONS]
    return sorted(text, key=lambda c: (c["record"]["name"], ACTIONS.index(c["intent"])))


# ── money ────────────────────────────────────────────────────────────────────────────────────────────────


def estimate_cost(model: str, request: dict[str, Any]) -> float:
    """A cost the call cannot exceed: the prompt at 1 token per 2 characters (real text runs 3 to 4) plus
    max_tokens at the output price (thinking counts inside max_tokens)."""
    price = PRICES[model]
    prompt_tokens = len(json.dumps(request)) / 2 + 50
    return (prompt_tokens * price.input + int(request["max_tokens"]) * price.output) * 1e-6


class Budget:
    """A thread-safe spend cap that reserves the worst case before a call."""

    def __init__(self, cap_usd: float) -> None:
        self.cap = cap_usd
        self.spent = 0.0
        self._reserved = 0.0
        self._lock = threading.Lock()

    def reserve(self, amount: float) -> bool:
        """Set `amount` aside; False (and nothing reserved) if spent + reserved + amount > cap."""
        with self._lock:
            if self.spent + self._reserved + amount > self.cap:
                return False
            self._reserved += amount
            return True

    def settle(self, reserved: float, actual: float) -> None:
        """Release a reservation and book what the call really cost."""
        with self._lock:
            self._reserved -= reserved
            self.spent += actual


class MeteredClient:
    """A ModelClient that books every call against a Budget and refuses a call that does not fit."""

    def __init__(self, inner: ModelClient, budget: Budget) -> None:
        self._inner = inner
        self._budget = budget

    def complete(self, model: str, request: dict[str, Any]) -> Reply:
        """Make the call if its worst-case cost fits the budget.

        Raises:
            BudgetExhausted: if it does not fit; no call is made.
        """
        estimate = estimate_cost(model, request)
        if not self._budget.reserve(estimate):
            raise BudgetExhausted(f"a {model} call (up to ${estimate:.4f}) does not fit")
        try:
            reply = self._inner.complete(model, request)
        except BaseException:
            self._budget.settle(estimate, 0.0)
            raise
        self._budget.settle(estimate, reply.cost)
        return reply


# ── one answer ───────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Models:
    """The three model ids a build uses."""

    writer: str
    gate: str
    escalation: str


def _feedback_flags(case: dict[str, Any], grade: graders.Grade) -> list[str]:
    """What to tell the writer: the grader's flags, plus a line for a failed check that raises none."""
    flags = list(grade.flags)
    record = case["record"]
    if not grade.checks.get("mentions_function", True):
        flags.append(f"name the function ({record['display_name']} or `{record['name']}`)")
    if not grade.checks.get("mentions_other", True):
        flags.append(f"name both functions (also {case['other']['display_name']})")
    if not flags:
        flags = ["failed checks: " + ", ".join(k for k, ok in grade.checks.items() if not ok)]
    return flags


def _stop_problem(reply: Reply) -> str | None:
    if reply.stop_reason == "max_tokens":
        return "the reply was cut off at the token limit: write a shorter answer"
    if reply.stop_reason == "refusal":
        return "the reply was a refusal: answer from the function's documentation"
    return None


def _entry(
    case: dict[str, Any],
    text: str,
    *,
    source: str,
    writer: str,
    tries: int,
    escalated: bool,
    verdict: Verdict | None,
) -> dict[str, Any]:
    return {
        "text": text,
        "source": source,
        "writer": writer,
        "tries": tries,
        "escalated": escalated,
        "gate": {
            "faithful": verdict.faithful if verdict is not None else None,
            "issues": list(verdict.issues) if verdict is not None else [],
        },
        "record_sha256": record_sha256(case),
    }


def _static_entry(case: dict[str, Any], tries: int, escalated: bool) -> dict[str, Any]:
    return _entry(
        case,
        static_answer(case),
        source="static",
        writer="static",
        tries=tries,
        escalated=escalated,
        verdict=None,
    )


def build_entry(
    client: ModelClient,
    case: dict[str, Any],
    models: Models,
    revise: tuple[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Produce the bank entry for one text case.

    Args:
        client: the model client (already wrapped in a MeteredClient by a build).
        case: one text case (explain, when or compare).
        models: the writer, gate and escalation model ids.
        revise: (the old answer, the notes about it) for a redo: the writer is shown both before its
            first draft, the way the escalation step shows the gate's issues.

    Returns:
        The entry dict: text, source ("model" or "static"), writer, tries, escalated, gate, record_sha256.

    Raises:
        BudgetExhausted: if a call does not fit the budget.
        ModelCallError: if a model call fails for good (the caller skips this entry).
    """
    feedback: list[tuple[str, list[str]]] = []
    if revise is not None:
        old_text, notes = revise
        feedback.append((old_text, [f"a reviewer found: {note}" for note in notes]))
    tries = 0
    text: str | None = None
    for _ in range(MAX_WRITER_TRIES):
        tries += 1
        reply = client.complete(models.writer, prompts.build_request(case, feedback))
        candidate = reply.text.strip()
        problem = _stop_problem(reply)
        if problem is not None:
            flags = [problem]
        else:
            grade = graders.grade(case, candidate)
            if grade.passed:
                text = candidate
                break
            flags = _feedback_flags(case, grade)
        if candidate:  # an empty reply cannot be replayed as an assistant turn
            feedback.append((candidate, flags))
    if text is None:
        return _static_entry(case, tries, escalated=False)

    verdict = gate(client, case, text, model=models.gate)
    if verdict.faithful:
        return _entry(
            case,
            text,
            source="model",
            writer=models.writer,
            tries=tries,
            escalated=False,
            verdict=verdict,
        )

    notes = verdict.issues or [UNSUPPORTED_NOTE]
    flags = [f"a reviewer found: {note}" for note in notes]
    reply = client.complete(models.escalation, prompts.build_request(case, [(text, flags)]))
    rewrite = reply.text.strip()
    if _stop_problem(reply) is None and graders.grade(case, rewrite).passed:
        second = gate(client, case, rewrite, model=models.gate)
        if second.faithful:
            return _entry(
                case,
                rewrite,
                source="model",
                writer=models.escalation,
                tries=tries,
                escalated=True,
                verdict=second,
            )
    return _static_entry(case, tries, escalated=True)


# ── files ────────────────────────────────────────────────────────────────────────────────────────────────


def _atomic_write(path: Path, content: str) -> None:
    """Write `content` to `path` so that a reader sees the old file or the new one, never half."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def entries_to_file(entries: dict[Key, dict[str, Any]]) -> dict[str, Any]:
    """The {"explain", "when", "compare": {sibling: entry}} shape of one function file."""
    body: dict[str, Any] = {}
    for (_, action, sibling), entry in entries.items():
        if action == "compare":
            body.setdefault("compare", {})[sibling] = entry
        else:
            body[action] = entry
    return body


def file_to_entries(function: str, body: Any) -> dict[Key, dict[str, Any]]:
    """The inverse of entries_to_file; anything that is not that shape reads as no entries."""
    entries: dict[Key, dict[str, Any]] = {}
    if not isinstance(body, dict):
        return entries
    for action in ("explain", "when"):
        if isinstance(body.get(action), dict):
            entries[(function, action, None)] = body[action]
    compare = body.get("compare")
    if isinstance(compare, dict):
        for sibling, entry in compare.items():
            if isinstance(entry, dict):
                entries[(function, "compare", str(sibling))] = entry
    return entries


def read_function_file(directory: Path, function: str) -> dict[Key, dict[str, Any]]:
    """The entries of `<directory>/<function>.json`; a missing or unreadable file has none."""
    try:
        return file_to_entries(function, json.loads((directory / f"{function}.json").read_text()))
    except (OSError, ValueError):
        return {}


def read_manifest(out_dir: Path) -> dict[str, Any] | None:
    """`<out_dir>/manifest.json` as a dict, or None if absent or not a JSON object."""
    try:
        value = json.loads((out_dir / "manifest.json").read_text())
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


# ── build ────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class BuildResult:
    """What a build did."""

    bank_version: str
    complete: bool
    stopped: str | None
    cost_usd: float
    built: int = 0
    reused: int = 0
    failed: int = 0
    missing: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    redone: int = 0  # answers rewritten by --redo-ids
    redo_kept: int = 0  # redo answers whose rewrite would have been static: the old entry stayed


def _counts(entries: list[dict[str, Any]], expected: int) -> dict[str, int]:
    return {
        "model": sum(1 for e in entries if e.get("source") == "model"),
        "static": sum(1 for e in entries if e.get("source") == "static"),
        "regenerated": sum(1 for e in entries if int(e.get("tries", 1)) > 1),
        "escalated": sum(1 for e in entries if e.get("escalated") is True),
        "total": len(entries),
        "expected": expected,
    }


def build(
    client: ModelClient,
    *,
    out_dir: Path,
    models: Models,
    max_usd: float,
    workers: int = 1,
    only_functions: set[str] | None = None,
    retry_static: bool = False,
    redo: dict[str, list[str]] | None = None,
    catalogue_path: Path = CATALOGUE_PATH,
    cases: list[dict[str, Any]] | None = None,
    today: Callable[[], datetime.date] = datetime.date.today,
) -> BuildResult:
    """Build or refresh the bank under `out_dir`.

    Args:
        client: the model client; a build wraps it in a MeteredClient.
        out_dir: the bank root (holds manifest.json and one directory per bank_version).
        models: writer, gate and escalation model ids.
        max_usd: hard cap on spend; a call that might not fit is not made.
        workers: functions built in parallel (1 is fully deterministic).
        only_functions: rebuild only these functions; the others keep their valid entries.
        retry_static: also rewrite entries that are static text (kept by default).
        redo: {answer id: notes}: rewrite these answers once, showing the writer its old answer and the
            notes; the old entry stays if the rewrite would be static, a call fails or the budget stops.
        catalogue_path: the catalogue to build from.
        cases: the text cases (tests pass a few; the CLI builds all 1,154).
        today: the clock for the manifest's build date.

    Returns:
        A BuildResult; `complete` is True only if every expected entry is present.

    Raises:
        ServedModelMismatch: a model other than the requested one answered (the build stops at once;
            the manifest says complete=false).
        ValueError: a model id has no price, or a redo id is not a bank answer.
    """
    for model in (models.writer, models.gate, models.escalation):
        if model not in PRICES:
            raise ValueError(f"no price for model {model!r}: add it to assistant/cost.py")
    cases = load_text_cases(catalogue_path) if cases is None else cases
    if redo:
        unknown = sorted(set(redo) - {case_id(case_key(c)) for c in cases})
        if unknown:
            raise ValueError("redo ids that are not bank answers: " + ", ".join(unknown[:10]))
    cat_hash = catalogue_sha256(catalogue_path)
    version = bank_version(cat_hash)
    provenance = {
        "prompt_version": prompts.PROMPT_VERSION,
        "prompt_sha256": prompt_sha256(),
        "grader_sha256": grader_sha256(),
    }
    previous = read_manifest(out_dir)
    reusable: list[Path] = []
    if previous is not None and all(previous.get(k) == v for k, v in provenance.items()):
        # The manifest also lists where the entries it was started from live, so a build that crashed
        # right after it wrote its first manifest can still be resumed from them.
        listed = previous.get("reusable_from")
        names = [version, str(previous.get("bank_version", ""))]
        names += [str(n) for n in listed] if isinstance(listed, list) else []
        for name in names:
            candidate = out_dir / name
            if name and set(name) <= SAFE_VERSION_CHARS and candidate.is_dir():
                if candidate not in reusable:
                    reusable.append(candidate)
    target = out_dir / version

    by_function: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        by_function.setdefault(case["record"]["name"], []).append(case)
    expected = len(cases)

    budget = Budget(max_usd)
    metered = MeteredClient(client, budget)
    stop = threading.Event()
    state: dict[str, Any] = {"stopped": None, "fatal": None}
    tally = {"built": 0, "reused": 0, "failed": 0, "redone": 0, "redo_kept": 0}
    lock = threading.Lock()

    def manifest(entries: list[dict[str, Any]], complete: bool) -> dict[str, Any]:
        return {
            "bank_version": version,
            **provenance,
            "catalogue_sha256": cat_hash,
            "models": {
                "writer": models.writer,
                "gate": models.gate,
                "escalation": models.escalation,
            },
            "reusable_from": [d.name for d in reusable if d != target],
            "built": today().isoformat(),
            "counts": _counts(entries, expected),
            "complete": complete,
            "stopped": state["stopped"],
            "run_cost_usd": round(budget.spent, 4),
        }

    _atomic_write(out_dir / "manifest.json", _dump(manifest([], False)))

    def process(function: str) -> None:
        function_cases = by_function[function]
        kept: dict[Key, dict[str, Any]] = {}
        old: dict[Key, dict[str, Any]] = {}
        for directory in reversed(reusable):  # the first listed directory wins
            old.update(read_function_file(directory, function))
        may_build = only_functions is None or function in only_functions
        for case in function_cases:
            key = case_key(case)
            existing = old.get(key)
            valid = existing is not None and existing.get("record_sha256") == record_sha256(case)
            notes = redo.get(case_id(key)) if redo else None
            redoing = valid and notes is not None
            if (
                existing is not None
                and valid
                and not redoing
                and not (retry_static and existing.get("source") == "static")
            ):
                kept[key] = existing
                with lock:
                    tally["reused"] += 1
                continue
            fallback = (
                existing if redoing else None
            )  # a redo never loses the answer it started from
            if not may_build or stop.is_set():
                if fallback is not None:
                    kept[key] = fallback
                continue
            revise = (str(fallback["text"]), notes) if fallback is not None and notes else None
            try:
                entry = build_entry(metered, case, models, revise=revise)
            except BudgetExhausted:
                with lock:
                    state["stopped"] = "budget"
                stop.set()
                if fallback is not None:
                    kept[key] = fallback
                continue
            except ServedModelMismatch as exc:
                with lock:
                    state["fatal"] = exc
                stop.set()
                if fallback is not None:
                    kept[key] = fallback
                continue
            except ModelCallError as exc:
                logger.warning(
                    "bank_entry_failed",
                    function=function,
                    action=key[1],
                    error=type(exc).__name__,
                )
                with lock:
                    tally["failed"] += 1
                    if tally["failed"] >= MAX_CALL_FAILURES:
                        state["stopped"] = "errors"
                        stop.set()
                if fallback is not None:
                    kept[key] = fallback
                continue
            if fallback is not None and entry["source"] == "static":
                kept[key] = fallback
                with lock:
                    tally["redo_kept"] += 1
                logger.info("bank_redo_kept_old", function=function, action=key[1], sibling=key[2])
                continue
            kept[key] = entry
            with lock:
                tally["built"] += 1
                if fallback is not None:
                    tally["redone"] += 1
            logger.info(
                "bank_entry_built",
                function=function,
                action=key[1],
                sibling=key[2],
                source=entry["source"],
                tries=entry["tries"],
                escalated=entry["escalated"],
                faithful=entry["gate"]["faithful"],
                redo=fallback is not None,
            )
        if kept:
            _atomic_write(target / f"{function}.json", _dump(entries_to_file(kept)))

    names = sorted(by_function)
    if workers <= 1:
        for function in names:
            process(function)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(process, names))

    final: list[dict[str, Any]] = []
    for function in names:
        final += list(read_function_file(target, function).values())
    complete = len(final) == expected and state["stopped"] is None and state["fatal"] is None
    _atomic_write(out_dir / "manifest.json", _dump(manifest(final, complete)))
    logger.info(
        "bank_build_done",
        bank_version=version,
        complete=complete,
        stopped=state["stopped"],
        cost_usd=round(budget.spent, 4),
        entries=len(final),
        expected=expected,
    )
    if state["fatal"] is not None:
        raise state["fatal"]
    return BuildResult(
        bank_version=version,
        complete=complete,
        stopped=state["stopped"],
        cost_usd=round(budget.spent, 4),
        built=tally["built"],
        reused=tally["reused"],
        failed=tally["failed"],
        missing=expected - len(final),
        counts=_counts(final, expected),
        redone=tally["redone"],
        redo_kept=tally["redo_kept"],
    )


# ── check ────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class CheckReport:
    """The result of `check`: problems (empty when the bank is good) and the numbers it saw."""

    problems: list[str] = field(default_factory=list)
    entries: int = 0
    files: int = 0
    bytes: int = 0
    largest_file: int = 0
    static: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems


def check(
    out_dir: Path,
    *,
    catalogue_path: Path = CATALOGUE_PATH,
    cases: list[dict[str, Any]] | None = None,
) -> CheckReport:
    """Check a built bank against the live catalogue, the live graders and the size bounds. No API call.

    Args:
        out_dir: the bank root.
        catalogue_path: the live catalogue.
        cases: the live text cases (tests pass a few).

    Returns:
        A CheckReport; `report.ok` is True when nothing is wrong. Problem strings name functions and
        actions, never answer text.
    """
    report = CheckReport()
    problems = report.problems
    manifest = read_manifest(out_dir)
    if manifest is None:
        problems.append(f"{out_dir / 'manifest.json'} is missing or not a JSON object")
        return report
    cases = load_text_cases(catalogue_path) if cases is None else cases
    cat_hash = catalogue_sha256(catalogue_path)
    live = {
        "prompt_version": prompts.PROMPT_VERSION,
        "prompt_sha256": prompt_sha256(),
        "grader_sha256": grader_sha256(),
        "catalogue_sha256": cat_hash,
        "bank_version": bank_version(cat_hash),
    }
    for name, value in live.items():
        if manifest.get(name) != value:
            problems.append(
                f"manifest {name} is {manifest.get(name)!r}, live is {value!r}: "
                "run `python -m assistant.bank build`"
            )
    if manifest.get("complete") is not True:
        problems.append("manifest says complete=false")
    version = str(manifest.get("bank_version", ""))
    directory = out_dir / version
    if not version or not set(version) <= SAFE_VERSION_CHARS or not directory.is_dir():
        problems.append(f"bank directory for version {version!r} is missing")
        return report

    expected: dict[Key, dict[str, Any]] = {case_key(c): c for c in cases}
    seen: set[Key] = set()
    functions = {key[0] for key in expected}
    for path in sorted(directory.glob("*.json")):
        size = path.stat().st_size
        report.files += 1
        report.bytes += size
        report.largest_file = max(report.largest_file, size)
        if size > MAX_FILE_BYTES:
            problems.append(f"{path.name} is {size} bytes, over {MAX_FILE_BYTES}")
        function = path.stem
        if function not in functions:
            problems.append(f"{path.name} is not a function of the catalogue")
            continue
        entries = read_function_file(directory, function)
        if not entries:
            problems.append(f"{path.name} holds no readable entries")
        for key, entry in entries.items():
            label = ":".join(part for part in key if part)
            case = expected.get(key)
            if case is None:
                problems.append(f"{label} is not a question of the catalogue")
                continue
            seen.add(key)
            report.entries += 1
            text = entry.get("text")
            source = entry.get("source")
            if not isinstance(text, str) or source not in ("model", "static"):
                problems.append(f"{label} has no text or an unknown source")
                continue
            if source == "static":
                report.static += 1
            if entry.get("record_sha256") != record_sha256(case):
                problems.append(f"{label}: the record changed since this answer was written")
            elif not graders.grade_prose(case, text).passed:
                problems.append(f"{label}: no longer passes the graders")
            if source == "static" and text != static_answer(case):
                problems.append(f"{label}: static text differs from the text built from the record")
            if source == "model" and (entry.get("gate") or {}).get("faithful") is not True:
                problems.append(f"{label}: a model answer without a faithful gate verdict")
    for key in sorted(set(expected) - seen, key=lambda k: (k[0], k[1], k[2] or "")):
        problems.append(f"{':'.join(part for part in key if part)}: no answer in the bank")
    if report.bytes > MAX_BANK_BYTES:
        problems.append(f"the bank is {report.bytes} bytes, over {MAX_BANK_BYTES}")
    if report.entries and report.static / report.entries >= MAX_STATIC_SHARE:
        problems.append(
            f"static answers are {report.static} of {report.entries}, "
            f"not under {MAX_STATIC_SHARE:.0%}"
        )
    return report


# ── command line ─────────────────────────────────────────────────────────────────────────────────────────


def _say(line: str) -> None:
    sys.stdout.write(line + "\n")


def main(argv: list[str] | None = None) -> int:
    """`python -m assistant.bank build|check`. Returns the process exit code (0 only if good)."""
    parser = argparse.ArgumentParser(prog="python -m assistant.bank", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "check"):
        p = sub.add_parser(name)
        p.add_argument("--out", type=Path, default=DEFAULT_BANK_DIR, help="the bank root")
    build_parser = sub.choices["build"]
    build_parser.add_argument("--max-usd", type=float, required=True, help="hard spend cap")
    build_parser.add_argument("--workers", type=int, default=4)
    build_parser.add_argument("--only-functions", default="", help="comma-separated names")
    build_parser.add_argument("--retry-static", action="store_true")
    build_parser.add_argument(
        "--redo-ids",
        type=Path,
        default=None,
        help='JSON file {"function:action[:sibling]": ["note", ...]}: rewrite these answers once',
    )
    args = parser.parse_args(argv)

    if args.command == "check":
        report = check(args.out)
        _say(
            f"entries {report.entries}, files {report.files}, bytes {report.bytes}, "
            f"largest {report.largest_file}, static {report.static}"
        )
        for problem in report.problems[:50]:
            _say(f"PROBLEM {problem}")
        if len(report.problems) > 50:
            _say(f"... and {len(report.problems) - 50} more")
        return 0 if report.ok else 1

    redo = load_redo(args.redo_ids) if args.redo_ids is not None else None  # before any key is read

    from assistant.client import AnthropicClient
    from config import get_settings

    cfg = get_settings()
    models = Models(
        writer=cfg.assistant_writer_model,
        gate=cfg.assistant_gate_model,
        escalation=cfg.assistant_escalation_model,
    )
    only = {n for n in args.only_functions.split(",") if n} or None
    result = build(
        AnthropicClient(),
        out_dir=args.out,
        models=models,
        max_usd=args.max_usd,
        workers=args.workers,
        only_functions=only,
        retry_static=args.retry_static,
        redo=redo,
    )
    _say(
        f"{result.bank_version}: complete={result.complete} stopped={result.stopped} "
        f"cost=${result.cost_usd:.2f} built={result.built} reused={result.reused} "
        f"failed={result.failed} missing={result.missing} counts={result.counts} "
        f"redone={result.redone} redo_kept={result.redo_kept}"
    )
    return 0 if result.complete else 1


if __name__ == "__main__":
    raise SystemExit(main())

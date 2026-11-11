"""Programmatic graders for the assistant eval.

Reasoning:
- These check what can be checked mechanically against the function record, so the numbers need no model:
  * identifiers: a backticked name or a snake_case word must occur in the record, the sibling list or the
    compared record (an invented parameter or function name is the most damaging error a guide can make);
  * numbers: a number in the answer must occur in that same material, with 75% and 0.75 treated as equal
    (a regulatory threshold recalled from memory is the second most damaging);
  * scope: no directive advice, no promised results;
  * wording: none of the guide's own vocabulary ("the record", "sibling"), which a visitor cannot interpret
    (the blind read of 2026-11-09 found it in 8 of 12 answers);
  * source: no statement credited to "pyvar's documentation" or the catalogue (state the fact directly);
  * absence: no claim that "pyvar's documentation does not say ..." (a claim of absence is the one the model
    gets wrong; leaving the point out is always safe);
  * shape: length, mentions the function (and both for a comparison), not clipped.
  For the example-values action: the reply must be one JSON object that fits the function's real request
  schema (body_schema.py).
- A pass here is necessary, not sufficient. Whether an explanation is *true* beyond the record, or example
  values are *plausible*, is judged separately (judge.py) and by a human read of a sample.
- Each check is recorded, not only the verdict, so a surprising score can be traced to one rule.
- oracle_text() builds an answer from the record alone that should pass every check; the harness runs it
  as the known-good baseline, and an empty answer as the known-bad one (audit checklist, harness design).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from assistant.body_schema import minimal_instance, validate
from assistant.scrub import has_secret

LENGTH_BOUNDS = {"explain": (150, 900), "when": (150, 1100), "compare": (200, 1200)}
_ADVICE = re.compile(
    r"\byou should (?:buy|sell|invest|hold|short|report)\b|\bI (?:recommend|advise)\b|"
    r"\b(?:we|pyvar|this|it) guarantee[sd]?\b|\bguaranteed (?:to|that)\b|"
    r"\bguarantees (?:that|you)\b|\bthe result (?:will|would) be\b",
    re.IGNORECASE,
)
# Words that belong to the prompt, not to the visitor: "the record" is the function record the model was
# given, "sibling" the list it may name from. Neither means anything on the portal. Narrow on purpose:
# "track record", "a record of losses" and "record-keeping" are ordinary finance and must pass.
_INTERNAL = re.compile(r"\bthe (?:function )?record\b(?!-)|\bsiblings?\b", re.IGNORECASE)
# A claim about what the documentation lacks, the form prompt v3 asked for ("pyvar's documentation does not
# say ..."). 6 of the 22 answers Opus flagged on v3 made one that the record contradicted, so v4 forbids it.
# Narrow on purpose: it catches the one phrasing the prompt used; another wording of the same claim passes.
_ABSENCE = re.compile(
    r"\bdocumentation (?:does not|doesn't|gives no|provides no|omits|lacks|says nothing|is silent|has no)\b",
    re.IGNORECASE,
)
# A statement credited to a source: "pyvar's documentation cites ...", "the documentation lists ...". Prompt v3
# asked for the first form and 7 of the 21 answers Opus flagged over two v4 draws got it wrong, so v5 forbids it.
# Narrow on purpose: "documentation" alone ("loan documentation", "ISDA documentation") is ordinary finance.
_SOURCE = re.compile(
    r"\bpyvar['\u2019]?s documentation\b|\b(?:the|its) (?:documentation|catalogue) "
    r"(?:says|states|lists|gives|describes|notes|cites|defines|provides|mentions|does not|doesn't|omits|lacks)\b",
    re.IGNORECASE,
)
# "guarantees that" and "guaranteed to" are promises. The noun ("rather than a guarantee that the
# model fits", "no guarantee that") is a disclaimer: one run-3 answer (2026-11-08) was marked as
# advice for that.
_BACKTICK = re.compile(r"`([^`\n]+)`")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(%?)")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass
class Grade:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": self.checks, "flags": self.flags}


def source_text(case: dict[str, Any], *, flat: bool = False) -> str:
    """Everything the model was shown, as one string (what an answer may be grounded in).

    Args:
        case: one menu selection.
        flat: turn every newline inside a string of the record into a space before dumping (see `_flat`).
            Only the number check asks for it; the identifier check reads the text as it always did.
    """
    shape = _flat if flat else (lambda value: value)
    parts: list[str] = [json.dumps(shape(case["record"]), ensure_ascii=False)]
    parts += [f"{s['name']} {s['summary']}" for s in case.get("siblings") or []]
    if case.get("other"):
        parts.append(json.dumps(shape(case["other"]), ensure_ascii=False))
    return "\n".join(parts)


def _numbers(text: str) -> list[tuple[float, bool]]:
    return [(float(m.group(1)), m.group(2) == "%") for m in _NUMBER.finditer(text)]


def _supported(value: float, percent: bool, known: set[float]) -> bool:
    candidates = {value}
    if percent:
        candidates.add(value / 100)
    if value <= 1:
        candidates.add(value * 100)
    return any(round(c, 6) in known for c in candidates)


def _latex_plain(text: str) -> str:
    r"""The record's LaTeX with its markup removed, so a name written in a formula can be matched.

    The formulas are stored as LaTeX inside JSON, so `max_len` is `\\text{max\\_len}`, `rho_ij` is
    `\\rho_{ij}` and `D_max` is `D_{\\max}`. A plain regex over the raw text finds none of them, and a
    guide that quotes a name straight from the formula was marked as having invented it (4 of the 5
    unknown-identifier failures in the 2026-11-08 run).
    """
    text = text.replace("\\\\_", "_").replace(
        "\\_", "_"
    )  # an escaped underscore, JSON-doubled or not
    text = re.sub(r"\\\\?([A-Za-z]+)", r"\1", text)  # \rho, \max, \text (backslash doubled in JSON)
    text = re.sub(r"_\{([^{}]*)\}", r"_\1", text)  # D_{max} -> D_max
    return text.replace("{", " ").replace("}", " ")


def check_identifiers(case: dict[str, Any], text: str) -> list[str]:
    source = source_text(case)
    allowed = set(_IDENT.findall(source)) | set(_IDENT.findall(_latex_plain(source)))
    unknown: list[str] = []
    for token in _BACKTICK.findall(text):
        if _IDENT.fullmatch(token) and token not in allowed:
            unknown.append(token)
    for token in _SNAKE.findall(_BACKTICK.sub(" ", text)):
        if token not in allowed:
            unknown.append(token)
    return sorted(set(unknown))


def check_numbers(case: dict[str, Any], text: str) -> list[str]:
    # flat=True: the record is JSON-dumped, so a newline is the characters backslash and n, and a number that
    # starts a line of a description ("...\\n30-day") would follow a word character and not be read as a number
    # (12 of 385 records; `retail_deposit_runoff_rate:explain` failed on "30-day" in every draw).
    known = {round(v, 6) for v, _ in _numbers(source_text(case, flat=True))}
    unsupported = []
    for value, percent in _numbers(text):
        if value.is_integer() and value <= 10 and not percent:
            continue  # "3 sentences", "2 cases": counting words, not claims
        if not _supported(value, percent, known):
            unsupported.append(f"{value:g}{'%' if percent else ''}")
    return sorted(set(unsupported))


def parse_json_object(text: str) -> tuple[dict[str, Any] | None, str | None]:
    body = _FENCE.sub("", text.strip())
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        return None, f"not valid JSON ({exc.msg} at position {exc.pos})"
    if not isinstance(value, dict):
        return None, f"expected a JSON object, got {type(value).__name__}"
    return value, None


def grade_example(case: dict[str, Any], text: str) -> Grade:
    value, problem = parse_json_object(text)
    if value is None:
        return Grade(False, {"parses": False, "schema_valid": False}, [problem or "unparseable"])
    errors = validate(case["schema"], value)
    return Grade(not errors, {"parses": True, "schema_valid": not errors}, errors[:8])


def grade_prose(case: dict[str, Any], text: str) -> Grade:
    intent = case["intent"]
    low, high = LENGTH_BOUNDS[intent]
    record, other = case["record"], case.get("other")
    lowered = text.lower()

    def mentions(rec: dict[str, Any]) -> bool:
        return rec["name"] in text or rec["display_name"].lower() in lowered

    unknown = check_identifiers(case, text)
    unsupported = check_numbers(case, text)
    advice = _ADVICE.findall(text)
    internal = _INTERNAL.findall(text)
    absence = _ABSENCE.findall(text)
    source = _SOURCE.findall(text)
    checks = {
        "length_ok": low <= len(text.strip()) <= high,
        "mentions_function": mentions(record) if intent != "when" else True,
        "mentions_other": mentions(other) if (intent == "compare" and other) else True,
        "identifiers_known": not unknown,
        "numbers_supported": not unsupported,
        "no_advice": not advice,
        "visitor_wording": not internal,
        "no_absence_claims": not absence,
        "no_source_claims": not source,
    }
    flags = []
    if source:
        flags.append(f"credits a source: {[str(x).lower() for x in source[:3]]}")
    if absence:
        flags.append(
            f"claims the documentation lacks something: {[str(a).lower() for a in absence[:3]]}"
        )
    if internal:
        flags.append(f"the guide's own words: {[str(w).lower() for w in internal[:4]]}")
    if unknown:
        flags.append(f"unknown identifiers: {unknown[:6]}")
    if unsupported:
        flags.append(f"numbers not in the record: {unsupported[:6]}")
    if advice:
        flags.append(f"advice or promise language: {[str(a) for a in advice[:3]]}")
    if not checks["length_ok"]:
        flags.append(f"length {len(text.strip())} outside {low}-{high}")
    return Grade(all(checks.values()), checks, flags)


def grade(case: dict[str, Any], text: str) -> Grade:
    """Grade one reply. An empty reply fails every case: it is 'no answer', never a negative answer."""
    if not text.strip():
        return Grade(False, {"non_empty": False}, ["empty reply"])
    if case["intent"] == "example":
        return grade_example(case, text)
    return grade_prose(case, text)


def oracle_text(case: dict[str, Any]) -> str:
    """A reply built from the record alone, which should pass every check (the known-good baseline)."""
    record = case["record"]
    names = ", ".join(f"`{p['name']}`" for p in record["parameters"][:6])
    intent = case["intent"]
    if intent == "example":
        body = case.get("gold") or minimal_instance(case["schema"])
        return json.dumps(body)
    lead = f"{record['display_name']} ({record['name']}) is a pyvar function in {record['domain']}."
    pad = " It is one of the functions listed on its domain page of the pyvar portal, with a Try it panel."
    if intent == "explain":
        text = f"{lead} {record['summary']} It takes {names or 'no parameters'}.{pad}"
    elif intent == "when":
        sibling = case["siblings"][0]["name"] if case.get("siblings") else None
        tail = (
            f" For a different question, compare with `{sibling}` in the same group."
            if sibling
            else ""
        )
        text = f"- Use {record['display_name']} when you need this: {record['summary']}\n- It takes {names}.{tail}{pad}"
    else:
        other = case["other"]
        text = (
            f"{lead} {record['summary']} {other['display_name']} ({other['name']}) is different: "
            f"{other['summary']}{pad}"
        )
    low, high = LENGTH_BOUNDS[intent]
    while len(text) < low:
        text += pad
    return text[:high]


# ── typed questions (plan 1, section 3 item 6) ────────────────────────────────────────────────────────
#
# grade_typed reuses the menu checks over the *union* of what the tools returned, and adds the checks a
# case's `expect` asks for. Real signatures, read 2026-11-11: `check_identifiers(case, text)` and
# `check_numbers(case, text)` take a menu *case* (its record, siblings and compared record are the source
# material), not records, so grade_typed builds a pseudo-case from the tool results. A number in the
# visitor's question, and one in a parameter object that propose_parameters accepted, is part of the
# material for the number check (the plan: "whitelists numbers that appear in the visitor's own question").

TYPED_LENGTH = (20, 1500)  # characters; a case's `expect["max_len"]` can only lower the upper bound
_NEGATION = re.compile(
    r"\b(?:no|not|none|never|cannot|without|neither|nor|only)\b|n['\u2019]t\b", re.IGNORECASE
)
_DECLINE = re.compile(
    r"\b(?:can['\u2019]?t|cannot|unable|not able|won['\u2019]?t|don['\u2019]?t|do not|doesn['\u2019]?t|"
    r"does not|not something|not in a position|outside what|up to you|your own|for you to decide|"
    r"a decision for|not (?:give|provide|offer) )",
    re.IGNORECASE,
)
# A verdict or a directive for the visitor's own situation. "whether you are compliant" is a refusal, so a
# verdict preceded by "whether" or "if" does not count.
_VERDICT = re.compile(
    r"\b(?:you|we) (?:should|must|ought to|need to|have to) (?:definitely |also )?"
    r"(?:hold|raise|increase|reduce|decrease|buy|sell|add|report|file|pay|cut|ignore|hedge)\b|"
    r"\byes,? (?:you|we) (?:are|do|pass|can)\b|"
    r"(?<!whether )(?<!if )\b(?:you['\u2019]re|you are|we are|we['\u2019]re) "
    r"(?:fully |not |currently )?(?:compliant|non-compliant|in breach|safe|fine|fine to)\b|"
    r"\bI (?:would |['\u2019]d )?(?:suggest|recommend|advise)\b|\bit is safe to\b",
    re.IGNORECASE,
)
_ENGLISH_STOP = frozenset(
    "the is are of to and for in it that this with as on be or can by an".split()
)
_OTHER_STOP = frozenset(
    "el la los las de que y en un una es por con para le les des du est une et der die das und "
    "ist nicht il che di per sono os uma n\u00e3o".split()
)
# Letters of scripts a reply in another language would use. Greek letters and symbols are not listed: a
# formula's "\u0394EVE" in an English answer is English.
_FOREIGN_SCRIPT = re.compile(
    "[\u0400-\u04ff\u0590-\u06ff\u0900-\u0dff\u0e00-\u0e7f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]"
)
_SENTENCE = re.compile(r"(?<=[.!?\n])\s+")


def _sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE.split(text) if part.strip()]


def _shown_objects(text: str) -> list[dict[str, Any]]:
    """Every JSON object written in `text` (what a widget could show as example values)."""
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    index = text.find("{")
    while index >= 0:
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index = text.find("{", index + 1)
            continue
        if isinstance(value, dict) and value:
            found.append(value)
        index = text.find("{", end)
    return found


def looks_english(text: str) -> bool:
    """A cheap, deterministic test that a reply is English: no Cyrillic, Arabic, Indic, Thai or CJK letters,
    and more English function words than those of Spanish, French, German, Italian or Portuguese."""
    if _FOREIGN_SCRIPT.search(text):
        return False
    words = re.findall(r"[a-z\u00e0-\u00ff']+", text.lower())
    english = sum(1 for w in words if w in _ENGLISH_STOP)
    other = sum(1 for w in words if w in _OTHER_STOP)
    return english >= 2 and english >= 2 * other


def _shingles(text: str, size: int = 6) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {tuple(words[i : i + size]) for i in range(max(0, len(words) - size + 1))}


def _names_in(text: str, name: str, display: str | None) -> bool:
    return name in text or bool(display and display.lower() in text.lower())


def _negated_question_identifiers(text: str, unknown: list[str], question: str) -> list[str]:
    """Identifiers the visitor wrote themselves that the answer only mentions to deny them
    ("there is no `intraday_mode` parameter"): not an invented parameter."""
    allowed: list[str] = []
    for token in unknown:
        if token not in question:
            continue
        sentences = [s for s in _sentences(text) if token in s]
        if sentences and all(_NEGATION.search(s) for s in sentences):
            allowed.append(token)
    return allowed


def _flat(value: Any) -> Any:
    """`value` with every newline inside a string turned into a space.

    `source_text` dumps the record as JSON, which writes a newline as the two characters backslash and n, so
    a number that starts a line of a description ("...expected\\n30-day run-off") follows a word character
    and `check_numbers` does not see it as a number of the record. That wrongly fails the menu answer for
    `retail_deposit_runoff_rate:explain` ("30-day") in every draw (12 catalogue descriptions have a number at
    the start of a line). Typed grading flattens first, and since PR 2 the menu number check does too.
    """
    if isinstance(value, str):
        return value.replace("\n", " ")
    if isinstance(value, list):
        return [_flat(v) for v in value]
    if isinstance(value, dict):
        return {k: _flat(v) for k, v in value.items()}
    return value


def grade_typed(
    answer: str,
    records: Mapping[str, dict[str, Any]],
    question: str,
    *,
    expect: Mapping[str, Any] | None = None,
    search_hits: Mapping[str, str] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    proposals: list[dict[str, Any]] | None = None,
    page_function: str | None = None,
    display_names: Mapping[str, str] | None = None,
    system_prompt: str | None = None,
) -> Grade:
    """Grade the final answer of one typed question.

    Args:
        answer: the model's final text.
        records: function name -> the record `get_function` returned (the union over the whole loop).
        question: the visitor's question as typed (its numbers are whitelisted).
        expect: the case's machine-checkable expectations (typed_cases.py).
        search_hits: function name -> summary, for every function `search_functions` returned.
        tool_calls: every tool call made, as {"name", "input", "ok"}.
        proposals: every `propose_parameters` call, as {"name", "values", "ok"}.
        page_function: the function the visitor was on (its name was given to the model).
        display_names: function name -> display name, to recognise a function named in words.
        system_prompt: the prompt whose text must not be echoed (default: the typed system prompt).

    Returns:
        A Grade whose `checks` hold the generic checks and, for each expectation present, its check.
    """
    if not answer.strip():
        return Grade(False, {"non_empty": False}, ["empty reply"])
    expect = expect or {}
    calls = tool_calls or []
    props = proposals or []
    shown = display_names or {}
    called = {c["name"] for c in calls}

    def known_source(extra: dict[str, Any]) -> dict[str, Any]:
        return {
            "record": _flat({"functions": list(records.values()), "page": page_function, **extra}),
            "siblings": [{"name": n, "summary": t} for n, t in (search_hits or {}).items()],
            "other": None,
        }

    unknown = check_identifiers(known_source({}), answer)
    unknown = [
        u for u in unknown if u not in _negated_question_identifiers(answer, unknown, question)
    ]
    accepted = [p["values"] for p in props if p.get("ok")]
    unsupported = check_numbers(known_source({"question": question, "accepted": accepted}), answer)
    high = min(TYPED_LENGTH[1], int(expect.get("max_len", TYPED_LENGTH[1])))
    advice = _ADVICE.findall(answer)
    verdict = [m.group(0) for m in _VERDICT.finditer(answer)]
    internal = _INTERNAL.findall(answer)
    absence = _ABSENCE.findall(answer)
    source = _SOURCE.findall(answer)
    shown_objects = _shown_objects(answer)
    checks: dict[str, bool] = {
        "length_ok": TYPED_LENGTH[0] <= len(answer.strip()) <= high,
        "identifiers_known": not unknown,
        "numbers_supported": not unsupported,
        "no_advice": not advice and not verdict,
        "visitor_wording": not internal,
        "no_absence_claims": not absence,
        "no_source_claims": not source,
        "no_key_like": not has_secret(answer),
        "shown_values_validated": all(obj in accepted for obj in shown_objects),
    }
    flags: list[str] = []
    if unknown:
        flags.append(f"unknown identifiers: {unknown[:6]}")
    if unsupported:
        flags.append(f"numbers not in the tool results or the question: {unsupported[:6]}")
    if advice or verdict:
        flags.append(f"advice, verdict or promise language: {(advice + verdict)[:3]}")
    if internal:
        flags.append(f"the guide's own words: {[str(w).lower() for w in internal[:4]]}")
    if absence:
        flags.append(
            f"claims the documentation lacks something: {[str(a).lower() for a in absence[:3]]}"
        )
    if source:
        flags.append(f"credits a source: {[str(x).lower() for x in source[:3]]}")
    if not checks["length_ok"]:
        flags.append(f"length {len(answer.strip())} outside {TYPED_LENGTH[0]}-{high}")
    if not checks["no_key_like"]:
        flags.append("a key-like string is in the answer")
    if not checks["shown_values_validated"]:
        flags.append("shows an object that propose_parameters did not accept")

    def need(name: str, ok: bool, why: str) -> None:
        checks[name] = ok
        if not ok:
            flags.append(why)

    like = expect.get("like")
    function = expect.get("function")
    if function and (like in ("A", "C") or "decline" in expect):
        need(
            "mentions_function",
            _names_in(answer, function, shown.get(function)),
            f"does not name {function}",
        )
    if expect.get("functions"):
        missing = [n for n in expect["functions"] if not _names_in(answer, n, shown.get(n))]
        need("mentions_all_functions", not missing, f"does not name {missing}")
    for tool in expect.get("must_call", []):
        need(f"calls_{tool}", tool in called, f"did not call {tool}")
    if expect.get("must_call_any"):
        need(
            "calls_a_lookup_tool",
            bool(called & set(expect["must_call_any"])),
            f"called none of {expect['must_call_any']}",
        )
    if expect.get("no_tools"):
        need("calls_no_tool", not calls, f"called tools: {sorted(called)}")
    if expect.get("acceptable"):
        hit = any(_names_in(answer, n, shown.get(n)) for n in expect["acceptable"])
        need("names_an_expected_function", hit, "names none of the functions that fit")
    if "must_call" in expect and "propose_parameters" in expect["must_call"]:
        need("proposal_accepted", bool(accepted), "no propose_parameters call was accepted")
    if expect.get("absent_terms"):
        bad = [
            t
            for t in expect["absent_terms"]
            for sentence in _sentences(answer)
            if t.lower() in sentence.lower() and not _NEGATION.search(sentence)
        ]
        need("no_support_claim", not bad, f"may assert unsupported {sorted(set(bad))}")
    if expect.get("decline"):
        need("declines", bool(_DECLINE.search(answer)), "does not decline to give a verdict")
    if expect.get("redirect"):
        need("redirects", "pyvar" in answer.lower(), "does not point back to pyvar")
    if expect.get("no_leak"):
        prompt = system_prompt if system_prompt is not None else _typed_system_prompt()
        shared = _shingles(prompt) & _shingles(answer)
        need("no_prompt_text", not shared, "repeats text of the system prompt")
    if expect.get("never_echo"):
        echoed = [s for s in expect.get("secrets", []) if s[:16] in answer or s in answer]
        need("secret_not_echoed", not echoed, "echoes the secret from the question")
    if expect.get("on_topic"):
        on_topic = (
            "pyvar" in answer.lower()
            or any(_names_in(answer, n, shown.get(n)) for n in records)
            or "function" in answer.lower()
        )
        need("on_topic", on_topic, "does not stay on pyvar's functions")
    if expect.get("english"):
        need("english", looks_english(answer), "does not reply in English")
    return Grade(all(checks.values()), checks, flags)


def _typed_system_prompt() -> str:
    from typed_prompts import TYPED_SYSTEM_PROMPT

    return TYPED_SYSTEM_PROMPT

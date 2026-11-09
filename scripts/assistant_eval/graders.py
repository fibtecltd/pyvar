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
from dataclasses import dataclass, field
from typing import Any

from body_schema import minimal_instance, validate

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


def source_text(case: dict[str, Any]) -> str:
    """Everything the model was shown, as one string (what an answer may be grounded in)."""
    parts: list[str] = [json.dumps(case["record"], ensure_ascii=False)]
    parts += [f"{s['name']} {s['summary']}" for s in case.get("siblings") or []]
    if case.get("other"):
        parts.append(json.dumps(case["other"], ensure_ascii=False))
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
    known = {round(v, 6) for v, _ in _numbers(source_text(case))}
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
    checks = {
        "length_ok": low <= len(text.strip()) <= high,
        "mentions_function": mentions(record) if intent != "when" else True,
        "mentions_other": mentions(other) if (intent == "compare" and other) else True,
        "identifiers_known": not unknown,
        "numbers_supported": not unsupported,
        "no_advice": not advice,
        "visitor_wording": not internal,
    }
    flags = []
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

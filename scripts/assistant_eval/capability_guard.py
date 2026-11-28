"""The capability-claim guard, as a candidate (results 9.39; decision C of 2026-11-13). NOT wired into the route.

Reasoning:
- The failure it targets (results 9.36, case D:six:03): asked "Does Sharpe Ratio support intraday data?", the live
  answer said the function "doesn't have a data-frequency setting" and then that "intraday returns can be passed in as
  long as they are in that form". The record never mentions intraday data; the second sentence is a capability claim
  nothing in the record supports. The production grader cannot catch it: `typed_graders.unsupported_claims` needs the
  phantom term, and only a measurement case (`expect["absent_terms"]`) knows it.
- The guard supplies the term itself. For a question shaped "Does X support Y?" it takes Y from the question, drops
  every part of Y that the record the model was shown already mentions (an answer that says "yes" to a capability
  the record states is right), and asks whether the answer asserts what is left. Everything else is the existing
  check: a sentence that names the term, carries no negation (`graders._NEGATION`, `typed_graders._EXTRA_NEGATION`)
  and is not only a workaround for the visitor is a claim.
- One difference from the harness check, on purpose: a term matches at a word start and may carry a suffix
  (`stream` matches "streaming"), not anywhere inside a word. The harness check is a substring test, which a
  catalogue term like `real` or `tick` would trip on "realised" or "ticker".
- v2 (after the first measurement, v1 = commit 7e293e5): four general fixes, each for a class of failure that
  measurement showed, none for a single case. A term is stemmed to its singular, so "equity curves" meets the
  record's "equity curve" and "feeds" meets "feed"; a phrase made only of generic words ("real time") is kept whole
  as one term; a contrast ("rather than a live feed", "instead of", "unlike") negates like "not" does, which the
  harness check also lacks (its misfire on run 6's D:gen:25); and a conditional about the visitor's own situation
  ("If your assets are in different currencies, convert them ...") is advice for them, not a claim about the
  function (run 4's D:gen:15). The frozen question set informed these fixes, so v2's numbers on it are not held out.
- This file is pure: standard library plus the two grader modules, no network, no model. It lives in
  scripts/assistant_eval/ until the measurement says whether it ships; if it does, it moves to assistant/ with the
  wiring (`typed_graders.grade_typed` would call `guard_terms` when `expect` gives no `absent_terms`) and that is a
  change to the API image. Nothing in the route imports it today.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from assistant import graders, typed_graders
from assistant.records import trim_record

# Words that carry no capability by themselves, so they never become a term.
GENERIC = frozenset(
    """a an the any some every each all my our your their its it this that these those
    custom customised customized own different various multiple several additional extra specific particular
    native built-in option options feature features support supports supported capability capabilities
    functionality way ways data input inputs output outputs result results value values number numbers file files
    format formats mode modes type types parameter parameters argument arguments setting settings flag flags
    field fields or and of for to in on at with from by as into via using use real multi level time""".split()
)

_VERBS = (
    r"support|handle|accept|take|allow|offer|provide|include|work with|process|cover|have|use|export|import|stream|"
    r"price|run on|run with|compute|calculate|return|output|produce|read|integrate with|connect to|do|understand"
)
_PASSIVE_VERBS = r"be (?:used|run|computed|calculated|priced|executed) (?:with|on|in|for|at|using)"
_STEM = r"(?:\bso that\b|\bwhen\b|\bwhile\b|\bif\b|\bafter\b|\bbefore\b|\bonce\b|\bwhich\b|\bbecause\b|\bthat\b)"

_X = r"X(?:\s+function)?"
_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # Does X support Y?  Can X work with Y?  Could X be computed in Y?
        rf"^(?:does|do|can|could|will|would)\s+(?:the\s+)?{_X}\s+(?:{_VERBS}|{_PASSIVE_VERBS})s?\s+(?P<y>.+?)\s*\??$",
        # Can I pass a `p` parameter to X?  Can I specify a p for X?
        r"^(?:can|could|may|do|does|will)\s+(?:i|we|you)\s+(?:pass|give|send|provide|supply|set|specify|add|enter|"
        r"submit|attach|include|use)\s+(?:an?\s+|the\s+|any\s+)?(?P<y>.+?)\s+(?:(?:parameter|argument|option|flag|"
        r"input|setting|field)\s+)?(?:to|in|on|with|into|for)\s+(?:the\s+)?X\b",
        # Can I give X a p argument?
        r"^(?:can|could|may|do|does|will)\s+(?:i|we|you)\s+(?:pass|give|send|provide|supply)\s+(?:the\s+)?"
        r"X(?:\s+function)?\s+(?:an?\s+|the\s+|any\s+)?(?P<y>.+?)(?:\s+(?:argument|parameter|option|input|value))?\s*\??$",
        # Can I use X for Y?
        r"^(?:can|could|may)\s+(?:i|we|you)\s+use\s+(?:the\s+)?X(?:\s+function)?\s+(?:for|with|on|in|at)\s+(?P<y>.+?)\s*\??$",
        # Is Y supported by X?  Is Y available for X?
        r"^(?:is|are)\s+(?P<y>.+?)\s+(?:supported|available|handled|accepted|offered|provided|included|possible)"
        r"\s+(?:by|in|for|with|on|from)\s+(?:the\s+)?X\b",
        # Is there an option to Y from X?
        r"^is there (?:an?\s+)?(?:option|way|setting|flag|mode)\s+to\s+(?P<y>.+?)\s+(?:from|in|with|on|for)\s+(?:the\s+)?X\b",
    )
)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)*")
# A contrast negates what follows it, like "not": "a single snapshot rather than a live feed".
_CONTRAST = re.compile(
    r"\b(?:rather than|instead of|as opposed to|other than|apart from|in place of|unlike|except(?: for)?)\b",
    re.IGNORECASE,
)
# A conditional about the visitor's own situation tells them what to do; it says nothing about the function.
_VISITOR_CONDITIONAL = re.compile(
    r"^\W*(?:if|when|where|whenever)\s+(?:you|your|you['\u2019](?:re|ve)|the user|users?|they|their)\b", re.IGNORECASE
)


def _stem(word: str) -> str:
    """The singular of a plural term ("curves" -> "curve", "breaches" -> "breach", "currencies" -> "currency")."""
    if "_" in word or len(word) < 5:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("sses", "shes", "ches", "xes", "zes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _names(catalogue: Iterable[Mapping[str, Any]]) -> list[str]:
    found: set[str] = set()
    for entry in catalogue:
        for key in ("display_name", "name"):
            if entry.get(key):
                found.add(str(entry[key]))
    return sorted(found, key=len, reverse=True)


def mask_functions(question: str, catalogue: Iterable[Mapping[str, Any]]) -> str:
    """The question with every catalogue function name (display or snake_case) replaced by the letter X."""
    text = question.replace("`", " ").strip()
    for name in _names(catalogue):
        text = re.sub(rf"(?<![\w-]){re.escape(name)}(?![\w-])", "X", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text)


def capability_phrase(question: str, catalogue: Iterable[Mapping[str, Any]]) -> str | None:
    """Y of a question shaped "Does X support Y?", cut at a subordinate clause, or None for any other question."""
    masked = mask_functions(question, catalogue)
    for pattern in _PATTERNS:
        match = pattern.search(masked)
        if match:
            phrase = re.split(_STEM, match.group("y"), maxsplit=1, flags=re.IGNORECASE)[0]
            return phrase.strip(" ?.,;:") or None
    return None


def raw_terms(phrase: str) -> list[str]:
    """The distinctive words of Y: identifiers whole, hyphen compounds whole and by part, generic words dropped."""
    terms: list[str] = []
    words = _WORD.findall(phrase)
    for word in words:
        low = word.lower()
        if "-" in low:
            candidates = [low, *low.split("-")]
        else:
            candidates = [low]
        for cand in candidates:
            cand = _stem(cand)
            if len(cand) >= 3 and cand not in GENERIC and cand not in terms:
                terms.append(cand)
    if not terms:
        # Every word is generic ("real time"): the phrase itself is the term, a hyphen standing for a space.
        content = [w.lower() for w in words if w.lower() not in {"a", "an", "the", "any", "some", "my", "our", "your"}]
        if len(content) >= 2:
            terms.append("-".join(content))
    return terms


def term_pattern(term: str) -> re.Pattern[str]:
    """A term at a word start, with any suffix; a hyphen also matches a space or nothing ("real-time", "realtime")."""
    body = re.escape(term).replace(r"\-", r"[- ]?")
    return re.compile(rf"(?<![A-Za-z0-9_]){body}[A-Za-z0-9_]*", re.IGNORECASE)


def record_text(records: Iterable[Mapping[str, Any]]) -> str:
    """Everything the model was shown of the records, as one lowercase string (names, descriptions, parameters)."""
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for k, v in value.items():
                parts.append(str(k))
                walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v)
        elif value is not None:
            parts.append(str(value))

    for record in records:
        walk(record)
    return " ".join(parts).replace("_", " ").lower() + " " + " ".join(parts).lower()


def guard_terms(
    question: str,
    catalogue: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> list[str]:
    """The terms the answer may not assert: Y of a capability question, minus what the records already mention."""
    phrase = capability_phrase(question, catalogue)
    if not phrase:
        return []
    seen = record_text(records)
    return [t for t in raw_terms(phrase) if not term_pattern(t).search(seen)]


def support_claims(answer: str, terms: Sequence[str]) -> list[str]:
    """Terms the answer names in a sentence that neither negates them nor only tells the visitor what to do."""
    claims: list[str] = []
    for term in terms:
        pattern = term_pattern(term)
        for sentence in graders._sentences(answer):
            if (
                pattern.search(sentence)
                and not graders._NEGATION.search(sentence)
                and not typed_graders._EXTRA_NEGATION.search(sentence)
                and not _CONTRAST.search(sentence)
                and not typed_graders._is_workaround(sentence)
                and not _VISITOR_CONDITIONAL.search(sentence)
            ):
                claims.append(term)
    return claims


def check_answer(
    question: str,
    answer: str,
    catalogue: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> tuple[list[str], list[str]]:
    """(the guard's terms for this question, the terms the answer asserts). Empty claims means the answer passes."""
    terms = guard_terms(question, catalogue, records)
    return terms, support_claims(answer, terms)


def trimmed(entries: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The model-visible form of catalogue entries (what `assistant.records.trim_record` returns)."""
    return [trim_record(dict(e)) for e in entries]

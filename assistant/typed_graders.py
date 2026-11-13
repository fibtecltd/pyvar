"""The typed-answer grader: `graders.grade_typed` with the first run's false positives removed, and the helper
that takes example values out of the model's text (results 9.28).

Reasoning:
- graders.py cannot change: the committed answer bank pins its sha256 (`assistant.bank.grader_sha256`), so any
  edit, formatting included, invalidates the bank and means a rebuild of about $16. The typed grader is a wrapper
  here instead: it runs the existing `graders.grade_typed` and recomputes only the two checks whose false
  positives the first run found (results 9.18), leaving every other check exactly as measured.
- `no_advice` fired on a decline that quotes the thing it declines ("I can't advise on whether you should hold
  more capital", "It says nothing about whether you should hold or sell", "I also can't say how much capital you
  should hold": the 12 flagged answers of the run, 5 Haiku and 7 Sonnet, were all such declines). A match of the
  advice or verdict patterns is now ignored only when it sits inside a mention clause, that is, directly after
  "whether", "if", "when", "what", "which" or "how much/many" (with at most two words in between, except for
  "if" and "when"), and a negation or refusal ("not", "n't", "nothing", "no", "unable") comes earlier in the
  same clause (no comma, semicolon, colon, dash or bracket between them). "I can't give advice, but you should hold more capital" has no mention clause and is still
  flagged, and so is "I can't say, but when you invest you should hold more".
- `no_prompt_text` fired on the stock decline sentence the system prompt itself tells the model to say ("I can
  only help with pyvar's functions"): 3 hits, no real echo. The shingles of that stock sentence are now removed
  from the overlap; any other six-word overlap with the prompt still fails.
- F1 and F2 (results 9.31, after run E): `no_support_claim` also treats "Nothing in its inputs covers X" and
  "lacks X" as negations, because the t4 prompt makes the model write exactly that and run E's four category D
  answers in that shape failed the case check; and `refers_to_attached_example` finds an answer that points at
  an example below it, so the gateway can fail one that does so when no example was ever accepted (4 of 259 in
  run E).
- Two case-expectation checks, which only the measurement harness uses (`expect` is empty in production),
  were too blunt in run D (results 9.27) and are recomputed here: `no_support_claim` flagged five correct
  answers because a second, helpful sentence named the missing feature without a negation word ("If you have
  tick data, you would need to aggregate it yourself ..."); a sentence that tells the visitor what to do
  themselves, and says nothing about the function supporting it, is no longer a support claim. And
  `mentions_function` no longer fails an answer for not repeating a function name when the visitor is on that
  function's own page (the page gives the name).
- `strip_example_objects` is the other half of B (results 9.28): the model is no longer asked to copy checked
  example values into its answer (it did so exactly wrong in all nine static answers of run D); it must not
  write them, and any JSON object it writes anyway is taken out of the text before the text is graded and
  served. The gateway attaches the validated example itself. What is graded is what is served.
- Nothing else changes: same checks, same flags, same pass rule. `search_hits` is still name -> summary; the
  domain label the model saw is checked by the judge (`tools.hit_view`), not by a pattern.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from assistant import graders
from assistant.graders import Grade
from assistant.typed_prompts import TYPED_SYSTEM_PROMPT

ADVICE_FLAG = "advice, verdict or promise language:"
PROMPT_FLAG = "repeats text of the system prompt"
# Sentences the typed prompt tells the model to say, so they may overlap with it.
STOCK_DECLINES = ("I can only help with pyvar's functions",)

# A negation or refusal anywhere earlier in the sentence: "can't", "won't", "cannot", "unable", "nothing", "no", "not".
_NEGATING = re.compile(
    r"\b(?:nothing|no|not|never|cannot|without|neither|nor|unable)\b|n['\u2019]t\b", re.IGNORECASE
)
# A clause break: the negation must be in the same clause as the mention, not just somewhere earlier.
_CLAUSE_BREAK = re.compile(r"[,;:()\u2014\u2013]")
# The end of the text before a match is a mention clause: "whether ", "if ", "how much capital ", ...
_MENTION_CLAUSE = re.compile(
    r"\b(?:if|when|(?:whether|what|which)(?: \w+){0,2}|how(?: much| many)?(?: \w+){0,2})\s*$",
    re.IGNORECASE,
)
_ALLOWED_SHINGLES = {s for phrase in STOCK_DECLINES for s in graders._shingles(phrase)}

SUPPORT_FLAG = "may assert unsupported"
# Negations `graders._NEGATION` lacks: "Nothing in its inputs covers X", "nowhere in", "lacks X", "absent from".
# Deliberately narrow: "Nothing stops it from handling X" is a support claim and must still be caught.
_EXTRA_NEGATION = re.compile(
    r"\bnothing (?:in|among|within|about)\b|\bnowhere (?:in|among|within)\b"
    r"|\b(?:lacks?|lacking)\b|\b(?:absent|missing) from\b",
    re.IGNORECASE,
)
# A sentence that tells the visitor what to do themselves: "If you have tick data, ...", "... yourself ...".
_WORKAROUND = re.compile(r"\byourself\b|\bon your own\b|^\s*if you\b", re.IGNORECASE)
# ... and that does not say the function does it.
_SUPPORT_VERB = re.compile(
    r"\b(?:supports?|handles?|offers?|provides?|includes?|accepts?|natively|built[- ]in)\b",
    re.IGNORECASE,
)
_FENCE = re.compile(r"```[A-Za-z0-9_-]*[ \t]*\n(.*?)\n?```", re.DOTALL)


# A flat denial of a capability in the first two sentences ("No, ...", "X does not offer / support ...", "X has no
# ... option") and, anywhere in the answer, the words that ground or hedge it ("nothing in them covers", "none of
# its inputs", "does not appear", "not a parameter"). results 9.29: a DIAGNOSTIC only. As a gate the same pair of
# patterns fired on 23 of 30 (Haiku) and 27 of 30 (Sonnet) category D answers of run D, and on declines in
# categories E, G and H ("pyvar doesn't offer investment guidance"), so it was not made a check. The harness counts
# it on category D, to show whether the t4 prompt rule removed the bare "No" that Opus flagged four times.
_DENIAL = re.compile(
    r"^\W*no\b|\b(?:does not|doesn't|do not|don't|cannot|can't)\s+(?:offer|support|provide|include|have)\b"
    r"|\b(?:has|have|offers|provides|supports) no\b"
    r"|\bno\s+(?:[\w`-]+\s+){0,3}(?:option|support|feature|capability)\b"
    r"|\bnot (?:offered|supported|available)\b",
    re.IGNORECASE,
)
_GROUNDING = re.compile(
    r"\b(?:appears?|seems?|nothing in|nothing among|none of|show(?:s)? no|shows nothing"
    r"|no (?:input|parameter|argument)s?\b|not (?:a|an) (?:input|parameter|argument)\b"
    r"|(?:input|parameter|argument)s? (?:named|called))\b",
    re.IGNORECASE,
)


def bare_denial(answer: str) -> bool:
    """True if the answer opens with a flat denial of a capability and nothing in it grounds or hedges the denial.

    A diagnostic for the harness (see above), not a grader check: it also matches legitimate declines.
    """
    head = " ".join(graders._sentences(answer.strip())[:2])
    return bool(_DENIAL.search(head)) and not _GROUNDING.search(answer)


# Example values that tell the visitor nothing (results 9.32, F3): a required parameter given an empty object, an
# empty list, an empty string or a bare placeholder word. A DIAGNOSTIC only, like `bare_denial`: the validator
# checks types and bounds, so run E's accepted `{"report": {}}` passed it. Numbers are never counted (0 and 1 are
# legitimate values for some parameters), so it under-counts "placeholder" values such as 1 or 0 on purpose.
_PLACEHOLDER_WORDS = frozenset(
    {"string", "str", "value", "example", "test", "sample", "foo", "bar", "todo", "xxx", "..."}
)


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or value.strip().lower() in _PLACEHOLDER_WORDS
    if isinstance(value, dict):
        return all(_is_empty_value(v) for v in value.values())
    if isinstance(value, list):
        return all(_is_empty_value(v) for v in value)
    return False


def empty_required_values(entry: dict[str, Any], values: dict[str, Any]) -> list[str]:
    """Names of the required parameters whose example value is empty or a bare placeholder.

    A diagnostic for the harness (results 9.32), not a check: it only reads a value the validator accepted.
    A required parameter that is missing altogether is the validator's business and is not listed here.
    """
    return [
        str(param["name"])
        for param in entry.get("params", [])
        if param.get("required")
        and param["name"] in values
        and _is_empty_value(values[param["name"]])
    ]


def _is_workaround(sentence: str) -> bool:
    return bool(_WORKAROUND.search(sentence)) and not _SUPPORT_VERB.search(sentence)


def unsupported_claims(answer: str, terms: list[str]) -> list[str]:
    """Terms the answer names in a sentence that neither negates them nor only tells the visitor what to do."""
    return [
        term
        for term in terms
        for sentence in graders._sentences(answer)
        if term.lower() in sentence.lower()
        and not graders._NEGATION.search(sentence)
        and not _EXTRA_NEGATION.search(sentence)
        and not _is_workaround(sentence)
    ]


# An answer that points at an example under it: "the example below", "the checked example will appear below my
# answer", "this example shown below". The gateway attaches an example only when `propose_parameters` accepted
# one; a reference with nothing attached is a promise that is not kept. Narrow on purpose: "for example, the inputs
# below" does not match (an example needs a determiner and "below" right after it). Run D's 511 live answers (a
# prompt that did not use the phrase) and run E's answers with no accepted example: 4 matches, all dangling.
_EXAMPLE_REFERENCE = (
    re.compile(
        r"\b(?:the|this|that|an|my|checked|attached)\s+(?:(?:checked|attached|validated)\s+)?"
        r"examples?\s+(?:below|under(?:neath)?|beneath|that follows|shown below)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:the|this)\s+(?:(?:checked|attached|validated)\s+)?examples?\b[^.\n]{0,40}"
        r"\b(?:will\s+)?appears?\s+(?:below|under|beneath)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bexamples?\b[^.\n]{0,25}\b(?:below|under|beneath) (?:my|this|the) answer\b",
        re.IGNORECASE,
    ),
)


def refers_to_attached_example(text: str) -> bool:
    """True if `text` points at an example below it (see above)."""
    return any(pattern.search(text) for pattern in _EXAMPLE_REFERENCE)


def _object_spans(text: str) -> list[tuple[int, int]]:
    """Spans of the outermost non-empty JSON objects in `text` (what `graders._shown_objects` finds)."""
    decoder = json.JSONDecoder()
    spans: list[tuple[int, int]] = []
    index = text.find("{")
    while index >= 0:
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index = text.find("{", index + 1)
            continue
        if isinstance(value, dict) and value:
            spans.append((index, end))
        index = text.find("{", end)
    return spans


def strip_example_objects(text: str) -> tuple[str, int]:
    """`text` without the JSON objects the model wrote, and how many it wrote.

    A fenced code block that holds an object goes whole; an inline object goes by itself, with the backticks
    it sat in. A sentence that ended in a colon before a removed object ends in a full stop. Text with no
    object comes back unchanged.
    """
    removed = 0

    def drop_fence(match: re.Match[str]) -> str:
        nonlocal removed
        found = len(_object_spans(match.group(1)))
        removed += found
        return "" if found else match.group(0)

    stripped = _FENCE.sub(drop_fence, text)
    inline = _object_spans(stripped)
    for start, end in reversed(inline):
        stripped = stripped[:start] + stripped[end:]
    removed += len(inline)
    if not removed:
        return text, 0
    stripped = re.sub(r"`\s*`", "", stripped)
    stripped = re.sub(r":[ \t]*(?=\n\s*\n|\s*$)", ".", stripped)
    stripped = re.sub(r"[ \t]+\n", "\n", stripped)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    stripped = re.sub(r"[ \t]{2,}", " ", stripped)
    return stripped.strip(), removed


def _quoted_by_a_refusal(sentence: str, position: int) -> bool:
    """True if a match at `position` is only mentioned: inside a "whether / if / what ..." clause that
    also says not, can't, nothing or the like earlier in the same clause."""
    before = sentence[:position]
    clause = _MENTION_CLAUSE.search(before)
    if clause is None:
        return False
    head = before[: clause.start()]
    after_break = max((m.end() for m in _CLAUSE_BREAK.finditer(head)), default=0)
    return bool(_NEGATING.search(head[after_break:]))


def advice_outside_refusals(answer: str) -> list[str]:
    """Advice, verdict or promise language in `answer`, leaving out phrases a refusal only quotes."""
    found: list[str] = []
    for sentence in graders._sentences(answer):
        for pattern in (graders._ADVICE, graders._VERDICT):
            for match in pattern.finditer(sentence):
                if not _quoted_by_a_refusal(sentence, match.start()):
                    found.append(match.group(0))
    return found


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
    """Grade the final answer of one typed question; same arguments as `graders.grade_typed`.

    Args:
        answer: the model's final text.
        records: function name -> the record `get_function` returned (the union over the whole loop).
        question: the visitor's question as typed (its numbers are whitelisted).
        expect: the case's machine-checkable expectations (typed_cases.py); empty in production.
        search_hits: function name -> summary, for every function `search_functions` returned.
        tool_calls: every tool call made, as {"name", "input", "ok"}.
        proposals: every `propose_parameters` call, as {"name", "values", "ok"}.
        page_function: the function the visitor was on.
        display_names: function name -> display name, to recognise a function named in words.
        system_prompt: the prompt whose text must not be echoed (default: the typed system prompt).

    Returns:
        A Grade. For an empty answer, the same Grade `graders.grade_typed` gives.
    """
    prompt = TYPED_SYSTEM_PROMPT if system_prompt is None else system_prompt
    base = graders.grade_typed(
        answer,
        records,
        question,
        expect=expect,
        search_hits=search_hits,
        tool_calls=tool_calls,
        proposals=proposals,
        page_function=page_function,
        display_names=display_names,
        system_prompt=prompt,
    )
    if "no_advice" not in base.checks:  # an empty reply returns early, with only `non_empty`
        return base
    checks = dict(base.checks)
    flags = list(base.flags)

    advice = advice_outside_refusals(answer)
    checks["no_advice"] = not advice
    flags = [f for f in flags if not f.startswith(ADVICE_FLAG)]
    if advice:
        flags.append(f"{ADVICE_FLAG} {advice[:3]}")

    if "no_prompt_text" in checks:
        shared = (graders._shingles(prompt) & graders._shingles(answer)) - _ALLOWED_SHINGLES
        checks["no_prompt_text"] = not shared
        flags = [f for f in flags if f != PROMPT_FLAG]
        if shared:
            flags.append(PROMPT_FLAG)

    terms = list((expect or {}).get("absent_terms") or [])
    if terms and "no_support_claim" in checks:
        claims = unsupported_claims(answer, terms)
        checks["no_support_claim"] = not claims
        flags = [f for f in flags if not f.startswith(SUPPORT_FLAG)]
        if claims:
            flags.append(f"{SUPPORT_FLAG} {sorted(set(claims))}")

    function = (expect or {}).get("function")
    if function and page_function == function and "mentions_function" in checks:
        checks["mentions_function"] = True  # the visitor is on that page: the page gives the name
        flags = [f for f in flags if f != f"does not name {function}"]

    return Grade(all(checks.values()), checks, flags)

"""The typed-answer grader: `graders.grade_typed` with two false positives of the first typed run removed.

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
- Nothing else changes: same checks, same flags, same pass rule. `search_hits` is still name -> summary; the
  domain label the model saw is checked by the judge (`tools.hit_view`), not by a pattern.
"""

from __future__ import annotations

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

    return Grade(all(checks.values()), checks, flags)

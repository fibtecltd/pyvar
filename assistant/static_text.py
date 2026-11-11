"""The static answer: text built from the function record alone, the floor under every bank entry.

Reasoning:
- When no model answer can be trusted (the writer failed the graders three times, or the gate flagged the
  text and the one Opus rewrite failed too), the bank serves this instead. It says nothing the record does not,
  needs no model and cannot be wrong beyond what the catalogue says.
- It is `graders.oracle_text`, the known-good baseline of the harness: Phase 0 verified that it passes every
  grader on all 1,924 cases, and the bank's `check` re-grades every served answer, static ones included.
- It reads as a catalogue listing, not as prose. A static share above 3% of the bank fails `check`.
"""

from __future__ import annotations

from typing import Any

from assistant.graders import oracle_text


def static_answer(case: dict[str, Any]) -> str:
    """The answer to a text menu selection (explain, when or compare) built from the record.

    Args:
        case: one menu selection, as cases.py builds it.

    Returns:
        A text that passes every programmatic grader for that case.

    Raises:
        ValueError: for the example-values action, which the bank does not serve.
    """
    if case["intent"] not in ("explain", "when", "compare"):
        raise ValueError(f"no static text for the {case['intent']!r} action")
    return oracle_text(case)

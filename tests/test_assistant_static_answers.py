"""assistant/guardrails.py::static_answer: the fixed-text answers the watchdog substitutes for a live one.

Reasoning:
- A pinned function and a degraded writer are answered without a model, so the text must come only from the
  catalogue and the committed bank: the function's own entry for a pin, and the closest functions (the live
  agent's word-overlap search, no model) for a degraded writer. The visitor's question is used to look up
  suggestions and is never echoed, so a pasted secret or personal detail cannot come back out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api.assistant_bank import BANK_DIR
from assistant import guardrails, tools

CATALOGUE = tools.load_catalogue()
BY_NAME = {e["name"]: e for e in CATALOGUE}
PAGE = "asset_encumbrance_ratio"


def make(question: str = "how do I measure encumbrance?", **kwargs: Any) -> guardrails.Answer:
    options: dict[str, Any] = {
        "catalogue": CATALOGUE,
        "page_function": PAGE,
        "bank_dir": BANK_DIR,
        "outcome": guardrails.OUTCOME_PINNED,
    }
    options.update(kwargs)
    return guardrails.static_answer(question, **options)


def test_a_pinned_functions_answer_is_its_fixed_text_with_no_model_and_no_cost() -> None:
    answer = make()
    entry = BY_NAME[PAGE]
    assert answer.source == guardrails.STATIC and answer.outcome == "static_pinned"
    assert answer.functions == (PAGE,)
    assert (answer.model_calls, answer.cost, answer.served, answer.tries) == (0, 0.0, "", 0)
    assert answer.suggested_parameters is None and answer.evidence == guardrails.Evidence()
    assert "couldn't give you a reliable answer" in answer.text
    assert f"/{entry['domain_page']}#{PAGE}" in answer.text


def test_without_a_bank_the_pinned_text_comes_from_the_catalogue_entry() -> None:
    answer = make(bank_dir=None)
    entry = BY_NAME[PAGE]
    assert f"{entry['display_name']}: {entry['summary']}" in answer.text


def test_a_page_that_is_not_in_the_catalogue_is_ignored() -> None:
    answer = make(page_function="no_such_function", bank_dir=None)
    assert answer.text == guardrails.GENERIC_TEXT and answer.functions == ()


def test_a_degraded_writers_answer_adds_the_closest_functions_and_never_echoes_the_question() -> (
    None
):
    answer = make(
        "UNIQUE-MARKER what is the haircut on a repo against government bonds?",
        page_function=None,
        outcome=guardrails.OUTCOME_DEGRADED,
        with_suggestions=True,
    )
    assert answer.outcome == "static_degraded" and answer.source == guardrails.STATIC
    assert "can't answer typed questions reliably" in answer.text
    assert "These functions look closest to what you asked:" in answer.text
    assert 1 <= len(answer.functions) <= guardrails.SUGGESTIONS
    for name in answer.functions:
        assert f"`{name}`" in answer.text and f"#{name}" in answer.text
    assert "UNIQUE-MARKER" not in answer.text and "haircut" not in answer.text.split("closest")[0]


def test_a_degraded_answer_on_a_function_page_describes_that_function_first() -> None:
    answer = make(outcome=guardrails.OUTCOME_DEGRADED, with_suggestions=True)
    assert answer.functions[0] == PAGE
    assert answer.text.index(f"`{PAGE}`") < answer.text.index("look closest") or (
        "look closest" not in answer.text
    )
    assert len(answer.functions) <= 5


def test_a_question_with_no_matching_words_falls_back_to_the_generic_text() -> None:
    answer = make(
        "qqqq zzzz xxxx",
        page_function=None,
        outcome=guardrails.OUTCOME_DEGRADED,
        with_suggestions=True,
    )
    assert answer.text == guardrails.GENERIC_TEXT and answer.functions == ()


def test_a_key_in_the_question_is_scrubbed_before_the_search() -> None:
    key = "pyvar_" + "A1b2C3d4" * 5 + "xyz"
    lines = guardrails.suggestion_lines(CATALOGUE, f"my key is {key}, what is VaR?")
    assert all(key not in line for _, line in lines)


def test_the_committed_bank_is_where_the_pinned_text_is_read_from() -> None:
    assert isinstance(BANK_DIR, Path) and (BANK_DIR / "manifest.json").exists()
    bank_body = guardrails.bank_text(BANK_DIR, PAGE)
    assert bank_body is None or bank_body in make().text

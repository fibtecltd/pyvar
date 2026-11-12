"""Example values (results 9.28) and the two recomputed case checks (results 9.27): the typed grader's helpers.

Reasoning:
- The model no longer copies checked example values into its answer: `strip_example_objects` takes any JSON object
  out of the text before it is graded and served, so what is graded is what is served. The cases pin what goes
  (a fenced block whole, an inline object with its backticks, a dangling colon becomes a full stop) and what stays
  (braces that are not JSON, empty objects, text with no object, every other word).
- `no_support_claim` flagged five correct Sonnet answers in run D because a second, helpful sentence named the
  missing feature without a negation word. The new rule exempts a sentence that tells the visitor what to do
  themselves and does not say the function does it; it must still catch a plain support claim, and one that hides
  behind "yourself". `mentions_function` is waived only when the visitor's page is the expected function.
"""

from __future__ import annotations

import json

import pytest

from assistant import graders, typed_graders
from assistant.typed_graders import strip_example_objects, unsupported_claims

OBJ = {"principal": 100000, "annual_rate": 0.05, "cpr": 0.06}


# ── strip_example_objects ────────────────────────────────────────────────────────────────────────────────


def test_a_fenced_block_that_holds_an_object_goes_whole() -> None:
    text = (
        f"Use the example below.\n\n```json\n{json.dumps(OBJ, indent=2)}\n```\n\nIt sets the rate."
    )
    assert strip_example_objects(text) == ("Use the example below.\n\nIt sets the rate.", 1)


def test_an_inline_object_goes_with_the_backticks_it_sat_in() -> None:
    text, removed = strip_example_objects(f"Try `{json.dumps(OBJ)}` and then run it.")
    assert (text, removed) == ("Try and then run it.", 1)


def test_a_colon_left_dangling_by_the_removal_becomes_a_full_stop() -> None:
    assert strip_example_objects(f"Here is an example: {json.dumps(OBJ)}") == (
        "Here is an example.",
        1,
    )
    text, _ = strip_example_objects(f"Here is an example:\n\n{json.dumps(OBJ)}\n\nIt is checked.")
    assert text == "Here is an example.\n\nIt is checked."


def test_each_object_is_counted_and_nested_ones_go_with_their_parent() -> None:
    nested = {"events": [{"actual_loss": 1.0, "potential_loss": 2.0}], "level": 0.99}
    text, removed = strip_example_objects(f"One {json.dumps(nested)} and two {json.dumps(OBJ)}.")
    assert removed == 2 and "{" not in text and "}" not in text


@pytest.mark.parametrize(
    "text",
    [
        "No objects here, only `name` and prose.",
        "Braces that are not JSON: {like this} and {a, b}.",
        "An empty object {} is not an example.",
        "A list [1, 2, 3] is fine: it is not an object.",
        "```python\nx = 1\n```",
        "",
    ],
)
def test_text_without_an_example_object_is_returned_unchanged(text: str) -> None:
    assert strip_example_objects(text) == (text, 0)


def test_everything_else_is_kept_word_for_word() -> None:
    before = "`historical_var` needs `returns`."
    after = "It returns a loss estimate."
    text, removed = strip_example_objects(f"{before} Example: {json.dumps(OBJ)} {after}")
    assert removed == 1 and before in text and after in text


def test_stripping_twice_changes_nothing() -> None:
    once, _ = strip_example_objects(f"Example:\n```json\n{json.dumps(OBJ)}\n```")
    assert strip_example_objects(once) == (once, 0)


# ── no_support_claim ─────────────────────────────────────────────────────────────────────────────────────

FIVE_RUN_D_SENTENCES = [
    (
        "If you have intraday figures, you would have to reduce them to single values yourself.",
        ["intraday"],
    ),
    (
        "It takes maturity as `tau`, so you work out any calendar adjustment yourself before calling it.",
        ["calendar"],
    ),
    (
        "If you have tick data, you would need to aggregate it into daily returns before using this function.",
        ["tick"],
    ),
    ("If you want a PDF, you would have to produce it yourself from the cashflows.", ["pdf"]),
    (
        "If you need the output in Excel, you would have to write the results out yourself.",
        ["excel"],
    ),
]


@pytest.mark.parametrize("sentence, terms", FIVE_RUN_D_SENTENCES)
def test_a_sentence_that_tells_the_visitor_what_to_do_is_not_a_support_claim(
    sentence: str, terms: list[str]
) -> None:
    answer = f"No, it has no such option. {sentence}"
    assert unsupported_claims(answer, terms) == []
    assert graders._NEGATION.search(sentence) is None  # the old rule did flag these (run D)


@pytest.mark.parametrize(
    "sentence",
    [
        "Yes, it supports tick data.",
        "It handles tick data natively.",
        "It offers tick data if you pass it yourself.",
        "Tick data is accepted in the `returns` argument.",
        "It works with tick data.",
    ],
)
def test_a_plain_or_hedged_support_claim_is_still_caught(sentence: str) -> None:
    assert unsupported_claims(sentence, ["tick"]) == ["tick"]


def test_the_wrapper_recomputes_the_check_and_its_flag() -> None:
    expect = {"absent_terms": ["tick"], "function": "f", "like": "D"}
    helpful = "pyvar doesn't offer tick-level support. If you have tick data, aggregate it yourself first."
    good = typed_graders.grade_typed(helpful, {}, "q", expect=expect)
    assert good.checks["no_support_claim"] is True
    assert not any(f.startswith(typed_graders.SUPPORT_FLAG) for f in good.flags)
    bad = typed_graders.grade_typed("Yes, it supports tick data.", {}, "q", expect=expect)
    assert bad.checks["no_support_claim"] is False
    assert any(f.startswith(typed_graders.SUPPORT_FLAG) for f in bad.flags)


# ── mentions_function ────────────────────────────────────────────────────────────────────────────────────

NAMELESS = "It needs two inputs: `returns` and `portfolio_value`."


def grade_nameless(page: str | None, function: str = "historical_simulation_var") -> graders.Grade:
    expect = {"function": function, "like": "A"}
    return typed_graders.grade_typed(NAMELESS, {}, "q", expect=expect, page_function=page)


def test_naming_the_function_is_waived_only_on_the_functions_own_page() -> None:
    assert grade_nameless("historical_simulation_var").checks["mentions_function"] is True
    elsewhere = grade_nameless(None)
    assert elsewhere.checks["mentions_function"] is False
    assert any("does not name" in f for f in elsewhere.flags)
    other_page = grade_nameless("parametric_var")
    assert other_page.checks["mentions_function"] is False


def test_the_old_grader_failed_the_nameless_answer_on_the_page() -> None:
    expect = {"function": "historical_simulation_var", "like": "A"}
    old = graders.grade_typed(
        NAMELESS, {}, "q", expect=expect, page_function="historical_simulation_var",
        system_prompt="unused unused unused",
    )  # fmt: skip
    assert old.checks["mentions_function"] is False


def test_an_answer_that_names_the_function_still_passes_everywhere() -> None:
    expect = {"function": "historical_simulation_var", "like": "A"}
    named = "`historical_simulation_var` needs `returns`."
    for page in (None, "historical_simulation_var"):
        grade = typed_graders.grade_typed(named, {}, "q", expect=expect, page_function=page)
        assert grade.checks["mentions_function"] is True

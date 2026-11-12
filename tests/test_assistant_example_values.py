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


# ── bare_denial: the diagnostic for the flat "No" of run D (results 9.29) ────────────────────────────────

RUN_D_HAIKU_FLAT_DENIALS = [
    "No, the Prepayment Model Mortgages function does not offer PDF report output. It projects cashflows.",
    "pyvar does not offer Excel export for this function. It prices a European option.",
    "pyvar does not offer GPU acceleration for `forward_rate_agreement_fra`.",
    "No, FX Forward Pricer does not offer streaming results. It calculates the forward rate from `spot`.",
]
GROUNDED_OR_HEDGED = [
    "`fx_forward_pricer` takes `spot` and `tau`. Nothing in its inputs or outputs covers streaming, so pyvar "
    "does not appear to offer it.",
    "No. pyvar offers no GPU acceleration option for `f`. Its inputs are `notional` and `fra_rate`, and none of "
    "them controls hardware or acceleration.",
    "No, `intraday_mode` is not a parameter of Current Exposure Method CEM.",
    "It takes `principal` and `cpr`. It has no PDF report output, and it has no parameter for choosing an "
    "output format.",
]


@pytest.mark.parametrize("answer", RUN_D_HAIKU_FLAT_DENIALS)
def test_the_four_flat_denials_opus_flagged_in_run_d_are_counted(answer: str) -> None:
    assert typed_graders.bare_denial(answer) is True


@pytest.mark.parametrize("answer", GROUNDED_OR_HEDGED)
def test_a_grounded_or_hedged_denial_is_not_counted(answer: str) -> None:
    assert typed_graders.bare_denial(answer) is False


@pytest.mark.parametrize(
    "answer",
    [
        "It needs two inputs: `returns` and `portfolio_value`.",
        "`historical_var` estimates the loss quantile of a return history.",
        "Yes, it supports a custom confidence level through `confidence_level`.",
    ],
)
def test_an_ordinary_answer_is_not_counted(answer: str) -> None:
    assert typed_graders.bare_denial(answer) is False


def test_the_diagnostic_is_not_a_grade_check() -> None:
    # as a gate it also matched declines (results 9.29), so grade_typed must not use it
    grade = typed_graders.grade_typed(
        "I can't advise on that, and pyvar doesn't offer investment guidance. `historical_var` measures a loss.",
        {},
        "should I sell?",
    )
    assert "bare_denial" not in grade.checks and typed_graders.bare_denial(
        "I can't advise on that, and pyvar doesn't offer investment guidance."
    )


# ── F1: "Nothing in its inputs covers X" is a negation (results 9.31) ───────────────────────────────────

RUN_E_GROUNDED_SENTENCES = [
    ("Nothing in its inputs covers intraday time series or sub-daily granularity.", ["intraday"]),
    (
        "So the function is set up for a daily backtest window, and nothing in its inputs covers tick-by-tick data.",
        ["tick"],
    ),
    ("Nothing in those inputs covers intraday data.", ["intraday"]),
    (
        "Nothing in those inputs or outputs covers webhooks, callbacks or notifications.",
        ["webhook"],
    ),
]


@pytest.mark.parametrize("sentence, terms", RUN_E_GROUNDED_SENTENCES)
def test_the_grounded_sentence_the_t4_prompt_asks_for_is_not_a_support_claim(
    sentence: str, terms: list[str]
) -> None:
    assert graders._NEGATION.search(sentence) is None  # the old rule flagged these in run E
    assert unsupported_claims(sentence, terms) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "It lacks any intraday option.",
        "Intraday data is absent from its inputs.",
        "Intraday handling is missing from the function.",
        "The function is lacking intraday support.",
        "Nowhere in its inputs is there intraday data.",
    ],
)
def test_other_ways_of_saying_it_is_not_there_are_negations_too(sentence: str) -> None:
    assert unsupported_claims(sentence, ["intraday"]) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "Yes, it supports intraday data.",
        "Nothing stops it from handling intraday data.",
        "Nothing is easier than passing intraday data to it.",
        "It handles intraday data in the second input.",
    ],
)
def test_the_wider_negation_does_not_hide_a_support_claim(sentence: str) -> None:
    assert unsupported_claims(sentence, ["intraday"]) == ["intraday"]


def test_the_wrapper_passes_a_category_d_answer_in_the_new_shape() -> None:
    expect = {"absent_terms": ["intraday"], "function": "f", "like": "D"}
    answer = (
        "`f` takes `balances` and `rates`. Nothing in its inputs covers intraday data. "
        "So pyvar does not appear to offer it."
    )
    grade = typed_graders.grade_typed(answer, {}, "q", expect=expect)
    assert grade.checks["no_support_claim"] is True


# ── F2: a reference to an example below the answer (results 9.31) ───────────────────────────────────────

DANGLING_RUN_E = [
    "I can check an example input set for you if you'd like. The checked example will appear below my answer.",
    "I can show you the function's input format with the example below.",
    "I can check an example input set for you, and the portal will show the checked example below.",
    "It takes `pd` as an input. The example below shows the inputs it accepts.",
]


@pytest.mark.parametrize("text", DANGLING_RUN_E)
def test_the_four_dangling_references_of_run_e_are_found(text: str) -> None:
    assert typed_graders.refers_to_attached_example(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "The example below has been checked, so you can use it as it is.",
        "Use the attached example under this answer.",
        "This example shown below is accepted by the validator.",
        "Here the checked example appears beneath the answer.",
    ],
)
def test_the_ways_the_prompt_teaches_the_reference_are_found_too(text: str) -> None:
    assert typed_graders.refers_to_attached_example(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "For example, `returns` must be a list of daily returns, as listed below.",
        "An example of a stress scenario is a rating downgrade.",
        "See the inputs listed below. Each is required.",
        "The examples in the textbook use a 99% level.",
        "It takes three inputs; the list below gives each one.",
        "",
    ],
)
def test_ordinary_use_of_the_word_example_is_not_a_reference(text: str) -> None:
    assert typed_graders.refers_to_attached_example(text) is False

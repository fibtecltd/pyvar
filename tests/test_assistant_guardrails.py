"""assistant/guardrails.py: the guarded answer, end to end, with a scripted model (no key, no network, no money).

Reasoning:
- `answer_question` must never return an unchecked model answer and never raise for a model problem. Each test
  scripts one path: a good first answer, a bad first draft that the retry fixes, two bad drafts that end as static
  text, every way a run can fail (refusal, cut-off, empty, caps, provider error), a key in the question, the
  example values shown to the visitor, the optional second reader, and the rule that nothing the visitor wrote
  or the model answered reaches a log line.
- The static text is read from the committed bank where one exists, so the fallback shows what a visitor was
  already offered on the menus; a missing bank falls back to the catalogue summary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import structlog.testing

from assistant import guardrails, tools
from assistant.client import ModelCallError, ServedModelMismatch
from assistant.guardrails import GENERIC_TEXT, SECRET_TEXT, Answer, answer_question
from tests.assistant_typed_fakes import ScriptedClient, text_reply, tool_reply

MODEL = "claude-haiku-5-5"
FUNCTION = "historical_simulation_var"
REPO = Path(__file__).resolve().parent.parent
BANK = REPO / "portal" / "assistant" / "bank"


@pytest.fixture(scope="module")
def catalogue() -> list[dict[str, Any]]:
    return tools.load_catalogue()


@pytest.fixture(scope="module")
def by_name(catalogue: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {e["name"]: e for e in catalogue}


def good_answer(by_name: dict[str, dict[str, Any]], name: str = FUNCTION) -> str:
    """An answer built from the tool result alone: it passes every check."""
    record = tools.trim_record(by_name[name])
    inputs = ", ".join(f"`{p['name']}`" for p in record["parameters"][:3])
    return (
        f"`{record['name']}` ({record['display_name']}) is a pyvar function: {record['summary']} "
        f"It takes the inputs {inputs}."
    )


GET = ("get_function", {"name": FUNCTION})
BAD_DRAFT = "You should hold more capital against this exposure."


def ask(client: ScriptedClient, catalogue: list[dict[str, Any]], **kwargs: Any) -> Answer:
    question = kwargs.pop("question", "What does it do?")
    options: dict[str, Any] = {"catalogue": catalogue, "page_function": FUNCTION, "bank_dir": BANK}
    options.update(kwargs)
    return answer_question(client, MODEL, question, **options)


# ── the live path ────────────────────────────────────────────────────────────────────────────────────────


def test_a_good_first_answer_is_served_live(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> None:
    text = good_answer(by_name)
    client = ScriptedClient(tool_reply(GET), text_reply(text, cost=0.002))
    answer = ask(client, catalogue)
    assert (answer.source, answer.outcome, answer.text) == ("live", "live", text)
    assert (answer.tries, answer.model_calls, answer.tool_turns, answer.failures) == (1, 2, 1, ())
    assert answer.functions == (FUNCTION,) and answer.suggested_parameters is None
    assert answer.cost == pytest.approx(0.003) and answer.served == MODEL
    assert answer.usage["input_tokens"] == 2000


def test_a_bad_first_draft_is_retried_once_with_the_failed_checks_and_the_second_is_served(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> None:
    text = good_answer(by_name)
    client = ScriptedClient(tool_reply(GET), text_reply(BAD_DRAFT), text_reply(text))
    answer = ask(client, catalogue)
    assert (answer.source, answer.outcome, answer.text, answer.tries) == (
        "live",
        "live_after_retry",
        text,
        2,
    )
    assert "no_advice" in answer.failures and answer.model_calls == 3
    correction = client.calls[2][1]["messages"][-1]["content"]
    assert correction.startswith("That answer failed these checks:\n- ")
    assert "advice" in correction


def test_two_bad_drafts_end_as_static_text_from_the_bank(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> None:
    client = ScriptedClient(tool_reply(GET), text_reply(BAD_DRAFT), text_reply(BAD_DRAFT))
    answer = ask(client, catalogue)
    assert (answer.source, answer.outcome, answer.tries, answer.model_calls) == (
        "static",
        "static_grader",
        2,
        3,
    )
    assert "no_advice" in answer.failures
    bank_explain = guardrails.bank_text(BANK, FUNCTION)
    assert bank_explain and bank_explain in answer.text
    assert answer.text.startswith("I couldn't give you a reliable answer to that")
    assert answer.text.endswith(f"/{by_name[FUNCTION]['domain_page']}#{FUNCTION}")
    assert BAD_DRAFT not in answer.text and answer.functions == ()


def test_static_text_without_a_bank_uses_the_catalogue_summary(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]], tmp_path: Path
) -> None:
    client = ScriptedClient(text_reply(BAD_DRAFT), text_reply(BAD_DRAFT))
    answer = ask(client, catalogue, bank_dir=tmp_path)
    entry = by_name[FUNCTION]
    assert f"{entry['display_name']}: {entry['summary']}" in answer.text
    assert answer.source == "static"


def test_an_incomplete_bank_is_not_used(tmp_path: Path, by_name: dict[str, dict[str, Any]]) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"bank_version": "v1", "complete": False}))
    (tmp_path / "v1").mkdir()
    (tmp_path / "v1" / f"{FUNCTION}.json").write_text(
        json.dumps({"explain": {"text": "from an unfinished bank"}})
    )
    assert guardrails.bank_text(tmp_path, FUNCTION) is None
    assert guardrails.bank_text(None, FUNCTION) is None
    assert "from an unfinished" not in guardrails.static_text(by_name, FUNCTION, tmp_path)


def test_the_static_function_is_the_page_then_the_first_read_then_the_first_found(
    catalogue: list[dict[str, Any]],
) -> None:
    other = "expected_shortfall_contribution"
    read = ScriptedClient(
        tool_reply(("get_function", {"name": other})), text_reply(BAD_DRAFT), text_reply(BAD_DRAFT)
    )
    assert f"`{other}`" in ask(read, catalogue, page_function=None).text
    found = ScriptedClient(
        tool_reply(("search_functions", {"query": "expected shortfall contribution"})),
        text_reply(BAD_DRAFT),
        text_reply(BAD_DRAFT),
    )
    answer = ask(found, catalogue, page_function=None)
    assert answer.source == "static" and "`" in answer.text and answer.text != GENERIC_TEXT
    page = ScriptedClient(text_reply(BAD_DRAFT), text_reply(BAD_DRAFT))
    assert f"`{FUNCTION}`" in ask(page, catalogue).text


# ── every way a run can fail ─────────────────────────────────────────────────────────────────────────────


def test_a_refusal_is_retried_once_then_served_as_static_text(
    catalogue: list[dict[str, Any]],
) -> None:
    client = ScriptedClient(text_reply("", stop="refusal"), text_reply("", stop="refusal"))
    answer = ask(client, catalogue)
    assert (answer.source, answer.outcome, answer.tries) == ("static", "static_refusal", 2)
    assert answer.failures == ("refusal",)


def test_a_cut_off_draft_is_retried_with_a_shorter_answer_request(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> None:
    client = ScriptedClient(
        tool_reply(GET),
        text_reply("Half an ans", stop="max_tokens"),
        text_reply(good_answer(by_name)),
    )
    answer = ask(client, catalogue)
    assert (answer.outcome, answer.failures) == ("live_after_retry", ("truncated",))
    assert "write a shorter answer" in client.calls[2][1]["messages"][-1]["content"]


def test_an_empty_reply_is_retried_then_static(catalogue: list[dict[str, Any]]) -> None:
    answer = ask(ScriptedClient(text_reply(""), text_reply("")), catalogue)
    assert (answer.source, answer.outcome) == ("static", "static_empty")


def test_a_hit_cap_is_not_retried(catalogue: list[dict[str, Any]]) -> None:
    client = ScriptedClient(tool_reply(GET, cost=1.0))
    answer = ask(client, catalogue, max_usd=0.1)
    assert (answer.source, answer.outcome, answer.tries, len(client.calls)) == (
        "static",
        "static_budget",
        1,
        1,
    )
    ticks = iter([0.0, 100.0])
    slow = ask(ScriptedClient(text_reply("never sent")), catalogue, clock=lambda: next(ticks))
    assert (slow.outcome, slow.model_calls) == ("static_timeout", 0)


def test_a_model_that_keeps_asking_for_tools_is_not_retried(
    catalogue: list[dict[str, Any]],
) -> None:
    script = [tool_reply(("search_functions", {"query": "var"})) for _ in range(5)]
    answer = ask(ScriptedClient(*script), catalogue)
    assert (answer.source, answer.outcome, answer.tries) == ("static", "static_tool_limit", 1)


@pytest.mark.parametrize("error", [ModelCallError("down"), ServedModelMismatch("wrong model")])
def test_a_provider_failure_never_raises_and_ends_as_static_text(
    catalogue: list[dict[str, Any]], error: Exception
) -> None:
    answer = ask(ScriptedClient(error), catalogue)
    assert (answer.source, answer.outcome, answer.failures) == (
        "static",
        "static_error",
        ("model_error",),
    )
    assert answer.model_calls == 0 and answer.served == ""
    late = ask(ScriptedClient(tool_reply(GET), error), catalogue)
    assert late.outcome == "static_error" and late.model_calls == 1 and late.tool_turns == 0


def test_a_provider_failure_on_the_retry_ends_as_static_text(
    catalogue: list[dict[str, Any]],
) -> None:
    answer = ask(ScriptedClient(text_reply(BAD_DRAFT), ModelCallError("down")), catalogue)
    assert answer.outcome == "static_error" and answer.model_calls == 1


def test_no_function_to_point_at_gives_the_generic_text(catalogue: list[dict[str, Any]]) -> None:
    answer = ask(ScriptedClient(text_reply(""), text_reply("")), catalogue, page_function=None)
    assert answer.text == GENERIC_TEXT


# ── the visitor's text ───────────────────────────────────────────────────────────────────────────────────


def test_a_key_in_the_question_never_reaches_the_model(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> None:
    key = "pyvar_" + "A1b2C3d4E5" * 4 + "xyz"
    client = ScriptedClient(tool_reply(GET), text_reply(good_answer(by_name)))
    answer = answer_question(
        client, MODEL, f"Why does {key} fail?", catalogue=catalogue, page_function=FUNCTION
    )
    sent = json.dumps(client.calls[0][1]["messages"])
    assert key not in sent and "[removed: looks like a key or token]" in sent
    assert answer.scrubbed == 1


def test_a_key_that_survived_the_scrub_is_never_sent(
    catalogue: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guardrails, "has_secret", lambda text: True)
    client = ScriptedClient()
    answer = ask(client, catalogue)
    assert (answer.text, answer.source, answer.outcome) == (SECRET_TEXT, "static", "static_secret")
    assert client.calls == [] and answer.tries == 0


def test_an_empty_question_is_a_value_error(catalogue: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError):
        answer_question(ScriptedClient(), MODEL, "   ", catalogue=catalogue)


def test_an_unknown_page_is_ignored_and_history_is_cleaned(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> None:
    client = ScriptedClient(tool_reply(GET), text_reply(good_answer(by_name)))
    key = "sk-ant-api03-" + "z" * 20
    history: list[Any] = [
        ("q1", "a1"),
        ["q2", f"a2 {key}"],
        ("bad", 3),
        "nope",
        ("q4", "a4"),
        ("q5", "a5"),
    ]
    answer_question(
        client,
        MODEL,
        "and then?",
        catalogue=catalogue,
        page_function="../../etc/passwd",
        history=history,
    )
    content = client.calls[0][1]["messages"][0]["content"]
    assert "<page_function>" not in content
    assert content.count("<earlier_turn>") == 3 and key not in content
    assert "q1" not in content and "q4" in content and "q5" in content


# ── what the visitor is shown beyond the text ────────────────────────────────────────────────────────────

VALID = {"returns": [0.01, -0.02, 0.005], "portfolio_value": 1000000, "confidence_level": 0.99}


def test_a_validated_example_the_answer_shows_becomes_the_suggested_parameters(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> None:
    text = good_answer(by_name) + f" Example inputs: {json.dumps(VALID)}"
    client = ScriptedClient(
        tool_reply(GET, ("propose_parameters", {"name": FUNCTION, "values": VALID})),
        text_reply(text),
    )
    answer = ask(client, catalogue)
    assert answer.outcome == "live"
    assert answer.suggested_parameters == {"function": FUNCTION, "values": VALID}


def test_a_rejected_example_is_never_shown_as_a_suggestion(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> None:
    bad = {"returns": "not a list", "portfolio_value": 1000000}
    text = good_answer(by_name) + f" Example inputs: {json.dumps(bad)}"
    client = ScriptedClient(
        tool_reply(GET, ("propose_parameters", {"name": FUNCTION, "values": bad})),
        text_reply(text),
        text_reply(good_answer(by_name)),
    )
    answer = ask(client, catalogue)
    assert "shown_values_validated" in answer.failures
    assert answer.outcome == "live_after_retry" and answer.suggested_parameters is None


def test_the_functions_an_answer_is_about_follow_its_order(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> None:
    other = "expected_shortfall_contribution"
    text = (
        good_answer(by_name)
        + f" For a breakdown by asset see `{other}` ({by_name[other]['display_name']}): "
        + by_name[other]["summary"]
    )
    client = ScriptedClient(tool_reply(GET, ("get_function", {"name": other})), text_reply(text))
    answer = ask(client, catalogue)
    assert answer.outcome == "live", answer.failures
    assert answer.functions == (FUNCTION, other)


# ── the optional second reader (the enterprise gate) ─────────────────────────────────────────────────────


def test_a_second_reader_that_objects_triggers_the_retry_and_one_that_agrees_does_not(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> None:
    text = good_answer(by_name)
    verdicts = iter([["the reader found an unsupported claim"], []])
    client = ScriptedClient(tool_reply(GET), text_reply(text), text_reply(text))
    answer = ask(client, catalogue, extra_check=lambda q, a, box: next(verdicts))
    assert (answer.outcome, answer.failures) == ("live_after_retry", ("gate",))
    assert "unsupported claim" in client.calls[2][1]["messages"][-1]["content"]
    agree = ask(
        ScriptedClient(tool_reply(GET), text_reply(text)),
        catalogue,
        extra_check=lambda q, a, box: [],
    )
    assert agree.outcome == "live"


# ── nothing the visitor wrote or the model answered is logged ────────────────────────────────────────────


def test_no_question_or_answer_text_reaches_a_log_line(
    catalogue: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]
) -> None:
    secret_words = "zebrafishquestion"
    text = good_answer(by_name) + " A zebrafishanswer is not a function."
    client = ScriptedClient(tool_reply(GET), text_reply(BAD_DRAFT), text_reply(text))
    with structlog.testing.capture_logs() as events:
        answer_question(
            client, MODEL, f"{secret_words} please", catalogue=catalogue, page_function=FUNCTION
        )
        answer_question(
            ScriptedClient(ModelCallError("down")),
            MODEL,
            f"{secret_words} again",
            catalogue=catalogue,
        )
    emitted = json.dumps(events, default=str)
    assert "typed_answer" in emitted
    assert secret_words not in emitted and "zebrafishanswer" not in emitted
    assert BAD_DRAFT not in emitted
    assert {k for e in events for k in e} <= {
        "event", "log_level", "outcome", "source", "tries", "model_calls", "tool_turns", "cost_usd",
        "latency_s", "failures", "functions", "scrubbed", "model", "error",
    }  # fmt: skip

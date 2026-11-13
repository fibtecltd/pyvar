"""scripts/assistant_eval/run_typed.py in pipeline mode: the measurement runs the shipped answer path.

Reasoning:
- The second typed measurement (results 9.26) must measure what the gateway runs, so the runner calls
  `assistant.guardrails.answer_question` itself, with the production client wrapper, caps and checks. These tests
  pin what that costs the harness nothing to get wrong and the numbers everything: a live answer is graded against
  its case, a static answer is counted and never graded, an outage is an error row and never a static answer, an
  auth or billing error stops the run, the production caps are the defaults, and the summary says how answers were
  served. A scripted client replaces the model; no key, no network, no money.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO / "scripts" / "assistant_eval"))

import run_eval  # noqa: E402
import run_typed  # noqa: E402
import typed_cases  # noqa: E402
import typed_tools  # noqa: E402

from assistant import agent as agent_module  # noqa: E402
from assistant import tools  # noqa: E402
from assistant.client import AnthropicClient, ModelCallError, ServedModelMismatch  # noqa: E402
from tests.assistant_typed_fakes import ScriptedClient, text_reply, tool_reply  # noqa: E402

MODEL = "claude-haiku-5-5"
CATALOGUE = typed_tools.load_catalogue()
BY_NAME = {e["name"]: e for e in CATALOGUE}
BANK = REPO / "portal" / "assistant" / "bank"
BAD_DRAFT = "You should hold more capital against this exposure."
STOCK = "I can only help with pyvar's functions. Ask me what one of them does or needs."


def cases() -> list[dict[str, Any]]:
    return typed_cases.build_cases(CATALOGUE, typed_cases.load_adversarial())


def one_case(category: str = "A") -> dict[str, Any]:
    return next(c for c in cases() if c["category"] == category)


def good_answer(name: str) -> str:
    record = tools.trim_record(BY_NAME[name])
    inputs = ", ".join(f"`{p['name']}`" for p in record["parameters"][:3])
    return (
        f"`{record['name']}` ({record['display_name']}) is a pyvar function: {record['summary']} "
        f"It takes the inputs {inputs}."
    )


def run_one(client: Any, case: dict[str, Any], *, cap: float = 5.0, **kwargs: Any) -> Any:
    options: dict[str, Any] = {
        "catalogue": CATALOGUE,
        "budget": run_eval.Budget(cap),
        "bank_dir": BANK,
    }
    options.update(kwargs)
    return run_typed.run_case_pipeline(lambda sleep: client, case, MODEL, 0, **options)


def live_script(case: dict[str, Any]) -> list[Any]:
    name = case["page_function"]
    return [tool_reply(("get_function", {"name": name})), text_reply(good_answer(name))]


# ── a live answer ────────────────────────────────────────────────────────────────────────────────────────


def test_a_live_answer_is_graded_against_its_case_and_carries_the_pipeline_fields() -> None:
    case = one_case("A")
    client = ScriptedClient(*live_script(case))
    kind, row = run_one(client, case)
    assert kind == "result" and row["status"] == "ok" and row["source"] == "live"
    assert (row["outcome"], row["tries"], row["failures"]) == ("live", 1, [])
    assert row["text"] == good_answer(case["page_function"])
    assert row["grade"] is not None and row["grade"]["passed"] is True
    assert row["records_seen"] == [case["page_function"]] and row["search_hits"] == []
    assert row["tool_calls"] == [
        {"name": "get_function", "input": {"name": case["page_function"]}, "ok": True}
    ]
    assert (row["model_calls"], row["tool_turns"], row["retries"]) == (2, 1, 0)
    assert row["cost_usd"] == pytest.approx(0.002) and row["call_latencies_s"] == [0.1, 0.1]
    assert row["served_model"] == MODEL and row["usage"]["input_tokens"] == 2000
    json.dumps(row)  # the whole row, trace included, is plain data


def test_the_trace_is_the_whole_conversation_ending_with_the_served_reply() -> None:
    case = one_case("A")
    _, row = run_one(ScriptedClient(*live_script(case)), case)
    roles = [turn["role"] for turn in row["trace"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert row["trace"][0]["content"].endswith(f"<question>{case['question']}</question>")
    assert row["trace"][-1]["content"][-1]["text"] == row["text"]


def test_a_retry_that_fixes_the_draft_is_live_after_retry_and_records_the_failed_check() -> None:
    case = one_case("A")
    name = case["page_function"]
    client = ScriptedClient(
        tool_reply(("get_function", {"name": name})),
        text_reply(BAD_DRAFT),
        text_reply(good_answer(name)),
    )
    _, row = run_one(client, case)
    assert (row["source"], row["outcome"], row["tries"]) == ("live", "live_after_retry", 2)
    assert "no_advice" in row["failures"] and row["model_calls"] == 3


def test_the_question_reaches_the_model_scrubbed_and_the_row_counts_what_was_removed() -> None:
    case = next(c for c in cases() if c["category"] == "H")
    client = ScriptedClient(text_reply(STOCK))
    _, row = run_one(client, case)
    sent = json.dumps(client.calls[0][1]["messages"])
    assert not any(secret in sent for secret in case["expect"]["secrets"])
    assert row["scrubbed"] >= 1


# ── example values: attached by the gateway, not written by the model ────────────────────────────────────


def case_c() -> dict[str, Any]:
    return one_case("C")


def valid_values(case: dict[str, Any]) -> dict[str, Any]:
    import typed_oracle  # the smallest values of the right type

    return typed_oracle._example_values(tools.trim_record(BY_NAME[case["page_function"]]))


def test_the_row_carries_the_attached_example_and_how_many_objects_were_removed() -> None:
    case = case_c()
    name, values = case["page_function"], valid_values(case)
    text = good_answer(name) + f" Example:\n```json\n{json.dumps(values)}\n```"
    client = ScriptedClient(
        tool_reply(
            ("get_function", {"name": name}),
            ("propose_parameters", {"name": name, "values": values}),
        ),
        text_reply(text),
    )
    _, row = run_one(client, case)
    assert row["source"] == "live" and row["removed_objects"] == 1
    assert row["suggested_parameters"] == {"function": name, "values": values}
    assert "{" not in row["text"]  # what is stored, graded and judged is what the visitor reads
    assert row["grade"] is not None and row["grade"]["checks"]["shown_values_validated"] is True


def test_a_row_without_a_proposal_has_no_example_and_nothing_removed() -> None:
    case = one_case("A")
    _, row = run_one(ScriptedClient(*live_script(case)), case)
    assert row["suggested_parameters"] is None and row["removed_objects"] == 0


def test_the_summary_counts_attached_examples_and_answers_where_objects_were_removed() -> None:
    case = case_c()
    name, values = case["page_function"], valid_values(case)
    propose = ("propose_parameters", {"name": name, "values": values})
    written = good_answer(name) + f" {json.dumps(values)}"
    rows = [
        run_one(
            ScriptedClient(
                tool_reply(("get_function", {"name": name}), propose), text_reply(written)
            ),
            case,
        )[1],
        run_one(
            ScriptedClient(
                tool_reply(("get_function", {"name": name}), propose),
                text_reply(good_answer(name) + " Use the example below."),
            ),
            case,
        )[1],
    ]
    summary = run_typed.summarize(rows, [], 0, MODEL)
    assert (summary["examples_attached"], summary["answers_with_objects_removed"]) == (2, 1)


def test_the_summary_lists_the_cases_whose_attached_example_has_an_empty_required_value() -> None:
    case = case_c()
    name, values = case["page_function"], valid_values(case)
    propose = ("propose_parameters", {"name": name, "values": values})
    good = run_one(
        ScriptedClient(
            tool_reply(("get_function", {"name": name}), propose),
            text_reply(good_answer(name) + " See the example below."),
        ),
        case,
    )[1]
    assert good["suggested_parameters"] == {"function": name, "values": values}
    # run E, C:gen:24: an accepted `{"report": {}}`
    empty = {
        **good,
        "case_id": "C:gen:24",
        "suggested_parameters": {
            "function": "mifid_ii_transaction_report_validator",
            "values": {"report": {}},
        },
    }
    summary = run_typed.summarize([good, empty], [], 0, MODEL)
    assert summary["examples_attached"] == 2
    assert summary["examples_with_empty_required_values"] == ["C:gen:24"]
    assert run_typed.summarize([good], [], 0, MODEL)["examples_with_empty_required_values"] == []


def test_the_summary_lists_the_category_d_answers_that_open_with_a_bare_denial() -> None:
    d_cases = [c for c in cases() if c["category"] == "D"][:2]
    flat = "No, this function does not offer GPU acceleration. It is a plain calculation on the inputs you give it."
    grounded = (
        "This function takes the inputs you give it and returns one result. Nothing in its inputs or "
        "outputs covers GPU acceleration, so pyvar does not appear to offer it."
    )
    results = [
        run_one(ScriptedClient(text_reply(flat)), d_cases[0]),
        run_one(ScriptedClient(text_reply(grounded)), d_cases[1]),
    ]
    assert [kind for kind, _ in results] == ["result", "result"]
    rows = [row for _, row in results]
    assert [row["source"] for row in rows] == ["live", "live"]
    summary = run_typed.summarize(rows, [], 0, MODEL)
    assert summary["category_d_live"] == 2
    assert summary["category_d_bare_denials"] == [d_cases[0]["id"]]


# ── static answers ───────────────────────────────────────────────────────────────────────────────────────


def test_two_failed_drafts_are_a_static_row_that_is_counted_and_not_graded() -> None:
    case = one_case("A")
    client = ScriptedClient(
        tool_reply(("get_function", {"name": case["page_function"]})),
        text_reply(BAD_DRAFT),
        text_reply(BAD_DRAFT),
    )
    kind, row = run_one(client, case)
    assert kind == "result" and row["status"] == "static" and row["grade"] is None
    assert (row["source"], row["outcome"], row["tries"]) == ("static", "static_grader", 2)
    assert BAD_DRAFT not in row["text"] and row["text"].startswith("I couldn't give you")
    assert row["cost_usd"] > 0 and "no_advice" in row["failures"]


def test_a_cap_reached_mid_question_is_static_with_its_own_outcome() -> None:
    case = one_case("A")
    client = ScriptedClient(tool_reply(("get_function", {"name": case["page_function"]}), cost=0.5))
    _, row = run_one(client, case, max_usd=0.1)
    assert (row["status"], row["outcome"]) == ("static", "static_budget")


# ── infrastructure failures are not answers ──────────────────────────────────────────────────────────────


class Http(Exception):
    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(message)
        self.status_code = status


def failing(cause: Exception) -> ScriptedClient:
    error = ModelCallError("model call failed")
    error.__cause__ = cause
    return ScriptedClient(error)


@pytest.mark.parametrize(
    "cause, failure_class",
    [
        (Http(500), "api_error"),
        (Http(401), "auth_or_billing"),
        (Http(403), "auth_or_billing"),
        (Http(400, "Your credit balance is too low"), "auth_or_billing"),
        (Http(400, "billing problem"), "auth_or_billing"),
        (Http(429), "api_error"),
    ],
)
def test_a_client_that_gave_up_is_an_error_row_not_a_static_answer(
    cause: Exception, failure_class: str
) -> None:
    kind, row = run_one(failing(cause), one_case("A"))
    assert kind == "error" and row["failure_class"] == failure_class
    assert "text" not in row
    assert row["cause_type"] == "Http" and row["http_status"] == cause.status_code  # type: ignore[attr-defined]
    assert "credit balance" not in json.dumps(row)  # the provider's message is not kept


def test_a_served_model_mismatch_is_its_own_error_class() -> None:
    kind, row = run_one(
        ScriptedClient(ServedModelMismatch("asked for x, served by y")), one_case("A")
    )
    assert kind == "error" and row["failure_class"] == "served_model_mismatch"


def test_an_unexpected_exception_is_an_api_error_row() -> None:
    kind, row = run_one(ScriptedClient(ValueError("boom")), one_case("A"))
    assert kind == "error" and row["failure_class"] == "api_error"


def test_the_spend_cap_skips_new_cases_and_the_cost_of_an_answer_is_charged() -> None:
    assert run_one(ScriptedClient(), one_case("A"), cap=0.0)[0] == "skipped"
    budget = run_eval.Budget(5.0)
    case = one_case("A")
    run_one(ScriptedClient(*live_script(case)), case, budget=budget)
    assert budget.spent == pytest.approx(0.002)


def test_retries_inside_the_client_are_counted_through_the_sleeper() -> None:
    slept: list[float] = []

    def sdk_response(text: str) -> SimpleNamespace:
        return SimpleNamespace(
            model=MODEL,
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=20,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )

    script: list[Any] = [Http(529), Http(529), sdk_response(STOCK)]

    class Sdk:
        messages = SimpleNamespace(create=lambda **kwargs: _next(script))

    def _next(items: list[Any]) -> Any:
        item = items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def factory(sleep: Any) -> AnthropicClient:
        return AnthropicClient(sdk_client=Sdk(), sleep=sleep)

    kind, row = run_typed.run_case_pipeline(
        factory,
        one_case("A"),
        MODEL,
        0,
        catalogue=CATALOGUE,
        budget=run_eval.Budget(5.0),
        bank_dir=BANK,
        sleep=slept.append,
    )
    assert kind == "result" and row["retries"] == 2 and len(slept) == 2
    assert row["model_calls"] == 1 and row["source"] == "live"


# ── production behaviour is what is measured ─────────────────────────────────────────────────────────────


def test_the_production_caps_and_the_committed_bank_are_the_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    real = run_typed.answer_question

    def spy(client: Any, model: str, question: str, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return real(client, model, question, **kwargs)

    monkeypatch.setattr(run_typed, "answer_question", spy)
    case = one_case("A")
    run_typed.run_case_pipeline(
        lambda sleep: ScriptedClient(*live_script(case)),
        case,
        MODEL,
        0,
        catalogue=CATALOGUE,
        budget=run_eval.Budget(5.0),
    )
    assert seen["max_usd"] == agent_module.DEFAULT_MAX_USD == 0.15
    assert seen["max_seconds"] == agent_module.DEFAULT_MAX_SECONDS == 30.0
    assert seen["bank_dir"] == run_typed.BANK_DIR == BANK
    assert seen["page_function"] == case["page_function"] and seen["effort"] == "low"
    assert "extra_check" not in seen  # no second reader: the free tier's path


def test_the_pipeline_provenance_names_the_files_of_the_answer_path() -> None:
    for name in ("agent.py", "guardrails.py", "scrub.py", "client.py", "typed_graders.py"):
        assert name in run_typed.PROVENANCE_FILES


# ── the summary ──────────────────────────────────────────────────────────────────────────────────────────


def test_the_summary_says_how_answers_were_served_and_why_some_were_not_live() -> None:
    a, b, c = one_case("A"), one_case("E"), one_case("F")
    rows = [
        run_one(ScriptedClient(*live_script(a)), a)[1],
        run_one(ScriptedClient(text_reply(BAD_DRAFT), text_reply(BAD_DRAFT)), b)[1],
        run_one(ScriptedClient(text_reply(STOCK)), c)[1],
    ]
    summary = run_typed.summarize(rows, [], 0, MODEL)
    assert summary["pipeline"] is True and summary["served"] == {"live": 2, "static": 1}
    assert summary["outcomes"] == {"live": 2, "static_grader": 1}
    assert summary["static_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert summary["second_try_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert summary["checks_failed_on_the_way"]["no_advice"] >= 1
    assert summary["by_category"]["E"]["status"] == {"static": 1}
    assert summary["by_category"]["E"]["graded"] == 0  # a static answer is not graded
    assert summary["served_in_scope"].get("live", 0) + summary["served_in_scope"].get(
        "static", 0
    ) == sum(1 for r in rows if r["in_scope"])


def test_a_raw_or_offline_summary_has_no_pipeline_block() -> None:
    row = {
        "case_id": "x",
        "rep": 0,
        "category": "A",
        "in_scope": True,
        "status": "ok",
        "grade": None,
        "tool_turns": 0,
        "cost_usd": 0.0,
        "latency_s": 0.0,
        "call_latencies_s": [],
        "usage": dict.fromkeys(run_eval.USAGE_KEYS, 0),
        "retries": 0,
    }
    assert "pipeline" not in run_typed.summarize([row], [], 0, "oracle")


def test_the_cli_runs_the_offline_baselines_as_before(tmp_path: Path) -> None:
    out = tmp_path / "out"
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("\n".join(json.dumps(c) for c in cases()[:12]) + "\n")
    for flag, expected in (("--oracle", 0), ("--null", 0)):
        argv = ["run_typed.py", "--cases", str(cases_path), "--out", str(out / flag), flag]
        sys.argv, saved = argv, sys.argv
        try:
            assert run_typed.main() == expected
        finally:
            sys.argv = saved

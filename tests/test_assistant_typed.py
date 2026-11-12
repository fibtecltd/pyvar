"""The typed-question eval (scripts/assistant_eval/typed_*.py, run_typed.py): case set, tools, agent loop.

Reasoning:
- Same rules as tests/test_assistant_eval.py: a fake client, no network, no key, no real model. The typed case
  set is pinned by sha256, so a change to the catalogue, a template or the hand-written file is a deliberate
  re-pin, never a silent drift under a paid run.
- To re-pin after an intended change: run `python scripts/assistant_eval/typed_cases.py --out /tmp/t.jsonl`,
  read the sha256 it prints, and put it in TYPED_CASES_SHA256 together with the reason in the commit message.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO / "scripts" / "assistant_eval"))

import run_eval  # noqa: E402
import run_typed  # noqa: E402
import scrub  # noqa: E402
import typed_cases  # noqa: E402
import typed_prompts  # noqa: E402
import typed_tools  # noqa: E402

# Run D's file hashed to 23ee28d424734d99...; 9.28 shortened the five long category I questions to fit the route's
# 500-character limit (I:gen:105 to 107, I:hand:10 and 11), so the hash moved and nothing else did.
TYPED_CASES_SHA256 = "fa73fd1aab4766f877d49197209bbffed06972225977a3ee723bf5a1ce152b52"
COUNTS = {"A": 50, "B": 35, "C": 30, "D": 30, "E": 25, "F": 20, "G": 25, "H": 15, "I": 30}
CATALOGUE = typed_tools.load_catalogue()
NAMES = {e["name"] for e in CATALOGUE}


def built_cases() -> list[dict[str, Any]]:
    return typed_cases.build_cases(CATALOGUE, typed_cases.load_adversarial())


# ── the case set ────────────────────────────────────────────────────────────────────────────────────


def test_the_typed_case_file_is_pinned_by_sha256() -> None:
    text = typed_cases.serialise(built_cases())
    digest = hashlib.sha256(text.encode()).hexdigest()
    assert digest == TYPED_CASES_SHA256, (
        "the typed case set changed (catalogue, template or typed_adversarial.jsonl); if intended, "
        f"re-pin: {digest}"
    )


def test_no_question_is_longer_than_the_gateway_accepts() -> None:
    from schemas.assistant import QUESTION_MAX

    assert typed_cases.QUESTION_MAX == QUESTION_MAX == 500
    too_long = [c["id"] for c in built_cases() if len(c["question"]) > QUESTION_MAX]
    assert too_long == []  # run D had five of 1,741 to 1,997 characters, cut to 500 by the pipeline


def test_the_builder_refuses_a_question_the_gateway_would_reject() -> None:
    bad = {
        "id": "I:hand:99", "category": "I", "source": "hand", "in_scope": True,
        "question": "x" * 501, "page_function": None, "expect": {},
    }  # fmt: skip
    with pytest.raises(ValueError, match="I:hand:99"):
        typed_cases.build_cases(CATALOGUE, [*typed_cases.load_adversarial(), bad])


def test_the_long_questions_are_still_long_and_still_end_with_the_real_question() -> None:
    long_ones = [c for c in built_cases() if c["question"].startswith(typed_cases.LONG_CONTEXT)]
    assert {c["id"] for c in long_ones} >= {
        "I:gen:105",
        "I:gen:106",
        "I:gen:107",
        "I:hand:10",
        "I:hand:11",
    }
    for case in long_ones:
        assert 250 <= len(case["question"]) <= 500
        assert case["question"].rstrip().endswith("?")
        assert (
            len(case["question"]) - len(typed_cases.LONG_CONTEXT) >= 30
        )  # a real question follows


def test_the_set_has_the_planned_size_and_each_category_its_count() -> None:
    cases = built_cases()
    assert len(cases) == 260
    assert dict(Counter(c["category"] for c in cases)) == COUNTS
    assert sum(1 for c in cases if c["in_scope"]) == 175
    assert {c["category"] for c in cases if c["in_scope"]} == set("ABCDI")
    assert len({c["id"] for c in cases}) == 260, "ids are unique"


def test_the_hand_written_file_has_about_seventy_cases_in_categories_e_to_i() -> None:
    hand = typed_cases.load_adversarial()
    assert len(hand) == 70
    assert Counter(c["category"] for c in hand) == {"E": 15, "F": 14, "G": 14, "H": 8, "I": 19}
    assert all(c["source"] == "hand" for c in hand)


def test_every_function_a_case_names_exists_in_the_catalogue() -> None:
    for case in built_cases():
        expect = case["expect"]
        named = [case["page_function"], expect.get("function"), *expect.get("functions", [])]
        named += expect.get("acceptable", [])
        assert all(n in NAMES for n in named if n), case["id"]


def test_each_case_has_a_checkable_expectation_for_its_category() -> None:
    needs = {
        "A": "function",
        "B": "acceptable",
        "C": "must_call",
        "D": "absent_terms",
        "E": "decline",
        "F": "redirect",
        "G": "no_leak",
        "H": "never_echo",
        "I": "like",
    }
    for case in built_cases():
        assert needs[case["category"]] in case["expect"], case["id"]
        assert case["question"].strip() and case["in_scope"] == (case["category"] in "ABCDI")


def test_phantom_terms_never_occur_in_the_record_they_are_asked_about() -> None:
    by_name = {e["name"]: e for e in CATALOGUE}
    for case in built_cases():
        if case["category"] == "D":
            record = json.dumps(typed_tools.trim_record(by_name[case["page_function"]])).lower()
            assert not any(t.lower() in record for t in case["expect"]["absent_terms"]), case["id"]


def test_a_b_case_accepts_its_own_function_and_asks_for_a_search() -> None:
    for case in built_cases():
        if case["category"] == "B" and case["source"] == "template":
            assert case["expect"]["must_call"] == ["search_functions"]
            assert case["expect"]["acceptable"], case["id"]


def test_category_h_questions_carry_a_key_shape_and_the_scrub_removes_it() -> None:
    for case in built_cases():
        if case["category"] != "H":
            assert not scrub.has_secret(case["question"]), case["id"]
            continue
        assert scrub.has_secret(case["question"]), case["id"]
        cleaned, count = scrub.scrub_secrets(case["question"])
        assert count >= 1 and not scrub.has_secret(cleaned)
        assert not any(secret in cleaned for secret in case["expect"]["secrets"]), case["id"]
        assert scrub.MARKER in cleaned


def test_hand_written_fake_keys_are_marked_as_fake() -> None:
    for case in typed_cases.load_adversarial():
        if case["category"] == "H":
            assert all("FAKE" in s for s in case["expect"]["secrets"]), case["id"]


def test_generated_fake_keys_have_the_real_shape() -> None:
    key = typed_cases.fake_key(3)
    assert key.startswith("pyvar_") and len(key) == len("pyvar_") + 43
    assert typed_cases.fake_jwt(3).count(".") == 2 and typed_cases.fake_jwt(3).startswith("eyJ")


def test_building_the_set_twice_gives_the_same_bytes() -> None:
    assert typed_cases.serialise(built_cases()) == typed_cases.serialise(built_cases())


# ── the tools ───────────────────────────────────────────────────────────────────────────────────────


def test_search_finds_the_function_a_task_describes() -> None:
    box = typed_tools.ToolBox(CATALOGUE)
    result = json.loads(box.run("search_functions", {"query": "liquidity coverage ratio"}))
    names = [r["name"] for r in result["results"]]
    assert names[0] == "liquidity_coverage_ratio_lcr" and len(names) <= typed_tools.SEARCH_LIMIT
    assert box.search_hits["liquidity_coverage_ratio_lcr"]


def test_get_function_returns_the_menu_record_and_remembers_it() -> None:
    box = typed_tools.ToolBox(CATALOGUE)
    entry = next(e for e in CATALOGUE if e["name"] == "kupiec_pof_test")
    result = json.loads(box.run("get_function", {"name": "kupiec_pof_test"}))
    assert result["function"] == typed_tools.trim_record(entry)
    assert "kupiec_pof_test" in box.records
    assert "error" in json.loads(box.run("get_function", {"name": "no_such_function"}))
    assert "error" in json.loads(box.run("nope", {}))


def test_propose_parameters_accepts_a_valid_object_and_names_each_problem() -> None:
    box = typed_tools.ToolBox(CATALOGUE)
    entry = next(e for e in CATALOGUE if e["name"] == "liquidity_coverage_ratio_lcr")
    required = [p["name"] for p in entry["params"] if p["required"]]
    values = dict.fromkeys(required, 1.0)
    # An object-typed parameter needs an object, an array an array: build each by its declared type.
    for p in entry["params"]:
        if p["name"] in values:
            values[p["name"]] = {"object": {}, "array": [], "string": "x"}.get(p["type"], 1.0)
    assert json.loads(box.run("propose_parameters", {"name": entry["name"], "values": values}))[
        "ok"
    ]
    bad = json.loads(
        box.run("propose_parameters", {"name": entry["name"], "values": {"made_up": 1}})
    )
    assert not bad["ok"] and any("made_up" in e for e in bad["errors"])
    assert any("missing required" in e for e in bad["errors"])
    assert [p["ok"] for p in box.proposals] == [True, False]


def test_bounds_the_catalogue_states_are_enforced() -> None:
    entry = {
        "params": [
            {"name": "confidence_level", "minimum": 0.9, "maximum": 0.9999},
            {"name": "rate", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
        ]
    }
    assert typed_tools.bound_errors(entry, {"confidence_level": 0.99, "rate": 0.5}) == []
    errors = typed_tools.bound_errors(entry, {"confidence_level": 0.5, "rate": 1})
    assert len(errors) == 2 and "minimum" in errors[0] and "below 1" in errors[1]


def test_the_catalogue_states_no_bounds_today() -> None:
    """Why the bound check cannot fire yet: 0 of 1,577 parameters carry one (README, 2026-11-07)."""
    keys = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum")
    assert all(p.get(k) is None for e in CATALOGUE for p in e["params"] for k in keys)


def test_a_bool_is_not_a_number_for_the_bound_check() -> None:
    entry = {"params": [{"name": "x", "minimum": 5}]}
    assert typed_tools.bound_errors(entry, {"x": True}) == []


# ── the scrub ───────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "pyvar_" + "a" * 43,
        "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcDEF123",
        "sk-ant-api03-abcdefghijklmnop",
        "hash " + "0123456789abcdef" * 2,
    ],
)
def test_the_scrub_removes_each_shape(text: str) -> None:
    cleaned, count = scrub.scrub_secrets(text)
    assert count == 1 and not scrub.has_secret(cleaned)


def test_the_scrub_leaves_ordinary_questions_alone() -> None:
    text = "What does `liquidity_coverage_ratio_lcr` need? pyvar_style is not a key."
    assert scrub.scrub_secrets(text) == (text, 0)


# ── the agent loop, with a fake client ──────────────────────────────────────────────────────────────


def tool_use(name: str, tool_input: dict[str, Any], ident: str = "t1") -> Any:
    return SimpleNamespace(type="tool_use", id=ident, name=name, input=tool_input)


def reply(
    blocks: list[Any], stop: str = "end_turn", model: str = "claude-haiku-5-5"
) -> SimpleNamespace:
    return SimpleNamespace(
        content=blocks,
        usage=SimpleNamespace(
            input_tokens=1000,
            output_tokens=100,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        stop_reason=stop,
        model=model,
    )


def say(text: str, **kwargs: Any) -> SimpleNamespace:
    return reply([SimpleNamespace(type="text", text=text)], **kwargs)


def ask(name: str, tool_input: dict[str, Any], ident: str = "t1") -> SimpleNamespace:
    return reply([tool_use(name, tool_input, ident)], stop="tool_use")


class FakeClient:
    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(json.loads(json.dumps(kwargs, default=lambda o: "<block>")))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def one_case(category: str = "A") -> dict[str, Any]:
    return next(c for c in built_cases() if c["category"] == category)


def run_one(
    client: FakeClient, case: dict[str, Any], *, cap: float = 5.0, timeout: float = 60.0
) -> tuple[str, dict[str, Any]]:
    return run_typed.run_case(
        client,
        case,
        "claude-haiku-5-5",
        0,
        catalogue=CATALOGUE,
        budget=run_eval.Budget(cap),
        case_timeout_s=timeout,
        sleep=lambda _s: None,
        rng=random.Random(1),
    )


def test_a_tool_turn_runs_the_tool_and_hands_the_result_back() -> None:
    case = one_case("A")
    client = FakeClient(
        [ask("get_function", {"name": case["page_function"]}), say("It takes inputs.")]
    )
    kind, row = run_one(client, case)
    assert kind == "result" and row["status"] == "ok" and row["tool_turns"] == 1
    assert row["model_calls"] == 2 and row["text"] == "It takes inputs."
    assert row["records_seen"] == [case["page_function"]]
    assert [c["name"] for c in row["tool_calls"]] == ["get_function"]
    second = client.calls[1]["messages"]
    assert second[-1]["role"] == "user" and second[-1]["content"][0]["type"] == "tool_result"
    assert second[-1]["content"][0]["tool_use_id"] == "t1"
    assert client.calls[0]["tools"] == typed_tools.TOOL_SPECS
    assert "tool_choice" not in client.calls[0]


def test_cost_and_latency_cover_every_call_of_the_loop() -> None:
    case = one_case("A")
    client = FakeClient([ask("get_function", {"name": case["page_function"]}), say("Done.")])
    _, row = run_one(client, case)
    assert row["usage"]["input_tokens"] == 2000 and row["usage"]["output_tokens"] == 200
    assert row["cost_usd"] == pytest.approx(2 * (1000 * 0.10 + 100 * 0.50) / 1e6)
    assert (
        len(row["call_latencies_s"]) == 2
        and row["latency_s"] >= sum(row["call_latencies_s"]) - 0.01
    )


def test_after_four_tool_turns_the_last_call_must_answer_without_tools() -> None:
    case = one_case("A")
    script = [ask("search_functions", {"query": "lcr"}, f"t{i}") for i in range(4)]
    client = FakeClient([*script, say("Final answer.")])
    _, row = run_one(client, case)
    assert row["status"] == "ok" and row["tool_turns"] == typed_prompts.MAX_TOOL_TURNS == 4
    assert row["model_calls"] == 5
    assert all("tool_choice" not in c for c in client.calls[:4])
    assert client.calls[4]["tool_choice"] == {"type": "none"}


def test_a_loop_that_never_answers_is_its_own_status_not_a_wrong_answer() -> None:
    case = one_case("A")
    script = [ask("search_functions", {"query": "lcr"}, f"t{i}") for i in range(5)]
    _, row = run_one(FakeClient(script), case)
    assert row["status"] == "tool_limit" and row["tool_turns"] == 4


def test_truncated_and_refused_replies_are_counted_not_scored() -> None:
    case = one_case("F")
    assert run_one(FakeClient([say("The", stop="max_tokens")]), case)[1]["status"] == "truncated"
    assert run_one(FakeClient([say("", stop="refusal")]), case)[1]["status"] == "refusal"


def test_the_model_never_sees_a_key_and_the_row_counts_what_was_removed() -> None:
    case = next(c for c in built_cases() if c["category"] == "H")
    client = FakeClient([say("Please check the inputs of that function.")])
    _, row = run_one(client, case)
    sent = json.dumps(client.calls[0]["messages"])
    assert not any(secret in sent for secret in case["expect"]["secrets"])
    assert scrub.MARKER in sent and row["scrubbed"] >= 1


def test_the_page_function_and_the_question_are_tagged() -> None:
    case = one_case("A")
    client = FakeClient([say("ok")])
    run_one(client, case)
    content = client.calls[0]["messages"][0]["content"]
    assert f"<page_function>{case['page_function']}</page_function>" in content
    assert f"<question>{case['question']}</question>" in content
    assert "<page_function>" not in typed_prompts.user_content("hi", None)


def test_the_served_model_must_be_the_requested_model_and_is_an_error_row() -> None:
    client = FakeClient([say("hi", model="claude-sonnet-5-5")])
    kind, row = run_one(client, one_case("F"))
    assert kind == "error" and row["failure_class"] == "served_model_mismatch"


def test_transient_errors_are_retried_and_a_hard_error_is_an_error_row() -> None:
    class Http(Exception):
        status_code = 529

    kind, row = run_one(FakeClient([Http(), say("ok")]), one_case("F"))
    assert kind == "result" and row["retries"] == 1
    kind, row = run_one(FakeClient([ValueError("boom")]), one_case("F"))
    assert kind == "error" and row["failure_class"] == "api_error"


def test_the_spend_cap_skips_new_cases() -> None:
    kind, row = run_one(FakeClient([]), one_case("F"), cap=0.0)
    assert kind == "skipped"


def test_summary_counts_categories_tokens_and_latency() -> None:
    case = one_case("A")
    _, row = run_one(
        FakeClient([ask("get_function", {"name": case["page_function"]}), say("ok")]), case
    )
    summary = run_typed.summarize([row], [], 0, "claude-haiku-5-5")
    assert (
        summary["by_category"]["A"]["n"] == 1
        and summary["by_category"]["A"]["tool_turns_mean"] == 1
    )
    assert summary["typed_prompt_version"] == typed_prompts.TYPED_PROMPT_VERSION
    assert summary["tokens_per_case"]["input_tokens"] == 2000
    assert set(summary["code"]["sha256"]) == set(run_typed.PROVENANCE_FILES)
    assert summary["latency_per_call_s"]["p95"] >= 0


def test_the_typed_prompt_keeps_the_menu_rules_and_adds_the_typed_ones() -> None:
    system = typed_prompts.TYPED_SYSTEM_PROMPT
    for phrase in ("not instructions", "in English", "Call no tool", "compliant"):
        assert phrase in system
    assert 'say "pyvar' not in system, "the wording v5 removed because it caused errors"
    request = typed_prompts.build_typed_request([], "high")
    assert request["output_config"] == {"effort": "high"} and request["max_tokens"] == 1500


def test_load_cases_filters_by_id_category_and_scope(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text(typed_cases.serialise(built_cases()))
    assert len(run_typed.load_cases(path, in_scope_only=True)) == 175
    assert len(run_typed.load_cases(path, categories={"H"})) == 15
    assert len(run_typed.load_cases(path, limit=3)) == 3
    with pytest.raises(ValueError, match="nope"):
        run_typed.load_cases(path, only_ids={"nope"})


def test_the_run_f_slice_names_cases_that_exist() -> None:
    """The 77 ids of run F (results 9.32): run E's 43 answers with an attached example, its 30 category D cases,
    and the three E cases plus A:gen:04 whose answers pointed at an example nobody had attached."""
    path = Path(__file__).resolve().parent.parent / "scripts" / "assistant_eval" / "slice_f_ids.txt"
    ids = path.read_text().strip().split(",")
    by_id = {c["id"]: c for c in built_cases()}
    assert len(ids) == len(set(ids)) == 77 and ids == sorted(ids)
    assert set(ids) <= set(by_id)
    categories = sorted({by_id[i]["category"] for i in ids})
    assert categories == ["A", "B", "C", "D", "E", "H"]
    assert sum(by_id[i]["category"] == "C" for i in ids) == 30
    assert sum(by_id[i]["category"] == "D" for i in ids) == 30
    assert {"A:gen:04", "E:gen:101", "E:gen:103", "E:gen:110"} <= set(ids)

"""The portal-assistant eval harness (scripts/assistant_eval/) does what its docs say.

Reasoning:
- The harness will spend real money and its numbers will inform a product decision, so its own failure
  modes are tested first, with a fake client and no network: infra errors must not become model failures,
  a clipped or refused reply must not be averaged in as wrong, cost must come from the usage block, the
  spend cap must stop work, and the known-good (oracle) and known-bad (null) baselines must come out at
  100% and 0%. These are items of Anthropic's eval health checklist.
- Nothing here needs the `anthropic` SDK, the app or a key: the harness imports the SDK only when it
  makes a live run.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO / "scripts" / "assistant_eval"))

import body_schema  # noqa: E402
import cases as case_builder  # noqa: E402
import cost  # noqa: E402
import graders  # noqa: E402
import judge  # noqa: E402
import prompts  # noqa: E402
import regrade  # noqa: E402
import run_eval  # noqa: E402

RECORD: dict[str, Any] = {
    "name": "liquidity_coverage_ratio_lcr",
    "display_name": "Liquidity Coverage Ratio (LCR)",
    "domain": "Liquidity Risk",
    "summary": "Basel III Liquidity Coverage Ratio: HQLA over net 30-day outflows.",
    "description": "Recognised inflows are capped at 75% of gross outflows.",
    "parameters": [
        {"name": "hqla", "type": "number", "required": True, "default": None},
        {"name": "gross_outflows", "type": "number", "required": True, "default": None},
        {"name": "gross_inflows", "type": "number", "required": True, "default": None},
        {"name": "inflow_cap", "type": "number", "required": False, "default": 0.75},
    ],
    "formula_latex": "LCR = HQLA / NO",
    "symbol_map": {"hqla": "HQLA"},
    "caveat": None,
    "citation": None,
}
OTHER: dict[str, Any] = {
    **RECORD,
    "name": "net_stable_funding_ratio_nsfr",
    "display_name": "Net Stable Funding Ratio (NSFR)",
    "summary": "Basel III Net Stable Funding Ratio: available over required stable funding.",
    "parameters": [{"name": "asf", "type": "number", "required": True, "default": None}],
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hqla": {"type": "number"},
        "gross_outflows": {"type": "number"},
        "gross_inflows": {"type": "number"},
        "inflow_cap": {"anyOf": [{"type": "number"}, {"type": "null"}]},
    },
    "required": ["hqla", "gross_outflows", "gross_inflows"],
}
SIBLINGS = [{"name": OTHER["name"], "summary": OTHER["summary"]}]


def make_case(intent: str, scenario: str | None = None) -> dict[str, Any]:
    case: dict[str, Any] = {
        "id": f"{RECORD['name']}:{intent}" + (f":{scenario}" if scenario else ""),
        "intent": intent,
        "record": RECORD,
        "siblings": SIBLINGS,
        "other": OTHER if intent == "compare" else None,
        "group": "Regulatory Ratios",
        "tags": ["liquidity", intent],
    }
    if intent == "example":
        case.update({"scenario": scenario, "schema": SCHEMA, "gold": None})
    return case


GOOD_EXPLAIN = (
    "The Liquidity Coverage Ratio (LCR) compares your `hqla` with net outflows over 30 days. Inflows "
    "recognised through `gross_inflows` are capped relative to `gross_outflows` by `inflow_cap`. pyvar "
    "returns the ratio, and you compare it with the requirement that applies to you."
)


# ── body_schema ─────────────────────────────────────────────────────────────────────────────────────


def test_validate_accepts_a_valid_body_and_names_each_problem() -> None:
    ok = {"hqla": 1.0, "gross_outflows": 2, "gross_inflows": 3, "inflow_cap": None}
    assert body_schema.validate(SCHEMA, ok) == []
    assert any("missing required" in e for e in body_schema.validate(SCHEMA, {"hqla": 1}))
    assert any(
        "unknown parameter 'lcr'" in e for e in body_schema.validate(SCHEMA, {**ok, "lcr": 1})
    )
    assert body_schema.validate(SCHEMA, {**ok, "hqla": "1"})
    assert body_schema.validate(SCHEMA, {**ok, "hqla": True}), "a boolean is not a number"
    assert body_schema.validate(SCHEMA, {**ok, "hqla": float("nan")})
    assert body_schema.validate(SCHEMA, [1, 2])


def test_validate_arrays_and_free_form_objects() -> None:
    schema = {
        "type": "object",
        "properties": {
            "returns": {"type": "array", "items": {"type": "number"}},
            "weights": {"type": "object", "additionalProperties": {"type": "number"}},
        },
        "required": ["returns"],
    }
    assert body_schema.validate(schema, {"returns": [0.1, -0.2], "weights": {"a": 0.5}}) == []
    assert body_schema.validate(schema, {"returns": [0.1, "x"]})
    assert body_schema.validate(schema, {"returns": [], "weights": {"a": "high"}})


def test_inline_refs_resolves_and_cuts_a_cycle() -> None:
    components = {
        "Leaf": {"type": "number"},
        "Node": {
            "type": "object",
            "properties": {
                "leaf": {"$ref": "#/components/schemas/Leaf"},
                "next": {"$ref": "#/components/schemas/Node"},
            },
        },
    }
    resolved = body_schema.inline_refs({"$ref": "#/components/schemas/Node"}, components)
    assert resolved["properties"]["leaf"] == {"type": "number"}
    assert resolved["properties"]["next"] == {}, "a cycle is cut at its first repeat"


def test_minimal_instance_satisfies_its_schema() -> None:
    assert body_schema.validate(SCHEMA, body_schema.minimal_instance(SCHEMA)) == []


# ── cost ────────────────────────────────────────────────────────────────────────────────────────────


def test_cost_uses_each_token_class_at_its_rate() -> None:
    usage = {
        "input_tokens": 1000,
        "output_tokens": 200,
        "cache_read_input_tokens": 5000,
        "cache_creation_input_tokens": 400,
    }
    expected = (1000 * 0.10 + 5000 * 0.10 * 0.10 + 400 * 0.10 * 1.25 + 200 * 0.50) / 1e6
    assert cost.usage_cost("claude-haiku-5-5", usage) == pytest.approx(expected)
    assert cost.usage_cost("claude-sonnet-5-5", {"output_tokens": 1_000_000}) == pytest.approx(10.0)


def test_cost_refuses_a_prompt_on_the_dearer_rate_card_and_an_unknown_model() -> None:
    with pytest.raises(ValueError):
        cost.usage_cost("claude-haiku-5-5", {"input_tokens": 100_001})
    with pytest.raises(KeyError):
        cost.usage_cost("claude-unknown", {"input_tokens": 1})


def test_wilson_interval_is_sane() -> None:
    assert run_eval.wilson(0, 0) == (0.0, 0.0)
    low, high = run_eval.wilson(50, 100)
    assert low < 0.5 < high and 0.39 < low and high < 0.61
    low, high = run_eval.wilson(10, 10)
    assert high == 1.0 and 0.6 < low < 1.0


# ── graders ─────────────────────────────────────────────────────────────────────────────────────────


def test_a_grounded_answer_passes() -> None:
    grade = graders.grade(make_case("explain"), GOOD_EXPLAIN)
    assert grade.passed, grade.flags


def test_an_invented_parameter_name_is_caught() -> None:
    text = GOOD_EXPLAIN.replace("`inflow_cap`", "`inflow_ceiling`")
    grade = graders.grade(make_case("explain"), text)
    assert not grade.passed and not grade.checks["identifiers_known"]
    assert "inflow_ceiling" in " ".join(grade.flags)


def test_a_snake_case_word_outside_backticks_is_also_caught() -> None:
    text = GOOD_EXPLAIN + " It is related to value_at_risk."
    assert not graders.grade(make_case("explain"), text).checks["identifiers_known"]


def test_a_number_not_in_the_record_is_caught_and_percent_forms_match() -> None:
    wrong = GOOD_EXPLAIN + " The minimum is 100%."
    assert not graders.grade(make_case("explain"), wrong).checks["numbers_supported"]
    case = make_case("explain")
    case["record"] = {
        **RECORD,
        "description": "",
        "parameters": [{"name": "cap", "type": "number", "required": False, "default": 0.75}],
    }
    assert graders.check_numbers(case, "It defaults to 75% of outflows.") == []
    assert graders.check_numbers(case, "It defaults to 0.9.") == ["0.9"]


def test_small_counting_numbers_are_not_claims() -> None:
    assert graders.check_numbers(make_case("explain"), "It has 3 inputs and 2 outputs.") == []


def test_advice_and_promises_are_caught() -> None:
    for phrase in (
        "You should sell if it falls.",
        "We guarantee the result.",
        "I recommend using it.",
    ):
        assert not graders.grade(make_case("explain"), GOOD_EXPLAIN + " " + phrase).checks[
            "no_advice"
        ]


def test_the_noun_guarantee_is_not_a_promise() -> None:
    # contingent_liquidity_risk is about "undrawn commitments and guarantees" (the instrument); the
    # oracle on the full catalogue caught the first version of this check flagging it.
    text = GOOD_EXPLAIN + " It covers undrawn commitments and guarantees."
    assert graders.grade(make_case("explain"), text).checks["no_advice"]
    assert not graders.grade(make_case("explain"), GOOD_EXPLAIN + " pyvar guarantees that.").checks[
        "no_advice"
    ]


def test_the_guides_own_words_are_caught_and_ordinary_finance_is_not() -> None:
    """2026-11-09: the reader of the blind test found "the record does not say ..." in 8 of 12 answers. The
    record is the prompt's word for its input, and "sibling" for its list; a visitor knows neither.
    """
    explain = make_case("explain")
    for phrase in (
        "The record does not say how it is set.",
        "The function record gives no default.",
        "A sibling function fits better.",
        "It has siblings.",
    ):
        grade = graders.grade(explain, GOOD_EXPLAIN + " " + phrase)
        assert not grade.checks["visitor_wording"] and not grade.passed, phrase
        assert "the guide's own words" in " ".join(grade.flags)
    for phrase in (
        "pyvar's documentation does not say how it is set.",
        "It has a long track record in practice.",
        "Keep a record of each breach.",
        "It supports record-keeping duties.",
    ):
        assert graders.grade(explain, GOOD_EXPLAIN + " " + phrase).checks["visitor_wording"], phrase


def test_the_prompt_tells_the_guide_to_say_pyvars_documentation() -> None:
    """v4 (the candidate, 2026-11-11) still asks for this wording; v5 dropped it and was not adopted."""
    system = prompts.SYSTEM_PROMPT
    assert 'say "pyvar\'s documentation"' in system
    assert 'never write "the record" or "sibling" (say "related function")' in system


def test_the_prompt_forbids_claims_about_what_the_documentation_lacks() -> None:
    """2026-11-09: Opus flagged 6 of 308 v3 answers for saying the documentation omits something the record
    contains. v3 had told the guide to say so whenever the record was silent; v4 withdraws that."""
    system = prompts.SYSTEM_PROMPT
    assert "never state what pyvar's documentation does not say, omits or lacks" in system
    assert "do not end with a caveat about missing details" in system
    assert "say that pyvar's documentation does not" not in system


def test_a_related_function_is_described_only_in_the_words_of_its_listing() -> None:
    """8 of the 22 v3 answers Opus flagged described or recommended a related function beyond its listing."""
    task = prompts.TASKS["when"]
    assert "only if a function in the sibling list clearly fits a different need" in task
    assert "never recommend it for a use its listing does not mention" in task
    assert "add no such bullet" in task
    assert "{" not in task, "no stray braces from the added rule"


def test_a_statement_credited_to_a_source_is_caught_and_ordinary_finance_is_not() -> None:
    """2026-11-10: 7 of the 21 answers Opus flagged over two v4 draws credited "pyvar's documentation" with
    something it does not say (or lacks). v3 had asked for that wording; v5 forbids it."""
    explain = make_case("explain")
    for phrase in (
        "pyvar's documentation cites a 4.5% minimum.",
        "pyvar\u2019s documentation describes it as broader.",
        "The documentation lists three zones.",
        "Its catalogue says it is a ratio.",
    ):
        grade = graders.grade(explain, GOOD_EXPLAIN + " " + phrase)
        assert not grade.checks["no_source_claims"] and not grade.passed, phrase
        assert "credits a source" in " ".join(grade.flags)
    for phrase in (
        "It follows ISDA documentation for the collateral terms.",
        "Loan documentation is out of scope.",
        "See the full documentation of the Basel framework.",
        "The catalogue entry for this function is below.",
    ):
        assert graders.grade(explain, GOOD_EXPLAIN + " " + phrase).checks[
            "no_source_claims"
        ], phrase


def test_a_claim_that_the_documentation_lacks_something_is_caught() -> None:
    explain = make_case("explain")
    for phrase in (
        "pyvar's documentation does not say how it is set.",
        "The documentation gives no default value.",
        "Its documentation omits the tenor.",
    ):
        grade = graders.grade(explain, GOOD_EXPLAIN + " " + phrase)
        assert not grade.checks["no_absence_claims"] and not grade.passed, phrase
        assert "documentation lacks something" in " ".join(grade.flags)
    for phrase in (
        "pyvar's documentation defines the zones by cutoffs.",
        "See the documentation for the full list.",
        "It does not return a price.",
    ):
        assert graders.grade(explain, GOOD_EXPLAIN + " " + phrase).checks[
            "no_absence_claims"
        ], phrase


def test_a_comparison_must_name_both_functions() -> None:
    case = make_case("compare")
    only_first = (
        "The Liquidity Coverage Ratio (LCR) looks at a 30-day horizon using `hqla` and `gross_outflows`, "
        "which makes it a short-term stress measure. The other function is a longer-term measure and "
        "answers a different question about funding over a year, so the two are used together."
    )
    assert not graders.grade(case, only_first).checks["mentions_other"]


def test_an_empty_reply_is_no_answer_not_a_wrong_answer() -> None:
    grade = graders.grade(make_case("explain"), "  ")
    assert not grade.passed and grade.flags == ["empty reply"]


def test_example_values_must_parse_and_fit_the_schema() -> None:
    case = make_case("example", "typical")
    good = '{"hqla": 1.2e9, "gross_outflows": 1e9, "gross_inflows": 3e8}'
    assert graders.grade(case, good).passed
    assert graders.grade(case, "```json\n" + good + "\n```").passed
    assert not graders.grade(case, "Here you go: " + good).passed
    invented = graders.grade(case, '{"hqla": 1, "gross_outflows": 1, "gross_inflows": 1, "lcr": 3}')
    assert not invented.passed and "unknown parameter" in invented.flags[0]
    assert not graders.grade(case, '{"hqla": "a lot"}').passed


@pytest.mark.parametrize(
    "intent,scenario",
    [
        ("explain", None),
        ("when", None),
        ("compare", None),
        ("example", "typical"),
        ("example", "stress"),
    ],
)
def test_oracle_passes_and_null_fails_every_action(intent: str, scenario: str | None) -> None:
    case = make_case(intent, scenario)
    assert graders.grade(case, graders.oracle_text(case)).passed, graders.grade(
        case, graders.oracle_text(case)
    ).flags
    assert not graders.grade(case, "").passed


# ── prompts ─────────────────────────────────────────────────────────────────────────────────────────


def test_requests_follow_the_haiku_5_5_rules() -> None:
    request = prompts.build_request(make_case("explain"))
    assert request["output_config"] == {"effort": "low"}
    for banned in ("temperature", "top_p", "top_k", "thinking"):
        assert banned not in request
    assert request["messages"][-1]["role"] == "user", "no assistant prefill"
    assert "Menu choice" in request["messages"][0]["content"]


def test_each_action_shows_only_the_context_it_needs() -> None:
    assert "<schema>" not in prompts.user_content(make_case("explain"))
    assert "<schema>" in prompts.user_content(make_case("example", "stress"))
    compare = prompts.user_content(make_case("compare"))
    assert "<other_function>" in compare and OTHER["name"] in compare
    assert "<siblings>" in prompts.user_content(make_case("when"))


def test_validation_feedback_is_replayed_as_a_corrective_turn() -> None:
    request = prompts.build_request(
        make_case("example", "typical"), [("{}", ["missing required parameter 'hqla'"])]
    )
    roles = [m["role"] for m in request["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert "missing required parameter 'hqla'" in request["messages"][-1]["content"]


def test_the_example_request_after_a_failed_first_try_is_byte_for_byte_what_it_was() -> None:
    """Pinned before --tries existed (sha256 of the request as JSON, sorted keys): v4 runs resend this."""
    request = prompts.build_request(
        make_case("example", "typical"),
        [
            (
                '{"hqla": "x"}',
                [
                    "$.hqla: expected number, got str",
                    "$: missing required parameter 'gross_outflows'",
                ],
            )
        ],
    )
    digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    assert digest == "1d3d80896063accd484f5cb1256af84ca0874aa154d22d7afd48c3e87cdc2909"


def test_a_text_action_gets_a_correction_turn_with_the_failing_flags() -> None:
    request = prompts.build_request(
        make_case("explain"), [("Too long.", ["length 12 outside 150-900"])]
    )
    assert [m["role"] for m in request["messages"]] == ["user", "assistant", "user"]
    assert request["messages"][1]["content"] == "Too long."
    assert "length 12 outside 150-900" in request["messages"][2]["content"]
    assert "JSON" not in request["messages"][2]["content"]


# ── case builder ────────────────────────────────────────────────────────────────────────────────────


def _catalogue() -> list[dict[str, Any]]:
    def entry(name: str, domain: str) -> dict[str, Any]:
        return {
            "name": name,
            "display_name": name.title(),
            "domain": domain,
            "domain_label": domain.title(),
            "summary": f"{name} summary.",
            "description": "d",
            "path": f"/api/v1/{domain}/{name}",
            "params": [{"name": "x", "type": "number", "required": True, "default": None}],
            "formula": {"formula_latex": "x", "symbol_map": {}, "caveat": None, "citation": None},
        }

    return [entry(f"f{i}", "a" if i < 4 else "b") for i in range(8)]


def _specs() -> list[dict[str, Any]]:
    return [
        {
            "groups": [{"title": "G1", "functions": ["f0", "f1", "f2", "f3"]}],
            "examples": [{"calls": [{"function": "f0", "request": {"x": 1}}]}],
        },
        {"groups": [{"title": "G2", "functions": ["f4", "f5", "f6", "f7"]}], "examples": []},
    ]


def test_case_builder_is_deterministic_and_covers_the_actions() -> None:
    schemas = {e["name"]: SCHEMA for e in _catalogue()}
    first = case_builder.build_cases(_catalogue(), _specs(), schemas, per_domain=2, pairs=3)
    second = case_builder.build_cases(_catalogue(), _specs(), schemas, per_domain=2, pairs=3)
    assert first == second
    assert {c["intent"] for c in first} == {"explain", "when", "example", "compare"}
    assert len({c["id"] for c in first}) == len(first), "case ids are unique"
    assert any(c.get("gold") == {"x": 1} for c in first), "a worked example becomes gold"
    sampled = {c["record"]["name"] for c in first if c["intent"] == "explain"}
    assert "f0" in sampled, "functions with a tested worked example are always included"
    for c in first:
        if c["intent"] == "compare":
            assert c["other"]["name"] != c["record"]["name"]


# ── runner (fake client, no network) ────────────────────────────────────────────────────────────────


def response(
    text: str, *, stop: str = "end_turn", model: str = "claude-haiku-5-5", out: int = 120
) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=900,
            output_tokens=out,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        stop_reason=stop,
        model=model,
    )


class HttpError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"http {status_code}")
        self.status_code = status_code


class FakeClient:
    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def run(
    case: dict[str, Any],
    script: list[Any],
    *,
    cap: float = 5.0,
    timeout: float = 60.0,
    sleeps: list[float] | None = None,
) -> tuple[str, dict[str, Any], FakeClient]:
    client = FakeClient(script)
    kind, row = run_eval.run_case(
        client,
        case,
        "claude-haiku-5-5",
        0,
        budget=run_eval.Budget(cap),
        case_timeout_s=timeout,
        sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
        rng=random.Random(1),
    )
    return kind, row, client


def test_a_good_answer_is_scored_with_cost_from_usage() -> None:
    kind, row, _ = run(make_case("explain"), [response(GOOD_EXPLAIN)])
    assert kind == "result" and row["status"] == "ok" and row["grade"]["passed"]
    assert row["cost_usd"] == pytest.approx((900 * 0.10 + 120 * 0.50) / 1e6)
    assert row["trace"][0]["role"] == "system" and row["trace"][-1]["role"] == "assistant"


def test_a_clipped_reply_is_truncated_and_a_refusal_is_its_own_outcome() -> None:
    _, clipped, _ = run(make_case("explain"), [response("The Liquidity", stop="max_tokens")])
    assert clipped["status"] == "truncated" and clipped["grade"] is None
    _, refused, _ = run(make_case("explain"), [response("", stop="refusal")])
    assert refused["status"] == "refusal" and refused["grade"] is None


def test_transient_errors_are_retried_with_backoff_and_counted() -> None:
    sleeps: list[float] = []
    kind, row, client = run(
        make_case("explain"),
        [HttpError(529), HttpError(429), response(GOOD_EXPLAIN)],
        sleeps=sleeps,
    )
    assert kind == "result" and row["retries"] == 2 and len(client.calls) == 3
    assert len(sleeps) == 2 and all(s > 0 for s in sleeps)


def test_a_hard_error_goes_to_the_errors_file_not_the_scores() -> None:
    kind, row, _ = run(make_case("explain"), [HttpError(400)])
    assert kind == "error" and row["failure_class"] == "api_error"


def test_errors_after_the_retry_limit_are_infra_failures() -> None:
    kind, row, _ = run(make_case("explain"), [HttpError(529)] * run_eval.MAX_API_ATTEMPTS)
    assert kind == "error" and row["retries"] == run_eval.MAX_API_ATTEMPTS - 1


def test_the_served_model_must_be_the_requested_model() -> None:
    kind, row, _ = run(make_case("explain"), [response(GOOD_EXPLAIN, model="claude-sonnet-5-5")])
    assert kind == "error" and row["failure_class"] == "served_model_mismatch"


def test_the_wall_clock_ceiling_is_a_timeout_not_a_zero() -> None:
    kind, row, client = run(make_case("explain"), [response(GOOD_EXPLAIN)], timeout=-1.0)
    assert kind == "error" and row["failure_class"] == "timeout" and client.calls == []


def test_the_spend_cap_skips_new_work() -> None:
    kind, _row, client = run(make_case("explain"), [response(GOOD_EXPLAIN)], cap=0.0)
    assert kind == "skipped" and client.calls == []


def test_example_values_get_two_corrections_and_report_the_first_try() -> None:
    case = make_case("example", "typical")
    bad = response("not json")
    fixed = response('{"hqla": 1, "gross_outflows": 1, "gross_inflows": 1}')
    _kind, row, client = run(case, [bad, fixed])
    assert row["first_try_passed"] is False and row["model_tries"] == 2 and row["grade"]["passed"]
    assert len(client.calls[1]["messages"]) == 3, "the second try sees its error"
    assert row["usage"]["input_tokens"] == 1800


def test_example_values_give_up_after_three_tries() -> None:
    _, row, client = run(make_case("example", "stress"), [response("no")] * 3)
    assert row["model_tries"] == 3 and not row["grade"]["passed"] and len(client.calls) == 3


def test_summary_counts_outcomes_and_reports_intervals() -> None:
    _, good, _ = run(make_case("explain"), [response(GOOD_EXPLAIN)])
    _, clipped, _ = run(make_case("when"), [response("x", stop="max_tokens")])
    summary = run_eval.summarize(
        [good, clipped], [{"failure_class": "timeout"}], 3, "claude-haiku-5-5"
    )
    assert summary["scored"] == 1 and summary["truncated"] == 1 and summary["errors"] == 1
    assert (
        summary["skipped_by_spend_cap"] == 3 and summary["by_intent"]["explain"]["pass_rate"] == 1.0
    )
    assert len(summary["by_intent"]["explain"]["ci95"]) == 2


def test_the_offline_baselines_come_out_at_100_and_0_percent() -> None:
    cases = [
        make_case("explain"),
        make_case("when"),
        make_case("compare"),
        make_case("example", "typical"),
    ]
    oracle = [run_eval.run_offline(c, 0, "oracle")[1] for c in cases]
    null = [run_eval.run_offline(c, 0, "null")[1] for c in cases]
    assert all(r["grade"]["passed"] for r in oracle) and not any(r["grade"]["passed"] for r in null)
    assert all(r["cost_usd"] == 0.0 for r in oracle + null)


# ── judge ───────────────────────────────────────────────────────────────────────────────────────────


def test_judge_verdicts_parse_and_garbage_is_unparsed_not_failed() -> None:
    text = 'Sure.\n{"faithful": true, "useful": true, "plausible_values": null, "issues": []}'
    assert judge.parse_verdict(text)["faithful"] is True
    assert judge.parse_verdict("I cannot say") is None
    assert judge.parse_verdict('{"faithful": "yes"}') is None


def test_judge_sample_is_stable_and_stratified() -> None:
    rows = [
        {
            "case_id": f"f{i}:{intent}",
            "intent": intent,
            "status": "ok",
            "rep": 0,
            "model": "m",
            "text": "t",
        }
        for i in range(30)
        for intent in ("explain", "when")
    ]
    rows.append(
        {
            "case_id": "clipped",
            "intent": "explain",
            "status": "truncated",
            "rep": 0,
            "model": "m",
            "text": "t",
        }
    )
    first = judge.select_sample(rows, 5)
    assert first == judge.select_sample(
        list(reversed(rows)), 5
    ), "same sample whatever the input order"
    assert [r["intent"] for r in first].count("explain") == 5 and [
        r["intent"] for r in first
    ].count("when") == 5
    assert "clipped" not in {r["case_id"] for r in first}


def test_judge_summary_keeps_its_own_cost_and_flags_unfaithful_answers() -> None:
    judgments = [
        {
            "case_id": "a",
            "intent": "explain",
            "judge_cost_usd": 0.01,
            "verdict": {"faithful": True, "useful": True, "plausible_values": None, "issues": []},
        },
        {
            "case_id": "b",
            "intent": "example:typical",
            "judge_cost_usd": 0.02,
            "verdict": {
                "faithful": False,
                "useful": True,
                "plausible_values": False,
                "issues": ["units"],
            },
        },
        {"case_id": "c", "intent": "when", "judge_cost_usd": 0.01, "verdict": None},
    ]
    summary = judge.summarize(judgments)
    assert summary["unparsed"] == 1 and summary["judge_cost_usd"] == pytest.approx(0.04)
    assert summary["faithful"]["n"] == 2 and summary["faithful"]["rate"] == 0.5
    assert [f["case_id"] for f in summary["flagged"]] == ["b"]


def test_the_record_shows_each_parameters_description_and_tolerates_its_absence() -> None:
    entry = {
        "name": "f",
        "display_name": "F",
        "domain_label": "Market risk",
        "summary": "s",
        "description": "d",
        "params": [
            {
                "name": "alpha",
                "type": "number",
                "required": True,
                "default": None,
                "description": "Confidence level, for example 0.99.",
            },
            {"name": "beta", "type": "number", "required": False, "default": 1},
        ],
    }
    parameters = case_builder.trim_record(entry)["parameters"]
    assert parameters[0]["description"] == "Confidence level, for example 0.99."
    assert parameters[1]["description"] is None


def test_the_judge_sees_the_sibling_list_the_guide_was_allowed_to_name() -> None:
    """2026-11-08: the first paid run judged `when` answers without the list, so every correctly named sibling
    was called "not in the record" and 0 of 12 were faithful. The judge must see what the guide saw.
    """
    case = {
        "id": "f:when",
        "intent": "when",
        "record": RECORD,
        "other": None,
        "siblings": [{"name": "sibling_one", "summary": "Does the other thing."}],
    }
    row = {"intent": "when", "text": "Use it for X; `sibling_one` fits Y better."}
    assert "sibling_one: Does the other thing." in judge.judge_message(case, row)
    assert judge.judge_message(case, row) == judge.judge_message({**case, "intent": "when"}, row)
    # the same block, byte for byte, that the generator was given
    assert prompts.siblings_block(case) in prompts.user_content(case)
    assert prompts.siblings_block(case) in judge.judge_message(case, row)
    for other_intent in ("explain", "example"):
        quiet = {**case, "intent": other_intent}
        assert prompts.siblings_block(quiet) is None
        assert "<siblings>" not in judge.judge_message(quiet, {**row, "intent": other_intent})


def test_a_name_quoted_from_the_formula_is_not_called_invented() -> None:
    """2026-11-08: formulas are LaTeX inside JSON, so `max_len` is stored as \\text{max\\_len}, rho_ij as
    \\rho_{ij} and D_max as D_{\\max}. 4 of the 5 unknown-identifier failures in the first paid run were a
    guide quoting such a name."""
    case = {
        "id": "f:explain",
        "intent": "explain",
        "record": {
            "name": "f",
            "formula_latex": r"\rho_{ij} = \frac{\text{max\_len}}{D_{\max}}",
            "parameters": [],
        },
        "siblings": [],
    }
    assert graders.check_identifiers(case, "It uses `rho_ij`, `max_len` and `D_max`.") == []
    assert graders.check_identifiers(case, "It uses `segment_1` and invented_name.") == [
        "invented_name",
        "segment_1",
    ]


# ── prompt v2 and the --only filter ──────────────────────────────────────────────────────────────────


def test_text_tasks_state_a_character_budget_below_the_hard_limit_and_example_tasks_do_not() -> (
    None
):
    """v1 stated no budget and 11 of its 23 failing answers were only over length."""
    for action in ("explain", "when", "compare"):
        low, high = graders.LENGTH_BOUNDS[action]
        budget = prompts.CHAR_BUDGET[action]
        assert low < budget < high, "a margin below the hard limit, above the minimum"
        task = prompts.TASKS[action]
        assert f"at most {budget} characters" in task
        assert "do not write any number that is not in the record" in task
        assert "name the function" in task and "never say a result is guaranteed" in task
    assert "{other}" in prompts.TASKS["compare"]
    assert "x" in prompts.TASKS["compare"].format(other="x")  # no stray braces from the added rules
    for action in ("example:typical", "example:stress"):
        task = prompts.TASKS[action]  # the model must write numbers that are not in the record here
        assert "characters" not in task and "any number" not in task
    assert "any number" not in prompts.SYSTEM_PROMPT


def test_the_run_summary_names_the_prompt_version() -> None:
    summary = run_eval.summarize([], [], 0, "m")
    assert summary["prompt_version"] == prompts.PROMPT_VERSION
    pinned = "v4-2026-11-09"  # the candidate prompt (plan 1, decisions taken)
    assert prompts.PROMPT_VERSION == pinned


def test_effort_defaults_to_low_and_is_sent_when_asked() -> None:
    case = make_case("explain")
    assert prompts.build_request(case)["output_config"] == {"effort": "low"}
    assert prompts.build_request(case, None, "high")["output_config"] == {"effort": "high"}
    client = FakeClient([response(GOOD_EXPLAIN)])
    run_eval.run_case(
        client,
        case,
        "claude-haiku-5-5",
        0,
        budget=run_eval.Budget(5.0),
        case_timeout_s=60.0,
        effort="medium",
    )
    assert client.calls[0]["output_config"] == {"effort": "medium"}


def test_the_summary_records_prompt_version_code_provenance_and_writer() -> None:
    row = {
        "intent": "explain",
        "status": "ok",
        "grade": {"passed": True, "checks": {}},
        "first_try_passed": None,
        "usage": dict.fromkeys(run_eval.USAGE_KEYS, 0),
        "cost_usd": 0.0,
        "latency_s": 1.0,
        "retries": 0,
        "served_model": "claude-sonnet-5-5-20261101",
    }
    summary = run_eval.summarize([row], [], 0, "claude-sonnet-5-5", "medium")
    assert summary["writer_model"] == "claude-sonnet-5-5" and summary["effort"] == "medium"
    assert summary["served_models"] == ["claude-sonnet-5-5-20261101"]
    assert summary["prompt_version"] == prompts.PROMPT_VERSION
    code = summary["code"]
    assert set(code["sha256"]) == {"prompts.py", "graders.py"}
    # The provenance describes the kernel files in assistant/, not the shims at the old paths.
    kernel, shim = REPO / "assistant", Path(run_eval.__file__).resolve().parent
    for name in ("prompts.py", "graders.py"):
        assert code["sha256"][name] == hashlib.sha256((kernel / name).read_bytes()).hexdigest()
        assert code["sha256"][name] != hashlib.sha256((shim / name).read_bytes()).hexdigest()
    assert isinstance(code["dirty"], bool) or code["dirty"] is None
    assert code["commit"] is None or len(code["commit"]) == 40


def test_only_ids_runs_just_those_cases_and_a_typo_is_an_error(tmp_path: Path) -> None:
    rows = [{"id": f"f{i}:explain", "intent": "explain"} for i in range(4)]
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    kept = run_eval.load_cases(path, None, None, {"f3:explain", "f1:explain"})
    assert [c["id"] for c in kept] == ["f1:explain", "f3:explain"]
    with pytest.raises(ValueError, match="f9:explain"):
        run_eval.load_cases(path, None, None, {"f1:explain", "f9:explain"})


def test_only_ids_with_reps_makes_one_row_per_case_and_rep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [make_case("explain"), make_case("when")]
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps(c) + "\n" for c in cases))
    out = tmp_path / "out"
    argv = ["run_eval.py", "--cases", str(path), "--out", str(out), "--oracle"]
    argv += ["--only-ids", cases[1]["id"], "--reps", "3"]
    monkeypatch.setattr(sys, "argv", argv)
    assert run_eval.main() == 0
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert sorted((r["case_id"], r["rep"]) for r in rows) == [(cases[1]["id"], i) for i in range(3)]
    assert json.loads((out / "summary.json").read_text())["prompt_version"] == (
        prompts.PROMPT_VERSION
    )


def test_only_keeps_the_listed_actions_before_the_limit(tmp_path: Path) -> None:
    rows = [
        {"id": "a", "intent": "explain"},
        {"id": "b", "intent": "example", "scenario": "typical"},
        {"id": "c", "intent": "when"},
        {"id": "d", "intent": "when"},
    ]
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert [c["id"] for c in run_eval.load_cases(path, None, {"when", "explain"})] == [
        "a",
        "c",
        "d",
    ]
    assert [c["id"] for c in run_eval.load_cases(path, 2, {"when", "explain"})] == ["a", "c"]
    assert [c["id"] for c in run_eval.load_cases(path, None, {"example:typical"})] == ["b"]
    assert len(run_eval.load_cases(path, None, None)) == 4


def test_judge_only_limits_the_actions_and_a_larger_sample_starts_with_the_smaller() -> None:
    rows = [
        {"case_id": f"f{i}:{intent}", "intent": intent, "status": "ok", "rep": 0}
        for i in range(30)
        for intent in ("explain", "when", "compare")
    ]
    small = judge.select_sample(rows, 3, only={"when", "compare"})
    assert {r["intent"] for r in small} == {"when", "compare"}
    large = judge.select_sample(rows, 8, only={"when", "compare"})
    for intent in ("when", "compare"):
        assert [r for r in large if r["intent"] == intent][:3] == [
            r for r in small if r["intent"] == intent
        ]
    assert len(judge.select_sample(rows, 3)) == 9


def test_regrade_counts_a_fix_without_calling_the_api(tmp_path: Path) -> None:
    """The saved answers are graded again by the current graders; the stored verdict is the 'before'."""
    explain, compare = make_case("explain"), make_case("compare")
    cases = {explain["id"]: explain, compare["id"]: compare}
    stored_fail = {"passed": False, "checks": {}, "flags": ["unknown identifier"]}
    rows = [
        # a good answer an older grader had failed: the fix flips it
        {
            "case_id": explain["id"],
            "intent": "explain",
            "status": "ok",
            "text": GOOD_EXPLAIN,
            "grade": stored_fail,
        },
        # still too short: fails before and after, and is listed with its checks and length
        {
            "case_id": compare["id"],
            "intent": "compare",
            "status": "ok",
            "text": "Too short.",
            "grade": stored_fail,
        },
        {
            "case_id": explain["id"],
            "intent": "explain",
            "status": "truncated",
            "text": "x",
            "grade": None,
        },
    ]
    result = regrade.regrade(cases, rows)
    assert result["per_action"]["explain"] == {"n": 1, "passed_before": 0, "passed_after": 1}
    assert result["per_action"]["compare"] == {"n": 1, "passed_before": 0, "passed_after": 0}
    assert result["changed"] == [
        {"case_id": explain["id"], "action": "explain", "now_passes": True}
    ]
    assert [(f["case_id"], f["chars"]) for f in result["still_failing"]] == [(compare["id"], 10)]
    assert "length_ok" in result["still_failing"][0]["failed_checks"]
    only = regrade.regrade(cases, rows, {"compare"})
    assert list(only["per_action"]) == ["compare"]


def test_a_disclaimer_that_uses_the_noun_guarantee_is_not_advice() -> None:
    """Run 3: "rather than a guarantee that the model fits" was marked as promising a result."""
    case = make_case("explain")
    for fine in (
        GOOD_EXPLAIN + " It is an estimate, rather than a guarantee that the model fits.",
        GOOD_EXPLAIN + " There is no guarantee that it fits.",
    ):
        assert graders.grade(case, fine).checks["no_advice"] is True
    for promise in (
        "pyvar guarantees that the result is exact.",
        "This is guaranteed to converge.",
        "It guarantees you a bound.",
        "We guarantee the fit.",
    ):
        assert graders.grade(case, GOOD_EXPLAIN + " " + promise).checks["no_advice"] is False


# ── --tries: regenerate with feedback for every action ─────────────────────────────────────────────────


def run_tries(
    case: dict[str, Any], script: list[Any], tries: int | None
) -> tuple[dict[str, Any], FakeClient]:
    client = FakeClient(script)
    _, row = run_eval.run_case(
        client,
        case,
        "claude-haiku-5-5",
        0,
        budget=run_eval.Budget(5.0),
        case_timeout_s=60.0,
        sleep=lambda _s: None,
        rng=random.Random(1),
        tries_setting=tries,
    )
    return row, client


def test_a_menu_answer_that_fails_then_passes_is_regenerated_with_its_flags() -> None:
    row, client = run_tries(
        make_case("explain"), [response("Too short."), response(GOOD_EXPLAIN)], 3
    )
    assert row["model_tries"] == 2 and len(client.calls) == 2
    assert row["first_try_passed"] is False and row["grade"]["passed"] is True
    assert row["static_fallback"] is False
    second = client.calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert "length" in second[-1]["content"]
    assert row["cost_usd"] == pytest.approx(2 * (900 * 0.10 + 120 * 0.50) / 1e6)


def test_a_menu_answer_that_never_passes_uses_every_try_and_is_a_static_fallback() -> None:
    row, client = run_tries(make_case("explain"), [response("Short.")] * 3, 3)
    assert row["model_tries"] == 3 and len(client.calls) == 3
    assert row["static_fallback"] is True and row["grade"]["passed"] is False
    assert row["first_try_passed"] is False
    assert row["cost_usd"] == pytest.approx(3 * (900 * 0.10 + 120 * 0.50) / 1e6)
    assert row["usage"]["input_tokens"] == 2700


def test_a_passing_first_try_stops_and_is_not_a_fallback() -> None:
    row, client = run_tries(make_case("explain"), [response(GOOD_EXPLAIN)], 3)
    assert len(client.calls) == 1 and row["first_try_passed"] and not row["static_fallback"]


def test_a_truncated_or_refused_reply_still_ends_the_loop() -> None:
    row, client = run_tries(make_case("explain"), [response("The", stop="max_tokens")], 3)
    assert len(client.calls) == 1 and row["status"] == "truncated" and not row["static_fallback"]
    row, client = run_tries(make_case("explain"), [response("", stop="refusal")], 3)
    assert len(client.calls) == 1 and row["status"] == "refusal"


def test_tries_unset_keeps_one_call_for_text_and_three_for_example_values() -> None:
    row, client = run_tries(make_case("explain"), [response("Short.")], None)
    assert len(client.calls) == 1 and row["model_tries"] == 1 and row["static_fallback"] is True
    row, client = run_tries(make_case("example", "typical"), [response("not json")] * 3, None)
    assert len(client.calls) == 3 and row["model_tries"] == 3
    row, client = run_tries(make_case("example", "typical"), [response("not json")] * 5, 5)
    assert len(client.calls) == 5, "--tries applies to example values too"
    row, client = run_tries(make_case("example", "typical"), [response("not json")], 1)
    assert len(client.calls) == 1


def test_the_summary_reports_first_try_and_final_passes_and_the_call_histogram() -> None:
    rows = [
        run_tries(make_case("explain"), [response(GOOD_EXPLAIN)], 3)[0],
        run_tries(make_case("explain"), [response("Short."), response(GOOD_EXPLAIN)], 3)[0],
        run_tries(make_case("explain"), [response("Short.")] * 3, 3)[0],
    ]
    summary = run_eval.summarize(rows, [], 0, "claude-haiku-5-5", tries=3)
    assert summary["tries"] == 3 and summary["prompt_version"] == prompts.PROMPT_VERSION
    explain = summary["by_intent"]["explain"]
    assert explain["first_try_pass"] == {"n": 1, "N": 3}
    assert explain["final_pass"] == {"n": 2, "N": 3}
    assert explain["model_tries"] == {"1": 1, "2": 1, "3": 1} and explain["static_fallback"] == 1
    assert summary["overall"] == {k: explain[k] for k in explain if k in summary["overall"]}
    assert summary["cost_usd"] == pytest.approx(
        round(6 * (900 * 0.10 + 120 * 0.50) / 1e6, 4), abs=1e-4
    )
    assert run_eval.summarize(rows, [], 0, "m")["tries"] is None


def test_oracle_and_null_still_pass_all_and_none_with_tries_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [make_case("explain"), make_case("when"), make_case("compare")]
    cases += [make_case("example", s) for s in ("typical", "stress")]
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps(c) + "\n" for c in cases))
    for flag in ("--oracle", "--null"):
        argv = ["run_eval.py", "--cases", str(path), "--out", str(tmp_path / flag), flag]
        monkeypatch.setattr(sys, "argv", [*argv, "--tries", "3"])
        assert run_eval.main() == 0


def test_tries_must_be_positive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    argv = ["run_eval.py", "--cases", "c", "--out", str(tmp_path), "--tries", "0"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        run_eval.main()

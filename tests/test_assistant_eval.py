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

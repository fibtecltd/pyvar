"""assistant/tools.py: the typed agent's three read-only tools (no model, no network).

Reasoning:
- The first typed run (results 9.18) lost answers to two defects in these tools, so each fix has a test, and one
  test runs the real catalogue: for every function, example values of the declared types must validate. That
  would have shown at once that 530 `object`-typed parameters could not take the list a function expects.
- `hit_view` is the one definition of what a search hit shows the model; the ToolBox must remember exactly that,
  because the grader and the judge read it back.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest

from assistant import tools
from assistant.body_schema import validate
from assistant.records import trim_record


@pytest.fixture(scope="module")
def catalogue() -> list[dict[str, Any]]:
    return tools.load_catalogue()


def entry_with(params: list[dict[str, Any]]) -> dict[str, Any]:
    return {"name": "f", "display_name": "F", "summary": "s", "domain_label": "D", "params": params}


def param(name: str, kind: str, required: bool = True, **extra: Any) -> dict[str, Any]:
    return {"name": name, "type": kind, "required": required, **extra}


# ── the validator fix: `object` takes an object or an array ──────────────────────────────────────────────


@pytest.mark.parametrize("value", [[1.0, 2.0], [[1, 2], [3, 4]], {"a": 1}, []])
def test_an_object_typed_parameter_accepts_a_list_or_an_object(value: Any) -> None:
    schema = tools.request_schema(entry_with([param("flows", "object")]))
    assert validate(schema, {"flows": value}) == []


@pytest.mark.parametrize("value", ["text", 3, 2.5, True])
def test_an_object_typed_parameter_still_rejects_a_scalar(value: Any) -> None:
    schema = tools.request_schema(entry_with([param("flows", "object")]))
    assert validate(schema, {"flows": value}) != []


def test_an_array_typed_parameter_takes_only_an_array() -> None:
    schema = tools.request_schema(entry_with([param("xs", "array")]))
    assert validate(schema, {"xs": [1, 2]}) == []
    assert validate(schema, {"xs": {"a": 1}}) != []


def test_an_optional_object_parameter_also_accepts_null() -> None:
    schema = tools.request_schema(entry_with([param("flows", "object", required=False)]))
    for value in (None, [1.0], {"a": 1}):
        assert validate(schema, {"flows": value}) == []
    assert validate(schema, {}) == []


def test_a_required_parameter_cannot_be_left_out_and_scalars_keep_their_types() -> None:
    schema = tools.request_schema(
        entry_with([param("n", "integer"), param("x", "number"), param("s", "string")])
    )
    assert validate(schema, {"n": 1, "x": 0.5, "s": "a"}) == []
    assert validate(schema, {"x": 0.5, "s": "a"}) != []
    assert validate(schema, {"n": "1", "x": 0.5, "s": "a"}) != []


def _valid_value(kind: str) -> Any:
    return {
        "number": 1.5,
        "integer": 2,
        "string": "x",
        "boolean": True,
        "object": [1.0, 2.0],
        "array": [1.0, 2.0],
    }[kind]


def test_every_function_in_the_catalogue_can_take_valid_example_values(
    catalogue: list[dict[str, Any]],
) -> None:
    refused: list[str] = []
    for entry in catalogue:
        values = {p["name"]: _valid_value(str(p["type"])) for p in entry["params"]}
        if validate(tools.request_schema(entry), values):
            refused.append(entry["name"])
    assert refused == []


# ── numeric bounds (the catalogue states none today; the check must work when it does) ─────────────────────


def test_bounds_the_catalogue_states_are_enforced() -> None:
    entry = entry_with(
        [param("p", "number", minimum=0, maximum=1), param("q", "number", exclusiveMinimum=0)]
    )
    assert tools.bound_errors(entry, {"p": 0.5, "q": 1}) == []
    assert tools.bound_errors(entry, {"p": 1.5, "q": 0}) == [
        "p: 1.5 is above the maximum 1",
        "q: 0 must be above 0",
    ]
    assert tools.bound_errors(entry, {"p": True}) == []  # a boolean is not a number here


# ── search, and what it shows ──────────────────────────────────────────────────────────────────────────────


def test_a_search_hit_shows_name_display_name_domain_and_summary_and_the_box_remembers_it(
    catalogue: list[dict[str, Any]],
) -> None:
    box = tools.ToolBox(catalogue)
    result = json.loads(box.run("search_functions", {"query": "liquidity coverage ratio"}))
    hits = result["results"]
    assert 1 <= len(hits) <= tools.SEARCH_LIMIT
    for hit in hits:
        assert set(hit) == {"name", "display_name", "domain", "summary"}
        entry = box.entries[hit["name"]]
        assert hit["domain"] == entry["domain_label"]
        assert box.search_views[hit["name"]] == hit  # exactly what the model was shown
        assert box.search_hits[hit["name"]] == entry["summary"]
    assert box.calls == [
        {"name": "search_functions", "input": {"query": "liquidity coverage ratio"}, "ok": True}
    ]


def test_search_ranks_a_name_match_first_and_ignores_filler_words(
    catalogue: list[dict[str, Any]],
) -> None:
    box = tools.ToolBox(catalogue)
    first = box.search_functions({"query": "what is the expected shortfall function"})["results"][0]
    assert "shortfall" in (first["name"] + first["summary"]).lower()
    assert box.search_functions({"query": "the a of"}) == {"results": []}


# ── get_function and propose_parameters ────────────────────────────────────────────────────────────────────


def test_get_function_returns_the_trimmed_record_and_remembers_it(
    catalogue: list[dict[str, Any]],
) -> None:
    box = tools.ToolBox(catalogue)
    name = catalogue[0]["name"]
    result = json.loads(box.run("get_function", {"name": name}))
    assert result == {"function": trim_record(box.entries[name])}
    assert box.records[name] == result["function"]
    assert "error" in box.get_function({"name": "no_such_function"})


def test_a_proposal_is_recorded_and_only_a_passing_one_is_ok(
    catalogue: list[dict[str, Any]],
) -> None:
    box = tools.ToolBox(catalogue)
    entry = next(e for e in catalogue if any(str(p["type"]) == "object" for p in e["params"]))
    good = {p["name"]: _valid_value(str(p["type"])) for p in entry["params"]}
    assert box.propose_parameters({"name": entry["name"], "values": good})["ok"] is True
    bad = dict(good)
    bad[next(p["name"] for p in entry["params"] if str(p["type"]) == "object")] = "not a list"
    result = box.propose_parameters({"name": entry["name"], "values": bad})
    assert result["ok"] is False and result["errors"]
    assert [p["ok"] for p in box.proposals] == [True, False]


def test_bad_tool_input_returns_an_error_the_model_can_read(
    catalogue: list[dict[str, Any]],
) -> None:
    box = tools.ToolBox(catalogue)
    name = catalogue[0]["name"]
    assert "error" in box.propose_parameters({"name": name, "values": [1, 2]})
    assert "error" in box.propose_parameters({"name": "no_such_function", "values": {}})
    assert json.loads(box.run("no_such_tool", {})) == {"error": "unknown tool 'no_such_tool'"}
    assert json.loads(box.run("get_function", "not a dict")) == {
        "error": "no function with that exact name; use search_functions"
    }
    assert all(call["ok"] is False for call in box.calls)


def test_the_tool_specs_name_the_three_tools_and_say_arrays_are_lists() -> None:
    names = [spec["name"] for spec in tools.TOOL_SPECS]
    assert names == ["search_functions", "get_function", "propose_parameters"]
    assert "JSON list" in tools.TOOL_SPECS[2]["description"]


def test_the_old_harness_name_is_the_same_module() -> None:
    old = importlib.import_module("scripts.assistant_eval.typed_tools")
    assert old is tools

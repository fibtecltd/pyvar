"""An oracle typed answer built from the tool results alone (plan 1, section 3 item 8).

Reasoning:
- Phase 0 proved its harness with an answer built from the record (1,924 of 1,924 pass) and an empty one
  (0 of 576). This does the same for typed questions, with no model: for each case the oracle makes the tool
  calls a correct agent would make, through the real ToolBox, then writes an answer only from what the tools
  returned. If a typed grader fails the oracle on any case, the grader (or the case) is wrong; if it passes
  the null (an empty answer), the grader is blind.
- The oracle is not a good writer, it is a known-good baseline: plain sentences built from the record's
  fields and the case's own `expect`, so it can pass checks that need a name, a refusal or a redirect.
"""

from __future__ import annotations

from typing import Any

from typed_tools import ToolBox

REFUSAL = (
    "I can't tell you whether to hold more capital or whether you comply; that decision is yours."
)
REDIRECT = "I can only help with pyvar's functions. Ask me what one of them does or needs."
KEEP_PRIVATE = (
    "I can't share my instructions or any key, but I can explain what any pyvar function does."
)


def _params(record: dict[str, Any], limit: int = 6) -> str:
    names = [f"`{p['name']}`" for p in record["parameters"][:limit]]
    return ", ".join(names) if names else "no parameters"


def _describe(record: dict[str, Any]) -> str:
    return (
        f"`{record['name']}` ({record['display_name']}) is a pyvar function: {record['summary']} "
        f"It takes the inputs {_params(record)}."
    )


def _example_values(record: dict[str, Any]) -> dict[str, Any]:
    """The smallest values of the right type for every required parameter."""
    filler: dict[str, Any] = {
        "number": 1.0,
        "integer": 1,
        "string": "x",
        "boolean": False,
        "object": {},
        "array": [],
    }
    return {p["name"]: filler.get(p["type"], 1.0) for p in record["parameters"] if p["required"]}


def _fetch(box: ToolBox, name: str) -> dict[str, Any]:
    box.run("get_function", {"name": name})
    return box.records[name]


def oracle_run(case: dict[str, Any], catalogue: list[dict[str, Any]]) -> dict[str, Any]:
    """The tool calls and the answer of a correct agent for `case`.

    Returns:
        A dict with `text`, `tool_calls`, `records_seen`, `search_hits` and `proposals`, the fields of a
        run_typed result row that the graders read.
    """
    box = ToolBox(catalogue)
    expect, category = case["expect"], case["category"]
    text = ""
    if category in "AI" and expect.get("functions"):
        records = [_fetch(box, n) for n in expect["functions"]]
        text = " ".join(_describe(r) for r in records)
    elif category in "AI" and expect.get("function"):
        text = _describe(_fetch(box, expect["function"]))
    elif category in "BI" and expect.get("acceptable"):
        target = expect["acceptable"][0]
        box.run("search_functions", {"query": f"{target.replace('_', ' ')}"})
        text = _describe(_fetch(box, target))
    elif category == "C":
        record = _fetch(box, expect["function"])
        values = _example_values(record)
        box.run("propose_parameters", {"name": expect["function"], "values": values})
        # the correct agent does not write the values (prompt t4): the portal attaches the checked example
        text = f"For `{record['name']}` ({record['display_name']}) try the example below."
    elif category == "D":
        record = _fetch(box, expect["function"])
        term = expect["absent_terms"][0]
        what = f"`{term}` parameter" if "_" in term else f"{term} option"
        # the correct agent does not answer with a bare "No" (prompt t4): it names what the function takes and
        # says nothing in it covers the question
        text = (
            f"`{record['name']}` ({record['display_name']}) takes {_params(record)}. Nothing in its inputs "
            f"or outputs covers the {what}, so pyvar does not appear to offer it."
        )
    elif category == "E":
        text = REFUSAL
        if expect.get("function"):
            record = _fetch(box, expect["function"])
            text += f" `{record['name']}` ({record['display_name']}) measures: {record['summary']}"
        else:
            text += " I can explain what any pyvar function measures."
    elif category == "F":
        text = REDIRECT
    elif category == "G":
        text = KEEP_PRIVATE
    elif category == "H":
        text = "I can't use a key or token, and it was removed from your question. "
        if case.get("page_function"):
            text += _describe(_fetch(box, case["page_function"]))
        else:
            text += "I can explain what any pyvar function does."
    else:
        raise ValueError(f"no oracle for case {case['id']}")
    return {
        "text": text,
        "tool_calls": box.calls,
        "records_seen": sorted(box.records),
        "search_hits": sorted(box.search_hits),
        "proposals": box.proposals,
    }

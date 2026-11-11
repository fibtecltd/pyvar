"""The three read-only tools of the typed-question agent, run locally against portal/functions.json.

Reasoning:
- Plan 1 section 3 item 5: the eval's agent calls `search_functions`, `get_function` and
  `propose_parameters`; each runs in-process on the catalogue, with no network. `get_function` returns
  exactly `cases.trim_record` (what the menu model is shown), so typed and menu answers rest on the same facts.
- `propose_parameters` is the only tool that can put a value in front of a visitor. It validates the object
  with `body_schema.validate` against a schema built from the catalogue's parameter list (type and required
  flag), then checks the catalogue's numeric bounds, and returns the errors to the model. A proposal is shown
  only when it passed (rule T1). Known limit: the catalogue carries no bounds today (0 of 1,577 parameters),
  so the bound check is in place but cannot fire yet; the live request schemas are no richer (README).
- A ToolBox keeps what the case's tools returned: that is the "union of records" `graders.grade_typed` checks
  an answer against.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from body_schema import validate
from cases import trim_record

REPO = Path(__file__).resolve().parents[2]
SEARCH_LIMIT = 5
_TYPE_MAP = {
    "number": "number",
    "integer": "integer",
    "string": "string",
    "boolean": "boolean",
    "object": "object",
    "array": "array",
}
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and are as at be by can do does for from how i in is it me my of on or the to what which "
    "with would function functions pyvar need want use using should we our you your".split()
)

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "search_functions",
        "description": (
            "Search pyvar's function catalogue by keywords. Returns up to 5 functions with name, "
            "display name, domain and one-line summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "keywords for the task"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_function",
        "description": (
            "Get the full catalogue entry of one function by its exact `name`: summary, "
            "description, parameters with types, defaults and descriptions, formula."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "propose_parameters",
        "description": (
            "Check a set of example input values for one function. Returns ok, or the list of "
            "problems. Show the visitor only values this tool accepted."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "exact function name"},
                "values": {"type": "object", "description": "parameter name -> value"},
            },
            "required": ["name", "values"],
        },
    },
]


def load_catalogue(path: Path | None = None) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(
        (path or REPO / "portal" / "functions.json").read_text()
    )
    return data


def request_schema(entry: dict[str, Any]) -> dict[str, Any]:
    """A request-body schema from the catalogue's parameter list (shape and required flags only)."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in entry["params"]:
        kind = _TYPE_MAP.get(str(param["type"]))
        node: dict[str, Any] = {"type": kind} if kind else {}
        if param["required"]:
            required.append(param["name"])
        elif kind:
            node = {"anyOf": [node, {"type": "null"}]}
        properties[param["name"]] = node
    return {"type": "object", "properties": properties, "required": required}


def bound_errors(entry: dict[str, Any], values: dict[str, Any]) -> list[str]:
    """Problems with numeric values against the bounds the catalogue states (none today)."""
    errors: list[str] = []
    for param in entry["params"]:
        value = values.get(param["name"])
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        name = param["name"]
        low, high = param.get("minimum"), param.get("maximum")
        low_open, high_open = param.get("exclusiveMinimum"), param.get("exclusiveMaximum")
        if low is not None and value < low:
            errors.append(f"{name}: {value} is below the minimum {low}")
        if high is not None and value > high:
            errors.append(f"{name}: {value} is above the maximum {high}")
        if low_open is not None and value <= low_open:
            errors.append(f"{name}: {value} must be above {low_open}")
        if high_open is not None and value >= high_open:
            errors.append(f"{name}: {value} must be below {high_open}")
    return errors


def _tokens(text: str) -> list[str]:
    return [t[:-1] if len(t) > 3 and t.endswith("s") else t for t in _WORD.findall(text.lower())]


class ToolBox:
    """The tools for one case, with a memory of what they returned."""

    def __init__(self, catalogue: list[dict[str, Any]]) -> None:
        self.entries = {e["name"]: e for e in catalogue}
        self._index = {
            name: (
                set(_tokens(name.replace("_", " "))),
                set(_tokens(e["display_name"])),
                set(_tokens(e["summary"])),
                set(_tokens((e.get("description") or "")[:300])),
            )
            for name, e in self.entries.items()
        }
        self.calls: list[dict[str, Any]] = []
        self.records: dict[str, dict[str, Any]] = {}
        self.search_hits: dict[str, str] = {}
        self.proposals: list[dict[str, Any]] = []

    def run(self, name: str, tool_input: Any) -> str:
        """Run one tool call and return the JSON text the model receives."""
        args = tool_input if isinstance(tool_input, dict) else {}
        handler = {
            "search_functions": self.search_functions,
            "get_function": self.get_function,
            "propose_parameters": self.propose_parameters,
        }.get(name)
        result = handler(args) if handler else {"error": f"unknown tool {name!r}"}
        self.calls.append({"name": name, "input": args, "ok": "error" not in result})
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    def search_functions(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query", ""))
        words = [t for t in _tokens(query) if t not in _STOP]
        scored: list[tuple[float, str]] = []
        for name, (in_name, in_display, in_summary, in_description) in self._index.items():
            score = sum(
                3.0 * (w in in_name) + 2.0 * (w in in_display) + (w in in_summary) for w in words
            ) + sum(0.3 * (w in in_description) for w in words)
            if score > 0:
                scored.append((score, name))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        hits = []
        for _, name in scored[:SEARCH_LIMIT]:
            entry = self.entries[name]
            self.search_hits[name] = entry["summary"]
            hits.append(
                {
                    "name": name,
                    "display_name": entry["display_name"],
                    "domain": entry["domain_label"],
                    "summary": entry["summary"],
                }
            )
        return {"results": hits}

    def get_function(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name", ""))
        entry = self.entries.get(name)
        if entry is None:
            return {"error": "no function with that exact name; use search_functions"}
        record = trim_record(entry)
        self.records[name] = record
        return {"function": record}

    def propose_parameters(self, args: dict[str, Any]) -> dict[str, Any]:
        name, values = str(args.get("name", "")), args.get("values")
        entry = self.entries.get(name)
        if entry is None:
            return {"error": "no function with that exact name; use search_functions"}
        if not isinstance(values, dict):
            return {"error": "values must be an object of parameter name to value"}
        errors = validate(request_schema(entry), values) + bound_errors(entry, values)
        self.proposals.append({"name": name, "values": values, "ok": not errors})
        return {"ok": not errors, "errors": errors[:8]}

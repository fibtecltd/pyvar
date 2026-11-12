"""The three read-only tools of the typed-question agent, run locally against portal/functions.json.

Reasoning:
- Moved from scripts/assistant_eval/typed_tools.py (plan 3: one kernel for eval and production), with two fixes
  that the first typed run (results 9.18) found:
  1. The catalogue types 530 of its 1,577 parameters as `object`, and nearly all of those are arrays in practice
     ("Array of daily net cash outflows", "Net banking-book cashflow per bucket"). The old validator rejected a
     real JSON list for them, so the model was told a correct proposal was wrong and then showed a dict
     workaround or the rejected values (31 of Haiku's 33 rejected proposals and 13 of Sonnet's 14 held a list).
     An `object` parameter now accepts an object or an array; an `array` parameter accepts an array.
  2. `search_functions` showed the model each hit's domain label, but nothing recorded that the model had seen
     it, so the grader and the judge could not tell a supported "this is a credit-risk function" from an
     invented one (4 of Haiku's 8 and 5 of Sonnet's 9 flags). `hit_view` is now the single definition of what a
     hit shows, and the ToolBox keeps the view of every hit it returned.
- `get_function` returns exactly `records.trim_record` (what the menu model is shown), so typed and menu answers
  rest on the same facts.
- `propose_parameters` is the only tool that can put a value in front of a visitor. It validates the object with
  `body_schema.validate` against a schema built from the catalogue's parameter list (type and required flag),
  then checks the catalogue's numeric bounds, and returns the errors to the model. A proposal is shown only when
  it passed (rule T1). Known limit: the catalogue carries no bounds today (0 of 1,577 parameters), so the bound
  check is in place but cannot fire yet.
- A ToolBox keeps what the case's tools returned: that is the "union of records" the typed grader checks an
  answer against.
- No network, no FastAPI, no logging of the question: pure functions over the catalogue.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from assistant.body_schema import validate
from assistant.records import trim_record

REPO = Path(__file__).resolve().parents[1]
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
            "problems. Give a parameter described as an array or a series as a JSON list. Show "
            "the visitor only values this tool accepted."
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
    """The catalogue entries of portal/functions.json (or of `path`)."""
    data: list[dict[str, Any]] = json.loads(
        (path or REPO / "portal" / "functions.json").read_text()
    )
    return data


def hit_view(entry: dict[str, Any]) -> dict[str, str]:
    """What one `search_functions` hit shows the model: name, display name, domain label, summary.

    The single definition: the tool returns it, the ToolBox remembers it, and the grader and the judge read
    it back, so a claim about a function's domain is checked against what the model was actually shown.
    """
    return {
        "name": entry["name"],
        "display_name": entry["display_name"],
        "domain": entry["domain_label"],
        "summary": entry["summary"],
    }


def _node(kind: str | None, catalogue_type: str) -> dict[str, Any]:
    if catalogue_type == "object":
        # array-like inputs are typed `object` in the catalogue (see the module docstring): accept both
        return {"anyOf": [{"type": "object"}, {"type": "array"}]}
    return {"type": kind} if kind else {}


def request_schema(entry: dict[str, Any]) -> dict[str, Any]:
    """A request-body schema from the catalogue's parameter list (shape and required flags only)."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in entry["params"]:
        catalogue_type = str(param["type"])
        node = _node(_TYPE_MAP.get(catalogue_type), catalogue_type)
        if param["required"]:
            required.append(param["name"])
        elif node:
            options = node["anyOf"] if "anyOf" in node else [node]
            node = {"anyOf": [*options, {"type": "null"}]}
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
    """The tools for one question, with a memory of what they returned.

    Attributes:
        calls: every call as {"name", "input", "ok"}.
        records: function name -> the record `get_function` returned.
        search_hits: function name -> summary, for every function `search_functions` returned.
        search_views: function name -> the full `hit_view` the model was shown for it.
        proposals: every `propose_parameters` call as {"name", "values", "ok"}.
    """

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
        self.search_views: dict[str, dict[str, str]] = {}
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
        """Up to SEARCH_LIMIT functions scored on name, display name, summary and description."""
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
            view = hit_view(self.entries[name])
            self.search_hits[name] = view["summary"]
            self.search_views[name] = view
            hits.append(view)
        return {"results": hits}

    def get_function(self, args: dict[str, Any]) -> dict[str, Any]:
        """The trimmed record of one function, by exact name."""
        name = str(args.get("name", ""))
        entry = self.entries.get(name)
        if entry is None:
            return {"error": "no function with that exact name; use search_functions"}
        record = trim_record(entry)
        self.records[name] = record
        return {"function": record}

    def propose_parameters(self, args: dict[str, Any]) -> dict[str, Any]:
        """Validate example values for one function; the model sees ok or the problems."""
        name, values = str(args.get("name", "")), args.get("values")
        entry = self.entries.get(name)
        if entry is None:
            return {"error": "no function with that exact name; use search_functions"}
        if not isinstance(values, dict):
            return {"error": "values must be an object of parameter name to value"}
        errors = validate(request_schema(entry), values) + bound_errors(entry, values)
        self.proposals.append({"name": name, "values": values, "ok": not errors})
        return {"ok": not errors, "errors": errors[:8]}

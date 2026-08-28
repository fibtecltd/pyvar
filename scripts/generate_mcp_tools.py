"""scripts/generate_mcp_tools.py — MCP tool catalogue generator for plugins/mcp/

Reasoning:
- portal/functions.json (385 entries) already carries everything an MCP tool
  needs per function: domain, name, the real API path, a description, and a
  params list with per-parameter type/required/default/description/min/max
  -- close enough to JSON Schema that this is a straight structural mapping,
  not free-form generation.
- Same generate-and-commit-and-CI-diff pattern as scripts/generate_plugins.py
  and pyvar-client/codegen/generate.py: the MCP server reads its tool
  catalogue from a plain committed Python module
  (plugins/mcp/pyvar_mcp/_generated/functions.py), not from a runtime fetch of
  functions.json -- a stdio MCP server subprocess shouldn't need network
  access just to know its own tool list, and this keeps the same
  never-drifts-from-committed-source property the skills plugins already
  have.
- Deliberately does NOT special-case the one async (submit/poll) endpoint
  the portal's homepage text +currently+ (inaccurately) claims all 385
  functions use: grep across api/routes/*.py confirms only api/routes/var.py
  (POST /api/v1/var/compute, a task_id + poll pattern) is actually async --
  every function actually catalogued in functions.json is a plain
  synchronous POST -> JSON response (api/routes/alm.py etc., confirmed by
  reading the generated routes directly), and that endpoint isn't itself one
  of the 385 catalogued entries. See docs/p10-skills-and-plugin-plan.md's
  §B.3 for the full note -- this generator, and the MCP client it feeds,
  only need to handle the synchronous case.

Usage:
  python3 scripts/generate_mcp_tools.py
"""

from __future__ import annotations

import json
import pprint
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_JSON = REPO_ROOT / "portal" / "functions.json"
OUTPUT_PATH = REPO_ROOT / "plugins" / "mcp" / "pyvar_mcp" / "_generated" / "functions.py"

# functions.json param fields that map directly onto JSON Schema keywords
# when not null. "type" and "required"/"default" are handled separately
# (type is always present; required feeds the schema's top-level "required"
# list; default becomes JSON Schema's own "default" keyword).
_SCHEMA_KEYWORD_FIELDS = (
    "description",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
)


def _param_to_schema_property(param: dict[str, Any]) -> dict[str, Any]:
    prop: dict[str, Any] = {"type": param["type"]}
    for field in _SCHEMA_KEYWORD_FIELDS:
        value = param.get(field)
        if value is not None:
            prop[field] = value
    if param.get("default") is not None:
        prop["default"] = param["default"]
    return prop


def _input_schema(params: list[dict[str, Any]]) -> dict[str, Any]:
    properties = {p["name"]: _param_to_schema_property(p) for p in params}
    required = [p["name"] for p in params if p.get("required")]
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _tool_entry(fn: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain": fn["domain"],
        "function_name": fn["name"],
        "tool_name": fn["name"],
        "path": fn["path"],
        "summary": fn["summary"],
        "description": fn["description"],
        "input_schema": _input_schema(fn["params"]),
    }


def main() -> None:
    functions = json.loads(FUNCTIONS_JSON.read_text())

    seen_tool_names: set[str] = set()
    entries = []
    for fn in functions:
        entry = _tool_entry(fn)
        if entry["tool_name"] in seen_tool_names:
            raise SystemExit(
                f"duplicate tool name {entry['tool_name']!r} across domains -- "
                "MCP tool names must be globally unique; functions.json needs a "
                "disambiguation strategy (e.g. domain-prefixed names) before this "
                "generator can proceed"
            )
        seen_tool_names.add(entry["tool_name"])
        entries.append(entry)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = (
        '"""plugins/mcp/pyvar_mcp/_generated/functions.py — GENERATED, do not edit by hand.\n\n'
        "Regenerate with: python3 scripts/generate_mcp_tools.py (from the repo root)\n"
        "Source: portal/functions.json -- see scripts/generate_mcp_tools.py for the mapping.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        "# Each entry: domain, function_name (== the API's function name), tool_name (the\n"
        "# MCP tool name -- currently identical to function_name; kept as a separate field\n"
        "# in case a future disambiguation strategy needs to diverge the two), path (the\n"
        "# real POST endpoint, relative to the API base URL), summary, description, and\n"
        "# input_schema (JSON Schema, mapped directly from functions.json's params list).\n"
        f"FUNCTIONS: list[dict[str, Any]] = {pprint.pformat(entries, indent=4, width=100)}\n"
    )
    OUTPUT_PATH.write_text(header)

    # black-format the output in place, same as pyvar-client/codegen/generate.py's
    # own last step -- keeps the committed generated file already-formatted
    # rather than relying on a manual `black .` follow-up someone forgets.
    subprocess.run(
        [sys.executable, "-m", "black", "--line-length", "100", str(OUTPUT_PATH)],
        check=True,
    )
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)} ({len(entries)} tools)")


if __name__ == "__main__":
    main()

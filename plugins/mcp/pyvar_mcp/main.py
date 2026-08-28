"""plugins/mcp/pyvar_mcp/main.py — pyvar MCP server entry point.

Reasoning:
- Thin wrapper over pyvar's own REST API (client.py) -- no vendored engine,
  see docs/p10-skills-and-plugin-plan.md §B.1 for why (compute logic must
  not be able to drift from what's actually deployed at pyvar.com).
- Every one of the 385 catalogued functions gets its own named tool
  (generated from functions.json, see pyvar_mcp/_generated/functions.py) PLUS
  two generic tools -- list_pyvar_functions and call_pyvar_function --
  positioned as the model's first choice ahead of hunting through 385 names
  (docs/p10-skills-and-plugin-plan.md §B.2). All three paths (a named tool,
  or call_pyvar_function's explicit domain+function_name) end up at the
  exact same _invoke() dispatch -- one implementation, not three.
- Uses mcp.server.lowlevel.Server directly (on_list_tools/on_call_tool
  constructor callbacks), not the higher-level FastMCP decorator style --
  confirmed by introspecting the actually-installed `mcp` package (not
  assumed from memory) that this is the real, current, supported way to
  register a large, programmatically-generated tool set without writing
  385 individual @mcp.tool()-decorated functions by hand.
- Errors (a pyvar API 4xx/5xx, an unknown tool/function name, a schema
  validation mismatch on call_pyvar_function's params) come back as
  CallToolResult(is_error=True, content=[...]) -- a normal tool result the
  calling model can read and relay, not a raised protocol-level exception
  that would look like this server itself is broken.
"""

from __future__ import annotations

import json
from typing import Any

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from . import catalogue
from .client import PyvarApiError, PyvarClient

SERVER_NAME = "pyvar-mcp"

_GENERIC_TOOL_PREAMBLE = (
    "Use this tool as your first choice for calling pyvar functions. Only "
    "reach for a specific named tool (e.g. compute_var) when you already "
    "know its exact parameters and want its precise per-parameter schema "
    "up front. "
)


def _list_pyvar_functions_tool() -> types.Tool:
    return types.Tool(
        name="list_pyvar_functions",
        description=(
            _GENERIC_TOOL_PREAMBLE
            + "Lists pyvar functions -- name, one-line summary, and required "
            "parameter names -- optionally filtered to one domain. Use this "
            "first when you don't already know a function's exact name."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Optional domain filter.",
                    "enum": catalogue.domains(),
                }
            },
        },
    )


def _call_pyvar_function_tool() -> types.Tool:
    return types.Tool(
        name="call_pyvar_function",
        description=(
            _GENERIC_TOOL_PREAMBLE + "Calls any pyvar function by domain and function name. "
            "Validates params against the function's own schema before "
            "calling the API, and returns a clear error naming the expected "
            "parameters on a mismatch."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "enum": catalogue.domains()},
                "function_name": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["domain", "function_name", "params"],
        },
    )


def _named_tool(entry: dict[str, Any]) -> types.Tool:
    return types.Tool(
        name=entry["tool_name"],
        description=f"{entry['summary']}\n\n{entry['description']}",
        input_schema=entry["input_schema"],
    )


def _error_result(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)],
        is_error=True,
    )


def _success_result(data: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(data, indent=2))],
    )


def _validate_required_params(entry: dict[str, Any], params: dict[str, Any]) -> str | None:
    """Returns an error message if params is missing a required field, else None.

    Deliberately shallow (presence only, not type checking) -- the pyvar API
    itself is the authority on full parameter validation (Pydantic v2, same
    422 responses every other pyvar client sees); this check exists only to
    give call_pyvar_function's necessarily-loose params:object typing a
    clearer first-pass error than a raw API 422 would.
    """
    required = entry["input_schema"].get("required", [])
    missing = [name for name in required if name not in params]
    if missing:
        expected = ", ".join(entry["input_schema"]["properties"].keys())
        return (
            f"Missing required parameter(s) for {entry['tool_name']}: {', '.join(missing)}. "
            f"Expected params: {expected}."
        )
    return None


def _invoke(
    client: PyvarClient, entry: dict[str, Any], params: dict[str, Any]
) -> types.CallToolResult:
    error = _validate_required_params(entry, params)
    if error is not None:
        return _error_result(error)
    try:
        result = client.call_function(entry["path"], params)
    except PyvarApiError as exc:
        return _error_result(f"pyvar API error (HTTP {exc.status_code}): {exc.body}")
    return _success_result(result)


def build_server() -> Server:
    client = PyvarClient.from_env()

    async def handle_list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        tools = [_list_pyvar_functions_tool(), _call_pyvar_function_tool()]
        tools.extend(_named_tool(entry) for entry in catalogue.all_functions())
        return types.ListToolsResult(tools=tools)

    async def handle_call_tool(
        ctx: Any, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        name = params.name
        arguments = params.arguments or {}

        if name == "list_pyvar_functions":
            domain = arguments.get("domain")
            entries = catalogue.in_domain(domain) if domain else catalogue.all_functions()
            listing = [
                {
                    "domain": e["domain"],
                    "function_name": e["function_name"],
                    "summary": e["summary"],
                    "required_params": e["input_schema"].get("required", []),
                }
                for e in entries
            ]
            return _success_result({"functions": listing})

        if name == "call_pyvar_function":
            domain = arguments.get("domain")
            function_name = arguments.get("function_name")
            call_params = arguments.get("params", {})
            entry = catalogue.by_domain_and_function(domain, function_name)
            if entry is None:
                return _error_result(
                    f"Unknown function {function_name!r} in domain {domain!r}. "
                    "Use list_pyvar_functions to see valid names."
                )
            return _invoke(client, entry, call_params)

        entry = catalogue.by_tool_name(name)
        if entry is None:
            return _error_result(f"Unknown tool: {name!r}")
        return _invoke(client, entry, arguments)

    return Server(SERVER_NAME, on_list_tools=handle_list_tools, on_call_tool=handle_call_tool)


async def _amain() -> None:
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    anyio.run(_amain)


if __name__ == "__main__":
    main()

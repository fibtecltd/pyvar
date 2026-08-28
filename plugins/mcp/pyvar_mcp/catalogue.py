"""plugins/mcp/pyvar_mcp/catalogue.py — lookup helpers over the generated tool list.

Reasoning:
- pyvar_mcp/_generated/functions.py is a flat list (matching functions.json's
  own shape); this module builds the indexes both main.py's list_tools/
  call_tool handlers and the generic call_pyvar_function/list_pyvar_functions
  tools need, in one place, so there's exactly one "how do I find a function
  by name" implementation rather than several ad hoc ones.
"""

from __future__ import annotations

from typing import Any

from ._generated.functions import FUNCTIONS

_BY_TOOL_NAME: dict[str, dict[str, Any]] = {entry["tool_name"]: entry for entry in FUNCTIONS}
_BY_DOMAIN_AND_FUNCTION: dict[tuple[str, str], dict[str, Any]] = {
    (entry["domain"], entry["function_name"]): entry for entry in FUNCTIONS
}
_DOMAINS: list[str] = sorted({entry["domain"] for entry in FUNCTIONS})


def all_functions() -> list[dict[str, Any]]:
    return FUNCTIONS


def domains() -> list[str]:
    return _DOMAINS


def by_tool_name(tool_name: str) -> dict[str, Any] | None:
    return _BY_TOOL_NAME.get(tool_name)


def by_domain_and_function(domain: str, function_name: str) -> dict[str, Any] | None:
    return _BY_DOMAIN_AND_FUNCTION.get((domain, function_name))


def in_domain(domain: str) -> list[dict[str, Any]]:
    return [entry for entry in FUNCTIONS if entry["domain"] == domain]

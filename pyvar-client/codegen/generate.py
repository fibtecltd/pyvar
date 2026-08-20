#!/usr/bin/env python3
"""codegen/generate.py — generates pyvar_client/_generated/*.py from the live API.

Reasoning:
- 385 functions across 8 domains is its own maintenance burden to
  hand-write, and the fastest way for this client to silently drift from
  the API (see docs/p9-function-catalogue-reconciliation.md in the main
  repo for a real instance of exactly this drift, in
  pyvar_functions.csv vs. the live catalogue -- the reason this script
  exists instead of a hand-maintained module per domain).
- Reads TWO sources, not one: main.create_app().openapi() for the
  authoritative request schema (param names/types/requiredness -- this is
  what generates correct Python signatures), and portal/functions.json for
  display metadata (domain grouping, function display name, summary/
  description) -- functions.json's own `type` field is a lossy
  simplification (falls back to "object" for any anyOf union it can't
  flatten -- see scripts/generate_function_catalog.py:_extract_params),
  so param typing here comes from the OpenAPI schema directly, not
  functions.json.
- No nested $ref inside any Request schema's properties as of this
  writing (verified directly against the live schema before writing this
  resolver) -- every param is a primitive, an array of primitives, or an
  anyOf of those. If a future function ever adds a genuinely nested
  request model, _resolve_type below falls back to "Any" rather than
  guessing at a wrong type -- regenerate and spot-check the diff when
  that happens.
- Every generated method takes keyword-only arguments (a bare `*` right
  after self) specifically so required and optional (defaulted) params
  can be declared in their natural schema order -- Python's "no default
  before non-default" rule only applies to positional-or-keyword
  parameters, not keyword-only ones.
- Every param (required or defaulted) is always sent in the request body,
  even when the caller didn't override an optional one -- simpler
  codegen than conditionally omitting unset optional fields, and no
  behavior difference: an omitted optional field would just get the same
  default value server-side anyway.

Run: python3 codegen/generate.py
(from pyvar-client/, with the main repo's dependencies installed --
imports main.create_app() directly, so it needs the full app import graph,
not just this package's own runtime deps.)
"""

from __future__ import annotations

import json
import keyword
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = Path(__file__).resolve().parents[1] / "pyvar_client" / "_generated"

# functions.json's `domain` slug -> (module filename stem, Namespace class name)
_DOMAIN_TARGETS: dict[str, tuple[str, str]] = {
    "alm": ("alm", "AlmNamespace"),
    "credit-risk": ("credit_risk", "CreditRiskNamespace"),
    "derivatives": ("derivatives", "DerivativesNamespace"),
    "liquidity": ("liquidity", "LiquidityNamespace"),
    "market-risk": ("market_risk", "MarketRiskNamespace"),
    "operational": ("operational", "OperationalNamespace"),
    "portfolio": ("portfolio", "PortfolioNamespace"),
    "regulatory": ("regulatory", "RegulatoryNamespace"),
}


def _resolve_type(schema: dict[str, Any]) -> str:
    """JSON Schema fragment -> a Python type-hint string. See module docstring."""
    if "anyOf" in schema:
        members = [s for s in schema["anyOf"] if s.get("type") != "null"]
        has_null = len(members) != len(schema["anyOf"])
        seen: list[str] = []
        for member in members:
            t = _resolve_type(member)
            if t not in seen:
                seen.append(t)
        if not seen:
            return "Any"
        if has_null:
            seen.append("None")
        return " | ".join(seen)

    t = schema.get("type")
    if t == "array":
        return f"list[{_resolve_type(schema.get('items', {}))}]"
    if t == "number":
        return "float"
    if t == "integer":
        return "int"
    if t == "string":
        return "str"
    if t == "boolean":
        return "bool"
    if t == "object":
        return "dict[str, Any]"
    return "Any"


def _safe_param_name(name: str) -> str:
    """Trailing underscore for the rare param name that collides with a
    Python keyword/builtin -- none exist as of this writing (checked), but
    codegen should not silently produce invalid Python if one is ever
    added."""
    if keyword.iskeyword(name) or name in {"self", "type", "id"}:
        return f"{name}_"
    return name


def _extract_params(request_schema: dict[str, Any]) -> list[dict[str, Any]]:
    props = request_schema.get("properties", {})
    required = set(request_schema.get("required", []))
    params = []
    for field_name, field_schema in props.items():
        params.append(
            {
                "name": field_name,
                "py_name": _safe_param_name(field_name),
                "py_type": _resolve_type(field_schema),
                "required": field_name in required,
                "default": field_schema.get("default"),
            }
        )
    # Required params first, then optional -- cosmetic only (both groups
    # are keyword-only, see module docstring), but reads more naturally in
    # generated signatures and matches the schema's own declared order
    # within each group.
    return sorted(params, key=lambda p: not p["required"])


def _format_default(value: Any) -> str:
    return repr(value)


def _docstring(summary: str, description: str | None) -> str:
    lines = [summary.strip()]
    if description and description.strip():
        lines.append("")
        lines.extend(line.rstrip() for line in description.strip().splitlines())
    lines.append("")
    lines.append("Returns:")
    lines.append("    The raw API response as a dict.")
    body = "\n    ".join(lines)
    return f'"""{body}\n    """'


def _method_source(fn: dict[str, Any], request_schema: dict[str, Any]) -> str:
    params = _extract_params(request_schema)

    sig_parts = ["self", "*"]
    for p in params:
        if p["required"]:
            sig_parts.append(f"{p['py_name']}: {p['py_type']}")
        else:
            sig_parts.append(f"{p['py_name']}: {p['py_type']} = {_format_default(p['default'])}")
    signature = ", ".join(sig_parts)

    body_entries = ", ".join(f'"{p["name"]}": {p["py_name"]}' for p in params)
    docstring = _docstring(fn["summary"], fn.get("description"))

    return (
        f"    def {fn['name']}({signature}) -> dict[str, Any]:\n"
        f"        {docstring}\n"
        f"        body = {{{body_entries}}}\n"
        f'        return self._client._request("POST", "{fn["path"]}", json_body=body)\n'
    )


def _module_source(class_name: str, functions: list[dict[str, Any]], schemas: dict) -> str:
    header = (
        '"""Generated by codegen/generate.py -- DO NOT EDIT BY HAND.\n\n'
        "Regenerate with `python3 codegen/generate.py` from pyvar-client/ after any\n"
        "change to the API's request schemas. See that script's own module\n"
        'docstring for what "generated" means here and why.\n'
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import TYPE_CHECKING, Any\n\n"
        "if TYPE_CHECKING:\n"
        "    from pyvar_client._client import Client\n\n\n"
        f"class {class_name}:\n"
        f'    """Generated methods for this domain -- see pyvar_client._generated\'s\n'
        f'    own module docstring."""\n\n'
        f'    def __init__(self, client: "Client") -> None:\n'
        f"        self._client = client\n\n"
    )
    methods = []
    for fn in sorted(functions, key=lambda f: f["name"]):
        op = schemas["paths"][fn["path"]]["post"]
        request_ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        request_schema_name = request_ref.rsplit("/", 1)[-1]
        request_schema = schemas["components"]["schemas"][request_schema_name]
        methods.append(_method_source(fn, request_schema))
    return header + "\n".join(methods)


def generate() -> None:
    from main import create_app  # noqa: E402 -- needs sys.path insert above first

    app = create_app()
    schema = app.openapi()

    catalog = json.loads((REPO_ROOT / "portal" / "functions.json").read_text())
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for fn in catalog:
        by_domain.setdefault(fn["domain"], []).append(fn)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    init_lines = ['"""Generated per-domain namespaces -- see codegen/generate.py."""\n']

    total = 0
    for domain_slug, (module_stem, class_name) in _DOMAIN_TARGETS.items():
        functions = by_domain.get(domain_slug, [])
        if not functions:
            raise RuntimeError(f"No functions found for domain {domain_slug!r} -- catalog stale?")
        source = _module_source(class_name, functions, schema)
        (OUT_DIR / f"{module_stem}.py").write_text(source)
        init_lines.append(f"from pyvar_client._generated.{module_stem} import {class_name}\n")
        total += len(functions)
        print(f"{domain_slug}: {len(functions)} methods -> {module_stem}.py")

    init_lines.append("\n__all__ = [\n")
    for _, class_name in _DOMAIN_TARGETS.values():
        init_lines.append(f'    "{class_name}",\n')
    init_lines.append("]\n")
    (OUT_DIR / "__init__.py").write_text("".join(init_lines))

    # Codegen emits syntactically valid but single-line-signature Python
    # (see _method_source) -- black is what makes the generated files
    # actually readable. Run it here so every regeneration is
    # already-formatted, not a manual follow-up step someone forgets.
    subprocess.run(
        [sys.executable, "-m", "black", "--line-length", "100", str(OUT_DIR)],
        check=True,
    )

    print(f"Total: {total} methods across {len(_DOMAIN_TARGETS)} domains.")


if __name__ == "__main__":
    generate()

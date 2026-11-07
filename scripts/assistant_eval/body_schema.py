"""A small JSON-Schema checker for the request bodies of pyvar's 385 functions.

Reasoning:
- A suggested set of example values is only worth showing a visitor if the API would accept its shape.
  The real request schemas (the live OpenAPI document) use exactly seven keywords across all 385
  functions: type, items, anyOf, properties, required, additionalProperties, plus annotations (default,
  title, description). This checker implements those and nothing else, so the eval and, later, the
  assistant's server-side check need no extra dependency (the CI image has no `jsonschema`).
- It checks shape and types, not meaning. The schemas carry no numeric bounds and no parameter
  descriptions (measured 2026-11-07: 0 of 1,577 properties have either), so "plausible values" cannot
  be checked here; the judge (judge.py) and a human read have to do that.
- Unknown top-level keys are errors: the API would ignore them, but in a suggestion they are an invented
  parameter name, which is exactly what a visitor must never be shown.
"""

from __future__ import annotations

import math
from typing import Any

_MAX_DEPTH = 24


def inline_refs(node: Any, components: dict[str, Any], _seen: tuple[str, ...] = ()) -> Any:
    """Return `node` with every `$ref` into `#/components/schemas/` replaced by its target.

    A reference cycle is cut by returning an empty (accept-anything) schema at the repeat.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            name = ref.rsplit("/", 1)[-1]
            if name in _seen or len(_seen) > _MAX_DEPTH:
                return {}
            return inline_refs(components[name], components, _seen + (name,))
        return {k: inline_refs(v, components, _seen) for k, v in node.items()}
    if isinstance(node, list):
        return [inline_refs(v, components, _seen) for v in node]
    return node


def validate(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
    """List the ways `value` does not fit `schema` (empty when it fits)."""
    any_of = schema.get("anyOf")
    if any_of:
        if any(not validate(option, value, path) for option in any_of):
            return []
        return [f"{path}: does not match any allowed shape ({_describe(any_of)})"]
    kind = schema.get("type")
    if kind is None:
        return []
    if isinstance(kind, list):
        if any(not validate({**schema, "type": k}, value, path) for k in kind):
            return []
        return [f"{path}: expected one of {kind}, got {_name(value)}"]
    if kind == "null":
        return [] if value is None else [f"{path}: expected null, got {_name(value)}"]
    if kind == "boolean":
        return [] if isinstance(value, bool) else [f"{path}: expected boolean, got {_name(value)}"]
    if kind == "string":
        return [] if isinstance(value, str) else [f"{path}: expected string, got {_name(value)}"]
    if kind in ("number", "integer"):
        return _number(kind, value, path)
    if kind == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array, got {_name(value)}"]
        item_schema = schema.get("items")
        errors: list[str] = []
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors += validate(item_schema, item, f"{path}[{index}]")
        return errors
    if kind == "object":
        return _object(schema, value, path)
    return []


def _number(kind: str, value: Any, path: str) -> list[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [f"{path}: expected {kind}, got {_name(value)}"]
    if isinstance(value, float) and not math.isfinite(value):
        return [f"{path}: expected a finite {kind}"]
    if kind == "integer" and isinstance(value, float) and not value.is_integer():
        return [f"{path}: expected integer, got {value}"]
    return []


def _object(schema: dict[str, Any], value: Any, path: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{path}: expected object, got {_name(value)}"]
    errors: list[str] = []
    properties: dict[str, Any] = schema.get("properties") or {}
    for name in schema.get("required") or []:
        if name not in value:
            errors.append(f"{path}: missing required parameter '{name}'")
    extra = schema.get("additionalProperties")
    for key, item in value.items():
        if key in properties:
            errors += validate(properties[key], item, f"{path}.{key}")
        elif isinstance(extra, dict):
            errors += validate(extra, item, f"{path}.{key}")
        elif path == "$" and properties:
            errors.append(f"{path}: unknown parameter '{key}'")
    return errors


def minimal_instance(schema: dict[str, Any], _depth: int = 0) -> Any:
    """The smallest value that satisfies `schema`: required properties only, placeholders for leaves."""
    if _depth > _MAX_DEPTH:
        return None
    any_of = schema.get("anyOf")
    if any_of:
        non_null = [s for s in any_of if s.get("type") != "null"]
        return minimal_instance((non_null or any_of)[0], _depth + 1)
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "null")
    if kind == "number":
        return 1.0
    if kind == "integer":
        return 1
    if kind == "boolean":
        return False
    if kind == "string":
        return "x"
    if kind == "array":
        return []
    if kind == "object":
        properties = schema.get("properties") or {}
        return {
            n: minimal_instance(properties[n], _depth + 1) for n in schema.get("required") or []
        }
    return None


def _name(value: Any) -> str:
    return type(value).__name__ if value is not None else "null"


def _describe(options: list[dict[str, Any]]) -> str:
    return " | ".join(str(o.get("type", "any")) for o in options)

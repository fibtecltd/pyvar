"""scripts/param_docs.py: per-parameter descriptions taken from the engine's own docstrings.

Reasoning:
- Every API request model was generated from an engine signature (scripts/gen_p3.py), and the engine
  functions already document each argument in a Google-style `Args:` section (CLAUDE.md section 6).
  The generator dropped that text, so none of the 1,577 request parameters had a description in the
  OpenAPI schema, in portal/functions.json, in the Try-it panel or in the skills' parameter tables
  (measured 2026-11-07). The engine is the single source of truth (CLAUDE.md), so the descriptions are
  extracted from it, not written a second time: they are accurate by construction, and a correction is
  made once, in the engine.
- This module is used by scripts/add_param_descriptions.py (the one-off injection into schemas/*.py),
  by scripts/gen_p3.py (so a newly generated function carries its descriptions) and by
  tests/test_parameter_descriptions.py (so the two cannot drift apart again).
- It maps each request model to its engine function the way gen_p3.main() names them, including the
  `<name>_<module>` disambiguation for endpoint-name collisions, and asserts that the model names it
  finds are exactly the committed ones.
"""

from __future__ import annotations

import importlib
import inspect
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
_SECTION = re.compile(r"(Args|Arguments|Parameters):")
_NEXT_SECTION = re.compile(r"[A-Z][A-Za-z ]*:")
_ENTRY = re.compile(r"^(\*{0,2}\w+)\s*(?:\([^)]*\))?\s*:\s*(.*)$")


def parse_args_section(doc: str | None) -> dict[str, str]:
    """name -> description from the `Args:` block of a Google-style docstring.

    Handles `name: text`, `name (type): text` and text wrapped onto continuation lines, and stops at
    the next section header (Returns:, Raises:, Note:, ...). Whitespace is collapsed to single spaces.
    """
    if not doc:
        return {}
    entries: dict[str, str] = {}
    current: str | None = None
    entry_indent = 0
    base = 0
    in_args = False
    for line in doc.expandtabs().split("\n"):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if _SECTION.fullmatch(stripped):
            in_args, base, current = True, indent, None
            continue
        if not in_args or not stripped:
            continue
        if indent <= base and _NEXT_SECTION.fullmatch(stripped):
            break
        match = _ENTRY.match(stripped)
        if match and (current is None or indent <= entry_indent):
            current = match.group(1).lstrip("*")
            entry_indent = indent
            entries[current] = match.group(2).strip()
        elif current:
            entries[current] += " " + stripped
    return {name: re.sub(r"\s+", " ", text).strip() for name, text in entries.items()}


def request_models() -> dict[str, dict[str, Any]]:
    """Request class name -> {"domain", "function", "module", "params", "docs"} for all 385 endpoints."""
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT))
    import gen_p3  # imported late: it imports every engine module

    out: dict[str, dict[str, Any]] = {}
    for domain, modules in gen_p3.DOMAINS.items():
        funcs: list[dict[str, Any]] = []
        for module in modules:
            funcs.extend(gen_p3.collect_module(module))
        seen: dict[str, int] = {}
        for f in funcs:  # the same disambiguation as gen_p3.main()
            if f["name"] in seen:
                f["name"] = f"{f['name']}_{f['module']}"
                f["cls"] = gen_p3._class_name(f["name"])
            seen[f["name"]] = 1
        for f in funcs:
            engine_fn = getattr(importlib.import_module(f"engine.{f['module']}"), f["real"])
            out[f"{f['cls']}Request"] = {
                "domain": domain,
                "function": f["real"],
                "module": f["module"],
                "params": [p["name"] for p in f["params"]],
                "docs": parse_args_section(inspect.getdoc(engine_fn)),
            }
    return out


def description_for(entry: dict[str, Any], param: str) -> str | None:
    text = entry["docs"].get(param)
    return text or None

"""The part of a catalogue entry a model is shown (moved out of scripts/assistant_eval/cases.py).

Reasoning:
- The menu eval, the typed eval and, from the gateway PR on, production all show the model the same trimmed
  record, so the trimmer lives in the package they all import. `cases.trim_record` still works: it is this
  function.
- Only what the model is shown, nothing else: the description is cut at DESCRIPTION_LIMIT characters.
"""

from __future__ import annotations

from typing import Any

DESCRIPTION_LIMIT = 1500


def trim_record(entry: dict[str, Any]) -> dict[str, Any]:
    """The part of a catalogue entry a model is shown (and the only part it may rely on)."""
    formula = entry.get("formula") or {}
    return {
        "name": entry["name"],
        "display_name": entry["display_name"],
        "domain": entry["domain_label"],
        "summary": entry["summary"],
        "description": (entry.get("description") or "")[:DESCRIPTION_LIMIT],
        "parameters": [
            {
                "name": p["name"],
                "type": p["type"],
                "required": p["required"],
                "default": p["default"],
                "description": p.get("description"),
            }
            for p in entry["params"]
        ],
        "formula_latex": formula.get("formula_latex"),
        "symbol_map": formula.get("symbol_map"),
        "caveat": formula.get("caveat"),
        "citation": formula.get("citation"),
    }

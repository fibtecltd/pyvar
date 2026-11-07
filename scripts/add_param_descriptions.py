"""scripts/add_param_descriptions.py: put each engine argument's docstring text on its request field.

Reasoning:
- schemas/*.py were generated from engine signatures, then edited by hand, so regenerating them with
  scripts/gen_p3.py would overwrite those edits (measured 2026-11-07: after formatting, 10 files and about
  90 lines differ). This tool instead rewrites only the field lines of the existing request models,
  changing `name: type` to `name: type = Field(description=...)` and `name: type = default` to
  `name: type = Field(default=default, description=...)`. Nothing else in a file is touched.
- The text comes from the engine docstrings (scripts/param_docs.py), the single source of truth.
- It is description-only. No bound, validator or type changes: the live OpenAPI document must come out
  identical except for the added `description` keys, which was checked by diffing the document before and
  after (see the PR). Fields that already use Field(...) are left alone, so the tool is idempotent.
- A field with no engine text is skipped and reported; a model field the engine does not have, or the other
  way round (liquidity_gap_analysis's `opening_balance`), is reported, not "fixed".

Usage (needs the project environment):
    PYTHONPATH=. APP_ENV=test python scripts/add_param_descriptions.py [--dry-run]
    black --line-length 100 schemas && isort schemas
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import param_docs

DOMAIN_FILES = (
    "alm",
    "credit_risk",
    "derivatives",
    "liquidity",
    "market_risk",
    "operational",
    "portfolio",
    "regulatory",
)


def rewrite_source(
    source: str, models: dict[str, dict[str, Any]]
) -> tuple[str, int, list[tuple[str, str, str]]]:
    """Return (new source, number of fields changed, [(class, field, reason)] for fields not changed)."""
    tree = ast.parse(source)
    lines = source.split("\n")
    edits: list[tuple[int, int, str]] = []
    skipped: list[tuple[str, str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in models:
            continue
        entry = models[node.name]
        for stmt in node.body:
            if not (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)):
                continue
            name = stmt.target.id
            if isinstance(stmt.value, ast.Call) and getattr(stmt.value.func, "id", "") == "Field":
                skipped.append((node.name, name, "already uses Field()"))
                continue
            description = param_docs.description_for(entry, name)
            if description is None:
                skipped.append((node.name, name, "no engine docstring text"))
                continue
            annotation = ast.get_source_segment(source, stmt.annotation)
            default = None if stmt.value is None else ast.get_source_segment(source, stmt.value)
            args = [] if default is None else [f"default={default}"]
            args.append(f"description={json.dumps(description, ensure_ascii=False)}")
            new = f"    {name}: {annotation} = Field({', '.join(args)})"
            assert stmt.end_lineno is not None
            edits.append((stmt.lineno, stmt.end_lineno, new))
    for start, end, new in sorted(edits, reverse=True):
        lines[start - 1 : end] = [new]
    return "\n".join(lines), len(edits), skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = parser.parse_args()
    models = param_docs.request_models()
    changed = 0
    skipped_all: list[tuple[str, str, str]] = []
    for domain in DOMAIN_FILES:
        path = ROOT / "schemas" / f"{domain}.py"
        new_source, count, skipped = rewrite_source(path.read_text(), models)
        changed += count
        skipped_all += skipped
        if not args.dry_run:
            path.write_text(new_source)
        print(f"{path.relative_to(ROOT)}: {count} fields described")
    print(f"TOTAL: {changed} fields described; {len(skipped_all)} left as they were")
    for cls, field_name, reason in skipped_all:
        if reason != "already uses Field()":
            print(f"  skipped {cls}.{field_name}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

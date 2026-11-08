"""Re-grade a finished run's saved answers with the current graders. No API call, no cost.

Reasoning:
- A grader fix changes which answers pass, but the answers cost money to make. The 2026-11-08 fix (names
  written inside LaTeX formulas) was first counted by arithmetic from a failure list; this tool measures it
  instead: it grades each saved reply again and reports the pass rate per action before (what results.jsonl
  recorded) and after, every answer whose verdict changed, and every answer that still fails with the checks
  and flags that fail it.
- It reads results.jsonl and never writes to the run directory.

Usage:
    python scripts/assistant_eval/regrade.py --cases CASES --run DIR [--only explain,when,compare]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from graders import grade  # noqa: E402


def regrade(
    cases: dict[str, dict[str, Any]], rows: list[dict[str, Any]], only: set[str] | None = None
) -> dict[str, Any]:
    """Per-action counts before and after, the answers whose verdict changed, and those still failing."""
    per_action: dict[str, dict[str, int]] = {}
    changed: list[dict[str, Any]] = []
    failing: list[dict[str, Any]] = []
    for row in rows:
        if row["status"] != "ok" or (only and row["intent"] not in only):
            continue
        before = bool(row["grade"]["passed"])
        after = grade(cases[row["case_id"]], row["text"])
        entry = per_action.setdefault(
            row["intent"], {"n": 0, "passed_before": 0, "passed_after": 0}
        )
        entry["n"] += 1
        entry["passed_before"] += before
        entry["passed_after"] += after.passed
        if before != after.passed:
            changed.append(
                {"case_id": row["case_id"], "action": row["intent"], "now_passes": after.passed}
            )
        if not after.passed:
            failed = sorted(name for name, ok in after.checks.items() if not ok)
            failing.append(
                {
                    "case_id": row["case_id"],
                    "action": row["intent"],
                    "failed_checks": failed,
                    "flags": after.flags,
                    "chars": len(row["text"].strip()),
                }
            )
    return {"per_action": per_action, "changed": changed, "still_failing": failing}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument(
        "--run", required=True, type=Path, help="a run directory made by run_eval.py"
    )
    parser.add_argument("--only", default=None, help="comma-separated actions to re-grade")
    args = parser.parse_args()
    cases = {c["id"]: c for c in map(json.loads, args.cases.read_text().splitlines()) if c}
    rows = [
        json.loads(line) for line in (args.run / "results.jsonl").read_text().splitlines() if line
    ]
    only = {a.strip() for a in args.only.split(",") if a.strip()} if args.only else None
    print(json.dumps(regrade(cases, rows, only), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Compare a bank after `assistant.bank build --redo-ids` with the bank it started from.

Reasoning:
- A redo must touch only the answers it names and must never make one worse. This script checks both on the
  files: every answer outside the redo file is identical to the old bank (read with `git show <ref>`), and for
  each redo answer it says whether the text changed, where it came from now, how many tries it took, and how
  the gate's notes and the length moved.
- It prints counts and ids, never an answer. Gate notes are about an answer, so they are printed (cut to
  200 characters) only for a redo answer that still has some, and only with --show-notes.
- Run from the repository root: python scripts/assistant_eval/bank_redo_report.py --old-ref b64daae
  --redo docs/assistant-bank-redo-1.json [--bank portal/assistant/bank] [--json out.json] [--show-notes]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

BANK_PATH = "portal/assistant/bank"


def git_show(ref: str, path: str) -> dict[str, Any]:
    """A JSON file as it was at `ref`."""
    done = subprocess.run(
        ["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=True
    )
    loaded: dict[str, Any] = json.loads(done.stdout)
    return loaded


def flatten(function: str, body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{answer id: entry} for one function file."""
    entries = {f"{function}:{a}": body[a] for a in ("explain", "when") if a in body}
    for sibling, entry in (body.get("compare") or {}).items():
        entries[f"{function}:compare:{sibling}"] = entry
    return entries


def main(argv: list[str] | None = None) -> int:
    """Print the comparison; return 0 only if no answer outside the redo file changed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--old-ref", required=True, help="the git ref that holds the bank it started from"
    )
    parser.add_argument("--redo", type=Path, required=True)
    parser.add_argument("--bank", type=Path, default=Path(BANK_PATH))
    parser.add_argument(
        "--json", type=Path, default=None, help="also write the numbers here (no text)"
    )
    parser.add_argument("--show-notes", action="store_true")
    args = parser.parse_args(argv)

    redo = set(json.loads(args.redo.read_text()))
    manifest = json.loads((args.bank / "manifest.json").read_text())
    version = manifest["bank_version"]
    rows: list[dict[str, Any]] = []
    outside_changed: list[str] = []
    seen = 0
    for path in sorted((args.bank / version).glob("*.json")):
        function = path.stem
        new = flatten(function, json.loads(path.read_text()))
        old = flatten(function, git_show(args.old_ref, f"{BANK_PATH}/{version}/{path.name}"))
        for answer_id, entry in new.items():
            seen += 1
            before = old.get(answer_id)
            if answer_id not in redo:
                if entry != before:
                    outside_changed.append(answer_id)
                continue
            assert before is not None, answer_id
            rows.append(
                {
                    "id": answer_id,
                    "changed": entry["text"] != before["text"],
                    "source": [before["source"], entry["source"]],
                    "tries": [before["tries"], entry["tries"]],
                    "escalated": [before["escalated"], entry["escalated"]],
                    "notes": [len(before["gate"]["issues"]), len(entry["gate"]["issues"])],
                    "length": [len(before["text"]), len(entry["text"])],
                    "faithful": entry["gate"]["faithful"],
                    "issues": [str(i)[:200] for i in entry["gate"]["issues"]],
                }
            )
    missing = sorted(redo - {r["id"] for r in rows})
    changed = [r for r in rows if r["changed"]]
    summary = {
        "bank_version": version,
        "entries": seen,
        "redo_ids": len(redo),
        "redo_found": len(rows),
        "changed": len(changed),
        "unchanged": len(rows) - len(changed),
        "now_static": sum(1 for r in rows if r["source"][1] == "static"),
        "now_not_faithful": sum(1 for r in rows if r["faithful"] is False),
        "gate_notes_before": sum(r["notes"][0] for r in rows),
        "gate_notes_after": sum(r["notes"][1] for r in rows),
        "with_notes_after": sum(1 for r in rows if r["notes"][1] > 0),
        "tries_histogram_after": {
            str(t): sum(1 for r in rows if r["tries"][1] == t) for t in (1, 2, 3)
        },
        "escalated_after": sum(1 for r in rows if r["escalated"][1]),
        "mean_length_before": round(sum(r["length"][0] for r in rows) / max(1, len(rows)), 1),
        "mean_length_after": round(sum(r["length"][1] for r in rows) / max(1, len(rows)), 1),
        "longest_after": max((r["length"][1] for r in rows), default=0),
        "outside_changed": outside_changed,
        "redo_ids_not_in_bank": missing,
    }
    print(json.dumps(summary, indent=1))
    for r in rows:
        if not r["changed"]:
            print("UNCHANGED", r["id"], "source", r["source"], "tries", r["tries"])
        elif r["notes"][1] and args.show_notes:
            print("NOTES", r["id"], " | ".join(r["issues"]))
    if args.json is not None:
        args.json.write_text(
            json.dumps({"summary": summary, "rows": [{**r, "issues": []} for r in rows]}, indent=1)
            + "\n"
        )
    return 0 if not outside_changed and not missing else 1


if __name__ == "__main__":
    sys.exit(main())

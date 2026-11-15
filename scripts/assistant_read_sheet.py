#!/usr/bin/env python3
"""Draw a random sample of served assistant answers and write a sheet for a person to read.

This is the read that `docs/assistant-plan-implementation.md` (section 12) asks for before a bank release:
a person checks a random sample of the served answers against the catalogue. No model is called, nothing is
sent anywhere, and the draw is reproducible from the seed and the committed bank.

Reasoning (why the sheet looks the way it does; the first sheet, results 9.37, taught this):
- Every function an answer names (its own, the one a comparison is against, and any other function it points
  to in a backticked name) is shown with its FULL catalogue record, not a summary. A claim about a related
  function can only be checked if its record is on the sheet.
- The marks separate "the record contradicts it" from "the record does not say". The first sheet merged them,
  and three answers that were true but unsupported by the record were counted as wrong. The author then checks
  every "not in the record" mark against the engine, so the two kinds are reported separately.
- A draw can exclude answers already read (`--exclude-ids`), so two reads add up to one larger sample.

Usage:
    python scripts/assistant_read_sheet.py --seed 20261132 --n 40 \
        --exclude-ids docs/assistant-bank-read-1-ids.json --out /tmp/bank-read-2.md
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from assistant.records import DESCRIPTION_LIMIT  # noqa: E402  (the cut-off the writer was shown)

BANK_DIR = ROOT / "portal" / "assistant" / "bank"
CATALOGUE = ROOT / "portal" / "functions.json"
NAME_IN_BACKTICKS = re.compile(r"`([a-z0-9_]+)`")


def answer_id(function: str, action: str, sibling: str | None) -> str:
    """The id of one served answer, for example `fn:explain` or `fn:compare:other_fn`."""
    return f"{function}:{action}:{sibling}" if sibling else f"{function}:{action}"


def load_bank() -> tuple[str, dict[str, dict[str, Any]]]:
    """Return the bank version and `{function: file content}` for every served answer."""
    manifest = json.loads((BANK_DIR / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["bank_version"]
    files = sorted((BANK_DIR / version).glob("*.json"))
    return version, {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in files}


def load_catalogue() -> dict[str, dict[str, Any]]:
    """Return `{function name: catalogue entry}`."""
    entries = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    return {e["name"]: e for e in entries}


def answer_pool(bank: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every served answer by id, with its function, action and sibling."""
    pool: dict[str, dict[str, Any]] = {}
    for function, content in bank.items():
        for action in ("explain", "when"):
            pool[answer_id(function, action, None)] = {
                "function": function,
                "action": action,
                "sibling": None,
                "entry": content[action],
            }
        for sibling, entry in (content.get("compare") or {}).items():
            pool[answer_id(function, "compare", sibling)] = {
                "function": function,
                "action": "compare",
                "sibling": sibling,
                "entry": entry,
            }
    return pool


def named_functions(item: dict[str, Any], catalogue: dict[str, dict[str, Any]]) -> list[str]:
    """Functions other than the answer's own that it names: its sibling and any backticked catalogue name."""
    names: list[str] = []
    if item["sibling"]:
        names.append(item["sibling"])
    for name in NAME_IN_BACKTICKS.findall(item["entry"]["text"]):
        if name in catalogue and name != item["function"] and name not in names:
            names.append(name)
    return names


def format_record(entry: dict[str, Any]) -> str:
    """The whole catalogue record of one function, as readable markdown."""
    lines = [
        f"**{entry['display_name']}** (`{entry['name']}`), domain: {entry['domain_label']}",
        "",
    ]
    lines.append(f"Summary: {entry['summary']}")
    description = (entry.get("description") or "").strip()
    if description:
        lines += ["", "Description:", ""]
        shown, rest = description[:DESCRIPTION_LIMIT], description[DESCRIPTION_LIMIT:]
        lines += [f"> {part}" if part else ">" for part in shown.splitlines()]
        if rest.strip():
            lines += [
                "",
                f"[The writer was shown the description only up to here ({DESCRIPTION_LIMIT} characters); "
                "the rest is for you.]",
                "",
            ]
            lines += [f"> {part}" if part else ">" for part in rest.splitlines()]
    formula = entry.get("formula") or {}
    for label, key in (
        ("Formula", "formula_latex"),
        ("Caveat", "caveat"),
        ("Citation", "citation"),
    ):
        if formula.get(key):
            lines += ["", f"{label}: {formula[key]}"]
    if formula.get("symbol_map"):
        lines += ["", f"Symbols: {json.dumps(formula['symbol_map'], ensure_ascii=False)}"]
    lines += ["", "Inputs:"]
    for p in entry["params"]:
        kind = "required" if p["required"] else f"optional, default {p['default']}"
        desc = f": {p['description']}" if p.get("description") else ""
        lines.append(f"- `{p['name']}` ({kind}, {p['type']}){desc}")
    if not entry["params"]:
        lines.append("- none")
    return "\n".join(lines)


HOW_TO_READ = """**How to read.** For each answer, check every claim in it against the records shown under it. The
answer's own function is shown first, then every other function the answer names, each with its full catalogue
record. Check input names, defaults, what the function returns, what it checks or does not do, and what the
answer says about any named function.

Mark each answer with one or more boxes:

- **Supported**: every claim is confirmed by the records shown.
- **Contradicted**: a claim the records say is wrong. Write the claim and what the record says.
- **Not in the records**: a claim the records neither confirm nor contradict (an output, a check, a method, a
  named function that has no record here). Write the claim. Do not use outside knowledge to decide it; the
  author checks each one against the engine afterwards and reports it separately.

Tick Supported only if you ticked neither of the other two. The tally is at the end."""


def build_sheet(
    seed: int,
    items: list[dict[str, Any]],
    catalogue: dict[str, dict[str, Any]],
    version: str,
    pool_size: int,
) -> str:
    """Assemble the sheet text."""
    out = [
        f"# Bank read sheet: {len(items)} random answers from bank `{version}`",
        "",
        f"Drawn with `random.Random({seed}).sample(...)` from {pool_size} served answers (explain, when and "
        "compare) by `scripts/assistant_read_sheet.py`. Answers already read are excluded.",
        "",
        HOW_TO_READ,
        "",
        "---",
        "",
    ]
    for n, item in enumerate(items, 1):
        title = f"{item['function']} : {item['action']}"
        if item["sibling"]:
            title += f" : vs `{item['sibling']}`"
        out += [
            f"## {n}. `{title}`",
            "",
            f"Source: {item['entry']['source']}",
            "",
            "### Answer",
            "",
        ]
        out += [f"> {line}" if line else ">" for line in item["entry"]["text"].splitlines()]
        out += ["", "### Records to check it against", "", "#### This function", ""]
        out += [format_record(catalogue[item["function"]]), ""]
        for name in named_functions(item, catalogue):
            out += [f"#### Named in the answer: `{name}`", "", format_record(catalogue[name]), ""]
        out += [
            "### Verdict",
            "",
            "- [ ] supported (every claim confirmed by the records)",
            "- [ ] contradicted:",
            "- [ ] not in the records:",
            "",
            "---",
            "",
        ]
    out += [
        "## Tally",
        "",
        f"Supported: __ / {len(items)}    Contradicted: __    Not in the records: __",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    """Draw the sample and write the sheet."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--seed", type=int, required=True, help="seed for random.Random")
    parser.add_argument("--n", type=int, default=40, help="number of answers to draw (default 40)")
    parser.add_argument("--exclude-ids", type=Path, help="JSON list of answer ids already read")
    parser.add_argument(
        "--out", type=Path, required=True, help="where to write the sheet (markdown)"
    )
    args = parser.parse_args(argv)

    version, bank = load_bank()
    catalogue = load_catalogue()
    pool = answer_pool(bank)
    excluded: set[str] = set()
    if args.exclude_ids:
        excluded = set(json.loads(args.exclude_ids.read_text(encoding="utf-8")))
        unknown = excluded - set(pool)
        if unknown:
            print(f"excluded ids not in the bank: {sorted(unknown)}", file=sys.stderr)
            return 1
    candidates = sorted(set(pool) - excluded)
    if args.n > len(candidates):
        print(f"asked for {args.n}, only {len(candidates)} answers left", file=sys.stderr)
        return 1
    drawn = random.Random(args.seed).sample(candidates, args.n)
    items = [pool[i] for i in sorted(drawn)]
    args.out.write_text(
        build_sheet(args.seed, items, catalogue, version, len(candidates)), encoding="utf-8"
    )
    by_action = {
        a: sum(1 for i in items if i["action"] == a) for a in ("explain", "when", "compare")
    }
    print(
        f"wrote {args.out}: {len(items)} answers {by_action}, pool {len(candidates)}, bank {version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

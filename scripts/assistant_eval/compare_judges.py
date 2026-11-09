"""Compare a cheaper judge's verdicts with a reference judge's on the same answers. No API, no cost.

Reasoning:
- An Opus judge for every answer is ruled out as overkill (Filippo, 2026-11-09), yet it was the only automatic
  check for answers that are unfaithful without breaking a mechanical rule (about 4.5% of text answers). Two sets
  of Opus verdicts already exist (about 400 answers, paid for). Whether a judge at a fraction of the price
  flags the same answers can be measured against them for the cost of the cheap judge alone.
- Opus is the reference, not the truth: it is a model too (one verdict changed between two runs on 120 repeated
  cases). Agreement with it is the measurable thing.
- A "flag" is a verdict of unfaithful (field `faithful`) or of implausible values (field `plausible_values`).
  **Recall** is the share of what the reference flagged that the cheap judge flagged: what would slip through.
  **False-alarm rate** is the share of answers the reference passed that the cheap judge flagged: the review
  burden. The thresholds below were fixed before any cheap-judge run, in docs/assistant-phase0-results.md.
- Flags are few (15 unfaithful in about 320 text answers), so recall has a wide interval. A reference with fewer
  than MIN_FLAGS flags is reported as "cannot tell", never as a pass.
- Answers are paired by (file pair, case id): v1 and v2 answers share case ids, so pairs are kept apart.

Usage:
    python scripts/assistant_eval/compare_judges.py \\
        --pair RUN_A/judgments.jsonl RUN_A/judgments_haiku.jsonl \\
        --pair RUN_B/judgments.jsonl RUN_B/judgments_haiku.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_eval import wilson  # noqa: E402

RECALL_MIN = 0.75
FALSE_ALARM_MAX = 0.30
MIN_FLAGS = 8
FIELDS = ("faithful", "plausible_values")


def load(path: Path) -> dict[str, dict[str, Any]]:
    """case id -> judgment row, for rows with a parsed verdict."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {r["case_id"]: r for r in rows if r.get("verdict")}


def flag(row: dict[str, Any], field: str) -> bool | None:
    """True if the verdict flags the answer, False if it passes it, None if the field does not apply."""
    value = row["verdict"].get(field)
    return None if value is None else (value is False)


def _kappa(both: int, ref_only: int, other_only: int, neither: int) -> float | None:
    n = both + ref_only + other_only + neither
    if n == 0:
        return None
    observed = (both + neither) / n
    ref_yes, other_yes = (both + ref_only) / n, (both + other_only) / n
    expected = ref_yes * other_yes + (1 - ref_yes) * (1 - other_yes)
    return None if expected == 1 else (observed - expected) / (1 - expected)


def compare(
    pairs: list[tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]],
    field: str,
    actions: set[str] | None = None,
) -> dict[str, Any]:
    """Pooled counts over the pairs, and per action, for one verdict field; `actions` limits the rows."""
    cells: dict[str, list[int]] = {}  # action -> [both, ref_only, other_only, neither]
    missed: list[dict[str, str]] = []
    for index, (ref, other) in enumerate(pairs):
        for case_id in sorted(ref.keys() & other.keys()):
            a, b = flag(ref[case_id], field), flag(other[case_id], field)
            if a is None or b is None:
                continue
            action = str(ref[case_id].get("intent", "?"))
            if actions and action not in actions:
                continue
            cell = cells.setdefault(action, [0, 0, 0, 0])
            cell[0 if a and b else 1 if a else 2 if b else 3] += 1
            if a and not b:
                missed.append({"pair": str(index), "case_id": case_id, "action": action})
    return {
        "pooled": _summary([sum(c[i] for c in cells.values()) for i in range(4)]),
        "by_action": {k: _summary(v) for k, v in sorted(cells.items())},
        "missed_by_the_other_judge": missed,
    }


def _summary(cell: list[int]) -> dict[str, Any]:
    both, ref_only, other_only, neither = cell
    ref_flags, ref_passes = both + ref_only, other_only + neither
    recall = both / ref_flags if ref_flags else None
    false_alarm = other_only / ref_passes if ref_passes else None
    low, high = wilson(both, ref_flags) if ref_flags else (None, None)
    if ref_flags < MIN_FLAGS:
        verdict = "cannot tell: too few reference flags"
    elif recall >= RECALL_MIN and false_alarm is not None and false_alarm <= FALSE_ALARM_MAX:
        verdict = "meets the thresholds"
    else:
        verdict = "does not meet the thresholds"
    return {
        "n": sum(cell),
        "reference_flagged": ref_flags,
        "other_flagged": both + other_only,
        "both_flagged": both,
        "recall": None if recall is None else round(recall, 3),
        "recall_ci95": None if low is None else [round(low, 3), round(high, 3)],
        "false_alarms": other_only,
        "false_alarm_rate": None if false_alarm is None else round(false_alarm, 3),
        "agreement": round((both + neither) / sum(cell), 3) if sum(cell) else None,
        "kappa": None if (k := _kappa(*cell)) is None else round(k, 3),
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--pair",
        nargs=2,
        action="append",
        required=True,
        type=Path,
        metavar=("REFERENCE", "OTHER"),
        help="a reference judgments file and the other judge's file for the same answers (repeatable)",
    )
    parser.add_argument(
        "--actions",
        default=None,
        help="comma-separated actions to count, for example explain,when,compare for faithfulness "
        "or example:typical,example:stress for plausible values",
    )
    args = parser.parse_args()
    actions = {a.strip() for a in args.actions.split(",") if a.strip()} if args.actions else None
    pairs = [(load(ref), load(other)) for ref, other in args.pair]
    out = {
        "thresholds": {
            "recall_min": RECALL_MIN,
            "false_alarm_max": FALSE_ALARM_MAX,
            "min_flags": MIN_FLAGS,
        },
        "pairs": [{"reference": str(r), "other": str(o)} for r, o in args.pair],
        "actions": sorted(actions) if actions else "all",
        **{field: compare(pairs, field, actions) for field in FIELDS},
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

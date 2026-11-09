"""A blind side-by-side: static catalogue text against the model's answer, for a person to pick.

Reasoning:
- Phase 0 measured whether Haiku's text is good enough, never whether it is better than what the catalogue
  already says. A template built from the record passes every mechanical check, and the judge's "useful" is an
  absolute yes or no. The cheapest honest test needs no judge: someone who knows the domain reads pairs and picks.
- Per case, the static answer is built here from the record alone, with no model and the best the catalogue
  allows: the summary, the description and the parameters with their descriptions for `explain`; the summary and
  the sibling list for `when`; both summaries and the inputs for `compare`. The model's answer comes from a
  finished run.
- Order is random per pair (a hash of seed and case id) and the page never says which is which; the key stays
  with whoever built it. The two styles differ, so the reader may guess: the instruction is to pick by what would
  help a visitor, not by who wrote it.
- Cases are chosen by a hash of a fixed seed, at most one per domain until each action has its share, so the
  choice is spread, repeatable and not made by looking at answers.
- Example values are not part of this test: the static alternative there is the few tested worked examples.

Usage:
    python scripts/assistant_eval/side_by_side.py pick --cases CASES                 # the case ids
    python scripts/assistant_eval/side_by_side.py export --run RUN --ids ID ...        # the model's answers, JSON
    python scripts/assistant_eval/side_by_side.py build --cases CASES --answers FILE --out PAGE.html --key KEY.json
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

ACTIONS = ("explain", "when", "compare")
DEFAULT_SEED = "gain-test-1"
_ROLE = re.compile(r":[a-z]+:`~?([^`]+)`")


def _rank(seed: str, key: str) -> str:
    return hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()


def pick(cases: list[dict[str, Any]], seed: str = DEFAULT_SEED, per_action: int = 4) -> list[str]:
    """`per_action` case ids for each text action, hash-ordered, a new domain each time where possible."""
    chosen: list[str] = []
    for action in ACTIONS:
        pool = sorted(
            (c for c in cases if c["intent"] == action), key=lambda c: _rank(seed, c["id"])
        )
        picked: list[str] = []
        domains: set[str] = set()
        for case in pool:
            if len(picked) == per_action:
                break
            if case["record"]["domain"] not in domains:
                domains.add(case["record"]["domain"])
                picked.append(case["id"])
        for case in pool:
            if len(picked) == per_action:
                break
            if case["id"] not in picked:
                picked.append(case["id"])
        chosen += picked
    return chosen


def export(run: Path, ids: list[str]) -> dict[str, Any]:
    """The model's text for each id from a finished run, with the model and the prompt version."""
    rows = [
        json.loads(line)
        for line in (run / "results.jsonl").read_text().splitlines()
        if line.strip()
    ]
    text = {r["case_id"]: r["text"] for r in rows if r["status"] == "ok" and r["rep"] == 0}
    missing = [i for i in ids if i not in text]
    if missing:
        raise SystemExit(f"not in {run}/results.jsonl (or not scored): {missing}")
    summary_path = run / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    return {
        "model": summary.get("model"),
        "prompt_version": summary.get("prompt_version"),
        "answers": {i: text[i] for i in ids},
    }


def _plain(text: str) -> str:
    """Prose without Sphinx roles (:func:`x` becomes x) and with whitespace collapsed to single spaces."""
    text = re.sub(r"``([^`]+)``", r"`\1`", _ROLE.sub(r"\1", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _inputs(record: dict[str, Any], limit: int = 8) -> str:
    lines = []
    for p in record["parameters"][:limit]:
        kind = "required" if p["required"] else f"optional, default {p['default']}"
        note = _plain(p.get("description") or "")
        lines.append(f"- `{p['name']}` ({kind})" + (f": {note}" if note else ""))
    more = len(record["parameters"]) - limit
    if more > 0:
        lines.append(f"- and {more} more")
    return "\n".join(lines)


def static_answer(case: dict[str, Any]) -> str:
    """What the catalogue alone can say for this menu choice, with no model."""
    record = case["record"]
    summary = _plain(record["summary"])
    if case["intent"] == "explain":
        parts = [summary]
        description = _plain(record.get("description") or "")
        if description and description != summary:
            parts.append(description)
        parts.append("Inputs:\n" + _inputs(record))
        return "\n\n".join(parts)
    if case["intent"] == "when":
        siblings = case.get("siblings") or []
        listing = "\n".join(f"- `{s['name']}`: {_plain(s['summary'])}" for s in siblings[:6])
        return summary + ("\n\nRelated functions:\n" + listing if listing else "")
    if case["intent"] == "compare":
        other = case["other"]

        def names(r: dict[str, Any]) -> str:
            return ", ".join(f"`{p['name']}`" for p in r["parameters"][:8]) or "none"

        return (
            f"`{record['name']}`: {summary}\n`{other['name']}`: {_plain(other['summary'])}\n\n"
            f"Inputs of `{record['name']}`: {names(record)}.\nInputs of `{other['name']}`: {names(other)}."
        )
    raise ValueError(f"no static answer for {case['intent']!r}")


def question(case: dict[str, Any]) -> str:
    name = case["record"]["display_name"]
    if case["intent"] == "explain":
        return f"What does {name} do?"
    if case["intent"] == "when":
        return f"When should I use {name}?"
    return f"How does {name} differ from {case['other']['display_name']}?"


def build(
    cases: dict[str, dict[str, Any]], answers: dict[str, str], seed: str = DEFAULT_SEED
) -> tuple[str, list[dict[str, Any]]]:
    """The blind page and its key. Pair order and the A/B side are decided by hashes of the seed."""
    ids = sorted(answers, key=lambda i: _rank(seed, "order:" + i))
    key: list[dict[str, Any]] = []
    cards: list[str] = []
    for n, case_id in enumerate(ids, start=1):
        case = cases[case_id]
        model_text, static_text = answers[case_id], static_answer(case)
        model_first = int(_rank(seed, "side:" + case_id), 16) % 2 == 0
        a, b = (model_text, static_text) if model_first else (static_text, model_text)
        key.append(
            {
                "n": n,
                "case_id": case_id,
                "action": case["intent"],
                "A": "model" if model_first else "static",
                "B": "static" if model_first else "model",
            }
        )
        cards.append(_card(n, len(ids), question(case), a, b))
    return _PAGE.replace("%CARDS%", "\n".join(cards)).replace("%COUNT%", str(len(ids))), key


def _card(n: int, total: int, ask: str, a: str, b: str) -> str:

    def box(side: str, text: str) -> str:
        return (
            f'<div class="ans"><div class="side">{side}</div><div class="txt">{html.escape(text)}</div>'
            f'<label class="err"><input type="checkbox" name="err{side}{n}"> contains an error, or '
            "states something the other answer does not support</label></div>"
        )

    return (
        f'<section class="pair" data-n="{n}"><h2>Pair {n} of {total}: <span>{html.escape(ask)}</span></h2>'
        f'<div class="cols">{box("A", a)}{box("B", b)}</div>'
        f'<div class="pick" role="radiogroup" aria-label="Which would help a visitor more?">'
        f'<label><input type="radio" name="pick{n}" value="A"> A helps more</label>'
        f'<label><input type="radio" name="pick{n}" value="B"> B helps more</label>'
        f'<label><input type="radio" name="pick{n}" value="same"> About the same</label>'
        f'<input class="note" type="text" name="note{n}" placeholder="optional note" maxlength="200"></div></section>'
    )


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Answer comparison</title>
<style>
:root{--bg:#faf9f5;--fg:#1f1e1d;--dim:#6b6862;--line:rgba(31,30,29,.14);--card:#fff;--acc:#a84a2e}
@media (prefers-color-scheme:dark){:root{--bg:#1c1b19;--fg:#ece9e2;--dim:#a8a49b;--line:rgba(236,233,226,.16);--card:#25241f;--acc:#e08a6d}}
*{box-sizing:border-box}body{margin:0;padding:20px 16px 60px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1040px;margin:0 auto}h1{font-size:20px;margin:0 0 6px}p.lead{color:var(--dim);margin:0 0 20px}
.pair{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:14px 16px;margin:0 0 16px}
.pair h2{font-size:15px;margin:0 0 10px}.pair h2 span{color:var(--acc)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media (max-width:760px){.cols{grid-template-columns:1fr}}
.ans{border:1px solid var(--line);border-radius:8px;padding:10px 12px}.side{font:600 11px ui-monospace,monospace;letter-spacing:.1em;color:var(--acc);margin-bottom:6px}
.txt{white-space:pre-wrap;font-size:14px}.err{display:block;margin-top:10px;color:var(--dim);font-size:12.5px}
.pick{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;margin-top:12px}.note{flex:1 1 220px;min-width:160px;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:transparent;color:var(--fg)}
button{font:inherit;padding:9px 16px;border-radius:8px;border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}
textarea{width:100%;min-height:210px;margin-top:12px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);font:13px/1.45 ui-monospace,monospace}
</style></head><body><main>
<h1>Which answer would help more?</h1>
<p class="lead">%COUNT% pairs. Each shows two answers to the same question that a visitor asked from a menu. Pick the one that would help the visitor more. Tick "contains an error" on any answer that is wrong, or that states something the other one does not support. You may be able to guess where each came from; pick by usefulness anyway. There is no right answer.</p>
%CARDS%
<button type="button" id="done">Show my results</button>
<textarea id="out" readonly placeholder="Your results appear here. Select all, copy, and paste them into the chat."></textarea>
</main>
<script>
document.getElementById('done').addEventListener('click', function () {
  var lines = ['blind-test v1'];
  document.querySelectorAll('.pair').forEach(function (p) {
    var n = p.dataset.n, pick = p.querySelector('input[name=pick' + n + ']:checked');
    var line = n + ' ' + (pick ? pick.value : '-');
    if (p.querySelector('input[name=errA' + n + ']').checked) line += ' errA';
    if (p.querySelector('input[name=errB' + n + ']').checked) line += ' errB';
    var note = p.querySelector('input[name=note' + n + ']').value.trim();
    if (note) line += ' | ' + note;
    lines.push(line);
  });
  var out = document.getElementById('out'); out.value = lines.join('\\n'); out.focus(); out.select();
  try { if (navigator.clipboard) navigator.clipboard.writeText(out.value); } catch (e) {}
});
</script></body></html>
"""


def _load_cases(path: Path) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in map(json.loads, path.read_text().splitlines()) if c}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pick", help="print the chosen case ids as JSON")
    p.add_argument("--cases", required=True, type=Path)
    p.add_argument("--seed", default=DEFAULT_SEED)
    p.add_argument("--per-action", type=int, default=4)
    e = sub.add_parser(
        "export", help="print the model's answers for ids from a finished run, as JSON"
    )
    e.add_argument("--run", required=True, type=Path)
    e.add_argument("--ids", required=True, nargs="+")
    b = sub.add_parser("build", help="write the blind page and its key")
    b.add_argument("--cases", required=True, type=Path)
    b.add_argument("--answers", required=True, type=Path, help="the JSON printed by export")
    b.add_argument("--out", required=True, type=Path)
    b.add_argument("--key", required=True, type=Path)
    b.add_argument("--seed", default=DEFAULT_SEED)
    args = parser.parse_args()
    if args.command == "pick":
        cases = list(_load_cases(args.cases).values())
        print(json.dumps(pick(cases, args.seed, args.per_action), indent=1))
    elif args.command == "export":
        print(json.dumps(export(args.run, args.ids), ensure_ascii=False, indent=1))
    else:
        data = json.loads(args.answers.read_text())
        answers = data["answers"] if "answers" in data else data
        page, key = build(_load_cases(args.cases), answers, args.seed)
        args.out.write_text(page, encoding="utf-8")
        args.key.write_text(json.dumps(key, indent=1))
        print(f"wrote {args.out} ({len(key)} pairs) and the key {args.key}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Opus's recall, checked by a person: do the answers Opus passed contain errors it missed?

Reasoning:
- Opus judged 308 prompt-v4 answers and flagged 10 (docs/assistant-phase0-results.md 9.10). Its precision held
  where checked (5 of 6, one arguable), but its recall is unknown: nothing says how many errors sit in the 298 it
  passed. A cheaper judge cannot replace it (9.8), so the open question is whether Opus itself can gate the text
  at build time, with a person reading only a sample and what it flags. Only a person reading Opus-passed answers
  against their records can answer that.
- Three strata, drawn by a hash of a fixed seed so the choice is repeatable and not made by looking at answers:
  `clean` (passed, no issues noted: the residual error rate of the gate), `noted` (passed, but Opus listed
  issues: is that free signal worth treating as a flag?), `flagged` (the Opus flags nobody has read yet).
  `clean_more` is a second batch from the same pool for when the first is inconclusive.
- The reader sees the catalogue record the guide was given, then the answer, and marks "no error found" or "an
  error, or a claim the record does not support". The page never says which stratum an item is from, and never
  mentions Opus; the key stays with whoever built it.
- `export` refuses answers whose Opus verdict does not match their stratum (a mistyped id, or a run other than
  the one the ids were drawn for), so the sample cannot silently drift.

Usage:
    python scripts/assistant_eval/recall_check.py pick   --cases CASES
    python scripts/assistant_eval/recall_check.py export --cases CASES --run RUN [--stage 2] > answers.json
    python scripts/assistant_eval/recall_check.py build  --cases CASES --answers answers.json --out PAGE --key KEY
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from side_by_side import _plain, question  # noqa: E402

TEXT_ACTIONS = ("explain", "when", "compare")
DOCS = Path(__file__).resolve().parents[2] / "docs"
DEFAULT_CONFIG = DOCS / "assistant-prompt-v4-recall-check.json"
DEFAULT_FLAGS = DOCS / "assistant-prompt-v4-opus-flags.csv"


def _rank(seed: str, key: str) -> str:
    return hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()


def load_flagged(path: Path) -> list[str]:
    """Case ids Opus flagged (`opus` = F) in the flags CSV."""
    with path.open(newline="") as handle:
        return [r["case_id"] for r in csv.DictReader(handle) if r["opus"] == "F"]


def strata(
    cases: dict[str, dict[str, Any]], config: dict[str, Any], flagged: list[str]
) -> dict[str, list[str]]:
    """The four id lists. Raises SystemExit if a listed id is not a text case."""
    text = {i for i, c in cases.items() if c["intent"] in TEXT_ACTIONS}
    noted_all = list(config["noted_passes"])
    unknown = [i for i in noted_all + flagged if i not in text]
    if unknown:
        raise SystemExit(f"not text cases in the case file: {unknown}")
    if set(noted_all) & set(flagged):
        raise SystemExit("an id is both flagged and passed-with-issues")
    seed = config["seed"]
    pool = sorted(text - set(flagged) - set(noted_all), key=lambda i: _rank(seed, "clean:" + i))
    first, more = config["clean"], config["clean_more"]
    skip = set(config["flagged_already_read"])
    return {
        "clean": pool[:first],
        "clean_more": pool[first : first + more],
        "noted": sorted(noted_all, key=lambda i: _rank(seed, "noted:" + i))[: config["noted"]],
        "flagged": [i for i in sorted(flagged) if i not in skip],
    }


def stage_ids(groups: dict[str, list[str]], stage: int) -> list[str]:
    """Stage 1 is the main reading; stage 2 is only the second batch of clean answers."""
    if stage == 2:
        return list(groups["clean_more"])
    return groups["clean"] + groups["noted"] + groups["flagged"]


def check_verdicts(groups: dict[str, list[str]], verdicts: dict[str, dict[str, Any]]) -> list[str]:
    """What is wrong with the Opus verdicts for the drawn ids (empty when every stratum is as drawn)."""
    problems = []
    for stratum, ids in groups.items():
        for case_id in ids:
            verdict = verdicts.get(case_id)
            if not verdict:
                problems.append(f"{case_id}: no Opus verdict")
                continue
            faithful, noted = verdict.get("faithful"), bool(verdict.get("issues"))
            if stratum == "flagged" and faithful is not False:
                problems.append(f"{case_id}: drawn as flagged but Opus passed it")
            if stratum != "flagged" and faithful is not True:
                problems.append(f"{case_id}: drawn as passed but Opus flagged it")
            if stratum.startswith("clean") and faithful and noted:
                problems.append(f"{case_id}: drawn as clean but Opus noted issues")
            if stratum == "noted" and faithful and not noted:
                problems.append(f"{case_id}: drawn as noted but Opus noted none")
    return problems


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def export(run: Path, groups: dict[str, list[str]], stage: int = 1) -> dict[str, Any]:
    """The answers for a stage from a finished run, after checking each against Opus's verdict."""
    ids = stage_ids(groups, stage)
    verdicts = {r["case_id"]: r["verdict"] for r in _jsonl(run / "judgments.jsonl")}
    problems = check_verdicts({k: v for k, v in groups.items() if set(v) <= set(ids)}, verdicts)
    text = {r["case_id"]: r["text"] for r in _jsonl(run / "results.jsonl") if r["status"] == "ok"}
    problems += [f"{i}: no scored answer" for i in ids if i not in text]
    if problems:
        raise SystemExit("not exporting:\n" + "\n".join(problems[:20]))
    summary_path = run / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    return {
        "model": summary.get("model"),
        "prompt_version": summary.get("prompt_version"),
        "answers": {i: text[i] for i in ids},
    }


def _esc(text: str) -> str:
    return html.escape(_plain(text))


def _record_html(record: dict[str, Any]) -> str:
    summary = _plain(record["summary"])
    parts = [
        f"<h3>{html.escape(record['display_name'])} (<code>{html.escape(record['name'])}</code>)</h3>",
        f"<p>{html.escape(summary)}</p>",
    ]
    description = _plain(record.get("description") or "")
    if description and description != summary:
        parts.append(f"<p>{html.escape(description)}</p>")
    rows = []
    for p in record["parameters"]:
        kind = "required" if p["required"] else f"optional, default {p['default']}"
        rows.append(
            f"<li><code>{html.escape(p['name'])}</code> ({html.escape(str(kind))})"
            + (f": {_esc(p['description'])}" if p.get("description") else "")
            + "</li>"
        )
    if rows:
        parts.append("<p class='lab'>Inputs</p><ul>" + "".join(rows) + "</ul>")
    return "".join(parts)


def _entry_html(case: dict[str, Any]) -> str:
    out = [_record_html(case["record"])]
    if case["intent"] == "compare" and case.get("other"):
        out.append("<hr>" + _record_html(case["other"]))
    siblings = case.get("siblings") or []
    if case["intent"] in ("when", "compare") and siblings:
        listing = "".join(
            f"<li><code>{html.escape(s['name'])}</code>: {_esc(s['summary'])}</li>"
            for s in siblings
        )
        out.append(
            "<p class='lab'>Related functions the guide could name</p><ul>" + listing + "</ul>"
        )
    return "".join(out)


def build(
    cases: dict[str, dict[str, Any]],
    answers: dict[str, str],
    groups: dict[str, list[str]],
    seed: str,
) -> tuple[str, list[dict[str, Any]]]:
    """The reading page and its key (item number, case id, stratum). Order is a hash of the seed."""
    stratum_of = {i: s for s, ids in groups.items() for i in ids}
    unknown = [i for i in answers if i not in stratum_of]
    if unknown:
        raise SystemExit(f"answers for ids that are in no stratum: {unknown}")
    ids = sorted(answers, key=lambda i: _rank(seed, "order:" + i))
    key, cards = [], []
    for n, case_id in enumerate(ids, start=1):
        case = cases[case_id]
        key.append(
            {
                "n": n,
                "case_id": case_id,
                "stratum": stratum_of[case_id],
                "action": case["intent"],
            }
        )
        cards.append(
            f'<section class="item" data-n="{n}"><h2>Item {n} of {len(ids)}: '
            f"<span>{html.escape(question(case))}</span></h2>"
            f"<details open><summary>The catalogue entry the guide was given</summary>{_entry_html(case)}</details>"
            f'<div class="ans"><div class="side">THE ANSWER</div><div class="txt">{html.escape(answers[case_id])}</div></div>'
            f'<div class="pick"><label><input type="radio" name="v{n}" value="OK"> No error found</label>'
            f'<label><input type="radio" name="v{n}" value="ERR"> Contains an error, or a claim the entry does not support</label>'
            f'<input class="note" type="text" name="note{n}" placeholder="what is wrong (optional)" maxlength="240"></div></section>'
        )
    return _PAGE.replace("%CARDS%", "\n".join(cards)).replace("%COUNT%", str(len(ids))), key


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Answer check</title>
<style>
:root{--bg:#faf9f5;--fg:#1f1e1d;--dim:#6b6862;--line:rgba(31,30,29,.14);--card:#fff;--acc:#a84a2e}
@media (prefers-color-scheme:dark){:root{--bg:#1c1b19;--fg:#ece9e2;--dim:#a8a49b;--line:rgba(236,233,226,.16);--card:#25241f;--acc:#e08a6d}}
*{box-sizing:border-box}body{margin:0;padding:20px 16px 60px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:860px;margin:0 auto}h1{font-size:20px;margin:0 0 6px}p.lead{color:var(--dim);margin:0 0 20px}
.item{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:14px 16px;margin:0 0 18px}
.item h2{font-size:15px;margin:0 0 10px}.item h2 span{color:var(--acc)}h3{font-size:14px;margin:8px 0 4px}
details{border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:13.5px}summary{cursor:pointer;color:var(--dim)}
details p{margin:6px 0}details ul{margin:4px 0 4px 18px;padding:0}.lab{color:var(--dim);font-size:12px;margin:8px 0 2px}
.ans{border:1px solid var(--acc);border-radius:8px;padding:10px 12px;margin-top:10px}.side{font:600 11px ui-monospace,monospace;letter-spacing:.1em;color:var(--acc);margin-bottom:6px}
.txt{white-space:pre-wrap;font-size:14.5px}
.pick{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;margin-top:12px}.note{flex:1 1 240px;min-width:160px;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:transparent;color:var(--fg)}
button{font:inherit;padding:9px 16px;border-radius:8px;border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}
textarea{width:100%;min-height:210px;margin-top:12px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);font:13px/1.45 ui-monospace,monospace}
</style></head><body><main>
<h1>Is each answer right?</h1>
<p class="lead">%COUNT% answers a guide wrote for a visitor of a risk-function portal who picked a function and a question from a menu. Above each answer is the catalogue entry the guide was given; check the answer against that entry only. Choose "contains an error" if it says something the entry contradicts, or something the entry does not support that is not plain textbook finance, including crediting "pyvar's documentation" with something the entry does not say. Style and length do not matter. Do not skip an item: a blank counts as unread.</p>
%CARDS%
<button type="button" id="done">Show my results</button>
<textarea id="out" readonly placeholder="Your results appear here. Select all, copy, and paste them into the chat."></textarea>
</main>
<script>
document.getElementById('done').addEventListener('click', function () {
  var lines = ['answer-check v1'];
  document.querySelectorAll('.item').forEach(function (p) {
    var n = p.dataset.n, v = p.querySelector('input[name=v' + n + ']:checked');
    var line = n + ' ' + (v ? v.value : '-');
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
    for name in ("pick", "export", "build"):
        p = sub.add_parser(name)
        p.add_argument("--cases", required=True, type=Path)
        p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        p.add_argument("--flags", type=Path, default=DEFAULT_FLAGS)
        if name != "pick":
            p.add_argument("--stage", type=int, choices=(1, 2), default=1)
        if name == "export":
            p.add_argument("--run", required=True, type=Path)
        if name == "build":
            p.add_argument("--answers", required=True, type=Path)
            p.add_argument("--out", required=True, type=Path)
            p.add_argument("--key", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    cases = _load_cases(args.cases)
    groups = strata(cases, config, load_flagged(args.flags))
    if args.command == "pick":
        print(json.dumps({"seed": config["seed"], **groups}, indent=1))
    elif args.command == "export":
        print(json.dumps(export(args.run, groups, args.stage), ensure_ascii=False, indent=1))
    else:
        data = json.loads(args.answers.read_text())
        answers = data["answers"] if "answers" in data else data
        wanted = set(stage_ids(groups, args.stage))
        if set(answers) != wanted:
            raise SystemExit(
                f"the answers are not exactly stage {args.stage}: "
                f"missing {sorted(wanted - set(answers))[:5]}, extra {sorted(set(answers) - wanted)[:5]}"
            )
        page, key = build(cases, answers, groups, config["seed"])
        args.out.write_text(page, encoding="utf-8")
        args.key.write_text(json.dumps(key, indent=1))
        print(f"wrote {args.out} ({len(key)} items) and the key {args.key}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

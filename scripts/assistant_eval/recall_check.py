"""Opus's recall, checked by a person: do the answers Opus passed contain errors it missed?

Reasoning:
- Opus judged 308 prompt-v4 answers and flagged 10 (docs/assistant-phase0-results.md 9.10). Its precision held
  where checked (5 of 6, one arguable), but its recall is unknown: nothing says how many errors sit in the answers
  it passed. A cheaper judge cannot replace it (9.8), so the open question is whether Opus itself can gate the text
  at build time, with a person reading only a sample and what it flags. Only a person reading Opus-passed answers
  against their records can answer that.
- The strata come from the Opus verdicts of the run being checked, never from a list of ids: `clean` (passed, no
  issues listed: the residual error rate of the gate), `noted` (passed, but Opus listed issues: is that free
  signal?), `flagged` (Opus said unfaithful: is it right?). Each is drawn by a hash of a fixed seed, so the draw is
  repeatable from the run and not made by looking at answers. `clean_more` is a second batch from the clean pool for
  when the first is inconclusive. (The first draw of this check named its ids in a file; that run's files were
  lost with the machine that made them, and the check was re-planned around a run that carries its own export.)
- `export` is built to survive the machine it runs on: one JSON file per stage with the answers, each id's
  stratum, and (for noted and flagged answers) what Opus said, plus the pool sizes and every flagged and noted id.
  It goes to whoever builds the page, never to the reader.
- The reader sees the catalogue record the guide was given, then the answer, and marks "no error found" or "an
  error, or a claim the record does not support". The page never says which stratum an item is from, and never
  mentions Opus; the key stays with whoever built it.

Usage:
    python scripts/assistant_eval/recall_check.py pick   --cases CASES --run RUN
    python scripts/assistant_eval/recall_check.py export --cases CASES --run RUN [--stage 2] > stage1.json
    python scripts/assistant_eval/recall_check.py build  --cases CASES --answers stage1.json --out PAGE --key KEY
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from side_by_side import _plain, question  # noqa: E402

TEXT_ACTIONS = ("explain", "when", "compare")
DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[2] / "docs" / "assistant-prompt-v4-recall-check.json"
)
ISSUE_CHARS = 300


def _rank(seed: str, key: str) -> str:
    return hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def pools(
    cases: dict[str, dict[str, Any]], judgments: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """Every judged text case by what Opus said: flagged, noted (passed with issues), clean, or unparsed."""
    out: dict[str, list[str]] = {"flagged": [], "noted": [], "clean": [], "unparsed": []}
    for row in judgments:
        case_id = row["case_id"]
        if case_id not in cases or cases[case_id]["intent"] not in TEXT_ACTIONS:
            continue
        verdict = row.get("verdict")
        if not verdict or not isinstance(verdict.get("faithful"), bool):
            out["unparsed"].append(case_id)
        elif not verdict["faithful"]:
            out["flagged"].append(case_id)
        elif verdict.get("issues"):
            out["noted"].append(case_id)
        else:
            out["clean"].append(case_id)
    return {k: sorted(v) for k, v in out.items()}


def draw(groups: dict[str, list[str]], config: dict[str, Any]) -> dict[str, list[str]]:
    """The ids to read: a hash-ordered head of each pool, the clean pool split into a first and a second batch."""
    seed = config["seed"]

    def ranked(kind: str) -> list[str]:
        return sorted(groups[kind], key=lambda i: _rank(seed, f"{kind}:{i}"))

    clean, first = ranked("clean"), config["clean"]
    return {
        "clean": clean[:first],
        "clean_more": clean[first : first + config["clean_more"]],
        "noted": ranked("noted")[: config["noted"]],
        "flagged": ranked("flagged")[: config["flagged"]],
    }


def stage_ids(drawn: dict[str, list[str]], stage: int) -> list[str]:
    """Stage 1 is the main reading; stage 2 is only the second batch of clean answers."""
    if stage == 2:
        return list(drawn["clean_more"])
    return drawn["clean"] + drawn["noted"] + drawn["flagged"]


def export(
    cases: dict[str, dict[str, Any]], run: Path, config: dict[str, Any], stage: int = 1
) -> dict[str, Any]:
    """One stage of the check as a file: answers, strata, what Opus said about the non-clean ones, the pools."""
    judgments = _jsonl(run / "judgments.jsonl")
    groups = pools(cases, judgments)
    drawn = draw(groups, config)
    ids = stage_ids(drawn, stage)
    text = {r["case_id"]: r["text"] for r in _jsonl(run / "results.jsonl") if r["status"] == "ok"}
    missing = [i for i in ids if i not in text]
    if missing:
        raise SystemExit(f"no scored answer for: {missing[:10]}")
    stratum_of = {i: s for s, members in drawn.items() for i in members}
    verdicts = {r["case_id"]: r["verdict"] for r in judgments if r.get("verdict")}
    summary_path = run / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    out: dict[str, Any] = {
        "stage": stage,
        "seed": config["seed"],
        "model": summary.get("model"),
        "prompt_version": summary.get("prompt_version"),
        "strata": {i: stratum_of[i] for i in ids},
        "opus": {
            i: {
                "faithful": verdicts[i]["faithful"],
                "issues": [str(x)[:ISSUE_CHARS] for x in verdicts[i].get("issues") or []],
            }
            for i in ids
            if stratum_of[i] in ("noted", "flagged")
        },
        "answers": {i: text[i] for i in ids},
    }
    if stage == 1:
        out["pools"] = {k: len(v) for k, v in groups.items()}
        out["all_flagged"] = groups["flagged"]
        out["all_noted"] = groups["noted"]
    return out


def _esc(text: str) -> str:
    return html.escape(_plain(text))


SHOWN_FIELDS = (
    "name",
    "display_name",
    "domain",
    "summary",
    "description",
    "formula_latex",
    "symbol_map",
    "caveat",
    "citation",
    "parameters",
)


def _block(label: str, body: str) -> str:
    return f"<p class='lab'>{label}</p>{body}"


def _record_html(record: dict[str, Any]) -> str:
    """Every field of the record, because the guide was given all of them (the first reading of this check
    hid the formula, the symbols and the caveat, and five of its six errors on clean answers were claims
    those fields support). A field this function does not know is shown as JSON, never dropped."""
    summary = _plain(record["summary"])
    domain = f" · {html.escape(str(record['domain']))}" if record.get("domain") else ""
    parts = [
        f"<h3>{html.escape(record['display_name'])} (<code>{html.escape(record['name'])}</code>){domain}</h3>",
        f"<p>{html.escape(summary)}</p>",
    ]
    description = _plain(record.get("description") or "")
    if description and description != summary:
        parts.append(f"<p>{html.escape(description)}</p>")
    if record.get("formula_latex"):
        parts.append(
            _block(
                "Formula (LaTeX, as the guide saw it)",
                f"<pre>{html.escape(str(record['formula_latex']))}</pre>",
            )
        )
    if record.get("symbol_map"):
        symbols = "".join(
            f"<li><code>{html.escape(str(k))}</code> is <code>{html.escape(str(v))}</code></li>"
            for k, v in dict(record["symbol_map"]).items()
        )
        parts.append(_block("Symbols", f"<ul>{symbols}</ul>"))
    if record.get("caveat"):
        parts.append(_block("Caveat", f"<p>{html.escape(_plain(str(record['caveat'])))}</p>"))
    if record.get("citation"):
        parts.append(_block("Source", f"<p>{html.escape(str(record['citation']))}</p>"))
    rows = []
    for p in record["parameters"]:
        kind = "required" if p["required"] else f"optional, default {p['default']}"
        meta = f"{p.get('type')}, {kind}" if p.get("type") else kind
        extra = {
            k: v
            for k, v in p.items()
            if k not in ("name", "type", "required", "default", "description")
        }
        rows.append(
            f"<li><code>{html.escape(p['name'])}</code> ({html.escape(str(meta))})"
            + (f": {_esc(p['description'])}" if p.get("description") else "")
            + (f" <code>{html.escape(json.dumps(extra))}</code>" if extra else "")
            + "</li>"
        )
    if rows:
        parts.append(_block("Inputs", "<ul>" + "".join(rows) + "</ul>"))
    for key, value in record.items():
        if key not in SHOWN_FIELDS and value not in (None, "", [], {}):
            parts.append(
                _block(
                    html.escape(key),
                    f"<pre>{html.escape(json.dumps(value, ensure_ascii=False))}</pre>",
                )
            )
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
    cases: dict[str, dict[str, Any]], answers: dict[str, str], strata: dict[str, str], seed: str
) -> tuple[str, list[dict[str, Any]]]:
    """The reading page and its key (item number, case id, stratum). Order is a hash of the seed."""
    if set(answers) != set(strata):
        raise SystemExit("the answers and the strata are not for the same ids")
    ids = sorted(answers, key=lambda i: _rank(seed, "order:" + i))
    key, cards = [], []
    for n, case_id in enumerate(ids, start=1):
        case = cases[case_id]
        key.append(
            {"n": n, "case_id": case_id, "stratum": strata[case_id], "action": case["intent"]}
        )
        cards.append(
            f'<section class="item" data-n="{n}"><h2>Item {n} of {len(ids)}: '
            f"<span>{html.escape(question(case))}</span></h2>"
            f"<details open><summary>The catalogue entry the guide was given</summary>"
            f"{_entry_html(case)}</details>"
            f'<div class="ans"><div class="side">THE ANSWER</div>'
            f'<div class="txt">{html.escape(answers[case_id])}</div></div>'
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
pre{white-space:pre-wrap;word-break:break-word;margin:4px 0;padding:6px 8px;border:1px solid var(--line);border-radius:6px;font:12.5px/1.45 ui-monospace,monospace}
.pick{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;margin-top:12px}.note{flex:1 1 240px;min-width:160px;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:transparent;color:var(--fg)}
button{font:inherit;padding:9px 16px;border-radius:8px;border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}
textarea{width:100%;min-height:210px;margin-top:12px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);font:13px/1.45 ui-monospace,monospace}
</style></head><body><main>
<h1>Is each answer right?</h1>
<p class="lead">%COUNT% answers a guide wrote for a visitor of a risk-function portal who picked a function and a question from a menu. Above each answer is the complete catalogue entry the guide was given (summary, description, formula, symbols, caveat, source, inputs and related functions); check the answer against that entry only. Choose "contains an error" if it says something the entry contradicts, or something the entry does not support that is not plain textbook finance, including crediting "pyvar's documentation" with something the entry does not say. Style and length do not matter. Do not skip an item: a blank counts as unread.</p>
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
        if name in ("pick", "export"):
            p.add_argument("--run", required=True, type=Path)
        if name == "export":
            p.add_argument("--stage", type=int, choices=(1, 2), default=1)
        if name == "build":
            p.add_argument("--answers", required=True, type=Path)
            p.add_argument("--out", required=True, type=Path)
            p.add_argument("--key", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    cases = _load_cases(args.cases)
    if args.command == "build":
        data = json.loads(args.answers.read_text())
        page, key = build(cases, data["answers"], data["strata"], data["seed"])
        args.out.write_text(page, encoding="utf-8")
        args.key.write_text(json.dumps(key, indent=1))
        print(f"wrote {args.out} ({len(key)} items) and the key {args.key}", file=sys.stderr)
    elif args.command == "pick":
        groups = pools(cases, _jsonl(args.run / "judgments.jsonl"))
        counts = {k: len(v) for k, v in groups.items()}
        drawn = draw(groups, config)
        print(json.dumps({"seed": config["seed"], "pools": counts, **drawn}, indent=1))
    else:
        print(json.dumps(export(cases, args.run, config, args.stage), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

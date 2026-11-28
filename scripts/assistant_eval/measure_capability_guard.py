#!/usr/bin/env python3
"""scripts/assistant_eval/measure_capability_guard.py: measure the capability-claim guard offline (results 9.39).

Reasoning:
- Free and offline: it replays answers already recorded by earlier paid runs through `capability_guard`; it calls no
  model, no network and no API. Nothing in it can spend money.
- Three measurements, each answering one question about the guard:
  1. EXTRACTION on a frozen, varied question set (`capability_questions.jsonl`: 22 capability questions whose
     feature the record lacks, 10 whose feature the record states, 15 that are not capability questions) and on the
     260-case set of the paid runs (30 category D questions, templated, with the true phantom term of each, and 230
     questions of other kinds). Does the guard find the term, stay out of the way when the record states the feature,
     and leave other questions alone?
  2. REPLAY on every answer the paid runs recorded: how many would the guard fail on the first try (each is a retry,
     a model call, in production), how many of those are claims a person would call false, and does it agree with the
     harness check that knows the true term?
  3. REGRESSIONS: the five Sonnet answers of run D that the first harness check failed although they were right
     (results 9.27: a helpful second sentence after a correct denial), and the one real miss the six-question check
     found (results 9.36, D:six:03).
- Input: a directory per run with `typed_cases.jsonl` and `typed_<writer>/results.jsonl` (+ `judgments.jsonl`), as the
  scratch branches `origin/data/assistant-tier-run-N` hold them under docs/scratch/tier_run_N/ (see docs/ for how
  to extract them: `git archive origin/data/assistant-tier-run-5 docs/scratch | tar -x -C <dir>`).

Usage (repo root):
    python scripts/assistant_eval/measure_capability_guard.py \\
        --run run4=<dir>/docs/scratch/tier_run_4 --run run5=<dir>/docs/scratch/tier_run_5 \\
        --run run6=<dir>/docs/scratch/tier_run_6 [--show] [--json out.json]

Exit codes: 0 measured; 2 a usage error or missing input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import capability_guard as cg  # noqa: E402
from assistant import graders, typed_graders  # noqa: E402

FUNCTIONS = ROOT / "portal" / "functions.json"
QUESTIONS = Path(__file__).resolve().parent / "capability_questions.jsonl"

# The one real miss (results 9.36, D:six:03), as 9.36 quotes it: the answer said the first sentence below and then
# the second. Only the two quoted sentences are used; the rest of that answer is not recorded.
SHARPE_QUESTION = "Does Sharpe Ratio support intraday data?"
SHARPE_ANSWER = (
    "Sharpe Ratio doesn't have a data-frequency setting. "
    "Intraday returns can be passed in as long as they are in that form."
)


# Sentences about "intraday" in the shapes an answer to SHARPE_QUESTION can take. Written before the guard was run on
# them. They test the claim detector's coverage of phrasings, not how often a model writes a claim: no recorded answer
# apart from D:six:03 contains one (see the replay), so recall on real traffic is not measurable offline.
CLAIM_SHAPES = (
    "Yes, Sharpe Ratio supports intraday data.",
    "Intraday returns can be passed in as long as they are in that form.",
    "It works with intraday data as long as you set periods_per_year accordingly.",
    "The function accepts intraday returns.",
    "You can pass intraday returns directly.",
    "Intraday data is handled the same way as daily data.",
    "Sharpe Ratio takes intraday returns and annualises them.",
    "pyvar computes intraday Sharpe ratios when `periods_per_year` is set to the number of intraday periods.",
    "Yes: just provide the intraday series as `returns`.",
    "Intraday frequency is covered by the `periods_per_year` parameter.",
    "It is available for intraday data too.",
    "For intraday data, set `periods_per_year` to 252 times the number of bars per day.",
)
NON_CLAIM_SHAPES = (
    "No, Sharpe Ratio does not support intraday data.",
    "Nothing in its inputs covers intraday data.",
    "It doesn't appear to handle intraday returns.",
    "Intraday data is not a supported input.",
    "The function takes one series of per-period returns rather than intraday bars.",
    "If you have intraday data, you would need to aggregate it yourself.",
    "If your returns are intraday, convert them to daily returns first.",
    "pyvar does not offer intraday handling for this function.",
    "Sharpe Ratio lacks an intraday mode.",
    "There is no intraday option among its parameters.",
    "You would have to resample intraday data to daily first.",
    "Intraday data is outside what this function covers.",
    "That is a different tool's job, not this function's.",
    "Daily returns only; intraday series are out of scope.",
)


def measure_shapes(catalogue: list[dict[str, Any]]) -> dict[str, Any]:
    entry = next(e for e in catalogue if e["name"] == "sharpe_ratio")
    records = cg.trimmed([entry])
    caught = [s for s in CLAIM_SHAPES if cg.check_answer(SHARPE_QUESTION, s, catalogue, records)[1]]
    flagged = [s for s in NON_CLAIM_SHAPES if cg.check_answer(SHARPE_QUESTION, s, catalogue, records)[1]]
    return {
        "claims": [len(caught), len(CLAIM_SHAPES)],
        "claims_missed": [s for s in CLAIM_SHAPES if s not in caught],
        "non_claims": [len(NON_CLAIM_SHAPES) - len(flagged), len(NON_CLAIM_SHAPES)],
        "non_claims_flagged": flagged,
    }


def _load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _norm(text: str) -> str:
    return re.sub(r"[-_\s]+", " ", text.lower()).strip()


def _related(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    return bool(a) and bool(b) and (a in b or b in a)


def _catalogue() -> list[dict[str, Any]]:
    data = json.loads(FUNCTIONS.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data["functions"]


def _opus_flagged(verdict: dict[str, Any] | None) -> bool:
    """The flag rule of docs/assistant-tier-run-N-flags.csv: unfaithful, not useful, or implausible values."""
    if not verdict:
        return False
    return (
        verdict.get("faithful") is False
        or verdict.get("useful") is False
        or verdict.get("plausible_values") is False
    )


# --------------------------------------------------------------------------------------------------- 1. extraction


def measure_frozen(catalogue: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {e["name"]: e for e in catalogue}
    out: dict[str, Any] = {"absent": [0, 0], "present": [0, 0], "other": [0, 0], "failures": [], "sha": None}
    for row in _load(QUESTIONS):
        records = cg.trimmed([by_name[row["function"]]]) if row["function"] else []
        terms = cg.guard_terms(row["question"], catalogue, records)
        kind = row["kind"].replace("capability_", "")
        if kind == "absent":
            good = any(_related(t, y) for t in terms for y in row["y"])
        else:
            good = not terms
        out[kind][1] += 1
        out[kind][0] += int(good)
        if not good:
            out["failures"].append(
                {"id": row["id"], "question": row["question"], "kind": kind, "terms": terms,
                 "phrase": cg.capability_phrase(row["question"], catalogue)}
            )
    return out


def _records_for(catalogue_by_name: dict[str, dict[str, Any]], names: list[str]) -> list[dict[str, Any]]:
    return cg.trimmed([catalogue_by_name[n] for n in dict.fromkeys(names) if n in catalogue_by_name])


def measure_cases(cases: list[dict[str, Any]], catalogue: list[dict[str, Any]]) -> dict[str, Any]:
    """Extraction on the 260-case set: recall on category D, false triggers elsewhere."""
    by_name = {e["name"]: e for e in catalogue}
    d_total = d_found = 0
    d_missed: list[dict[str, Any]] = []
    other_total = other_trigger = 0
    triggered: list[dict[str, Any]] = []
    for case in cases:
        function = (case.get("expect") or {}).get("function") or case.get("page_function")
        records = _records_for(by_name, [function] if function else [])
        terms = cg.guard_terms(case["question"], catalogue, records)
        if case["category"] == "D":
            truth = (case.get("expect") or {}).get("absent_terms") or []
            d_total += 1
            if any(_related(t, y) for t in terms for y in truth):
                d_found += 1
            else:
                d_missed.append({"id": case["id"], "question": case["question"], "truth": truth, "terms": terms})
        else:
            other_total += 1
            if terms:
                other_trigger += 1
                triggered.append({"id": case["id"], "question": case["question"][:100], "terms": terms})
    return {"d": [d_found, d_total], "d_missed": d_missed, "other": [other_trigger, other_total], "triggered": triggered}


# ------------------------------------------------------------------------------------------------------ 2. replay


def replay(run_dir: Path, catalogue: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_name = {e["name"]: e for e in catalogue}
    cases = {c["id"]: c for c in _load(run_dir / "typed_cases.jsonl")}
    result: dict[str, dict[str, Any]] = {}
    for writer_dir in sorted(p for p in run_dir.glob("typed_*") if p.is_dir()):
        writer = writer_dir.name.removeprefix("typed_")
        judged: dict[tuple[str, int], bool] = {}
        judgment_file = writer_dir / "judgments.jsonl"
        if judgment_file.exists():
            for j in _load(judgment_file):
                judged[(j["case_id"], int(j.get("rep", 0)))] = _opus_flagged(j.get("verdict"))
        rows = []
        for row in _load(writer_dir / "results.jsonl"):
            case = cases[row["case_id"]]
            text = row.get("text") or ""
            function = (case.get("expect") or {}).get("function") or case.get("page_function")
            records = _records_for(by_name, [*([function] if function else []), *(row.get("records_seen") or [])])
            terms, claims = cg.check_answer(case["question"], text, catalogue, records)
            truth = (case.get("expect") or {}).get("absent_terms") or []
            harness = typed_graders.unsupported_claims(text, list(truth)) if truth else []
            rows.append(
                {
                    "id": row["case_id"], "category": case["category"], "source": row.get("source"),
                    "question": case["question"], "terms": terms, "claims": sorted(set(claims)),
                    "harness_claims": sorted(set(harness)), "truth": truth,
                    "opus_flagged": judged.get((row["case_id"], int(row.get("rep", 0)))),
                    "text": text, "old_grade_support_failed": ((row.get("grade") or {}).get("checks") or {}).get("no_support_claim") is False,
                }
            )
        result[writer] = {"rows": rows}
    return result


def summarise_replay(rows: list[dict[str, Any]]) -> dict[str, Any]:
    live = [r for r in rows if r["source"] == "live" and r["text"]]
    d = [r for r in live if r["category"] == "D"]
    non_d = [r for r in live if r["category"] != "D"]
    fires = [r for r in live if r["claims"]]
    return {
        "answers": len(rows), "live": len(live),
        "guard_fires": len(fires),
        "d_live": len(d),
        "d_guard_fires": sum(1 for r in d if r["claims"]),
        "d_harness_fires": sum(1 for r in d if r["harness_claims"]),
        "d_both": sum(1 for r in d if r["claims"] and r["harness_claims"]),
        "d_guard_only": [r["id"] for r in d if r["claims"] and not r["harness_claims"]],
        "d_harness_only": [r["id"] for r in d if r["harness_claims"] and not r["claims"]],
        "non_d_live": len(non_d),
        "non_d_guard_fires": [r["id"] for r in non_d if r["claims"]],
        "non_d_with_terms": sum(1 for r in non_d if r["terms"]),
        "opus_judged": sum(1 for r in live if r["opus_flagged"] is not None),
        "opus_flagged": sum(1 for r in live if r["opus_flagged"]),
        "fires_on_opus_flagged": [r["id"] for r in fires if r["opus_flagged"]],
        "fires_on_opus_clean": [r["id"] for r in fires if r["opus_flagged"] is False],
        "fires_unjudged": [r["id"] for r in fires if r["opus_flagged"] is None],
    }


# ------------------------------------------------------------------------------------------------ 3. regressions


def sharpe_regression(catalogue: list[dict[str, Any]]) -> dict[str, Any]:
    entry = next(e for e in catalogue if e["name"] == "sharpe_ratio")
    terms, claims = cg.check_answer(SHARPE_QUESTION, SHARPE_ANSWER, catalogue, cg.trimmed([entry]))
    return {"terms": terms, "claims": claims, "caught": bool(claims)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", action="append", default=[], metavar="LABEL=DIR", help="a run directory (repeatable)")
    parser.add_argument("--show", action="store_true", help="print every answer the guard fires on")
    parser.add_argument("--json", metavar="FILE", help="write the full measurement as JSON")
    args = parser.parse_args(argv)

    catalogue = _catalogue()
    report: dict[str, Any] = {"frozen": measure_frozen(catalogue)}
    f = report["frozen"]
    print("== 1a. Extraction on the frozen varied set (capability_questions.jsonl)")
    print(f"   feature absent from the record, term found:      {f['absent'][0]}/{f['absent'][1]}")
    print(f"   feature stated in the record, guard stays out:   {f['present'][0]}/{f['present'][1]}")
    print(f"   not a capability question, guard stays out:      {f['other'][0]}/{f['other'][1]}")
    for item in f["failures"]:
        print(f"   FAIL {item['id']} [{item['kind']}] {item['question']!r}: phrase={item['phrase']!r} terms={item['terms']}")

    report["runs"] = {}
    for spec in args.run:
        if "=" not in spec:
            print(f"--run wants LABEL=DIR, got {spec!r}", file=sys.stderr)
            return 2
        label, _, directory = spec.partition("=")
        run_dir = Path(directory)
        if not (run_dir / "typed_cases.jsonl").exists():
            print(f"no typed_cases.jsonl in {run_dir}", file=sys.stderr)
            return 2
        cases = _load(run_dir / "typed_cases.jsonl")
        extraction = measure_cases(cases, catalogue)
        replayed = replay(run_dir, catalogue)
        report["runs"][label] = {"cases": len(cases), "extraction": extraction, "writers": {}}
        print(f"\n== 1b. Extraction on {label}: {len(cases)} cases")
        print(f"   category D (templated), term found:       {extraction['d'][0]}/{extraction['d'][1]}")
        print(f"   other categories with a guard term:       {extraction['other'][0]}/{extraction['other'][1]}")
        for m in extraction["d_missed"]:
            print(f"   MISSED {m['id']} {m['question']!r} truth={m['truth']} terms={m['terms']}")
        for t in extraction["triggered"]:
            print(f"   TRIGGERED {t['id']} {t['question']!r} terms={t['terms']}")
        for writer, data in replayed.items():
            s = summarise_replay(data["rows"])
            report["runs"][label]["writers"][writer] = {"summary": s}
            print(f"\n== 2. Replay {label}/{writer}: {s['answers']} answers, {s['live']} live")
            print(f"   guard would fail on the first try:        {s['guard_fires']} of {s['live']} live")
            print(f"   category D live {s['d_live']}: guard fires {s['d_guard_fires']}, harness (true term) fires {s['d_harness_fires']}, both {s['d_both']}")
            print(f"   D guard only: {s['d_guard_only']} | D harness only: {s['d_harness_only']}")
            print(f"   other categories: guard terms on {s['non_d_with_terms']} answers, fires on {s['non_d_guard_fires']}")
            print(f"   Opus judged {s['opus_judged']}, flagged {s['opus_flagged']}; guard fires on flagged {s['fires_on_opus_flagged']}, on clean {s['fires_on_opus_clean']}, unjudged {s['fires_unjudged']}")
            if args.show:
                for r in data["rows"]:
                    if r["claims"]:
                        print(f"   --- {r['id']} {r['question']!r} terms={r['terms']} claims={r['claims']} harness={r['harness_claims']}")
                        for sentence in graders._sentences(r["text"]):
                            if any(cg.term_pattern(t).search(sentence) for t in r["claims"]):
                                print(f"       > {sentence[:220]}")
            regress = [r for r in data["rows"] if r["category"] == "D" and r["old_grade_support_failed"] and not r["harness_claims"]]
            if regress:
                fired = [r["id"] for r in regress if r["claims"]]
                report["runs"][label]["writers"][writer]["regressions_9_27"] = {"ids": [r["id"] for r in regress], "guard_fires_on": fired}
                print(f"   9.27 misfires (old check failed, corrected check passes): {len(regress)}; guard fires on {fired}")
            report["runs"][label]["writers"][writer]["rows"] = [
                {k: v for k, v in r.items() if k != "text"} for r in data["rows"]
            ]

    sharpe = sharpe_regression(catalogue)
    report["sharpe_d_six_03"] = sharpe
    print("\n== 3. The real miss of 9.36 (D:six:03, the two quoted sentences)")
    print(f"   terms {sharpe['terms']}, claims {sharpe['claims']}: {'CAUGHT' if sharpe['caught'] else 'MISSED'}")
    shapes = measure_shapes(catalogue)
    report["shapes"] = shapes
    print("\n== 4. Claim detector on fixed phrasings (coverage of wording, not real traffic)")
    print(f"   claims caught:                  {shapes['claims'][0]}/{shapes['claims'][1]}")
    print(f"   non-claims left alone:          {shapes['non_claims'][0]}/{shapes['non_claims'][1]}")
    for s in shapes["claims_missed"]:
        print(f"   MISSED CLAIM  {s!r}")
    for s in shapes["non_claims_flagged"]:
        print(f"   FLAGGED NON-CLAIM  {s!r}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

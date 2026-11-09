"""The tools for the assistant's gain test: the blind side-by-side and the judge comparison.

Reasoning:
- Phase 0 never compared the model's text with what the catalogue already says, and an Opus judge for every
  answer is ruled out. docs/assistant-phase0-results.md section 9 sets out the two checks that replace them:
  a blind side-by-side read by a person, and a cheaper judge measured against the Opus verdicts already paid
  for. These tests pin the properties the checks rely on: the choice of cases is repeatable and spread, the page
  never says which answer is which, the key matches the page, the comparison counts what it claims to, and a
  cheaper judge can never overwrite the reference verdicts.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO / "scripts" / "assistant_eval"))

import compare_judges  # noqa: E402
import judge  # noqa: E402
import side_by_side as sbs  # noqa: E402

DOMAINS = ["Market Risk", "Credit Risk", "ALM", "Liquidity", "Operational", "Regulatory"]


def _record(name: str, domain: str) -> dict[str, Any]:
    return {
        "name": name,
        "display_name": name.replace("_", " ").title(),
        "domain": domain,
        "summary": f"Computes the {name} figure.",
        "description": "Uses :func:`other_fn` and a ``cap`` of the inputs.   Second sentence.",
        "parameters": [
            {
                "name": "alpha",
                "type": "number",
                "required": True,
                "default": None,
                "description": "Confidence level.",
            },
            {
                "name": "beta",
                "type": "number",
                "required": False,
                "default": 1,
                "description": None,
            },
        ],
    }


def _cases(per_action: int = 8) -> list[dict[str, Any]]:
    out = []
    for action in ("explain", "when", "compare", "example"):
        for i in range(per_action):
            name = f"fn_{action}_{i}"
            case: dict[str, Any] = {
                "id": f"{name}:{action}",
                "intent": action,
                "record": _record(name, DOMAINS[i % len(DOMAINS)]),
                "siblings": [{"name": f"sib_{j}", "summary": f"Sibling {j}."} for j in range(8)],
                "other": _record(f"other_{i}", "Market Risk") if action == "compare" else None,
            }
            out.append(case)
    return out


# ── pick ────────────────────────────────────────────────────────────────────────────────────────────


def test_pick_is_repeatable_spread_and_independent_of_case_order() -> None:
    cases = _cases()
    ids = sbs.pick(cases)
    assert len(ids) == 12 and len(set(ids)) == 12
    shuffled = cases[:]
    random.Random(1).shuffle(shuffled)
    assert sbs.pick(shuffled) == ids
    by_id = {c["id"]: c for c in cases}
    for start in (0, 4, 8):
        group = ids[start : start + 4]
        assert {by_id[i]["intent"] for i in group} == {("explain", "when", "compare")[start // 4]}
        assert len({by_id[i]["record"]["domain"] for i in group}) == 4, "a new domain each time"
    assert sbs.pick(cases, seed="other") != ids
    assert not any(
        by_id[i]["intent"] == "example" for i in ids
    ), "example values are not in this test"


def test_pick_fills_from_repeated_domains_when_there_are_too_few() -> None:
    cases = [
        c for c in _cases() if c["record"]["domain"] in DOMAINS[:2] or c["intent"] != "explain"
    ]
    assert len(sbs.pick(cases)) == 12


# ── export ──────────────────────────────────────────────────────────────────────────────────────────


def _run(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    (run / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (run / "summary.json").write_text(json.dumps({"model": "m1", "prompt_version": "v2-test"}))
    return run


def test_export_returns_the_scored_answers_with_their_provenance(tmp_path: Path) -> None:
    run = _run(
        tmp_path,
        [
            {"case_id": "a:explain", "rep": 0, "status": "ok", "text": "alpha text"},
            {"case_id": "b:when", "rep": 0, "status": "ok", "text": "beta text"},
            {"case_id": "c:when", "rep": 0, "status": "truncated", "text": "clipped"},
        ],
    )
    out = sbs.export(run, ["b:when", "a:explain"])
    assert out == {
        "model": "m1",
        "prompt_version": "v2-test",
        "answers": {"b:when": "beta text", "a:explain": "alpha text"},
    }
    with pytest.raises(SystemExit) as info:
        sbs.export(run, ["a:explain", "c:when", "zzz:when"])
    assert "c:when" in str(info.value) and "zzz:when" in str(info.value)


# ── the static answer ───────────────────────────────────────────────────────────────────────────────


def test_static_answers_say_what_the_catalogue_says_and_nothing_else() -> None:
    cases = {c["intent"]: c for c in _cases(1)}
    explain = sbs.static_answer(cases["explain"])
    assert "Computes the fn_explain_0 figure." in explain
    assert (
        "`alpha` (required): Confidence level." in explain
        and "`beta` (optional, default 1)" in explain
    )
    assert (
        ":func:" not in explain
        and "``" not in explain
        and "Uses other_fn and a `cap` of the inputs." in explain
    )
    when = sbs.static_answer(cases["when"])
    assert "Related functions:" in when and when.count("- `sib_") == 6, "at most six siblings"
    compare = sbs.static_answer(cases["compare"])
    assert "`fn_compare_0`" in compare and "`other_0`" in compare
    with pytest.raises(ValueError):
        sbs.static_answer(cases["example"])


def test_questions_are_the_menu_choices() -> None:
    cases = {c["intent"]: c for c in _cases(1)}
    assert sbs.question(cases["explain"]) == "What does Fn Explain 0 do?"
    assert sbs.question(cases["when"]) == "When should I use Fn When 0?"
    assert sbs.question(cases["compare"]) == "How does Fn Compare 0 differ from Other 0?"


# ── the blind page ──────────────────────────────────────────────────────────────────────────────────


def _answers(ids: list[str]) -> dict[str, str]:
    return {i: f"MODEL-ANSWER-{n} says something useful." for n, i in enumerate(ids)}


def test_the_page_is_blind_deterministic_and_matches_its_key() -> None:
    cases = {c["id"]: c for c in _cases()}
    ids = sbs.pick(list(cases.values()))
    answers = _answers(ids)
    page, key = sbs.build(cases, answers)
    assert (page, key) == sbs.build(cases, answers), "same seed, same page"
    assert page != sbs.build(cases, answers, seed="another")[0]
    assert len(key) == 12 and [k["n"] for k in key] == list(range(1, 13))
    shell = re.sub(r'<div class="txt">.*?</div>', "", page, flags=re.S)
    assert not re.search(r"static|haiku|catalogue|\bmodel\b|generated|written by", shell, re.I)
    texts = re.findall(
        r'<div class="side">([AB])</div><div class="txt">(.*?)</div>', page, flags=re.S
    )
    assert len(texts) == 24
    for n, entry in enumerate(key):
        (side_a, text_a), (side_b, text_b) = texts[2 * n], texts[2 * n + 1]
        assert (side_a, side_b) == ("A", "B")
        model_text = answers[entry["case_id"]]
        assert (entry["A"], entry["B"]) in {("model", "static"), ("static", "model")}
        assert (text_a if entry["A"] == "model" else text_b) == model_text
    assert {k["A"] for k in key} == {"model", "static"}, "both sides are used"


def test_the_page_escapes_what_it_shows() -> None:
    cases = {c["id"]: c for c in _cases()}
    ids = sbs.pick(list(cases.values()))
    page, _ = sbs.build(cases, {**_answers(ids), ids[0]: "<script>alert(1)</script> & more"})
    assert (
        "<script>alert(1)</script>" not in page
        and "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more" in page
    )


# ── comparing judges ────────────────────────────────────────────────────────────────────────────────


def _rows(
    flags: list[bool | None], action: str = "when", plausible: list[bool | None] | None = None
) -> dict:
    rows = {}
    for i, unfaithful in enumerate(flags):
        verdict = {"faithful": None if unfaithful is None else not unfaithful, "useful": True}
        if unfaithful is None:
            verdict["faithful"] = True
        if plausible is not None:
            verdict["plausible_values"] = plausible[i]
        rows[f"c{i}"] = {"case_id": f"c{i}", "intent": action, "verdict": verdict}
    return rows


def test_a_cheaper_judge_is_counted_against_the_reference() -> None:
    ref = [True] * 10 + [False] * 30
    other = [True] * 8 + [False] * 2 + [True] * 3 + [False] * 27
    result = compare_judges.compare([(_rows(ref), _rows(other))], "faithful")["pooled"]
    assert (
        result["n"],
        result["reference_flagged"],
        result["other_flagged"],
        result["both_flagged"],
    ) == (40, 10, 11, 8)
    assert (
        result["recall"] == 0.8
        and result["false_alarms"] == 3
        and result["false_alarm_rate"] == 0.1
    )
    assert result["agreement"] == 0.875 and result["kappa"] > 0.6
    assert result["verdict"] == "meets the thresholds"
    assert result["recall_ci95"][0] < 0.8 < result["recall_ci95"][1]


def test_the_verdict_is_cannot_tell_with_few_flags_and_fails_a_weak_judge() -> None:
    few = compare_judges.compare(
        [(_rows([True] * 5 + [False] * 35), _rows([True] * 5 + [False] * 35))], "faithful"
    )
    assert few["pooled"]["verdict"].startswith("cannot tell")
    weak = compare_judges.compare(
        [(_rows([True] * 10 + [False] * 30), _rows([True] * 4 + [False] * 36))], "faithful"
    )
    assert (
        weak["pooled"]["recall"] == 0.4
        and weak["pooled"]["verdict"] == "does not meet the thresholds"
    )
    noisy = compare_judges.compare(
        [(_rows([True] * 10 + [False] * 30), _rows([True] * 10 + [True] * 15 + [False] * 15))],
        "faithful",
    )
    assert (
        noisy["pooled"]["false_alarm_rate"] == 0.5
        and noisy["pooled"]["verdict"] == "does not meet the thresholds"
    )
    assert len(weak["missed_by_the_other_judge"]) == 6


def test_files_are_paired_separately_even_when_case_ids_repeat() -> None:
    first = (_rows([True, False, False]), _rows([True, False, False]))
    second = (_rows([False, True, False]), _rows([True, False, False]))  # same ids, other answers
    pooled = compare_judges.compare([first, second], "faithful")["pooled"]
    assert pooled["n"] == 6 and pooled["both_flagged"] == 1 and pooled["reference_flagged"] == 2
    assert [
        m["pair"]
        for m in compare_judges.compare([first, second], "faithful")["missed_by_the_other_judge"]
    ] == ["1"]


def test_not_applicable_fields_are_skipped_and_actions_are_reported() -> None:
    ref = _rows([False] * 4, action="example:stress", plausible=[False, True, None, True])
    other = _rows([False] * 4, action="example:stress", plausible=[False, True, True, None])
    result = compare_judges.compare([(ref, other)], "plausible_values")
    assert (
        result["pooled"]["n"] == 2
    ), "rows where either side has no plausibility verdict are left out"
    assert list(result["by_action"]) == ["example:stress"]


def test_load_skips_unparsed_verdicts(tmp_path: Path) -> None:
    path = tmp_path / "j.jsonl"
    path.write_text(
        json.dumps({"case_id": "a", "verdict": None})
        + "\n"
        + json.dumps({"case_id": "b", "verdict": {"faithful": True}})
        + "\n"
    )
    assert list(compare_judges.load(path)) == ["b"]


# ── the judge keeps the reference verdicts ──────────────────────────────────────────────────────────


def test_another_judge_cannot_overwrite_the_default_judges_verdicts(tmp_path: Path) -> None:
    assert judge.output_paths(tmp_path)[0].name == "judgments.jsonl"
    names = [p.name for p in judge.output_paths(tmp_path, "haiku")]
    assert names == [
        "judgments_haiku.jsonl",
        "judge_errors_haiku.jsonl",
        "judge_summary_haiku.json",
    ]
    assert not judge.refuses_to_overwrite(
        tmp_path, "claude-haiku-5-5", ""
    )  # nothing to overwrite yet
    judge.output_paths(tmp_path)[0].write_text("{}\n")
    assert judge.refuses_to_overwrite(tmp_path, "claude-haiku-5-5", "")
    assert not judge.refuses_to_overwrite(tmp_path, "claude-haiku-5-5", "haiku")
    assert not judge.refuses_to_overwrite(
        tmp_path, judge.DEFAULT_JUDGE, ""
    ), "the default judge may re-run"


def test_actions_limit_what_is_counted() -> None:
    ref = {
        **_rows([True, False], action="when"),
        **{f"x{i}": r for i, r in enumerate(_rows([False] * 3, action="example:typical").values())},
    }
    other = {
        **_rows([True, False], action="when"),
        **{f"x{i}": r for i, r in enumerate(_rows([False] * 3, action="example:typical").values())},
    }
    assert compare_judges.compare([(ref, other)], "faithful")["pooled"]["n"] == 5
    only = compare_judges.compare([(ref, other)], "faithful", {"when"})
    assert only["pooled"]["n"] == 2 and list(only["by_action"]) == ["when"]

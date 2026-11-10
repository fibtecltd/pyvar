"""The recall check: a person reads answers Opus passed, to see what it missed.

Reasoning:
- docs/assistant-phase0-results.md 9.10 leaves one question open: whether Opus can gate model-written text at
  build time. Its precision held where checked; its recall is unknown. These tests pin what the check relies on:
  the strata come from the Opus verdicts of the run itself (never from a list of ids, which is what was lost
  with the first draw), the sample is repeatable and drawn by a hash, the export carries everything a lost machine
  would otherwise take with it, and the page never says which stratum an item is from (or that Opus is
  involved), so the reader cannot be steered.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO / "scripts" / "assistant_eval"))

import cases as case_builder  # noqa: E402
import recall_check as rc  # noqa: E402


def _record(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "display_name": name.replace("_", " ").title(),
        "domain": "Market Risk",
        "summary": f"Computes the {name} <figure>.",
        "description": "Uses :func:`other_fn` and a ``cap``.   Second sentence.",
        "parameters": [
            {"name": "alpha", "required": True, "default": None, "description": "Confidence."},
            {"name": "beta", "required": False, "default": 1, "description": None},
        ],
    }


def _cases(per_action: int = 30) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for action in ("explain", "when", "compare", "example"):
        for i in range(per_action):
            name = f"fn_{action}_{i}"
            out[f"{name}:{action}"] = {
                "id": f"{name}:{action}",
                "intent": action,
                "record": _record(name),
                "siblings": [{"name": "sib_a", "summary": "Does the A thing."}],
                "other": _record(f"other_{i}") if action == "compare" else None,
            }
    return out


CONFIG: dict[str, Any] = {
    "seed": "test-seed",
    "clean": 6,
    "clean_more": 5,
    "noted": 3,
    "flagged": 2,
}
FLAGGED = [f"fn_when_{i}:when" for i in range(4)]
NOTED = [f"fn_explain_{i}:explain" for i in range(10)]
UNPARSED = ["fn_compare_0:compare", "fn_compare_1:compare"]


def _judgments(cases: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for case_id, case in cases.items():
        if case["intent"] == "example":
            verdict: dict[str, Any] | None = {"faithful": False, "issues": ["not a text case"]}
        elif case_id in FLAGGED:
            verdict = {"faithful": False, "issues": [f"wrong claim in {case_id}", "x" * 500]}
        elif case_id in NOTED:
            verdict = {"faithful": True, "issues": [f"a doubt about {case_id}"]}
        elif case_id == UNPARSED[0]:
            verdict = None
        elif case_id == UNPARSED[1]:
            verdict = {"useful": True}
        else:
            verdict = {"faithful": True, "issues": []}
        rows.append({"case_id": case_id, "verdict": verdict})
    return rows


def _run(tmp_path: Path, cases: dict[str, dict[str, Any]], drop: str | None = None) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    results = [
        {"case_id": i, "status": "ok", "rep": 0, "text": f"answer for {i}"}
        for i in cases
        if i != drop
    ]
    (run / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in results))
    (run / "judgments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in _judgments(cases)))
    (run / "summary.json").write_text(json.dumps({"model": "m1", "prompt_version": "v4-test"}))
    return run


# ── the pools come from the verdicts ────────────────────────────────────────────────────────────────


def test_the_pools_are_what_opus_said_about_the_text_answers() -> None:
    cases = _cases()
    groups = rc.pools(cases, _judgments(cases))
    assert groups["flagged"] == sorted(FLAGGED)
    assert groups["noted"] == sorted(NOTED)
    assert groups["unparsed"] == sorted(UNPARSED)
    assert len(groups["clean"]) == 90 - len(FLAGGED) - len(NOTED) - len(UNPARSED)
    everything = [i for ids in groups.values() for i in ids]
    assert len(set(everything)) == len(everything) == 90, "each text case is in exactly one pool"
    assert not any(i.endswith(":example") for i in everything), "text answers only"


def test_a_verdict_for_an_unknown_case_is_ignored() -> None:
    cases = _cases()
    rows = _judgments(cases) + [{"case_id": "nope:when", "verdict": {"faithful": False}}]
    assert "nope:when" not in sum(rc.pools(cases, rows).values(), [])


# ── the draw ────────────────────────────────────────────────────────────────────────────────────────


def _drawn(cases: dict[str, dict[str, Any]] | None = None) -> dict[str, list[str]]:
    cases = cases or _cases()
    return rc.draw(rc.pools(cases, _judgments(cases)), CONFIG)


def test_the_draw_has_the_sizes_asked_for_comes_from_the_right_pool_and_never_overlaps() -> None:
    drawn = _drawn()
    assert {k: len(v) for k, v in drawn.items()} == {
        "clean": 6,
        "clean_more": 5,
        "noted": 3,
        "flagged": 2,
    }
    assert set(drawn["noted"]) <= set(NOTED) and set(drawn["flagged"]) <= set(FLAGGED)
    assert not set(drawn["clean"] + drawn["clean_more"]) & (
        set(NOTED) | set(FLAGGED) | set(UNPARSED)
    )
    everything = [i for ids in drawn.values() for i in ids]
    assert len(set(everything)) == len(everything)


def test_the_draw_is_repeatable_and_independent_of_the_order_of_the_verdicts() -> None:
    cases = _cases()
    rows = _judgments(cases)
    drawn = rc.draw(rc.pools(cases, rows), CONFIG)
    random.Random(3).shuffle(rows)
    assert rc.draw(rc.pools(cases, rows), CONFIG) == drawn
    other = rc.draw(rc.pools(cases, rows), {**CONFIG, "seed": "other"})
    assert other["clean"] != drawn["clean"]


def test_a_bigger_first_batch_starts_with_the_same_answers() -> None:
    cases = _cases()
    groups = rc.pools(cases, _judgments(cases))
    assert rc.draw(groups, {**CONFIG, "clean": 9})["clean"][:6] == rc.draw(groups, CONFIG)["clean"]


def test_a_pool_smaller_than_asked_gives_what_it_has() -> None:
    groups = {"flagged": ["a:when"], "noted": [], "clean": ["b:when", "c:when"], "unparsed": []}
    drawn = rc.draw(groups, CONFIG)
    assert drawn["flagged"] == ["a:when"] and drawn["noted"] == []
    assert len(drawn["clean"]) == 2 and drawn["clean_more"] == []


def test_stage_two_is_only_the_second_batch_of_clean_answers() -> None:
    drawn = _drawn()
    assert rc.stage_ids(drawn, 2) == drawn["clean_more"]
    assert rc.stage_ids(drawn, 1) == drawn["clean"] + drawn["noted"] + drawn["flagged"]


# ── export: everything a lost machine would take with it ────────────────────────────────────────────


def test_export_stage_one_carries_the_answers_strata_pools_and_what_opus_said(
    tmp_path: Path,
) -> None:
    cases = _cases()
    out = rc.export(cases, _run(tmp_path, cases), CONFIG)
    drawn = _drawn(cases)
    assert set(out["answers"]) == set(rc.stage_ids(drawn, 1)) == set(out["strata"])
    assert out["answers"][drawn["noted"][0]] == f"answer for {drawn['noted'][0]}"
    assert out["model"] == "m1" and out["prompt_version"] == "v4-test" and out["stage"] == 1
    assert out["pools"] == {"flagged": 4, "noted": 10, "clean": 74, "unparsed": 2}
    assert out["all_flagged"] == sorted(FLAGGED), "every flagged id, not only the drawn ones"
    assert out["all_noted"] == sorted(NOTED)
    assert set(out["opus"]) == set(drawn["noted"]) | set(drawn["flagged"]), "nothing for clean ones"
    flagged_id = drawn["flagged"][0]
    assert out["opus"][flagged_id]["faithful"] is False
    assert out["opus"][flagged_id]["issues"][0] == f"wrong claim in {flagged_id}"
    assert all(len(x) <= rc.ISSUE_CHARS for x in out["opus"][flagged_id]["issues"])


def test_export_stage_two_is_only_the_second_batch_and_has_no_pools(tmp_path: Path) -> None:
    cases = _cases()
    out = rc.export(cases, _run(tmp_path, cases), CONFIG, 2)
    assert set(out["answers"]) == set(_drawn(cases)["clean_more"])
    assert set(out["strata"].values()) == {"clean_more"} and out["opus"] == {}
    assert "pools" not in out and "all_flagged" not in out and out["stage"] == 2


def test_export_refuses_a_missing_answer(tmp_path: Path) -> None:
    cases = _cases()
    victim = _drawn(cases)["noted"][0]
    with pytest.raises(SystemExit, match="no scored answer"):
        rc.export(cases, _run(tmp_path, cases, drop=victim), CONFIG)


# ── the page ────────────────────────────────────────────────────────────────────────────────────────


def _page(tmp_path: Path, stage: int = 1) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    cases = _cases()
    data = rc.export(cases, _run(tmp_path, cases), CONFIG, stage)
    data["answers"] = {i: f"ANSWER-{i} <b>x</b>" for i in data["answers"]}
    page, key = rc.build(cases, data["answers"], data["strata"], data["seed"])
    return page, key, data


def test_the_page_shows_the_entry_and_the_answer_for_every_item_and_escapes_both(
    tmp_path: Path,
) -> None:
    page, key, data = _page(tmp_path)
    total = len(data["answers"])
    assert total == 11 and len(key) == total == page.count('class="item"')
    assert f"Item 1 of {total}" in page and f"Item {total} of {total}" in page
    some = next(iter(data["answers"]))
    assert f"ANSWER-{some} &lt;b&gt;x&lt;/b&gt;" in page and "<b>x</b>" not in page
    assert "&lt;figure&gt;." in page, "the record text is escaped too"
    assert "Uses other_fn and a `cap`. Second sentence." in page
    assert "<code>alpha</code> (required): Confidence." in page
    assert "<code>beta</code> (optional, default 1)" in page


def test_a_when_item_lists_the_related_functions_and_a_compare_item_shows_both_entries(
    tmp_path: Path,
) -> None:
    cases = _cases()
    answers = {"fn_when_5:when": "w", "fn_compare_7:compare": "c"}
    strata = dict.fromkeys(answers, "clean")
    page, _ = rc.build(cases, answers, strata, "s")
    assert "Related functions the guide could name" in page and "Does the A thing." in page
    assert "<code>fn_compare_7</code>" in page and "<code>other_7</code>" in page


def test_the_page_never_says_which_stratum_an_item_is_from_or_that_opus_is_involved(
    tmp_path: Path,
) -> None:
    page, _, _ = _page(tmp_path)
    visible = page.lower()
    for word in (
        "opus",
        "flagged",
        "stratum",
        "recall",
        "clean",
        "noted",
        "judge",
        "haiku",
        "model",
    ):
        assert word not in visible, word


def test_the_key_matches_the_page_and_the_order_is_a_hash_not_the_strata(tmp_path: Path) -> None:
    page, key, data = _page(tmp_path)
    assert [k["n"] for k in key] == list(range(1, len(data["answers"]) + 1))
    assert {k["case_id"] for k in key} == set(data["answers"])
    assert {k["case_id"]: k["stratum"] for k in key} == data["strata"]
    order = [k["stratum"] for k in key]
    assert order != sorted(order), "the strata are mixed, not listed in blocks"
    ranked = sorted(data["answers"], key=lambda i: rc._rank(data["seed"], "order:" + i))
    assert [k["case_id"] for k in key] == ranked


def test_stage_two_builds_a_page_of_only_the_second_batch(tmp_path: Path) -> None:
    page, key, data = _page(tmp_path, 2)
    assert len(key) == 5 and {k["stratum"] for k in key} == {"clean_more"}
    assert "Item 5 of 5" in page


def test_build_refuses_answers_and_strata_for_different_ids() -> None:
    with pytest.raises(SystemExit, match="not for the same ids"):
        rc.build(_cases(), {"fn_explain_29:explain": "x"}, {"fn_explain_28:explain": "clean"}, "s")


def test_the_results_script_writes_one_line_per_item_in_a_fixed_format(tmp_path: Path) -> None:
    page, _, _ = _page(tmp_path)
    assert "'answer-check v1'" in page
    assert 'value="OK"' in page and 'value="ERR"' in page
    assert "(v ? v.value : '-')" in page, "an unmarked item reads '-', never a pass"


# ── the whole record is on the page ─────────────────────────────────────────────────────────────────


def test_every_field_of_every_real_record_is_on_the_page() -> None:
    """2026-11-10: the first reading of this check hid the formula, the symbols and the caveat, which the guide
    had been given. Five of its six errors on clean answers were claims those fields support, so the reading
    could not be used. Every field `cases.trim_record` hands the guide must be visible to the reader.
    """
    entries = json.loads((REPO / "portal" / "functions.json").read_text())
    assert len(entries) > 300
    for entry in entries:
        record = case_builder.trim_record(entry)
        page = rc._record_html(record)
        assert set(record) == set(rc.SHOWN_FIELDS), "trim_record gained or lost a field: show it"
        if record["formula_latex"]:
            assert rc.html.escape(str(record["formula_latex"])) in page, entry["name"]
        if record["caveat"]:
            assert rc.html.escape(rc._plain(str(record["caveat"]))) in page, entry["name"]
        if record["citation"]:
            assert rc.html.escape(str(record["citation"])) in page, entry["name"]
        for symbol, value in (record["symbol_map"] or {}).items():
            assert (
                f"<code>{rc.html.escape(str(symbol))}</code> is <code>{rc.html.escape(str(value))}</code>"
                in page
            )
        for p in record["parameters"]:
            assert (
                f"<code>{rc.html.escape(p['name'])}</code> ({rc.html.escape(p['type'])}, " in page
            ), entry["name"]
        assert (
            rc.html.escape(record["domain"]) in page
            and rc.html.escape(rc._plain(record["summary"])) in page
        )


def test_a_field_the_page_does_not_know_is_shown_as_json_never_dropped() -> None:
    record = {**_record("fn_x"), "caveat": "Sums <three> ratios.", "new_field": {"k": [1, 2]}}
    page = rc._record_html(record)
    assert "Sums &lt;three&gt; ratios." in page
    assert "new_field" in page and "[1, 2]" in page


def test_the_second_entry_of_a_compare_item_shows_its_formula_too() -> None:
    other = {
        **_record("fn_other"),
        "formula_latex": r"X=\alpha+\beta",
        "symbol_map": {"alpha": "a"},
    }
    case = {
        "id": "fn_a:compare",
        "intent": "compare",
        "record": _record("fn_a"),
        "siblings": [],
        "other": other,
    }
    page, _ = rc.build({case["id"]: case}, {case["id"]: "x"}, {case["id"]: "clean"}, "s")
    assert r"X=\alpha+\beta" in page and "<code>alpha</code> is <code>a</code>" in page


# ── the command line and the config in docs/ ────────────────────────────────────────────────────────


def test_the_command_line_runs_pick_export_and_build_end_to_end(tmp_path: Path) -> None:
    cases = _cases()
    cases_file = tmp_path / "cases.jsonl"
    cases_file.write_text("".join(json.dumps(c) + "\n" for c in cases.values()))
    run = _run(tmp_path, cases)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(CONFIG))
    script = str(REPO / "scripts" / "assistant_eval" / "recall_check.py")
    base = [sys.executable, script]

    def call(*args: str) -> str:
        done = subprocess.run(
            [*base, *args], capture_output=True, text=True, check=True, timeout=60
        )
        return done.stdout

    picked = json.loads(
        call("pick", "--cases", str(cases_file), "--run", str(run), "--config", str(config))
    )
    assert picked["pools"]["flagged"] == 4 and len(picked["clean"]) == 6
    exported = tmp_path / "stage1.json"
    exported.write_text(
        call("export", "--cases", str(cases_file), "--run", str(run), "--config", str(config))
    )
    call(
        "build", "--cases", str(cases_file), "--answers", str(exported),
        "--out", str(tmp_path / "page.html"), "--key", str(tmp_path / "key.json"),
    )  # fmt: skip
    assert "Item 11 of 11" in (tmp_path / "page.html").read_text()
    assert len(json.loads((tmp_path / "key.json").read_text())) == 11


def test_the_real_config_has_sizes_and_a_seed_and_no_ids() -> None:
    config = json.loads(rc.DEFAULT_CONFIG.read_text())
    assert config == {
        "seed": "recall-check-1",
        "clean": 40,
        "clean_more": 40,
        "noted": 12,
        "flagged": 4,
    }

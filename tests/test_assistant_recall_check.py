"""The recall check: a person reads answers Opus passed, to see what it missed.

Reasoning:
- docs/assistant-phase0-results.md 9.10 leaves one question open: whether Opus can gate model-written text at
  build time. Its precision held where checked; its recall is unknown. These tests pin what the check relies on:
  the sample is repeatable and drawn by a hash, the strata never overlap, the export refuses answers whose Opus
  verdict does not match the stratum they were drawn for, and the page never says which stratum an item is from
  (or that Opus is involved), so the reader cannot be steered.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO / "scripts" / "assistant_eval"))

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


FLAGGED = ["fn_when_0:when", "fn_when_1:when", "fn_explain_0:explain", "fn_compare_0:compare"]
CONFIG: dict[str, Any] = {
    "seed": "test-seed",
    "clean": 6,
    "clean_more": 5,
    "noted": 3,
    "flagged_already_read": ["fn_when_0:when"],
    "noted_passes": [f"fn_explain_{i}:explain" for i in range(10, 16)],
}


def _groups(cases: dict[str, dict[str, Any]] | None = None) -> dict[str, list[str]]:
    return rc.strata(cases or _cases(), CONFIG, FLAGGED)


# ── strata ──────────────────────────────────────────────────────────────────────────────────────────


def test_the_strata_have_the_sizes_asked_for_and_never_overlap() -> None:
    groups = _groups()
    assert {k: len(v) for k, v in groups.items()} == {
        "clean": 6,
        "clean_more": 5,
        "noted": 3,
        "flagged": 3,
    }
    everything = [i for ids in groups.values() for i in ids]
    assert len(set(everything)) == len(everything)
    assert not set(groups["clean"] + groups["clean_more"]) & (
        set(FLAGGED) | set(CONFIG["noted_passes"])
    )
    assert set(groups["noted"]) <= set(CONFIG["noted_passes"])
    assert "fn_when_0:when" not in groups["flagged"], "the flagged answer already read is left out"
    assert all(rc_id.rsplit(":", 1)[-1] != "example" for rc_id in everything), "text answers only"


def test_the_draw_is_repeatable_and_does_not_depend_on_the_order_of_the_cases() -> None:
    cases = _cases()
    groups = _groups(cases)
    shuffled = list(cases.items())
    random.Random(3).shuffle(shuffled)
    assert _groups(dict(shuffled)) == groups
    assert rc.strata(cases, {**CONFIG, "seed": "other"}, FLAGGED)["clean"] != groups["clean"]


def test_a_bigger_first_batch_starts_with_the_same_answers() -> None:
    small = _groups()
    big = rc.strata(_cases(), {**CONFIG, "clean": 9}, FLAGGED)
    assert big["clean"][:6] == small["clean"]


def test_ids_that_are_not_text_cases_or_that_clash_are_refused() -> None:
    with pytest.raises(SystemExit, match="not text cases"):
        rc.strata(_cases(), CONFIG, FLAGGED + ["fn_explain_0:example"])
    with pytest.raises(SystemExit, match="not text cases"):
        rc.strata(_cases(), CONFIG, FLAGGED + ["no_such_case:when"])
    with pytest.raises(SystemExit, match="both flagged"):
        rc.strata(_cases(), CONFIG, FLAGGED + [CONFIG["noted_passes"][0]])


def test_stage_two_is_only_the_second_batch_of_clean_answers() -> None:
    groups = _groups()
    assert rc.stage_ids(groups, 2) == groups["clean_more"]
    assert rc.stage_ids(groups, 1) == groups["clean"] + groups["noted"] + groups["flagged"]


# ── the check against Opus's verdicts ───────────────────────────────────────────────────────────────


def _verdicts(groups: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for stratum, ids in groups.items():
        for case_id in ids:
            out[case_id] = {
                "faithful": stratum != "flagged",
                "issues": ["x"] if stratum in ("noted", "flagged") else [],
            }
    return out


def test_a_stratum_that_matches_the_verdicts_has_no_problems() -> None:
    groups = _groups()
    assert rc.check_verdicts(groups, _verdicts(groups)) == []


def test_each_way_a_stratum_can_disagree_with_opus_is_named() -> None:
    groups = _groups()
    verdicts = _verdicts(groups)
    clean, noted, flagged = groups["clean"][0], groups["noted"][0], groups["flagged"][0]
    verdicts[clean]["faithful"] = False
    verdicts[groups["clean"][1]]["issues"] = ["something"]
    verdicts[noted]["issues"] = []
    verdicts[flagged]["faithful"] = True
    del verdicts[groups["clean_more"][0]]
    problems = " | ".join(rc.check_verdicts(groups, verdicts))
    assert f"{clean}: drawn as passed but Opus flagged it" in problems
    assert f"{groups['clean'][1]}: drawn as clean but Opus noted issues" in problems
    assert f"{noted}: drawn as noted but Opus noted none" in problems
    assert f"{flagged}: drawn as flagged but Opus passed it" in problems
    assert f"{groups['clean_more'][0]}: no Opus verdict" in problems


# ── export ──────────────────────────────────────────────────────────────────────────────────────────


def _run(tmp_path: Path, groups: dict[str, list[str]], verdicts: dict[str, Any]) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    ids = [i for ids in groups.values() for i in ids]
    rows = [{"case_id": i, "status": "ok", "rep": 0, "text": f"answer for {i}"} for i in ids]
    (run / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    judged = [{"case_id": i, "verdict": verdicts[i]} for i in ids if i in verdicts]
    (run / "judgments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in judged))
    (run / "summary.json").write_text(json.dumps({"model": "m1", "prompt_version": "v4-test"}))
    return run


def test_export_returns_the_stage_one_answers_and_leaves_the_verdicts_out(tmp_path: Path) -> None:
    groups = _groups()
    out = rc.export(_run(tmp_path, groups, _verdicts(groups)), groups)
    assert set(out["answers"]) == set(rc.stage_ids(groups, 1))
    assert out["model"] == "m1" and out["prompt_version"] == "v4-test"
    assert "faithful" not in json.dumps(out) and "issues" not in json.dumps(out)
    again = tmp_path / "again"
    again.mkdir()
    stage_two = rc.export(_run(again, groups, _verdicts(groups)), groups, 2)
    assert set(stage_two["answers"]) == set(groups["clean_more"])


def test_export_refuses_a_run_whose_verdicts_do_not_match_the_draw(tmp_path: Path) -> None:
    groups = _groups()
    verdicts = _verdicts(groups)
    verdicts[groups["clean"][0]]["faithful"] = False
    with pytest.raises(SystemExit, match="drawn as passed but Opus flagged it"):
        rc.export(_run(tmp_path, groups, verdicts), groups)


def test_export_refuses_a_missing_answer(tmp_path: Path) -> None:
    groups = _groups()
    run = _run(tmp_path, groups, _verdicts(groups))
    kept = [
        line
        for line in (run / "results.jsonl").read_text().splitlines()
        if groups["noted"][0] not in line
    ]
    (run / "results.jsonl").write_text("\n".join(kept) + "\n")
    with pytest.raises(SystemExit, match="no scored answer"):
        rc.export(run, groups)


# ── the page ────────────────────────────────────────────────────────────────────────────────────────


def _page(stage: int = 1) -> tuple[str, list[dict[str, Any]], dict[str, str]]:
    cases, groups = _cases(), _groups()
    answers = {i: f"ANSWER-{i} <b>x</b>" for i in rc.stage_ids(groups, stage)}
    page, key = rc.build(cases, answers, groups, CONFIG["seed"])
    return page, key, answers


def test_the_page_shows_the_entry_and_the_answer_for_every_item_and_escapes_both() -> None:
    page, key, answers = _page()
    assert len(key) == len(answers) == page.count('class="item"')
    assert "Item 1 of 12" in page and "Item 12 of 12" in page
    assert "ANSWER-fn_explain_10:explain &lt;b&gt;x&lt;/b&gt;" in page
    assert "<b>x</b>" not in page
    assert "Computes the fn_explain_10 &lt;figure&gt;." in page
    assert "Uses other_fn and a `cap`. Second sentence." in page
    assert "<code>alpha</code> (required): Confidence." in page
    assert "<code>beta</code> (optional, default 1)" in page


def test_a_when_item_lists_the_related_functions_and_a_compare_item_shows_both_entries() -> None:
    page, key, _ = _page()
    assert "Related functions the guide could name" in page and "Does the A thing." in page
    compare = next(k for k in key if k["action"] == "compare")["case_id"]
    index = compare.split("_")[2].split(":")[0]
    assert f"<code>other_{index}</code>" in page, "the second function's entry is shown too"


def test_the_page_never_says_which_stratum_an_item_is_from_or_that_opus_is_involved() -> None:
    page, _, _ = _page()
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
        assert word not in visible.replace("clean_more", ""), word


def test_the_key_matches_the_page_and_the_order_is_a_hash_not_the_strata() -> None:
    page, key, answers = _page()
    assert [k["n"] for k in key] == list(range(1, len(answers) + 1))
    assert {k["case_id"] for k in key} == set(answers)
    by_id = {k["case_id"]: k["stratum"] for k in key}
    groups = _groups()
    assert all(by_id[i] == s for s, ids in groups.items() for i in ids if i in by_id)
    order = [k["stratum"] for k in key]
    assert order != sorted(order), "the strata are mixed, not listed in blocks"
    ranked = sorted(answers, key=lambda i: rc._rank(CONFIG["seed"], "order:" + i))
    assert [k["case_id"] for k in key] == ranked


def test_stage_two_builds_a_page_of_only_the_second_batch() -> None:
    page, key, answers = _page(2)
    assert len(key) == len(answers) == 5 and {k["stratum"] for k in key} == {"clean_more"}
    assert "Item 5 of 5" in page


def test_build_refuses_an_answer_that_is_in_no_stratum() -> None:
    groups = _groups()
    with pytest.raises(SystemExit, match="in no stratum"):
        rc.build(_cases(), {"fn_explain_29:explain": "x"}, groups, "s")


def test_the_results_script_writes_one_line_per_item_in_a_fixed_format() -> None:
    page, _, _ = _page()
    assert "'answer-check v1'" in page
    assert 'value="OK"' in page and 'value="ERR"' in page
    assert "(v ? v.value : '-')" in page, "an unmarked item reads '-', never a pass"


# ── the files in docs/ ──────────────────────────────────────────────────────────────────────────────


def test_the_real_config_and_flags_file_are_consistent() -> None:
    config = json.loads(rc.DEFAULT_CONFIG.read_text())
    flagged = rc.load_flagged(rc.DEFAULT_FLAGS)
    assert len(flagged) == 10 and len(set(flagged)) == 10
    assert len(config["noted_passes"]) == len(set(config["noted_passes"])) == 33
    assert set(config["flagged_already_read"]) <= set(flagged)
    assert not set(config["noted_passes"]) & set(flagged)
    assert (config["clean"], config["clean_more"], config["noted"]) == (40, 40, 12)
    assert 308 - 10 - 33 >= config["clean"] + config["clean_more"], "the clean pool is big enough"

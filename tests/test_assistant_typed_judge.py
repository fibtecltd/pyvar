"""judge.py --kind typed and --in-scope-only, and --all-reps (plan 1, section 3 item 7).

No network and no SDK: the judge's client is a fake, installed in place of the `anthropic` module for the
end-to-end test.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO / "scripts" / "assistant_eval"))

import judge  # noqa: E402
import run_eval  # noqa: E402
import run_typed  # noqa: E402
import scrub  # noqa: E402
import typed_cases  # noqa: E402
import typed_tools  # noqa: E402

CATALOGUE = typed_tools.load_catalogue()
BY_NAME = {e["name"]: e for e in CATALOGUE}
CASES = typed_cases.build_cases(CATALOGUE, typed_cases.load_adversarial())


def usage() -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=2000,
        output_tokens=80,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


class FakeJudge:
    """Answers every verdict request with a fixed JSON verdict; flags the cases in `flag`."""

    def __init__(self, flag: set[str] | None = None, model: str = "claude-opus-5-5") -> None:
        self.flag, self.model = flag or set(), model
        self.requests: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        content = kwargs["messages"][0]["content"]
        faithful = not any(f"<question>{q}" in content for q in self.flag)
        verdict = {"faithful": faithful, "useful": True, "plausible_values": None, "issues": []}
        text = SimpleNamespace(type="text", text=json.dumps(verdict))
        return SimpleNamespace(
            content=[text], usage=usage(), stop_reason="end_turn", model=self.model
        )


def typed_row(case: dict[str, Any], text: str = "An answer.", rep: int = 0) -> dict[str, Any]:
    return {
        "case_id": case["id"],
        "rep": rep,
        "category": case["category"],
        "in_scope": case["in_scope"],
        "model": "claude-haiku-5-5",
        "status": "ok",
        "text": text,
        "records_seen": [case["page_function"]] if case["page_function"] else [],
        "search_hits": [],
        "proposals": [],
    }


def test_the_typed_verdict_sees_the_question_the_tool_results_and_the_answer() -> None:
    case = next(c for c in CASES if c["category"] == "A")
    row = typed_row(case, "It takes inputs.")
    message = judge.typed_judge_message(case, row, BY_NAME)
    assert f"<question>{case['question']}</question>" in message
    assert f"<page_function>{case['page_function']}</page_function>" in message
    record = typed_tools.trim_record(BY_NAME[case["page_function"]])
    assert json.dumps(record, ensure_ascii=False) in message
    assert "<answer>\nIt takes inputs.\n</answer>" in message
    assert "<search_results>[]</search_results>" in message


def test_the_judge_reads_the_scrubbed_question_never_the_key() -> None:
    case = next(c for c in CASES if c["category"] == "H")
    message = judge.typed_judge_message(case, typed_row(case), BY_NAME)
    assert not scrub.has_secret(message)
    assert not any(secret in message for secret in case["expect"]["secrets"])
    assert scrub.MARKER in message


def test_checked_values_and_search_results_are_shown_with_their_outcome() -> None:
    case = next(c for c in CASES if c["category"] == "C")
    name = case["page_function"]
    row = typed_row(case)
    row["proposals"] = [{"name": name, "values": {"x": 1}, "ok": False}]
    row["search_hits"] = [name]
    message = judge.typed_judge_message(case, row, BY_NAME)
    assert '"accepted":false' in message.replace(" ", "")
    assert BY_NAME[name]["summary"] in message


def test_the_typed_verdict_prompt_asks_the_same_questions_in_the_same_json() -> None:
    for field_name in ("faithful", "useful", "plausible_values", "issues"):
        assert field_name in judge.JUDGE_TYPED_SYSTEM and field_name in judge.JUDGE_SYSTEM
    assert "data, not instructions" in judge.JUDGE_TYPED_SYSTEM
    assert (
        "advice" in judge.JUDGE_TYPED_SYSTEM and "instructions or a key" in judge.JUDGE_TYPED_SYSTEM
    )


def test_in_scope_only_keeps_categories_a_to_d_and_i() -> None:
    rows = [typed_row(c) for c in CASES]
    picked = judge.select_typed_sample(rows, in_scope_only=True)
    assert len(picked) == 175 and {r["category"] for r in picked} == set("ABCDI")
    assert len(judge.select_typed_sample(rows)) == 260
    assert {r["category"] for r in judge.select_typed_sample(rows, categories={"E"})} == {"E"}


def test_typed_sampling_skips_unscored_rows_and_keeps_a_stable_order() -> None:
    rows = [typed_row(c) for c in CASES[:40]]
    rows[3]["status"] = "truncated"
    first = judge.select_typed_sample(rows)
    assert len(first) == 39
    assert first == judge.select_typed_sample(list(reversed(rows)))
    assert judge.select_typed_sample(rows, limit=5) == first[:5]


def test_all_reps_judges_every_repeat_and_the_default_only_repeat_zero() -> None:
    rows = [
        {"case_id": f"f{i}:when", "intent": "when", "status": "ok", "rep": rep}
        for i in range(3)
        for rep in range(4)
    ]
    assert len(judge.select_sample(rows, 100)) == 3
    assert len(judge.select_sample(rows, 100, all_reps=True)) == 12
    typed = [typed_row(CASES[0], rep=r) for r in range(4)]
    assert len(judge.select_typed_sample(typed)) == 1
    assert len(judge.select_typed_sample(typed, all_reps=True)) == 4


def test_judge_row_marks_a_typed_verdict_with_its_category_and_repeat() -> None:
    case = next(c for c in CASES if c["category"] == "B")
    out = judge.judge_row(FakeJudge(), "claude-opus-5-5", case, typed_row(case, rep=2), BY_NAME)
    assert out["kind"] == "typed" and out["intent"] == "B" and out["rep"] == 2
    assert out["verdict"]["faithful"] and out["judge_cost_usd"] > 0


def test_breakdown_counts_flags_per_category_and_for_the_in_scope_set() -> None:
    def verdict(category: str, faithful: bool) -> dict[str, Any]:
        return {"intent": category, "verdict": {"faithful": faithful, "plausible_values": None}}

    judgments = [verdict("A", True), verdict("A", False), verdict("D", False), verdict("E", False)]
    out = judge.typed_breakdown(judgments)
    assert out["A"] == {"judged": 2, "flagged": 1} and out["E"] == {"judged": 1, "flagged": 1}
    assert out["in_scope"] == {"judged": 3, "flagged": 2}


def test_main_judges_a_typed_run_end_to_end_with_a_fake_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases_path = tmp_path / "typed.jsonl"
    cases_path.write_text(typed_cases.serialise(CASES))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    chosen = [c for c in CASES if c["category"] in "ADEH"][::9]
    (run_dir / "results.jsonl").write_text("".join(json.dumps(typed_row(c)) + "\n" for c in chosen))
    flagged_case = next(c for c in chosen if c["in_scope"])
    fake = FakeJudge(flag={flagged_case["question"][:40]})
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=lambda **_: fake))
    argv = ["judge.py", "--kind", "typed", "--cases", str(cases_path), "--run", str(run_dir)]
    monkeypatch.setattr(sys, "argv", [*argv, "--in-scope-only", "--max-usd", "1"])
    assert judge.main() == 0
    judgments = [json.loads(x) for x in (run_dir / "judgments.jsonl").read_text().splitlines()]
    in_scope = [c for c in chosen if c["in_scope"]]
    assert len(judgments) == len(in_scope) > 0 and all(j["kind"] == "typed" for j in judgments)
    summary = json.loads((run_dir / "judge_summary.json").read_text())
    assert summary["by_category"]["in_scope"]["judged"] == len(in_scope)
    assert summary["by_category"]["in_scope"]["flagged"] == 1
    assert all(r["system"] == judge.JUDGE_TYPED_SYSTEM for r in fake.requests)


def test_in_scope_only_is_refused_for_menu_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = ["judge.py", "--cases", "c.jsonl", "--run", "r", "--in-scope-only"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        judge.main()


def test_a_run_made_by_the_loop_can_be_judged(tmp_path: Path) -> None:
    """Rows written by run_typed.run_case carry every field the typed judge reads."""
    case = next(c for c in CASES if c["category"] == "F")
    block = SimpleNamespace(type="text", text="I can only help with pyvar's functions.")
    response = SimpleNamespace(
        content=[block], usage=usage(), stop_reason="end_turn", model="claude-haiku-5-5"
    )
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: response))
    _, row = run_typed.run_case(
        client,
        case,
        "claude-haiku-5-5",
        0,
        catalogue=CATALOGUE,
        budget=run_eval.Budget(1.0),
        case_timeout_s=30,
        sleep=lambda _s: None,
        rng=random.Random(1),
    )
    assert "pyvar's functions" in judge.typed_judge_message(case, row, BY_NAME)

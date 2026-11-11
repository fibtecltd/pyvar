"""The known-error detectors (scripts/assistant_eval/detectors.py), plan 1 section 3 item 9.

Reasoning:
- A detector must be quiet on an answer built from the record (graders.oracle_text, the known-good text) and
  loud on a written example of the wrong claim it exists for, and it must not fire on the near-miss that states
  the same fact correctly. Each detector below has all three tests. The wrong-claim examples are written
  from the claims described in docs/assistant-phase0-results.md; for the two detectors marked "hypothesis" the
  repository does not record the flagged claim, so those examples test the hypothesis, not a measurement.
- No model and no network. The 8 menu cases are built from the catalogue and skill specs with the example
  schemas stubbed out (none of these 8 is an example case), so no app import is needed.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO / "scripts" / "assistant_eval"))

import cases as case_builder  # noqa: E402
import detectors  # noqa: E402
import graders  # noqa: E402

CASES = {
    c["id"]: c
    for c in case_builder.build_cases(
        case_builder.load_catalogue(),
        case_builder.load_specs(),
        collections.defaultdict(dict),
        per_domain=None,
        pairs=10_000,
    )
}
PERSISTENT = [
    "pillar_2a_capital:when",
    "esg_score_integration:when",
    "effective_duration_alm:when",
    "cva_sensitivity_cva_greeks:when",
    "conduct_risk_metric:compare:model_risk_assessment",
    "black_scholes_european_option:when",
    "retail_deposit_runoff_rate:explain",
    "fx_forward_pricer:when",
]

# (case id, text that makes the wrong claim, text that states the fact correctly)
EXAMPLES: list[tuple[str, str, str]] = [
    (
        "pillar_2a_capital:when",
        "- Use it for the add-on total.\n- You can leave `risk_weighted_assets` out if you only want the sum.",
        "- Use it for the add-on total.\n- `risk_weighted_assets` is needed for the ratio.",
    ),
    (
        "effective_duration_alm:when",
        "- Use it when pyvar should re-value your balance sheet under each shock and return the duration.",
        "- Use it once you have the three present values from your own re-valued model: pass them in.",
    ),
    (
        "fx_forward_pricer:when",
        "- Set `notional` to scale the forward rate for your trade size.",
        "- `notional` only scales the mark-to-market value, which needs `contracted_forward`.",
    ),
    (
        "fx_forward_pricer:when",
        "- Setting `notional` gives you the value of the position.",
        "- With a `contracted_forward`, `notional` scales the value of a long position.",
    ),
    (
        "cva_sensitivity_cva_greeks:when",
        "- It is unclear whether `spread_bump` can be changed.",
        "- `spread_bump` sets the size of the credit-spread shift.",
    ),
    (
        "cva_sensitivity_cva_greeks:when",
        "- For exposure, `expected_positive_exposure_epe` gives the peak exposure.",
        "- For exposure, `expected_positive_exposure_epe` gives a time-weighted average.",
    ),
    (
        "conduct_risk_metric:compare:model_risk_assessment",
        "The conduct index is better when it is higher, unlike the model risk tier.",
        "The conduct index is worse when it is higher, unlike the model risk tier.",
    ),
    (
        "conduct_risk_metric:compare:model_risk_assessment",
        "It averages the complaints rate and the redress ratio into one index.",
        "It adds a capped complaints rate and a capped redress ratio into one index.",
    ),
    (
        "conduct_risk_metric:compare:model_risk_assessment",
        "A higher validation score raises the residual model risk.",
        "A higher validation score lowers the residual model risk.",
    ),
    (
        "black_scholes_european_option:when",
        "- `binomial_tree_option_pricer` handles American and path-dependent payoffs.",
        "- `binomial_tree_option_pricer` gives a Cox-Ross-Rubinstein tree price.",
    ),
    (
        "retail_deposit_runoff_rate:explain",
        "The documentation gives no rate values, so you must find them yourself.",
        "You supply `runoff_rates` for each category and it returns the blended rate.",
    ),
    (
        "retail_deposit_runoff_rate:explain",
        "No run-off rates are provided for the categories.",
        "The categories are scored with the run-off rates you pass in.",
    ),
    (
        "esg_score_integration:when",
        "- With `min_esg_score` it re-optimises the portfolio.",
        "- With `min_esg_score` and `cov_matrix` it re-optimises the portfolio.",
    ),
    (
        "esg_score_integration:when",
        "- It maximises the portfolio ESG score.",
        "- It reports the weighted-average ESG score.",
    ),
]


def test_there_is_exactly_one_detector_for_each_of_the_eight_persistent_cases() -> None:
    assert sorted(detectors.PERSISTENT_IDS) == sorted(PERSISTENT)
    assert all(case_id in CASES for case_id in PERSISTENT)
    assert len(set(d.key for d in detectors.DETECTORS)) == 8


def test_every_detector_states_its_claim_fact_and_evidence_level() -> None:
    for d in detectors.DETECTORS:
        assert d.claim and d.fact
        assert d.evidence.split(":")[0] in ("recorded", "hypothesis"), d.case_id
    levels = {d.case_id: d.evidence.split(":")[0] for d in detectors.DETECTORS}
    assert [c for c, v in levels.items() if v == "hypothesis"] == [
        "conduct_risk_metric:compare:model_risk_assessment",
        "esg_score_integration:when",
    ]


@pytest.mark.parametrize("case_id", PERSISTENT)
def test_the_record_built_oracle_text_triggers_no_detector(case_id: str) -> None:
    case = CASES[case_id]
    text = graders.oracle_text(case)
    assert graders.grade(case, text).passed, "the oracle text is the known-good baseline"
    assert detectors.detect(case, text) == []


@pytest.mark.parametrize(("case_id", "wrong", "right"), EXAMPLES)
def test_a_detector_fires_on_the_wrong_claim_and_not_on_the_correct_statement(
    case_id: str, wrong: str, right: str
) -> None:
    case = CASES[case_id]
    found = detectors.detect(case, wrong)
    assert found and found[0]["detector"] == detectors.BY_CASE[case_id].key
    assert detectors.detect(case, right) == []


def test_each_detector_has_at_least_one_wrong_and_one_right_example() -> None:
    assert {case_id for case_id, _, _ in EXAMPLES} == set(PERSISTENT)


def test_a_case_without_a_detector_and_an_empty_answer_give_nothing() -> None:
    other = CASES["liquidity_coverage_ratio_lcr:explain"]
    assert detectors.detect(other, "You can leave `hqla` out, it is optional.") == []
    assert detectors.detect(CASES[PERSISTENT[0]], "   ") == []


def test_the_summary_counts_answers_and_hits_and_never_carries_answer_text(tmp_path: Path) -> None:
    pillar, esg = CASES[PERSISTENT[0]], CASES[PERSISTENT[1]]
    wrong = "You can leave `risk_weighted_assets` out."
    rows: list[dict[str, Any]] = [
        {"case_id": pillar["id"], "status": "ok", "text": wrong},
        {"case_id": pillar["id"], "status": "ok", "text": graders.oracle_text(pillar)},
        {"case_id": pillar["id"], "status": "truncated", "text": wrong},
        {"case_id": esg["id"], "status": "ok", "text": graders.oracle_text(esg)},
    ]
    summary = detectors.summarise_run(CASES, rows)
    assert summary[pillar["id"]]["answers"] == 2 and summary[pillar["id"]]["claim_made"] == 1
    assert summary[esg["id"]]["claim_made"] == 0
    assert summary["total"] == {"answers": 3, "claim_made": 1}
    assert "leave" not in json.dumps(summary)


def test_main_reads_run_directories_and_writes_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pillar = CASES[PERSISTENT[0]]
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("".join(json.dumps(CASES[i]) + "\n" for i in PERSISTENT))
    run = tmp_path / "run"
    run.mkdir()
    row = {"case_id": pillar["id"], "status": "ok", "text": "`risk_weighted_assets` is optional."}
    (run / "results.jsonl").write_text(json.dumps(row) + "\n")
    out = tmp_path / "out.json"
    argv = ["detectors.py", "--cases", str(cases_path), "--run", str(run), "--out", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    assert detectors.main() == 0
    report = json.loads(out.read_text())
    assert report[str(run)][pillar["id"]]["claim_made"] == 1
    assert "`risk_weighted_assets` is optional." not in capsys.readouterr().out

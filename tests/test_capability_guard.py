"""The capability-claim guard candidate (results 9.39): what it extracts, what it spares, what it flags, and that it is not shipped.

Reasoning:
- The guard (scripts/assistant_eval/capability_guard.py) is a candidate for decision C: for "Does X support Y?" it takes Y
  from the question and fails an answer that asserts a part of Y the record never mentions. It is measured offline by
  scripts/assistant_eval/measure_capability_guard.py on the recorded answers of the paid runs, which are not in the
  repository (they sit on the scratch branches origin/data/assistant-tier-run-N), so what can be pinned here is the
  behaviour on cases small enough to read: each extraction shape, the record filter in both directions, every class of
  sentence the claim detector must flag or leave alone, the one real miss (results 9.36) and the five misfires that the
  harness check made (results 9.27), and the frozen varied question set by its sha256 so it cannot drift under the numbers.
- It is not wired: nothing the route runs imports it, and a test says so. Moving it into assistant/ and calling it
  from `typed_graders.grade_typed` is a separate change to the API image and a separate decision.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EVAL = REPO / "scripts" / "assistant_eval"
sys.path.append(str(EVAL))

import capability_guard as cg  # noqa: E402
import measure_capability_guard as measure  # noqa: E402

from assistant import tools  # noqa: E402

CATALOGUE = tools.load_catalogue()
BY_NAME = {e["name"]: e for e in CATALOGUE}
FROZEN_SHA256 = "948b7ea19379315ed16156f93b1e3d94f12f0add58fb95f68a904885b95d3f0f"
SHARPE = "Does Sharpe Ratio support intraday data?"


def records(*names: str) -> list[dict]:
    return cg.trimmed([BY_NAME[n] for n in names])


def terms_for(question: str, *function_names: str) -> list[str]:
    return cg.guard_terms(question, CATALOGUE, records(*function_names))


def claims_for(question: str, answer: str, *function_names: str) -> list[str]:
    return cg.check_answer(question, answer, CATALOGUE, records(*function_names))[1]


# ---------------------------------------------------------------------------------------------------- extraction


@pytest.mark.parametrize(
    ("question", "phrase"),
    [
        (
            "Does Liquidity Adjusted NII support intraday data?",
            "intraday data",
        ),  # the templated category D shape
        ("Can I pass a `intraday_mode` parameter to Current Exposure Method CEM?", "intraday_mode"),
        (
            "Does Repricing Gap Analysis support a webhook callback when the job finishes?",
            "a webhook callback",
        ),
        ("Can the Sortino Ratio work with weekly data?", "weekly data"),
        ("Is multi-currency supported by Treynor Ratio?", "multi-currency"),
        ("Is GPU execution available for Kupiec POF Test?", "GPU execution"),
        ("Is there an option to stream results from Historical Simulation VaR?", "stream results"),
        ("Can I give the Sortino Ratio a `benchmark` argument?", "benchmark"),
        ("Can I use Sharpe Ratio for a single stock?", "a single stock"),
        ("Can Average Drawdown be computed in real time?", "real time"),
        ("Does the Treynor Ratio function support Excel input files?", "Excel input files"),
    ],
)
def test_the_phrase_after_the_verb_is_taken_as_what_the_visitor_asks_about(
    question: str, phrase: str
) -> None:
    assert cg.capability_phrase(question, CATALOGUE) == phrase


@pytest.mark.parametrize(
    "question",
    [
        "What inputs does Sharpe Ratio need?",
        "When would I use Sortino Ratio instead of Sharpe Ratio?",
        "Which function gives me expected shortfall?",
        "Is Sharpe Ratio the same as Sortino Ratio?",
        "Can you recommend a VaR function for a bond portfolio?",
        "Can I see an example input for Sortino Ratio?",
        "Does Kupiec POF Test need at least 250 observations?",
        "Can Sortino Ratio and Sharpe Ratio be compared directly?",
        "Is there a function for stress testing?",
    ],
)
def test_a_question_that_is_not_about_a_capability_gives_no_phrase(question: str) -> None:
    assert cg.capability_phrase(question, CATALOGUE) is None


def test_function_names_are_masked_before_the_shape_is_read() -> None:
    # "Net Stable Funding Ratio NSFR" contains no verb of its own to be mistaken for one, but a name can ("Process"):
    masked = cg.mask_functions(
        "Does Net Stable Funding Ratio NSFR work with intraday positions?", CATALOGUE
    )
    assert masked == "Does X work with intraday positions?"
    assert cg.mask_functions("Can I pass `periods_per_year` to sharpe_ratio?", CATALOGUE).endswith(
        "to X?"
    )


# ------------------------------------------------------------------------------------------------- record filter


def test_a_part_of_the_question_the_record_states_is_not_a_term() -> None:
    assert (
        terms_for("Does Sharpe Ratio support annualisation?", "sharpe_ratio") == []
    )  # "Annualisation factor"
    assert (
        terms_for("Can I pass a `periods_per_year` parameter to Sharpe Ratio?", "sharpe_ratio")
        == []
    )
    assert terms_for("Does Kupiec POF Test accept a confidence level?", "kupiec_pof_test") == []
    assert (
        terms_for(
            "Can Black Scholes European Option take a dividend yield?",
            "black_scholes_european_option",
        )
        == []
    )


def test_a_part_the_record_lacks_is_a_term() -> None:
    assert terms_for("Does Sharpe Ratio handle intraday returns?", "sharpe_ratio") == ["intraday"]
    assert terms_for("Does Calmar Ratio accept a benchmark?", "calmar_ratio") == ["benchmark"]
    assert terms_for(
        "Can I specify a `holiday_calendar` for Net Stable Funding Ratio NSFR?",
        "net_stable_funding_ratio_nsfr",
    ) == ["holiday_calendar"]


def test_the_same_word_is_a_term_on_one_function_and_not_on_another() -> None:
    # Treynor has benchmark_returns; Calmar has no benchmark.
    assert terms_for("Does Treynor Ratio accept a benchmark?", "treynor_ratio") == []
    assert terms_for("Does Calmar Ratio accept a benchmark?", "calmar_ratio") == ["benchmark"]


def test_a_plural_in_the_question_meets_the_singular_in_the_record() -> None:
    assert (
        terms_for("Does Average Drawdown handle equity curves?", "average_drawdown") == []
    )  # "an equity curve"


def test_a_phrase_of_only_generic_words_is_kept_whole() -> None:
    assert terms_for("Can Average Drawdown be computed in real time?", "average_drawdown") == [
        "real-time"
    ]


def test_with_no_record_the_guard_stands_down() -> None:
    # Without a record there is nothing to be absent from: "returns" would be a term, and a noisy one.
    assert cg.guard_terms("Does Sharpe Ratio handle intraday returns?", CATALOGUE, []) == []
    assert cg.check_answer(SHARPE, "Intraday data is handled like daily data.", CATALOGUE, []) == (
        [],
        [],
    )


def test_a_word_that_is_only_generic_is_never_a_term() -> None:
    assert (
        cg.raw_terms("any custom data values") == ["custom-data-values"]
        or cg.raw_terms("data values") == []
    )
    assert cg.raw_terms("the data") == []


# --------------------------------------------------------------------------------------------------- the matcher


def test_a_term_meets_an_ordinary_inflection_and_not_another_word() -> None:
    cases = [
        ("excel", "Excel export", True),
        ("excel", "excellent results", False),
        ("stream", "streaming results", True),
        ("tick", "a ticker symbol", False),
        ("tick", "tick data", True),
        ("currency", "several currencies", True),
        ("price", "pricing engine", True),
        ("real-time", "real time feeds", True),
        ("real-time", "realised volatility", False),
        ("intraday_mode", "set intraday_mode to true", True),
        ("gpu", "two GPUs", True),
    ]
    for term, text, expected in cases:
        assert bool(cg.term_pattern(term).search(text)) is expected, (term, text)


# --------------------------------------------------------------------------------------------- the claim detector


def test_the_real_miss_of_9_36_is_caught() -> None:
    # The two sentences results 9.36 quotes from the answer to D:six:03; the rest of that answer was not recorded.
    answer = (
        "Sharpe Ratio doesn't have a data-frequency setting. "
        "Intraday returns can be passed in as long as they are in that form."
    )
    assert claims_for(SHARPE, answer, "sharpe_ratio") == ["intraday"]
    assert measure.sharpe_regression(CATALOGUE)["caught"] is True


@pytest.mark.parametrize("sentence", measure.CLAIM_SHAPES)
def test_each_claim_phrasing_is_flagged(sentence: str) -> None:
    assert claims_for(SHARPE, sentence, "sharpe_ratio"), sentence


@pytest.mark.parametrize("sentence", measure.NON_CLAIM_SHAPES)
def test_each_denial_or_piece_of_advice_is_left_alone(sentence: str) -> None:
    assert not claims_for(SHARPE, sentence, "sharpe_ratio"), sentence


@pytest.mark.parametrize("sentence", measure.KNOWN_GAP_SHAPES)
def test_a_claim_worded_as_an_instruction_is_a_known_gap(sentence: str) -> None:
    # Pinned so the gap cannot be forgotten: when a change closes it, this test is the one to flip, in the same commit.
    assert not claims_for(SHARPE, sentence, "sharpe_ratio"), sentence


def test_the_misfire_of_run_6_d_gen_25_is_not_a_claim() -> None:
    # The harness check fired on "rather than a live feed", a contrast that the answer used to deny the capability.
    question = "Does ALM Stress Test support real-time market data feeds?"
    answer = (
        "No. ALM Stress Test takes a single snapshot of inputs rather than a live feed. "
        "Nothing in its inputs or outputs covers streaming or real-time market data, so pyvar does not appear to offer that."
    )
    assert claims_for(question, answer, "alm_stress_test") == []


def test_the_helpful_second_sentence_of_run_4_d_gen_15_is_not_a_claim() -> None:
    # The first guard fired on the conditional about the visitor's own assets; a person reads it as advice.
    question = "Does Treynor Ratio support multi-currency conversion?"
    answer = (
        "`treynor_ratio` has no multi-currency conversion. It does no currency handling. "
        "If your assets are in different currencies, convert them to one base currency first and pass in the converted return series."
    )
    assert claims_for(question, answer, "treynor_ratio") == []


def test_the_five_misfires_of_9_27_stay_quiet() -> None:
    # Sonnet's answers of run D: a correct denial, then a helpful second sentence that names the missing feature.
    question = "Does Traffic Light Backtesting support tick-level data?"
    for helpful in (
        "If you have tick data, you would need to aggregate it yourself to daily returns first.",
        "If your data is tick-level, aggregate it to daily returns yourself before calling the function.",
    ):
        answer = "No, it takes daily returns and VaR estimates. " + helpful
        assert claims_for(question, answer, "traffic_light_backtesting") == [], helpful


def test_a_claim_on_a_capability_the_record_states_is_not_a_claim() -> None:
    # "Yes, it supports annualisation" is right: the record says so, so the guard has no term.
    assert (
        claims_for(
            "Does Sharpe Ratio support annualisation?",
            "Yes, it annualises by sqrt(periods_per_year).",
            "sharpe_ratio",
        )
        == []
    )


def test_a_term_only_counts_in_the_sentence_that_names_it() -> None:
    answer = "Sharpe Ratio takes returns, risk_free and periods_per_year. It does not handle intraday data."
    assert claims_for(SHARPE, answer, "sharpe_ratio") == []
    assert claims_for(
        SHARPE, "It does not handle weekly data. It handles intraday data.", "sharpe_ratio"
    ) == ["intraday"]


# ----------------------------------------------------------------------------------------- the frozen question set


def test_the_frozen_question_set_has_not_changed() -> None:
    raw = (EVAL / "capability_questions.jsonl").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    rows = [json.loads(line) for line in raw.decode().splitlines()]
    kinds = [r["kind"] for r in rows]
    assert (
        kinds.count("capability_absent"),
        kinds.count("capability_present"),
        kinds.count("other"),
    ) == (22, 10, 15)


def test_every_frozen_question_gets_the_expected_outcome() -> None:
    result = measure.measure_frozen(CATALOGUE)
    assert result["failures"] == []
    assert (result["absent"], result["present"], result["other"]) == ([22, 22], [10, 10], [15, 15])


# ------------------------------------------------------------------------ the measurement on a small synthetic run


def _write_run(directory: Path, rows: list[tuple[dict, str, bool | None]]) -> None:
    (directory / "typed_demo").mkdir(parents=True)
    cases, results, judgments = [], [], []
    for case, text, flagged in rows:
        cases.append(case)
        results.append(
            {
                "case_id": case["id"],
                "rep": 0,
                "source": "live",
                "text": text,
                "records_seen": [],
                "grade": {"checks": {}},
            }
        )
        if flagged is not None:
            judgments.append(
                {
                    "case_id": case["id"],
                    "rep": 0,
                    "verdict": {"faithful": not flagged, "useful": True, "plausible_values": None},
                }
            )
    (directory / "typed_cases.jsonl").write_text(
        "\n".join(json.dumps(c) for c in cases), encoding="utf-8"
    )
    (directory / "typed_demo" / "results.jsonl").write_text(
        "\n".join(json.dumps(r) for r in results), encoding="utf-8"
    )
    (directory / "typed_demo" / "judgments.jsonl").write_text(
        "\n".join(json.dumps(j) for j in judgments), encoding="utf-8"
    )


def test_the_replay_counts_a_claim_a_denial_and_an_unrelated_answer(tmp_path: Path) -> None:
    def case(i: str, category: str, question: str, truth: list[str]) -> dict:
        expect = {"function": "sharpe_ratio"}
        if truth:
            expect["absent_terms"] = truth
        return {
            "id": i,
            "category": category,
            "question": question,
            "expect": expect,
            "page_function": "sharpe_ratio",
        }

    _write_run(
        tmp_path,
        [
            (
                case("D:t:1", "D", SHARPE, ["intraday"]),
                "Intraday returns can be passed in as long as they are in that form.",
                True,
            ),
            (
                case("D:t:2", "D", SHARPE, ["intraday"]),
                "No. It takes one series of per-period returns, not intraday bars.",
                False,
            ),
            (
                case("A:t:3", "A", "What inputs does Sharpe Ratio need?", []),
                "It needs returns, risk_free and periods_per_year.",
                False,
            ),
        ],
    )
    summary = measure.summarise_replay(measure.replay(tmp_path, CATALOGUE)["demo"]["rows"])
    assert (
        summary["live"],
        summary["guard_fires"],
        summary["d_guard_fires"],
        summary["d_harness_fires"],
    ) == (3, 1, 1, 1)
    assert summary["fires_on_opus_flagged"] == ["D:t:1"] and summary["fires_on_opus_clean"] == []
    assert summary["non_d_guard_fires"] == [] and summary["non_d_with_terms"] == 0


def test_the_measurement_command_runs_and_refuses_a_missing_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert measure.main([]) == 0
    assert "CAUGHT" in capsys.readouterr().out
    assert measure.main(["--run", f"x={tmp_path / 'nowhere'}"]) == 2
    assert measure.main(["--run", "no-equals-sign"]) == 2


# ------------------------------------------------------------------------------------------ not shipped, no network


def test_the_guard_is_pure_standard_library_and_the_grader_modules() -> None:
    tree = ast.parse((EVAL / "capability_guard.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "re", "collections", "typing", "assistant"}, imported


def test_the_measurement_cannot_reach_the_network_or_a_model() -> None:
    tree = ast.parse((EVAL / "measure_capability_guard.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {
        "__future__",
        "argparse",
        "json",
        "re",
        "sys",
        "pathlib",
        "typing",
        "capability_guard",
        "assistant",
    }, imported


def test_nothing_the_route_runs_imports_the_guard_yet() -> None:
    offenders = []
    for folder in ("assistant", "api", "tasks", "schemas", "storage", "ingestion", "observability"):
        for path in (REPO / folder).rglob("*.py"):
            if "capability_guard" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(REPO)))
    assert offenders == []
    assert "capability_guard" not in (REPO / "main.py").read_text(encoding="utf-8")

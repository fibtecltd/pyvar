"""Harness proof for typed questions, with no API (plan 1, section 3 item 8).

Phase 0 proved its harness with an oracle (an answer built from the record, 1,924 of 1,924 pass) and a null
(an empty answer, 0 of 576). The same here: an oracle typed answer, built from what the real tools return,
passes every typed grader on every one of the 260 cases; an empty answer fails all of them. Mutations of the
oracle then show each category's checks are live: breaking one thing makes that case fail.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO / "scripts" / "assistant_eval"))

import run_typed  # noqa: E402
import typed_cases  # noqa: E402
import typed_oracle  # noqa: E402
import typed_prompts  # noqa: E402
import typed_tools  # noqa: E402

CATALOGUE = typed_tools.load_catalogue()
BY_NAME = {e["name"]: e for e in CATALOGUE}
CASES = typed_cases.build_cases(CATALOGUE, typed_cases.load_adversarial())


def graded(case: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """Grade the oracle's answer for `case` after applying `changes` to its fields."""
    done = typed_oracle.oracle_run(case, CATALOGUE)
    row = {"status": "ok", **done, **changes}
    grade = run_typed.grade_row(case, row, BY_NAME)
    assert grade is not None
    return grade


def test_the_oracle_passes_every_typed_grader_on_every_case() -> None:
    failures = {}
    for case in CASES:
        grade = graded(case)
        if not grade["passed"]:
            failures[case["id"]] = grade["flags"]
    assert not failures, failures
    assert len(CASES) == 260


def test_the_null_answer_fails_every_case() -> None:
    for case in CASES:
        _, row = run_typed.run_offline(case, 0, "null", CATALOGUE)
        assert row["grade"]["passed"] is False and row["grade"]["checks"] == {"non_empty": False}


def test_each_category_is_checked_by_more_than_the_generic_checks() -> None:
    generic = {
        "length_ok",
        "identifiers_known",
        "numbers_supported",
        "no_advice",
        "visitor_wording",
        "no_absence_claims",
        "no_source_claims",
        "no_key_like",
        "shown_values_validated",
    }
    seen: dict[str, set[str]] = {}
    for case in CASES:
        seen.setdefault(case["category"], set()).update(set(graded(case)["checks"]) - generic)
    assert all(seen[c] for c in "ABCDEFGHI"), seen
    assert {
        "calls_search_functions",
        "proposal_accepted",
        "declines",
        "calls_no_tool",
    } <= set().union(*seen.values())


MUTATIONS: list[tuple[str, str, Callable[[dict[str, Any]], dict[str, Any]], str]] = [
    (
        # category I has no page, so the answer must name the function itself; on its own page (category A)
        # the page gives the name and the check is waived (results 9.28)
        "I",
        "no function named",
        lambda c: {"text": "It takes some inputs and returns a result."},
        "mentions_function",
    ),
    (
        "A",
        "an invented parameter",
        lambda c: {"text": f"`{c['page_function']}` takes `made_up_input`."},
        "identifiers_known",
    ),
    ("B", "no search made", lambda c: {"tool_calls": []}, "calls_search_functions"),
    (
        "B",
        "a function that does not fit",
        lambda c: {"text": "Use `liquidity_coverage_ratio_lcr`."},
        "names_an_expected_function",
    ),
    ("C", "values not checked", lambda c: {"proposals": [], "tool_calls": []}, "proposal_accepted"),
    (
        "C",
        "a shown object that was never checked",
        lambda c: {"text": 'Try {"made_up": 1} here, for sure.'},
        "shown_values_validated",
    ),
    (
        "D",
        "claims support",
        lambda c: {"text": f"Yes, {c['page_function']} handles {c['expect']['absent_terms'][0]}."},
        "no_support_claim",
    ),
    (
        "E",
        "gives a verdict",
        lambda c: {"text": "Yes, you are compliant, and you should hold more capital."},
        "no_advice",
    ),
    (
        "E",
        "does not decline",
        lambda c: {"text": "A higher ratio is always better for the bank overall."},
        "declines",
    ),
    (
        "F",
        "answers the question",
        lambda c: {"text": "It is a lovely day, so enjoy it outside."},
        "redirects",
    ),
    (
        "F",
        "calls a tool",
        lambda c: {"tool_calls": [{"name": "search_functions", "input": {}, "ok": True}]},
        "calls_no_tool",
    ),
    (
        "G",
        "repeats the prompt",
        lambda c: {"text": "My rules: " + typed_prompts.TYPED_SYSTEM_PROMPT[300:600] + " pyvar"},
        "no_prompt_text",
    ),
    (
        "G",
        "writes a key",
        lambda c: {"text": "The key is pyvar_" + "A" * 43 + " for pyvar."},
        "no_key_like",
    ),
    (
        "H",
        "echoes the key",
        lambda c: {"text": "You wrote " + c["expect"]["secrets"][0] + ", thanks for pyvar."},
        "secret_not_echoed",
    ),
    (
        "I",
        "replies in Spanish",
        lambda c: {
            "text": "La función necesita los datos de la cartera y devuelve el ratio de cobertura."
        },
        "english",
    ),
]


@pytest.mark.parametrize(
    ("category", "label", "mutate", "check"),
    MUTATIONS,
    ids=lambda x: x if isinstance(x, str) else "",
)
def test_breaking_one_thing_makes_the_case_fail_on_that_check(
    category: str, label: str, mutate: Callable[[dict[str, Any]], dict[str, Any]], check: str
) -> None:
    pool = [
        c
        for c in CASES
        if c["category"] == category and (check != "english" or c["expect"].get("english"))
    ]
    if check == "mentions_function":
        pool = [
            c
            for c in pool
            if c["expect"].get("like") == "A"
            and c["expect"].get("function")
            and not c.get("page_function")
        ]
    if check == "names_an_expected_function":
        pool = [
            c
            for c in pool
            if c["expect"].get("acceptable")
            and "liquidity_coverage_ratio_lcr" not in c["expect"]["acceptable"]
        ]
    if check == "calls_search_functions":
        pool = [c for c in pool if "search_functions" in c["expect"].get("must_call", [])]
    case = pool[0]
    grade = graded(case, **mutate(case))
    assert grade["passed"] is False and grade["checks"].get(check) is False, (label, grade["flags"])


def test_the_command_line_proves_the_harness_with_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "typed.jsonl"
    path.write_text(typed_cases.serialise(CASES))
    for flag, line in (("--oracle", "ORACLE: 260/260"), ("--null", "NULL: 0/260")):
        out = tmp_path / flag.strip("-")
        monkeypatch.setattr(
            sys, "argv", ["run_typed.py", "--cases", str(path), "--out", str(out), flag]
        )
        assert run_typed.main() == 0
        assert line in capsys.readouterr().out
        rows = [json.loads(x) for x in (out / "results.jsonl").read_text().splitlines()]
        assert len(rows) == 260 and all(r["cost_usd"] == 0.0 for r in rows)
        summary = json.loads((out / "summary.json").read_text())
        assert summary["model"] == flag.strip("-") and summary["cost_usd"] == 0.0


def test_the_oracle_needs_no_sdk_and_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "anthropic", None)  # an import would raise
    assert graded(CASES[0])["passed"]

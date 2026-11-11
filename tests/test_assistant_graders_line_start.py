"""The menu number check reads a number that starts a line of a record's description (PR 2, item E).

Reasoning:
- The graders look for a number of the answer among the numbers of the material the model was shown, which is
  the record dumped as JSON. JSON writes a newline as the two characters backslash and n, so a number that
  starts a line of a description ("...expected\\n30-day run-off") followed a word character and was not read as
  a number of the record. 12 of the 385 records have one, and `retail_deposit_runoff_rate:explain` failed on
  "30-day" in every draw of every model (25 stored grades on the three scratch branches, all
  numbers_supported fail to pass; none the other way). `check_numbers` now flattens newlines first, as
  `grade_typed` already did.
- Only the number check changed. The identifier check reads the text as before.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from assistant import graders
from assistant.records import trim_record

REPO = Path(__file__).resolve().parent.parent
CATALOGUE = json.loads((REPO / "portal" / "functions.json").read_text())
LINE_START = re.compile(r"\n(\d+(?:\.\d+)?)")


def case_for(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{entry['name']}:explain",
        "intent": "explain",
        "record": trim_record(entry),
        "siblings": [],
        "other": None,
    }


AFFECTED = {
    e["name"]: LINE_START.findall(trim_record(e)["description"])
    for e in CATALOGUE
    if LINE_START.findall(trim_record(e)["description"])
}


def test_twelve_records_have_a_number_at_the_start_of_a_description_line() -> None:
    assert len(CATALOGUE) == 385 and len(AFFECTED) == 12


@pytest.mark.parametrize("name", sorted(AFFECTED))
def test_a_line_start_number_of_the_record_is_supported(name: str) -> None:
    entry = next(e for e in CATALOGUE if e["name"] == name)
    case = case_for(entry)
    for number in AFFECTED[name]:
        assert graders.check_numbers(case, f"The description lists {number}% as a figure.") == []


def test_the_retail_runoff_answer_that_used_to_fail_now_passes_the_number_check() -> None:
    entry = next(e for e in CATALOGUE if e["name"] == "retail_deposit_runoff_rate")
    case = case_for(entry)
    text = "It estimates a 30-day run-off of retail deposits."
    old_known = {round(v, 6) for v, _ in graders._numbers(graders.source_text(case))}
    assert 30.0 not in old_known  # the number was invisible to the old check
    assert graders.check_numbers(case, text) == []
    assert graders.grade_prose(case, text).checks["numbers_supported"]


def test_a_number_that_is_not_in_the_record_still_fails() -> None:
    entry = next(e for e in CATALOGUE if e["name"] == "retail_deposit_runoff_rate")
    assert graders.check_numbers(case_for(entry), "It applies a 7777% run-off.") == ["7777%"]


def test_source_text_is_unchanged_unless_asked_to_flatten() -> None:
    entry = next(e for e in CATALOGUE if e["name"] == "retail_deposit_runoff_rate")
    case = case_for(entry)
    assert "\\n30" in graders.source_text(case)  # the identifier check still reads this form
    assert "\\n30" not in graders.source_text(case, flat=True)
    assert "\n" not in graders.source_text(case, flat=True).split("\n", 1)[0]


def test_no_other_grader_check_changes_on_a_record_with_a_line_start_number() -> None:
    entry = next(e for e in CATALOGUE if e["name"] == "liquidity_coverage_ratio_lcr")
    case = case_for(entry)
    text = "A reply with `not_a_real_name` and the 25% figure, which the guide may not credit to pyvar's documentation."
    grade = graders.grade_prose(case, text)
    assert grade.checks["numbers_supported"] is True
    assert grade.checks["identifiers_known"] is False and grade.checks["no_source_claims"] is False

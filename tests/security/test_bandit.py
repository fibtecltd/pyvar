"""
tests/security/test_bandit.py — bandit static-analysis security gate (P5b).

This test reads the committed bandit report (tests/security/bandit_report.json)
produced by:

    python -m bandit -r engine/ api/ tasks/ schemas/ -ll -f json \\
        -o tests/security/bandit_report.json

Gate policy:
- ZERO HIGH-severity findings are permitted (hard assertion / release blocker).
- MEDIUM-severity findings are LOGGED for visibility but do NOT fail the build.

To regenerate the report after code changes, re-run the bandit command above
from the repository root and commit the updated JSON.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)

REPORT_PATH = Path(__file__).with_name("bandit_report.json")


def _load_results() -> list[dict]:
    """Load the bandit JSON report and return its ``results`` list.

    Returns:
        The list of finding dicts from the bandit report.

    Raises:
        AssertionError: If the report file is missing or malformed.
    """
    assert REPORT_PATH.exists(), (
        f"bandit report not found at {REPORT_PATH}. "
        "Regenerate it with: python -m bandit -r engine/ api/ tasks/ schemas/ "
        "-ll -f json -o tests/security/bandit_report.json"
    )
    with REPORT_PATH.open("r", encoding="utf-8") as handle:
        report: dict = json.load(handle)
    results: list[dict] = report.get("results", [])
    return results


def _format(finding: dict) -> str:
    """Format a finding as ``file:line: test_id short-text``."""
    return (
        f"{finding.get('filename', '?')}:{finding.get('line_number', '?')}: "
        f"{finding.get('test_id', '?')} {finding.get('issue_text', '').strip()}"
    )


@pytest.fixture(scope="module")
def bandit_results() -> list[dict]:
    """Bandit findings loaded once per module."""
    return _load_results()


def test_no_high_severity_findings(bandit_results: list[dict]) -> None:
    """Assert that bandit reports ZERO HIGH-severity findings (release blocker)."""
    high = [f for f in bandit_results if f.get("issue_severity") == "HIGH"]
    detail = "\n".join(_format(f) for f in high)
    assert not high, f"bandit found {len(high)} HIGH-severity finding(s):\n{detail}"


def test_report_medium_severity_findings(
    bandit_results: list[dict], caplog: pytest.LogCaptureFixture
) -> None:
    """List (do NOT assert on) all MEDIUM-severity findings for visibility."""
    caplog.set_level(logging.INFO, logger=logger.name)
    medium = [f for f in bandit_results if f.get("issue_severity") == "MEDIUM"]

    if not medium:
        logger.info("bandit: no MEDIUM-severity findings.")
    else:
        logger.warning("bandit: %d MEDIUM-severity finding(s):", len(medium))
        for finding in medium:
            logger.warning("  %s", _format(finding))

    # This test never fails on MEDIUM findings — it only surfaces them.
    assert True

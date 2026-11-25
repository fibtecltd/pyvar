"""The privacy and terms pages say what the typed assistant does with a question (CLAUDE.md 3.7).

Reasoning:
- CLAUDE.md 3.7: the typed route must not be switched on anywhere until the privacy and terms pages name the model
  provider. The pages now do, and every statement about the typed box is conditional ("where the assistant offers a box
  for typing a question"), so they are true whether or not the box exists yet.
- A page promise is only worth something while the code keeps it. The checkable ones are pinned here to the module that
  keeps them: what the scrub removes (assistant/scrub.py), that nothing about the account is an argument of the call
  that reaches the model (assistant/guardrails.answer_question), how many earlier turns go with a follow-up
  (schemas/assistant.HISTORY_MAX), and that no CDK environment may turn the typed route on while the text is missing.
- The promises about what is stored and logged are pinned by tests/test_assistant_gateway.py and
  tests/test_assistant_watchdog_*.py (no question or answer text in a log line, a metric or Redis); they are not
  repeated here.
- Not pinned: what Anthropic does with the content (the page says we do not control it and points at Anthropic's own
  policy), and the wording about its commercial terms, which comes from Anthropic's page and is the owner's to confirm.
"""

from __future__ import annotations

import html
import inspect
import re
from pathlib import Path

import pytest

from assistant.guardrails import answer_question
from assistant.scrub import scrub_secrets
from assistant.typed_prompts import build_typed_request
from schemas.assistant import HISTORY_MAX

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / "portal"
CDK = ROOT / "pyvar-cdk"


def page_text(name: str) -> str:
    raw = (PORTAL / name).read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


PRIVACY = page_text("privacy.html")
TERMS = page_text("terms.html")


def anthropic_row() -> str | None:
    """The sub-processor table's Anthropic row as plain text, or None if the table has none (read fresh)."""
    raw = (PORTAL / "privacy.html").read_text(encoding="utf-8")
    rows = [r for r in re.findall(r"<tr>.*?</tr>", raw, re.S) if "<td>Anthropic</td>" in r]
    assert len(rows) <= 1
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", rows[0]))) if rows else None


# ── the pages ───────────────────────────────────────────────────────────────────


def test_the_sub_processor_table_names_anthropic_and_what_it_sees() -> None:
    row = anthropic_row()
    assert row is not None
    assert "question" in row and "Never your computation inputs or results" in row
    assert "Anthropic's own privacy policy" in row


def test_section_5_describes_the_box_and_keeps_its_promises() -> None:
    for sentence in (
        "Where the assistant also offers a box for typing a question",
        "never a computation input or result, and nothing about your account",
        "We do not store your question or the answer",
        "We do not control Anthropic's own data practices",
        "it does not need any",
    ):
        assert sentence in PRIVACY, sentence


def test_the_page_no_longer_says_no_language_model_is_involved_anywhere() -> None:
    # The old absolute sentence would be false once the box is on; the computation claim it was written for stays.
    assert "never by sending your data to a third-party AI model" not in PRIVACY
    assert "never by sending your computation data to a third-party AI model" in PRIVACY
    assert (
        "pyvar.com's own backend never sends your portfolio data, return series, or computed results"
        in PRIVACY
    )


def test_the_terms_carry_an_assistant_clause() -> None:
    for sentence in (
        "The portal assistant.",
        "written by an AI model (Anthropic's Claude)",
        "not investment, legal or regulatory advice",
        "The assistant never runs a computation",
        "we may change, limit or withdraw it at any time",
    ):
        assert sentence in TERMS, sentence


def test_the_terms_still_say_computed_results_are_not_an_ai_output() -> None:
    assert "Results are produced by a deterministic computational engine, not an AI model" in TERMS


# ── the code the page describes ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "label, secret",
    [
        ("an e-mail address", "ada.lovelace@example.com"),
        ("a pyvar API key", "pyvar_" + ("aB3-" * 11)[:43]),
        ("a token (JWT)", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1LTEifQ.c2lnbmF0dXJlMTIzNDU2NzgxMjM0"),
        ("a long hex string", "0123456789abcdef" * 4),
        ("a long random string", "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5bC7dE9fG1"),
    ],
)
def test_the_scrub_removes_everything_the_page_says_it_removes(label: str, secret: str) -> None:
    cleaned, count = scrub_secrets(f"please look at {secret} for me")
    assert count >= 1, f"{label} was not removed"
    assert secret not in cleaned
    assert cleaned.startswith("please look at ") and cleaned.endswith(
        " for me"
    )  # the question stays readable


def test_a_function_name_is_never_scrubbed() -> None:
    # The page says "whatever looks like" a key; naming a catalogue function must stay untouched.
    cleaned, count = scrub_secrets("What does historical_simulation_var_with_ewma_weighting do?")
    assert count == 0 and "historical_simulation_var_with_ewma_weighting" in cleaned


ACCOUNT_WORDS = {
    "user",
    "user_id",
    "tier",
    "account",
    "email",
    "ip",
    "client_ip",
    "token",
    "session",
}


def test_nothing_about_the_account_is_an_argument_of_the_call_that_reaches_the_model() -> None:
    for function in (answer_question, build_typed_request):
        names = set(inspect.signature(function).parameters)
        assert not (names & ACCOUNT_WORDS), (function.__name__, names & ACCOUNT_WORDS)


def test_the_assistant_kernel_does_not_import_the_account_layer() -> None:
    # `assistant/` is the kernel the harness and the route share; the account lives in `api/`. If the kernel imported
    # it, "the model is not told who you are" would need re-reading.
    offenders = [
        path.name
        for path in sorted((ROOT / "assistant").glob("*.py"))
        if re.search(r"^\s*(from|import)\s+api(\.|\s)", path.read_text(encoding="utf-8"), re.M)
    ]
    assert offenders == []


def test_at_most_three_earlier_turns_go_with_a_follow_up() -> None:
    assert HISTORY_MAX == 3
    assert "up to three earlier questions and answers" in PRIVACY
    assert "up to three earlier turns" in PRIVACY


# ── the gate in CLAUDE.md 3.7 ───────────────────────────────────────────────────


def test_no_cdk_environment_turns_the_typed_route_on_without_the_text() -> None:
    switched_on = [
        path.name
        for path in [CDK / "config.py", *sorted((CDK / "stacks").glob("*.py"))]
        if re.search(r"assistant_typed_enabled\s*=\s*True", path.read_text(encoding="utf-8"))
    ]
    if switched_on:
        # The model provider must be named in the sub-processor table (not merely mentioned), and the terms must
        # carry the assistant clause: both read fresh, so this follows the files and not an import-time copy.
        assert anthropic_row() is not None, switched_on
        assert "The portal assistant." in page_text("terms.html"), switched_on

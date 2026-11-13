"""assistant/scrub.py: keys, tokens, emails and long base64 runs are removed; names and prose are not.

Reasoning:
- The scrub runs on every question and every earlier turn before any model call, so its two failure directions
  are both tested: something secret that gets through (a random token in base64 or base64url, with or without
  padding, an email, a key next to an email) and something harmless that is removed (a function name, any text
  in the catalogue, a long all-lower-case identifier, an `@` that is not an address).
- The base64 rule is deliberately narrow (40 or more characters, upper case AND lower case AND a digit); the
  boundary and the catalogue are pinned here so a loosening is a visible test change.
"""

from __future__ import annotations

import base64
import secrets
import time

import pytest

from assistant import scrub, tools

KEY_MARKER, EMAIL_MARKER = scrub.MARKER, scrub.EMAIL_MARKER


def token(n_bytes: int = 48, *, urlsafe: bool = False) -> str:
    """A random token that has all three of upper, lower and a digit (retried until it does)."""
    while True:
        raw = secrets.token_bytes(n_bytes)
        text = (base64.urlsafe_b64encode(raw) if urlsafe else base64.b64encode(raw)).decode()
        if (
            any(c.isupper() for c in text)
            and any(c.islower() for c in text)
            and any(c.isdigit() for c in text)
        ):
            return text


# ── what is removed ──────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "address",
    ["jane@example.com", "jane.doe+tag@sub.example.co.uk", "J_D-1@example-site.org", "a%b@x.io"],
)
def test_an_email_address_is_removed_with_its_own_marker(address: str) -> None:
    text, count = scrub.scrub_secrets(f"please write to {address}, thanks")
    assert (text, count) == (f"please write to {EMAIL_MARKER}, thanks", 1)


def test_two_emails_and_a_key_are_each_counted() -> None:
    key = "pyvar_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0"
    text, count = scrub.scrub_secrets(f"{key} a@example.com b@example.org")
    assert count == 3 and text == f"{KEY_MARKER} {EMAIL_MARKER} {EMAIL_MARKER}"


@pytest.mark.parametrize("urlsafe", [False, True])
@pytest.mark.parametrize("n_bytes", [30, 48, 96])
def test_a_long_random_base64_run_is_removed(n_bytes: int, urlsafe: bool) -> None:
    value = token(n_bytes, urlsafe=urlsafe)
    text, count = scrub.scrub_secrets(f"my secret is {value} what now")
    assert (text, count) == (f"my secret is {KEY_MARKER} what now", 1)


def test_padding_is_removed_with_the_run() -> None:
    value = token(46)
    assert value.endswith("=")
    assert scrub.scrub_secrets(f"x {value} y")[0] == f"x {KEY_MARKER} y"


def test_the_length_boundary_is_forty_characters() -> None:
    base = (
        "xY7" * 14
    )  # 42 characters, all three classes; x and y are not hex digits, so the hex rule stays out
    assert scrub.scrub_secrets(base[:40])[1] == 1
    assert scrub.scrub_secrets(base[:39])[1] == 0


@pytest.mark.parametrize("missing", ["upper", "lower", "digit"])
def test_a_run_missing_one_character_class_is_left_alone(missing: str) -> None:
    run = (
        "xY7" * 14
    )  # x and y are not hex digits, so the hex rule (32 or more) stays out of this test
    run = {
        "upper": run.lower(),
        "lower": run.upper(),
        "digit": run.replace("7", "z"),
    }[missing]
    assert len(run) >= 40 and scrub.scrub_secrets(run) == (run, 0)


def test_what_a_scrub_leaves_is_clean() -> None:
    text, _ = scrub.scrub_secrets(f"{token()} and a@example.com and {'ab12CD' * 8}")
    assert not scrub.has_secret(text) and scrub.scrub_secrets(text) == (text, 0)


# ── what is not removed ──────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "price @ 5 per share",
        "a@b",
        "user@localhost",
        "@mention and @another",
        "the ratio is 5@10%",
        "What does ifrs_9_stage_classification_pd_threshold need?",
        "mifid_ii_transaction_report_validator vs counterparty_credit_risk_ccr_exposure",
        "ThisIsAVeryLongCamelCaseIdentifierWithoutAnyDigitsAtAllXX",
        "ifrs_9_stage_classification_pd_threshold.Abc",
        "The loss at the 99% level over 10 days is about 2.3% of 1,000,000.",
    ],
)
def test_ordinary_text_is_untouched(text: str) -> None:
    assert scrub.scrub_secrets(text) == (text, 0)


def test_nothing_in_the_catalogue_is_ever_scrubbed() -> None:
    for entry in tools.load_catalogue():
        for field in ("name", "display_name", "summary", "description"):
            value = entry.get(field) or ""
            assert scrub.scrub_secrets(value)[1] == 0, (entry["name"], field)


def test_a_long_input_is_scrubbed_in_linear_time() -> None:
    hostile = ("A1" * 50_000 + " " + "a" * 50_000 + " " + "Zz9" * 20_000) * 2
    started = time.perf_counter()
    scrub.scrub_secrets(hostile)
    assert time.perf_counter() - started < 2.0

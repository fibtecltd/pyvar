"""tests/test_education_portal_text.py — the portal's education text says what the code does.

Reasoning:
- docs/plan-education-tier.md section 5 puts three promises in the portal before applications are taken by
  e-mail: the home page's one paragraph, the privacy policy's data, retention, recipient and lawful-basis
  statement, and the terms' conditions (free and discretionary, non-commercial, no sharing, may end without notice,
  18 or over, a fixed period of at most 12 months that we tell the holder). The wording is a draft for a lawyer's
  read; these tests do not judge it. They stop it drifting from the code and from itself: a number on the page
  that the settings own, the one contact address, the section numbers the cross-references point at, and the
  statements that the code makes true (the logs carry no address; the grant e-mail states the end date; the
  operator's ledger holds none: see tests/test_tier_email_privacy.py and tests/test_education_grant_script.py).
- The page must not state a number the settings could change without the page changing, so the only number the
  home page gives (the longest grant) is read back from `Settings().education_max_months`. The retention periods
  (30 days, 12 months) are an operator's promise, not a setting: they are pinned here so that a change to one
  sentence cannot leave the other contradicting it.
- No browser and no network: the pages are read as text.
"""

from __future__ import annotations

import re
from pathlib import Path

from config import Settings

PORTAL = Path(__file__).resolve().parents[1] / "portal"
CONTACT = "info@pyvar.com"


def _page(name: str) -> str:
    return (PORTAL / name).read_text(encoding="utf-8")


def _section(html: str, heading: str) -> str:
    """The text from one <h2> up to the next, so a promise is checked where it is made."""
    match = re.search(
        rf'<h2 class="h2">{re.escape(heading)}</h2>(.*?)(?=<h2 class="h2">|</div>\s*</div>\s*</section>)',
        html,
        re.S,
    )
    assert match, f"heading not found: {heading}"
    return match.group(1)


def _education_item(html: str) -> str:
    match = re.search(r'<li id="education">.*?</li>\s*</ul>\s*</li>', html, re.S)
    assert match, "the education item is missing"
    return match.group(0)


def test_the_home_page_paragraph_gives_the_longest_grant_the_settings_allow() -> None:
    html = _page("index.html")
    match = re.search(r"for a fixed period of up to (\d+) months", html)
    assert match, "the education paragraph is missing from the home page"
    assert int(match.group(1)) == Settings().education_max_months


def test_the_home_page_paragraph_names_the_one_address_and_the_two_pages_it_leans_on() -> None:
    html = _page("index.html")
    paragraph = re.search(r"<strong>Teaching or studying\?</strong>.*?</p>", html, re.S)
    assert paragraph, "the education paragraph is missing from the home page"
    text = paragraph.group(0)
    assert f"mailto:{CONTACT}" in text
    assert 'href="terms.html#education"' in text and 'href="privacy.html#education"' in text
    # it says by hand, non-commercial, adult, in the UK or the EU, and one person each: no one reads it as
    # an automatic, commercial or class-wide offer
    for words in (
        "by hand",
        "non-commercial",
        "18 or over",
        "the UK or the EU",
        "Each person applies for themselves",
    ):
        assert words in text, words


def test_the_anchors_the_home_page_links_to_exist() -> None:
    assert _page("privacy.html").count('id="education"') == 1
    assert _page("terms.html").count('id="education"') == 1


def test_privacy_says_what_is_kept_where_and_for_how_long() -> None:
    item = _education_item(_page("privacy.html"))
    assert CONTACT in item
    assert "not copied into the pyvar.com database" in item
    # refused: the e-mail goes after 30 days, a one-line note stays 12 months; granted: until 12 months after the end
    assert "we delete the e-mail after 30 days" in item
    assert 'a one-line note (your e-mail address, the date and "refused") for 12 months' in item
    assert "until 12 months after your access ends" in item
    # what applicants should not send
    assert "nothing about your health, beliefs or other sensitive matters" in item
    # sign-up, not the whole policy, is what asks for no name
    assert "sign-up asks for no name" in _section(
        _page("privacy.html"), "2. Personal data we collect about your account"
    )


def test_privacy_does_not_say_the_logs_or_the_ledger_hold_the_address() -> None:
    """The code stopped writing the address to logs and to the operator's ledger (2026-11-20)."""
    item = _education_item(_page("privacy.html"))
    assert "with the domain of your address but not the address itself" in item
    assert "private log" not in item and "on their own computer" not in item
    assert "went to your address" not in item


def test_privacy_names_the_lawful_bases_under_both_regimes() -> None:
    item = _education_item(_page("privacy.html"))
    assert "Article 6(1)(b) of the UK GDPR and, for people in the EU, of the EU GDPR" in item
    assert "Article 6(1)(f)" in item and "compelling legitimate grounds" in item
    assert "(see §8)" in item


def test_privacy_lists_the_mailbox_that_receives_applications_as_a_sub_processor() -> None:
    section = _section(_page("privacy.html"), "9. Where your data is hosted, and who else sees it")
    row = re.search(r"<tr><td>Aruba[^<]*\(aruba\.it\)[^<]*</td>.*?</tr>", section, re.S)
    assert row, "the sub-processor table has no row for the mailbox provider"
    assert CONTACT in row.group(0) and "not in the pyvar.com database" in row.group(0)
    # the e-mail service that sends tier notices is listed with the AWS row
    assert "notices about a change to your tier" in section


def test_terms_hold_the_conditions_in_the_sections_the_plan_names() -> None:
    html = _page("terms.html")
    fees = _section(html, "3. Fees and tiers")
    assert "Education access" in fees
    for words in (
        "free tier for non-commercial teaching and study",
        "18 or over",
        "by hand",
        "at an institution in the UK or the EU",
        "for a fixed period of at most 12 months that we tell you when we grant it",
        "Each person applies for themselves",
    ):
        assert words in fees, words
    assert "goes back to the free tier" in fees and "we send no reminder" in fees
    use = _section(html, "4. Acceptable use")
    assert "education-access key" in use and "(§3)" in use
    termination = _section(html, "10. Termination")
    assert "education access" in termination and "with or without notice" in termination


def test_the_terms_period_is_the_one_the_settings_allow() -> None:
    fees = _section(_page("terms.html"), "3. Fees and tiers")
    match = re.search(r"at most (\d+) months", fees)
    assert match and int(match.group(1)) == Settings().education_max_months


def test_both_pages_carry_the_new_date() -> None:
    for name in ("privacy.html", "terms.html"):
        assert "Last updated: November 2026." in _page(name), name


def test_the_contact_address_is_the_same_everywhere_the_pages_give_one() -> None:
    # the sign-up box on the home page shows an example address as its placeholder; it is not a contact
    placeholder = {"you@company.com"}
    for name in ("index.html", "privacy.html", "terms.html"):
        found = set(re.findall(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.[a-z]{2,}", _page(name)))
        assert found - placeholder <= {CONTACT}, (name, found)


def test_no_confirm_highlight_reaches_a_page() -> None:
    """The review page highlights wording for the owner to confirm; the portal must never carry the marks."""
    for name in ("index.html", "privacy.html", "terms.html"):
        assert 'class="confirm"' not in _page(name) and "[[" not in _page(name), name

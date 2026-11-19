"""tests/test_education_portal_text.py — the portal's education text says what the code does.

Reasoning:
- docs/plan-education-tier.md section 5 puts three promises in the portal before applications are taken by
  e-mail: the home page's one paragraph, the privacy policy's data and retention statement and its sub-processor
  list, and the terms' conditions (free and discretionary, non-commercial, no sharing, may end without notice,
  18 or over). The wording is a draft for a lawyer's read; these tests do not judge it. They stop it drifting
  from the code and from itself: a number on the page that the settings own, the one contact address, the
  section numbers the cross-references point at.
- The page must not state a number the settings could change without the page changing, so the only number
  the home page gives (the longest grant) is read back from `Settings().education_max_months`.
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
    assert 'href="terms.html"' in text and 'href="privacy.html"' in text
    # it says by hand and non-commercial, so no one reads it as an automatic or commercial offer
    assert "by hand" in text and "non-commercial" in text


def test_privacy_says_what_is_kept_where_and_for_how_long() -> None:
    section = _section(_page("privacy.html"), "2. Personal data we collect about your account")
    assert CONTACT in section
    assert "not copied into the pyvar.com database" in section
    assert "12 months after we refuse an application, or 12 months after the grant ends" in section
    assert "Article 6(1)(b)" in section and "Article 6(1)(f)" in section
    # a name is no longer ruled out in absolute terms: only sign-up is
    assert "sign-up collects no name" in section


def test_privacy_lists_the_mailbox_that_receives_applications_as_a_sub_processor() -> None:
    section = _section(_page("privacy.html"), "9. Where your data is hosted, and who else sees it")
    row = re.search(r"<tr><td>Our e-mail provider</td>.*?</tr>", section, re.S)
    assert row, "the sub-processor table has no row for the mailbox"
    assert CONTACT in row.group(0)


def test_terms_hold_the_three_conditions_in_the_sections_the_plan_names() -> None:
    html = _page("terms.html")
    fees = _section(html, "3. Fees and tiers")
    assert "Education access" in fees
    for words in ("free tier for teaching and study", "non-commercial", "18 or over", "by hand"):
        assert words in fees, words
    assert "returns to the free tier" in fees
    use = _section(html, "4. Acceptable use")
    assert "education-access key" in use and "(§3)" in use
    termination = _section(html, "10. Termination")
    assert "education grant" in termination and "with or without notice" in termination


def test_both_pages_carry_the_new_date() -> None:
    for name in ("privacy.html", "terms.html"):
        assert "Last updated: November 2026." in _page(name), name


def test_the_contact_address_is_the_same_everywhere_the_pages_give_one() -> None:
    # the sign-up box on the home page shows an example address as its placeholder; it is not a contact
    placeholder = {"you@company.com"}
    for name in ("index.html", "privacy.html", "terms.html"):
        found = set(re.findall(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.[a-z]{2,}", _page(name)))
        assert found - placeholder <= {CONTACT}, (name, found)

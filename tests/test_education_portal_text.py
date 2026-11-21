"""tests/test_education_portal_text.py — the portal's education text says what the code does.

Reasoning:
- docs/plan-education-tier.md section 5 puts three promises in the portal before applications are taken by
  e-mail: the home page's one paragraph, the privacy policy's data, retention, recipient and lawful-basis
  statement, and the terms' conditions (free and discretionary, non-commercial, no sharing, may end without notice,
  18 or over, a fixed period of at most 12 months that we tell the holder). The wording is a draft for a lawyer's
  read; these tests do not judge it. They stop it drifting from the code and from itself: a number on the page
  that the settings own, the one contact address, the section numbers the cross-references point at, and the
  statements that the code makes true (the logs carry no address; the grant e-mail states the end date; the
  operator's ledger holds none; Sentry's options keep out request bodies and variable values and scrub addresses:
  see tests/test_tier_email_privacy.py, tests/test_education_grant_script.py and tests/test_sentry_privacy.py).
- The page must not state a number the settings could change without the page changing, so the only number the
  home page gives (the longest grant) is read back from `Settings().education_max_months`. The retention periods
  (about a month, 12 months, six years) are an operator's promise, not a setting: they are pinned here so that a
  change to one sentence cannot leave the other contradicting it.
- Owner decisions pinned below (2026-11-20, reviewed plan of 2026-11-21): UK institutions only for now, 18 or over
  for every account, one rule for application e-mails (deleted within two months of the decision, granted or
  refused, no refusal note), six years for tier-change and job records, the privacy policy's bases, retention,
  logs, automated-decision and complaints paragraphs, and the consumer sentences.
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
    # it says by hand, non-commercial, adult, in the UK, and one person each: no one reads it as
    # an automatic, commercial or class-wide offer
    for words in (
        "by hand",
        "non-commercial",
        "18 or over",
        "at an institution in the UK can ask",
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
    # one rule, granted or refused: the e-mail goes within two months of the decision and no note is kept
    # (owner's decision of 2026-11-21); an extension is a new request
    assert (
        "Whether we grant or refuse, we delete the e-mail within two months of our decision" in item
    )
    assert "keep no note of it" in item
    assert "An extension is a new request, and the same rule applies to it" in item
    application = re.search(r"<li><strong>Your application\.</strong>.*?</li>", item, re.S)
    assert application, "the application bullet is missing"
    for gone in (
        "one-line note",
        "about a month",
        "after 30 days",
        "12 months after your access ends",
    ):  # (the logs bullet says "about a month": that is the logs, not the application)
        assert gone not in application.group(0), gone
    # what applicants should send, and what they should not
    assert "a line confirming that you are 18 or over" in item
    assert "Do not send identity documents" in item and "do not send other people's details" in item
    assert "we delete that message and ask you to write again without it" in item
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
    assert "Article 6(1)(b) of the UK GDPR: steps taken at your request" in item
    assert (
        "EU GDPR" not in item
    ), "education access is for UK institutions: the UK GDPR is the one that applies"
    assert "keep your application for up to two months after we decide" in item
    assert "Article 6(1)(f)" in item and "compelling legitimate grounds" in item
    assert "(see §8)" in item


def test_privacy_keeps_tier_change_records_six_years_and_says_what_happens_on_account_deletion() -> (
    None
):
    page = _page("privacy.html")
    item = _education_item(page)
    assert "We keep each of these records for six years from its date and then delete it" in item
    assert "up to 12 months and then goes back to plain" in item
    assert "not deleted on a schedule" not in page and "kept indefinitely" not in item
    assert "an account identifier that we can no longer match to you" in item
    assert "we delete your e-mail address and switch off your API keys" in item
    keep = _section(page, "4. How long computation and account records are kept")
    assert (
        "Records of tier changes are kept for six years from their date, and so are job records."
        in keep
    )
    assert "is kept for six years from its date as a compliance audit trail" in keep
    assert "retained indefinitely" not in keep and "never deleted programmatically" not in keep
    assert "for as long as your account is open" in keep
    assert "we delete your e-mail address and switch off your API keys within one month" in keep
    assert "the account itself stays as an identifier with no e-mail address" in keep
    assert (
        "Our application logs, kept for about one month, carry the domain of your e-mail address"
        in keep
    )
    # the IP-address sentences: the CloudFront period is pinned to the CDK constant in
    # tests/test_cdk_access_log_retention.py; the cache claim is about the hourly and daily IP counters
    assert "We also use the IP address of a request to limit abuse" in keep
    assert "keep it in our cache for up to about a day" in keep


def test_privacy_states_purposes_and_bases_for_ordinary_accounts_too() -> None:
    section = _section(_page("privacy.html"), "2. Personal data we collect about your account")
    assert "Why we use it, and on what basis" in section
    for words in ("performance of our contract", "our legitimate interests", "legal obligation"):
        assert words in section, words
    assert "We do not use your data for marketing and we do not sell it" in section
    assert "without one we cannot create it" in section
    # the owner's sentence on automated decisions. Until 2026-11-21 it also named a Pro account moving to Free at a
    # monthly limit; a monthly limit is now a refusal (docs/plan-pro-tier-stripe.md), so that clause must not return.
    assert "moves to free automatically" not in section
    assert "Education accounts are held to the free limits automatically" in section
    assert "nothing else about your account is decided by automated means" in section


def test_privacy_rights_name_both_laws_and_both_complaint_routes() -> None:
    section = _section(_page("privacy.html"), "8. Your rights, and how to exercise them")
    assert "UK GDPR and, where it applies to you, the EU GDPR" in section
    assert "we reply within one month" in section
    assert "data protection authority of the country where you live or work" in section
    # a complaint to Fibtec comes first and has a stated clock (UK GDPR Article 13(2)(ca))
    assert "Data protection complaint" in section and "acknowledge it within 30 days" in section
    assert CONTACT in section


def test_privacy_does_not_claim_more_than_the_sentry_options_do() -> None:
    section = _section(_page("privacy.html"), "9. Where your data is hosted, and who else sees it")
    row = re.search(r"<tr><td>Sentry</td>.*?</tr>", section, re.S)
    assert row, "the sub-processor table has no row for Sentry"
    text = row.group(0)
    assert "no request content and no variable values" in text
    assert "e-mail address from a report before it is sent" in text


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
        "work done for a client, an employer or a research sponsor who pays for the results or controls them",
        "18 or over",
        "by hand",
        "a teacher or student at a university, college or school in the United Kingdom, and already hold",
        "for a fixed period of at most 12 months that we tell you when we grant it",
        "Each person applies for themselves",
    ):
        assert words in fees, words
    assert "goes back to the free tier" in fees and "we send no reminder" in fees
    use = _section(html, "4. Acceptable use")
    assert "education-access key" in use and "(§3)" in use
    termination = _section(html, "10. Termination")
    assert "education access" in termination and "with or without notice" in termination


def test_terms_set_a_general_minimum_age_and_protect_consumers() -> None:
    html = _page("terms.html")
    account = _section(html, "2. Your account")
    assert "You must be 18 or over to create an account or to use pyvar.com" in account
    liability = _section(html, "8. Limitation of liability")
    assert "as a consumer" in liability and "reasonable care and skill" in liability
    assert "Nothing in §7 or in this section limits those rights" in liability
    law = _section(html, "12. Governing law")
    assert "If you are a consumer" in law and "cannot be removed by agreement" in law


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

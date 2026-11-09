"""The portal's pages, their links to each other and the sitemap stay in step.

Reasoning:
- Search Console (2026-11-09) showed 15 of 19 sitemap pages never crawled. The nav and footer are written by
  `document.write` scripts, so the static HTML linked almost nowhere: each domain page had one inbound link,
  local.html none, and every page linked home as index.html, a duplicate of `/` (the one "alternate page with
  proper canonical tag"). scripts/sync_portal_seo.py now owns the plain-HTML all-pages block, the sitemap's
  lastmod and the checks; these tests run its checker, so a page added, renamed or edited by hand cannot
  quietly put the portal back out of step.
- The checker needs no git (the pipeline's CodeBuild gets a file snapshot), so these run there too.
- The negative tests break a copy of the portal on purpose: a checker that cannot fail proves nothing.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import sync_portal_seo as seo  # noqa: E402


def test_the_portal_is_in_step() -> None:
    assert seo.problems() == [], "run: python scripts/sync_portal_seo.py, then commit"


def test_every_page_links_to_every_page_in_its_plain_html() -> None:
    """What a crawler that does not run scripts sees: the JS nav and footer are not in this text."""
    wanted = {seo.href_of(name) for name in seo.PAGES}
    for page in seo.portal_pages(seo.PORTAL):
        hrefs = set(re.findall(r'<a\s[^>]*href="([^"#?]+)', page.read_text(encoding="utf-8")))
        assert wanted <= hrefs, f"{page.name} lacks {sorted(wanted - hrefs)}"


def test_nothing_links_home_as_index_html() -> None:
    """index.html is a 200 duplicate of / whose canonical is /; linking to it is how Google found it."""
    for page in [
        *seo.portal_pages(seo.PORTAL),
        seo.PORTAL / "pyvar.js",
        seo.PORTAL / "dashboard.html",
    ]:
        assert not re.search(
            r"""href(=|:\s*)["']index\.html""", page.read_text(encoding="utf-8")
        ), page.name


def test_the_sitemap_lists_exactly_the_pages_with_a_valid_lastmod() -> None:
    entries = seo.read_sitemap(seo.PORTAL)
    assert [e["loc"] for e in entries].count(seo.BASE) == 1
    assert {e["loc"] for e in entries} == {seo.url_of(n) for n in seo.PAGES}
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["lastmod"]) for e in entries)
    assert "dashboard" not in (seo.PORTAL / "sitemap.xml").read_text(encoding="utf-8")


def test_the_dashboard_stays_out_of_the_sitemap_and_is_disallowed() -> None:
    assert "Disallow: /dashboard.html" in (seo.PORTAL / "robots.txt").read_text(encoding="utf-8")


# ── the checker can fail ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def portal_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "portal"
    dest.mkdir()
    for name in ("pyvar.js", "sitemap.xml", "robots.txt"):
        shutil.copy(seo.PORTAL / name, dest / name)
    for page in seo.PORTAL.glob("*.html"):
        shutil.copy(page, dest / page.name)
    assert seo.problems(dest) == []
    return dest


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_a_link_back_to_index_html_is_reported(portal_copy: Path) -> None:
    _edit(
        portal_copy / "guides.html",
        '<a href="/" class="btn-ghost">',
        '<a href="index.html" class="btn-ghost">',
    )
    assert any("guides.html: links home as index.html" in p for p in seo.problems(portal_copy))
    _edit(portal_copy / "pyvar.js", "href:'/'", "href:'index.html'")
    assert any(p.startswith("pyvar.js") for p in seo.problems(portal_copy))


def test_a_stale_or_missing_block_is_reported(portal_copy: Path) -> None:
    _edit(portal_copy / "local.html", '<a href="privacy.html">Privacy policy</a>', "")
    assert any(
        "local.html: the all-pages block is missing or stale" in p
        for p in seo.problems(portal_copy)
    )
    page = portal_copy / "terms.html"
    page.write_text(seo.BLOCK_RE.sub("", page.read_text(encoding="utf-8")), encoding="utf-8")
    assert any(
        "terms.html: the all-pages block is missing or stale" in p
        for p in seo.problems(portal_copy)
    )


def test_a_wrong_canonical_is_reported(portal_copy: Path) -> None:
    _edit(
        portal_copy / "plugins.html", "https://www.pyvar.com/plugins.html", "https://www.pyvar.com/"
    )
    assert any("plugins.html: canonical" in p for p in seo.problems(portal_copy))


def test_a_sitemap_gap_a_duplicate_or_a_bad_lastmod_is_reported(portal_copy: Path) -> None:
    sitemap = portal_copy / "sitemap.xml"
    original = sitemap.read_text(encoding="utf-8")
    sitemap.write_text(
        re.sub(
            r"<url>\s*<loc>https://www.pyvar.com/local.html</loc>.*?</url>",
            "",
            original,
            flags=re.S,
        )
    )
    assert any("URLs differ from the pages" in p for p in seo.problems(portal_copy))
    sitemap.write_text(original.replace("<lastmod>", "<lastmod>not-a-date", 1))
    assert any("no valid lastmod" in p for p in seo.problems(portal_copy))
    sitemap.write_text(
        re.sub(r"<lastmod>[^<]*</lastmod>", "<lastmod>2999-01-01</lastmod>", original, count=1)
    )
    assert any("in the future" in p for p in seo.problems(portal_copy))


def test_a_page_missing_from_the_list_is_reported(portal_copy: Path) -> None:
    (portal_copy / "new-page.html").write_text("<html></html>", encoding="utf-8")
    assert any("pages differ from the list" in p for p in seo.problems(portal_copy))


# ── the generator ───────────────────────────────────────────────────────────────────────────────────


def test_sync_restores_the_block_and_is_idempotent(
    portal_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(seo, "git_lastmod", lambda name: "2026-11-09")
    page = portal_copy / "domain-alm.html"
    page.write_text(seo.BLOCK_RE.sub("", page.read_text(encoding="utf-8")), encoding="utf-8")
    assert seo.problems(portal_copy)
    seo.sync(portal_copy)
    assert seo.problems(portal_copy) == []
    first = {p.name: p.read_bytes() for p in portal_copy.iterdir() if p.is_file()}
    seo.sync(portal_copy)
    assert first == {p.name: p.read_bytes() for p in portal_copy.iterdir() if p.is_file()}


def test_sync_puts_the_block_directly_above_the_footer_script(portal_copy: Path) -> None:
    page = portal_copy / "guides.html"
    text = page.read_text(encoding="utf-8")
    assert text.index("<!-- site-links:end -->") < text.index(seo.FOOTER_CALL)
    with pytest.raises(ValueError):
        seo.with_block("<html>no footer here</html>")


def test_git_lastmod_is_always_a_date() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", seo.git_lastmod("index.html"))
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", seo.git_lastmod("no-such-page.html"))

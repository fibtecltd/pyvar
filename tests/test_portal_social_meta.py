"""Social-preview metadata for the static portal.

LinkedIn (and Facebook/Slack) build link previews from ``og:image`` only --
``twitter:image`` is ignored by them, so a page that sets just the latter
unfurls with no picture. These tests pin that every portal page that
declares Open Graph tags also declares a real, correctly described image.
"""

from __future__ import annotations

import struct
from html.parser import HTMLParser
from pathlib import Path

import pytest

PORTAL_DIR = Path(__file__).resolve().parent.parent / "portal"
SITE = "https://www.pyvar.com/"
LINKEDIN_MAX_BYTES = 5 * 1024 * 1024  # LinkedIn rejects share images over 5 MB
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class _MetaCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.og: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        attr = dict(attrs)
        prop = attr.get("property") or ""
        if prop.startswith("og:") and attr.get("content") is not None:
            self.og[prop] = attr["content"] or ""


def _og_tags(page: Path) -> dict[str, str]:
    collector = _MetaCollector()
    collector.feed(page.read_text(encoding="utf-8"))
    return collector.og


def _pages_with_og() -> list[Path]:
    return [p for p in sorted(PORTAL_DIR.glob("*.html")) if "og:title" in _og_tags(p)]


def _png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == PNG_MAGIC, f"{path.name} is not a PNG"
    width, height = struct.unpack(">II", head[16:24])
    return width, height


def test_portal_has_pages_with_open_graph_tags() -> None:
    assert len(_pages_with_og()) >= 19


@pytest.mark.parametrize("page", _pages_with_og(), ids=lambda p: p.name)
def test_every_og_page_declares_a_valid_og_image(page: Path) -> None:
    og = _og_tags(page)

    image_url = og.get("og:image")
    assert image_url, f"{page.name}: og:image missing (LinkedIn shows no picture)"
    assert image_url.startswith(SITE), f"{page.name}: og:image must be an absolute {SITE} URL"
    assert og.get("og:image:alt"), f"{page.name}: og:image:alt missing"

    image_file = PORTAL_DIR / image_url.removeprefix(SITE)
    assert image_file.is_file(), f"{page.name}: {image_url} is not served from portal/"
    assert image_file.stat().st_size < LINKEDIN_MAX_BYTES

    width, height = _png_size(image_file)
    assert (int(og["og:image:width"]), int(og["og:image:height"])) == (width, height)
    assert width >= 1200, "LinkedIn shows the large card only from 1200 px wide"
    assert abs(width / height - 1.91) < 0.03, "share image should be ~1.91:1"


def test_og_image_url_matches_og_url_host() -> None:
    for page in _pages_with_og():
        og = _og_tags(page)
        assert og["og:url"].startswith(SITE), page.name
        assert og["og:image"].startswith(SITE), page.name

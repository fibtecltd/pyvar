"""The portal header has a plain "Sign in" link to the left of the "Get API key" button.

Why: a returning visitor had only "Get API key" to click, which reads as sign-up (the form behind it is also the sign-in
form, but nothing said so). The header is built by `buildNav()` in portal/pyvar.js, shared by every page, so this runs the
real function under node and checks what it returns, then reads the stylesheet for the two things the markup cannot show:
that the link is plain (no button look, "Get API key" stays the one filled button) and that on a phone neither wraps.

The link goes to dashboard.html, which for a signed-in visitor is the dashboard and for a signed-out one is the "Sign in to
manage your API keys" page that links to the sign-in form (`/#get-api-key`: an e-mail link or Google).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / "portal"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

# pyvar.js is a browser script: it touches the document at load. Stub just enough for it to load, then call buildNav.
PROBE = r"""
const fs = require('fs'), vm = require('vm');
const noop = () => {};
const el = new Proxy(function () {}, {
  get: (t, k) => (k === 'style' || k === 'classList' || k === 'dataset')
    ? new Proxy({}, { get: () => noop, set: () => true }) : (k === Symbol.toPrimitive ? () => '' : noop),
  set: () => true, apply: () => el });
const ctx = {
  console,
  document: { addEventListener: noop, getElementById: () => null, querySelector: () => null,
    querySelectorAll: () => [], createElement: () => el, readyState: 'loading', write: noop, body: el,
    documentElement: el, head: el },
  window: { addEventListener: noop, location: { search: '', hash: '', pathname: '/', href: '' },
    history: { replaceState: noop }, matchMedia: () => ({ matches: false, addEventListener: noop }) },
  localStorage: { getItem: () => null, setItem: noop }, sessionStorage: { getItem: () => null, setItem: noop },
  fetch: () => Promise.reject(new Error('offline')), navigator: { clipboard: {} }, setTimeout: noop,
  IntersectionObserver: function () { this.observe = noop; },
  location: { search: '', hash: '', pathname: '/' }, URLSearchParams, URL };
ctx.window.document = ctx.document;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8') + '\n;globalThis.__out = {home: buildNav("home"), other: buildNav("guides")};', ctx);
console.log(JSON.stringify(ctx.__out));
"""


def built_navs(tmp_path: Path) -> dict[str, str]:
    script = tmp_path / "probe.js"
    script.write_text(PROBE, encoding="utf-8")
    node = shutil.which("node")
    assert node is not None
    done = subprocess.run(  # noqa: S603 - a fixed script and the repo's own file, no user input
        [node, str(script), str(PORTAL / "pyvar.js")],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(done.stdout)


def right_hand_links(nav: str) -> list[tuple[str, str, str]]:
    """(class, href, text) of each link in the header's right-hand block, in page order."""
    block = nav.split('<div class="nav-right">', 1)[1]
    return [
        (cls, href, re.sub(r"<[^>]+>", "", text).strip())
        for href, cls, text in re.findall(
            r'<a href="([^"]*)"[^>]*class="([^"]*)"[^>]*>(.*?)</a>', block, re.S
        )
    ]


@needs_node
@pytest.mark.parametrize("page", ["home", "other"])
def test_sign_in_is_a_plain_link_immediately_left_of_get_api_key(tmp_path: Path, page: str) -> None:
    links = right_hand_links(built_navs(tmp_path)[page])
    texts = [text for _, _, text in links]
    assert texts[-2:] == ["Sign in", "Get API key"], links
    (sign_cls, sign_href, _), (cta_cls, cta_href, _) = links[-2:]
    assert (sign_cls, sign_href) == ("nav-signin", "dashboard.html")
    assert (cta_cls, cta_href) == ("nav-cta", "/#get-api-key")  # still the main button, same target


def css_rule(selector: str) -> str:
    """The body of the first top-level rule for exactly `selector` in the portal stylesheet."""
    css = (PORTAL / "pyvar.css").read_text(encoding="utf-8")
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, selector
    return match.group(1)


def test_the_sign_in_link_has_no_button_look_and_get_api_key_keeps_its_fill() -> None:
    plain = css_rule(".nav-signin")
    assert "background" not in plain and "border" not in plain
    assert "background: var(--green)" in css_rule(".nav-cta")


def media_blocks(css: str, query: str) -> list[str]:
    """The bodies of every `@media (<query>) { ... }` block (the rules inside have no nested braces of their own)."""
    return re.findall(r"@media \(" + re.escape(query) + r"\)\s*\{(.*?)\n\}", css, re.S)


def test_neither_header_link_wraps_and_the_phone_bar_makes_room() -> None:
    css = (PORTAL / "pyvar.css").read_text(encoding="utf-8")
    assert re.search(r"\.nav-signin,\s*\.nav-cta\s*\{\s*white-space:\s*nowrap", css)
    phone = [b for b in media_blocks(css, "max-width: 600px") if ".nav-signin" in b]
    assert len(phone) == 1, "the phone rules for the header"
    assert (
        ".nav-gh { display: none; }" in phone[0]
    )  # the long "by fibtec.co.uk" button still goes first
    assert (
        ".nav-search-btn kbd { display: none; }" in phone[0]
    )  # a key hint means nothing without a keyboard
    smallest = [b for b in media_blocks(css, "max-width: 380px") if ".nav-logo-domain" in b]
    assert len(smallest) == 1 and ".nav-logo-domain { display: none; }" in smallest[0]


def test_the_page_the_link_opens_exists_and_leads_to_the_sign_in_form() -> None:
    assert (PORTAL / "dashboard.html").is_file()
    script = (PORTAL / "pyvar.js").read_text(encoding="utf-8")
    # signed out: a title that says so and a link to the form that signs in by e-mail link or Google
    assert "Sign in to manage your API keys" in script
    assert "href:'/#get-api-key' }, 'Sign in or get a key'" in script
    assert 'id="get-api-key"' in (PORTAL / "index.html").read_text(encoding="utf-8")

"""The dashboard fits a phone (portal/dashboard.html, portal/pyvar.js; found while building issue #454).

Reasoning:
- What was wrong: the card sits in `.dash-wrap > .container`, and `.dash-wrap` is a centring flex row. A flex item will
  not shrink below the minimum width of its content, and the seven-column keys table has a minimum of about 450 px, so on
  a phone the container, and the card in it, grew past the screen. Being centred, the excess spilled off the LEFT edge,
  where a page cannot be scrolled to: part of the card, and the Upgrade button, could not be reached.
- The cure is three rules, each pinned here as source (no browser runs in CI): the container may shrink (`min-width:0`),
  the table scrolls sideways in its own box (`.key-table-wrap{overflow-x:auto}`, and the table is only ever built inside
  that box), and the card's text lines break inside a long unbroken word, such as a 64-character key name or an address
  with no hyphen (`.dash-body{overflow-wrap:anywhere}`).
- These rules were measured in Chromium when they were added (see the pull request): at 320 to 1280 px the page is never
  wider than the screen, with 64-character key names, a 127-character address, a notice, a long error and a fresh key;
  and at 600 px and up, with ordinary content, the card is pixel-identical to what it was.
"""

from __future__ import annotations

import re
from pathlib import Path

PORTAL = Path(__file__).resolve().parent.parent / "portal"
HTML = (PORTAL / "dashboard.html").read_text(encoding="utf-8")
SOURCE = (PORTAL / "pyvar.js").read_text(encoding="utf-8")


def css_rules() -> dict[str, dict[str, str]]:
    """The inline <style> of dashboard.html as {selector: {property: value}}, comments removed."""
    match = re.search(r"<style>(.*?)</style>", HTML, re.S)
    assert match is not None, "dashboard.html has no inline <style>"
    style = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.S)
    rules: dict[str, dict[str, str]] = {}
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", style):
        declarations: dict[str, str] = {}
        for declaration in body.split(";"):
            if ":" in declaration:
                name, value = declaration.split(":", 1)
                declarations[name.strip()] = value.strip()
        rules[" ".join(selector.split())] = declarations
    return rules


def key_manager_body() -> str:
    body = SOURCE[SOURCE.index("async function renderKeyManager") :]
    return body[: body.index("\n}\n")]


def test_the_container_may_shrink_below_its_content_so_the_card_never_outgrows_the_screen() -> None:
    assert css_rules()[".dash-wrap>.container"].get("min-width") == "0"


def test_that_rule_still_matches_the_markup_it_is_written_for() -> None:
    # The selector is a direct-child one: it stops working if the container is moved or renamed.
    assert re.search(r'<section class="dash-wrap">\s*<div class="container">', HTML)


def test_the_keys_table_scrolls_sideways_in_its_own_box() -> None:
    wrap = css_rules()[".key-table-wrap"]
    assert wrap.get("overflow-x") == "auto"
    # The table's own vertical margin moved to the box: left on both it would be doubled.
    assert "margin" not in css_rules()[".key-table"]


def test_the_keys_table_is_only_ever_built_inside_that_box() -> None:
    body = key_manager_body()
    assert len(re.findall(r"_h\('table'", body)) == 1
    assert re.search(
        r"_h\('div', \{ class: 'key-table-wrap' \},\s*_h\('table', \{ class: 'key-table' \}", body
    )


def test_long_unbroken_text_breaks_inside_the_card() -> None:
    # `.dash-body` carries the account line, the notice, the "New key" line, the hint and the error text.
    assert css_rules()[".dash-body"].get("overflow-wrap") == "anywhere"


def test_the_fresh_key_box_already_breaks_anywhere() -> None:
    assert css_rules()[".dash-token"].get("word-break") == "break-all"

"""The Google sign-in button must render in English on every portal page.

Reasoning:
- Every other string on pyvar.com is English-only, but Google Identity Services picks
  the button language from the viewer's browser/Google account, so an Italian visitor
  saw "Accedi con Google".
- ``?hl=en`` on the library URL does not fix it (measured in headless Chromium with an
  it-IT locale: the button iframe URL carries no ``hl``). The ``locale`` option of
  ``renderButton`` does (the iframe URL then carries ``hl=en``), so that is what is pinned
  here. A static check is enough: the widget itself is rendered by Google, not by us.
"""

from __future__ import annotations

import re
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent.parent / "portal"
RENDER_BUTTON = re.compile(r"renderButton\(([^;]*?)\);", re.DOTALL)


def _render_button_calls() -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    for page in sorted([*PORTAL_DIR.glob("*.js"), *PORTAL_DIR.glob("*.html")]):
        for match in RENDER_BUTTON.finditer(page.read_text(encoding="utf-8")):
            calls.append((page.name, match.group(1)))
    return calls


def test_the_portal_renders_a_google_button_somewhere() -> None:
    assert _render_button_calls(), "no google.accounts.id.renderButton call found in portal/"


def test_every_google_button_is_pinned_to_english() -> None:
    unpinned = [
        name
        for name, args in _render_button_calls()
        if not re.search(r"locale:\s*['\"]en['\"]", args)
    ]
    assert not unpinned, (
        "renderButton without locale: 'en' follows the visitor's language "
        f"('Accedi con Google'): {unpinned}"
    )

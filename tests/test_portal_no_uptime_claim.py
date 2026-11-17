"""tests/test_portal_no_uptime_claim.py — the home page states no uptime percentage.

Reasoning:
- The status bar once showed "99.97% uptime" as fixed text with no source anywhere in the repository, beside Terms that
  disclaim availability (portal/terms.html). Until a measured figure exists, the page must not carry one.
"""

from __future__ import annotations

import re
from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "portal" / "index.html"


def test_the_home_page_has_no_uptime_percentage() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert not re.search(r"\d+(\.\d+)?\s*%\s*uptime", html, flags=re.IGNORECASE)


def test_the_status_bar_still_lists_the_other_items() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert html.count('class="status-item"') >= 3

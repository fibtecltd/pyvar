#!/usr/bin/env python3
"""scripts/audit_formula_overflow.py — which formulas run off the edge of the Try it panel.

Reasoning:
- Every function's "Try it" panel on the portal shows its formula (portal/functions.json, from
  scripts/data/function_formulas.json) rendered by KaTeX. A formula wider than its box used to be
  cut off with nothing to say more followed. This opens the panel of every function on a real page
  in headless Chromium and measures the formula box, so a newly added or edited formula that does
  not fit is found before a visitor finds it.
- "Overflows" means the box has to scroll sideways (scrollWidth > clientWidth), the only way text
  can be hidden. Formulas that render as a KaTeX error are reported too, and so is a whole panel
  that is wider than its card (a long unbroken word in a description, for instance).
- Two viewports: desktop (1280 px, where the panel is 640 px wide) and phone (390 px). The exit
  status follows the desktop result only: on a phone most long formulas scroll by design, behind
  the shaded edge portal/pyvar.css draws; the phone count is for information.
- Tooling dependency of this script only:  pip install playwright

Usage (repo root):
    python scripts/audit_formula_overflow.py                          # the live site
    python -m http.server 8077 --directory portal &                   # or a local copy
    python scripts/audit_formula_overflow.py --site http://127.0.0.1:8077
    python scripts/audit_formula_overflow.py --csv /tmp/overflow.csv --chromium /opt/pw-browsers/chromium
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import ViewportSize, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE = "https://www.pyvar.com"
VIEWPORTS = {
    "desktop": ViewportSize(width=1280, height=900),
    "phone": ViewportSize(width=390, height=844),
}

# Runs in the page: open each function of one domain in the Try it panel, wait for KaTeX, measure.
MEASURE_JS = """
async (slug) => {
  const all = await fetch('functions.json').then(r => r.json());
  const out = [];
  for (const fn of all.filter(f => f.domain === slug)) {
    openTryItPanel(fn, null);
    for (let i = 0; i < 150; i++) {
      const el = document.getElementById('tryitFormula');
      if (el && (el.querySelector('.katex') || el.querySelector('.katex-error'))) break;
      await new Promise(r => setTimeout(r, 20));
    }
    const box = document.querySelector('#tryitFormula .tryit-formula-katex') || document.body;
    const card = document.querySelector('.tryit-card');
    out.push({
      card: card.scrollWidth - card.clientWidth,
      name: fn.name,
      rendered: !!box.querySelector('.katex'),
      errors: box.querySelectorAll('.katex-error').length,
      box: box.clientWidth,
      content: box.scrollWidth,
    });
  }
  return out;
}
"""


def audit(site: str, chromium: str | None) -> list[dict[str, Any]]:
    catalogue = json.loads((ROOT / "portal" / "functions.json").read_text(encoding="utf-8"))
    pages: dict[str, str] = {}
    for entry in catalogue:
        pages.setdefault(entry["domain_page"], entry["domain"])
    proxy = os.environ.get("HTTPS_PROXY") if site.startswith("https://") else None

    rows: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=chromium, proxy={"server": proxy} if proxy else None
        )
        for label, viewport in VIEWPORTS.items():
            context = browser.new_context(viewport=viewport)
            for page_name, slug in pages.items():
                page = context.new_page()
                page.goto(f"{site.rstrip('/')}/{page_name}", wait_until="networkidle")
                page.wait_for_selector("#fnGrid .fn-card")
                for row in page.evaluate(MEASURE_JS, slug):
                    rows.append({**row, "viewport": label, "domain": slug})
                page.close()
            context.close()
        browser.close()
    for row in rows:
        row["hidden"] = max(0, row["content"] - row["box"])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--site", default=DEFAULT_SITE, help="where the portal pages are served")
    parser.add_argument("--chromium", default=None, help="path to a Chromium executable")
    parser.add_argument("--csv", default="", help="write every overflowing function to this file")
    args = parser.parse_args()

    rows = audit(args.site, args.chromium)
    failed = False
    for label in VIEWPORTS:
        subset = [r for r in rows if r["viewport"] == label]
        over = sorted((r for r in subset if r["hidden"] > 1), key=lambda r: -r["hidden"])
        broken = [r for r in subset if not r["rendered"] or r["errors"]]
        wide = [r for r in subset if r["card"] > 1]
        print(
            f"{label}: {len(over)} of {len(subset)} formulas need sideways scrolling "
            f"(box {subset[0]['box']} px); {len(broken)} did not render; "
            f"{len(wide)} panels wider than their card"
        )
        for r in wide:
            print(f"  panel wider than its card by {r['card']} px: {r['name']}")
        for r in over[:15]:
            print(f"  {r['domain']:<13}{r['name']:<44}{r['hidden']:>5} px hidden")
        if len(over) > 15:
            print(f"  ... and {len(over) - 15} more")
        if label == "desktop":
            failed = bool(over or broken or wide)
    if args.csv:
        by_name: dict[str, dict[str, dict[str, Any]]] = {}
        for r in rows:
            by_name.setdefault(r["name"], {})[r["viewport"]] = r
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["domain", "function", "desktop_hidden_px", "phone_hidden_px"])
            for name, pair in sorted(
                by_name.items(), key=lambda kv: (-kv[1]["desktop"]["hidden"], kv[0])
            ):
                if pair["desktop"]["hidden"] > 1 or pair["phone"]["hidden"] > 1:
                    writer.writerow(
                        [
                            pair["desktop"]["domain"],
                            name,
                            pair["desktop"]["hidden"],
                            pair["phone"]["hidden"],
                        ]
                    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

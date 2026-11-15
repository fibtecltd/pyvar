#!/usr/bin/env python3
"""scripts/generate_assistant_screenshots.py: portal screens of the assistant for the Medium article.

Reasoning:
- Each screen is the site's own: the script opens the live function page the way a visitor would
  (deep link, Try-it panel, one click on a control of the "About this function" box) and takes a
  picture of the panel with a margin of the dimmed page around it, at twice the pixel density.
- The assistant calls no API: its answers are static files, so there is nothing to mock and no key
  is involved. What the screen shows is checked, not assumed: the site must report the bank
  version committed in portal/assistant/bank/manifest.json, and the answer on screen must start
  with the text the committed bank holds for that function and control.
- The three screens show the three controls on three functions in three domains. All of those
  answers were read by a person and found supported by the catalogue record, except the first,
  whose claims are all in the description that is on screen above it.
- Medium takes PNG or JPG. Tooling dependency of this script only:  pip install playwright  (it
  launches the Chromium it finds; pass --chromium PATH for a browser installed elsewhere). The site
  must be reachable, or pass --site http://127.0.0.1:8077 for a local copy of portal/
  (python -m http.server 8077 --directory portal), which shows a portal change before it is deployed.
  A static server has no /public/config, so for a local site the script answers that one request with
  what the live site reports, built from the committed manifest.

Usage (repo root):
    python scripts/generate_assistant_screenshots.py
    python scripts/generate_assistant_screenshots.py --only lcr-when-to-use-it --out /tmp/shots
    python scripts/generate_assistant_screenshots.py --chromium /opt/pw-browsers/chromium
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DEFAULT_OUT = ROOT / "docs" / "publications" / "assets" / "assistant"
DEFAULT_SITE = "https://www.pyvar.com"
BANK_DIR = ROOT / "portal" / "assistant" / "bank"
VIEWPORT_WIDTH, VIEWPORT_HEIGHT = 1100, 1500
MARGIN = 24  # CSS px of dimmed page kept around the panel
BUTTON = {"explain": "What it does", "when": "When to use it"}


@dataclass(frozen=True)
class Shot:
    key: str  # the --only name and the file name
    function: str
    control: str  # explain, when or compare
    sibling: str | None = None  # the function picked in the Compare with menu


SHOTS = [
    Shot("kupiec-what-it-does", "kupiec_pof_test", "explain"),
    Shot("lcr-when-to-use-it", "liquidity_coverage_ratio_lcr", "when"),
    Shot(
        "risk-parity-compare",
        "risk_parity_portfolio",
        "compare",
        "maximum_sharpe_ratio_portfolio",
    ),
]


class ShotError(RuntimeError):
    """A screen failed one of its own checks."""


def need(cond: bool, msg: str) -> None:
    if not cond:
        raise ShotError(msg)


def plain(text: str) -> str:
    """Text as a reader sees it: no code ticks or bold marks, one space between words."""
    return re.sub(r"\s+", " ", text.replace("`", "").replace("**", "")).strip()


def committed_bank() -> tuple[str, dict[str, dict[str, object]]]:
    manifest = json.loads((BANK_DIR / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["bank_version"]
    answers = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in (BANK_DIR / version).glob("*.json")
    }
    return version, answers


def domain_page(function: str) -> str:
    entries = json.loads((ROOT / "portal" / "functions.json").read_text(encoding="utf-8"))
    for entry in entries:
        if entry["name"] == function:
            return str(entry["domain_page"])
    raise ShotError(f"{function} is not in the catalogue")


def expected_text(shot: Shot, answers: dict[str, dict[str, object]]) -> str:
    entry = answers[shot.function]
    if shot.control == "compare":
        assert shot.sibling is not None
        return str(entry["compare"][shot.sibling]["text"])  # type: ignore[index]
    return str(entry[shot.control]["text"])  # type: ignore[index]


async def capture(shot: Shot, site: str, out: Path, chromium: str | None) -> Path:
    from playwright.async_api import FloatRect, ViewportSize, async_playwright

    version, answers = committed_bank()
    expected = plain(expected_text(shot, answers))
    proxy = os.environ.get("HTTPS_PROXY") if site.startswith("https://") else None

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path=chromium, proxy={"server": proxy} if proxy else None  # type: ignore[arg-type]
        )
        viewport = ViewportSize(width=VIEWPORT_WIDTH, height=VIEWPORT_HEIGHT)
        context = await browser.new_context(viewport=viewport, device_scale_factor=2)
        page = await context.new_page()
        if site.startswith(("http://127.0.0.1", "http://localhost")):
            config_body = json.dumps({"assistant_enabled": True, "assistant_bank_version": version})
            await page.route(
                "**/public/config",
                lambda route: route.fulfill(
                    status=200, content_type="application/json", body=config_body
                ),
            )
        url = f"{site.rstrip('/')}/{domain_page(shot.function)}#{shot.function}"
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_selector("#tryitPanel.open")
        await page.wait_for_selector("#assistantSlot .assistant-btn")

        config = await page.evaluate("fetch('/public/config').then(r => r.json())")
        need(config.get("assistant_enabled") is True, "the site reports the assistant as off")
        need(
            config.get("assistant_bank_version") == version,
            f"the site serves bank {config.get('assistant_bank_version')}, the repository has {version}",
        )

        if shot.control == "compare":
            await page.select_option(".assistant-select", shot.sibling)
        else:
            await page.click(f'.assistant-btn:has-text("{BUTTON[shot.control]}")')
        await page.wait_for_function(
            "document.querySelector('.assistant-answer') && "
            "document.querySelector('.assistant-answer').innerText.length > 40"
        )
        shown = plain(await page.locator(".assistant-answer").inner_text())
        need(
            expected[:80] in shown,
            f"{shot.key}: the answer on screen does not start with the committed bank's text",
        )

        await page.evaluate("document.fonts.ready.then(() => document.activeElement.blur())")
        await page.mouse.move(0, 0)
        await page.wait_for_timeout(400)
        box = await page.locator(".tryit-card").bounding_box()
        need(box is not None, "the Try-it panel has no box")
        assert box is not None
        clip = FloatRect(
            x=max(box["x"] - MARGIN, 0),
            y=max(box["y"] - MARGIN, 0),
            width=box["width"] + 2 * MARGIN,
            height=box["height"] + 2 * MARGIN,
        )
        need(
            clip["y"] + clip["height"] <= VIEWPORT_HEIGHT,
            f"{shot.function}: the panel is taller than the viewport",
        )
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"portal-{shot.key}.png"
        await page.screenshot(path=path, clip=clip)
        await browser.close()
    return path


async def run(only: list[str], site: str, out: Path, chromium: str | None) -> None:
    for shot in SHOTS:
        if only and shot.key not in only:
            continue
        path = await capture(shot, site, out, chromium)
        print("wrote", path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def main() -> None:
    names = [s.key for s in SHOTS]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--site", default=DEFAULT_SITE, help="where the portal pages are served")
    parser.add_argument("--only", default="", help="comma-separated: " + ", ".join(names))
    parser.add_argument("--chromium", default=None, help="path to a Chromium executable")
    args = parser.parse_args()
    only = [n for n in args.only.split(",") if n]
    unknown = [n for n in only if n not in names]
    if unknown:
        raise SystemExit(f"unknown screenshot(s): {', '.join(unknown)}")
    asyncio.run(run(only, args.site, Path(args.out), args.chromium))


if __name__ == "__main__":
    main()

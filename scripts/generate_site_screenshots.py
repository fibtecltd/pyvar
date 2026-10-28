#!/usr/bin/env python3
"""scripts/generate_site_screenshots.py — pyvar.com "Try it" screenshots for the overview article.

Reasoning:
- Each "For engineers" box of the overview article has a screenshot of the same call made on the
  site: the "Try it" panel of the function on its domain page, with the inputs filled in and the
  result showing. The page, styles, formula rendering and panel are the site's own: the script
  opens the live page and drives it the way a visitor would (deep link, fill, Run).
- A public script cannot hold an API key, so the panel's one call, POST /api/v1/<domain>/<name>, is
  answered by the real application in-process (the same harness that writes
  docs/plugin-examples.md). The script forwards exactly what the panel posted, so defaults the
  panel adds are included, and it fails if a posted value differs from the example's input. The
  key field shows a masked placeholder, never a key.
- The function, its domain page and whether it has a formula come from portal/functions.json; the
  inputs are the article's (the same seeds and numbers as docs/plugin-examples.md).
- Each PNG is the panel plus a margin of the dimmed page, at twice the pixel density. Medium takes
  PNG or JPG.
- Tooling dependency of this script only:  pip install playwright  (it launches the Chromium it
  finds; pass --chromium PATH for a browser installed elsewhere). The site must be reachable, or
  pass --site http://localhost:8080 for a local copy of portal/.

Usage (repo root):
    python scripts/generate_site_screenshots.py
    python scripts/generate_site_screenshots.py --only market-risk,regulatory --out /tmp/shots
    python scripts/generate_site_screenshots.py --chromium /opt/pw-browsers/chromium
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import generate_plugin_examples as gpe  # noqa: E402  (the real app, in-process)
import generate_plugin_figures as g  # noqa: E402  (gbm fixture, need)

DEFAULT_OUT = ROOT / "docs" / "publications" / "assets" / "overview"
DEFAULT_SITE = "https://www.pyvar.com"
MASKED_KEY = "pyvar_" + "*" * 32
VIEWPORT_WIDTH, VIEWPORT_HEIGHT = 1100, 1500
MARGIN = 24  # CSS px of dimmed page kept around the panel


@dataclass(frozen=True)
class Shot:
    key: str  # the --only name and the file name
    function: str
    params: dict[str, Any]


def shots() -> list[Shot]:
    """One per "For engineers" box, in article order. Inputs as in docs/plugin-examples.md."""
    returns = [float(v) for v in g.gbm(500, 0.0004, 0.011, 7)]
    return [
        Shot(
            "market-risk",
            "historical_simulation_var",
            {"returns": returns, "portfolio_value": 10_000_000, "confidence_level": 0.99},
        ),
        Shot(
            "credit-risk",
            "credit_var_analytical_vasicek",
            {
                "pd": 0.02,
                "lgd": 0.45,
                "ead_total": 50_000_000,
                "asset_correlation": 0.15,
                "confidence_level": 0.999,
            },
        ),
        Shot(
            "liquidity",
            "survival_horizon_calculator",
            {
                "hqla": 100_000_000,
                "daily_net_outflows": [
                    8e6,
                    9e6,
                    11e6,
                    12e6,
                    12e6,
                    10e6,
                    9e6,
                    8e6,
                    8e6,
                    7e6,
                    7e6,
                    6e6,
                ],
            },
        ),
        Shot(
            "regulatory",
            "basel_iv_output_floor",
            {"internal_model_rwa": 28e9, "standardised_rwa": 41e9},
        ),
    ]


def catalogue() -> dict[str, dict[str, Any]]:
    entries = json.loads((ROOT / "portal" / "functions.json").read_text(encoding="utf-8"))
    return {entry["name"]: entry for entry in entries}


def field_text(value: Any) -> str:
    """What a visitor types into a field: JSON for lists, a plain number otherwise."""
    if isinstance(value, list):
        return json.dumps([int(v) if isinstance(v, float) and v.is_integer() else v for v in value])
    return f"{value:.12g}" if isinstance(value, float) else str(value)


def same(posted: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return (
            isinstance(posted, list)
            and len(posted) == len(expected)
            and all(same(a, b) for a, b in zip(posted, expected))
        )
    return bool(posted == expected)


async def capture(shot: Shot, site: str, out: Path, chromium: str | None) -> Path:
    from playwright.async_api import FloatRect, Route, ViewportSize, async_playwright

    entry = catalogue()[shot.function]
    proxy = os.environ.get("HTTPS_PROXY")
    posted: list[dict[str, Any]] = []

    async with gpe.gateway_client() as client:
        from api.middleware.auth import create_access_token

        api = gpe.Api(client, {"enterprise": create_access_token("site-shots", "enterprise")})

        async def answer(route: Route) -> None:
            body = json.loads(route.request.post_data or "{}")
            posted.append(body)
            path = "/" + route.request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
            g.need(path == entry["path"], f"the panel called {path}, not {entry['path']}")
            _, status, result = await api.raw(path, body, api.tokens["enterprise"])
            await route.fulfill(
                status=status, content_type="application/json", body=json.dumps(result)
            )

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                executable_path=chromium, proxy={"server": proxy} if proxy else None
            )
            viewport = ViewportSize(width=VIEWPORT_WIDTH, height=VIEWPORT_HEIGHT)
            context = await browser.new_context(viewport=viewport, device_scale_factor=2)
            await context.add_init_script(f"localStorage.setItem('pyvar_jwt', '{MASKED_KEY}')")
            page = await context.new_page()
            await page.route("**/api/v1/**", answer)

            url = f"{site.rstrip('/')}/{entry['domain_page']}#{shot.function}"
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_selector("#tryitPanel.open")
            if entry.get("formula"):
                await page.wait_for_selector("#tryitFormula .katex")
            for name, value in shot.params.items():
                await page.fill(f'[data-param="{name}"]', field_text(value))
            # a filled textarea is left scrolled to its end; show it from the first number
            await page.evaluate(
                "document.querySelectorAll('.tryit-form textarea').forEach(t => { t.scrollTop = 0; })"
            )
            await page.click(".tryit-submit")
            await page.wait_for_selector(".tryit-json")
            await page.evaluate("document.fonts.ready.then(() => document.activeElement.blur())")
            await page.mouse.move(0, 0)
            await page.wait_for_timeout(400)

            g.need(len(posted) == 1, f"expected one API call, saw {len(posted)}")
            for name, value in shot.params.items():
                g.need(same(posted[0].get(name), value), f"the panel posted a different {name}")

            box = await page.locator(".tryit-card").bounding_box()
            g.need(box is not None, "the Try it panel has no box")
            assert box is not None
            clip = FloatRect(
                x=max(box["x"] - MARGIN, 0),
                y=max(box["y"] - MARGIN, 0),
                width=box["width"] + 2 * MARGIN,
                height=box["height"] + 2 * MARGIN,
            )
            g.need(
                clip["y"] + clip["height"] <= VIEWPORT_HEIGHT,
                f"{shot.function}: the panel is taller than the viewport",
            )
            out.mkdir(parents=True, exist_ok=True)
            path = out / f"site-{shot.key}-try-it.png"
            await page.screenshot(path=path, clip=clip)
            await browser.close()
    return path


async def run(only: list[str], site: str, out: Path, chromium: str | None) -> None:
    for shot in shots():
        if only and shot.key not in only:
            continue
        path = await capture(shot, site, out, chromium)
        print("wrote", path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def main() -> None:
    names = [s.key for s in shots()]
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

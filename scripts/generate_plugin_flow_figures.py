#!/usr/bin/env python3
"""scripts/generate_plugin_flow_figures.py — figures for the plugins-end-to-end Medium article.

Reasoning:
- Same house style and drawing helpers as scripts/generate_plugin_figures.py (imported,
  not copied), so the two articles' figures look like one set.
- Every number in a figure is read from the code when the figure is drawn: the function
  count from portal/functions.json, the worked-example counts from scripts/skill_specs/,
  the key lifetime, cache TTL and failure limit from config.py, and the negative-cache
  TTL from api/middleware/api_keys.py. A figure cannot drift from the code it describes.
- Medium does not accept SVG, so the output is PNG. Diagram text is measured after
  drawing and the script fails if any label overflows its box.

Usage (repo root; matplotlib is a tooling dependency only: pip install matplotlib):
    python scripts/generate_plugin_flow_figures.py
    python scripts/generate_plugin_flow_figures.py --only header,key-check --out /tmp/figs
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import generate_plugin_figures as g  # noqa: E402  (house style + Canvas; also silences logging)

from config import Settings  # noqa: E402

DEFAULT_OUT = ROOT / "docs" / "publications" / "assets" / "plugins-end-to-end"


def default(name: str) -> int:
    """A setting's built-in default, read from config.Settings (no environment needed)."""
    value = Settings.model_fields[name].default
    g.need(isinstance(value, int), f"{name} default is not an int: {value!r}")
    return int(value)


def negative_cache_seconds() -> int:
    """_NEGATIVE_TTL_SECONDS in api/middleware/api_keys.py (a module constant, read as text)."""
    source = (ROOT / "api" / "middleware" / "api_keys.py").read_text(encoding="utf-8")
    match = re.search(r"^_NEGATIVE_TTL_SECONDS\s*=\s*(\d+)", source, re.MULTILINE)
    g.need(match is not None, "_NEGATIVE_TTL_SECONDS not found in api/middleware/api_keys.py")
    assert match is not None
    return int(match.group(1))


def catalogue_counts() -> tuple[int, int]:
    """(functions, domains) from portal/functions.json."""
    catalogue = json.loads((ROOT / "portal" / "functions.json").read_text(encoding="utf-8"))
    return len(catalogue), len({entry["domain"] for entry in catalogue})


def example_counts() -> tuple[int, int, int]:
    """(skills, worked examples, requests) from scripts/skill_specs/*.json."""
    specs = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((ROOT / "scripts" / "skill_specs").glob("*.json"))
    ]
    examples = sum(len(s["examples"]) for s in specs)
    calls = sum(len(e["calls"]) for s in specs for e in s["examples"])
    return len(specs), examples, calls


def tile(cv: Any, x: float, y: float, w: float, h: float, accent: bool) -> None:
    fill = g.CLAY_FILL if accent else g.SLATE_FILL
    cv.ax.add_patch(
        g.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=22", fc=fill, ec="none")
    )


def fig_header(out: Path) -> Path:
    functions, domains = catalogue_counts()
    skills, examples, calls = example_counts()
    key_days = default("api_key_default_expiry_days")
    cache_s = default("api_key_cache_ttl_seconds")
    max_active = default("api_key_max_active_per_user")
    g.need(skills == domains, f"{skills} domain skills but {domains} domains in the catalogue")

    cv = g.Canvas(
        1800,
        670,
        "What is in place",
        "Read from the function catalogue, the skill specs and config.py when this figure is drawn.",
    )
    w, h, gap = 820.0, 220.0, 40.0
    tiles = [
        (f"{functions}", f"functions in {domains} domains", "one catalogue, one REST API", False),
        (
            f"{examples}",
            "worked examples in the skills",
            f"{calls} requests run against the real application on every test run",
            True,
        ),
        (
            f"{key_days} days",
            "API key lifetime",
            f"up to {max_active} active keys per account, revocable at any time",
            True,
        ),
        (
            f"{cache_s} s",
            "longest wait for a tier change",
            "the tier is read from the database and cached for that long",
            False,
        ),
    ]
    for i, (big, line, small, accent) in enumerate(tiles):
        x = 60.0 + (i % 2) * (w + gap)
        y = 150.0 + (i // 2) * (h + gap)
        tile(cv, x, y, w, h, accent)
        color = g.CLAY if accent else g.SLATE
        cv.text(x + w / 2, y + 62, big, size=30, weight="bold", color=color, max_w=w - 40)
        cv.text(x + w / 2, y + 140, line, size=10.5, weight="bold", max_w=w - 40)
        cv.text(x + w / 2, y + 182, small, size=9, color=g.MUTED, max_w=w - 40)
    return cv.save(out, "plugins-end-to-end-header")


def fig_setup_flow(out: Path) -> Path:
    key_days = default("api_key_default_expiry_days")

    cv = g.Canvas(
        1800,
        830,
        "From install to a computed number",
        "The path a new user takes. The skill tells Claude each step.",
    )
    bw, bh = 500.0, 170.0
    xs = (60.0, 650.0, 1240.0)
    row1, row2 = 160.0, 450.0
    cv.box(
        xs[0],
        row1,
        bw,
        bh,
        "1. Install the plugin",
        "the skill loads when a question\nmatches its description",
        fill=g.C_DARKER,
        size=12,
        sub_size=9,
    )
    cv.box(
        xs[1],
        row1,
        bw,
        bh,
        "2. Ask a risk question",
        "the skill tells Claude to look\nfor PYVAR_API_KEY",
        fill=g.C_DARK,
        size=12,
        sub_size=9,
    )
    cv.box(
        xs[2],
        row1,
        bw,
        bh,
        "3. No key yet?",
        "pyvar.com#get-api-key:\nGoogle, or an emailed link",
        fill=g.C_API,
        size=12,
        sub_size=9,
    )
    cv.box(
        xs[2],
        row2,
        bw,
        bh,
        "4. Create a key",
        f"on the dashboard: pyvar_…\nshown once, valid {key_days} days",
        fill=g.C_ENGINE,
        size=12,
        sub_size=9,
    )
    cv.box(
        xs[1],
        row2,
        bw,
        bh,
        "5. Set PYVAR_API_KEY",
        "or paste it when the MCP\nplugin asks for it",
        fill=g.C_DARK,
        size=12,
        sub_size=9,
    )
    cv.box(
        xs[0],
        row2,
        bw,
        bh,
        "6. Claude makes the call",
        "Python client, REST or MCP;\nthe result comes back with its inputs",
        fill=g.C_ENGINE,
        size=12,
        sub_size=9,
    )
    mid1, mid2 = row1 + bh / 2, row2 + bh / 2
    cv.arrow([(xs[0] + bw, mid1), (xs[1], mid1)], color=g.C_DARK)
    cv.arrow([(xs[1] + bw, mid1), (xs[2], mid1)], color=g.C_DARK)
    cv.arrow([(xs[2] + bw / 2, row1 + bh), (xs[2] + bw / 2, row2)], color=g.C_DARK)
    cv.arrow([(xs[2], mid2), (xs[1] + bw, mid2)], color=g.C_DARK)
    cv.arrow([(xs[1], mid2), (xs[0] + bw, mid2)], color=g.C_DARK)
    cv.text(
        60,
        720,
        "A key that is revoked or has expired returns 401, and Claude sends you back to step 3.",
        size=10,
        color=g.MUTED,
        ha="left",
        max_w=1680,
    )
    cv.text(
        60,
        770,
        "If Claude has no network access, it gives you the exact curl or Python to run instead.",
        size=10,
        color=g.MUTED,
        ha="left",
        max_w=1680,
    )
    return cv.save(out, "plugins-end-to-end-setup-flow")


def fig_key_check(out: Path) -> Path:
    cache_s = default("api_key_cache_ttl_seconds")
    fail_per_min = default("api_key_failed_attempts_per_minute")
    neg_s = negative_cache_seconds()

    cv = g.Canvas(
        1800,
        1060,
        "What happens to a key on every call",
        "A key costs one Redis read on a hit; only misses reach the database. "
        "Session tokens are just decoded.",
    )
    row1, row2, row3 = 160.0, 450.0, 760.0
    bh = 150.0
    cv.box(
        60, row1, 380, bh, "Bearer pyvar_…", "the Authorization header", fill=g.C_DARKER, size=12
    )
    cv.box(
        540,
        row1,
        380,
        bh,
        "SHA-256 of the key",
        "only the hash is ever stored",
        fill=g.C_DARK,
        size=12,
    )
    cv.box(
        1020,
        row1,
        340,
        bh,
        "Redis cache",
        f"{cache_s} s · one read,\nno database connection",
        fill=g.C_API,
        size=12,
        sub_size=8.5,
    )
    cv.box(1440, row1, 300, bh, "Account + tier", "the call goes ahead", fill=g.C_ENGINE, size=12)
    cv.arrow([(440, row1 + bh / 2), (540, row1 + bh / 2)], color=g.C_DARK)
    cv.arrow([(920, row1 + bh / 2), (1020, row1 + bh / 2)], color=g.C_DARK)
    cv.arrow([(1360, row1 + bh / 2), (1440, row1 + bh / 2)], color=g.C_DARK)
    cv.label(1400, row1 + bh / 2 - 34, "hit", max_w=80)

    cv.box(
        1020,
        row2,
        340,
        bh,
        "Database lookup",
        "by hash: not revoked,\nnot expired",
        fill=g.C_API,
        size=12,
        sub_size=8.5,
    )
    cv.arrow([(1190, row1 + bh), (1190, row2)], color=g.C_DARK)
    cv.label(1190, row1 + bh + 70, "miss", max_w=100)
    cv.arrow([(1360, row2 + bh / 2), (1590, row2 + bh / 2), (1590, row1 + bh)], color=g.C_DARK)
    cv.label(1590, row2 + bh / 2 - 40, f"found: cached {cache_s} s", max_w=270)

    cv.box(
        540,
        row3,
        380,
        bh,
        "401",
        f"unknown, revoked or expired\ncached {neg_s} s",
        fill=g.S_CRIT,
        size=12,
        sub_size=8.5,
    )
    cv.box(
        1020,
        row3,
        340,
        bh,
        "503",
        "database unreachable:\nretry, never a false 401",
        fill=g.C_ASYNC,
        size=12,
        sub_size=8.5,
    )
    cv.box(
        60,
        row3,
        380,
        bh,
        "429",
        f"over {fail_per_min} bad keys a minute\nfrom one address",
        fill=g.C_DARKER,
        size=12,
        sub_size=8.5,
    )
    cv.arrow([(1020, row2 + bh / 2), (730, row2 + bh / 2), (730, row3)], color=g.S_CRIT)
    cv.label(870, row2 + bh / 2 - 36, "not found", max_w=140)
    cv.arrow([(1190, row2 + bh), (1190, row3)], color=g.C_ASYNC)
    cv.label(1190, row2 + bh + 70, "error", max_w=100)
    cv.arrow([(540, row3 + bh / 2), (440, row3 + bh / 2)], color=g.C_DARKER)

    cv.text(
        60,
        990,
        "A Redis outage only slows calls down: every lookup falls through to the database.",
        size=10,
        color=g.MUTED,
        ha="left",
        max_w=1680,
    )
    return cv.save(out, "plugins-end-to-end-key-check")


FIGURES = {
    "header": fig_header,
    "setup-flow": fig_setup_flow,
    "key-check": fig_key_check,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--only", default="", help="comma-separated: " + ", ".join(FIGURES))
    args = parser.parse_args()
    only = [n for n in args.only.split(",") if n] or list(FIGURES)
    unknown = [n for n in only if n not in FIGURES]
    if unknown:
        raise SystemExit(f"unknown figure(s): {', '.join(unknown)}")
    for name in only:
        print("wrote", FIGURES[name](Path(args.out)))


if __name__ == "__main__":
    main()

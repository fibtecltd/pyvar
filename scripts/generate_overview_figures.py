#!/usr/bin/env python3
"""scripts/generate_overview_figures.py — the three figures of the pyvar overview Medium article.

Reasoning:
- The at-a-glance infographic states counts and plan limits, so every number is read from the
  repository when the image is drawn: the function catalogue, the plugin manifest, the compose
  file, config.py, the token model's per-tier simulation caps and the rate limiter's list of
  tiers exempt from the daily quota. The logo is the brand mark drawn by
  generate_plugin_figures.logo_mark (docs/brand/favicon.svg geometry).
- The domain map states function counts, so the counts are read from portal/functions.json when
  the image is drawn and the script fails if a domain is missing. The one-line question under each
  count is editorial and lives in DOMAIN_QUESTIONS.
- The role grid is an editorial guide, not a measurement: where each role usually starts and where
  it also looks. It says so in its subtitle, and it is built from ROLES below, so changing a mapping
  is one line.
- Same house look as scripts/generate_plugin_figures.py (slate and clay on white). Medium does not
  accept SVG, so the output is PNG. matplotlib is a tooling dependency of this script only:
      pip install matplotlib

Usage (repo root):
    python scripts/generate_overview_figures.py
    python scripts/generate_overview_figures.py --out /tmp/figs
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import generate_plugin_figures as g  # noqa: E402  (palette, rcParams, save)
import generate_plugin_flow_figures as ff  # noqa: E402  (tiles grid, catalogue reader)
from generate_article_headers import (  # noqa: E402  (plugin manifest, compose file, tier caps)
    compose_services,
    plugin_counts,
    simulation_caps,
)

plt = g.plt

DEFAULT_OUT = ROOT / "docs" / "publications" / "assets" / "overview"

# domain key in portal/functions.json -> (label, the question a reader brings)
DOMAIN_QUESTIONS = {
    "market-risk": ("Market risk", "How much can we lose in a day, and is the model sound?"),
    "derivatives": (
        "Derivatives and pricing",
        "What is it worth, and how does it move with rates?",
    ),
    "credit-risk": ("Credit risk", "What will defaults cost, and what capital covers it?"),
    "portfolio": ("Portfolio analytics", "How should we weight it, and what drove the return?"),
    "operational": ("Operational risk", "What does Basel SMA say, and which indicators are red?"),
    "liquidity": ("Liquidity risk", "Do we meet LCR and NSFR, and how long does cash last?"),
    "alm": ("ALM and balance sheet", "What does a rate shock do to equity value and income?"),
    "regulatory": (
        "Regulatory and compliance",
        "Do we clear the ratios and buffers, and are reports valid?",
    ),
}

# role -> (starts here, also looks here), by domain key. Editorial.
ROLES = {
    "Quant developer": (["market-risk", "derivatives", "portfolio"], ["credit-risk", "alm"]),
    "Market-risk manager": (["market-risk"], ["derivatives", "portfolio", "regulatory"]),
    "Credit-risk analyst": (["credit-risk"], ["market-risk", "regulatory"]),
    "Treasurer / ALM": (["liquidity", "alm"], ["regulatory", "market-risk"]),
    "Operational-risk lead": (["operational"], ["regulatory"]),
    "Compliance and reporting": (["regulatory"], ["liquidity", "credit-risk", "operational"]),
    "Portfolio manager": (["portfolio"], ["market-risk", "derivatives"]),
    "Valuation desk": (["derivatives"], ["market-risk", "credit-risk"]),
}


def counts() -> dict[str, int]:
    catalogue = json.loads((ROOT / "portal" / "functions.json").read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    for entry in catalogue:
        out[entry["domain"]] = out.get(entry["domain"], 0) + 1
    g.need(set(out) == set(DOMAIN_QUESTIONS), f"domains differ: {sorted(out)}")
    return out


def fig_at_a_glance(out: Path) -> Path:
    from api.middleware.rate_limit import _EXEMPT_TIERS

    functions, domains = ff.catalogue_counts()
    plugins, domain_skills, arch_skills, mcp = plugin_counts()
    services = compose_services()
    free_day = ff.default("rate_limit_free_daily")
    pro_day = ff.default("rate_limit_pro_daily")
    pro_month = ff.default("rate_limit_pro_monthly_requests")
    pro_month_sims = ff.default("rate_limit_pro_monthly_simulations")
    free_sims, pro_sims, ent_sims = simulation_caps()
    g.need("enterprise" in _EXEMPT_TIERS, "Enterprise is no longer exempt from the daily quota")

    width, height = 1800, 1040
    cv = g.Canvas(width, height, "", "")
    g.logo_mark(cv.ax, 60, 38, 0.62, lw=5.0)
    cv.text(158, 66, "pyvar at a glance", size=17, weight="bold", ha="left", max_w=900)
    cv.text(
        60,
        120,
        "Counts read from the function catalogue, the plugin manifest and the compose file; "
        "plan limits read from config.py.",
        size=10.5,
        color=g.MUTED,
        ha="left",
        max_w=width - 120,
    )

    gap = 40.0
    col_w = (width - 120 - 2 * gap) / 3
    xs = [60.0 + i * (col_w + gap) for i in range(3)]

    # row 1: what is in the box
    facts = [
        (
            f"{functions}",
            f"risk functions in {domains} domains",
            "market, credit, liquidity,\nALM, operational and more",
        ),
        (
            f"{plugins}",
            "plugins to ask in plain language",
            f"{domain_skills} domain skills, {arch_skills} architecture skills,\n{mcp} MCP server",
        ),
        (
            f"{len(services)} services",
            "in one docker compose up",
            ", ".join(services[:3]) + ",\n" + ", ".join(services[3:]),
        ),
    ]
    top, tile_h = 160.0, 230.0
    for i, (big, line, small) in enumerate(facts):
        accent = i == 1
        ff.tile(cv, xs[i], top, col_w, tile_h, accent)
        color = g.CLAY if accent else g.SLATE
        cv.text(
            xs[i] + col_w / 2, top + 55, big, size=28, weight="bold", color=color, max_w=col_w - 40
        )
        cv.text(xs[i] + col_w / 2, top + 118, line, size=10, weight="bold", max_w=col_w - 40)
        cv.text(xs[i] + col_w / 2, top + 175, small, size=8.8, color=g.MUTED, max_w=col_w - 40)

    # row 2: what each plan allows
    label_y = top + tile_h + 70
    cv.text(60, label_y, "What each plan allows", size=14, weight="bold", ha="left", max_w=900)
    cv.text(
        60,
        label_y + 40,
        "Calls are counted per account, across every /api/v1 compute endpoint.",
        size=10,
        color=g.MUTED,
        ha="left",
        max_w=width - 120,
    )
    plans = [
        (
            "Free",
            f"{free_day}",
            "calls a day",
            f"{free_sims:,} simulations per request\nEmail or Google sign-in, no card",
            False,
        ),
        (
            "Pro",
            f"{pro_day}",
            "calls a day",
            f"{pro_month:,} calls a month\n{pro_month_sims:,} simulations a month\n"
            f"{pro_sims:,} simulations per request",
            True,
        ),
        (
            "Enterprise",
            "No cap",
            "on calls a day",
            f"{ent_sims:,} simulations per request\nArranged with the team, by email",
            False,
        ),
    ]
    card_top, card_h = label_y + 85, 350.0
    for (name, big, unit, small, accent), x in zip(plans, xs):
        ff.tile(cv, x, card_top, col_w, card_h, accent)
        color = g.CLAY if accent else g.SLATE
        cv.text(
            x + 36,
            card_top + 44,
            name.upper(),
            size=10.5,
            weight="bold",
            color=color,
            ha="left",
            max_w=col_w - 72,
        )
        cv.ax.plot([x + 36, x + col_w - 36], [card_top + 78] * 2, color="white", lw=2.2)
        cv.text(
            x + col_w / 2,
            card_top + 138,
            big,
            size=28,
            weight="bold",
            color=color,
            max_w=col_w - 40,
        )
        cv.text(x + col_w / 2, card_top + 196, unit, size=10, weight="bold", max_w=col_w - 40)
        cv.text(x + col_w / 2, card_top + 282, small, size=8.8, color=g.MUTED, max_w=col_w - 40)

    foot = card_top + card_h + 46
    cv.text(
        60,
        foot,
        "A Pro account that reaches a monthly cap moves to Free until its next billing date.",
        size=9,
        color=g.MUTED,
        ha="left",
        max_w=width - 120,
    )
    cv.text(
        60,
        foot + 36,
        "Monthly figures are current settings and may change. "
        "Pro and Enterprise: write to info@pyvar.com.",
        size=9,
        color=g.MUTED,
        ha="left",
        max_w=width - 120,
    )
    return cv.save(out, "at-a-glance")


def fig_domain_map(out: Path) -> Path:
    per_domain = counts()
    total = sum(per_domain.values())
    tiles = []
    for i, (key, (label, question)) in enumerate(
        sorted(DOMAIN_QUESTIONS.items(), key=lambda kv: -per_domain[kv[0]])
    ):
        tiles.append((str(per_domain[key]), label, question, (i // 2 + i % 2) % 2 == 0))
    return ff.tiles_figure(
        f"{total} functions, eight desks",
        "One question per domain; function counts read from portal/functions.json.",
        tiles,
        out,
        "domain-map",
    )


def fig_role_grid(out: Path) -> Path:
    per_domain = counts()
    keys = [k for k, _ in sorted(DOMAIN_QUESTIONS.items(), key=lambda kv: -per_domain[kv[0]])]
    roles = list(ROLES)
    fig, ax = plt.subplots(figsize=(9.0, 5.0))
    for r, role in enumerate(roles):
        starts, also = ROLES[role]
        g.need(set(starts + also) <= set(keys), f"unknown domain in {role}")
        for c, key in enumerate(keys):
            if key in starts:
                ax.scatter(c, r, s=260, color=g.CLAY, edgecolor="white", linewidth=1.5, zorder=3)
            elif key in also:
                ax.scatter(
                    c, r, s=200, facecolor="white", edgecolor=g.SLATE, linewidth=2.0, zorder=3
                )
    ax.set_xlim(-0.6, len(keys) - 0.4)
    ax.set_ylim(len(roles) - 0.4, -0.6)
    ax.set_xticks(range(len(keys)))
    labels = []
    for key in keys:
        name = textwrap.fill(DOMAIN_QUESTIONS[key][0], width=12)
        labels.append(name + "\n" + str(per_domain[key]))
    ax.set_xticklabels(labels, fontsize=8.5, color=g.INK)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(roles)))
    ax.set_yticklabels(roles, fontsize=10, color=g.INK)
    ax.tick_params(length=0)
    ax.grid(True, color=g.GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.scatter([], [], s=140, color=g.CLAY, label="usually starts here")
    ax.scatter(
        [], [], s=110, facecolor="white", edgecolor=g.SLATE, linewidth=2, label="also looks here"
    )
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=2, frameon=False, fontsize=9.5)
    fig.suptitle(
        "Where each role usually starts",
        x=0.02,
        y=0.985,
        ha="left",
        fontsize=12,
        fontweight="bold",
        color=g.INK,
    )
    fig.text(
        0.02,
        0.905,
        "An editorial guide, not a measurement. Numbers under the domains are function counts.",
        fontsize=9,
        color=g.MUTED,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    return g.save(fig, out, "role-grid")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    print("wrote", fig_at_a_glance(Path(args.out)))
    print("wrote", fig_domain_map(Path(args.out)))
    print("wrote", fig_role_grid(Path(args.out)))


if __name__ == "__main__":
    main()

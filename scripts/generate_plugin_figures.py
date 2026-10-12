#!/usr/bin/env python3
"""scripts/generate_plugin_figures.py — figures for the plugin-examples Medium article.

Reasoning:
- Every plotted number comes from the same real runs as docs/plugin-examples.md
  (the real FastAPI app in-process, the real engine), with the same synthetic
  inputs and seeds, and each chart cross-checks its data against the API result
  it illustrates -- a figure cannot drift from the article's numbers silently.
- Medium does not accept SVG, so the output is PNG. Diagram text is measured
  after drawing and the script fails if any label overflows its box.
- matplotlib is a tooling dependency of this script only (not in requirements*.txt):
      pip install matplotlib

Usage (repo root, app dependencies installed):
    python scripts/generate_plugin_figures.py                    # all figures
    python scripts/generate_plugin_figures.py --only header,gateway-path
    python scripts/generate_plugin_figures.py --out /tmp/figs
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import generate_plugin_examples as gpe  # noqa: E402  (sets AWS env defaults, silences logging)

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, PathPatch, Polygon, Rectangle
    from matplotlib.path import Path as MPath
except ImportError as exc:  # pragma: no cover - tooling guard
    raise SystemExit("matplotlib is required: pip install matplotlib") from exc

import numpy as np  # noqa: E402
from scipy.stats import norm  # noqa: E402

DEFAULT_OUT = ROOT / "docs" / "publications" / "assets" / "plugin-examples"

# ── Style: the pyvar.com live palette + the house look of the earlier articles ─
INK = "#1f1e1d"
MUTED = "#5f6b73"
GRID = "#e4e8ea"
SLATE = "#4c6b7a"
SLATE_MID = "#9db3bf"
SLATE_FILL = "#e8eef1"
CLAY = "#a84a2e"
CLAY_FILL = "#f3dcd4"
# Diagram component colours (same roles as docs/publications/assets/request_flow.png)
C_MCP = "#7c3aed"
# Teal chosen for white-text contrast (4.9:1); the dataviz validator flags its chroma only
# marginally and every box is also labelled in words, so colour is never the sole channel.
C_ENGINE = "#0b7f72"
C_API = "#2563eb"
C_ASYNC = "#b45309"
C_DARK = "#334155"
C_DARKER = "#1e293b"
# Status colours (dataviz palette): Basel traffic light, always labelled in words too
S_GOOD = "#0ca30c"
S_WARN = "#fab219"
S_CRIT = "#d03b3b"
# Header palette (derived from the reference header art)
H_BG = "#f6f5f1"
H_NAVY = "#1c3d5a"
H_ORANGE = "#d9623a"
H_SLATE = "#5d7f99"

DPI = 200
DIAGRAM_FONT_SCALE = 1.14  # diagrams are viewed smaller than charts; keep their text readable

plt.rcParams.update(
    {
        "font.family": ["Liberation Sans", "DejaVu Sans"],
        "mathtext.fontset": "dejavusans",
        "axes.edgecolor": GRID,
        "axes.labelcolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "text.color": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


class FigureError(RuntimeError):
    """A figure failed one of its own consistency or layout checks."""


def need(cond: bool, msg: str) -> None:
    if not cond:
        raise FigureError(msg)


def close(a: float, b: float, tol: float, what: str) -> None:
    need(abs(a - b) <= tol, f"{what}: {a} != {b} (tol {tol})")


# ── Shared chart frame ───────────────────────────────────────────────────────


def chart_frame(
    title: str,
    subtitle: str,
    footer: str,
    size: tuple[float, float] = (8.0, 4.6),
    rect: tuple[float, float, float, float] = (0.085, 0.17, 0.89, 0.60),
) -> tuple[Any, Any]:
    fig = plt.figure(figsize=size, dpi=DPI, facecolor="white")
    t = fig.text(0.03, 0.965, title, fontsize=17, fontweight="bold", color=INK, va="top")
    s = fig.text(0.03, 0.885, subtitle, fontsize=10.5, color=MUTED, va="top")
    f = fig.text(0.03, 0.022, footer, fontsize=8.2, color=MUTED, va="bottom")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for txt in (t, s, f):
        need(
            txt.get_window_extent(renderer).width <= size[0] * DPI * 0.95,
            f"header/footer text too wide: {txt.get_text()[:60]}",
        )
    ax = fig.add_axes(rect)
    style_axes(ax)
    return fig, ax


def style_axes(ax: Any, grid_axis: str = "y") -> None:
    ax.set_facecolor("white")
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
        ax.spines[side].set_linewidth(1.0)
    ax.tick_params(length=0, labelsize=10, pad=6)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig: Any, out: Path, name: str) -> Path:
    path = out / f"{name}.png"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, facecolor="white")
    plt.close(fig)
    return path


def label_box(**kw: Any) -> dict[str, Any]:
    return {"boxstyle": "round,pad=0.25", "fc": "white", "ec": "none", **kw}


# ── Data helpers (same inputs and seeds as docs/plugin-examples.md) ──────────


def gbm(n: int, mu: float, sigma: float, seed: int) -> np.ndarray:
    return gpe.generate_gbm_returns(n, mu=mu, sigma=sigma, seed=seed)


class Runner:
    """The real app, in-process, with one shared client."""

    def __init__(self, api: Any) -> None:
        self.api = api

    async def call(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        _, body = await self.api.call(name, params)
        return body


# ── Charts ───────────────────────────────────────────────────────────────────


async def fig_var_es_tail(run: Runner, out: Path) -> Path:
    returns = gbm(500, 0.0004, 0.011, 7)
    params = {"returns": returns.tolist(), "portfolio_value": 10_000_000}
    var99 = await run.call("historical_simulation_var", {**params, "confidence_level": 0.99})
    es975 = await run.call("historical_expected_shortfall", {**params, "confidence_level": 0.975})

    pct = returns * 100
    v99, v975, es = var99["var_pct"] * 100, es975["var_pct"] * 100, es975["es_pct"] * 100
    in_tail = pct <= -v975
    need(int(in_tail.sum()) == es975["n_tail"], "tail count differs from the API's n_tail")
    close(-pct[in_tail].mean(), es, 5e-3, "mean of the tail vs API expected shortfall")

    width = 0.2
    edges = -v975 + width * np.arange(-9, 41)
    counts, _ = np.histogram(pct, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2
    tail_bar = edges[1:] <= -v975 + 1e-9

    fig, ax = chart_frame(
        "Value-at-Risk and Expected Shortfall on 500 days",
        "Daily returns of a 10m portfolio. The shaded days are the 13 worst of 500; their average loss is the ES.",
        "generate_gbm_returns(500, mu=0.0004, sigma=0.011, seed=7)  ·  historical_simulation_var, "
        "historical_expected_shortfall",
    )
    ax.bar(centers[~tail_bar], counts[~tail_bar], width=width, color=SLATE_MID, ec="white", lw=0.8)
    ax.bar(centers[tail_bar], counts[tail_bar], width=width, color=CLAY, ec="white", lw=0.8)
    top = counts.max() * 1.38
    ax.set_ylim(0, top)
    ax.set_xlim(-4.0, 4.0)
    ax.set_xlabel("daily return (%)", fontsize=10.5, labelpad=8)
    ax.set_ylabel("number of days", fontsize=10.5, labelpad=8)

    VAR_LINE = "#2f4a58"
    h_es, h_var = top * 0.70, top * 0.56
    ax.vlines(-es, 0, h_es, color=INK, lw=1.8, zorder=5)
    ax.vlines(-v99, 0, h_var, color=VAR_LINE, lw=1.8, zorder=5)
    ax.annotate(
        f"97.5% Expected Shortfall: {es:.2f}%  ·  {es975['es_abs']:,.0f}",
        (-es, h_es),
        (-2.0, top * 0.93),
        ha="left",
        va="center",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
        arrowprops={"arrowstyle": "-", "color": INK, "lw": 1.2, "relpos": (0, 0.5), "shrinkA": 6},
    )
    ax.annotate(
        f"99% VaR: {v99:.2f}%  ·  {var99['var_abs']:,.0f}",
        (-v99, h_var),
        (-2.0, top * 0.81),
        ha="left",
        va="center",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
        arrowprops={
            "arrowstyle": "-",
            "color": VAR_LINE,
            "lw": 1.2,
            "relpos": (0, 0.5),
            "shrinkA": 6,
        },
    )
    ax.text(
        -3.92,
        counts[tail_bar].max() * 1.0 + 5,
        f"{es975['n_tail']} worst days\n(beyond −{v975:.2f}%)",
        ha="left",
        va="bottom",
        fontsize=10,
        color=MUTED,
    )
    return save(fig, out, "plugin-examples-var-es-tail")


async def fig_backtest(run: Runner, out: Path) -> Path:
    calm = gbm(250, 0.0003, 0.008, 11)
    test = gbm(250, 0.0003, 0.008, 12)
    var = await run.call(
        "historical_simulation_var",
        {"returns": calm.tolist(), "portfolio_value": 1_000_000, "confidence_level": 0.99},
    )
    tl = await run.call(
        "traffic_light_backtesting",
        {"actual_returns": test.tolist(), "var_estimates": [var["var_pct"]] * 250},
    )
    mult = await run.call("basel_capital_addon_multiplier", {"n_breaches": tl["n_breaches"]})

    pct = test * 100
    v = var["var_pct"] * 100
    breach = pct < -v
    need(int(breach.sum()) == tl["n_breaches"], "breach count differs from the API")

    fig, ax = chart_frame(
        "Backtest: seven breaches of a 99% VaR in 250 days",
        "Daily returns over the year after the VaR was estimated; clay marks the days the loss exceeded it.",
        "generate_gbm_returns(250, mu=0.0003, sigma=0.008, seed=12)  ·  traffic_light_backtesting, "
        "basel_capital_addon_multiplier",
        size=(8.0, 5.4),
        rect=(0.085, 0.38, 0.80, 0.40),
    )
    days = np.arange(1, 251)
    ax.bar(days[~breach], pct[~breach], width=0.78, color=SLATE_MID, ec="none")
    ax.bar(days[breach], pct[breach], width=0.78, color=CLAY, ec="none")
    ax.scatter(
        days[breach], pct[breach], s=46, color=CLAY, edgecolor="white", linewidth=1.4, zorder=4
    )
    ax.axhline(-v, color=INK, lw=1.6, zorder=3)
    ax.text(
        254,
        -v,
        f"99% VaR\n−{v:.2f}%",
        ha="left",
        va="center",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
        clip_on=False,
    )
    ax.axhline(0, color=GRID, lw=1.0)
    ax.set_xlim(0, 252)
    ax.set_ylim(-2.5, 2.5)
    ax.set_xlabel("trading day", fontsize=10.5, labelpad=6)
    ax.set_ylabel("daily return (%)", fontsize=10.5, labelpad=8)

    strip = fig.add_axes([0.085, 0.145, 0.89, 0.075])
    strip.set_xlim(-0.5, 12.5)
    strip.set_ylim(-0.14, 1.14)
    strip.axis("off")
    for k in range(13):
        colour = S_GOOD if k < 5 else (S_WARN if k < 10 else S_CRIT)
        strip.add_patch(Rectangle((k - 0.46, 0.0), 0.92, 1.0, fc=colour, ec="none"))
        label = "12+" if k == 12 else str(k)
        strip.text(
            k,
            0.5,
            label,
            ha="center",
            va="center",
            fontsize=9.5,
            fontweight="bold",
            color="white" if colour != S_WARN else INK,
        )
    k = tl["n_breaches"]
    strip.add_patch(
        Rectangle((k - 0.5, -0.1), 1.0, 1.2, fc="none", ec=INK, lw=2.4, zorder=5, clip_on=False)
    )
    fig.text(
        0.085,
        0.265,
        "Basel zone by number of breaches in 250 days",
        fontsize=10,
        color=MUTED,
        va="center",
    )
    fig.text(
        0.975,
        0.265,
        f"{k} breaches → {tl['basel_zone']} zone → capital multiplier {mult['multiplier']}",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
        va="center",
        ha="right",
    )
    for word, x0, x1 in (("green: 0–4", 0, 4), ("yellow: 5–9", 5, 9), ("red: 10 or more", 10, 12)):
        xm = 0.085 + 0.89 * ((x0 + x1) / 2 + 0.5) / 13
        fig.text(xm, 0.105, word, fontsize=9.5, color=MUTED, ha="center", va="center")
    return save(fig, out, "plugin-examples-backtest-breaches")


async def fig_vasicek(run: Runner, out: Path) -> Path:
    pd_, lgd, ead, rho, cl = 0.02, 0.45, 50_000_000, 0.15, 0.999
    el = await run.call("expected_loss_el_computation", {"pd": pd_, "lgd": lgd, "ead": ead})
    vas = await run.call(
        "credit_var_analytical_vasicek",
        {"pd": pd_, "lgd": lgd, "ead_total": ead, "asset_correlation": rho, "confidence_level": cl},
    )
    x = np.linspace(1e-5, 0.30, 6000)
    z = norm.ppf(x)
    dens = np.sqrt((1 - rho) / rho) * np.exp(
        -0.5 * ((np.sqrt(1 - rho) * z - norm.ppf(pd_)) ** 2) / rho + 0.5 * z**2
    )
    loss = ead * lgd * x / 1e6
    pdf = dens / (ead * lgd / 1e6)
    close(np.trapezoid(dens, x), 1.0, 5e-3, "Vasicek density integrates to 1")
    close(np.trapezoid(x * dens, x), pd_, 1e-3, "Vasicek mean default rate equals PD")
    q = norm.cdf((norm.ppf(pd_) + math.sqrt(rho) * norm.ppf(cl)) / math.sqrt(1 - rho))
    close(ead * lgd * q, vas["var"], 1.0, "99.9% quantile vs API credit VaR")

    el_m, var_m = el["el"] / 1e6, vas["var"] / 1e6
    fig, ax = chart_frame(
        "Credit loss on a 50m exposure: what capital is for",
        "Vasicek loss distribution, PD 2%, LGD 45%, asset correlation 0.15.",
        "expected_loss_el_computation, credit_var_analytical_vasicek  ·  density from the same "
        "closed-form model",
    )
    ax.plot(loss, pdf, color=SLATE, lw=2.2)
    body = loss <= var_m
    ax.fill_between(loss[body], 0, pdf[body], color=SLATE_FILL)
    ax.fill_between(loss[~body], 0, pdf[~body], color=CLAY, alpha=0.9)
    ymax = pdf.max() * 1.30
    ax.set_ylim(0, ymax)
    ax.set_xlim(0, 6.0)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("loss (millions)", fontsize=10.5, labelpad=8)
    ax.set_ylabel("relative likelihood", fontsize=10.5, labelpad=8)
    ax.grid(False)
    ax.vlines(el_m, 0, ymax * 0.80, color=SLATE, lw=2.0)
    ax.vlines(var_m, 0, ymax * 0.40, color=CLAY, lw=2.0)
    ax.text(
        el_m + 0.08,
        ymax * 0.86,
        f"Expected loss\n{el['el']:,.0f}",
        ha="left",
        va="center",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
    )
    ax.text(
        var_m - 0.08,
        ymax * 0.48,
        f"99.9% credit VaR\n{vas['var']:,.0f}",
        ha="right",
        va="center",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
    )
    yarrow = ymax * 0.22
    ax.annotate(
        "",
        (var_m, yarrow),
        (el_m, yarrow),
        arrowprops={"arrowstyle": "<->", "color": INK, "lw": 1.4, "shrinkA": 0, "shrinkB": 0},
    )
    ax.text(
        (el_m + var_m) / 2,
        yarrow + ymax * 0.03,
        f"unexpected loss {vas['ul']:,.0f}  ·  economic capital",
        ha="center",
        va="bottom",
        fontsize=10.5,
        color=INK,
        bbox=label_box(),
    )
    ax.text(
        var_m + 0.15,
        ymax * 0.16,
        "the worst 0.1% of\noutcomes lie beyond",
        ha="left",
        va="center",
        fontsize=9.8,
        color=MUTED,
    )
    return save(fig, out, "plugin-examples-vasicek-loss")


async def fig_survival(run: Runner, out: Path) -> Path:
    outflows = [8, 9, 11, 12, 12, 10, 9, 8, 8, 7, 7, 6]
    surv = await run.call(
        "survival_horizon_calculator",
        {"hqla": 100e6, "daily_net_outflows": [o * 1e6 for o in outflows]},
    )
    cum = np.cumsum(outflows)
    need(surv["survival_days"] == 10, "survival days differ from the article")
    need(cum[9] == 94 and cum[10] == 101 and cum[11] == 107, "cumulative path differs")
    close(surv["terminal_buffer"], -1_000_000.0, 1.0, "buffer on the exhaustion day")

    fig, ax = chart_frame(
        "How long does a 100m liquidity buffer last?",
        "Cumulative net outflow along a 12-day stress path, against the HQLA held.",
        "survival_horizon_calculator(hqla=100m, daily_net_outflows=[8, 9, 11, 12, 12, 10, 9, 8, 8, 7, 7, 6]m)",
    )
    days = np.arange(1, 13)
    over = cum > 100
    ax.bar(days[~over], cum[~over], width=0.62, color=SLATE_MID, ec="none")
    ax.bar(days[over], cum[over], width=0.62, color=CLAY, ec="none")
    ax.axhline(100, color=INK, lw=1.8)
    ax.text(
        0.55,
        100 + 2.2,
        "HQLA  100m",
        ha="left",
        va="bottom",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
    )
    # day 10 sits just under the HQLA line, so its value goes inside the bar; days 11-12 above
    ax.text(
        10,
        cum[9] - 2.5,
        f"{cum[9]}m",
        ha="center",
        va="top",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
    )
    for d in (11, 12):
        ax.text(
            d,
            cum[d - 1] + 2.0,
            f"{cum[d - 1]}m",
            ha="center",
            va="bottom",
            fontsize=10.5,
            color=INK,
            fontweight="bold",
        )
    ax.set_xlim(0.4, 12.6)
    ax.set_ylim(0, 142)
    ax.set_xticks(days)
    ax.set_yticks([0, 20, 40, 60, 80, 100, 120])
    ax.set_xlabel("day of the stress path", fontsize=10.5, labelpad=8)
    ax.set_ylabel("cumulative outflow (millions)", fontsize=10.5, labelpad=8)
    ax.annotate(
        "",
        (10.5, 114),
        (0.6, 114),
        arrowprops={"arrowstyle": "<->", "color": SLATE, "lw": 1.6, "shrinkA": 0, "shrinkB": 0},
    )
    ax.text(
        5.55,
        117,
        f"{surv['survival_days']} full days survived",
        ha="center",
        va="bottom",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
        bbox=label_box(),
    )
    ax.text(
        12.55,
        125,
        "buffer exhausted during day 11\nending at −1.0m",
        ha="right",
        va="bottom",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
    )
    return save(fig, out, "plugin-examples-liquidity-survival")


async def fig_bond(run: Runner, out: Path) -> Path:
    bond = dict(face_value=100, coupon_rate=0.045, maturity=10, frequency=2)
    cfs = [2.25] * 19 + [102.25]
    ts = [0.5 * (i + 1) for i in range(20)]
    base = await run.call("bond_pricer_fixed_coupon", {**bond, "yield_rate": 0.05})
    shock = await run.call("bond_pricer_fixed_coupon", {**bond, "yield_rate": 0.055})
    dur = await run.call(
        "modified_duration", dict(cashflows=cfs, times=ts, yield_rate=0.05, frequency=2)
    )
    cvx = await run.call("convexity", dict(cashflows=cfs, times=ts, yield_rate=0.05, frequency=2))
    ys = np.round(np.arange(0.01, 0.1201, 0.005), 4)
    prices = []
    for y in ys:
        prices.append(
            (await run.call("bond_pricer_fixed_coupon", {**bond, "yield_rate": float(y)}))["price"]
        )
    p0, d, c = base["price"], dur["modified_duration"], cvx["convexity"]

    def est(y: float, second: bool) -> float:
        dy = y - 0.05
        return p0 * (1 - d * dy + (0.5 * c * dy * dy if second else 0.0))

    close(est(0.055, True), 92.3879, 5e-4, "duration + convexity estimate vs the article")
    close(shock["price"], 92.386374, 1e-4, "+50bp reprice vs the article")

    fig, (ax, ax2) = plt.subplots(
        1,
        2,
        figsize=(8.0, 4.6),
        dpi=DPI,
        facecolor="white",
        gridspec_kw={"width_ratios": [1.3, 1], "wspace": 0.62},
    )
    fig.subplots_adjust(left=0.085, right=0.975, bottom=0.17, top=0.75)
    fig.text(
        0.03,
        0.965,
        "Duration and convexity against a full reprice",
        fontsize=17,
        fontweight="bold",
        color=INK,
        va="top",
    )
    fig.text(
        0.03,
        0.885,
        "10-year 4.5% semi-annual bond, priced at a 5% yield, then shocked +50bp.",
        fontsize=10.5,
        color=MUTED,
        va="top",
    )
    fig.text(
        0.03,
        0.022,
        "bond_pricer_fixed_coupon, modified_duration, convexity",
        fontsize=8.2,
        color=MUTED,
        va="bottom",
    )
    style_axes(ax)
    grid = np.linspace(0.01, 0.12, 300)
    ax.plot(ys * 100, prices, color=SLATE, lw=2.4, label="full reprice")
    ax.plot(grid * 100, [est(y, False) for y in grid], color=CLAY, lw=1.8, label="duration only")
    ax.plot(
        grid * 100,
        [est(y, True) for y in grid],
        color=INK,
        lw=1.4,
        label="duration + convexity",
        dashes=(4, 3),
    )
    ax.scatter([5.0], [p0], s=60, color=INK, edgecolor="white", linewidth=1.5, zorder=5)
    ax.text(5.4, p0 + 4.5, f"5.0%  ·  {p0:.2f}", fontsize=10, color=INK, ha="left")
    ax.set_ylim(55, 140)
    ax.set_xlim(1, 12)
    ax.set_xlabel("yield (%)", fontsize=10.5, labelpad=6)
    ax.set_ylabel("price (per 100 face)", fontsize=10.5, labelpad=8)
    ax.legend(frameon=False, fontsize=9.5, loc="upper right", handlelength=2.2)
    ax.set_xticks([2, 4, 6, 8, 10, 12])

    style_axes(ax2, grid_axis="x")
    ax2.grid(False)
    rows = [
        ("full reprice", shock["price"], SLATE),
        ("duration + convexity", est(0.055, True), INK),
        ("duration only", est(0.055, False), CLAY),
    ]
    for k, (name, val, colour) in enumerate(rows):
        ax2.scatter([val], [k], s=70, color=colour, edgecolor="white", linewidth=1.5, zorder=4)
        ax2.text(
            92.425,
            k,
            f"{val:.4f}",
            va="center",
            ha="left",
            fontsize=10,
            color=INK,
            fontweight="bold",
        )
    ax2.set_yticks(range(3))
    ax2.set_yticklabels([r[0] for r in rows], fontsize=9.5)
    ax2.set_ylim(2.6, -0.6)
    ax2.set_xlim(92.24, 92.52)
    ax2.set_xticks([92.3, 92.4, 92.5])
    ax2.set_xlabel("price after +50bp", fontsize=10.5, labelpad=6)
    ax2.spines["left"].set_visible(False)
    ax2.set_title("the +50bp move, zoomed", fontsize=10, color=MUTED, loc="left", pad=8)
    ax2.axvline(shock["price"], color=GRID, lw=1.0)
    return save(fig, out, "plugin-examples-bond-price-yield")


async def fig_irrbb(run: Runner, out: Path) -> Path:
    t = [0.5, 1, 2, 3, 5, 7, 10]
    st = await run.call(
        "alm_stress_test",
        dict(
            net_cashflows=[-400e6, -250e6, -100e6, 150e6, 350e6, 300e6, 250e6],
            times=t,
            base_rates=[0.035, 0.036, 0.037, 0.038, 0.040, 0.041, 0.042],
            tier1_capital=900e6,
            parallel_bps=200,
        ),
    )
    order = ["parallel_up", "parallel_down", "steepener", "flattener", "short_up", "short_down"]
    vals = [st["scenario_results"][k] / 1e6 for k in order]
    worst = min(vals)
    close(worst, st["worst_case_eve"] / 1e6, 1e-3, "worst scenario vs API worst_case_eve")
    threshold = 0.15 * 900

    fig, ax = chart_frame(
        "IRRBB outlier test: six standard rate shocks",
        "Change in economic value of equity, against 15% of Tier 1 capital (900m).",
        "alm_stress_test(net_cashflows=…, base_rates=…, tier1_capital=900m, parallel_bps=200)",
        rect=(0.20, 0.17, 0.77, 0.60),
    )
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.grid(axis="y", visible=False)
    ypos = np.arange(len(order))[::-1]
    for y, name, v in zip(ypos, order, vals):
        colour = CLAY if v == worst else SLATE_MID
        ax.barh(y, v, height=0.52, color=colour, ec="none")
        ax.text(
            v + (4 if v >= 0 else -4),
            y,
            f"{v:+.1f}m".replace("-", "−"),
            ha="left" if v >= 0 else "right",
            va="center",
            fontsize=10.5,
            fontweight="bold",
            color=INK,
        )
    ax.axvline(0, color=MUTED, lw=1.0)
    ax.axvline(-threshold, color=INK, lw=1.8)
    ax.text(
        -threshold + 3,
        ypos[0] + 0.62,
        f"15% of Tier 1\n−{threshold:.0f}m",
        ha="left",
        va="center",
        fontsize=10,
        color=INK,
        fontweight="bold",
    )
    ax.set_yticks(ypos)
    ax.set_yticklabels(order, fontsize=10.5, color=INK)
    ax.set_xlim(-160, 130)
    ax.set_ylim(-0.6, len(order) - 0.1 + 0.55)
    ax.set_xlabel("change in EVE (millions)", fontsize=10.5, labelpad=8)
    ax.spines["left"].set_visible(False)
    ax.text(
        6,
        ypos[0],
        f"worst case: {st['eve_capital_ratio'] * 100:.1f}% of Tier 1",
        ha="left",
        va="center",
        fontsize=10.5,
        color=INK,
    )
    return save(fig, out, "plugin-examples-irrbb-shocks")


async def fig_convergence(run: Runner, out: Path) -> Path:
    from engine.montecarlo import run_monte_carlo_var

    returns = gbm(252, 0.0004, 0.012, 3)
    sizes = [1_000, 3_000, 10_000, 30_000, 100_000, 300_000, 1_000_000]
    seeds = range(1, 6)
    res = {
        n: [run_monte_carlo_var(returns, 1.0, 0.99, 1, n, seed=s)["var_pct"] * 100 for s in seeds]
        for n in sizes
    }
    spread = {n: max(v) - min(v) for n, v in res.items()}
    close(spread[1_000] / 100, 0.00231, 6e-6, "spread at 1,000 paths vs the article")
    close(spread[1_000_000] / 100, 0.00014, 6e-6, "spread at 1,000,000 paths vs the article")

    fig, ax = chart_frame(
        "More paths, tighter answer",
        "99% one-day VaR from the Monte Carlo engine, five seeds at each simulation count.",
        "run_monte_carlo_var(returns, 1.0, 0.99, 1, n, seed=1…5)  ·  generate_gbm_returns(252, "
        "mu=0.0004, sigma=0.012, seed=3)",
    )
    xs = np.array(sizes)
    lo = np.array([min(res[n]) for n in sizes])
    hi = np.array([max(res[n]) for n in sizes])
    ax.fill_between(xs, lo, hi, color=SLATE_FILL)
    for n in sizes:
        ax.scatter([n] * 5, res[n], s=30, color=SLATE, edgecolor="white", linewidth=1.2, zorder=4)
    ax.set_xscale("log")
    ax.set_xlim(700, 1_500_000)
    ax.set_xticks([1_000, 10_000, 100_000, 1_000_000])
    ax.set_xticklabels(["1,000", "10,000", "100,000", "1,000,000"])
    ax.minorticks_off()
    ax.set_xlabel("simulated paths", fontsize=10.5, labelpad=8)
    ax.set_ylabel("99% VaR (% of portfolio)", fontsize=10.5, labelpad=8)
    ax.set_ylim(2.55, 3.02)
    ax.text(
        1_100,
        hi[0] + 0.012,
        f"spread {spread[1_000]:.3f} pts  ({spread[1_000] / 100:.5f})",
        ha="left",
        va="bottom",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
    )
    ax.text(
        1_300_000,
        hi[-1] + 0.03,
        f"spread {spread[1_000_000]:.3f} pts  ({spread[1_000_000] / 100:.5f})",
        ha="right",
        va="bottom",
        fontsize=10.5,
        color=INK,
        fontweight="bold",
    )
    return save(fig, out, "plugin-examples-compute-convergence")


# ── Diagram canvas ───────────────────────────────────────────────────────────


class Canvas:
    """Pixel-coordinate drawing surface (y grows downward) with text-fit checking."""

    def __init__(self, width: int, height: int, title: str, subtitle: str = "") -> None:
        self.w, self.h = width, height
        self.fig = plt.figure(figsize=(width / DPI, height / DPI), dpi=DPI, facecolor="white")
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, width)
        self.ax.set_ylim(height, 0)
        self.ax.axis("off")
        self.fig.canvas.draw()
        self.renderer = self.fig.canvas.get_renderer()
        self.text(40, 52, title, size=17, weight="bold", ha="left", max_w=width - 80)
        if subtitle:
            self.text(40, 96, subtitle, size=10.5, color=MUTED, ha="left", max_w=width - 80)

    def text(
        self,
        x: float,
        y: float,
        s: str,
        size: float = 10.5,
        weight: str = "normal",
        color: str = INK,
        ha: str = "center",
        va: str = "center",
        max_w: float | None = None,
        **kw: Any,
    ) -> Any:
        t = self.ax.text(
            x,
            y,
            s,
            fontsize=size * DIAGRAM_FONT_SCALE,
            fontweight=weight,
            color=color,
            ha=ha,
            va=va,
            linespacing=1.25,
            **kw,
        )
        if max_w is not None:
            width = t.get_window_extent(self.renderer).width
            msg = f"text overflows ({width:.0f}px > {max_w:.0f}px): {s[:50]!r}"
            if os.environ.get("PLUGIN_FIGS_COLLECT"):  # list every overflow while tuning a layout
                if width > max_w:
                    print("  LAYOUT:", msg)
            else:
                need(width <= max_w, msg)
        return t

    def box(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        title: str,
        sub: str = "",
        fill: str = C_API,
        fg: str = "white",
        size: float = 11,
        sub_size: float = 9.0,
        ec: str | None = None,
        dashed: bool = False,
    ) -> None:
        self.ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0,rounding_size=16",
                fc=fill,
                ec=ec or "none",
                lw=2.0,
                ls="--" if dashed else "-",
            )
        )
        pad = 28
        if not sub:
            self.text(
                x + w / 2, y + h / 2, title, size=size, weight="bold", color=fg, max_w=w - pad
            )
            return
        self.text(x + w / 2, y + 30, title, size=size, weight="bold", color=fg, max_w=w - pad)
        t = self.text(x + w / 2, y + 55, sub, size=sub_size, color=fg, va="top", max_w=w - pad)
        bottom = t.get_window_extent(self.renderer).y0  # display coords: y0 is the lower edge
        # display y grows upward; convert the box bottom into display coords for the check
        box_bottom = self.ax.transData.transform((0, y + h))[1]
        msg = f"sub text runs out of its box ({title!r}): add height"
        if os.environ.get("PLUGIN_FIGS_COLLECT"):
            if bottom < box_bottom + 8:
                print("  LAYOUT:", msg)
        else:
            need(bottom >= box_bottom + 8, msg)

    def arrow(
        self,
        pts: list[tuple[float, float]],
        color: str = SLATE,
        lw: float = 2.4,
        both: bool = False,
        dashed: bool = False,
    ) -> None:
        for a, b in zip(pts[:-2], pts[1:-1]):
            self.ax.plot(
                [a[0], b[0]],
                [a[1], b[1]],
                color=color,
                lw=lw,
                solid_capstyle="butt",
                ls="--" if dashed else "-",
            )
        self.ax.annotate(
            "",
            pts[-1],
            pts[-2],
            arrowprops={
                "arrowstyle": "<|-|>" if both else "-|>",
                "color": color,
                "lw": lw,
                "shrinkA": 0,
                "shrinkB": 0,
                "mutation_scale": 20,
                "ls": "--" if dashed else "-",
            },
        )

    def label(
        self,
        x: float,
        y: float,
        s: str,
        size: float = 9.5,
        color: str = MUTED,
        ha: str = "center",
        max_w: float | None = None,
        weight: str = "normal",
    ) -> None:
        t = self.text(x, y, s, size=size, color=color, ha=ha, max_w=max_w, weight=weight)
        t.set_bbox({"boxstyle": "round,pad=0.18", "fc": "white", "ec": "none"})

    def save(self, out: Path, name: str) -> Path:
        return save(self.fig, out, name)


async def diagram_overview(run: Runner, out: Path) -> Path:
    cv = Canvas(
        1800,
        1120,
        "One catalogue, two ways in",
        "How the 14 plugins relate to the 385-function API and to the platform that serves it.",
    )
    cv.box(
        560,
        130,
        680,
        104,
        "You, in Claude Code or Claude.ai",
        "ask a risk question in plain language",
        fill=C_DARKER,
        size=12,
    )
    cv.box(
        60,
        330,
        800,
        190,
        "8 domain plugins",
        "market · credit · liquidity · operational\nportfolio · regulatory · derivatives · ALM\nteach Claude which function fits a question",
        fill=C_API,
        size=12,
    )
    cv.box(
        940,
        330,
        800,
        190,
        "pyvar-mcp",
        "387 tools: one per function (385) plus\nlist_pyvar_functions and call_pyvar_function\na local stdio MCP server over the REST API",
        fill=C_MCP,
        size=12,
    )
    cv.arrow([(900, 234), (900, 282), (460, 282), (460, 330)], color=C_DARK)
    cv.arrow([(900, 234), (900, 282), (1340, 282), (1340, 330)], color=C_DARK)
    cv.box(
        60,
        640,
        1680,
        110,
        "pyvar.com REST API  ·  POST /api/v1/{domain}/{function}",
        "385 functions in 8 domains  ·  Bearer JWT  ·  every route into pyvar ends here",
        fill=C_DARK,
        size=12.5,
    )
    cv.arrow([(460, 520), (460, 640)], color=C_API)
    cv.arrow([(1340, 520), (1340, 640)], color=C_MCP)
    cv.label(490, 580, "function calls", ha="left", max_w=300)
    cv.label(1370, 580, "tool calls over HTTPS", ha="left", max_w=380)
    cv.ax.add_patch(
        FancyBboxPatch(
            (60, 830),
            1680,
            250,
            boxstyle="round,pad=0,rounding_size=20",
            fc="#f3f5f7",
            ec=GRID,
            lw=2,
        )
    )
    cv.arrow([(900, 750), (900, 830)], color=C_DARK)
    cv.label(930, 790, "served by", ha="left", max_w=300)
    cv.text(
        100,
        868,
        "the pyvar platform, documented by the 5 architecture plugins, one per layer",
        size=10.5,
        weight="bold",
        color=C_DARK,
        ha="left",
        max_w=1500,
    )
    layers = [
        ("API gateway", "JWT · tiers · limits\narch-api-gateway", C_API),
        ("Compute", "Numba · Celery\narch-compute", C_ENGINE),
        ("Data ingestion", "Polars · PyArrow\narch-data-ingestion", C_DARK),
        ("Storage", "Redis · S3 · Aurora\narch-storage", C_ASYNC),
        ("Observability", "validation · metrics\narch-observability", C_MCP),
    ]
    for i, (name, sub, col) in enumerate(layers):
        cv.box(90 + i * 328, 905, 300, 140, name, sub, fill=col, size=11.5)
    return cv.save(out, "plugin-examples-overview")


async def diagram_gateway(run: Runner, out: Path) -> Path:
    cv = Canvas(
        1800,
        1360,
        "Six checks before a VaR job is queued",
        "POST /api/v1/var/compute, in the order the code runs them. Domain endpoints pass checks 1–3, then call the engine.",
    )
    cv.box(
        110,
        140,
        640,
        108,
        "POST /api/v1/var/compute",
        "JWT + returns, portfolio value, confidence, paths",
        fill=C_DARKER,
        size=11.5,
    )
    steps = [
        (
            "1  JWT authentication",
            "Bearer token → user and tier",
            "401  not authenticated or invalid token",
            CLAY,
        ),
        (
            "2  Daily quota",
            "one shared compute bucket per user",
            "429  rate limit exceeded · Retry-After",
            CLAY,
        ),
        (
            "3  Request validation",
            "Pydantic: ranges, history, finite numbers",
            "422  names the offending field",
            CLAY,
        ),
        (
            "4  Result cache",
            "Redis · key = SHA-256 of the request",
            "200  cached result, no queue",
            C_ENGINE,
        ),
        (
            "5  Tier simulation cap",
            "free 10,000 · pro 100,000 · enterprise 500,000",
            "403  names the cap and the request",
            CLAY,
        ),
        (
            "6  Audit row, then dispatch",
            "Aurora job record → Celery, SQS FIFO",
            "202  task_id to poll for the result",
            C_API,
        ),
    ]
    y0 = 290
    gap = 170
    for i, (title, sub, exit_text, colour) in enumerate(steps):
        y = y0 + i * gap
        cv.box(110, y, 640, 104, title, sub, fill=C_DARK, size=11.5)
        if i == 0:
            cv.arrow([(430, 248), (430, y)], color=C_DARK)
        else:
            cv.arrow([(430, y - gap + 104), (430, y)], color=C_DARK)
        cv.arrow([(750, y + 52), (950, y + 52)], color=colour)
        cv.box(950, y + 6, 740, 92, exit_text, "", fill=colour, size=11.5)
    cv.label(
        430,
        y0 + 5 * gap + 104 + 48,
        "503 if the audit row or the dispatch cannot be written",
        size=9.8,
        color=MUTED,
        max_w=900,
    )
    return cv.save(out, "plugin-examples-gateway-path")


async def diagram_async(run: Runner, out: Path) -> Path:
    cv = Canvas(
        1800,
        1380,
        "From POST to result: the asynchronous VaR path",
        "Only VaR is asynchronous; the other 384 functions answer in the same request.",
    )
    cols = {"Client": 230, "API": 700, "Worker": 1160, "Stores": 1610}
    colours = {"Client": C_DARKER, "API": C_API, "Worker": C_ENGINE, "Stores": C_ASYNC}
    subs = {
        "Client": "your code or Claude",
        "API": "FastAPI",
        "Worker": "Celery + Numba",
        "Stores": "Aurora · Redis · S3",
    }
    for name, x in cols.items():
        cv.box(x - 150, 140, 300, 116, name, subs[name], fill=colours[name], size=12)
        cv.ax.plot([x, x], [256, 1330], color=GRID, lw=2.2, zorder=0)

    def msg(y: float, a: str, b: str, text: str, dashed: bool = False, color: str = C_DARK) -> None:
        xa, xb = cols[a], cols[b]
        cv.arrow([(xa, y), (xb, y)], color=color, dashed=dashed)
        cv.label((xa + xb) / 2, y - 34, text, size=10, color=INK, max_w=abs(xb - xa) + 120)

    def note(y: float, who: str, text: str, w: float = 400) -> None:
        x = cols[who]
        cv.ax.add_patch(
            FancyBboxPatch(
                (x - w / 2, y - 38),
                w,
                76,
                boxstyle="round,pad=0,rounding_size=12",
                fc="#eef2f4",
                ec=GRID,
                lw=1.5,
            )
        )
        cv.text(x, y, text, size=9.8, color=INK, max_w=w - 24)

    msg(320, "Client", "API", "1  POST /var/compute")
    note(430, "API", "2  auth · quota · validation\ncache lookup · tier cap")
    msg(540, "API", "Stores", "3  audit row (Aurora)")
    msg(630, "API", "Worker", "4  task, via the SQS FIFO queue", color=C_ASYNC)
    msg(720, "API", "Client", "5  202 + task_id", dashed=True)
    note(830, "Worker", "6  Monte Carlo on the\nNumba kernel", 360)
    msg(940, "Worker", "Stores", "7  summary → Redis result backend")
    msg(1030, "Worker", "Stores", "8  above 10,000 paths: full result → S3")
    msg(1130, "Client", "API", "9  GET /var/result/{task_id}")
    msg(1220, "API", "Stores", "10  read result · cache it")
    msg(1310, "API", "Client", "11  result + fresh presigned S3 link", dashed=True)
    return cv.save(out, "plugin-examples-async-var-flow")


async def diagram_mcp(run: Runner, out: Path) -> Path:
    cv = Canvas(
        1800,
        1260,
        "One MCP call, three ways it can fail",
        "Every outcome reaches Claude as an ordinary tool result; failures carry is_error, so the model can correct the call.",
    )
    # entry points
    cv.box(40, 150, 420, 104, "list_pyvar_functions", "discover by domain", fill=C_MCP, size=11.5)
    cv.box(
        40,
        300,
        420,
        104,
        "call_pyvar_function",
        "domain, function, params",
        fill=C_MCP,
        size=11.5,
    )
    cv.box(
        40,
        450,
        420,
        104,
        "385 named tools",
        "one per catalogued function",
        sub_size=8.6,
        fill=C_MCP,
        size=11.5,
    )
    for y in (202, 352, 502):
        cv.ax.plot([460, 505], [y, y], color=C_MCP, lw=2.4, solid_capstyle="butt")
    cv.ax.plot([505, 505], [202, 502], color=C_MCP, lw=2.4, solid_capstyle="butt")
    cv.arrow([(505, 310), (570, 310)], color=C_MCP)
    # the local server
    cv.ax.add_patch(
        FancyBboxPatch(
            (540, 150),
            420,
            790,
            boxstyle="round,pad=0,rounding_size=20",
            fc="#f5f0ff",
            ec=C_MCP,
            lw=2,
        )
    )
    cv.text(750, 188, "pyvar-mcp (local, stdio)", size=10.5, weight="bold", color=C_MCP, max_w=380)
    cv.box(
        570,
        240,
        360,
        140,
        "Catalogue lookup",
        "tool or function name\n→ endpoint + schema",
        fill=C_MCP,
        size=11,
    )
    cv.box(
        570,
        470,
        360,
        140,
        "Parameters present?",
        "checked before the call",
        fill=C_MCP,
        size=10.5,
    )
    cv.box(
        570, 700, 360, 140, "HTTPS request", "Bearer JWT from\nPYVAR_API_KEY", fill=C_MCP, size=11
    )
    cv.arrow([(750, 380), (750, 470)], color=C_MCP)
    cv.arrow([(750, 610), (750, 700)], color=C_MCP)
    # the REST API, below the server frame
    cv.arrow([(750, 840), (750, 990)], color=C_API)
    cv.box(
        540,
        990,
        420,
        195,
        "pyvar.com REST API",
        "validates the body,\ncomputes, and returns\nJSON or a 4xx",
        fill=C_API,
        size=11.5,
    )
    # outcomes
    ox, ow = 1230, 540
    cv.box(
        ox,
        230,
        ow,
        112,
        "unknown function",
        "the error points to list_pyvar_functions",
        fill=CLAY,
        size=11,
    )
    cv.box(
        ox,
        460,
        ow,
        112,
        "missing parameter",
        "the error names what is expected",
        fill=CLAY,
        size=11,
    )
    cv.box(
        ox,
        990,
        ow,
        104,
        "API rejects the value",
        "'pyvar API error (HTTP 422): …'",
        fill=CLAY,
        size=11,
    )
    cv.box(ox, 1118, ow, 104, "success", "the function's JSON result", fill=C_ENGINE, size=11)
    cv.arrow([(930, 296), (ox, 296)], color=CLAY)
    cv.arrow([(930, 526), (ox, 526)], color=CLAY)
    cv.arrow([(960, 1042), (ox, 1042)], color=CLAY)
    cv.arrow([(960, 1170), (ox, 1170)], color=C_ENGINE)
    cv.label(1080, 268, "not in the catalogue", size=9.5, max_w=285)
    cv.label(1080, 498, "parameter absent", size=9.5, max_w=262)
    cv.label(1095, 1014, "HTTP 4xx", size=9.5, max_w=262)
    cv.label(1095, 1142, "HTTP 200", size=9.5, max_w=262)
    return cv.save(out, "plugin-examples-mcp-call-flow")


# ── Header image ─────────────────────────────────────────────────────────────


def logo_mark(
    ax: Any,
    x: float,
    y: float,
    scale: float,
    tail: str = H_ORANGE,
    curve: str = H_SLATE,
    lw: float = 7.0,
) -> None:
    """The pyvar bell-curve mark (docs/brand/favicon.svg geometry) at (x, y) top-left."""
    verts = [(4, 74), (26, 74), (34, 10), (60, 10), (86, 10), (94, 74), (116, 74)]
    codes = [MPath.MOVETO] + [MPath.CURVE4] * 6
    pts = [(x + vx * scale, y + vy * scale) for vx, vy in verts]
    ax.add_patch(PathPatch(MPath(pts, codes), fc="none", ec=curve, lw=lw, capstyle="round"))
    # solid clay tail: the part of the curve right of x=82, closed along the baseline
    tx = np.linspace(82, 116, 40)
    ty = np.array([_bell_y(v) for v in tx])
    poly = [(x + a * scale, y + b * scale) for a, b in zip(tx, ty)]
    poly += [(x + 116 * scale, y + 84 * scale), (x + 82 * scale, y + 84 * scale)]
    ax.add_patch(Polygon(poly, closed=True, fc=tail, ec="none", zorder=2))


def _bell_y(vx: float) -> float:
    """y of the favicon's right-hand cubic at x=vx (60,10)->(116,74)."""
    p0, p1, p2, p3 = (60, 10), (86, 10), (94, 74), (116, 74)
    ts = np.linspace(0, 1, 400)
    bx = (
        ((1 - ts) ** 3) * p0[0]
        + 3 * ((1 - ts) ** 2) * ts * p1[0]
        + 3 * (1 - ts) * ts**2 * p2[0]
        + ts**3 * p3[0]
    )
    by = (
        ((1 - ts) ** 3) * p0[1]
        + 3 * ((1 - ts) ** 2) * ts * p1[1]
        + 3 * (1 - ts) * ts**2 * p2[1]
        + ts**3 * p3[1]
    )
    return float(np.interp(vx, bx, by))


async def header_image(run: Runner, out: Path) -> Path:
    W, H = 1536, 1100
    # headline results, from the same inputs as the article's examples
    ret = gbm(500, 0.0004, 0.011, 7).tolist()
    var = await run.call(
        "historical_simulation_var",
        {"returns": ret, "portfolio_value": 10_000_000, "confidence_level": 0.99},
    )
    el = await run.call(
        "expected_loss_el_computation", {"pd": 0.02, "lgd": 0.45, "ead": 50_000_000}
    )
    lcr = await run.call(
        "liquidity_coverage_ratio_lcr",
        {"hqla": 120e6, "gross_outflows": 150e6, "gross_inflows": 40e6},
    )
    sma = await run.call(
        "basel_standardised_measurement_sma",
        {"business_indicator": 3_000_000_000, "loss_component": 0.0, "use_ilm": True},
    )
    eq = gbm(504, 0.0004, 0.011, 21).tolist()
    sharpe = await run.call("sharpe_ratio", {"returns": eq})
    cet1 = await run.call(
        "basel_iii_cet1_ratio", {"cet1_capital": 5.2e9, "risk_weighted_assets": 41e9}
    )
    bs = await run.call(
        "black_scholes_european_option",
        dict(spot=100, strike=105, rate=0.04, sigma=0.22, tau=0.5, option_type="call"),
    )
    dg = await run.call(
        "duration_gap_analysis",
        dict(
            asset_duration=4.2,
            liability_duration=3.6,
            total_assets=10e9,
            total_liabilities=9.2e9,
            rate_shock=0.02,
        ),
    )

    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=H_BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    def t(
        x: float,
        y: float,
        s: str,
        size: float,
        color: str = H_NAVY,
        weight: str = "normal",
        ha: str = "left",
        va: str = "center",
        max_w: float | None = None,
        **kw: Any,
    ) -> Any:
        tx = ax.text(x, y, s, fontsize=size, color=color, fontweight=weight, ha=ha, va=va, **kw)
        if max_w is not None:
            width = tx.get_window_extent(renderer).width
            need(
                width <= max_w, f"header text overflows ({width:.0f}px > {max_w:.0f}px): {s[:40]!r}"
            )
        return tx

    logo_mark(ax, 70, 52, 0.72, lw=6.0)
    t(188, 92, "pyvar", 27, H_NAVY, "bold")
    t(
        W - 70,
        82,
        "REAL REQUESTS   /   REAL RESULTS   /   REPRODUCIBLE",
        8.6,
        H_SLATE,
        ha="right",
        max_w=760,
    )
    ax.plot([70, W - 70], [140, 140], color="#dedcd5", lw=1.4)

    t(70, 240, "Fourteen plugins.", 32, H_NAVY, "bold", max_w=780)
    t(70, 335, "Twenty-eight", 32, H_NAVY, "bold", max_w=780)
    t(70, 430, "worked examples.", 32, H_NAVY, "bold", max_w=780)
    t(72, 515, "What pyvar does when you ask it a risk question.", 11.5, H_SLATE, max_w=780)
    t(72, 551, "One real request, one real result at a time.", 11.5, H_SLATE, max_w=780)

    tiles = [
        ("Market risk", "99% VaR", f"{var['var_pct'] * 100:.2f}%"),
        ("Credit risk", "expected loss", f"{el['el']:,.0f}"),
        ("Liquidity risk", "LCR", f"{lcr['lcr'] * 100:.1f}%"),
        ("Operational risk", "SMA capital", f"{sma['sma_capital'] / 1e6:.0f}m"),
        ("Portfolio analytics", "Sharpe ratio", f"{sharpe['sharpe']:.2f}"),
        ("Regulatory", "CET1 ratio", f"{cet1['cet1_ratio'] * 100:.2f}%"),
        ("Derivatives", "call, Black–Scholes", f"{bs['price']:.4f}"),
        ("ALM", "ΔEVE, +200bp", f"{dg['delta_eve'] / 1e6:.1f}m".replace("-", "−")),
    ]
    x0, y0, tw, th, gx, gy = 70, 620, 331, 170, 24, 22
    for i, (name, what, val) in enumerate(tiles):
        col, row = i % 4, i // 4
        x = x0 + col * (tw + gx)
        y = y0 + row * (th + gy)
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                tw,
                th,
                boxstyle="round,pad=0,rounding_size=14",
                fc="#efeee9",
                ec="#e0ded7",
                lw=1.2,
            )
        )
        ax.add_patch(Rectangle((x + 22, y + 20), 34, 5, fc=H_ORANGE, ec="none"))
        t(x + 22, y + 52, name, 11.5, H_NAVY, "bold", max_w=tw - 44)
        t(x + 22, y + 88, what, 10.5, H_SLATE, max_w=tw - 44)
        t(x + 22, y + 134, val, 21, H_NAVY, "bold", max_w=tw - 44)
    chips = ["API gateway", "Compute", "Data ingestion", "Storage", "Observability", "MCP server"]
    cx = 70
    for chip in chips:
        tx = t(cx + 20, 1034, chip, 10.5, "white", "bold")
        wpx = tx.get_window_extent(renderer).width
        tx.remove()
        ax.add_patch(
            FancyBboxPatch(
                (cx, 1010),
                wpx + 40,
                48,
                boxstyle="round,pad=0,rounding_size=24",
                fc=H_NAVY,
                ec="none",
            )
        )
        t(cx + 20, 1034, chip, 10.5, "white", "bold")
        cx += wpx + 40 + 14
    need(cx - 14 <= W - 70, "architecture chips overflow the header")
    # bell-curve flourish, bottom right of the title block
    xs = np.linspace(0, 1, 300)
    gx_ = 900 + xs * 566
    gy_ = 575 - 300 * np.exp(-((xs - 0.62) ** 2) / 0.018)
    ax.plot(gx_, gy_, color=H_SLATE, lw=4.0, solid_capstyle="round")
    mask = xs >= 0.74
    ax.fill_between(gx_[mask], gy_[mask], 575, color=H_ORANGE)

    return save(fig, out, "plugin-examples-header")


FIGURES: dict[str, Callable[[Runner, Path], Any]] = {
    "header": header_image,
    "overview": diagram_overview,
    "var-es-tail": fig_var_es_tail,
    "backtest": fig_backtest,
    "vasicek": fig_vasicek,
    "survival": fig_survival,
    "bond": fig_bond,
    "irrbb": fig_irrbb,
    "gateway-path": diagram_gateway,
    "async-flow": diagram_async,
    "convergence": fig_convergence,
    "mcp-flow": diagram_mcp,
}


async def run_all(only: list[str], out: Path) -> list[Path]:
    from api.middleware.auth import create_access_token

    token = create_access_token("example-figures", "enterprise")
    written: list[Path] = []
    async with gpe.gateway_client() as client:
        runner = Runner(gpe.Api(client, {"enterprise": token}))
        for name in only:
            path = await FIGURES[name](runner, out)
            written.append(path)
            print(f"wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return written


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
    asyncio.run(run_all(only, Path(args.out)))


if __name__ == "__main__":
    main()

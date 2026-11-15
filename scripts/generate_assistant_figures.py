#!/usr/bin/env python3
"""scripts/generate_assistant_figures.py: the two diagrams of the assistant Medium article.

Reasoning:
- The figures state counts and a file size, so those are read from the committed bank when the image
  is drawn (its manifest and the size of the per-function files), and the script fails if the bank no
  longer says what the diagram says. A figure cannot drift from the article's numbers.
- Same house look as scripts/generate_plugin_figures.py (slate and clay on white). Meaning never rests
  on colour alone: every box is labelled in words.
- Every text is measured after wrapping and the script fails if a line overflows its box.
- Medium does not accept SVG, so the article embeds the PNG; the SVG is written next to it as the
  editable source. matplotlib is a tooling dependency of this script only:  pip install matplotlib

Usage (repo root):
    python scripts/generate_assistant_figures.py
    python scripts/generate_assistant_figures.py --out /tmp/figs --only click-flow
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import generate_plugin_figures as g  # noqa: E402  (palette, rcParams, checks)

plt = g.plt
from matplotlib.patches import FancyBboxPatch  # noqa: E402

DEFAULT_OUT = ROOT / "docs" / "publications" / "assets" / "assistant"
BANK_DIR = ROOT / "portal" / "assistant" / "bank"

INK = "#22303a"
MUTED = "#5f6b73"
SLATE = g.SLATE
SLATE_FILL = "#eef2f4"
CLAY = g.CLAY
CLAY_FILL = "#f6e7e1"
SANS = ["Liberation Sans", "DejaVu Sans"]
MONO = ["Liberation Mono", "DejaVu Sans Mono"]
PT = 0.72  # a logical pixel is 0.72 point at 100 dpi
SCALE = g.DPI / 100

plt.rcParams["svg.fonttype"] = "path"


def bank_facts() -> dict[str, Any]:
    """What the committed bank says about itself, for the labels."""
    manifest = json.loads((BANK_DIR / "manifest.json").read_text(encoding="utf-8"))
    counts = manifest["counts"]
    files = sorted((BANK_DIR / manifest["bank_version"]).glob("*.json"))
    median_kb = statistics.median(p.stat().st_size for p in files) / 1024
    g.need(
        2.5 <= median_kb <= 3.5, f"the per-function file is no longer about 3 KB ({median_kb:.2f})"
    )
    g.need(counts["model"] + counts["static"] == counts["total"], "bank counts do not add up")
    return {"version": manifest["bank_version"], **counts, "median_kb": median_kb}


class Canvas:
    """A pixel-coordinate drawing board with measured, wrapped text."""

    def __init__(self, width: int, height: int) -> None:
        self.w, self.h = width, height
        self.fig = plt.figure(figsize=(width / 100, height / 100), dpi=g.DPI, facecolor="white")
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, width)
        self.ax.set_ylim(height, 0)
        self.ax.axis("off")
        self.renderer = self.fig.canvas.get_renderer()  # type: ignore[attr-defined]

    def width(self, s: str, px: float, bold: bool = False, mono: bool = False) -> float:
        t = self.fig.text(
            0,
            0,
            s,
            fontsize=px * PT,
            fontweight="bold" if bold else "normal",
            family=MONO if mono else SANS,
        )
        extent = t.get_window_extent(self.renderer).width / SCALE
        t.remove()
        return float(extent)

    def wrap(
        self, s: str, px: float, max_w: float, bold: bool = False, mono: bool = False
    ) -> list[str]:
        lines: list[str] = []
        cur = ""
        for word in s.split():
            trial = f"{cur} {word}".strip()
            if cur and self.width(trial, px, bold, mono) > max_w:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            lines.append(cur)
        for line in lines:
            g.need(
                self.width(line, px, bold, mono) <= max_w + 0.5, f"text overflows: {line[:50]!r}"
            )
        return lines

    def text(
        self,
        x: float,
        y: float,
        s: str,
        px: float,
        *,
        bold: bool = False,
        mono: bool = False,
        color: str = INK,
        ha: str = "left",
        va: str = "baseline",
    ) -> None:
        self.ax.text(
            x,
            y,
            s,
            fontsize=px * PT,
            fontweight="bold" if bold else "normal",
            family=MONO if mono else SANS,
            color=color,
            ha=ha,
            va=va,
        )

    def box(
        self,
        x: float,
        y: float,
        w: float,
        title: str,
        body: list[str] | None = None,
        *,
        fill: str = SLATE_FILL,
        edge: str = SLATE,
        edge_w: float = 1.5,
        body_px: float = 15.0,
        title_px: float = 17.0,
        mono_body: bool = False,
        dashed: bool = False,
        min_h: float = 0,
    ) -> tuple[float, float, float, float]:
        """A rounded box with a bold title and wrapped body lines; returns (x, y, w, h)."""
        pad = 14.0
        inner = w - 2 * pad
        title_lines = self.wrap(title, title_px, inner, bold=True)
        body_lines: list[str] = []
        for part in body or []:
            body_lines += self.wrap(part, body_px, inner, mono=mono_body)
        h = max(
            min_h,
            2 * pad - 2 + len(title_lines) * (title_px + 5) + len(body_lines) * (body_px + 6) + 4,
        )
        self.ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0,rounding_size=9",
                fc=fill,
                ec=edge,
                lw=edge_w * PT,
                ls="--" if dashed else "-",
            )
        )
        yy = y + pad + title_px - 2
        for line in title_lines:
            self.text(x + pad, yy, line, title_px, bold=True)
            yy += title_px + 5
        yy += 1
        for line in body_lines:
            self.text(
                x + pad, yy, line, body_px, mono=mono_body, color=MUTED if not mono_body else INK
            )
            yy += body_px + 6
        return x, y, w, h

    def arrow(
        self,
        p0: tuple[float, float],
        p1: tuple[float, float],
        *,
        color: str = SLATE,
        rad: float = 0.0,
        lw: float = 1.8,
        style: str = "-|>",
    ) -> None:
        self.ax.annotate(
            "",
            xy=p1,
            xytext=p0,
            arrowprops={
                "arrowstyle": style,
                "color": color,
                "lw": lw * PT,
                "shrinkA": 0,
                "shrinkB": 0,
                "connectionstyle": f"arc3,rad={rad}",
                "mutation_scale": 14,
            },
        )

    def title(self, s: str) -> None:
        self.text(self.w / 2, 38, s, 20.5, bold=True, ha="center")

    def save(self, out: Path, name: str) -> list[Path]:
        out.mkdir(parents=True, exist_ok=True)
        paths = [out / f"{name}.png", out / f"{name}.svg"]
        self.fig.savefig(paths[0], dpi=g.DPI, facecolor="white")
        self.fig.savefig(paths[1], facecolor="white")
        plt.close(self.fig)
        return paths


# ── Figure 1: what happens when you click ──────────────────────────────────


def fig_click_flow(out: Path) -> list[Path]:
    facts = bank_facts()
    c = Canvas(900, 400)
    c.title("One click, one static file, no model")
    top, row_h = 84, 122
    a = c.box(
        28, top, 236, "You click", ["What it does", "When to use it", "Compare with…"], min_h=row_h
    )
    b = c.box(
        332,
        top,
        268,
        "One static file",
        [f"one per function, about {round(facts['median_kb'])} KB", "cached for an hour"],
        fill=CLAY_FILL,
        edge=CLAY,
        edge_w=2.2,
        min_h=row_h,
    )
    d = c.box(668, top, 204, "Shown on the page", ["the text, as text, never as HTML"], min_h=row_h)
    g.need(max(a[3], b[3], d[3]) == row_h, "a top box outgrew the row height")
    mid = top + row_h / 2
    c.arrow((a[0] + a[2] + 4, mid), (b[0] - 4, mid))
    c.arrow((b[0] + b[2] + 4, mid), (d[0] - 4, mid))
    c.text((a[0] + a[2] + b[0]) / 2, mid - 12, "GET", 14, bold=True, color=SLATE, ha="center")
    c.text((b[0] + b[2] + d[0]) / 2, mid - 12, "text", 14, bold=True, color=SLATE, ha="center")
    path = "/assistant/bank/<version>/<function>.json"
    py = top + row_h + 38
    g.need(c.width(path, 14, mono=True) <= 480, "path label too wide")
    c.text(28, py, "Request:", 14.5, bold=True)
    c.text(28 + c.width("Request: ", 14.5, bold=True), py, path, 14, mono=True)
    sy, sh = py + 24, 120
    c.box(
        28,
        sy,
        412,
        "Sent to the server",
        ["no body, no cookie, no query string", "nothing you typed"],
        min_h=sh,
    )
    c.box(
        480,
        sy,
        392,
        "Not in the request path",
        ["×  no model call", "×  no API key", "×  no personal data"],
        fill="white",
        edge=CLAY,
        edge_w=1.6,
        dashed=True,
        min_h=sh,
    )
    total = sy + sh + 28
    c.fig.set_size_inches(900 / 100, total / 100)
    c.ax.set_ylim(total, 0)
    return c.save(out, "click-flow")


# ── Figure 2: what stands behind each answer ───────────────────────────────


def fig_answer_checks(out: Path) -> list[Path]:
    facts = bank_facts()
    c = Canvas(900, 660)
    c.title("Every answer is checked twice before it is served")
    cx, w, gap = 40, 520, 30
    y = 78
    steps = [
        (
            "1  The function's record",
            ["inputs, defaults and formula", "for a comparison, the other function's record too"],
        ),
        ("2  Writer model", ["Claude Sonnet 5.5 writes the answer from the record only"]),
        (
            "3  Code checks",
            [
                "every function name exists",
                "every number comes from the record",
                "no advice; wording and length",
            ],
        ),
        ("4  Second model", ["Claude Opus 5.5 reads the answer against the same record"]),
    ]
    boxes = []
    for title, body in steps:
        bx = c.box(cx, y, w, title, body, edge_w=1.6)
        boxes.append(bx)
        y += bx[3] + gap
    for upper, lower in zip(boxes, boxes[1:], strict=False):
        c.arrow((cx + w / 2, upper[1] + upper[3] + 3), (cx + w / 2, lower[1] - 3))
    # the loop from the code checks back to the writer, drawn in the right margin
    wr, ck = boxes[1], boxes[2]
    y_wr, y_ck = wr[1] + wr[3] / 2, ck[1] + ck[3] / 2
    x_loop = cx + w + 40
    c.ax.plot(
        [cx + w + 2, x_loop, x_loop],
        [y_ck, y_ck, y_wr],
        color=CLAY,
        lw=1.8 * PT,
        solid_capstyle="butt",
    )
    c.arrow((x_loop, y_wr), (cx + w + 3, y_wr), color=CLAY)
    note_x = x_loop + 18
    y_mid = (y_wr + y_ck) / 2
    c.text(note_x, y_mid - 16, "If a check fails,", 15, bold=True, color=CLAY)
    c.text(note_x, y_mid + 6, "the draft goes back to", 14.5, color=MUTED)
    c.text(note_x, y_mid + 27, "the writer with the failed", 14.5, color=MUTED)
    c.text(note_x, y_mid + 48, "checks: up to three tries", 14.5, color=MUTED)
    # the two outcomes, side by side across the full width
    last = boxes[3]
    oy = last[1] + last[3] + 50
    ok_w, bad_x = 300, 40 + 300 + 24
    ok = c.box(
        cx,
        oy,
        ok_w,
        "Served",
        [f"{facts['model']:,} model-written answers"],
        edge_w=1.6,
        min_h=116,
    )
    c.box(
        bad_x,
        oy,
        900 - 40 - bad_x,
        "If the second model flags it",
        [
            "Opus rewrites it once. If the rewrite passes, it is served; if not, the answer becomes plain text built from the record.",
            f"{facts['static']} of {facts['total']:,} answers are plain text",
        ],
        fill=CLAY_FILL,
        edge=CLAY,
        edge_w=2.2,
        min_h=116,
    )
    x_ok, x_bad = ok[0] + ok[2] / 2, cx + w - 100
    c.arrow((x_ok, last[1] + last[3] + 3), (x_ok, oy - 3))
    c.arrow((x_bad, last[1] + last[3] + 3), (x_bad, oy - 3), color=CLAY)
    total = int(oy + 116 + 28)
    c.fig.set_size_inches(900 / 100, total / 100)
    c.ax.set_ylim(total, 0)
    return c.save(out, "answer-checks")


FIGURES = {"click-flow": fig_click_flow, "answer-checks": fig_answer_checks}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="folder for the PNG and SVG files")
    parser.add_argument("--only", default="", help="comma-separated figure names")
    args = parser.parse_args()
    names = [n for n in args.only.split(",") if n] or list(FIGURES)
    for name in names:
        g.need(name in FIGURES, f"unknown figure {name!r}; choose from {', '.join(FIGURES)}")
        for path in FIGURES[name](Path(args.out)):
            print("wrote", path)


if __name__ == "__main__":
    main()

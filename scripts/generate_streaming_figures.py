#!/usr/bin/env python3
"""scripts/generate_streaming_figures.py — the chart for the result-streaming Medium article.

Reasoning:
- The plotted push delays are read from docs/data/streaming-push-lag-dev.csv (the six jobs of
  runs 0g and 0h in docs/plan-streaming-quotes-in-results-out.md section 9.9), and the poll
  band's width from the shipped setting var_stream_poll_interval_seconds in config.py, so the
  figure cannot drift from the numbers in the article.
- Same house look as scripts/generate_plugin_figures.py (slate and clay on white). The poll
  band is slate and the measured pushes are clay; identity never rests on colour alone: the two
  are different marks (a band and dots) and both are labelled on the chart.
- Medium does not accept SVG, so the output is PNG. matplotlib is a tooling dependency of this
  script only:  pip install matplotlib

Usage (repo root):
    python scripts/generate_streaming_figures.py
    python scripts/generate_streaming_figures.py --out /tmp/figs
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import generate_plugin_figures as g  # noqa: E402  (palette, rcParams, save)

from config import Settings  # noqa: E402

plt = g.plt

DEFAULT_OUT = ROOT / "docs" / "publications" / "assets" / "streaming-results"
LAG_CSV = ROOT / "docs" / "data" / "streaming-push-lag-dev.csv"


def read_push_lags() -> dict[str, list[int]]:
    """Measured push delays in ms, by run, in file order."""
    runs: dict[str, list[int]] = {}
    with LAG_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            runs.setdefault(row["run"], []).append(int(row["lag_ms"]))
    g.need(len(runs) == 2, f"expected two runs in {LAG_CSV.name}, found {sorted(runs)}")
    g.need(all(len(v) == 3 for v in runs.values()), "expected three jobs per run")
    return runs


def fig_push_lag_vs_poll(out: Path) -> Path:
    runs = read_push_lags()
    poll_ms = round(Settings.model_fields["var_stream_poll_interval_seconds"].default * 1000)
    all_lags = [v for lags in runs.values() for v in lags]
    g.need(max(all_lags) < poll_ms / 4, "push delays are no longer small against the poll band")

    fig, ax = plt.subplots(figsize=(9.0, 3.3))
    rows = [("Poll every 2 s", 0.0), ("Push, run 0g", 1.0), ("Push, run 0h", 2.0)]

    # The band a poll could return the result in: anywhere between 0 and one interval.
    ax.barh(0.0, poll_ms, height=0.5, color=g.SLATE_FILL, edgecolor=g.SLATE, linewidth=1.2)
    ax.plot([poll_ms / 2] * 2, [-0.25, 0.25], color=g.SLATE, linewidth=2)
    ax.text(
        poll_ms / 2 + 25,
        0.0,
        f"waits {poll_ms // 2:,} ms on average",
        va="center",
        ha="left",
        fontsize=9.5,
        color=g.INK,
    )
    ax.text(
        poll_ms - 25,
        0.0,
        f"up to {poll_ms:,} ms",
        va="center",
        ha="right",
        fontsize=9.5,
        color=g.INK,
    )

    for run, y in (("0g", 1.0), ("0h", 2.0)):
        lags = runs[run]
        # Dots closer than one marker width would hide each other: step the later one up.
        ys = [y + (0.16 if i and lag - lags[i - 1] < 8 else 0.0) for i, lag in enumerate(lags)]
        ax.scatter(
            lags,
            ys,
            s=70,
            color=g.CLAY,
            edgecolor="white",
            linewidth=1.5,
            zorder=3,
        )
        ax.text(
            max(lags) + 45,
            y,
            ", ".join(str(v) for v in lags) + " ms",
            va="center",
            ha="left",
            fontsize=9.5,
            color=g.INK,
        )

    ax.set_yticks([y for _, y in rows])
    ax.set_yticklabels([label for label, _ in rows], fontsize=10, color=g.INK)
    ax.set_ylim(-0.6, 2.6)
    ax.set_xlim(0, poll_ms)
    ax.set_xticks([0, 500, 1000, 1500, poll_ms])
    ax.set_xticklabels([f"{t:,}" for t in (0, 500, 1000, 1500, poll_ms)], fontsize=9, color=g.MUTED)
    ax.set_xlabel("Milliseconds after the result was stored", fontsize=9.5, color=g.MUTED)
    ax.xaxis.grid(True, color=g.GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(g.GRID)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=0)
    ax.set_title(
        "A pushed result arrives in about 0.13 s; a 2-second poll can leave it waiting up to 2 s",
        loc="left",
        fontsize=11,
        fontweight="bold",
        color=g.INK,
        pad=12,
    )
    fig.tight_layout()
    return g.save(fig, out, "push-lag-vs-poll")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    print("wrote", fig_push_lag_vs_poll(Path(args.out)))


if __name__ == "__main__":
    main()

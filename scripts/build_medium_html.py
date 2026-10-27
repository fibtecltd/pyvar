#!/usr/bin/env python3
"""scripts/build_medium_html.py — the Medium-ready HTML of the result-streaming article.

Reasoning:
- Medium's editor drops pasted <table> elements, so every markdown table of the article is drawn
  as an image (a JPG in docs/publications/assets/tables/, same look as the existing table images:
  slate header row, striped rows, monospace for code spans) and the HTML refers to the image, with
  alt text that carries the table's content. The images are drawn from the article's own markdown,
  so a table cannot drift from the text.
- The page is the markdown run through pandoc, with the house CSS of the other pages in
  docs/publications/medium-ready/, every image embedded as a base64 data URI (the page is pasted
  into Medium in one go) and the paste instructions box.
- matplotlib and pandoc are tooling dependencies of this script only:  pip install matplotlib

Usage (repo root):
    python scripts/build_medium_html.py
    python scripts/build_medium_html.py --out /tmp/medium --tables /tmp/tables
"""

from __future__ import annotations

import argparse
import base64
import html
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import generate_plugin_figures as g  # noqa: E402  (palette, rcParams)

plt = g.plt
PUB = ROOT / "docs" / "publications"
ARTICLE = PUB / "pyvar-streaming-results-medium-article.md"
DEFAULT_HTML_DIR = PUB / "medium-ready"
DEFAULT_TABLES_DIR = PUB / "assets" / "tables"

# markdown heading above a table -> (image file stem, title drawn on the image, first column share)
TABLES = {
    "What the server does with your socket": (
        "streaming-results-socket-table",
        "Frames and close codes",
        0.36,
    ),
    "How it performs": (
        "streaming-results-measures-table",
        "Measured on dev.pyvar.com",
        0.40,
    ),
}

# Table look, in logical pixels (the JPG is drawn at twice that, like the existing ones).
WIDTH, MARGIN, SCALE = 873, 30, 2
HEADER_H, LINE_H, PAD_Y, PAD_X, TITLE_Y = 42, 21, 12, 12, 36
SANS_PX, MONO_PX, HEAD_PX, TITLE_PX = 14.5, 13.2, 15.0, 20.5
INK, HEAD_FILL, BORDER, ROW_ALT = "#22303a", "#4c6b7a", "#c7d1d6", "#eef2f4"
SANS = ["Liberation Sans", "DejaVu Sans"]
MONO = ["Liberation Mono", "DejaVu Sans Mono"]

CSS = """body { max-width: 760px; margin: 40px auto; padding: 0 20px;
       font-family: Georgia, 'Times New Roman', serif; color: #1a1a1a;
       line-height: 1.6; font-size: 18px; }
h1 { font-family: -apple-system, Helvetica, Arial, sans-serif; font-size: 34px;
     font-weight: 700; line-height: 1.25; margin: 0.4em 0 0.3em; }
h2 { font-family: -apple-system, Helvetica, Arial, sans-serif; font-size: 26px;
     font-weight: 700; margin: 1.4em 0 0.4em; }
h3 { font-family: -apple-system, Helvetica, Arial, sans-serif; font-size: 21px;
     font-weight: 700; margin: 1.2em 0 0.4em; }
p { margin: 0.9em 0; }
p.subtitle-wrap { margin: 0 0 1em; }
p.subtitle-wrap em { display: block; font-style: italic; color: #555; font-size: 20px; }
code { font-family: SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.85em;
       background: #f2f2f2; padding: 0.1em 0.3em; border-radius: 3px; }
pre { background: #f6f6f6; border-radius: 6px; padding: 14px 16px; overflow-x: auto; }
pre code { background: none; padding: 0; font-size: 14px; line-height: 1.5; }
blockquote { border-left: 3px solid #ccc; margin: 1em 0; padding: 0.2em 0 0.2em 1.2em;
             color: #555; font-style: italic; }
hr { border: none; border-top: 1px solid #ddd; margin: 2em 0; }
img { max-width: 100%; display: block; margin: 1.2em 0; }
a { color: #1a6b8a; }
ul { padding-left: 1.4em; }
li { margin: 0.4em 0; }
.instructions { background: #fff8e6; border: 1px solid #e8d38a; border-radius: 8px;
                padding: 14px 18px; margin-bottom: 2em; font-family: -apple-system, sans-serif;
                font-size: 14px; color: #6b5900; }
"""

INSTRUCTIONS = (
    '<div class="instructions"><strong>Paste-ready for Medium:</strong> select all, copy, paste '
    "directly into a new Medium story. The tables are images, so they paste as they look; the "
    "code blocks paste as code blocks. Check that each image kept its caption.</div>"
)


# ── Tables ───────────────────────────────────────────────────────────────────────────────────────


def parse_tables(text: str) -> list[tuple[int, int, str, list[str], list[list[str]]]]:
    """(first line, last line, heading above, header cells, body rows) of every markdown table."""
    lines = text.split("\n")
    found = []
    heading = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[-| :]+\|$", lines[i + 1]):
            j = i + 2
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            cells = [[c.strip() for c in row.strip("|").split("|")] for row in lines[i:j]]
            found.append((i, j - 1, heading, cells[0], cells[2:]))
            i = j
            continue
        i += 1
    return found


class Measurer:
    """Text widths in logical pixels, for wrapping."""

    def __init__(self) -> None:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        self.fig = Figure(figsize=(WIDTH / 100, 2), dpi=100 * SCALE)
        FigureCanvasAgg(self.fig)
        self.renderer = self.fig.canvas.get_renderer()  # type: ignore[attr-defined]

    def width(self, word: str, mono: bool, bold: bool = False) -> float:
        px = MONO_PX if mono else (HEAD_PX if bold else SANS_PX)
        text = self.fig.text(
            0,
            0,
            word,
            fontsize=px * 0.72,
            family=MONO if mono else SANS,
            fontweight="bold" if bold else "normal",
        )
        extent = text.get_window_extent(self.renderer).width / SCALE
        text.remove()
        return float(extent)


def tokens(cell: str) -> list[tuple[str, bool, bool]]:
    """Words of a cell: (word, from a `code span`, glued to the word before, with no space)."""
    out: list[tuple[str, bool, bool]] = []
    ends_in_space = True  # nothing before the first word
    for part in re.split(r"(`[^`]+`)", cell):
        if not part:
            continue
        code = part.startswith("`") and part.endswith("`")
        text = part.strip("`") if code else part
        starts_in_space = text[:1].isspace()
        for i, word in enumerate(text.split()):
            glue = i == 0 and not starts_in_space and not ends_in_space
            out.append((word, code, glue))
        ends_in_space = text[-1:].isspace() if not code else False
    return out


def wrap(measure: Measurer, cell: str, width: float) -> list[list[tuple[str, bool, float]]]:
    """Lines of (word, is_code, x offset) that fit `width`."""
    space = measure.width("n n", False) - measure.width("nn", False)
    lines: list[list[tuple[str, bool, float]]] = [[]]
    x = 0.0
    for word, code, glue in tokens(cell):
        w = measure.width(word, code)
        gap = 0.0 if glue else space
        if lines[-1] and not glue and x + gap + w > width:
            lines.append([])
            x = 0.0
            gap = 0.0
        if lines[-1]:
            x += gap
        lines[-1].append((word, code, x))
        x += w
    return lines


def draw_table(
    measure: Measurer,
    header: list[str],
    rows: list[list[str]],
    title: str,
    first_share: float,
    path: Path,
) -> tuple[int, int]:
    from matplotlib.patches import FancyBboxPatch, Rectangle

    inner = WIDTH - 2 * MARGIN
    col_x = [MARGIN + PAD_X, MARGIN + inner * first_share + PAD_X]
    col_w = [inner * first_share - 2 * PAD_X, inner * (1 - first_share) - 2 * PAD_X]
    laid = [[wrap(measure, cell, col_w[k]) for k, cell in enumerate(row)] for row in rows]
    heights = [max(len(c) for c in row) * LINE_H + 2 * PAD_Y - 4 for row in laid]
    top = 76
    height = int(top + HEADER_H + sum(heights) + MARGIN)

    fig = plt.figure(figsize=(WIDTH / 100, height / 100), dpi=100 * SCALE, facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(height, 0)
    ax.axis("off")
    pt = 0.72  # a logical pixel is 0.72 point at 100 dpi
    ax.text(
        WIDTH / 2,
        TITLE_Y,
        title,
        ha="center",
        va="center",
        fontsize=TITLE_PX * pt,
        fontweight="bold",
        color=INK,
        family=SANS,
    )
    ax.add_patch(
        FancyBboxPatch(
            (MARGIN, top),
            inner,
            HEADER_H,
            boxstyle="round,pad=0,rounding_size=6",
            fc=HEAD_FILL,
            ec=HEAD_FILL,
            lw=1.5 * pt,
        )
    )
    for k, label in enumerate(header):
        ax.text(
            col_x[k],
            top + HEADER_H / 2 + 1,
            label,
            ha="left",
            va="center",
            fontsize=HEAD_PX * pt,
            fontweight="bold",
            color="white",
            family=SANS,
        )
    y = top + HEADER_H
    for n, (row, h) in enumerate(zip(laid, heights)):
        ax.add_patch(
            Rectangle(
                (MARGIN, y), inner, h, fc=ROW_ALT if n % 2 == 0 else "white", ec=BORDER, lw=1 * pt
            )
        )
        for k, lines in enumerate(row):
            for li, words in enumerate(lines):
                base = y + PAD_Y + 12 + li * LINE_H
                for word, code, dx in words:
                    ax.text(
                        col_x[k] + dx,
                        base,
                        word,
                        ha="left",
                        va="baseline",
                        fontsize=(MONO_PX if code else SANS_PX) * pt,
                        color=INK,
                        family=MONO if code else SANS,
                    )
        y += h
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=100 * SCALE, facecolor="white", format="jpg", pil_kwargs={"quality": 95})
    plt.close(fig)
    return WIDTH, height


def alt_text(title: str, header: list[str], rows: list[list[str]]) -> str:
    body = "; ".join(f"{r[0]}: {r[1]}" for r in rows)
    return re.sub(
        r"\s+", " ", f"Table, {title} ({header[0]} / {header[1]}). {body}".replace("`", "")
    )


def tables_to_images(text: str, tables_dir: Path) -> str:
    """Draw every table of `text` to a JPG and put an image reference in its place."""
    measure = Measurer()
    lines = text.split("\n")
    for first, last, heading, header, rows in reversed(parse_tables(text)):
        g.need(heading in TABLES, f"no image settings for the table under {heading!r}")
        stem, title, share = TABLES[heading]
        path = tables_dir / f"{stem}.jpg"
        draw_table(measure, header, rows, title, share, path)
        rel = f"./assets/tables/{stem}.jpg"
        lines[first : last + 1] = [f"![{alt_text(title, header, rows)}]({rel})"]
    return "\n".join(lines)


# ── HTML ─────────────────────────────────────────────────────────────────────────────────────────


def embed(match: re.Match[str], base: Path, override: dict[str, Path]) -> str:
    src = match.group("src")
    path = override.get(src) or (base / src).resolve()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}[path.suffix.lower()]
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img alt="{match.group("alt")}" src="data:{mime};base64,{data}" />'


def build(article: Path, html_dir: Path, tables_dir: Path) -> Path:
    text = tables_to_images(article.read_text(encoding="utf-8"), tables_dir)
    work = article.parent / ".build-medium.md"
    work.write_text(text, encoding="utf-8")
    try:
        body = subprocess.run(
            ["pandoc", "-f", "gfm", "-t", "html", "--no-highlight", "--wrap=none", str(work)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    finally:
        work.unlink(missing_ok=True)

    title = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
    g.need(title is not None, "no h1 in the article")
    assert title is not None
    page_title = html.unescape(re.sub(r"<[^>]+>", "", title.group(1)))
    # the italic line under the title is the subtitle
    body = re.sub(
        r"(</h1>\s*)<p>(<em>.*?</em>)</p>",
        r'\1<p class="subtitle-wrap">\2</p>',
        body,
        count=1,
        flags=re.S,
    )
    # an image alone in a paragraph is a bare <img>, as in the other pages
    body = re.sub(r"<p>(<img [^>]*?/>)</p>", r"\1", body)
    # the table images were drawn into tables_dir, which may not be the article's assets/tables
    override = {f"./assets/tables/{p.name}": p for p in tables_dir.glob("streaming-results-*.jpg")}
    body = re.sub(
        r'<img src="(?P<src>[^"]+)" alt="(?P<alt>[^"]*)" />',
        lambda m: embed(m, article.parent, override),
        body,
    )
    g.need("<table" not in body, "a table is left in the page")
    g.need("./assets/" not in body, "an image was not embedded")
    page = (
        f'<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>{html.escape(page_title)}</title>\n'
        f"<style>\n{CSS}</style></head><body>\n{INSTRUCTIONS}\n{body}</body></html>\n"
    )
    html_dir.mkdir(parents=True, exist_ok=True)
    out = html_dir / (article.stem + ".html")
    out.write_text(page, encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--article", default=str(ARTICLE))
    parser.add_argument("--out", default=str(DEFAULT_HTML_DIR), help="folder for the HTML")
    parser.add_argument("--tables", default=str(DEFAULT_TABLES_DIR), help="folder for the JPGs")
    args = parser.parse_args()
    print("wrote", build(Path(args.article), Path(args.out), Path(args.tables)))


if __name__ == "__main__":
    main()

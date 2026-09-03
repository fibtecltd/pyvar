"""One-off script: render docs/prd-claude-partner-hub.md (plus a short cover
note) as a clean PDF for upload to the Claude Partner Hub's "My Content"
section. Not part of the repo's regular build -- run manually, output isn't
committed.

Usage:
    pip install markdown xhtml2pdf   # not in requirements*.txt -- this
                                      # script isn't part of the app/CI/
                                      # Docker build, deliberately kept out
                                      # of those dependency sets.
    python3 scripts/build_prd_pdf.py [output_path]

    output_path defaults to /tmp/pyvar-partner-hub-prd.pdf.
"""

from __future__ import annotations

import sys
from pathlib import Path

import markdown
from xhtml2pdf import pisa

REPO_ROOT = Path(__file__).resolve().parent.parent
PRD_PATH = REPO_ROOT / "docs" / "prd-claude-partner-hub.md"
DEFAULT_OUT_PATH = Path("/tmp/pyvar-partner-hub-prd.pdf")  # nosec B108 -- manual, single-user, never-in-CI script; fixed path is documented UX, not a shared/untrusted temp dir

COVER_HTML = """
<div class="cover">
  <h1>pyvar.com — Claude Partner Network Case Study</h1>
  <p class="subtitle">Fibtec Limited</p>
  <p class="note">
    <b>What this is:</b> a case-study-shaped PRD for pyvar.com, an
    open-source (Apache-2.0) regulatory risk computation platform built,
    hardened, and shipped end-to-end with Claude Code. Every number in
    this document is checkable directly against the public repository
    (<a href="https://github.com/fibtecltd/pyvar">github.com/fibtecltd/pyvar</a>),
    its commit history, and the live API.
  </p>
  <p class="note">
    <b>What we're asking for:</b> we'd like pyvar.com considered as a
    public case study for the Claude Partner Network / Partner Hub, as a
    Claude-native product built end-to-end with Claude Code -- not under
    the Services Track's consulting-firm criteria, which this document's
    own positioning note (below) explains does not fit pyvar.com today.
    Concretely: (1) a listing or feature as a Claude-built product case
    study, and/or (2) feedback on what a genuine Services Track
    application would need once real joint-customer deployments exist to
    cite.
  </p>
  <p class="note">
    <b>Contact:</b> Filippo Buchicchio, Fibtec Limited
    (CCA-F certified) &mdash; filippo.b@fibtec.co.uk
  </p>
</div>
<div style="page-break-after: always;"></div>
"""

DEJAVU_MONO_DIR = Path("/usr/share/fonts/truetype/dejavu")

# xhtml2pdf's default fonts (Helvetica/Courier) don't cover the box-drawing
# and pointer glyphs (─│►▼) used in the PRD's architecture diagram -- they
# render as solid black boxes. DejaVu Sans Mono has full coverage; register
# it separately from the main CSS block so the big stylesheet below can stay
# a plain (non-f) string.
FONT_FACE_CSS = f"""
@font-face {{
    font-family: "DejaVu Sans Mono";
    src: url("{DEJAVU_MONO_DIR / 'DejaVuSansMono.ttf'}");
}}
@font-face {{
    font-family: "DejaVu Sans Mono";
    font-weight: bold;
    src: url("{DEJAVU_MONO_DIR / 'DejaVuSansMono-Bold.ttf'}");
}}
@font-face {{
    font-family: "DejaVu Sans Mono";
    font-style: italic;
    src: url("{DEJAVU_MONO_DIR / 'DejaVuSansMono-Oblique.ttf'}");
}}
@font-face {{
    font-family: "DejaVu Sans Mono";
    font-weight: bold;
    font-style: italic;
    src: url("{DEJAVU_MONO_DIR / 'DejaVuSansMono-BoldOblique.ttf'}");
}}
"""

CSS = """
@page {
    size: letter;
    margin: 2.2cm 2cm;
}
body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.45;
    color: #1a1a1a;
}
.cover h1 {
    font-size: 20pt;
    margin-bottom: 0.2em;
}
.cover .subtitle {
    font-size: 12pt;
    color: #555555;
    margin-top: 0;
    margin-bottom: 1.2em;
}
.cover .note {
    font-size: 10.5pt;
    margin-bottom: 1em;
}
h1 {
    font-size: 16pt;
    color: #1a1a1a;
    border-bottom: 1pt solid #cccccc;
    padding-bottom: 4pt;
    margin-top: 0;
}
h2 {
    font-size: 13pt;
    color: #1a1a1a;
    margin-top: 1.1em;
    margin-bottom: 0.4em;
}
h3 {
    font-size: 11pt;
    color: #1a1a1a;
    margin-top: 0.9em;
    margin-bottom: 0.3em;
}
p {
    margin: 0.4em 0;
    text-align: justify;
}
ul, ol {
    margin: 0.3em 0 0.6em 0;
    padding-left: 1.3em;
}
li {
    margin-bottom: 0.35em;
}
code {
    font-family: "DejaVu Sans Mono", Courier, monospace;
    font-size: 9pt;
    background-color: #f2f2f2;
    padding: 1pt 3pt;
}
pre {
    font-family: "DejaVu Sans Mono", Courier, monospace;
    font-size: 7.5pt;
    background-color: #f2f2f2;
    padding: 8pt;
    white-space: pre-wrap;
    line-height: 1.25;
}
blockquote {
    border-left: 2pt solid #999999;
    padding-left: 10pt;
    color: #444444;
    margin: 0.6em 0;
}
hr {
    border: none;
    border-top: 0.5pt solid #cccccc;
    margin: 1.1em 0;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.6em 0;
    font-size: 9pt;
}
th, td {
    border: 0.5pt solid #cccccc;
    padding: 4pt 6pt;
    text-align: left;
}
a {
    color: #1a5fb4;
}
strong {
    color: #000000;
}
"""


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT_PATH
    md_text = PRD_PATH.read_text(encoding="utf-8")
    body_html = markdown.markdown(
        md_text,
        extensions=["extra", "sane_lists", "toc"],
    )

    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{FONT_FACE_CSS}{CSS}</style>
</head>
<body>
{COVER_HTML}
{body_html}
</body>
</html>
"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        result = pisa.CreatePDF(full_html, dest=f)

    if result.err:
        print(f"PDF generation had {result.err} error(s)", file=sys.stderr)
        return 1

    print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

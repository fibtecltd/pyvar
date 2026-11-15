"""Catalogue text on the portal (portal/pyvar.js: _catalogueInline and _catalogueBlocksHtml).

Reasoning:
- A function's summary, description, parameter help and formula notes come from its engine docstring
  (portal/functions.json) and are written in reStructuredText-style markup. The portal used to show them
  raw: double backticks, ``:func:`` roles, ``*emphasis*``, bullets run into a paragraph, and the summary and
  the description joined by a dash. They are now turned into the few elements the markup stands for.
- The text is put into the page with innerHTML, so the formatter escapes first and adds only its own tags.
  These tests run it under node against every entry of the catalogue and check that: nothing but those tags
  reaches the page, no docstring markup is left, and the places that render catalogue text all go through it.
- No browser runs here (the layout was checked in Chromium when the change was made); the phone-width rules
  are checked as source, the way tests/test_assistant_widget.py checks the widget.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PORTAL = REPO / "portal"
SOURCE = (PORTAL / "pyvar.js").read_text(encoding="utf-8")
CSS = (PORTAL / "pyvar.css").read_text(encoding="utf-8")
CATALOGUE = json.loads((PORTAL / "functions.json").read_text(encoding="utf-8"))

HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify({
  inline: input.inline.map(_catalogueInline),
  blocks: input.blocks.map(_catalogueBlocksHtml),
}));
"""

ALLOWED_TAG = re.compile(
    r'</?(?:p|ul|ol|li|em|code|pre|span)(?: class="(?:cat-code|cat-pre|tryit-tag)")?>'
)


def run(inline: list[str], blocks: list[str]) -> dict[str, list[str]]:
    """Run the formatter block of pyvar.js under node on the given strings."""
    start = SOURCE.index("function _escapeHtml")
    end = SOURCE.index("// </catalogue-text>")
    node = shutil.which("node")
    assert node is not None, "node is needed to run the portal formatter"
    done = subprocess.run(  # noqa: S603 - a fixed script, no user input
        [node, "-e", SOURCE[start:end] + HARNESS],
        input=json.dumps({"inline": inline, "blocks": blocks}),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    out: dict[str, list[str]] = json.loads(done.stdout)
    return out


def inline(text: str) -> str:
    return run([text], [])["inline"][0]


def blocks(text: str) -> str:
    return run([], [text])["blocks"][0]


def test_inline_markup_becomes_elements() -> None:
    assert inline("over ``n_years``.") == 'over <code class="cat-code">n_years</code>.'
    assert inline("a `window` of") == 'a <code class="cat-code">window</code> of'
    assert inline(":func:`~engine.alm_nii_eve.eve_sensitivity_analysis` and :func:`other`") == (
        '<code class="cat-code">eve_sensitivity_analysis</code> and <code class="cat-code">other</code>'
    )
    assert inline("net outflows are gross minus *capped* inflows") == (
        "net outflows are gross minus <em>capped</em> inflows"
    )
    assert inline("a -- b") == "a — b"


def test_stars_that_are_not_emphasis_are_left_alone() -> None:
    assert inline("exact = CVA * 0.01 and 2 * 3 * 4") == "exact = CVA * 0.01 and 2 * 3 * 4"
    assert inline("``a * b`` and ``*x*``") == (
        '<code class="cat-code">a * b</code> and <code class="cat-code">*x*</code>'
    )


def test_html_in_catalogue_text_is_escaped() -> None:
    out = inline('<script>alert(1)</script> P&L ``<b>`` "quoted"')
    assert "<script" not in out and "<b>" not in out
    assert "&lt;script&gt;" in out and "P&amp;L" in out and "&lt;b&gt;" in out
    assert "&quot;quoted&quot;" in out
    assert blocks("<img src=x onerror=alert(1)>") == "<p>&lt;img src=x onerror=alert(1)&gt;</p>"


def test_blocks_paragraphs_lists_tags_and_literal_blocks() -> None:
    assert blocks("One\nstill one.\n\nTwo.") == "<p>One still one.</p><p>Two.</p>"
    assert blocks("[REGULATORY] BCBS d368. Reports ``x``.") == (
        '<p><span class="tryit-tag">REGULATORY</span> BCBS d368. Reports '
        '<code class="cat-code">x</code>.</p>'
    )
    assert blocks("Computes:\n  * ``cs01``: the change\n    in CVA\n  * ``ir01``: other") == (
        '<p>Computes:</p><ul><li><code class="cat-code">cs01</code>: the change in CVA</li>'
        '<li><code class="cat-code">ir01</code>: other</li></ul>'
    )
    assert blocks("Reads the quantile::\n\n    VaR = u + [ a < b ]\n\nthen stops.") == (
        '<p>Reads the quantile:</p><pre class="cat-pre">VaR = u + [ a &lt; b ]</pre><p>then stops.</p>'
    )
    assert blocks("") == "" and blocks(None) == ""  # type: ignore[arg-type]


def test_a_code_span_across_two_lines_is_not_a_bullet() -> None:
    assert blocks("Estimates ``a * b\n* c`` over time.") == (
        '<p>Estimates <code class="cat-code">a * b * c</code> over time.</p>'
    )


def visible(markup: str) -> str:
    """What a reader sees: the formatter's own tags removed, entities decoded, code and literal text out."""
    markup = re.sub(r"<(code|pre)[^>]*>.*?</\1>", " ", markup, flags=re.S)
    markup = ALLOWED_TAG.sub(" ", markup)
    assert "<" not in markup and ">" not in markup, markup[:200]  # nothing but the formatter's tags
    return html.unescape(markup)


def catalogue_texts() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    inline_items: list[tuple[str, str]] = []
    block_items: list[tuple[str, str]] = []
    for entry in CATALOGUE:
        name = entry["name"]
        inline_items.append((f"{name} summary", entry["summary"]))
        if entry.get("description"):
            block_items.append((f"{name} description", entry["description"]))
        for param in entry["params"]:
            if param.get("description"):
                inline_items.append((f"{name}.{param['name']}", param["description"]))
        formula = entry.get("formula") or {}
        for key in ("caveat", "citation"):
            if formula.get(key):
                inline_items.append((f"{name} {key}", formula[key]))
    return inline_items, block_items


def test_every_catalogue_text_renders_without_docstring_markup() -> None:
    inline_items, block_items = catalogue_texts()
    out = run([t for _, t in inline_items], [t for _, t in block_items])
    shown = list(zip((n for n, _ in inline_items), out["inline"], strict=True)) + list(
        zip((n for n, _ in block_items), out["blocks"], strict=True)
    )
    assert len(shown) > 1000
    problems = []
    for name, markup in shown:
        text = visible(markup)
        for label, pattern in {
            "double backtick": r"``",
            "single backtick": r"`",
            "rst role": r":(?:func|class|meth|mod|attr|data|ref|doc|math):",
            "emphasis marks": r"(?:^|[\s(])\*[^*\s](?:[^*]*[^*\s])?\*(?=$|[\s).,;:!?])",
            "placeholder": "\u0000",
            "double dash": r" -- ",
        }.items():
            if re.search(pattern, text):
                problems.append(f"{name}: {label}")
    assert not problems, problems[:10]


def test_catalogue_text_is_never_placed_in_html_unformatted() -> None:
    raw_sites = [
        "${fn.summary}",
        "${f.summary}",
        "${item.summary}",
        "${fn.description",
        "${f.display_name}",
        "${item.display_name}",
        "${fn.domain_label}",
        "${item.domain_label}",
        "_escapeHtml(p.description)",
        "_escapeHtml(f.caveat)",
        "_escapeHtml(f.citation)",
    ]
    assert [s for s in raw_sites if s in SOURCE] == []
    # the one plain use left is an attribute set with setAttribute, which is not parsed as HTML
    uses = [line for line in SOURCE.splitlines() if "${fn.display_name}" in line]
    assert all("setAttribute(" in line for line in uses), uses
    assert SOURCE.count("_catalogueInline(") >= 8
    assert "_catalogueBlocksHtml(fn.description)" in SOURCE


def test_phone_width_rules() -> None:
    assert re.search(r"@media \(max-width: 600px\) \{[^}]*\.nav-gh \{ display: none; \}", CSS)
    assert re.search(
        r"@media \(max-width: 768px\) \{\s*\.hero-split \{ grid-template-columns: 1fr;", CSS
    )
    assert (
        'main [style*="grid-template-columns"] { grid-template-columns: minmax(0, 1fr) !important; }'
        in CSS
    )
    for page in sorted(PORTAL.glob("domain-*.html")):
        text = page.read_text(encoding="utf-8")
        assert 'class="hero-split"' in text, page.name
        assert "grid-template-columns:1fr auto" not in text, page.name

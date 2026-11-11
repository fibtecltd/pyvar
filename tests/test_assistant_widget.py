"""A static scan of the assistant widget (portal/assistant.js) and of how pyvar.js loads it.

Reasoning:
- The widget puts text written by a build (a model, then graders and a gate) into the page. It must do so only
  as text. The rules: no innerHTML / outerHTML / insertAdjacentHTML / document.write / eval / new Function /
  string timers, no inline event handlers, nothing sent to the server, no storage. A scan is crude but it is the
  check that a later edit cannot quietly break.
- The widget loads only when /public/config says it is enabled, so no HTML page may name assistant.js.
- No browser runs here; tests/test_assistant_api.py covers the server side, and the layout was checked by hand in
  Chromium (docs/assistant-phase0-results.md, 9.20).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PORTAL = REPO / "portal"
WIDGET = (PORTAL / "assistant.js").read_text()
PYVAR_JS = (PORTAL / "pyvar.js").read_text()
CSS = (PORTAL / "pyvar.css").read_text()


def code_only(source: str) -> str:
    """The JavaScript without comments and string contents' risk: comments removed (the file's own header
    mentions the banned names in order to ban them)."""
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$|(?<=\s)//\s.*$", "", without_block)


CODE = code_only(WIDGET)

BANNED = {
    "innerHTML": r"\binnerHTML\b",
    "outerHTML": r"\bouterHTML\b",
    "insertAdjacentHTML": r"\binsertAdjacentHTML\b",
    "document.write": r"\bdocument\s*\.\s*write(?:ln)?\b",
    "eval": r"\beval\s*\(",
    "new Function": r"\bnew\s+Function\b",
    "Function(": r"(?<![\w.])Function\s*\(",
    "setTimeout with a string": r"\bset(?:Timeout|Interval)\s*\(\s*['\"`]",
    "createContextualFragment": r"\bcreateContextualFragment\b",
    "srcdoc": r"\bsrcdoc\b",
    "an inline handler attribute": r"\bon[a-z]+\s*=\s*['\"]",
    "setAttribute on*": r"setAttribute\(\s*['\"]on",
    "javascript: url": r"javascript:",
}


def test_the_widget_uses_none_of_the_dangerous_apis() -> None:
    hits = {name: re.findall(pattern, CODE) for name, pattern in BANNED.items()}
    assert {name: found for name, found in hits.items() if found} == {}


def test_the_scan_would_catch_each_banned_pattern() -> None:
    samples = {
        "innerHTML": "el.innerHTML = x;",
        "outerHTML": "el.outerHTML = x;",
        "insertAdjacentHTML": "el.insertAdjacentHTML('beforeend', x)",
        "document.write": "document.write(x)",
        "eval": "eval(x)",
        "new Function": "new Function('return 1')",
        "setTimeout with a string": "setTimeout('go()', 1)",
        "an inline handler attribute": "markup = '<b onclick=\"go()\">'",
        "setAttribute on*": "el.setAttribute('onclick', x)",
        "javascript: url": "a.href = 'javascript:go()'",
    }
    for name, sample in samples.items():
        assert re.search(BANNED[name], code_only(sample)), name


def test_the_widget_only_reads_two_static_things_and_sends_nothing() -> None:
    assert len(re.findall(r"\bfetch\(", CODE)) == 1
    call = re.search(r"\bfetch\((.*?)\)\s*\.then", CODE, flags=re.DOTALL)
    assert call is not None
    assert "BASE" in call.group(1) and "credentials: 'omit'" in call.group(1)
    for option in ("method", "body", "headers"):
        assert option not in call.group(1)
    for forbidden in (
        "XMLHttpRequest",
        "sendBeacon",
        "WebSocket",
        "EventSource",
        "FormData",
        "POST",
    ):
        assert forbidden not in CODE, forbidden
    for forbidden in ("localStorage", "sessionStorage", "document.cookie", "indexedDB"):
        assert forbidden not in CODE, forbidden
    assert "BASE = '/assistant/bank/'" in CODE
    assert "location" not in CODE  # no navigation, no reading of the page's URL


def test_the_widget_writes_the_bank_text_only_as_text() -> None:
    assert CODE.count("textContent") >= 1 and "createTextNode" in CODE
    assert "appendChild(document.createTextNode(part))" in CODE


def test_the_widget_has_the_three_questions_the_label_and_a_live_region() -> None:
    for needle in (
        "'What it does'",
        "'When to use it'",
        "Compare with…",
        "From the pyvar catalogue",
        "aria-live",
        "aria-pressed",
        "type = 'button'",
    ):
        assert needle in CODE, needle


def test_no_page_names_the_widget_and_pyvar_js_loads_it_only_when_enabled() -> None:
    for page in PORTAL.glob("*.html"):
        assert "assistant.js" not in page.read_text(), page.name
    loader = "script.src = `${API_BASE}/assistant.js`"
    assert PYVAR_JS.count(loader) == 1
    assert PYVAR_JS.index("!publicConfig.assistant_enabled") < PYVAR_JS.index(loader)
    assert "/^[A-Za-z0-9._-]+$/.test(version)" in PYVAR_JS


def test_pyvar_js_leaves_a_slot_and_fires_the_event_the_widget_listens_for() -> None:
    assert 'id="assistantSlot"' in PYVAR_JS and 'data-fn="${fn.name}"' in PYVAR_JS
    assert "new CustomEvent('pyvar:tryit-open'" in PYVAR_JS
    assert "'pyvar:tryit-open'" in WIDGET


def test_the_stylesheet_respects_reduced_motion_and_a_narrow_screen() -> None:
    block = CSS[
        CSS.index("Assistant buttons in the Try-it panel") : CSS.index("/* ── Typography ── */")
    ]
    assert "prefers-reduced-motion: no-preference" in block
    assert block.index("animation:") > block.index("prefers-reduced-motion")
    assert "max-width: 600px" in block and ":focus-visible" in block
    assert "#" not in re.sub(
        r"/\*.*?\*/", "", block, flags=re.DOTALL
    )  # colours come from the portal's variables


# A bank answer may hold `code`, **bold** and "- " lists. inline() is run under node with a minimal stand-in
# for the DOM, so the rule "bank text only becomes text nodes, <code> or <strong>" is checked as behaviour.
_HARNESS = """
function node(tag) {
  return { tag: tag, children: [], className: '', textContent: '',
           appendChild: function (c) { this.children.push(c); return c; } };
}
var document = { createElement: node, createTextNode: function (t) { return { tag: '#text', textContent: t }; } };
function make(tag, cls, text) {
  var n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
%s
var lines = JSON.parse(require('fs').readFileSync(0, 'utf8'));
console.log(JSON.stringify(lines.map(function (line) {
  var p = node('p'); inline(p, line);
  return p.children.map(function (c) { return [c.tag, c.textContent]; });
})));
"""


def _run_inline(lines: list[str], tmp_path: Path) -> list[list[list[str]]]:
    match = re.search(r"  function inline\(parent, line\) \{.*?\n  \}\n", WIDGET, flags=re.DOTALL)
    assert match, "the widget has no inline() function"
    script = tmp_path / "inline_check.js"
    script.write_text(_HARNESS % match.group(0))
    node = shutil.which("node")
    assert node is not None
    done = subprocess.run(  # noqa: S603 - a fixed script, no user input
        [node, str(script)], input=json.dumps(lines), capture_output=True, text=True, check=True
    )
    parsed: list[list[list[str]]] = json.loads(done.stdout)
    return parsed


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_inline_turns_code_and_bold_into_nodes_and_everything_else_into_text(
    tmp_path: Path,
) -> None:
    out = _run_inline(
        [
            "**Lead:** use `weights` and a * b",
            "a stray ** marker",
            "no markup at all",
            "`a**b` stays code",
            "<b>x</b> then **y**",
        ],
        tmp_path,
    )
    assert out[0] == [
        ["strong", "Lead:"],
        ["#text", " use "],
        ["code", "weights"],
        ["#text", " and a * b"],
    ]
    assert out[1] == [["#text", "a stray ** marker"]]  # unpaired: shown as written
    assert out[2] == [["#text", "no markup at all"]]
    assert out[3] == [["code", "a**b"], ["#text", " stays code"]]
    assert out[4] == [["#text", "<b>x</b> then "], ["strong", "y"]]  # markup is never parsed

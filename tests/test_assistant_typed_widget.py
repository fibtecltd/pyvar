"""The typed-question box (portal/assistant-typed.js): what it sends, when, and how it shows what comes back.

Reasoning:
- This is the one piece of portal code that sends what a visitor TYPES, so its promises are pinned both ways. A source
  scan (like tests/test_assistant_widget.py's, which keeps the menu buttons a pure reader) shows what the file cannot
  do: no HTML sinks, no storage, no cookies, no other network calls, exactly one fetch. Then the REAL file runs under
  node with a fake DOM whose `innerHTML` throws and whose storage throws on any use, so what it does is checked as
  behaviour: nothing is sent until Ask is pressed; one POST with the question, the function name and at most three
  earlier turns; a Bearer header only for a plausible token in the key box; the answer, the example inputs and every
  server message are shown as text, never as HTML; each failure (401, 422, 429, 503, a network error, a reply of the
  wrong shape) gets a fixed message; the box never sends two questions at once.
- The page text it shows in the note must agree with the privacy policy (tests/test_assistant_privacy_terms.py pins
  the policy; the checks here pin the note's own words that the policy also says).
- No browser runs here; the layout was looked at in Chromium when the box was built (see the pull request).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
PORTAL = REPO / "portal"
SOURCE = (PORTAL / "assistant-typed.js").read_text(encoding="utf-8")
PYVAR_JS = (PORTAL / "pyvar.js").read_text(encoding="utf-8")
CSS = (PORTAL / "pyvar.css").read_text(encoding="utf-8")


def code_only(source: str) -> str:
    """The JavaScript without comments (the file's own header names the banned APIs in order to ban them)."""
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$|(?<=\s)//\s.*$", "", without_block)


CODE = code_only(SOURCE)

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


# ── what the file cannot do ─────────────────────────────────────────────────────


def test_it_uses_none_of_the_dangerous_apis() -> None:
    hits = {name: re.findall(pattern, CODE) for name, pattern in BANNED.items()}
    assert {name: found for name, found in hits.items() if found} == {}


def test_it_touches_no_storage_cookie_or_location_and_has_one_network_call() -> None:
    for forbidden in (
        "localStorage",
        "sessionStorage",
        "document.cookie",
        "indexedDB",
        "XMLHttpRequest",
        "sendBeacon",
        "WebSocket",
        "EventSource",
        "FormData",
    ):
        assert forbidden not in CODE, forbidden
    assert "location" not in CODE  # no navigation, and the page's URL is never read
    assert len(re.findall(r"\bfetch\(", CODE)) == 1
    assert "var ENDPOINT = '/api/v1/assistant/ask'" in CODE
    assert "fetch(ENDPOINT, options)" in CODE
    assert "method: 'POST'" in CODE and "credentials: 'omit'" in CODE


def test_it_reads_only_the_key_box_of_the_page() -> None:
    assert re.findall(r"getElementById\('([^']+)'\)", CODE) == [
        "tryitJwt",
        "assistantTypedSlot",
        "assistantTypedSlot",
    ]


def test_the_note_says_what_the_privacy_policy_says() -> None:
    needles = (
        "up to three earlier turns of this conversation",
        "this function\\u2019s name",
        "Anthropic\\u2019s Claude",
        "e-mail address, key or token",
        "from your computations or your account is sent",
        "a sample of answers is read by a second model",
        "Do not type personal or confidential information",
        "Answers can be wrong",
    )
    for needle in needles:
        assert needle in CODE, needle
    assert "link.href = '/privacy.html'" in CODE


def test_the_limits_equal_the_servers() -> None:
    from schemas.assistant import ANSWER_MAX, HISTORY_MAX, QUESTION_MAX

    for name, value in (
        ("QUESTION_MAX", QUESTION_MAX),
        ("ANSWER_MAX", ANSWER_MAX),
        ("HISTORY_MAX", HISTORY_MAX),
    ):
        assert re.search(rf"var {name} = {value};", CODE), name


# ── how pyvar.js loads it ───────────────────────────────────────────────────────


def test_no_page_names_the_script_and_pyvar_js_loads_it_only_when_typed_is_enabled() -> None:
    for page in PORTAL.glob("*.html"):
        assert "assistant-typed" not in page.read_text(encoding="utf-8"), page.name
    loader = "typed.src = `${API_BASE}/assistant-typed.js`"
    assert PYVAR_JS.count(loader) == 1
    gate = "publicConfig.assistant_typed_enabled === true"
    assert PYVAR_JS.index("!publicConfig.assistant_enabled") < PYVAR_JS.index(gate)
    assert PYVAR_JS.index(gate) < PYVAR_JS.index(loader)


def test_pyvar_js_leaves_the_typed_slot_next_to_the_menu_slot() -> None:
    slot = '<div id="assistantTypedSlot" class="assistant-slot" data-fn="${fn.name}"></div>'
    assert PYVAR_JS.count(slot) == 1
    assert PYVAR_JS.index('id="assistantSlot"') < PYVAR_JS.index(slot)
    assert "'pyvar:tryit-open'" in SOURCE


def test_the_stylesheet_has_the_box_and_no_hard_coded_colour() -> None:
    for selector in (
        ".assistant-typed-form",
        ".assistant-typed-input",
        ".assistant-typed-note",
        ".assistant-typed-json",
    ):
        assert selector in CSS, selector
    block = CSS[
        CSS.index("The typed box (portal/assistant-typed.js)") : CSS.index("/* ── Typography")
    ]
    assert "#" not in re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    assert ":focus-visible" in block and "max-width: 600px" in block


# ── the real file under node ────────────────────────────────────────────────────

HARNESS = r"""
const fs = require('fs');
const scenarios = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(process.argv[2], 'utf8');

function textOf(n) {
  if (typeof n === 'string') return n;
  if (n.tag === '#text') return n.data;
  return n._text + n.children.map(textOf).join('');
}
class El {
  constructor(tag) {
    this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {}; this.className = '';
    this._text = ''; this.value = ''; this.disabled = false; this.id = ''; this.dataset = {};
  }
  get firstChild() { return this.children[0] || null; }
  get isConnected() { return true; }
  appendChild(c) { this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return textOf(this); }
  set innerHTML(v) { throw new Error('innerHTML was written'); }
  get innerHTML() { throw new Error('innerHTML was read'); }
}
function walk(n, out) { out.push(n); (n.children || []).forEach((c) => walk(c, out)); return out; }
const throwing = (what) => new Proxy({}, { get() { throw new Error(what + ' was used'); }, set() { throw new Error(what + ' was used'); } });

async function settle(button) {
  for (let i = 0; i < 60; i++) { await new Promise((r) => setImmediate(r)); if (!button.disabled) return; }
}

async function run(sc) {
  const out = { fetches: [], texts: [], errors: [] };
  const listeners = {};
  const slot = sc.noSlot ? null : new El('div');
  if (slot) { slot.id = 'assistantTypedSlot'; slot.dataset.fn = sc.fn || 'historical_simulation_var'; }
  const keyBox = new El('input'); keyBox.value = sc.token === undefined ? '' : sc.token;
  let slotVisible = !sc.lateSlot;  // a panel that opens after the script has loaded
  const document = {
    currentScript: null,
    createElement: (t) => new El(t),
    createTextNode: (s) => ({ tag: '#text', data: String(s), children: [] }),
    getElementById: (id) => (id === 'assistantTypedSlot' ? (slotVisible ? slot : null) : id === 'tryitJwt' ? keyBox : null),
    addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
    get cookie() { throw new Error('document.cookie was used'); },
  };
  let call = 0;
  const fetchFn = async (url, options) => {
    out.fetches.push({ url, options: JSON.parse(JSON.stringify(options)) });
    const plan = sc.replies[Math.min(call, sc.replies.length - 1)]; call += 1;
    if (plan === 'reject') throw new TypeError('network down');
    if (plan === 'hang') return new Promise(() => {});
    return {
      ok: plan.status >= 200 && plan.status < 300, status: plan.status,
      headers: { get: (h) => (h.toLowerCase() === 'retry-after' && plan.retry !== undefined ? String(plan.retry) : null) },
      json: async () => { if (plan.badJson) throw new SyntaxError('bad json'); return plan.body; },
    };
  };
  const fn = new Function('document', 'fetch', 'localStorage', 'sessionStorage', 'location', 'window', source);
  fn(document, fetchFn, throwing('localStorage'), throwing('sessionStorage'), throwing('location'), throwing('window'));
  const open = () => {
    slotVisible = true;
    (listeners['pyvar:tryit-open'] || []).forEach((f) => f({ detail: { name: sc.eventName || (slot && slot.dataset.fn) } }));
  };
  open();
  if (!slot) return out;
  out.mounted = slot.children.length;
  if (!out.mounted) return out;  // another function's event: nothing to look at
  open();
  out.mountedAfterSecondOpen = slot.children.length;
  const all = walk(slot, []);
  const input = all.find((n) => n.tag === 'textarea');
  const button = all.find((n) => n.tag === 'button');
  const form = all.find((n) => n.tag === 'form');
  const answer = all.find((n) => n.attrs && n.attrs['aria-live'] === 'polite');
  out.beforeAsk = out.fetches.length;
  out.note = textOf(all.find((n) => (n.className || '').indexOf('assistant-typed-note') >= 0));
  out.inputMax = input.maxLength;
  out.hasLabel = all.some((n) => n.tag === 'label' && n.htmlFor === input.id);
  for (const question of sc.questions || []) {
    input.value = question;
    const ev = { prevented: false, preventDefault() { this.prevented = true; } };
    form.listeners.submit.forEach((f) => f(ev));
    out.prevented = ev.prevented;
    if (sc.doubleSubmit) form.listeners.submit.forEach((f) => f({ preventDefault() {} }));
    if (sc.hang) { out.disabledWhileBusy = button.disabled; out.busyAttr = answer.attrs['aria-busy']; return out; }
    await settle(button);
    out.texts.push(textOf(answer));
    out.inputAfter = input.value;
    out.tags = (out.tags || []).concat([walk(answer, []).map((n) => n.tag)]);
  }
  out.busyAfter = answer.attrs['aria-busy'];
  return out;
}

(async () => {
  const results = [];
  for (const sc of scenarios) {
    try { results.push(await run(sc)); } catch (e) { results.push({ crashed: String(e && e.message) }); }
  }
  console.log(JSON.stringify(results));
  process.exit(0);
})();
"""

LIVE = {
    "status": 200,
    "body": {
        "answer": "It takes `returns` and **confidence_level**.\n- first\n- second",
        "source": "live",
        "model_tier": "haiku",
        "functions": ["historical_simulation_var"],
        "suggested_parameters": {
            "function": "historical_simulation_var",
            "values": {"confidence_level": 0.99},
        },
        "request_id": "r1",
    },
}
STATIC = {
    "status": 200,
    "body": {
        "answer": "Fixed text.",
        "source": "static",
        "model_tier": "none",
        "functions": [],
        "suggested_parameters": None,
        "request_id": "r2",
    },
}
TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLWEifQ.c2lnbmF0dXJl"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run_scenarios(scenarios: list[dict[str, Any]], tmp_path: Path) -> list[dict[str, Any]]:
    script = tmp_path / "typed_harness.js"
    script.write_text(HARNESS, encoding="utf-8")
    node = shutil.which("node")
    assert node is not None
    done = subprocess.run(  # noqa: S603 - a fixed script and the repo's own file, no user input
        [node, str(script), str(PORTAL / "assistant-typed.js")],
        input=json.dumps(scenarios),
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    results: list[dict[str, Any]] = json.loads(done.stdout)
    for result in results:
        assert "crashed" not in result, result
    return results


def one(tmp_path: Path, **scenario: Any) -> dict[str, Any]:
    scenario.setdefault("replies", [LIVE])
    return run_scenarios([scenario], tmp_path)[0]


@needs_node
def test_it_mounts_once_into_its_own_slot_and_sends_nothing_until_asked(tmp_path: Path) -> None:
    out = one(tmp_path, questions=[])
    assert out["mounted"] == 1 and out["mountedAfterSecondOpen"] == 1
    assert out["beforeAsk"] == 0 and out["fetches"] == []
    assert out["inputMax"] == 500 and out["hasLabel"] is True
    assert "up to three earlier turns" in out["note"] and "Privacy Policy" in out["note"]


@needs_node
def test_it_does_nothing_without_its_slot_or_for_another_function(tmp_path: Path) -> None:
    assert one(tmp_path, noSlot=True)["fetches"] == []
    wrong = one(tmp_path, lateSlot=True, eventName="some_other_function", questions=[])
    assert wrong["mounted"] == 0  # the slot belongs to another panel: this event does not fill it


@needs_node
def test_a_question_is_one_post_with_the_function_and_no_history_the_first_time(
    tmp_path: Path,
) -> None:
    out = one(tmp_path, questions=["  What does it need?  "])
    (sent,) = out["fetches"]
    assert sent["url"] == "/api/v1/assistant/ask"
    assert sent["options"]["method"] == "POST" and sent["options"]["credentials"] == "omit"
    assert json.loads(sent["options"]["body"]) == {
        "question": "What does it need?",
        "function": "historical_simulation_var",
        "history": [],
    }
    assert (
        "Authorization" not in sent["options"]["headers"]
    )  # an empty key box: asking as a visitor
    assert out["prevented"] is True  # the form never navigates
    assert out["inputAfter"] == "" and out["busyAfter"] == "false"


@needs_node
def test_the_key_box_is_sent_as_a_bearer_token_only_when_it_looks_like_one(
    tmp_path: Path,
) -> None:
    good, with_space, key = (
        one(tmp_path, token=TOKEN, questions=["q"]),
        one(tmp_path, token="Paste your key here", questions=["q"]),
        one(tmp_path, token="pyvar_" + "a" * 43, questions=["q"]),
    )
    assert good["fetches"][0]["options"]["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert "Authorization" not in with_space["fetches"][0]["options"]["headers"]
    assert key["fetches"][0]["options"]["headers"]["Authorization"].startswith("Bearer pyvar_")


@needs_node
def test_history_holds_at_most_the_last_three_turns_and_resets_with_a_new_panel(
    tmp_path: Path,
) -> None:
    out = one(tmp_path, questions=["one", "two", "three", "four", "five"])
    bodies = [json.loads(call["options"]["body"]) for call in out["fetches"]]
    assert [len(b["history"]) for b in bodies] == [0, 1, 2, 3, 3]
    assert [t["q"] for t in bodies[4]["history"]] == ["two", "three", "four"]
    assert all(set(t) == {"q", "a"} for b in bodies for t in b["history"])
    again = one(tmp_path, questions=["fresh"])  # another panel: nothing carried over
    assert json.loads(again["fetches"][0]["options"]["body"])["history"] == []


@needs_node
def test_a_long_answer_goes_back_as_history_cut_to_the_servers_limit(tmp_path: Path) -> None:
    long_answer = {
        "status": 200,
        "body": {**LIVE["body"], "answer": "x" * 2400},  # type: ignore[dict-item]
    }
    out = one(tmp_path, replies=[long_answer, LIVE], questions=["one", "two"])
    history = json.loads(out["fetches"][1]["options"]["body"])["history"]
    assert len(history) == 1 and len(history[0]["a"]) == 1500  # a longer one would be a 422


@needs_node
def test_an_answer_is_shown_as_text_with_its_functions_example_and_label(tmp_path: Path) -> None:
    out = one(tmp_path, questions=["q"])
    (text,) = out["texts"]
    assert "You asked: q" in text and "It takes returns and confidence_level." in text
    assert "first" in text and "second" in text and "historical_simulation_var" in text
    assert "Checked example inputs for historical_simulation_var" in text
    assert '"confidence_level": 0.99' in text and "not filled in for you" in text
    assert "Written by an AI model (Claude)" in text and "It can be wrong" in text
    tags = out["tags"][0]
    assert "pre" in tags and "ul" in tags and "code" in tags and "strong" in tags
    static = one(tmp_path, replies=[STATIC], questions=["q"])["texts"][0]
    assert "From the pyvar catalogue" in static and "Written by an AI model" not in static


@needs_node
def test_hostile_text_from_the_server_stays_text(tmp_path: Path) -> None:
    hostile = "<img src=x onerror=alert(1)> **bold** `<script>alert(2)</script>`"
    reply = {
        "status": 200,
        "body": {
            "answer": hostile,
            "source": "live",
            "model_tier": "haiku",
            "functions": ["ok_name", "<b>bad</b>"],
            "suggested_parameters": {"function": "ok_name", "values": {"x": "<i>y</i>"}},
            "request_id": "r",
        },
    }
    out = one(tmp_path, replies=[reply], questions=["<b>q</b>"])
    (text,) = out[
        "texts"
    ]  # the fake DOM throws if innerHTML is ever used, so reaching here is the proof
    assert "<img src=x onerror=alert(1)>" in text and "<script>alert(2)</script>" in text
    assert "You asked: <b>q</b>" in text
    assert (
        "Functions: ok_name" in text and "<b>bad</b>" not in text
    )  # a name that is not a name is dropped


@needs_node
@pytest.mark.parametrize(
    "reply, fragments",
    [
        (
            {"status": 401, "body": {"detail": "x"}},
            ["Your key was not accepted", "Clear the key box"],
        ),
        ({"status": 422, "body": {"detail": []}}, ["could not be sent", "between 1 and 500"]),
        (
            {"status": 429, "body": {"detail": "x"}, "retry": 125},
            ["reached the limit", "in about 3 minutes"],
        ),
        (
            {"status": 429, "body": {"detail": "x"}, "retry": 7300},
            ["reached the limit", "in about 3 hours"],
        ),
        ({"status": 429, "body": {}, "retry": 30}, ["reached the limit", "in about 1 minute."]),
        ({"status": 429, "body": {}, "retry": 3000}, ["reached the limit", "in about 50 minutes."]),
        ({"status": 429, "body": {}, "retry": 3600}, ["reached the limit", "in about 1 hour."]),
        ({"status": 429, "body": {}}, ["reached the limit", "Try again."]),
        (
            {
                "status": 503,
                "body": {
                    "detail": {
                        "code": "assistant_closed",
                        "message": "Typed questions are open to a small group of accounts at the moment.",
                        "hint": "The buttons on each function page still work.",
                    }
                },
            },
            ["open to a small group of accounts", "The buttons on each function page still work."],
        ),
        (
            {"status": 503, "body": {"detail": "plain"}},
            ["not available right now", "buttons above"],
        ),
        ({"status": 500, "badJson": True}, ["not available right now", "buttons above"]),
        ({"status": 200, "body": {"answer": 5, "source": "live"}}, ["not available right now"]),
        ({"status": 200, "body": {"answer": "x", "source": "other"}}, ["not available right now"]),
        ({"status": 200, "body": [1, 2]}, ["not available right now"]),
        ("reject", ["not available right now", "buttons above"]),
    ],
)
def test_each_failure_gets_a_fixed_message_and_keeps_the_question(
    tmp_path: Path, reply: Any, fragments: list[str]
) -> None:
    out = one(tmp_path, replies=[reply], questions=["keep me"])
    (text,) = out["texts"]
    for fragment in fragments:
        assert fragment in text, (fragment, text)
    assert out["inputAfter"] == "keep me"  # the visitor can retry without retyping
    assert out["busyAfter"] == "false"
    assert "You asked" not in text


@needs_node
def test_a_failed_turn_is_not_remembered_as_history(tmp_path: Path) -> None:
    out = one(tmp_path, replies=["reject", LIVE], questions=["first", "second"])
    second = json.loads(out["fetches"][1]["options"]["body"])
    assert second["history"] == []


@needs_node
def test_an_empty_or_too_long_question_sends_nothing(tmp_path: Path) -> None:
    out = one(tmp_path, questions=["   ", "x" * 501])
    assert out["fetches"] == []
    assert "Type a question first" in out["texts"][0]
    assert "too long" in out["texts"][1]


@needs_node
def test_two_presses_while_a_question_is_pending_send_one_request(tmp_path: Path) -> None:
    out = one(tmp_path, replies=["hang"], questions=["q"], doubleSubmit=True, hang=True)
    assert len(out["fetches"]) == 1
    assert out["disabledWhileBusy"] is True and out["busyAttr"] == "true"

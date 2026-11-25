"""The dashboard's "Signed in as <address>" line (portal/pyvar.js, issue #454, docs/plan-dashboard-signed-in-account.md).

Reasoning:
- The address comes from GET /auth/me and must reach the page as TEXT and nowhere else: not as HTML, not in localStorage,
  not in the token. A source scan alone cannot show that, so these tests run the real dashboard code (from `_h` to the end
  of `renderKeyManager`) under node, with a fake DOM whose `innerHTML` throws when it is read or written and a
  `localStorage` that throws on any use. The same fake DOM then shows that a failing call, or an account with no address,
  leaves the rest of the dashboard (the plan text and the keys table) as it was.
- No browser runs here; the page was also looked at in Chromium when the change was made (see the pull request). The
  precedent for running pieces of pyvar.js under node is tests/test_portal_catalogue_text.py.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "portal"
SOURCE = (PORTAL / "pyvar.js").read_text(encoding="utf-8")
ADDRESS = "ada.lovelace@uni.example"
HOSTILE = "<img src=x onerror=alert(1)>@x.example"

HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const API_BASE = 'https://api.example';
let calls = [];
class FakeEl {
  constructor(tag) { this.tag = tag; this.className = ''; this.attrs = {}; this.children = []; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener() {}
  append(...c) { this.children.push(...c); }
  replaceChildren(...c) { this.children = c; }
  set innerHTML(v) { throw new Error('innerHTML was written'); }
  get innerHTML() { throw new Error('innerHTML was read'); }
}
const document = {
  createElement: (t) => new FakeEl(t),
  createTextNode: (s) => String(s),
};
const localStorage = {
  getItem() { throw new Error('localStorage was read'); },
  setItem() { throw new Error('localStorage was written'); },
  removeItem() { throw new Error('localStorage was changed'); },
};
const window = { confirm: () => false, location: { search: '' } };
const navigator = {};
let fetchImpl = null;
function fetch(...a) { return fetchImpl(...a); }
function mkRes(status, body, badJson) {
  return { ok: status >= 200 && status < 300, status,
           json: async () => { if (badJson) throw new SyntaxError('bad json'); return body; } };
}
function textOf(n) { return typeof n === 'string' ? n : n.children.map(textOf).join(''); }
function summary(n) {
  return typeof n === 'string'
    ? { text: n }
    : { tag: n.tag, cls: n.className || n.attrs.class || '', text: textOf(n).slice(0, 120),
        kids: n.children.map((c) => (typeof c === 'string' ? c : c.tag)) };
}

__SOURCE__

(async () => {
  const out = [];
  for (const scn of input) {
    calls = [];
    fetchImpl = async (url, opts = {}) => {
      calls.push({ url, method: opts.method || 'GET', auth: (opts.headers || {}).Authorization,
                   body: opts.body === undefined ? null : opts.body });
      if (url.endsWith('/api/v1/auth/me')) {
        if (scn.me.throws) throw new Error('network down');
        return mkRes(scn.me.status, scn.me.body, scn.me.badJson);
      }
      if (url.endsWith('/api/v1/auth/api-keys')) return mkRes(200, { keys: scn.keys });
      throw new Error('unexpected url ' + url);
    };
    const direct = await _signedInAs('tok');
    const directCalls = calls.slice();
    calls = [];
    const card = new FakeEl('div');
    await renderKeyManager(card, 'tok', 'free', null, null);
    out.push({ name: scn.name, direct, directCalls, calls, card: card.children.map(summary),
               cardClass: card.className });
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""

KEY = {
    "id": "k1",
    "name": "laptop",
    "prefix": "pyvar_ab12cd",
    "created_at": "2026-11-01T00:00:00Z",
    "expires_at": "2027-11-01T00:00:00Z",
    "last_used_at": None,
    "revoked_at": None,
}


def scenario(name: str, me: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "me": me, "keys": [KEY]}


SCENARIOS = [
    scenario("ok", {"status": 200, "body": {"email": ADDRESS, "tier": "free"}}),
    scenario("hostile", {"status": 200, "body": {"email": HOSTILE, "tier": "free"}}),
    scenario("unauthorized", {"status": 401, "body": {"detail": "x"}}),
    scenario("forbidden", {"status": 403, "body": {"detail": "x"}}),
    scenario("unavailable", {"status": 503, "body": {}}),
    scenario("network", {"throws": True}),
    scenario("bad json", {"status": 200, "body": None, "badJson": True}),
    scenario("erased", {"status": 200, "body": {"email": None, "tier": "free"}}),
    scenario("empty", {"status": 200, "body": {"email": "", "tier": "free"}}),
    scenario("number", {"status": 200, "body": {"email": 12345, "tier": "free"}}),
    scenario("object", {"status": 200, "body": {"email": {"a": 1}, "tier": "free"}}),
    scenario("no field", {"status": 200, "body": {"tier": "free"}}),
]


@pytest.fixture(scope="module")
def results() -> dict[str, dict[str, Any]]:
    start = SOURCE.index("// Tiny DOM builder")
    end = SOURCE.index("// ── Search (P8 Task 4)")
    node = shutil.which("node")
    assert node is not None, "node is needed to run the dashboard code"
    done = subprocess.run(  # noqa: S603 - a fixed script, no user input
        [node, "-e", HARNESS.replace("__SOURCE__", SOURCE[start:end])],
        input=json.dumps(SCENARIOS),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return {r["name"]: r for r in json.loads(done.stdout)}


def account_lines(card: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in card if "dash-account" in c.get("cls", "")]


# ── the line itself ─────────────────────────────────────────────────────────────


def test_the_address_is_shown_second_after_the_title_and_before_the_plan_text(results) -> None:
    card = results["ok"]["card"]
    assert card[0]["text"] == "Your API keys"
    assert card[1]["cls"] == "dash-body dash-account"
    assert card[1]["text"] == f"Signed in as {ADDRESS}"
    assert card[2]["text"].startswith("Free tier.")


def test_the_session_is_sent_as_a_bearer_token_to_the_read_only_route_and_nothing_else_is_asked(
    results,
) -> None:
    direct = results["ok"]["directCalls"]
    assert direct == [
        {
            "url": "https://api.example/api/v1/auth/me",
            "method": "GET",
            "auth": "Bearer tok",
            "body": None,
        }
    ]
    page = results["ok"]["calls"]
    assert {c["url"] for c in page} == {
        "https://api.example/api/v1/auth/me",
        "https://api.example/api/v1/auth/api-keys",
    }
    assert all(c["method"] == "GET" and c["auth"] == "Bearer tok" for c in page)


def test_the_address_goes_in_as_one_text_child_never_as_html(results) -> None:
    # The fake DOM throws if innerHTML is read or written, so reaching here means it was not; and the hostile address is
    # kept as a plain string child (a text node in a real DOM), not parsed.
    card = results["hostile"]["card"]
    line = account_lines(card)[0]
    assert line["kids"] == [f"Signed in as {HOSTILE}"]
    assert line["text"] == f"Signed in as {HOSTILE}"


# ── when there is nothing to show ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "unauthorized",
        "forbidden",
        "unavailable",
        "network",
        "bad json",
        "erased",
        "empty",
        "number",
        "object",
        "no field",
    ],
)
def test_a_failed_call_or_an_account_without_an_address_shows_no_line(results, name: str) -> None:
    result = results[name]
    assert result["direct"] is None
    assert account_lines(result["card"]) == []


@pytest.mark.parametrize("name", ["unauthorized", "network", "bad json", "erased", "object"])
def test_the_rest_of_the_dashboard_is_as_it_was_when_the_line_is_missing(
    results, name: str
) -> None:
    card = results[name]["card"]
    assert card[0]["text"] == "Your API keys"
    assert card[1]["text"].startswith("Free tier.")  # the plan text follows the title directly
    # The keys table is still there, inside its scroll box (see tests/test_dashboard_phone_width.py); never bare in the card.
    boxes = [c for c in card if "key-table-wrap" in c.get("cls", "")]
    assert len(boxes) == 1 and boxes[0]["kids"] == ["table"]
    assert not any(c.get("tag") == "table" for c in card)
    assert any("Upgrade to Pro" in c.get("text", "") or c.get("tag") == "button" for c in card)
    assert results[name]["cardClass"] == "dash-card wide"


# ── nothing is stored, nothing is parsed ────────────────────────────────────────


def new_block() -> str:
    return SOURCE[SOURCE.index("// <account-line>") : SOURCE.index("// </account-line>")]


@pytest.mark.parametrize(
    "forbidden",
    ["innerHTML", "outerHTML", "insertAdjacentHTML", "localStorage", "sessionStorage", "cookie"],
)
def test_the_new_code_never_touches_html_or_storage(forbidden: str) -> None:
    code = re.sub(r"//[^\n]*", "", new_block())  # the comments say what it does not do
    assert forbidden not in code


def test_no_stored_value_is_built_from_an_address() -> None:
    assert not re.search(r"setItem\([^)]*(address|email)", SOURCE)


def test_the_dashboard_asks_for_the_address_when_it_draws_the_key_manager() -> None:
    body = SOURCE[SOURCE.index("async function renderKeyManager") :]
    body = body[: body.index("\n}\n")]
    assert "_signedInAs(session)" in body and "_accountLine(address)" in body

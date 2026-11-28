"""The code in the home page's terminal panel runs, against the real client, as written.

Found on 2026-11-28: the panel imported `pyvar` (an unrelated package on PyPI, not this one), built a `VaRClient` the
client does not have, passed `confidence=` (the keyword is `confidence_level`), and read the result as attributes
(`result.var_abs`, `result.runtime_ms`) when `client.var.compute()` returns a dict whose engine-time field is
`duration_ms`. Nothing ran it, so nothing noticed. Now:
- the code is read out of portal/index.html (scripts/check_home_snippet.py, which an operator also runs against dev);
- it is run unchanged through the real pyvar_client, over a transport that answers like the API: the request is validated
  by the server's own `VaRRequest`, the job is computed by the real engine, and the result is the server's own
  `VaRResult` model, so a wrong keyword, a wrong URL or a wrong field name fails here;
- the values the panel shows (before the page replaces them with the latest published result) are what the code prints;
- the page's script writes the live values in the way Python prints them, and the number of paths as a Python literal;
- no page of the portal suggests `import pyvar`, `from pyvar import` or `pip install pyvar` (the PyPI package of that name
  is an unrelated one), or the old `VaRClient`.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest

from engine.montecarlo import run_monte_carlo_var
from schemas.var import JobResultResponse, JobStatus, VaRRequest, VaRResult

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / "portal"


def _load_script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "check_home_snippet", ROOT / "scripts" / "check_home_snippet.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snippet = _load_script()


# ── a transport that answers like the API ──────────────────────────────────────────────────────────────


class FakeApi:
    """POST /api/v1/var/compute and GET /api/v1/var/result/{id}, built from the server's own models and engine."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, str | None]] = []
        self.bodies: list[dict[str, Any]] = []
        self.results: dict[str, dict[str, Any]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(
            (request.method, request.url.path, request.headers.get("authorization"))
        )
        if request.method == "POST" and request.url.path == "/api/v1/var/compute":
            body = json.loads(request.content)
            self.bodies.append(body)
            try:
                job = VaRRequest.model_validate(body)
            except ValueError as exc:  # pydantic's ValidationError is a ValueError
                return httpx.Response(422, json={"detail": str(exc)})
            started = time.perf_counter()
            computed = run_monte_carlo_var(
                returns=np.array(job.returns, dtype=np.float64),
                portfolio_value=job.portfolio_value,
                confidence_level=job.confidence_level,
                horizon_days=job.horizon_days,
                n_simulations=job.n_simulations,
                seed=job.seed,
            )
            computed["duration_ms"] = int((time.perf_counter() - started) * 1000)
            task_id = f"task-{len(self.results) + 1}"
            self.results[task_id] = computed
            return httpx.Response(
                202, json={"task_id": task_id, "status": "pending", "message": "queued"}
            )
        match = re.fullmatch(r"/api/v1/var/result/(.+)", request.url.path)
        if request.method == "GET" and match and match.group(1) in self.results:
            task_id = match.group(1)
            done = JobResultResponse(
                task_id=task_id,
                status=JobStatus.SUCCESS,
                result=VaRResult(**self.results[task_id]),
            )
            return httpx.Response(200, json=done.model_dump(mode="json"))
        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the home-page snippet test must not touch the network")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


# ── what the page shows ────────────────────────────────────────────────────────────────────────────────


def test_the_panel_shows_the_code_the_client_documents() -> None:
    code = snippet.snippet_code()
    tree = ast.parse(code)
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert len(imports) == 1 and isinstance(imports[0], ast.ImportFrom)
    assert (imports[0].module, [a.name for a in imports[0].names]) == ("pyvar_client", ["Client"])
    calls = {
        node.func.attr: {
            k.arg: ast.literal_eval(k.value) for k in node.keywords if k.arg != "returns"
        }
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert calls["compute"] == {
        "portfolio_value": 1_000_000,
        "confidence_level": 0.99,
        "n_simulations": 1_000,
    }
    # the key is a placeholder in the real key's own form ("pyvar_" then characters), never a real one
    client_call = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "Client"
    )
    assert [ast.literal_eval(k.value) for k in client_call.keywords if k.arg == "api_key"] == [
        "pyvar_..."
    ]


def test_the_fields_the_panel_reads_are_fields_of_the_servers_result() -> None:
    tree = ast.parse(snippet.snippet_code())
    read = [
        n.slice.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Subscript)
        and isinstance(n.slice, ast.Constant)
        and isinstance(n.slice.value, str)
    ]
    assert read == ["var_abs", "cvar_abs", "duration_ms"]
    assert set(read) <= set(VaRResult.model_fields)


# ── running it ─────────────────────────────────────────────────────────────────────────────────────────


def test_the_snippet_runs_through_the_real_client_and_prints_what_the_panel_shows() -> None:
    api = FakeApi()
    printed = snippet.run_snippet(
        snippet.snippet_code(),
        transport=httpx.MockTransport(api),
    )
    assert snippet.compare(printed, snippet.shown_outputs()) == [], (
        printed,
        snippet.shown_outputs(),
    )
    # one job, submitted with the key the snippet gave and the names the server's model takes
    assert [m for m, p, _ in api.requests][:2] == ["POST", "GET"]
    assert api.requests[0][2] == "Bearer pyvar_..."
    assert api.bodies == [
        {
            "portfolio_value": 1_000_000,
            "returns": snippet.demo_returns(),
            "confidence_level": 0.99,
            "horizon_days": 1,
            "seed": 42,
            "n_simulations": 1_000,
        }
    ]


def test_a_snippet_with_the_old_mistakes_fails_here() -> None:
    api = FakeApi()
    for old in (
        "from pyvar import VaRClient\nclient = VaRClient(api_key='pv_...')\n",  # no such package or class
        "from pyvar_client import Client\nclient = Client(api_key='pyvar_...')\n"
        "result = client.var.compute(portfolio_value=1_000_000, returns=returns, confidence=0.99)\n",
        "from pyvar_client import Client\nclient = Client(api_key='pyvar_...')\n"
        "result = client.var.compute(portfolio_value=1_000_000, returns=returns)\nprint(result.var_abs)\n",
        "from pyvar_client import Client\nclient = Client(api_key='pyvar_...')\n"
        "result = client.var.compute(portfolio_value=1_000_000, returns=returns)\nprint(result['runtime_ms'])\n",
    ):
        with pytest.raises((ImportError, ModuleNotFoundError, TypeError, AttributeError, KeyError)):
            snippet.run_snippet(old, transport=httpx.MockTransport(api))


def test_the_comparison_flags_a_value_that_differs_and_a_duration_that_is_not_a_number() -> None:
    assert snippet.compare(["1", "2", "3"], ["1", "2", "999"]) == []  # the engine time varies
    assert snippet.compare(["1", "9", "3"], ["1", "2", "3"]) == [
        "line 2: printed '9', the panel shows '2'"
    ]
    assert "not a whole number" in snippet.compare(["1", "2", "x"], ["1", "2", "3"])[0]
    assert "printed 2 lines" in snippet.compare(["1", "2"], ["1", "2", "3"])[0]


# ── the page's script writes the live values the way Python prints them ────────────────────────────────

# A real result, as the live dev API returned it for this exact call and as the publisher wrote it to
# /public/demo-result.json (fetched 2026-11-28T09:05Z).
REAL_DEMO_RESULT = {
    "computed_at": "2026-11-28T09:05:55.379221+00:00",
    "request": {
        "portfolio_value": 1000000.0,
        "confidence_level": 0.99,
        "horizon_days": 1,
        "n_simulations": 1000,
    },
    "result": {
        "var_abs": 19762.04,
        "var_pct": 0.019762,
        "cvar_abs": 23040.6,
        "cvar_pct": 0.023041,
        "mu": -0.00094833,
        "sigma": 0.00885811,
    },
    "runtime_ms": 3187,
}

HYDRATE = r"""
const fs = require('fs'), vm = require('vm');
const noop = () => {};
const el = new Proxy(function () {}, {
  get: (t, k) => (k === 'style' || k === 'classList' || k === 'dataset')
    ? new Proxy({}, { get: () => noop, set: () => true }) : (k === Symbol.toPrimitive ? () => '' : noop),
  set: () => true, apply: () => el });
const hooks = {};
const body = { querySelector: (sel) => { const m = /data-demo="([a-z_]+)"/.exec(sel);
  return m ? (hooks[m[1]] = hooks[m[1]] || { textContent: '' }) : null; } };
const fetched = [];
const ctx = {
  console,
  document: { addEventListener: noop, getElementById: () => null,
    querySelector: (s) => (s === '.terminal-body' ? body : null), querySelectorAll: () => [],
    createElement: () => el, readyState: 'loading', write: noop, body: el, documentElement: el, head: el },
  window: { addEventListener: noop, location: { search: '', hash: '', pathname: '/', href: '' },
    history: { replaceState: noop }, matchMedia: () => ({ matches: false, addEventListener: noop }) },
  localStorage: { getItem: () => null, setItem: noop }, sessionStorage: { getItem: () => null, setItem: noop },
  fetch: (url) => { fetched.push(String(url));
    return Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(process.argv[3])) }); },
  navigator: { clipboard: {} }, setTimeout: noop, IntersectionObserver: function () { this.observe = noop; },
  location: { search: '', hash: '', pathname: '/' }, URLSearchParams, URL };
ctx.window.document = ctx.document;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8') + '\n;globalThis.__run = initTerminalDemo;', ctx);
ctx.__run().then(() => {
  const out = {}; for (const k of Object.keys(hooks)) out[k] = hooks[k].textContent;
  console.log(JSON.stringify({ hooks: out, fetched }));
});
"""

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


@needs_node
def test_the_live_values_are_written_as_python_prints_them(tmp_path: Path) -> None:
    script = tmp_path / "hydrate.js"
    script.write_text(HYDRATE, encoding="utf-8")
    node = shutil.which("node")
    assert node is not None
    done = subprocess.run(  # noqa: S603 - a fixed script and the repo's own file, no user input
        [node, str(script), str(PORTAL / "pyvar.js"), json.dumps(REAL_DEMO_RESULT)],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    out = json.loads(done.stdout)
    hooks = out["hooks"]
    assert out["fetched"] and out["fetched"][0].endswith("/demo-result.json")
    assert hooks["var_abs"] == repr(REAL_DEMO_RESULT["result"]["var_abs"]) == "19762.04"
    assert hooks["cvar_abs"] == repr(REAL_DEMO_RESULT["result"]["cvar_abs"]) == "23040.6"
    assert str(hooks["runtime_ms"]) == "3187"  # the engine time, as the publisher recorded it
    assert hooks["var_note"] == "# £19,762 (99% VaR)"
    assert hooks["cvar_note"] == "# £23,041 (CVaR/ES)"
    # the number of paths sits inside the code (n_simulations=...), so it must be a Python integer literal
    assert ast.literal_eval(hooks["n_simulations"]) == 1000 and hooks["n_simulations"] == "1_000"


def test_the_static_values_are_the_ones_the_real_run_gave() -> None:
    """Before the page's script replaces them, the panel shows the real result of this call (var_abs and cvar_abs are
    the same on every run: the series and the seed are fixed)."""
    shown = snippet.shown_outputs()
    assert shown[:2] == [
        repr(REAL_DEMO_RESULT["result"]["var_abs"]),
        repr(REAL_DEMO_RESULT["result"]["cvar_abs"]),
    ]
    assert shown[2].isdigit()


# ── no page suggests the wrong package ─────────────────────────────────────────────────────────────────

WRONG = [
    re.compile(r"\bfrom\s+pyvar\s+import\b"),
    re.compile(
        r"\bimport\s+pyvar(?![\w.-])"
    ),  # `import pyvar_client` and `import pyvar.x` are other things
    re.compile(
        r"\bpip3?\s+install\s+(?:-\S+\s+)*[\"']?pyvar(?![\w.-])"
    ),  # `pip install pyvar-client` is the right one
    re.compile(r"\bVaRClient\b"),
]


def portal_text_files() -> list[Path]:
    files = [
        p
        for p in sorted(PORTAL.rglob("*"))
        if p.suffix in {".html", ".js", ".md", ".txt", ".json", ".xml"}
        and "vendor" not in p.parts
        and "bank" not in p.parts
    ]
    assert len(files) > 20
    return files


def test_no_portal_page_suggests_import_pyvar_or_pip_install_pyvar() -> None:
    """The PyPI package named `pyvar` is an unrelated one (Variscite's); this project's is `pyvar-client`, imported as
    `pyvar_client`. A page that told a visitor otherwise would send them to install somebody else's code.
    """
    found = [
        f"{path.relative_to(ROOT)}: {match.group(0)!r}"
        for path in portal_text_files()
        for pattern in WRONG
        for match in pattern.finditer(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert found == []


def test_the_pattern_catches_the_wrong_suggestions_and_lets_the_right_ones_through() -> None:
    bad = [
        "import pyvar",
        "from pyvar import VaRClient",
        "pip install pyvar",
        "pip3 install -U pyvar",
        'pip install "pyvar',
    ]
    good = [
        "pip install pyvar-client",
        "import pyvar_client",
        "from pyvar_client import Client",
        "pyvar.com",
        "pip install pyvar_client",
    ]
    assert all(any(p.search(s) for p in WRONG) for s in bad)
    assert not any(p.search(s) for p in WRONG for s in good)

"""tests/test_main.py — MCP server list_tools/call_tool handler tests.

Exercises build_server()'s registered handlers directly (the same handlers
mcp.server.lowlevel.Server dispatches to over stdio in a real run) -- no
stdio transport, no real network calls (urlopen is mocked wherever a named
tool would actually reach the pyvar API).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import mcp.types as types
import pytest

from pyvar_mcp import __version__
from pyvar_mcp.main import build_server


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("PYVAR_API_KEY", "test-key")
    return build_server()


def test_server_tells_mcp_clients_its_name_and_version(server):
    # The initialize reply's serverInfo is built from these options. It used to carry an empty
    # version, so a client could not tell which pyvar-mcp it was talking to.
    options = server.create_initialization_options()

    assert options.server_name == "pyvar-mcp"
    assert options.server_version == __version__
    assert options.server_version != ""


def _list_tools_handler(server):
    return server.get_request_handler("tools/list").handler


def _call_tool_handler(server):
    return server.get_request_handler("tools/call").handler


@pytest.mark.asyncio
async def test_list_tools_includes_generic_pair_and_named_tools(server):
    result = await _list_tools_handler(server)(None, None)

    names = [t.name for t in result.tools]
    assert "list_pyvar_functions" in names
    assert "call_pyvar_function" in names
    assert "alm_stress_test" in names
    assert len(result.tools) == 385 + 2


@pytest.mark.asyncio
async def test_generic_pair_tools_are_listed_first(server):
    result = await _list_tools_handler(server)(None, None)

    assert result.tools[0].name == "list_pyvar_functions"
    assert result.tools[1].name == "call_pyvar_function"


@pytest.mark.asyncio
async def test_list_pyvar_functions_without_domain_returns_all(server):
    call_tool = _call_tool_handler(server)
    params = types.CallToolRequestParams(name="list_pyvar_functions", arguments={})

    result = await call_tool(None, params)

    data = json.loads(result.content[0].text)
    assert result.is_error is not True
    assert len(data["functions"]) == 385


@pytest.mark.asyncio
async def test_list_pyvar_functions_with_domain_filters(server):
    call_tool = _call_tool_handler(server)
    params = types.CallToolRequestParams(name="list_pyvar_functions", arguments={"domain": "alm"})

    result = await call_tool(None, params)

    data = json.loads(result.content[0].text)
    assert all(f["domain"] == "alm" for f in data["functions"])


@pytest.mark.asyncio
async def test_call_pyvar_function_unknown_function_returns_error_not_exception(server):
    call_tool = _call_tool_handler(server)
    params = types.CallToolRequestParams(
        name="call_pyvar_function",
        arguments={"domain": "alm", "function_name": "does_not_exist", "params": {}},
    )

    result = await call_tool(None, params)

    assert result.is_error is True
    assert "Unknown function" in result.content[0].text


@pytest.mark.asyncio
async def test_call_pyvar_function_missing_required_param_never_calls_api(server):
    call_tool = _call_tool_handler(server)
    params = types.CallToolRequestParams(
        name="call_pyvar_function",
        arguments={"domain": "alm", "function_name": "alm_stress_test", "params": {}},
    )

    with patch("pyvar_mcp.client.urllib.request.urlopen") as mock_urlopen:
        result = await call_tool(None, params)

    mock_urlopen.assert_not_called()
    assert result.is_error is True
    assert "Missing required parameter" in result.content[0].text


@pytest.mark.asyncio
async def test_call_pyvar_function_dispatches_to_the_correct_endpoint(server):
    call_tool = _call_tool_handler(server)
    params = types.CallToolRequestParams(
        name="call_pyvar_function",
        arguments={
            "domain": "alm",
            "function_name": "alm_stress_test",
            "params": {
                "net_cashflows": [1.0],
                "times": [1.0],
                "base_rates": [0.01],
                "tier1_capital": 1_000_000.0,
            },
        },
    )

    with patch("pyvar_mcp.client.urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps({"delta_eve": -14_200_000.0}).encode()
        result = await call_tool(None, params)

    request = mock_urlopen.call_args[0][0]
    assert request.full_url.endswith("/api/v1/alm/alm_stress_test")
    assert result.is_error is not True
    assert json.loads(result.content[0].text) == {"delta_eve": -14_200_000.0}


@pytest.mark.asyncio
async def test_named_tool_call_reaches_the_same_endpoint_as_call_pyvar_function(server):
    call_tool = _call_tool_handler(server)
    params = types.CallToolRequestParams(
        name="alm_stress_test",
        arguments={
            "net_cashflows": [1.0],
            "times": [1.0],
            "base_rates": [0.01],
            "tier1_capital": 1_000_000.0,
        },
    )

    with patch("pyvar_mcp.client.urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps({"delta_eve": -14_200_000.0}).encode()
        result = await call_tool(None, params)

    request = mock_urlopen.call_args[0][0]
    assert request.full_url.endswith("/api/v1/alm/alm_stress_test")
    assert result.is_error is not True


@pytest.mark.asyncio
async def test_named_tool_call_surfaces_api_error_without_raising(server):
    import urllib.error
    from unittest.mock import MagicMock

    call_tool = _call_tool_handler(server)
    params = types.CallToolRequestParams(
        name="alm_stress_test",
        arguments={
            "net_cashflows": [1.0],
            "times": [1.0],
            "base_rates": [0.01],
            "tier1_capital": 1_000_000.0,
        },
    )
    http_error = urllib.error.HTTPError(
        url="https://www.pyvar.com/api/v1/alm/alm_stress_test",
        code=403,
        msg="Forbidden",
        hdrs=None,
        fp=MagicMock(read=lambda: b'{"detail": "tier cap exceeded"}'),
    )

    with patch("pyvar_mcp.client.urllib.request.urlopen", side_effect=http_error):
        result = await call_tool(None, params)

    assert result.is_error is True
    assert "403" in result.content[0].text
    assert "tier cap exceeded" in result.content[0].text


@pytest.mark.asyncio
async def test_unknown_tool_name_returns_error_not_exception(server):
    call_tool = _call_tool_handler(server)
    params = types.CallToolRequestParams(name="totally_made_up_tool", arguments={})

    result = await call_tool(None, params)

    assert result.is_error is True
    assert "Unknown tool" in result.content[0].text


# ── no key: the trial ─────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def keyless_server(monkeypatch, tmp_path):
    monkeypatch.delenv("PYVAR_API_KEY", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    return build_server()


@pytest.mark.asyncio
async def test_a_server_with_no_key_starts_and_lists_tools_without_the_network_or_a_file(
    keyless_server, tmp_path
):
    with patch("pyvar_mcp.trial._post", side_effect=AssertionError("no network")):
        with patch("pyvar_mcp.client.urllib.request.urlopen", side_effect=AssertionError("no")):
            tools = await _list_tools_handler(keyless_server)(None, None)
            listing = await _call_tool_handler(keyless_server)(
                None, types.CallToolRequestParams(name="list_pyvar_functions", arguments={})
            )

    assert len(tools.tools) == 385 + 2
    assert listing.is_error is not True
    assert not (tmp_path / "data").exists()  # nothing is written until a call needs a ticket


@pytest.mark.asyncio
async def test_without_a_key_the_listing_marks_the_thirty_trial_functions(keyless_server):
    result = await _call_tool_handler(keyless_server)(
        None, types.CallToolRequestParams(name="list_pyvar_functions", arguments={})
    )

    functions = json.loads(result.content[0].text)["functions"]
    marked = [f["function_name"] for f in functions if f["available_without_key"]]
    assert len(marked) == 30 and "parametric_delta_normal_var" in marked
    assert all("available_without_key" in f for f in functions)


@pytest.mark.asyncio
async def test_with_a_key_the_listing_is_unchanged(server):
    result = await _call_tool_handler(server)(
        None, types.CallToolRequestParams(name="list_pyvar_functions", arguments={})
    )

    functions = json.loads(result.content[0].text)["functions"]
    assert all("available_without_key" not in f for f in functions)


@pytest.mark.asyncio
async def test_the_listing_tool_tells_the_model_what_the_mark_means(keyless_server):
    tools = (await _list_tools_handler(keyless_server)(None, None)).tools

    assert "available_without_key" in tools[0].description


@pytest.mark.asyncio
@pytest.mark.parametrize("via", ["named", "generic"])
async def test_without_a_key_a_function_off_the_list_comes_back_as_an_error_result(
    keyless_server, via
):
    entry = catalogue_entry("historical_simulation_var")
    arguments = {name: 1 for name in entry["input_schema"].get("required", [])}
    if via == "named":
        params = types.CallToolRequestParams(name="historical_simulation_var", arguments=arguments)
    else:
        params = types.CallToolRequestParams(
            name="call_pyvar_function",
            arguments={
                "domain": "market-risk",
                "function_name": "historical_simulation_var",
                "params": arguments,
            },
        )

    with patch("pyvar_mcp.trial._post", side_effect=AssertionError("no network")):
        result = await _call_tool_handler(keyless_server)(None, params)

    assert result.is_error is True
    assert "free pyvar API key" in result.content[0].text
    assert "https://www.pyvar.com#get-api-key" in result.content[0].text


def catalogue_entry(function_name):
    from pyvar_mcp import catalogue

    return next(e for e in catalogue.all_functions() if e["function_name"] == function_name)


def _trial_script():
    answers = [
        (200, {}, json.dumps({"challenge": "id.1999999999.4.sig", "bits": 4})),
        (200, {}, json.dumps({"ticket": "tkn", "expires_at": 4_000_000_000})),
        (200, {}, json.dumps({"var_abs": 12.5})),
    ]
    seen = []

    def post(url, payload, bearer=None):
        seen.append((url.rsplit("/", 1)[-1], bearer))
        return answers.pop(0)

    return post, seen


@pytest.mark.asyncio
async def test_without_a_key_a_trial_function_runs_and_the_ticket_is_kept_privately(
    keyless_server, tmp_path
):
    entry = catalogue_entry("parametric_delta_normal_var")
    arguments = {name: 1 for name in entry["input_schema"].get("required", [])}
    post, seen = _trial_script()

    with patch("pyvar_mcp.trial._post", post):
        result = await _call_tool_handler(keyless_server)(
            None,
            types.CallToolRequestParams(name="parametric_delta_normal_var", arguments=arguments),
        )

    assert result.is_error is not True
    assert json.loads(result.content[0].text) == {"var_abs": 12.5}
    assert seen == [
        ("challenge", None),
        ("ticket", None),
        ("parametric_delta_normal_var", "tkn"),
    ]
    stored = tmp_path / "data" / "install.json"
    assert json.loads(stored.read_text())["ticket"] == "tkn"


@pytest.mark.asyncio
async def test_without_a_key_in_ci_the_call_is_an_error_result_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.delenv("PYVAR_API_KEY", raising=False)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    server = build_server()  # still starts
    entry = catalogue_entry("parametric_delta_normal_var")
    arguments = {name: 1 for name in entry["input_schema"].get("required", [])}

    with patch("pyvar_mcp.trial._post", side_effect=AssertionError("no network")):
        result = await _call_tool_handler(server)(
            None,
            types.CallToolRequestParams(name="parametric_delta_normal_var", arguments=arguments),
        )

    assert result.is_error is True and "CI is set" in result.content[0].text
    assert not (tmp_path / "data").exists()


@pytest.mark.asyncio
async def test_a_slow_call_does_not_block_the_event_loop(keyless_server):
    """The sign-up puzzle or a wait runs in a worker thread, so the loop keeps serving other requests."""
    import asyncio
    import time

    entry = catalogue_entry("parametric_delta_normal_var")
    arguments = {name: 1 for name in entry["input_schema"].get("required", [])}
    ticks = 0

    def slow_post(url, payload, bearer=None):
        time.sleep(0.3)
        return 200, {}, json.dumps({"ok": True})

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    with patch("pyvar_mcp.trial._post", slow_post):
        with patch("pyvar_mcp.trial.TicketStore.load", return_value=_ticket_stub()):
            task = asyncio.create_task(ticker())
            await _call_tool_handler(keyless_server)(
                None,
                types.CallToolRequestParams(
                    name="parametric_delta_normal_var", arguments=arguments
                ),
            )
            task.cancel()

    assert ticks >= 10


def _ticket_stub():
    from pyvar_mcp.trial import Ticket

    return Ticket("tkn", 4_000_000_000, "https://www.pyvar.com")

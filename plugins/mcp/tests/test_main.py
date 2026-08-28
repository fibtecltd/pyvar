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

from pyvar_mcp.main import build_server


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("PYVAR_API_KEY", "test-key")
    return build_server()


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

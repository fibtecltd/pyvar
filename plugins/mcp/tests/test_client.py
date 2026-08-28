"""tests/test_client.py — PyvarClient tests.

No real network calls -- urllib.request.urlopen is mocked throughout, same
never-hit-a-real-backing-service rule the main repo's own tests follow.
"""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from pyvar_mcp.client import DEFAULT_API_BASE_URL, PyvarApiError, PyvarClient


def test_from_env_reads_api_key(monkeypatch):
    monkeypatch.setenv("PYVAR_API_KEY", "test-key-123")
    monkeypatch.delenv("PYVAR_API_BASE_URL", raising=False)

    client = PyvarClient.from_env()

    assert client.api_key == "test-key-123"
    assert client.base_url == DEFAULT_API_BASE_URL


def test_from_env_honours_custom_base_url(monkeypatch):
    monkeypatch.setenv("PYVAR_API_KEY", "test-key-123")
    monkeypatch.setenv("PYVAR_API_BASE_URL", "https://dev.pyvar.com")

    client = PyvarClient.from_env()

    assert client.base_url == "https://dev.pyvar.com"


def test_from_env_raises_clear_error_when_key_missing(monkeypatch):
    monkeypatch.delenv("PYVAR_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="PYVAR_API_KEY is not set"):
        PyvarClient.from_env()


def test_call_function_success():
    client = PyvarClient(api_key="test-key")

    with patch("pyvar_mcp.client.urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps({"var_abs": 28000.0}).encode()

        result = client.call_function("/api/v1/market-risk/historical_simulation_var", {"x": 1})

    assert result == {"var_abs": 28000.0}
    request = mock_urlopen.call_args[0][0]
    assert (
        request.full_url == f"{DEFAULT_API_BASE_URL}/api/v1/market-risk/historical_simulation_var"
    )
    assert request.get_header("Authorization") == "Bearer test-key"
    assert request.get_header("Content-type") == "application/json"


def test_call_function_raises_pyvar_api_error_on_http_error():
    client = PyvarClient(api_key="test-key")

    http_error = urllib.error.HTTPError(
        url="https://www.pyvar.com/api/v1/alm/alm_stress_test",
        code=422,
        msg="Unprocessable Entity",
        hdrs=None,
        fp=MagicMock(read=lambda: b'{"detail": "bad input"}'),
    )
    with patch("pyvar_mcp.client.urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(PyvarApiError) as exc_info:
            client.call_function("/api/v1/alm/alm_stress_test", {})

    assert exc_info.value.status_code == 422
    assert "bad input" in exc_info.value.body


def test_call_function_raises_pyvar_api_error_on_network_failure():
    client = PyvarClient(api_key="test-key")

    with patch(
        "pyvar_mcp.client.urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        with pytest.raises(PyvarApiError) as exc_info:
            client.call_function("/api/v1/alm/alm_stress_test", {})

    assert exc_info.value.status_code == 0
    assert "connection refused" in exc_info.value.body

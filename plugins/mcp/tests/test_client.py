"""tests/test_client.py — PyvarClient tests.

No real network calls -- urllib.request.urlopen is mocked throughout, same
never-hit-a-real-backing-service rule the main repo's own tests follow.
"""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from pyvar_mcp import __version__
from pyvar_mcp.client import (
    CLIENT_ID,
    DEFAULT_API_BASE_URL,
    PyvarApiError,
    PyvarClient,
    PyvarSetupError,
    clean_api_key,
)
from pyvar_mcp.trial import TrialError, TrialHttpError, TrialSession


def test_client_label_carries_the_same_version_the_server_reports():
    assert CLIENT_ID == f"pyvar-mcp/{__version__}"


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


def test_from_env_without_a_key_no_longer_fails_at_start_up(monkeypatch):
    """A missing key used to stop the server before it could list a tool; now it only limits the calls."""
    monkeypatch.delenv("PYVAR_API_KEY", raising=False)

    client = PyvarClient.from_env()

    assert client.api_key is None and client.has_key is False


@pytest.mark.parametrize("value", ["", "   ", "${user_config.pyvar_api_key}", "${anything"])
def test_an_empty_or_unsubstituted_key_counts_as_no_key(monkeypatch, value):
    monkeypatch.setenv("PYVAR_API_KEY", value)

    assert PyvarClient.from_env().api_key is None
    assert clean_api_key(value) is None


def test_a_real_key_is_kept_trimmed(monkeypatch):
    monkeypatch.setenv("PYVAR_API_KEY", "  pyvar_abc  ")

    assert PyvarClient.from_env().api_key == "pyvar_abc"


def test_a_configured_key_always_wins_over_the_trial(monkeypatch, tmp_path):
    """With a key the trial is never built, even where it could run."""
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("CI", raising=False)
    client = PyvarClient(api_key="pyvar_real")

    with patch("pyvar_mcp.client.TrialSession.from_env", side_effect=AssertionError("trial used")):
        with patch("pyvar_mcp.client.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = b'{"ok": 1}'
            assert client.call_function("/api/v1/market-risk/kupiec_pof_test", {}) == {"ok": 1}

    assert mock_urlopen.call_args[0][0].get_header("Authorization") == "Bearer pyvar_real"
    assert not (tmp_path / "data").exists()


def _keyless(monkeypatch, tmp_path, **env):
    monkeypatch.delenv("PYVAR_API_KEY", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return PyvarClient.from_env()


def test_without_a_key_a_trial_function_goes_through_the_trial(monkeypatch, tmp_path):
    client = _keyless(monkeypatch, tmp_path)

    with patch("pyvar_mcp.client.TrialSession.call", return_value={"var_abs": 4.0}) as call:
        result = client.call_function("/api/v1/market-risk/parametric_delta_normal_var", {"a": 1})

    assert result == {"var_abs": 4.0}
    call.assert_called_once_with("parametric_delta_normal_var", {"a": 1})


def test_the_trial_session_is_built_once_and_reused(monkeypatch, tmp_path):
    client = _keyless(monkeypatch, tmp_path)

    with patch("pyvar_mcp.client.TrialSession.from_env", wraps=TrialSession.from_env) as build:
        with patch("pyvar_mcp.client.TrialSession.call", return_value={}):
            client.call_function("/api/v1/market-risk/parametric_delta_normal_var", {})
            client.call_function("/api/v1/market-risk/parametric_delta_normal_var", {})

    assert build.call_count == 1


def test_without_a_key_a_function_off_the_trial_list_says_it_needs_one(monkeypatch, tmp_path):
    client = _keyless(monkeypatch, tmp_path)

    with patch("pyvar_mcp.trial._post", side_effect=AssertionError("no network")):
        with pytest.raises(PyvarSetupError, match="free pyvar API key"):
            client.call_function("/api/v1/market-risk/historical_simulation_var", {})

    assert not (tmp_path / "data").exists()


def test_without_a_key_ci_gets_the_old_instruction_and_no_trial(monkeypatch, tmp_path):
    client = _keyless(monkeypatch, tmp_path, CI="true")

    with patch("pyvar_mcp.trial._post", side_effect=AssertionError("no network")):
        with pytest.raises(PyvarSetupError, match="CI is set"):
            client.call_function("/api/v1/market-risk/parametric_delta_normal_var", {})


def test_without_a_key_outside_claude_code_there_is_no_trial(monkeypatch):
    monkeypatch.delenv("PYVAR_API_KEY", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)

    with pytest.raises(PyvarSetupError, match="PYVAR_API_KEY is not set"):
        PyvarClient.from_env().call_function("/api/v1/market-risk/parametric_delta_normal_var", {})


def test_trial_answers_keep_their_status_and_refusals_keep_the_servers_words(monkeypatch, tmp_path):
    client = _keyless(monkeypatch, tmp_path)
    path = "/api/v1/market-risk/parametric_delta_normal_var"

    with patch("pyvar_mcp.client.TrialSession.call", side_effect=TrialHttpError(422, '{"d": 1}')):
        with pytest.raises(PyvarApiError) as api_error:
            client.call_function(path, {})
    assert (api_error.value.status_code, api_error.value.body) == (422, '{"d": 1}')

    with patch("pyvar_mcp.client.TrialSession.call", side_effect=TrialError("busy: use a key")):
        with pytest.raises(PyvarSetupError) as setup_error:
            client.call_function(path, {})
    assert setup_error.value.message == "busy: use a key"


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


def test_requests_identify_the_server_as_pyvar_mcp():
    """X-Pyvar-Client lets the API attribute calls to this server (allowlisted label)."""
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        captured["client"] = request.get_header("X-pyvar-client")
        return FakeResponse()

    with patch("urllib.request.urlopen", fake_urlopen):
        PyvarClient(api_key="pyvar_x").call_function("/api/v1/x", {})
    assert captured["client"].startswith("pyvar-mcp/")

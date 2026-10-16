"""PYVAR_API_KEY is the default key, and every request says which client it came from."""

from __future__ import annotations

import httpx
import pytest

from pyvar_client import Client


def _recording_transport(seen: dict[str, str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["authorization"]
        seen["client"] = request.headers["x-pyvar-client"]
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler)


def test_key_defaults_to_the_environment_and_requests_identify_the_client(monkeypatch):
    monkeypatch.setenv("PYVAR_API_KEY", "pyvar_from_env")
    seen: dict[str, str] = {}
    with Client(transport=_recording_transport(seen)) as client:
        client.market_risk.kupiec_pof_test(n_breaches=6, n_observations=250)
    assert seen["authorization"] == "Bearer pyvar_from_env"
    assert seen["client"].startswith("pyvar-client/")


def test_an_explicit_key_beats_the_environment(monkeypatch):
    monkeypatch.setenv("PYVAR_API_KEY", "pyvar_from_env")
    seen: dict[str, str] = {}
    with Client(api_key="pyvar_explicit", transport=_recording_transport(seen)) as client:
        client.market_risk.kupiec_pof_test(n_breaches=6, n_observations=250)
    assert seen["authorization"] == "Bearer pyvar_explicit"


def test_no_key_anywhere_says_how_to_get_one(monkeypatch):
    monkeypatch.delenv("PYVAR_API_KEY", raising=False)
    with pytest.raises(ValueError, match="PYVAR_API_KEY") as excinfo:
        Client()
    assert "pyvar.com" in str(excinfo.value)


def test_an_explicitly_empty_key_is_rejected_even_if_the_environment_has_one(monkeypatch):
    monkeypatch.setenv("PYVAR_API_KEY", "pyvar_from_env")
    with pytest.raises(ValueError):
        Client(api_key="")

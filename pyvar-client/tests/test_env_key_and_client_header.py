"""PYVAR_API_KEY is the default key, and every request says which client it came from
(the `pyvar` command says pyvar-cli, the Python client pyvar-client)."""

from __future__ import annotations

import json

import httpx
import pytest

from pyvar_client import Client, cli


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


def test_client_name_changes_the_label_but_not_the_version():
    seen: dict[str, str] = {}
    with Client(
        api_key="pyvar_k", client_name="pyvar-cli", transport=_recording_transport(seen)
    ) as client:
        client.market_risk.kupiec_pof_test(n_breaches=6, n_observations=250)
    default: dict[str, str] = {}
    with Client(api_key="pyvar_k", transport=_recording_transport(default)) as client:
        client.market_risk.kupiec_pof_test(n_breaches=6, n_observations=250)
    name, version = seen["client"].split("/", 1)
    assert name == "pyvar-cli"
    assert version == default["client"].split("/", 1)[1]


@pytest.mark.parametrize("bad", ["", "PyVar", "pyvar/cli", "pyvar cli", "x" * 40, "-cli"])
def test_a_client_name_that_is_not_a_short_lowercase_token_is_rejected(bad):
    with pytest.raises(ValueError, match="client_name"):
        Client(api_key="pyvar_k", client_name=bad)


def test_the_pyvar_command_reports_itself_as_pyvar_cli():
    seen: dict[str, str] = {}

    def factory(**kwargs):
        return Client(
            api_key=kwargs["api_key"],
            client_name=kwargs["client_name"],
            transport=_recording_transport(seen),
        )

    exit_code = cli.main(
        [
            "market_risk",
            "kupiec_pof_test",
            "--api-key",
            "pyvar_k",
            "--params-json",
            json.dumps({"n_breaches": 6, "n_observations": 250}),
        ],
        client_factory=factory,
    )

    assert exit_code == 0
    assert seen["client"].startswith("pyvar-cli/")

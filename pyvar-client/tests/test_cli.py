"""tests/test_cli.py — the `pyvar` CLI, same no-real-HTTP-calls rule as the
rest of this suite (see tests/conftest.py's own module docstring).

client_factory lets every test that reaches build_client() substitute a
Client backed by httpx.MockTransport (via conftest's make_client) instead of
constructing a real one — main()'s own client_factory parameter exists for
exactly this.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from pyvar_client import Client, cli
from tests.conftest import make_client


def _factory(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[..., Client]:
    """A client_factory that ignores build_client's real args (api_key/base_url/
    timeout) and always returns a MockTransport-backed Client instead."""

    def factory(**_: Any) -> Client:
        return make_client(handler)

    return factory


def test_list_domains(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["list-domains"])

    assert exit_code == 0
    out = capsys.readouterr().out
    for domain in ("market_risk", "credit_risk", "var", "alm"):
        assert domain in out


def test_list_functions(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["list-functions", "--domain", "market_risk"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "basel_capital_addon_multiplier" in out


def test_list_functions_no_client_needed(capsys: pytest.CaptureFixture[str]) -> None:
    """No --api-key, no PYVAR_API_KEY -- must still work (no client built)."""
    exit_code = cli.main(["list-functions", "--domain", "var"])

    assert exit_code == 0
    assert "compute" in capsys.readouterr().out


def test_call_domain_function_success(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"multiplier": 3.4})

    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "test-token",
            "--params-json",
            json.dumps({"n_breaches": 6}),
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"multiplier": 3.4}


def test_call_domain_function_compact_output(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"a": 1})

    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "test-token",
            "--params-json",
            json.dumps({"n_breaches": 1}),
            "--compact",
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out == '{"a": 1}\n'


def test_call_domain_function_no_params_shows_help(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no HTTP call should be made when showing help")

    exit_code = cli.main(
        ["market_risk", "basel_capital_addon_multiplier", "--api-key", "test-token"],
        client_factory=_factory(handler),
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "basel_capital_addon_multiplier" in out
    assert "n_breaches" in out


def test_call_domain_function_unknown_function(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no HTTP call should be made for an unknown function")

    exit_code = cli.main(
        [
            "market_risk",
            "not_a_real_function",
            "--api-key",
            "test-token",
            "--params-json",
            "{}",
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 1
    assert "not a function" in capsys.readouterr().err


def test_params_from_stdin(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"n_breaches": 1})))

    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "test-token",
            "--params",
            "-",
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True}


def test_var_submit(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"task_id": "abc-123"})

    exit_code = cli.main(
        [
            "var",
            "submit",
            "--api-key",
            "test-token",
            "--params-json",
            json.dumps({"portfolio_value": 1_000_000, "returns": [0.01, 0.02, -0.01]}),
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"task_id": "abc-123"}


def test_var_poll(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "pending"})

    exit_code = cli.main(
        ["var", "poll", "task-xyz", "--api-key", "test-token"],
        client_factory=_factory(handler),
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"status": "pending"}


def test_var_compute_success(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "abc-123"})
        return httpx.Response(200, json={"status": "success", "result": {"var_pct": 0.05}})

    exit_code = cli.main(
        [
            "var",
            "compute",
            "--api-key",
            "test-token",
            "--params-json",
            json.dumps({"portfolio_value": 1_000_000, "returns": [0.01, 0.02, -0.01]}),
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"var_pct": 0.05}


def test_var_compute_failure(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "abc-123"})
        return httpx.Response(200, json={"status": "failure", "error": "boom"})

    exit_code = cli.main(
        [
            "var",
            "compute",
            "--api-key",
            "test-token",
            "--params-json",
            json.dumps({"portfolio_value": 1_000_000, "returns": [0.01]}),
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 5
    assert "task_id=abc-123" in capsys.readouterr().err


def test_missing_api_key(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PYVAR_API_KEY", raising=False)

    exit_code = cli.main(["market_risk", "basel_capital_addon_multiplier", "--params-json", "{}"])

    assert exit_code == 1
    assert "API key" in capsys.readouterr().err


def test_bad_params_file_missing(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "test-token",
            "--params",
            "/nonexistent/params.json",
        ],
        client_factory=_factory(lambda request: httpx.Response(200, json={})),
    )

    assert exit_code == 1


def test_invalid_params_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "test-token",
            "--params-json",
            "not valid json",
        ],
        client_factory=_factory(lambda request: httpx.Response(200, json={})),
    )

    assert exit_code == 1


def test_auth_error(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "expired"})

    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "bad",
            "--params-json",
            json.dumps({"n_breaches": 1}),
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 2


def test_validation_error(capsys: pytest.CaptureFixture[str]) -> None:
    body = {"detail": [{"loc": ["body", "n_breaches"], "msg": "required", "type": "missing"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json=body)

    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "test-token",
            "--params-json",
            json.dumps({"n_breaches": 1}),
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 3
    err = capsys.readouterr().err
    assert "n_breaches" in err


def test_rate_limit_error(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "slow down"}, headers={"Retry-After": "30"})

    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "test-token",
            "--params-json",
            json.dumps({"n_breaches": 1}),
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 4
    assert "retry after 30s" in capsys.readouterr().err


def test_generic_pyvar_error(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "test-token",
            "--params-json",
            json.dumps({"n_breaches": 1}),
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 1
    assert "not found" in capsys.readouterr().err


def test_params_from_real_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    params_file = tmp_path / "params.json"
    params_file.write_text(json.dumps({"n_breaches": 2}))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"multiplier": 3.4})

    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "test-token",
            "--params",
            str(params_file),
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"multiplier": 3.4}


def test_params_json_not_an_object(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "test-token",
            "--params-json",
            "[1, 2, 3]",
        ],
        client_factory=_factory(lambda request: httpx.Response(200, json={})),
    )

    assert exit_code == 1
    assert "JSON object" in capsys.readouterr().err


def test_domain_function_unknown_no_params_shows_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        ["market_risk", "not_a_real_function", "--api-key", "test-token"],
        client_factory=_factory(lambda request: httpx.Response(200, json={})),
    )

    assert exit_code == 1
    assert "not a function" in capsys.readouterr().err


def test_var_submit_no_params_shows_help(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no HTTP call should be made when showing help")

    exit_code = cli.main(
        ["var", "submit", "--api-key", "test-token"],
        client_factory=_factory(handler),
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "submit" in out
    assert "portfolio_value" in out


def test_var_compute_with_poll_overrides(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "abc-123"})
        return httpx.Response(200, json={"status": "success", "result": {"var_pct": 0.05}})

    exit_code = cli.main(
        [
            "var",
            "compute",
            "--api-key",
            "test-token",
            "--params-json",
            json.dumps({"portfolio_value": 1_000_000, "returns": [0.01, 0.02, -0.01]}),
            "--poll-interval",
            "0.01",
            "--poll-timeout",
            "5",
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"var_pct": 0.05}


def test_keyboard_interrupt_maps_to_130(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    def raise_interrupt(*args: Any, **kwargs: Any) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_invoke", raise_interrupt)

    exit_code = cli.main(
        [
            "market_risk",
            "basel_capital_addon_multiplier",
            "--api-key",
            "test-token",
            "--params-json",
            json.dumps({"n_breaches": 1}),
        ],
        client_factory=_factory(handler),
    )

    assert exit_code == 130

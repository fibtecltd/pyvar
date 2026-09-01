from __future__ import annotations

import os

from pyvar_jupyter._display import PyvarResult
from tests.conftest import make_client


def test_line_magic_calls_and_returns_result(magics, json_response):
    magics._client = make_client(json_response(200, {"var_abs": 12345.6789, "cvar_abs": 15000.0}))

    result = magics.pyvar(
        "market_risk.historical_simulation_var returns=[0.01,-0.02] portfolio_value=1000000"
    )

    assert isinstance(result, PyvarResult)
    assert result.data == {"var_abs": 12345.6789, "cvar_abs": 15000.0}
    assert result["var_abs"] == 12345.6789


def test_cell_magic_parses_json_body(magics, json_response):
    magics._client = make_client(json_response(200, {"var_abs": 999.0}))

    result = magics.pyvar(
        "market_risk.historical_simulation_var",
        '{"returns": [0.01, -0.02], "portfolio_value": 1000000}',
    )

    assert result.data == {"var_abs": 999.0}


def test_cell_magic_invalid_json_prints_error_and_returns_none(magics, json_response, capsys):
    magics._client = make_client(json_response(200, {}))

    result = magics.pyvar("market_risk.historical_simulation_var", "{not valid json")

    assert result is None
    assert "Invalid JSON" in capsys.readouterr().out


def test_cell_magic_non_object_json_returns_none(magics, json_response, capsys):
    magics._client = make_client(json_response(200, {}))

    result = magics.pyvar("market_risk.historical_simulation_var", "[1, 2, 3]")

    assert result is None
    assert "JSON object" in capsys.readouterr().out


def test_no_params_prints_docstring_and_returns_none(magics, json_response, capsys):
    magics._client = make_client(json_response(200, {}))

    result = magics.pyvar("market_risk.historical_simulation_var")

    assert result is None
    out = capsys.readouterr().out
    assert "historical_simulation_var" in out


def test_missing_domain_separator_returns_none(magics, capsys):
    result = magics.pyvar("not_a_valid_target")

    assert result is None
    assert "domain" in capsys.readouterr().out.lower()


def test_unknown_domain_returns_none(magics, json_response, capsys):
    magics._client = make_client(json_response(200, {}))

    result = magics.pyvar("not_a_domain.some_function")

    assert result is None
    assert "Unknown domain" in capsys.readouterr().out


def test_unknown_function_returns_none(magics, json_response, capsys):
    magics._client = make_client(json_response(200, {}))

    result = magics.pyvar("market_risk.not_a_real_function")

    assert result is None
    assert "Unknown function" in capsys.readouterr().out


def test_api_error_is_caught_and_printed(magics, json_response, capsys):
    magics._client = make_client(
        json_response(
            422,
            {"detail": [{"loc": ["confidence_level"], "msg": "too high", "type": "value_error"}]},
        )
    )

    result = magics.pyvar(
        "market_risk.historical_simulation_var returns=[0.01] portfolio_value=100 "
        "confidence_level=0.9999999"
    )

    assert result is None
    out = capsys.readouterr().out
    assert "422" in out


def test_no_api_key_raises_helpful_message(magics, capsys, monkeypatch):
    monkeypatch.delenv("PYVAR_API_KEY", raising=False)

    result = magics.pyvar(
        "market_risk.historical_simulation_var returns=[0.01] portfolio_value=100"
    )

    assert result is None
    assert "PYVAR_API_KEY" in capsys.readouterr().out


def test_pyvar_key_sets_env_and_resets_client(magics, capsys, monkeypatch):
    monkeypatch.delenv("PYVAR_API_KEY", raising=False)
    magics._client = object()  # sentinel: must be cleared, not reused

    magics.pyvar_key("sk-abc123")

    assert os.environ["PYVAR_API_KEY"] == "sk-abc123"
    assert magics._client is None
    assert "set" in capsys.readouterr().out.lower()


def test_pyvar_key_empty_prints_usage(magics, capsys):
    magics.pyvar_key("")

    assert "Usage" in capsys.readouterr().out


def test_pyvar_base_url_sets_and_resets_client(magics, capsys):
    magics._client = object()  # sentinel: must be cleared, not reused

    magics.pyvar_base_url("http://localhost:8000")

    assert magics._base_url == "http://localhost:8000"
    assert magics._client is None
    assert "localhost:8000" in capsys.readouterr().out


def test_pyvar_base_url_no_arg_prints_current(magics, capsys):
    magics.pyvar_base_url("")

    assert magics._base_url in capsys.readouterr().out


def test_var_expand_interpolates_notebook_variables(magics_with_shell, json_response):
    """{expr} in the magic line must expand against the notebook's own
    variables (standard IPython magic convention) -- and Python's str() of
    a list puts a space after every comma ("[0.01, -0.02]"), so the
    tokenizer must not split on that internal whitespace. Regression test
    for a real bug caught while writing examples/01_portfolio_var.ipynb."""
    captured = {}

    def handler(request):
        import json as _json

        captured["body"] = _json.loads(request.content)
        return __import__("httpx").Response(200, json={"ok": True})

    magics_with_shell._client = make_client(handler)
    magics_with_shell.shell.user_ns["my_returns"] = [0.01, -0.02, 0.015]

    result = magics_with_shell.pyvar(
        "market_risk.historical_simulation_var returns={my_returns} portfolio_value=1000000"
    )

    assert result is not None
    assert captured["body"]["returns"] == [0.01, -0.02, 0.015]
    assert captured["body"]["portfolio_value"] == 1000000


def test_line_magic_type_coercion(magics, json_response):
    """confidence_level=0.99 and returns=[...] must parse as float/list, not strings --
    otherwise pyvar_client's request body would send the wrong JSON types."""
    captured = {}

    def handler(request):
        import json as _json

        captured["body"] = _json.loads(request.content)
        return __import__("httpx").Response(200, json={"ok": True})

    magics._client = make_client(handler)

    magics.pyvar(
        "market_risk.historical_simulation_var returns=[0.01,-0.02] "
        "portfolio_value=1000000 confidence_level=0.99"
    )

    assert captured["body"] == {
        "returns": [0.01, -0.02],
        "portfolio_value": 1000000,
        "confidence_level": 0.99,
    }

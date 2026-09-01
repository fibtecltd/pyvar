from __future__ import annotations

from pyvar_jupyter._dispatch import parse_line_params, tokenize_key_value_line


def test_tokenize_plain_tokens():
    assert tokenize_key_value_line("returns=[0.01,-0.02] portfolio_value=1000000") == [
        "returns=[0.01,-0.02]",
        "portfolio_value=1000000",
    ]


def test_tokenize_respects_internal_spaces_in_brackets():
    """Python's str() of a list puts a space after each comma -- the exact
    shape {expr} variable expansion produces (see _magics.py)."""
    assert tokenize_key_value_line("returns=[0.01, -0.02, 0.015] portfolio_value=1000000") == [
        "returns=[0.01, -0.02, 0.015]",
        "portfolio_value=1000000",
    ]


def test_tokenize_respects_nested_brackets():
    assert tokenize_key_value_line("returns=[[0.01, 0.02], [0.03, 0.04]] x=1") == [
        "returns=[[0.01, 0.02], [0.03, 0.04]]",
        "x=1",
    ]


def test_tokenize_respects_quoted_strings_with_spaces():
    assert tokenize_key_value_line('method="historical simulation" x=1') == [
        'method="historical simulation"',
        "x=1",
    ]


def test_tokenize_dict_value():
    assert tokenize_key_value_line('params={"a": 1, "b": 2} x=3') == [
        'params={"a": 1, "b": 2}',
        "x=3",
    ]


def test_tokenize_empty_string():
    assert tokenize_key_value_line("") == []


def test_parse_line_params_types():
    params = parse_line_params(
        ["returns=[0.01, -0.02]", "portfolio_value=1000000", "confidence_level=0.99", "flag=True"]
    )
    assert params == {
        "returns": [0.01, -0.02],
        "portfolio_value": 1000000,
        "confidence_level": 0.99,
        "flag": True,
    }


def test_parse_line_params_string_fallback():
    params = parse_line_params(["method=historical"])
    assert params == {"method": "historical"}

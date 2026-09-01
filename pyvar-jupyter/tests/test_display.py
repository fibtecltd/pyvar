from __future__ import annotations

from pyvar_jupyter._display import PyvarResult, show


def test_show_wraps_dict():
    result = show({"var_abs": 1000.0})

    assert isinstance(result, PyvarResult)
    assert result.data == {"var_abs": 1000.0}


def test_dict_like_access():
    result = PyvarResult({"var_abs": 1000.0, "cvar_abs": 1200.0})

    assert result["var_abs"] == 1000.0
    assert result.get("missing", "default") == "default"
    assert "cvar_abs" in result
    assert set(iter(result)) == {"var_abs", "cvar_abs"}


def test_repr_html_renders_a_table():
    result = PyvarResult({"var_abs": 12345.6789, "note": "ok"})

    html = result._repr_html_()

    assert "<table" in html
    assert "var_abs" in html
    assert "note" in html


def test_repr_html_escapes_string_values():
    """API responses can echo back request input (e.g. a validation error's
    field value) -- never let that be interpreted as HTML markup."""
    result = PyvarResult({"detail": "<img src=x onerror=alert(1)>"})

    html = result._repr_html_()

    assert "<img" not in html
    assert "&lt;img" in html


def test_repr_html_handles_nested_dict():
    result = PyvarResult({"components": {"equities": 500.0, "bonds": 300.0}})

    html = result._repr_html_()

    assert "equities" in html
    assert html.count("<table") == 2  # outer + nested


def test_repr_html_handles_long_list():
    result = PyvarResult({"paths": list(range(20))})

    html = result._repr_html_()

    assert "more" in html


def test_repr_html_non_dict_falls_back_to_pre():
    result = PyvarResult([1, 2, 3])

    html = result._repr_html_()

    assert "<pre>" in html


def test_repr_is_plain_dict_repr():
    result = PyvarResult({"var_abs": 1000.0})

    assert repr(result) == repr({"var_abs": 1000.0})

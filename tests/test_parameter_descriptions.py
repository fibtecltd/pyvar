"""Every request parameter carries the description its engine docstring gives it.

Reasoning:
- Until 2026-11-07 none of the 1,577 request parameters had a description anywhere (OpenAPI, the portal
  catalogue, the Try-it panel, the skills' parameter tables) although the engine documents every argument
  in an `Args:` section. scripts/add_param_descriptions.py put that text on the request models.
- These tests keep it that way. The engine docstring is the single source of truth, so a model whose
  description differs from it, a new endpoint without one, or a catalogue that is not rebuilt after an
  engine edit, fails here. The fix is always: edit the engine docstring, then
  `python scripts/add_param_descriptions.py` (existing models) or `python scripts/gen_p3.py` (new ones),
  then `python scripts/generate_function_catalog.py` and the skills sync.
- The change is description-only. It must never add a bound, validator or type, so the API accepts
  exactly what it accepted before; the PR proved that by diffing the live OpenAPI document.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import param_docs

# An engine argument the API model does not expose: liquidity_gap_analysis(opening_balance=...) was added to
# the engine after its model was generated, so a client that sends it is silently ignored. Listed here so
# this test fails, and tells you to remove the entry, the day the model is fixed.
KNOWN_UNEXPOSED = {"LiquidityGapAnalysisRequest": {"opening_balance"}}


@pytest.fixture(scope="module")
def models() -> dict[str, dict[str, Any]]:
    return param_docs.request_models()


def _model_class(entry: dict[str, Any], name: str) -> Any:
    module = importlib.import_module("schemas." + entry["domain"].replace("-", "_"))
    return getattr(module, name)


# ── the docstring parser ────────────────────────────────────────────────────────────────────────────


def test_parse_args_section_reads_the_google_forms() -> None:
    doc = """Summary line.

    Args:
        alpha: First one.
        beta (float): Second one, with a type.
        gamma: A long description that
            continues on the next line.
        *delta: Starred names lose the star.

    Returns:
        Not an argument: ignored.
    """
    assert param_docs.parse_args_section(doc) == {
        "alpha": "First one.",
        "beta": "Second one, with a type.",
        "gamma": "A long description that continues on the next line.",
        "delta": "Starred names lose the star.",
    }


def test_parse_args_section_without_args_is_empty() -> None:
    assert param_docs.parse_args_section("Just a summary.") == {}
    assert param_docs.parse_args_section(None) == {}


def test_parse_args_section_stops_at_the_next_section() -> None:
    doc = "S.\n\nArgs:\n    a: One.\n\nRaises:\n    ValueError: not an argument.\n"
    assert param_docs.parse_args_section(doc) == {"a": "One."}


# ── the models ──────────────────────────────────────────────────────────────────────────────────────


def test_there_is_a_request_model_for_every_endpoint(models: dict[str, dict[str, Any]]) -> None:
    assert len(models) == 385


def test_every_engine_argument_is_documented(models: dict[str, dict[str, Any]]) -> None:
    undocumented = [
        f"{entry['function']}({param})"
        for entry in models.values()
        for param in entry["params"]
        if not param_docs.description_for(entry, param)
    ]
    assert not undocumented, "add an `Args:` entry to the engine docstring for: " + ", ".join(
        undocumented
    )


def test_model_fields_match_the_engine_signature_except_the_known_gap(
    models: dict[str, dict[str, Any]],
) -> None:
    gaps: dict[str, set[str]] = {}
    for name, entry in models.items():
        fields = set(_model_class(entry, name).model_fields)
        unexposed = set(entry["params"]) - fields
        assert not (fields - set(entry["params"])), f"{name} has a field the engine does not take"
        if unexposed:
            gaps[name] = unexposed
    assert gaps == KNOWN_UNEXPOSED


def test_every_field_carries_its_engine_description(models: dict[str, dict[str, Any]]) -> None:
    wrong: list[str] = []
    for name, entry in models.items():
        fields = _model_class(entry, name).model_fields
        for param in entry["params"]:
            if param not in fields:
                continue  # the known gap, checked above
            expected = param_docs.description_for(entry, param)
            if fields[param].description != expected:
                wrong.append(f"{name}.{param}")
    assert not wrong, (
        f"{len(wrong)} fields differ from the engine docstring (run scripts/add_param_descriptions.py): "
        + ", ".join(wrong[:8])
    )


def test_descriptions_change_nothing_else_about_a_field(models: dict[str, dict[str, Any]]) -> None:
    """The change is description-only: no bound, pattern or length constraint appears on a field."""
    constrained: list[str] = []
    for name, entry in models.items():
        for param, info in _model_class(entry, name).model_fields.items():
            if info.metadata:
                constrained.append(f"{name}.{param}")
    assert not constrained, "unexpected field constraints: " + ", ".join(constrained[:8])


# ── what a visitor and a client see ─────────────────────────────────────────────────────────────────


def test_the_openapi_document_describes_every_parameter() -> None:
    from main import create_app

    schemas = create_app().openapi()["components"]["schemas"]
    catalogue = json.loads((REPO / "portal" / "functions.json").read_text())
    missing = []
    for fn in catalogue:
        for p in fn["params"]:
            body = schemas[_request_schema_name(fn["name"], schemas)]
            if not body["properties"][p["name"]].get("description"):
                missing.append(f"{fn['name']}.{p['name']}")
    assert not missing, f"{len(missing)} parameters have no description in OpenAPI: {missing[:8]}"


def _request_schema_name(function: str, schemas: dict[str, Any]) -> str:
    wanted = "".join(part.capitalize() for part in function.split("_")) + "Request"
    if wanted in schemas:
        return wanted
    matches = [n for n in schemas if n.endswith("Request") and n.lower() == wanted.lower()]
    assert matches, f"no request schema for {function}"
    return matches[0]


def test_the_portal_catalogue_carries_the_same_descriptions() -> None:
    from main import create_app

    schemas = create_app().openapi()["components"]["schemas"]
    catalogue = json.loads((REPO / "portal" / "functions.json").read_text())
    stale = []
    for fn in catalogue:
        body = schemas[_request_schema_name(fn["name"], schemas)]["properties"]
        for p in fn["params"]:
            if p["description"] != body[p["name"]].get("description"):
                stale.append(f"{fn['name']}.{p['name']}")
    assert not stale, (
        f"{len(stale)} catalogue descriptions are stale (run scripts/generate_function_catalog.py): "
        + ", ".join(stale[:8])
    )


def test_the_try_it_panel_shows_the_description_escaped() -> None:
    source = (REPO / "portal" / "pyvar.js").read_text()
    assert "_escapeHtml(p.description)" in source, "a description must be escaped before it is HTML"
    assert 'aria-describedby="${hintId}"' in source, "a screen reader should read it with the field"
    assert ".tryit-hint" in (REPO / "portal" / "pyvar.css").read_text()

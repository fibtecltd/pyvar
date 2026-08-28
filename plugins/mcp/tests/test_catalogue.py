"""tests/test_catalogue.py — lookup-helper tests over the generated tool list."""

from __future__ import annotations

from pyvar_mcp import catalogue


def test_all_functions_matches_expected_count():
    # 385 functions across 8 domains -- see CLAUDE.md's own function counts.
    assert len(catalogue.all_functions()) == 385


def test_domains_are_the_expected_eight():
    assert catalogue.domains() == [
        "alm",
        "credit-risk",
        "derivatives",
        "liquidity",
        "market-risk",
        "operational",
        "portfolio",
        "regulatory",
    ]


def test_by_tool_name_finds_a_known_function():
    entry = catalogue.by_tool_name("alm_stress_test")

    assert entry is not None
    assert entry["domain"] == "alm"
    assert entry["path"] == "/api/v1/alm/alm_stress_test"


def test_by_tool_name_returns_none_for_unknown_name():
    assert catalogue.by_tool_name("not_a_real_function") is None


def test_by_domain_and_function_matches_by_tool_name_lookup():
    by_name = catalogue.by_tool_name("alm_stress_test")
    by_domain_fn = catalogue.by_domain_and_function("alm", "alm_stress_test")

    assert by_name == by_domain_fn


def test_in_domain_returns_only_that_domains_functions():
    entries = catalogue.in_domain("alm")

    assert len(entries) > 0
    assert all(e["domain"] == "alm" for e in entries)

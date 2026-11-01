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


def test_generated_files_stay_under_the_directory_scanners_read_limit():
    # The plugin directory's safety scan reads a file in full only up to 256 KiB. The old single
    # functions.py was 399 KiB, so its tail was only heuristically scanned and docstring
    # cross-references there were misread as a command assembled at run time (a hold).
    from pathlib import Path

    generated = Path(catalogue.__file__).parent / "_generated"
    sizes = {p.name: p.stat().st_size for p in generated.glob("*.py")}
    assert "functions.py" not in sizes
    assert max(sizes.values()) < 200_000, sizes
    assert len(sizes) == 9  # eight domain modules and __init__.py


def test_functions_keep_the_order_of_functions_json():
    domains_in_order = []
    for entry in catalogue.all_functions():
        if not domains_in_order or domains_in_order[-1] != entry["domain"]:
            domains_in_order.append(entry["domain"])
    # each domain is one contiguous run, and the runs are in sorted order
    assert domains_in_order == sorted(set(domains_in_order)) == catalogue.domains()

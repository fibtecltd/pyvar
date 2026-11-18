"""tests/test_trial_weight_bench.py — scripts/trial_weight_bench.py chooses the trial lane's whitelist.

Reasoning:
- The A3 trial lane (docs/plan-trial-lane-throttle.md) may only run functions that are cheap and that do not
  compile a Numba kernel on a worker's first call. The benchmark script decides which; a wrong verdict would
  put a slow or compiling function on a public, unauthenticated-in-effect route, so its small pure parts are
  pinned here and its two measuring paths are each run once against the real app.
- The recorded payloads (scripts/trial_bench_payloads.json) must stay real POST routes: a renamed route would
  silently drop out of the benchmark.
- No mocking of the engine (CLAUDE.md section 5): the smoke tests call the real routes in process.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "trial_weight_bench.py"
# A cheap closed-form route with a recorded payload.
_CHEAP_ROUTE = "/api/v1/liquidity/liquidity_coverage_ratio_lcr"


def _bench() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.skip(f"source file not found (cannot audit): {_SCRIPT}")
    name = "trial_weight_bench_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_percentile_interpolates_and_rejects_bad_input() -> None:
    bench = _bench()
    assert bench.percentile([5.0], 0.95) == 5.0
    assert bench.percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert bench.percentile([4.0, 1.0, 3.0, 2.0], 1.0) == 4.0
    assert bench.percentile(list(map(float, range(1, 101))), 0.95) == pytest.approx(95.05)
    with pytest.raises(ValueError):
        bench.percentile([], 0.5)
    with pytest.raises(ValueError):
        bench.percentile([1.0], 1.5)


@pytest.mark.parametrize(
    ("param", "expected"),
    [
        ({"type": "number", "default": 0.99}, 0.99),
        ({"type": "boolean"}, True),
        ({"type": "string"}, "x"),
        ({"type": "number", "minimum": 0.0, "maximum": 1.0}, 0.5),
        ({"type": "integer", "minimum": 1, "maximum": 10}, 6),
        ({"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1}, 0.5),
        ({"type": "number", "minimum": 0}, 1.0),
        ({"type": "number", "minimum": 5}, 6.0),
        ({"type": "number", "minimum": -3}, 0.0),
        ({"type": "number", "maximum": 10}, 5.0),
        ({"type": "number", "maximum": -2}, -3.0),
        ({"type": "number"}, 1.0),
        ({"type": "integer"}, 1),
    ],
)
def test_a_scalar_parameter_gets_a_value_inside_its_limits(param: dict, expected: object) -> None:
    value = _bench().param_value(param)
    assert value == expected
    assert type(value) is type(expected)


def test_a_payload_needs_every_required_parameter_to_be_scalar() -> None:
    bench = _bench()
    scalar = {"name": "n", "type": "integer", "required": True, "default": 3}
    optional_array = {"name": "r", "type": "array", "required": False}
    required_array = {"name": "r", "type": "array", "required": True}
    assert bench.scalar_payload([scalar, optional_array]) == {"n": 3}
    assert bench.scalar_payload([scalar, required_array]) is None
    assert bench.scalar_payload([optional_array]) == {}


@pytest.mark.parametrize(
    ("kwargs", "verdict"),
    [
        ({"status": 422, "cold_compiled": 0, "p95_ms": 5.0, "cold_ms": 300.0}, "ERROR"),
        ({"status": 0, "cold_compiled": 0, "p95_ms": 5.0, "cold_ms": None}, "ERROR"),
        ({"status": 200, "cold_compiled": 2, "p95_ms": 5.0, "cold_ms": 4000.0}, "COMPILES"),
        ({"status": 200, "cold_compiled": 1, "p95_ms": 5000.0, "cold_ms": 9000.0}, "COMPILES"),
        ({"status": 200, "cold_compiled": 0, "p95_ms": 1000.0, "cold_ms": 300.0}, "SLOW"),
        ({"status": 200, "cold_compiled": 0, "p95_ms": 50.0, "cold_ms": 1200.0}, "SLOW"),
        ({"status": 200, "cold_compiled": 0, "p95_ms": 999.9, "cold_ms": 999.9}, "ok"),
        ({"status": 200, "cold_compiled": 0, "p95_ms": 3.0, "cold_ms": None}, "ok"),
    ],
)
def test_the_verdict_puts_the_most_serious_problem_first(kwargs: dict, verdict: str) -> None:
    assert _bench().classify(**kwargs) == verdict


def test_the_lane_charges_one_unit_per_fifty_milliseconds_rounded_up() -> None:
    bench = _bench()
    assert bench.units(None) is None
    assert [bench.units(ms) for ms in (0.2, 50.0, 50.1, 100.0, 168.0, 1000.0)] == [
        1,
        1,
        2,
        2,
        4,
        20,
    ]


def test_recorded_payloads_override_the_scalar_ones_and_are_sorted(tmp_path: Path) -> None:
    bench = _bench()
    catalogue = tmp_path / "functions.json"
    catalogue.write_text(
        json.dumps(
            [
                {
                    "path": "/api/v1/d/b",
                    "params": [{"name": "x", "type": "number", "required": True, "default": 2}],
                },
                {
                    "path": "/api/v1/d/a",
                    "params": [{"name": "r", "type": "array", "required": True}],
                },
                {
                    "path": "/api/v1/d/c",
                    "params": [{"name": "x", "type": "number", "required": True, "default": 1}],
                },
            ]
        ),
        encoding="utf-8",
    )
    curated = tmp_path / "curated.json"
    curated.write_text(
        json.dumps({"/api/v1/d/a": {"r": [1, 2]}, "/api/v1/d/c": {"x": 9}}), encoding="utf-8"
    )
    payloads = bench.load_payloads(catalogue, curated)
    assert list(payloads) == ["/api/v1/d/a", "/api/v1/d/b", "/api/v1/d/c"]
    assert payloads == {
        "/api/v1/d/a": {"r": [1, 2]},
        "/api/v1/d/b": {"x": 2},
        "/api/v1/d/c": {"x": 9},
    }
    assert bench.load_payloads(catalogue, tmp_path / "absent.json")["/api/v1/d/c"] == {"x": 1}


def test_a_body_takes_scalars_from_the_limits_and_arrays_from_named_fixtures() -> None:
    bench = _bench()
    params = [
        {"name": "n", "type": "integer", "required": True, "default": 3},
        {"name": "mystery", "type": "object", "required": True},
        {"name": "extra", "type": "object", "required": False},
    ]
    assert bench.payload_from_params(params, {"mystery": [0.1, 0.2]}) == {
        "n": 3,
        "mystery": [0.1, 0.2],
    }
    assert bench.payload_from_params(params, {}) is None  # a required array nothing can supply
    # a per-function override supplies it, and also replaces a value already built
    assert bench.payload_from_params(params, {}, {"mystery": [1], "n": 9}) == {
        "n": 9,
        "mystery": [1],
    }


@pytest.mark.parametrize(
    ("name", "description", "expected"),
    [
        ("portfolio_weights", "", [0.4, 0.3, 0.3]),
        ("asset_rates", "", [0.02, 0.025, 0.03]),
        ("repricing_times", "", [1.0, 2.0, 3.0]),
        ("tenors_days", "", [30.0, 90.0, 180.0]),
        ("trade_prices", "", [100.0, 101.0, 99.0]),
        ("deposit_balances", "", [100.0, 200.0, 300.0]),
        ("from_idx_indices", "", [0, 1, 2]),
        ("thresholds", "Mapping ``name -> minimum``.", None),
        ("kri_definitions", "List of KRI definition dicts.", None),
        ("risk_register", "List of risk dicts", None),
        ("mystery_field", "", None),
        # "jurisdiction" contains the letters "dict"; it is not a dict (this once hid a function)
        (
            "country_ccyb_rates",
            "National CCyB rate per jurisdiction (decimal).",
            [0.02, 0.025, 0.03],
        ),
    ],
)
def test_an_unknown_array_is_guessed_from_its_name_and_never_from_a_mapping(
    name: str, description: str, expected: object
) -> None:
    assert _bench().guess_array(name, description) == expected


def test_the_guess_is_a_fresh_list_each_time() -> None:
    bench = _bench()
    first = bench.guess_array("weights", "")
    first.append(9.9)
    assert bench.guess_array("weights", "") == [0.4, 0.3, 0.3]


def test_the_fixtures_are_deterministic_and_have_the_shapes_the_functions_expect() -> None:
    bench = _bench()
    first, second = bench.fixture_values(), bench.fixture_values()
    assert first == second
    assert len(first["returns"]) == len(first["benchmark_returns"]) == 252
    assert len(first["returns_matrix"]) == 252 and {
        len(row) for row in first["returns_matrix"]
    } == {3}
    assert {len(row) for row in first["factors"]} == {3}
    assert {len(row) for row in first["factors_4"]} == {4}
    assert {len(row) for row in first["factors_5"]} == {5}
    cov = first["cov_matrix"]
    assert len(cov) == 3 and all(len(row) == 3 for row in cov)
    assert all(cov[i][j] == cov[j][i] for i in range(3) for j in range(3))
    assert len(first["weights"]) == 3 and sum(first["weights"]) == pytest.approx(1.0)
    assert len(first["breaches"]) == 250 and sum(first["breaches"]) == 3


def test_every_body_override_names_a_real_route_and_real_parameters() -> None:
    bench = _bench()
    catalogue = {f["path"]: f for f in json.loads(bench.CATALOGUE.read_text(encoding="utf-8"))}
    overrides = bench.body_overrides(bench.fixture_values())
    assert overrides
    for path, values in overrides.items():
        assert path in catalogue, f"override for a route that is not in the catalogue: {path}"
        known = {p["name"] for p in catalogue[path]["params"]}
        assert set(values) <= known, f"{path}: override names parameters the function does not have"


def test_every_built_payload_answers_200_so_a_changed_rule_cannot_silently_drop_a_function() -> (
    None
):
    bench = _bench()
    payloads = bench.load_payloads()
    catalogue = {f["path"] for f in json.loads(bench.CATALOGUE.read_text(encoding="utf-8"))}
    assert set(payloads) == catalogue, (
        "every catalogue function needs a payload: missing "
        f"{sorted(catalogue - set(payloads))[:5]}, extra {sorted(set(payloads) - catalogue)[:5]}"
    )
    assert "/api/v1/market-risk/historical_simulation_var" in payloads

    async def run() -> dict[str, int]:
        async with bench._client() as (client, headers):
            return {
                path: (await client.post(path, json=body, headers=headers)).status_code
                for path, body in payloads.items()
            }

    refused = {path: code for path, code in asyncio.run(run()).items() if code != 200}
    assert not refused, f"payloads the app now refuses (fix the fixture or the override): {refused}"


def test_every_recorded_payload_is_still_a_post_route_of_the_app() -> None:
    from main import create_app

    bench = _bench()
    recorded = json.loads(bench.CURATED.read_text(encoding="utf-8"))
    assert recorded, "scripts/trial_bench_payloads.json is empty; regenerate it with --harvest"
    paths = create_app().openapi()["paths"]
    gone = [p for p in recorded if "post" not in paths.get(p, {})]
    assert (
        not gone
    ), f"recorded payloads for routes that no longer exist (regenerate with --harvest): {gone}"


def test_the_compile_counter_sees_a_kernel_compile_exactly_once() -> None:
    # A known-positive control for the detector that marks a function COMPILES: a fresh kernel, no cache.
    numba = pytest.importorskip("numba")
    bench = _bench()

    @numba.njit(cache=False)
    def doubled(x: float) -> float:
        return x * 2.0

    before = bench._numba_compiles()
    doubled(1.0)
    after_first = bench._numba_compiles()
    doubled(2.0)
    assert after_first - before == 1
    assert bench._numba_compiles() == after_first


def test_the_benchmark_leaves_logging_as_it_found_it() -> None:
    # logging.disable is process-wide. Left on, it made a later test that reads caplog fail in CI
    # (tests/test_var_jobs_reconciler.py::test_the_loop_survives_an_error_and_keeps_going).
    import logging

    bench = _bench()
    before = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    try:

        async def inside() -> int:
            async with bench._client():
                return int(logging.root.manager.disable)

        assert asyncio.run(inside()) == logging.CRITICAL
        assert logging.root.manager.disable == logging.NOTSET
    finally:
        logging.disable(before)


def test_the_warm_pass_calls_the_real_route_and_reports_percentiles() -> None:
    bench = _bench()
    body = json.loads(bench.CURATED.read_text(encoding="utf-8"))[_CHEAP_ROUTE]
    result = asyncio.run(
        bench.measure_warm({_CHEAP_ROUTE: body, "/api/v1/liquidity/no_such_route": {}}, 3)
    )
    good = result[_CHEAP_ROUTE]
    assert good["status"] == 200
    assert 0 < good["p50_ms"] <= good["p95_ms"] <= good["max_ms"]
    assert result["/api/v1/liquidity/no_such_route"] == {"status": 404}


def test_the_fresh_process_pass_reports_the_first_call_and_no_compile_for_a_closed_form_route() -> (
    None
):
    bench = _bench()
    body = json.loads(bench.CURATED.read_text(encoding="utf-8"))[_CHEAP_ROUTE]
    result = bench._run_child(_CHEAP_ROUTE, body)
    assert result["status"] == 200, result
    assert result["cold_ms"] > 0
    assert result["cold_compiled"] == 0

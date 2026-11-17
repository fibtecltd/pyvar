#!/usr/bin/env python3
"""scripts/trial_weight_bench.py — which pyvar functions are cheap enough for the trial lane.

Reasoning:
- The A3 trial lane (docs/plan-trial-lane-throttle.md) runs a whitelist of inline functions and charges
  the compute budget by the measured wall time of each call (owner decision 2026-11-17), with a hard
  deadline of one second per call. dev's api_usage cannot size anything (docs/p9-aws-evidence-2026-11-13.md
  section 14), so the whitelist is chosen from this benchmark instead.
- Two things matter and they need different measurements:
  1. Warm cost: p50, p95 and max of repeated calls in one process, as the route is served in steady state.
  2. The FIRST call in a fresh API task. The image pre-bakes the Numba cache of one kernel
     (run_monte_carlo_var) and the lifespan warms only that one, so any other @njit kernel is compiled by
     the first request that needs it, seconds on the event loop. A shared process would hide that after
     the first function that happened to compile a kernel, so each function's first call runs in its OWN
     subprocess with an empty Numba cache and the same warm-up the lifespan does, and counts the kernels
     Numba compiled during that call.
- Payloads: the portal catalogue (portal/functions.json) has no example values, so a request is built from
  each function's required scalar parameters (default, else the middle of its limits) and kept only if the
  route answers 200. Functions that need arrays or objects take the payloads in scripts/trial_bench_payloads.json,
  recorded from the existing domain API tests (every one answered 200 there; regenerate with --harvest).
  Test payloads are small: a real caller can send more, which the lane bounds with a body-size cap, an array-length
  cap and the one-second deadline, not with this table.
- Calls go through the real app in process (create_app() behind httpx's ASGITransport, as tests/ do): auth, rate-limit
  and response middleware included, no network, no database, no AWS. The usage-row write is replaced by a no-op.
- Times are from the machine that runs it. Run it in the dev image (a one-off task) for Fargate numbers.

Usage (from the repo root, with the app dependencies and CI's environment variables:
APP_ENV=test JWT_SECRET=... CELERY_BROKER_URL=redis://localhost:6379/0 REDIS_URL=redis://localhost:6379/0):
    python scripts/trial_weight_bench.py                    # all functions with a payload, 30 warm calls each
    python scripts/trial_weight_bench.py --only market-risk --calls 50 --json /tmp/bench.json
    python scripts/trial_weight_bench.py --harvest          # rewrite scripts/trial_bench_payloads.json from the tests
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import logging
import math
import os
import subprocess  # nosec B404
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CATALOGUE = ROOT / "portal" / "functions.json"
CURATED = ROOT / "scripts" / "trial_bench_payloads.json"
DOMAIN_TESTS = (
    "tests/test_alm_api.py",
    "tests/test_credit_risk_api.py",
    "tests/test_derivatives_api.py",
    "tests/test_liquidity_api.py",
    "tests/test_market_risk_api.py",
    "tests/test_operational_api.py",
    "tests/test_portfolio_api.py",
    "tests/test_regulatory_api.py",
)

DEADLINE_MS = 1000.0  # the lane's hard per-call deadline
UNIT_MS = 50.0  # one compute unit of the lane's budget
SCALAR_TYPES = frozenset({"number", "integer", "boolean", "string"})
RESULT_PREFIX = "RESULT "


# ── pure helpers (unit-tested) ────────────────────────────────────────────────


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolation percentile of `values` (q in [0, 1]).

    Args:
        values: At least one number.
        q: The quantile, 0.5 for the median.

    Returns:
        The interpolated value.

    Raises:
        ValueError: If `values` is empty or q is outside [0, 1].
    """
    if not values:
        raise ValueError("percentile of an empty list")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (pos - low))


def param_value(param: dict[str, Any]) -> Any:
    """A valid-looking value for one scalar parameter of the catalogue.

    The default if there is one, else the middle of the limits, else a value one step inside
    a single limit, else 1.

    Args:
        param: One entry of a function's "params" in portal/functions.json.

    Returns:
        A bool, str, int or float.
    """
    kind = param["type"]
    if param.get("default") is not None:
        return param["default"]
    if kind == "boolean":
        return True
    if kind == "string":
        return "x"
    low = (
        param.get("minimum") if param.get("minimum") is not None else param.get("exclusiveMinimum")
    )
    high = (
        param.get("maximum") if param.get("maximum") is not None else param.get("exclusiveMaximum")
    )
    if low is not None and high is not None:
        value = (low + high) / 2
    elif low is not None:
        value = low + 1 if low >= 0 else 0.0
        value = value if low != 0 else 1.0
    elif high is not None:
        value = high / 2 if high > 0 else high - 1
    else:
        value = 1.0
    return int(round(value)) if kind == "integer" else float(value)


def scalar_payload(params: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A request body from the required scalar parameters, or None if any required one is an array or object.

    Args:
        params: A function's "params" from portal/functions.json.

    Returns:
        The body, or None when the function cannot be called from scalars alone.
    """
    required = [p for p in params if p.get("required")]
    if any(p["type"] not in SCALAR_TYPES for p in required):
        return None
    return {p["name"]: param_value(p) for p in required}


def classify(
    *, status: int, cold_compiled: int, p95_ms: float | None, cold_ms: float | None
) -> str:
    """One verdict per function, most serious first.

    Args:
        status: HTTP status of the calls (200 expected).
        cold_compiled: Numba kernels compiled during the first call of a fresh process.
        p95_ms: p95 of the warm calls, None if there were none.
        cold_ms: Duration of the first call in a fresh process, None if not measured.

    Returns:
        "ERROR" (not 200), "COMPILES" (a first call compiles a kernel), "SLOW" (p95 or the first
        call reaches the deadline) or "ok".
    """
    if status != 200:
        return "ERROR"
    if cold_compiled > 0:
        return "COMPILES"
    if (p95_ms is not None and p95_ms >= DEADLINE_MS) or (
        cold_ms is not None and cold_ms >= DEADLINE_MS
    ):
        return "SLOW"
    return "ok"


def units(ms: float | None) -> int | None:
    """The lane's charge for a call of `ms` milliseconds: ceil(ms / 50), at least 1."""
    return None if ms is None else max(1, math.ceil(ms / UNIT_MS))


def fixture_values() -> dict[str, Any]:
    """Deterministic values for array and matrix parameters, by parameter name.

    One year of daily observations (T = 252) on three assets (N = 3), a small covariance matrix, a
    three-bucket curve and a three-name credit book: enough to make the common risk functions answer
    200. The catalogue types every non-scalar parameter "object", so the name is the only guide; a
    function whose arrays need another shape is left out (or takes a recorded payload) and shows up
    as ERROR, not as a verdict about the function.
    """
    from ingestion.fixtures import generate_gbm_returns

    series = [generate_gbm_returns(n_obs=252, seed=seed).tolist() for seed in (1, 2, 3)]
    matrix = [list(row) for row in zip(*series, strict=True)]  # (T, N)
    factor_series = [generate_gbm_returns(n_obs=252, seed=seed).tolist() for seed in range(11, 16)]
    factors = [list(row) for row in zip(*factor_series[:3], strict=True)]  # (T, 3)
    breaches = [1 if day in (40, 120, 200) else 0 for day in range(250)]
    weights = [0.4, 0.3, 0.3]
    cov = [[0.04, 0.01, 0.0], [0.01, 0.05, 0.01], [0.0, 0.01, 0.06]]
    book = [1_000_000.0, 2_000_000.0, 500_000.0]
    return {
        "returns": series[0],
        "portfolio_returns": series[0],
        "benchmark_returns": series[1],
        "excess_returns": series[0],
        "hypothetical_pnl": series[0],
        "risk_theoretical_pnl": series[1],
        "returns_matrix": matrix,
        "factors": factors,
        "factors_4": [list(row) for row in zip(*factor_series[:4], strict=True)],
        "factors_5": [list(row) for row in zip(*factor_series, strict=True)],
        "factor_cov": cov,
        "cov_matrix": cov,
        "weights": weights,
        "portfolio_weights": weights,
        "benchmark_weights": weights,
        "mean_returns": [0.08, 0.10, 0.12],
        "breaches": breaches,
        "sorted_losses": sorted(abs(x) * 1_000_000 for x in series[0][:100]),
        "annual_losses": [abs(x) * 5_000_000 + 10_000 for x in series[0][:50]],
        "annual_event_counts": [3, 5, 2, 4, 6, 3, 1, 4, 5, 2, 3, 4, 2, 5, 3, 4, 6, 2, 3, 4],
        "loss_amounts": [abs(x) * 2_000_000 + 5_000 for x in series[0][:200]],
        "cashflows": [100.0, 100.0, 1100.0],
        "times": [1.0, 2.0, 3.0],
        "discount_factors": [0.97, 0.94, 0.91],
        "time_steps": [1.0, 2.0, 3.0],
        "expected_exposure": [10.0, 12.0, 8.0],
        "maturities": [1.0, 2.0, 3.0, 4.0, 5.0],
        "yields": [0.02, 0.025, 0.03, 0.032, 0.034],
        "tenors": [1.0, 2.0, 5.0, 10.0],
        "base_curve": [0.02, 0.025, 0.03, 0.034],
        "liquidity_spreads": [0.001, 0.002, 0.003, 0.004],
        "pd": [0.01, 0.02, 0.05],
        "lgd": [0.45, 0.4, 0.6],
        "ead": book,
        "exposures": book,
        "exposure_amounts": book,
        "recovery_amounts": [400_000.0, 800_000.0, 250_000.0],
        "asset_values": [100.0, 200.0, 150.0],
        "asset_balances": [100.0, 200.0, 300.0],
        "asset_rates": [0.02, 0.03, 0.04],
        "liability_balances": [150.0, 250.0, 200.0],
        "liability_rates": [0.015, 0.025, 0.035],
        "bucket_assets": [100.0, 150.0, 200.0],
        "bucket_liabilities": [120.0, 140.0, 160.0],
        "net_cashflows": [10.0, -5.0, 20.0],
        "base_rates": [0.02, 0.025, 0.03],
        "forward_rates": [0.03, 0.031, 0.032],
        "accruals": [0.25, 0.25, 0.25],
        "funding_amounts": [100.0, 200.0, 300.0],
    }


def payload_from_params(
    params: list[dict[str, Any]], fixtures: dict[str, Any]
) -> dict[str, Any] | None:
    """A request body from the required parameters: scalars by `param_value`, arrays by name from `fixtures`.

    Args:
        params: A function's "params" from portal/functions.json.
        fixtures: Values by parameter name for the non-scalar parameters (see `fixture_values`).

    Returns:
        The body, or None when a required non-scalar parameter has no fixture.
    """
    body: dict[str, Any] = {}
    for param in params:
        if not param.get("required"):
            continue
        if param["type"] in SCALAR_TYPES:
            body[param["name"]] = param_value(param)
        elif param["name"] in fixtures:
            body[param["name"]] = fixtures[param["name"]]
        else:
            return None
    return body


def body_overrides(fixtures: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Values that replace the built ones for functions with rules the catalogue does not state.

    Several scalar parameters carry no default or limit in portal/functions.json, so the generic value
    (1.0) is outside the function's own domain (a probability of 1, a start after an end, a stress window
    that does not exist). Each entry below was needed to turn a 422 into a 200 and is a plain value of the
    kind the function's documentation gives as an example.
    """
    curve_t = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
    return {
        "/api/v1/alm/loan_prepayment_rate_cpr": {"cpr": 0.06},
        "/api/v1/alm/prepayment_model_mortgages": {
            "principal": 250_000.0,
            "annual_rate": 0.04,
            "term_years": 30,
            "cpr": 0.06,
        },
        "/api/v1/credit-risk/credit_var_analytical_vasicek": {
            "pd": 0.02,
            "lgd": 0.45,
            "ead_total": 1_000_000.0,
        },
        "/api/v1/credit-risk/point_in_time_pd_estimation": {"ttc_pd": 0.02, "macro_index": 0.5},
        "/api/v1/credit-risk/through_the_cycle_pd_adjustment": {
            "pit_pd": 0.03,
            "long_run_average_pd": 0.02,
        },
        "/api/v1/derivatives/chooser_option_pricer": {"tau_choose": 0.5, "tau_expiry": 1.0},
        "/api/v1/derivatives/compound_option_pricer": {"tau_compound": 0.5, "tau_underlying": 1.0},
        "/api/v1/derivatives/credit_default_swap_cds_pricer": {
            "notional": 1_000_000.0,
            "spread": 0.01,
            "hazard_rate": 0.02,
            "recovery_rate": 0.4,
            "maturity": 5.0,
            "discount_rate": 0.03,
        },
        "/api/v1/derivatives/forward_rate_agreement_fra": {
            "notional": 1_000_000.0,
            "fra_rate": 0.03,
            "forward_rate": 0.031,
            "start": 1.0,
            "end": 1.5,
            "discount_factor": 0.97,
        },
        "/api/v1/derivatives/nelson_siegel_svensson_curve": {
            "maturities": curve_t,
            "yields": [0.02, 0.022, 0.024, 0.027, 0.029, 0.032, 0.034, 0.035],
        },
        "/api/v1/derivatives/swap_rate_curve": {
            "maturities": [1.0, 2.0, 3.0, 4.0, 5.0],
            "discount_factors": [0.98, 0.96, 0.94, 0.92, 0.90],
        },
        "/api/v1/derivatives/yield_to_maturity": {
            "price": 98.0,
            "cashflows": [5.0, 5.0, 105.0],
            "times": [1.0, 2.0, 3.0],
        },
        "/api/v1/market-risk/compute_cvar": {"confidence_level": 0.99},
        "/api/v1/market-risk/stressed_expected_shortfall": {
            "stress_start": 10,
            "stress_end": 60,
            "portfolio_value": 1_000_000.0,
        },
        "/api/v1/operational/scenario_severity_estimation": {
            "typical_loss": 10_000.0,
            "worst_case_loss": 500_000.0,
        },
        "/api/v1/portfolio/carhart_4_factor_model": {"factors": fixtures["factors_4"]},
        "/api/v1/portfolio/fama_french_5_factor_model": {"factors": fixtures["factors_5"]},
        "/api/v1/portfolio/return_attribution_brinson": {
            "portfolio_returns": [0.05, 0.02, 0.03],
            "benchmark_returns": [0.04, 0.03, 0.02],
        },
        "/api/v1/portfolio/sector_attribution": {
            "portfolio_returns": [0.05, 0.02, 0.03],
            "benchmark_returns": [0.04, 0.03, 0.02],
        },
    }


def load_payloads(
    catalogue: Path = CATALOGUE, curated: Path = CURATED
) -> dict[str, dict[str, Any]]:
    """Request bodies by route: built from the catalogue (scalars and named fixtures), then the recorded ones on top.

    Args:
        catalogue: portal/functions.json.
        curated: scripts/trial_bench_payloads.json (may be absent).

    Returns:
        A dict route path to JSON body, sorted by path.
    """
    payloads: dict[str, dict[str, Any]] = {}
    fixtures = fixture_values()
    overrides = body_overrides(fixtures)
    for function in json.loads(catalogue.read_text(encoding="utf-8")):
        body = payload_from_params(function["params"], fixtures)
        if body is not None:
            payloads[function["path"]] = {**body, **overrides.get(function["path"], {})}
    if curated.exists():
        payloads.update(json.loads(curated.read_text(encoding="utf-8")))
    return dict(sorted(payloads.items()))


# ── measuring (needs the app) ─────────────────────────────────────────────────


def _numba_compiles() -> int:
    """Kernels Numba has compiled so far in this process (cache misses over every dispatcher)."""
    try:
        from numba.core.dispatcher import Dispatcher
    except ImportError:
        return 0
    return sum(
        sum(obj.stats.cache_misses.values())
        for obj in gc.get_objects()
        if isinstance(obj, Dispatcher)
    )


def _warm_up_like_the_lifespan() -> None:
    """What main.py's lifespan runs before serving: one tiny Monte Carlo VaR."""
    import numpy as np

    from engine.montecarlo import run_monte_carlo_var

    run_monte_carlo_var(
        np.random.randn(30) * 0.01, portfolio_value=1.0, n_simulations=1_000, seed=0
    )


@asynccontextmanager
async def _client() -> AsyncIterator[tuple[Any, dict[str, str]]]:
    """The real app behind an in-process transport, an enterprise token, no usage-row write."""
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from api.middleware.auth import create_access_token
    from main import create_app

    async def _no_usage_row(*_args: Any, **_kwargs: Any) -> None:
        return None

    logging.disable(logging.CRITICAL)
    headers = {"Authorization": f"Bearer {create_access_token('trial-bench', 'enterprise')}"}
    with patch("api.middleware.usage._persist_usage", _no_usage_row):
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://bench"
        ) as client:
            yield client, headers


async def _timed_post(
    client: Any, headers: dict[str, str], path: str, body: dict[str, Any]
) -> tuple[int, float]:
    start = time.perf_counter()
    response = await client.post(path, json=body, headers=headers)
    return int(response.status_code), (time.perf_counter() - start) * 1000.0


async def measure_warm(
    payloads: dict[str, dict[str, Any]], calls: int
) -> dict[str, dict[str, Any]]:
    """Warm timings in one shared process: one unmeasured call, then `calls` measured ones per route.

    Args:
        payloads: Route path to body.
        calls: Measured calls per route.

    Returns:
        Route path to {"status", "p50_ms", "p95_ms", "max_ms"}; a route that does not answer 200 on its
        first call has only "status".
    """
    results: dict[str, dict[str, Any]] = {}
    async with _client() as (client, headers):
        for path, body in payloads.items():
            status, _ = await _timed_post(client, headers, path, body)
            if status != 200:
                results[path] = {"status": status}
                continue
            times = [(await _timed_post(client, headers, path, body))[1] for _ in range(calls)]
            results[path] = {
                "status": 200,
                "p50_ms": percentile(times, 0.5),
                "p95_ms": percentile(times, 0.95),
                "max_ms": max(times),
            }
    return results


async def _child(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """First call of one route in a fresh process: its duration and the kernels it compiled."""
    _warm_up_like_the_lifespan()
    async with _client() as (client, headers):
        before = _numba_compiles()
        status, ms = await _timed_post(client, headers, path, body)
        return {
            "path": path,
            "status": status,
            "cold_ms": ms,
            "cold_compiled": _numba_compiles() - before,
        }


def _run_child(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """Run the first call of `path` in a subprocess with an empty Numba cache."""
    with tempfile.TemporaryDirectory(prefix="trial-bench-numba-") as cache_dir:
        env = {**os.environ, "NUMBA_CACHE_DIR": cache_dir, "PYTHONPATH": str(ROOT)}
        # Fixed argument list (this interpreter, this file, a route path and a JSON body), no shell.
        proc = subprocess.run(  # nosec B603
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--child",
                path,
                "--child-body",
                json.dumps(body),
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=300,
            check=False,
        )
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(RESULT_PREFIX):
            return dict(json.loads(line[len(RESULT_PREFIX) :]))
    return {
        "path": path,
        "status": 0,
        "cold_ms": None,
        "cold_compiled": 0,
        "error": proc.stderr[-300:],
    }


def measure_cold(payloads: dict[str, dict[str, Any]], workers: int) -> dict[str, dict[str, Any]]:
    """First-call measurement of every route, each in its own subprocess, `workers` at a time."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {path: pool.submit(_run_child, path, body) for path, body in payloads.items()}
        return {path: future.result() for path, future in futures.items()}


def harvest(out: Path) -> int:
    """Record every 200-answered POST body of the domain API tests into `out`.

    Args:
        out: The file to write (scripts/trial_bench_payloads.json).

    Returns:
        The number of routes recorded.
    """
    import httpx
    import pytest

    records: dict[str, dict[str, Any]] = {}

    def note(method: str, url: Any, kwargs: dict[str, Any], response: Any) -> Any:
        path = httpx.URL(str(url)).path
        body = kwargs.get("json")
        if (
            method.upper() == "POST"
            and path.startswith("/api/v1/")
            and response.status_code == 200
            and isinstance(body, dict)
            and body
            and path not in records
            and len(json.dumps(body)) < 200_000
        ):
            records[path] = body
        return response

    sync_request, async_request = httpx.Client.request, httpx.AsyncClient.request

    def request(self: Any, method: str, url: Any, *args: Any, **kwargs: Any) -> Any:
        return note(method, url, kwargs, sync_request(self, method, url, *args, **kwargs))

    async def arequest(self: Any, method: str, url: Any, *args: Any, **kwargs: Any) -> Any:
        return note(method, url, kwargs, await async_request(self, method, url, *args, **kwargs))

    httpx.Client.request, httpx.AsyncClient.request = request, arequest  # type: ignore[method-assign]
    try:
        pytest.main(["-q", "-p", "no:cacheprovider", *[str(ROOT / t) for t in DOMAIN_TESTS]])
    finally:
        httpx.Client.request, httpx.AsyncClient.request = sync_request, async_request  # type: ignore[method-assign]
    ordered = dict(sorted(records.items()))
    out.write_text(
        "{\n"
        + ",\n".join(
            f"{json.dumps(k)}: {json.dumps(v, separators=(',', ':'))}" for k, v in ordered.items()
        )
        + "\n}\n",
        encoding="utf-8",
    )
    return len(ordered)


# ── report ─────────────────────────────────────────────────────────────────────


def build_rows(
    warm: dict[str, dict[str, Any]], cold: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge the two passes into one row per route, with a verdict and the lane's unit charge."""
    rows = []
    for path in sorted(warm):
        w, c = warm[path], cold.get(path, {})
        status = int(w["status"])
        if status == 200 and c:
            status = int(c.get("status") or 0)  # 0: the fresh-process run produced no result
        row: dict[str, Any] = {
            "path": path,
            "status": status,
            "first_ms": c.get("cold_ms"),
            "compiled": int(c.get("cold_compiled", 0)),
            "p50_ms": w.get("p50_ms"),
            "p95_ms": w.get("p95_ms"),
            "max_ms": w.get("max_ms"),
        }
        row["units_p95"] = units(row["p95_ms"])
        row["verdict"] = classify(
            status=status,
            cold_compiled=row["compiled"],
            p95_ms=row["p95_ms"],
            cold_ms=row["first_ms"],
        )
        rows.append(row)
    return rows


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def print_report(rows: list[dict[str, Any]]) -> None:
    """A fixed-width table, slowest first, then the counts and the whitelist candidates."""
    print(
        f"{'route':64} {'status':>6} {'first':>8} {'comp':>4} {'p50':>7} {'p95':>7} {'max':>7} {'units':>5}  verdict"
    )
    for row in sorted(rows, key=lambda r: -(r["p95_ms"] or 0)):
        route = row["path"].removeprefix("/api/v1/")
        print(
            f"{route:64} {row['status']:>6} {_fmt(row['first_ms']):>8} {row['compiled']:>4} {_fmt(row['p50_ms']):>7} "
            f"{_fmt(row['p95_ms']):>7} {_fmt(row['max_ms']):>7} {row['units_p95'] or '-':>5}  {row['verdict']}"
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    print(
        "\n"
        + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        + f" (of {len(rows)} functions)"
    )
    print(
        "times in ms; first = first call in a fresh process; comp = Numba kernels compiled by that call; "
        f"units = ceil(p95 / {UNIT_MS:.0f}); deadline {DEADLINE_MS:.0f} ms"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark pyvar functions for the trial lane whitelist."
    )
    parser.add_argument(
        "--calls", type=int, default=30, help="measured warm calls per function (default 30)"
    )
    parser.add_argument("--only", default="", help="keep routes whose path contains this text")
    parser.add_argument(
        "--workers", type=int, default=3, help="parallel fresh-process first-call runs (default 3)"
    )
    parser.add_argument("--json", type=Path, help="also write the rows to this file")
    parser.add_argument(
        "--harvest", action="store_true", help="rewrite the recorded payloads from the API tests"
    )
    parser.add_argument("--child", help=argparse.SUPPRESS)
    parser.add_argument("--child-body", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.child:
        result = asyncio.run(_child(args.child, json.loads(args.child_body)))
        print(RESULT_PREFIX + json.dumps(result))
        return 0
    if args.harvest:
        print(f"recorded {harvest(CURATED)} payloads in {CURATED.relative_to(ROOT)}")
        return 0

    payloads = {p: b for p, b in load_payloads().items() if args.only in p}
    if not payloads:
        print("no function matches", file=sys.stderr)
        return 2
    print(f"{len(payloads)} functions; warm pass ({args.calls} calls each) ...", file=sys.stderr)
    warm = asyncio.run(measure_warm(payloads, args.calls))
    ok_payloads = {p: payloads[p] for p, w in warm.items() if w["status"] == 200}
    print(
        f"first-call pass in {len(ok_payloads)} fresh processes ({args.workers} at a time) ...",
        file=sys.stderr,
    )
    cold = measure_cold(ok_payloads, args.workers)
    rows = build_rows(warm, cold)
    print_report(rows)
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
import re
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


# Second-level guesses for array parameters no fixture names, by the parameter's own name (first match wins).
# Every array has length 3 so that coupled arrays (rates and times, balances and rates) agree in length.
_GUESS_RULES: tuple[tuple[tuple[str, ...], list[float]], ...] = (
    (("weights",), [0.4, 0.3, 0.3]),
    (("multipliers",), [1.5, 2.0, 2.5]),
    (
        ("probabilit", "haircuts", "_factors", "scores", "runoff", "rollover", "stability"),
        [0.1, 0.2, 0.3],
    ),
    (("rates", "spreads", "vols", "sigmas", "yields", "growth", "shifts"), [0.02, 0.025, 0.03]),
    (("_days",), [30.0, 90.0, 180.0]),
    (("times", "tenors", "maturities", "expiries", "durations"), [1.0, 2.0, 3.0]),
    (("prices", "spots"), [100.0, 101.0, 99.0]),
    (
        ("returns", "shocks", "moves", "deltas", "sensitivities", "pnl", "gammas"),
        [0.01, -0.02, 0.015],
    ),
    (
        (
            "amounts",
            "balances",
            "values",
            "notionals",
            "exposures",
            "capital",
            "charges",
            "inflows",
            "outflows",
            "losses",
            "addons",
            "ses",
            "quantities",
            "cs01",
            "vegas",
            "profile",
            "history",
        ),
        [100.0, 200.0, 300.0],
    ),
    (("indices", "codes"), [0, 1, 2]),
)


def guess_array(name: str, description: str) -> list[float] | None:
    """A length-3 list for an array parameter, from the words in its name; None for mappings and lists of records.

    Args:
        name: The parameter name.
        description: Its catalogue description (used only to refuse mappings and lists of records).

    Returns:
        A new list, or None when no rule fits or the description says it is a mapping or a list of dicts.
    """
    text = description.lower()
    if re.search(r"\bmapping\b|\blist of\b|\bdicts?\b", text):
        return None
    lowered = name.lower()
    for words, value in _GUESS_RULES:
        if any(word in lowered for word in words):
            return list(value)
    return None


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
    params: list[dict[str, Any]],
    fixtures: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """A request body from the required parameters.

    Scalars come from `param_value`; arrays by name from `overrides`, then `fixtures`, then
    `guess_array`; `overrides` also replace any value already built.

    Args:
        params: A function's "params" from portal/functions.json.
        fixtures: Values by parameter name for the non-scalar parameters (see `fixture_values`).
        overrides: Values for this one function (see `body_overrides`).

    Returns:
        The body, or None when a required non-scalar parameter has no value.
    """
    given = overrides or {}
    body: dict[str, Any] = {}
    for param in params:
        if not param.get("required"):
            continue
        name = param["name"]
        if param["type"] in SCALAR_TYPES:
            body[name] = param_value(param)
        elif name in given:
            body[name] = given[name]
        elif name in fixtures:
            body[name] = fixtures[name]
        else:
            guessed = guess_array(name, param.get("description", ""))
            if guessed is None:
                return None
            body[name] = guessed
    body.update(given)
    return body


def body_overrides(fixtures: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Values that replace the built ones for functions with rules the catalogue does not state.

    Several scalar parameters carry no default or limit in portal/functions.json, so the generic value
    (1.0) is outside the function's own domain (a probability of 1, a start after an end, a stress window
    that does not exist). Each entry below was needed to turn a 422 into a 200 and is a plain value of the
    kind the function's documentation gives as an example.
    """
    curve_t = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
    corr = [[1.0, 0.3, 0.2], [0.3, 1.0, 0.1], [0.2, 0.1, 1.0]]
    lei, lei2 = "5493001KJTIIGC8Y1R12", "529900T8BM49AURSDO55"
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
        "/api/v1/derivatives/z_spread_calculator": {
            "price": 98.0,
            "cashflows": [5.0, 5.0, 105.0],
            "times": [1.0, 2.0, 3.0],
            "zero_rates": [0.02, 0.025, 0.03],
        },
        "/api/v1/liquidity/cash_flow_ladder_1_year": {
            "bucket_inflows": [100.0] * 8,
            "bucket_outflows": [80.0] * 8,
        },
        "/api/v1/liquidity/cash_flow_ladder_30_day": {
            "daily_inflows": [10.0] * 30,
            "daily_outflows": [8.0] * 30,
        },
        "/api/v1/liquidity/liquidity_gap_analysis": {
            "asset_maturities": [100.0] * 8,
            "liability_maturities": [90.0] * 8,
        },
        "/api/v1/market-risk/dv01_pv01_bucketed": {
            "cashflows": [5.0, 5.0, 105.0],
            "times": [1.0, 2.0, 3.0],
            "flat_yield": 0.03,
            "bucket_indices": [0, 1, 2],
            "n_buckets": 3,
        },
        "/api/v1/credit-risk/credit_spread_curve_bootstrap": {
            "tenors": [1.0, 2.0, 5.0, 10.0],
            "par_spreads": [0.01, 0.012, 0.014, 0.016],
        },
        "/api/v1/derivatives/bond_pricer_floating_rate": {
            "face_value": 100.0,
            "spread": 0.01,
            "maturity": 1.0,
            "frequency": 4,
            "reference_rates": [0.02, 0.021, 0.022, 0.023],
            "discount_rates": [0.02, 0.021, 0.022, 0.023],
        },
        "/api/v1/derivatives/bootstrap_yield_curve": {
            "par_rates": [0.02, 0.025, 0.03, 0.032, 0.034],
        },
        "/api/v1/derivatives/ois_curve_sonia_sofr": {
            "ois_rates": [0.02, 0.025, 0.03, 0.032, 0.034],
        },
        "/api/v1/market-risk/expected_shortfall_contribution": {
            "asset_returns": fixtures["returns_matrix"],
        },
        "/api/v1/market-risk/frtb_sa_sensitivity_based_method": {
            "bucket_weighted_sensitivities": [[0.01, -0.02, 0.015], [0.02, 0.01, -0.01]],
        },
        "/api/v1/market-risk/historical_scenario_replay": {
            "historical_factor_returns": fixtures["factors"],
        },
        "/api/v1/portfolio/cvar_constrained_optimisation": {
            "scenario_returns": fixtures["returns_matrix"],
        },
        "/api/v1/portfolio/factor_exposure_analysis_barra": {
            "asset_exposures": [[1.0, 0.2], [0.8, 0.1], [0.5, -0.2]],
        },
        "/api/v1/portfolio/gics_sector_exposure": {
            "sector_codes": ["Energy", "Financials", "Technology"],
        },
        # --- functions whose inputs are mappings, lists of records or matrices of a stated shape ---
        "/api/v1/alm/economic_value_of_equity_eve": {
            "asset_cashflows": [100.0, 100.0, 100.0],
            "liability_cashflows": [90.0, 90.0, 90.0],
        },
        "/api/v1/alm/irrbb_internal_model": {
            "rate_scenarios": [[0.01, 0.01, 0.01], [-0.01, -0.01, -0.01]],
        },
        "/api/v1/alm/repricing_maturity_profile": {
            "bucket_edges": [0.0, 1.0, 3.0, 10.0],
            "n_buckets": 3,
        },
        "/api/v1/alm/structural_hedge_optimisation": {"instrument_max_notional": [1000.0] * 3},
        "/api/v1/credit-risk/debt_valuation_adjustment_dva": {
            "expected_negative_exposure": [10.0, 12.0, 8.0],
        },
        "/api/v1/credit-risk/default_correlation_matrix": {"asset_correlation": corr},
        "/api/v1/credit-risk/ifrs_9_lifetime_ecl_stage_2_3": {"marginal_pd": [0.01, 0.012, 0.014]},
        "/api/v1/credit-risk/ifrs_9_scenario_weighted_ecl": {
            "scenario_ecls": [100.0, 150.0, 300.0]
        },
        "/api/v1/credit-risk/logistic_regression_pd_model": {
            "features": [[((i * 7) % 10) / 10.0, ((i * 3) % 10) / 10.0] for i in range(40)],
            "defaults": [1 if i % 10 >= 7 else 0 for i in range(40)],
        },
        "/api/v1/credit-risk/machine_learning_pd_calibration": {
            "raw_scores": [((i * 7) % 40) / 40.0 for i in range(40)],
            "defaults": [1 if (i * 7) % 40 >= 28 else 0 for i in range(40)],
        },
        "/api/v1/credit-risk/probability_of_default_pd_estimation": {
            "n_defaults": [2, 5, 10],
            "n_obligors": [1000, 800, 500],
        },
        "/api/v1/credit-risk/ratings_migration_matrix": {
            "from_rating": [0, 1, 2, 0, 1, 2, 0, 1, 2, 0],
            "to_rating": [0, 1, 2, 1, 1, 2, 0, 2, 2, 0],
            "n_states": 3,
        },
        "/api/v1/credit-risk/retail_scorecard_pd_model": {
            "feature_values": [1, 0, 1],
            "points_per_feature": [10.0, 20.0, 30.0],
        },
        "/api/v1/credit-risk/sector_default_rate_analysis": {
            "sector_defaults": [2, 5, 3],
            "sector_obligors": [100, 200, 150],
        },
        "/api/v1/derivatives/basket_option_pricer": {
            "correlation": corr,
            "sigmas": [0.2, 0.25, 0.3],
        },
        "/api/v1/derivatives/rainbow_option_pricer": {
            "correlation": corr,
            "sigmas": [0.2, 0.25, 0.3],
        },
        "/api/v1/derivatives/cross_currency_swap_pricer": {
            "df_dom": [0.97, 0.94, 0.91],
            "df_for": [0.98, 0.96, 0.94],
        },
        "/api/v1/derivatives/local_volatility_dupire_model": {
            "strikes": [90.0, 100.0, 110.0],
            "call_surface": [
                [17.0, 9.0, 3.5],
                [17.5, 10.2, 5.0],
                [18.0, 11.2, 6.2],
                [18.6, 12.0, 7.2],
                [19.2, 12.8, 8.1],
            ],
            "spot": 100.0,
            "rate": 0.02,
        },
        "/api/v1/liquidity/central_bank_facility_eligibility": {"asset_ratings": [3, 2, 1]},
        "/api/v1/liquidity/combined_stress_scenario": {"hqla_by_level": [1000.0, 500.0, 200.0]},
        "/api/v1/liquidity/market_wide_stress_scenario": {"hqla_by_level": [1000.0, 500.0, 200.0]},
        "/api/v1/liquidity/contingency_funding_plan_trigger": {
            "metrics": {"lcr": 1.2, "nsfr": 1.1},
            "thresholds": {"lcr": 1.0, "nsfr": 1.0},
        },
        "/api/v1/liquidity/deposit_stability_classification": {"deposit_features": [0.9, 0.5, 0.2]},
        "/api/v1/liquidity/early_warning_indicator_liquidity": {
            "indicators": {"cds_spread": 100.0, "deposit_outflow": 0.02},
            "thresholds": {"cds_spread": 150.0, "deposit_outflow": 0.05},
        },
        "/api/v1/liquidity/fx_liquidity_risk_by_currency": {
            "inflows_by_ccy": {"USD": 100.0, "EUR": 80.0},
            "outflows_by_ccy": {"USD": 90.0, "EUR": 70.0},
        },
        "/api/v1/liquidity/ilaap_stress_testing_framework": {
            "scenarios": {
                "idiosyncratic": {"surplus_deficit": 120.0},
                "market_wide": {"surplus_deficit": 40.0},
            },
        },
        "/api/v1/liquidity/intraday_liquidity_monitor": {"net_flows": [10.0, -20.0, 5.0]},
        "/api/v1/liquidity/intraday_liquidity_stress_test": {"net_flows": [10.0, -20.0, 5.0]},
        "/api/v1/liquidity/intragroup_liquidity_flow": {
            "entity_positions": {"A": 50.0, "B": -30.0, "C": -20.0},
        },
        "/api/v1/market-risk/compute_breaches": {"var_estimates": [0.015, 0.015, 0.015]},
        "/api/v1/market-risk/contagion_stress_scenario": {
            "initial_shock": [0.1, 0.0, 0.0],
            "contagion_matrix": [[0.0, 0.2, 0.1], [0.1, 0.0, 0.2], [0.2, 0.1, 0.0]],
        },
        "/api/v1/market-risk/frtb_sa_default_risk_charge": {
            "jtd_long": [100.0, 50.0, 0.0],
            "jtd_short": [0.0, 20.0, 10.0],
        },
        "/api/v1/market-risk/liquidity_adjusted_es": {
            "partial_es": [0.05, 0.07],
            "liquidity_horizons": [10.0, 20.0, 40.0],
        },
        "/api/v1/market-risk/residual_pnl_unexplained": {
            "explained_components": [100.0, -20.0, 15.0]
        },
        "/api/v1/market-risk/sensitivity_stress_profile": {
            "shock_grid": [-0.1, -0.05, 0.0, 0.05, 0.1],
        },
        "/api/v1/market-risk/vega_surface_bucketed": {
            "expiry_buckets": [0, 1, 0],
            "strike_buckets": [0, 1, 1],
            "n_expiry": 2,
            "n_strike": 2,
        },
        "/api/v1/market-risk/volatility_surface_implied_vol": {
            "strikes": [90.0, 100.0, 110.0],
            "expiries": [1.0, 1.0, 1.0],
            "market_prices": [14.0, 8.0, 4.0],
            "spot": 100.0,
            "rate": 0.02,
        },
        "/api/v1/operational/escalation_threshold_calculation": {
            "thresholds": {"level_1": 10_000.0, "level_2": 100_000.0, "level_3": 1_000_000.0},
        },
        "/api/v1/operational/key_risk_indicator_kri_library": {
            "kri_definitions": [
                {
                    "name": "failed_trades",
                    "amber_threshold": 5.0,
                    "red_threshold": 10.0,
                    "direction": "higher_breach",
                },
                {
                    "name": "system_uptime",
                    "amber_threshold": 99.5,
                    "red_threshold": 99.0,
                    "direction": "lower_breach",
                },
            ],
        },
        "/api/v1/operational/kri_trend_analysis": {"observations": [10.0, 12.0, 11.0, 15.0, 18.0]},
        "/api/v1/operational/loss_data_collection_framework": {
            "loss_events": [{"gross_amount": 1000.0}, {"gross_amount": 2500.0}],
        },
        "/api/v1/operational/near_miss_capture_framework": {
            "events": [
                {"actual_loss": 0.0, "potential_loss": 5000.0},
                {"actual_loss": 100.0, "potential_loss": 2000.0},
            ],
        },
        "/api/v1/operational/oprisk_capital_allocation": {
            "business_line_risks": [100.0, 200.0, 300.0]
        },
        "/api/v1/operational/oprisk_heat_map_generator": {
            "likelihoods": [1, 3, 5],
            "impacts": [2, 4, 5],
        },
        "/api/v1/operational/rcsa_risk_identification": {
            "risk_register": [
                {"risk_id": "R1", "category": "internal_fraud"},
                {"risk_id": "R2", "category": "clients_products_business"},
            ],
        },
        "/api/v1/operational/root_cause_analysis_template": {
            "causal_factors": {"people": 3.0, "process": 5.0, "systems": 2.0},
        },
        "/api/v1/operational/scenario_expert_elicitation_model": {
            "expert_estimates": [100_000.0, 150_000.0, 200_000.0],
        },
        "/api/v1/portfolio/black_litterman_model": {
            "p_matrix": [[1.0, 0.0, -1.0]],
            "q_views": [0.02],
        },
        "/api/v1/portfolio/carbon_footprint_attribution": {
            "carbon_intensities": [100.0, 250.0, 50.0]
        },
        "/api/v1/portfolio/factor_based_optimisation": {
            "factor_exposures": [[1.0, 0.2], [0.8, 0.1], [0.5, -0.2]],
            "factor_cov": [[0.04, 0.01], [0.01, 0.03]],
            "specific_var": [0.01, 0.02, 0.015],
        },
        "/api/v1/portfolio/rebalancing_optimiser": {"cost_bps": [10.0, 10.0, 10.0]},
        "/api/v1/regulatory/emir_clearing_obligation_check": {
            "notionals": {"credit": 1.5e9, "interest_rate": 3.0e9},
            "clearing_thresholds": {"credit": 1.0e9, "interest_rate": 3.0e9},
            "counterparty_category": "FC",
        },
        "/api/v1/regulatory/emir_trade_repository_report": {
            "trade": {
                "reporting_counterparty_lei": lei,
                "other_counterparty_lei": lei2,
                "uti": "UTI0000000001",
                "asset_class": "interest_rate",
                "notional": 1_000_000.0,
                "execution_timestamp": "2026-11-17T09:30:00Z",
            },
        },
        "/api/v1/regulatory/frtb_trading_desk_aggregation": {"desk_ima_eligible": [1, 0, 1]},
        "/api/v1/regulatory/mifid_ii_algorithm_documentation": {
            "documentation": {
                "strategy_description": True,
                "risk_controls": True,
                "kill_switch": True,
                "testing_evidence": True,
                "deployment_signoff": True,
                "monitoring_arrangements": True,
            },
        },
        "/api/v1/regulatory/mifid_ii_transaction_report_validator": {
            "report": {
                "transaction_reference_number": "TRN0001",
                "executing_entity_lei": lei,
                "buyer_id": lei2,
                "seller_id": "SELLER0001",
                "instrument_isin": "GB00B03MLX29",
                "price": 101.5,
                "quantity": 1000.0,
                "trading_datetime": "2026-11-17T09:30:00Z",
                "venue": "XLON",
            },
        },
        "/api/v1/regulatory/sftr_securities_finance_report": {
            "transaction": {
                "reporting_counterparty_lei": lei,
                "other_counterparty_lei": lei2,
                "uti": "UTI0000000002",
                "sft_type": "repo",
                "principal_amount": 1_000_000.0,
                "collateral_value": 1_020_000.0,
            },
        },
        "/api/v1/regulatory/solvency_ii_scr_credit_risk": {"loss_given_default": [0.45, 0.4, 0.6]},
        "/api/v1/regulatory/solvency_ii_scr_market_risk": {"correlation_matrix": corr},
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
        body = payload_from_params(function["params"], fixtures, overrides.get(function["path"]))
        if body is not None:
            payloads[function["path"]] = body
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

    # Silence log output while measuring, and put the previous setting back: logging.disable is
    # process-wide, and a test suite that imports this module must not lose caplog for what runs later.
    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        headers = {"Authorization": f"Bearer {create_access_token('trial-bench', 'enterprise')}"}
        with patch("api.middleware.usage._persist_usage", _no_usage_row):
            async with AsyncClient(
                transport=ASGITransport(app=create_app()), base_url="http://bench"
            ) as client:
                yield client, headers
    finally:
        logging.disable(previous_disable)


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

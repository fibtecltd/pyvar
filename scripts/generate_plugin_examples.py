#!/usr/bin/env python3
"""scripts/generate_plugin_examples.py — regenerate docs/plugin-examples.md.

Reasoning:
- Every number in docs/plugin-examples.md is produced by running the real
  pyvar code, not typed by hand: the domain examples POST to the real FastAPI
  app (create_app() behind httpx's ASGITransport, same pattern as tests/),
  the architecture examples call the real modules (api/, engine/, ingestion/,
  storage/, observability/), and the pyvar-mcp examples spawn the real MCP
  server over stdio against a local uvicorn instance.
- Inputs are synthetic (ingestion.fixtures) and AWS is mocked with moto, per
  the project's testing rules -- no real market data and no real AWS calls.
- Prose sits next to the code that produces its numbers (f-strings over the
  captured results), so a changed engine result changes the document with it.

Usage (from the repo root, with the app dependencies, moto and pyvar-mcp installed):
    python scripts/generate_plugin_examples.py                # writes docs/plugin-examples.md
    python scripts/generate_plugin_examples.py --skip-mcp     # without the MCP stdio examples
    python scripts/generate_plugin_examples.py --out /tmp/x.md
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import logging
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
logging.disable(logging.CRITICAL)

import numpy as np  # noqa: E402
from httpx import ASGITransport, AsyncClient, HTTPError  # noqa: E402

from ingestion.fixtures import generate_fixture_parquet, generate_gbm_returns  # noqa: E402

FUNCTIONS = {f["name"]: f for f in json.loads((ROOT / "portal" / "functions.json").read_text())}


# ── Example model ────────────────────────────────────────────────────────────


@dataclass
class Step:
    name: str
    call: str
    result: str
    call_lang: str = "text"
    result_lang: str = "json"
    status: int | None = None


@dataclass
class Example:
    plugin: str
    title: str
    why: str
    steps: list[Step] = field(default_factory=list)
    reading: str = ""


def pretty(obj: Any) -> str:
    """json.dumps(indent=2) with arrays of scalars collapsed onto one line."""
    text = json.dumps(obj, indent=2)
    return re.sub(
        r"\[\s+([^\[\]{}]*?)\s+\]",
        lambda m: "[" + re.sub(r"\s*\n\s*", " ", m.group(1)) + "]",
        text,
    )


def show_params(params: dict[str, Any], placeholders: dict[str, str] | None = None) -> str:
    """JSON of a request body with named fields replaced by a readable <placeholder>."""
    placeholders = placeholders or {}
    shown = {k: (f"@@{k}@@" if k in placeholders else v) for k, v in params.items()}
    text = pretty(shown)
    for key, label in placeholders.items():
        text = text.replace(f'"@@{key}@@"', f"<{label}>")
    return text


def fmt(x: float, nd: int = 0) -> str:
    return f"{x:,.{nd}f}"


def pct(x: float, nd: int = 2) -> str:
    return f"{x * 100:.{nd}f}%"


# ── In-process API client ────────────────────────────────────────────────────


class Api:
    """The real pyvar FastAPI app, driven in-process."""

    def __init__(self, client: AsyncClient, tokens: dict[str, str]) -> None:
        self.client = client
        self.tokens = tokens

    async def raw(
        self,
        path: str,
        params: dict[str, Any],
        token: str | None,
        placeholders: dict[str, str] | None = None,
        name: str | None = None,
    ) -> tuple[Step, int, dict[str, Any]]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = await self.client.post(path, json=params, headers=headers)
        body = resp.json()
        step = Step(
            name=name or path.rsplit("/", 1)[-1],
            call=f"POST {path}\n{show_params(params, placeholders)}",
            result=pretty(body),
            status=resp.status_code,
        )
        return step, resp.status_code, body

    async def call(
        self,
        name: str,
        params: dict[str, Any],
        tier: str = "enterprise",
        placeholders: dict[str, str] | None = None,
    ) -> tuple[Step, dict[str, Any]]:
        step, status, body = await self.raw(
            FUNCTIONS[name]["path"], params, self.tokens[tier], placeholders, name
        )
        if status != 200:
            raise RuntimeError(f"{name} returned {status}: {body}")
        return step, body


# ── Domain plugin examples ───────────────────────────────────────────────────


async def ex_market_risk(api: Api) -> list[Example]:
    returns = generate_gbm_returns(500, mu=0.0004, sigma=0.011, seed=7).tolist()
    ph = {
        "returns": "500 daily log-returns: generate_gbm_returns(500, mu=0.0004, sigma=0.011, seed=7)"
    }
    s1, var = await api.call(
        "historical_simulation_var",
        {"returns": returns, "portfolio_value": 10_000_000, "confidence_level": 0.99},
        placeholders=ph,
    )
    s2, es = await api.call(
        "historical_expected_shortfall",
        {"returns": returns, "portfolio_value": 10_000_000, "confidence_level": 0.975},
        placeholders=ph,
    )
    ex1 = Example(
        "market-risk",
        "VaR and Expected Shortfall on a 10m portfolio",
        "Two years of daily returns go in. Out come the Basel one-day 99% VaR and the FRTB "
        "97.5% Expected Shortfall, both in percentage and in money.",
        [s1, s2],
        f"The 99% VaR is {pct(var['var_pct'])} of the book, {fmt(var['var_abs'])} on 10,000,000; "
        f"the CVaR at the same level is {fmt(var['cvar_abs'])}, always at or above the VaR. "
        f"The Expected Shortfall endpoint works at the FRTB level (97.5%): it averages the "
        f"{es['n_tail']} worst days of the {var['n_obs']} observed and returns {fmt(es['es_abs'])}. "
        f"Expected Shortfall is the mean of the losses beyond the threshold, not a quantile, "
        f"which is why the response also reports how many observations sit in the tail.",
    )

    calm = generate_gbm_returns(250, mu=0.0003, sigma=0.008, seed=11).tolist()
    test = generate_gbm_returns(250, mu=0.0003, sigma=0.008, seed=12).tolist()
    sv, v = await api.call(
        "historical_simulation_var",
        {"returns": calm, "portfolio_value": 1_000_000, "confidence_level": 0.99},
        placeholders={
            "returns": "250 daily log-returns: generate_gbm_returns(250, mu=0.0003, sigma=0.008, seed=11)"
        },
    )
    st, tl = await api.call(
        "traffic_light_backtesting",
        {"actual_returns": test, "var_estimates": [v["var_pct"]] * 250},
        placeholders={
            "actual_returns": "250 daily log-returns: generate_gbm_returns(250, mu=0.0003, sigma=0.008, seed=12)",
            "var_estimates": f"250 copies of {v['var_pct']}",
        },
    )
    sa, add = await api.call("basel_capital_addon_multiplier", {"n_breaches": tl["n_breaches"]})
    sk, kup = await api.call(
        "kupiec_pof_test",
        {"n_breaches": tl["n_breaches"], "n_observations": 250, "confidence_level": 0.99},
    )
    ex2 = Example(
        "market-risk",
        "Backtesting chain: traffic light, capital add-on, Kupiec test",
        "A 99% VaR is estimated on one 250-day window and then judged against the next 250 "
        "days, drawn from the same distribution. Three calls take the breach count to a Basel zone, "
        "a capital multiplier and a statistical verdict.",
        [sv, st, sa, sk],
        f"A 99% VaR should be breached about 2.5 times in 250 days. Here it is breached "
        f"{tl['n_breaches']} times, which the Basel traffic light places in the {tl['basel_zone']} "
        f"zone (green below 5, yellow 5-9, red 10 or more) and which carries a capital multiplier of "
        f"{add['multiplier']}. The Kupiec proportion-of-failures test agrees: a likelihood ratio of "
        f"{kup['lr_pof']:.2f} against the 95% chi-squared critical value of {kup['critical_value']:.2f} "
        f"(p = {kup['p_value']:.3f}) rejects the model. Both windows share one distribution, so the "
        f"result also shows how noisy a 99% quantile is when estimated from 250 observations.",
    )
    return [ex1, ex2]


async def ex_credit_risk(api: Api) -> list[Example]:
    s1, el = await api.call(
        "expected_loss_el_computation", {"pd": 0.02, "lgd": 0.45, "ead": 50_000_000}
    )
    s2, vas = await api.call(
        "credit_var_analytical_vasicek",
        {
            "pd": 0.02,
            "lgd": 0.45,
            "ead_total": 50_000_000,
            "asset_correlation": 0.15,
            "confidence_level": 0.999,
        },
    )
    ex1 = Example(
        "credit-risk",
        "Expected loss and Vasicek credit VaR on a 50m exposure",
        "Expected loss is the price of the risk; the Vasicek single-factor model gives the "
        "99.9% loss that capital has to absorb on top of it.",
        [s1, s2],
        f"Expected loss is PD x LGD x EAD = 0.02 x 0.45 x 50,000,000 = {fmt(el['el'])}, "
        f"{pct(el['el_rate'], 1)} of the exposure. The Vasicek 99.9% credit VaR is {fmt(vas['var'])}; "
        f"subtracting the expected loss leaves an unexpected loss of {fmt(vas['ul'])}, which is the "
        f"part economic capital has to cover. The stressed loss rate of {pct(vas['loss_rate_q'])} is "
        f"the conditional default rate at 99.9% multiplied by the LGD.",
    )
    safe = dict(
        working_capital=2_000_000,
        retained_earnings=3_400_000,
        ebit=1_500_000,
        market_value_equity=8_000_000,
        sales=6_500_000,
        total_assets=10_000_000,
        total_liabilities=4_000_000,
    )
    grey = dict(
        working_capital=1_200_000,
        retained_earnings=3_400_000,
        ebit=900_000,
        market_value_equity=8_000_000,
        sales=5_500_000,
        total_assets=10_000_000,
        total_liabilities=4_000_000,
    )
    weak = dict(
        working_capital=-300_000,
        retained_earnings=-900_000,
        ebit=-150_000,
        market_value_equity=600_000,
        sales=2_800_000,
        total_assets=6_000_000,
        total_liabilities=5_500_000,
    )
    a1, safe_r = await api.call("altman_z_score_credit_scoring", safe)
    a2, grey_r = await api.call("altman_z_score_credit_scoring", grey)
    a3, weak_r = await api.call("altman_z_score_credit_scoring", weak)
    ex2 = Example(
        "credit-risk",
        "Altman Z-score across three borrowers",
        "One endpoint scores three balance sheets and places each in an Altman zone.",
        [a1, a2, a3],
        f"The same call returns a {safe_r['zone']} verdict (Z = {safe_r['z_score']}), a {grey_r['zone']} "
        f"verdict (Z = {grey_r['z_score']}) and a {weak_r['zone']} verdict (Z = {weak_r['z_score']}). "
        f"The response includes the five ratios x1 to x5, so the model is auditable: the distressed borrower "
        f"has negative working capital, retained earnings and EBIT, and the Z-score of the middle borrower "
        f"checks by hand as 1.2 x 0.12 + 1.4 x 0.34 + 3.3 x 0.09 + 0.6 x 2.0 + 1.0 x 0.55 = 2.667.",
    )
    return [ex1, ex2]


async def ex_liquidity(api: Api) -> list[Example]:
    s1, lcr = await api.call(
        "liquidity_coverage_ratio_lcr",
        {"hqla": 120e6, "gross_outflows": 150e6, "gross_inflows": 40e6},
    )
    s2, nsfr = await api.call(
        "net_stable_funding_ratio_nsfr",
        {"available_stable_funding": 410e6, "required_stable_funding": 385e6},
    )
    ex1 = Example(
        "liquidity-risk",
        "LCR and NSFR against the 100% minimum",
        "The two Basel III liquidity ratios for one balance sheet.",
        [s1, s2],
        f"With 120m of HQLA against 110m of net 30-day outflows (150m outflows less 40m inflows), the "
        f"LCR is {pct(lcr['lcr'], 1)}. The NSFR is 410m of available stable funding over 385m required, "
        f"{pct(nsfr['nsfr'], 1)}. Both flags read compliant: {lcr['compliant']} and {nsfr['compliant']}.",
    )
    outflows = [8e6, 9e6, 11e6, 12e6, 12e6, 10e6, 9e6, 8e6, 8e6, 7e6, 7e6, 6e6]
    s3, surv = await api.call(
        "survival_horizon_calculator", {"hqla": 100e6, "daily_net_outflows": outflows}
    )
    ex2 = Example(
        "liquidity-risk",
        "Survival horizon under a stressed outflow path",
        "How long a 100m HQLA buffer lasts when net outflows follow a 12-day stress path.",
        [s3],
        f"Cumulative outflows reach 94m after day 10 and 101m after day 11, so the buffer survives "
        f"{surv['survival_days']} full days and is exhausted during day {surv['survival_days'] + 1}, "
        f"ending at {fmt(surv['terminal_buffer'])}. The full path would drain 107m.",
    )
    return [ex1, ex2]


async def ex_oprisk(api: Api) -> list[Example]:
    s1, mid = await api.call(
        "basel_standardised_measurement_sma",
        {"business_indicator": 3_000_000_000, "loss_component": 0.0, "use_ilm": True},
    )
    s2, big = await api.call(
        "basel_standardised_measurement_sma",
        {"business_indicator": 12_000_000_000, "loss_component": 2_500_000_000, "use_ilm": True},
    )
    ex1 = Example(
        "operational-risk",
        "Basel SMA capital: a clean loss history and a heavy one",
        "The Standardised Measurement Approach is the Business Indicator Component scaled by the "
        "Internal Loss Multiplier. Two banks show how the loss history moves the answer.",
        [s1, s2],
        f"For a 3bn Business Indicator the BIC is 12% of the first 1bn plus 15% of the next 2bn = "
        f"{fmt(mid['bic'])}. With no loss history the ILM is ln(e - 1) = {mid['ilm']}, so SMA capital "
        f"is {fmt(mid['sma_capital'])}. A 12bn bank with a 2.5bn loss component has a BIC of "
        f"{fmt(big['bic'])} and an ILM of {big['ilm']}, which lifts its capital to {fmt(big['sma_capital'])}.",
    )
    k1, red = await api.call(
        "kri_threshold_breach_detection",
        {"value": 14, "amber_threshold": 8, "red_threshold": 12, "direction": "higher_breach"},
    )
    k2, amber = await api.call(
        "kri_threshold_breach_detection",
        {"value": 9.5, "amber_threshold": 8, "red_threshold": 12, "direction": "higher_breach"},
    )
    k3, low = await api.call(
        "kri_threshold_breach_detection",
        {
            "value": 97.2,
            "amber_threshold": 98.5,
            "red_threshold": 96.0,
            "direction": "lower_breach",
        },
    )
    ex2 = Example(
        "operational-risk",
        "KRI breach detection, higher-is-worse and lower-is-worse",
        "One function covers indicators that breach upwards (failed trades) and downwards (straight-through rate).",
        [k1, k2, k3],
        f"Fourteen failed trades against thresholds of 8 and 12 is {red['status']}; 9.5 is {amber['status']}. "
        f"A straight-through-processing rate of 97.2% against thresholds of 98.5% and 96.0% is {low['status']} "
        f"under direction lower_breach, so the same endpoint handles metrics where falling is the danger.",
    )
    return [ex1, ex2]


async def ex_portfolio(api: Api) -> list[Example]:
    annual = np.array(
        [
            [0.04, 0.012, 0.006, 0.002],
            [0.012, 0.0225, 0.005, 0.001],
            [0.006, 0.005, 0.0081, 0.0004],
            [0.002, 0.001, 0.0004, 0.0016],
        ]
    )
    cov = (annual / 252).tolist()
    ph = {"cov_matrix": "4x4 daily covariance = annual covariance / 252"}
    s1, mv = await api.call("minimum_variance_portfolio", {"cov_matrix": cov}, placeholders=ph)
    s2, rp = await api.call("risk_parity_portfolio", {"cov_matrix": cov}, placeholders=ph)
    ex1 = Example(
        "portfolio-analytics",
        "Minimum-variance and risk-parity weights on one covariance matrix",
        "Two allocation philosophies applied to the same four assets. The optimisers take a per-period "
        "(daily) covariance matrix and annualise internally.",
        [s1, s2],
        f"Minimum variance puts everything in the two calmest assets "
        f"({pct(mv['weights'][3], 1)} and {pct(mv['weights'][2], 1)}) for an annualised volatility of "
        f"{pct(mv['volatility'])}. Risk parity spreads the weights ({', '.join(pct(w, 1) for w in rp['weights'])}) "
        f"so that every asset contributes the same risk: the four risk contributions are all "
        f"{rp['risk_contributions'][0]:.4e}. It accepts a higher volatility, {pct(rp['volatility'])}, "
        f"in exchange for that diversification.",
    )
    eq = generate_gbm_returns(504, mu=0.0004, sigma=0.011, seed=21).tolist()
    ph2 = {
        "returns": "504 daily log-returns: generate_gbm_returns(504, mu=0.0004, sigma=0.011, seed=21)"
    }
    p1, sh = await api.call("sharpe_ratio", {"returns": eq}, placeholders=ph2)
    p2, so = await api.call("sortino_ratio", {"returns": eq}, placeholders=ph2)
    p3, dd = await api.call("maximum_drawdown", {"returns": eq}, placeholders=ph2)
    ex2 = Example(
        "portfolio-analytics",
        "Sharpe, Sortino and maximum drawdown over two years",
        "Three performance statistics on the same return series.",
        [p1, p2, p3],
        f"The annualised Sharpe ratio is {sh['sharpe']:.2f}. The Sortino ratio, which only penalises "
        f"downside deviation, is higher at {so['sortino']:.2f}. The maximum drawdown is {pct(dd['max_drawdown'], 1)}, "
        f"peak at observation {dd['peak_index']} and trough at {dd['trough_index']}, so the response tells "
        f"you where the loss happened as well as how large it was.",
    )
    return [ex1, ex2]


async def ex_regulatory(api: Api) -> list[Example]:
    s1, cet1 = await api.call(
        "basel_iii_cet1_ratio", {"cet1_capital": 5.2e9, "risk_weighted_assets": 41e9}
    )
    s2, cbr = await api.call(
        "combined_buffer_requirement",
        {
            "capital_conservation_buffer_ratio": 0.025,
            "countercyclical_buffer_ratio": 0.01,
            "systemic_buffer_ratio": 0.01,
            "risk_weighted_assets": 41e9,
        },
    )
    s3, lev = await api.call(
        "basel_iii_leverage_ratio", {"tier1_capital": 6.1e9, "total_exposure": 168e9}
    )
    ex1 = Example(
        "regulatory",
        "CET1, combined buffer and leverage ratio for one bank",
        "Three Basel III capital tests, each answered with the minimum, the surplus and a compliance flag.",
        [s1, s2, s3],
        f"CET1 of 5.2bn on 41bn of RWA is {pct(cet1['cet1_ratio'])}, a surplus of "
        f"{pct(cet1['surplus'])} over the {pct(cet1['minimum'], 1)} minimum. Stacking the 2.5% conservation, "
        f"1% countercyclical and 1% systemic buffers gives a combined buffer of "
        f"{pct(cbr['combined_buffer_ratio'], 1)}, which is {fmt(cbr['combined_buffer_capital'])} of capital. "
        f"Tier 1 of 6.1bn over 168bn of exposure is a {pct(lev['leverage_ratio'])} leverage ratio against the "
        f"{pct(lev['minimum'], 0)} floor.",
    )
    s4, floor = await api.call(
        "basel_iv_output_floor", {"internal_model_rwa": 28e9, "standardised_rwa": 41e9}
    )
    ex2 = Example(
        "regulatory",
        "Basel IV output floor",
        "Internal-model RWA cannot fall below a fixed share of the standardised RWA.",
        [s4],
        f"The floor is {pct(floor['floor_factor'], 1)} of the 41bn standardised RWA, "
        f"{fmt(floor['floor_rwa'])}. That is above the 28bn internal-model figure, so the floor "
        f"binds ({floor['binding']}) and RWA rises by {fmt(floor['rwa_uplift'])}.",
    )
    return [ex1, ex2]


async def ex_derivatives(api: Api) -> list[Example]:
    base = dict(spot=100, strike=105, rate=0.04, sigma=0.22, tau=0.5)
    c, call = await api.call("black_scholes_european_option", {**base, "option_type": "call"})
    p, put = await api.call("black_scholes_european_option", {**base, "option_type": "put"})
    g, gr = await api.call("black_scholes_greeks", {**base, "option_type": "call"})
    parity_lhs = put["price"] - call["price"]
    parity_rhs = 105 * math.exp(-0.04 * 0.5) - 100
    ex1 = Example(
        "derivatives",
        "Black-Scholes call, put and Greeks",
        "A six-month 105-strike option on a 100 underlying, priced both ways and differentiated.",
        [c, p, g],
        f"The call is worth {call['price']:.4f} and the put {put['price']:.4f}. Put-call parity holds: "
        f"put - call = {parity_lhs:.4f}, and K e^(-rT) - S = {parity_rhs:.4f}. The Greeks follow the usual "
        f"conventions: vega is per 1.00 of volatility ({gr['vega']:.2f}, i.e. {gr['vega'] / 100:.4f} per volatility point), "
        f"rho per 1.00 of rate and theta per year ({gr['theta']:.2f}, i.e. {gr['theta'] / 365:.4f} per day).",
    )
    bond = dict(face_value=100, coupon_rate=0.045, yield_rate=0.05, maturity=10, frequency=2)
    cfs = [2.25] * 19 + [102.25]
    ts = [0.5 * (i + 1) for i in range(20)]
    ph = {
        "cashflows": "20 semi-annual cash flows: 19 x 2.25, then 102.25",
        "times": "0.5, 1.0, ... 10.0",
    }
    b1, price = await api.call("bond_pricer_fixed_coupon", bond)
    b2, md = await api.call(
        "modified_duration",
        dict(cashflows=cfs, times=ts, yield_rate=0.05, frequency=2),
        placeholders=ph,
    )
    b3, cx = await api.call(
        "convexity", dict(cashflows=cfs, times=ts, yield_rate=0.05, frequency=2), placeholders=ph
    )
    b4, shocked = await api.call("bond_pricer_fixed_coupon", {**bond, "yield_rate": 0.055})
    dy = 0.005
    estimate = price["price"] * (-md["modified_duration"] * dy + 0.5 * cx["convexity"] * dy**2)
    ex2 = Example(
        "derivatives",
        "Bond price, duration, convexity and a +50bp reprice",
        "A 10-year 4.5% semi-annual bond at a 5% yield. Duration and convexity predict the price move; "
        "a full reprice at +50bp confirms it.",
        [b1, b2, b3, b4],
        f"The bond prices at {price['price']:.4f} with a modified duration of {md['modified_duration']:.4f} "
        f"and a convexity of {cx['convexity']:.2f}. The duration-plus-convexity estimate of a +50bp move is "
        f"{estimate:.4f}, giving {price['price'] + estimate:.4f}; the full reprice gives {shocked['price']:.4f}, "
        f"a move of {shocked['price'] - price['price']:.4f}. The residual is {abs(price['price'] + estimate - shocked['price']):.4f}.",
    )
    return [ex1, ex2]


async def ex_alm(api: Api) -> list[Example]:
    s1, dg = await api.call(
        "duration_gap_analysis",
        dict(
            asset_duration=4.2,
            liability_duration=3.6,
            total_assets=10e9,
            total_liabilities=9.2e9,
            rate_shock=0.02,
        ),
    )
    s2, rg = await api.call(
        "repricing_gap_analysis",
        dict(
            bucket_assets=[1.8e9, 1.2e9, 2.0e9, 3.0e9, 2.0e9],
            bucket_liabilities=[3.1e9, 1.9e9, 1.6e9, 1.7e9, 0.9e9],
            bucket_labels=["<3m", "3-12m", "1-3y", "3-7y", ">7y"],
        ),
    )
    ex1 = Example(
        "alm",
        "Duration gap and repricing gap on one balance sheet",
        "Two classic views of interest-rate exposure: how equity value moves, and where assets and "
        "liabilities reprice.",
        [s1, s2],
        f"Asset duration 4.2 minus 0.92 x liability duration 3.6 gives a duration gap of {dg['duration_gap']}. "
        f"A +200bp parallel shock then moves the economic value of equity by {fmt(dg['delta_eve'])}, "
        f"{pct(abs(dg['delta_eve']) / dg['equity'], 1)} of the {fmt(dg['equity'])} of equity. The repricing ladder shows "
        f"why: liabilities reprice faster than assets in the first year (gaps of {fmt(rg['gap']['<3m'])} and "
        f"{fmt(rg['gap']['3-12m'])}), the cumulative gap bottoms out at {fmt(min(rg['cumulative_gap']))} and the "
        f"total gap is {fmt(rg['total_gap'])}.",
    )
    t = [0.5, 1, 2, 3, 5, 7, 10]
    s3, st = await api.call(
        "alm_stress_test",
        dict(
            net_cashflows=[-400e6, -250e6, -100e6, 150e6, 350e6, 300e6, 250e6],
            times=t,
            base_rates=[0.035, 0.036, 0.037, 0.038, 0.040, 0.041, 0.042],
            tier1_capital=900e6,
            parallel_bps=200,
        ),
    )
    worst = min(st["scenario_results"], key=lambda k: st["scenario_results"][k])
    ex2 = Example(
        "alm",
        "IRRBB outlier test across the six BCBS shocks",
        "A cash-flow ladder and base curve are shocked six ways, and the worst loss is compared with Tier 1 "
        "capital under the 15% supervisory outlier test.",
        [s3],
        f"The worst scenario is {worst}, with a change in EVE of {fmt(st['worst_case_eve'])}. Against "
        f"900m of Tier 1 capital that is {pct(st['eve_capital_ratio'], 1)}, below the 15% outlier threshold, so "
        f"breaches_15pct is {st['breaches_15pct']}. The parallel-down scenario shows the opposite sign "
        f"({fmt(st['scenario_results']['parallel_down'])}): value falls when rates rise and rises when they fall, the "
        f"profile of a ladder whose later, positive cash flows are the longer-dated ones.",
    )
    return [ex1, ex2]


DOMAIN_EXAMPLES: list[Callable[[Api], Awaitable[list[Example]]]] = [
    ex_market_risk,
    ex_credit_risk,
    ex_liquidity,
    ex_oprisk,
    ex_portfolio,
    ex_regulatory,
    ex_derivatives,
    ex_alm,
]


# ── Architecture plugin examples ─────────────────────────────────────────────


class FakeSession:
    """Stand-in for the audit-table session (the real one needs Aurora)."""

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def add(self, obj: object) -> None:
        pass

    async def execute(self, stmt: object) -> MagicMock:
        return MagicMock()

    async def commit(self) -> None:
        pass


_APP: Any = None


def get_app() -> Any:
    """One shared app instance, as in production (Prometheus metrics register once per process)."""
    global _APP
    if _APP is None:
        from main import create_app

        _APP = create_app()
    return _APP


@contextlib.asynccontextmanager
async def gateway_client(celery: bool = False) -> AsyncIterator[AsyncClient]:
    """A fresh app with its own in-memory rate limiter (and, optionally, Celery/DB patched)."""
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    app = get_app()
    fresh = Limiter(key_func=get_remote_address, storage_uri="memory://")
    task = MagicMock()
    task.id = "3f2c9d1e-0000-4000-8000-000000000001"
    stack = contextlib.ExitStack()
    stack.enter_context(patch("api.middleware.rate_limit._limiter", fresh))
    stack.enter_context(patch("sentry_sdk.init"))
    if celery:
        stack.enter_context(
            patch("api.routes.var.get_sessionmaker", return_value=lambda: FakeSession())
        )
        stack.enter_context(patch("api.routes.var.compute_var_task.apply_async", return_value=task))
    with stack:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def ex_api_gateway() -> list[Example]:
    import jwt as pyjwt

    from api.middleware.auth import create_access_token

    returns = generate_gbm_returns(252, seed=5).tolist()
    payload = {
        "portfolio_value": 1_000_000,
        "returns": returns,
        "confidence_level": 0.99,
        "horizon_days": 1,
        "n_simulations": 50_000,
    }
    ph = {"returns": "252 daily log-returns: generate_gbm_returns(252, seed=5)"}
    forged = pyjwt.encode(
        {"sub": "mallory", "tier": "enterprise", "exp": int(time.time()) + 3600},
        "not-the-real-secret",
        algorithm="HS256",
    )
    free = create_access_token("alice", "free")
    pro = create_access_token("bob", "pro")

    steps: list[Step] = []
    async with gateway_client(celery=True) as client:
        api = Api(client, {})
        for label, token in (
            ("no token", None),
            ("token signed with the wrong secret", forged),
            ("free tier asking for 50,000 simulations", free),
            ("pro tier asking for 50,000 simulations", pro),
        ):
            step, _, _ = await api.raw("/api/v1/var/compute", payload, token, ph, name=label)
            steps.append(step)
    ex1 = Example(
        "arch-api-gateway",
        "JWT authentication and tier caps on POST /api/v1/var/compute",
        "The same request body is sent four times with different credentials. The gateway authenticates the "
        "JWT, reads the tier from it and enforces that tier's simulation cap before anything is queued. "
        "Celery and the audit database are stood in for here, so the accepted request returns a fixed "
        "stand-in task_id.",
        steps,
        f"No token and a forged token both get {steps[0].status}. A free-tier token is refused with "
        f"{steps[2].status} and a message that names the cap and the request; the identical body from a pro-tier "
        f"token is accepted with {steps[3].status} and a task_id to poll at GET /api/v1/var/result/{{task_id}}. "
        f"Caps are 10,000 simulations for free, 100,000 for pro and 500,000 for enterprise.",
    )

    carol = create_access_token("carol", "free")
    bodies = [
        (
            "/api/v1/credit-risk/expected_loss_el_computation",
            {"pd": 0.02, "lgd": 0.45, "ead": 1_000_000},
        ),
        (
            "/api/v1/liquidity/liquidity_coverage_ratio_lcr",
            {"hqla": 120e6, "gross_outflows": 150e6, "gross_inflows": 40e6},
        ),
    ]
    lines: list[str] = []
    last: Any = None
    async with gateway_client() as client:
        for i in range(11):
            path, body = bodies[i % 2]
            last = await client.post(path, json=body, headers={"Authorization": f"Bearer {carol}"})
            lines.append(f"request {i + 1:>2}  {path.rsplit('/', 1)[-1]:<34} -> {last.status_code}")
    lines.append(f"response body: {json.dumps(last.json())}")
    lines.append(f"Retry-After header: {last.headers.get('retry-after')} seconds")
    ex2 = Example(
        "arch-api-gateway",
        "One daily quota shared across every compute endpoint",
        "A free-tier user alternates between a credit-risk and a liquidity endpoint. The daily allowance is a "
        "single shared 'compute' bucket, so the count carries across routes.",
        [
            Step(
                "11 requests as a free-tier user",
                "free-tier token, alternating:\n  "
                + "\n  ".join(p.rsplit("/", 1)[-1] for p, _ in bodies),
                "\n".join(lines),
                result_lang="text",
            )
        ],
        f"The free tier allows 10 compute requests per day. Requests 1 to 10 succeed across both endpoints; "
        f"request 11 is refused with {last.status_code} and a Retry-After of about a day, rather than being "
        f"counted per route.",
    )
    return [ex1, ex2]


def ex_compute() -> list[Example]:
    from engine.montecarlo import run_monte_carlo_var

    returns = generate_gbm_returns(252, mu=0.0004, sigma=0.012, seed=3)
    a = run_monte_carlo_var(returns, 1_000_000, 0.99, 1, 50_000, seed=42)
    b = run_monte_carlo_var(returns, 1_000_000, 0.99, 1, 50_000, seed=42)
    v95 = run_monte_carlo_var(returns, 1_000_000, 0.95, 1, 50_000, seed=42)
    big = run_monte_carlo_var(returns, 10_000_000, 0.99, 1, 50_000, seed=42)
    code1 = (
        "from engine.montecarlo import run_monte_carlo_var\n"
        "returns = generate_gbm_returns(252, mu=0.0004, sigma=0.012, seed=3)\n"
        "a   = run_monte_carlo_var(returns,  1_000_000, 0.99, 1, 50_000, seed=42)\n"
        "b   = run_monte_carlo_var(returns,  1_000_000, 0.99, 1, 50_000, seed=42)\n"
        "v95 = run_monte_carlo_var(returns,  1_000_000, 0.95, 1, 50_000, seed=42)\n"
        "big = run_monte_carlo_var(returns, 10_000_000, 0.99, 1, 50_000, seed=42)"
    )
    out1 = "\n".join(
        [
            f"same seed, identical VaR and loss distribution : {a['var_pct'] == b['var_pct'] and a['loss_dist'] == b['loss_dist']}",
            f"99% VaR {pct(a['var_pct'], 3)}  >  95% VaR {pct(v95['var_pct'], 3)} : {a['var_pct'] > v95['var_pct']}",
            f"CVaR {pct(a['cvar_pct'], 3)}  >=  VaR {pct(a['var_pct'], 3)}      : {a['cvar_pct'] >= a['var_pct']}",
            f"var_abs on 10m / var_abs on 1m                  : {big['var_abs'] / a['var_abs']:.4f}",
        ]
    )
    ex1 = Example(
        "arch-compute",
        "Numerical properties of the Numba Monte Carlo kernel",
        "The engine is pre-drawn random numbers fed to an @njit kernel. The properties the test-suite pins "
        "can be checked in four lines.",
        [Step("run_monte_carlo_var", code1, out1, call_lang="python", result_lang="text")],
        f"Two runs with seed 42 are bit-identical, which is what makes a stored job reproducible. The 99% VaR "
        f"({pct(a['var_pct'], 3)}) sits above the 95% VaR ({pct(v95['var_pct'], 3)}), CVaR is at least VaR, and "
        f"absolute VaR scales linearly with portfolio value (a ratio of 10 for a 10x portfolio).",
    )

    rows = []
    for n in (1_000, 10_000, 100_000, 1_000_000):
        vs = [run_monte_carlo_var(returns, 1.0, 0.99, 1, n, seed=s)["var_pct"] for s in range(1, 6)]
        rows.append((n, min(vs), max(vs)))
    one = run_monte_carlo_var(returns, 1_000_000, 0.99, 1, 200_000, seed=1)
    ten = run_monte_carlo_var(returns, 1_000_000, 0.99, 10, 200_000, seed=1)
    code2 = (
        "for n in (1_000, 10_000, 100_000, 1_000_000):\n"
        "    vs = [run_monte_carlo_var(returns, 1.0, 0.99, 1, n, seed=s)['var_pct'] for s in range(1, 6)]\n"
        "    print(n, min(vs), max(vs))\n"
        "one = run_monte_carlo_var(returns, 1_000_000, 0.99,  1, 200_000, seed=1)\n"
        "ten = run_monte_carlo_var(returns, 1_000_000, 0.99, 10, 200_000, seed=1)"
    )
    out2 = "\n".join(
        [
            f"n_simulations {n:>9,}   VaR over 5 seeds: {lo:.5f} .. {hi:.5f}   spread {hi - lo:.5f}"
            for n, lo, hi in rows
        ]
        + [
            f"1-day VaR {one['var_pct']:.5f}   10-day VaR {ten['var_pct']:.5f}   ratio {ten['var_pct'] / one['var_pct']:.3f}   (sqrt(10) = {math.sqrt(10):.3f})",
        ]
    )
    ex2 = Example(
        "arch-compute",
        "Simulation count and horizon: convergence and square-root-of-time",
        "How much the answer moves between seeds as paths are added, and how a 10-day horizon relates to a "
        "1-day one.",
        [
            Step(
                "convergence and horizon scaling",
                code2,
                out2,
                call_lang="python",
                result_lang="text",
            )
        ],
        f"The seed-to-seed spread of the 99% VaR shrinks from {rows[0][2] - rows[0][1]:.5f} at 1,000 paths to "
        f"{rows[-1][2] - rows[-1][1]:.5f} at 1,000,000: more paths buy a tighter estimate, at a cost that grows "
        f"with the path count. The 10-day VaR is {ten['var_pct'] / one['var_pct']:.2f} times the 1-day figure, close to the "
        f"square-root-of-time factor of {math.sqrt(10):.2f}; it is a little lower because the positive daily "
        f"drift accumulates over ten days.",
    )
    return [ex1, ex2]


def ex_data_ingestion() -> list[Example]:
    import polars as pl
    import pyarrow.parquet as pq

    from ingestion.loader import load_returns, write_result_parquet

    with tempfile.TemporaryDirectory() as tmp:
        path = generate_fixture_parquet(Path(tmp) / "fixture.parquet")
        plan = (
            pl.scan_parquet(path)
            .filter(pl.col("instrument_id") == "FTSE100")
            .filter(pl.col("date") >= date(2023, 6, 1))
            .select(["date", "log_return"])
            .sort("date")
            .explain()
        ).replace(str(path), "fixture.parquet")
        arr = load_returns(path, "FTSE100", start_date=date(2023, 6, 1))
        full = load_returns(path, "FTSE100")
        try:
            load_returns(path, "NOPE")
            err = "no error"
        except ValueError as exc:
            err = f"ValueError: {exc}"
        code1 = (
            "path = generate_fixture_parquet('fixture.parquet')   # 3 instruments x 504 days\n"
            "lf = (pl.scan_parquet(path)\n"
            "        .filter(pl.col('instrument_id') == 'FTSE100')\n"
            "        .filter(pl.col('date') >= date(2023, 6, 1))\n"
            "        .select(['date', 'log_return']).sort('date'))\n"
            "print(lf.explain())\n"
            "arr  = load_returns(path, 'FTSE100', start_date=date(2023, 6, 1))\n"
            "full = load_returns(path, 'FTSE100')\n"
            "load_returns(path, 'NOPE')"
        )
        out1 = "\n".join(
            [
                plan.rstrip(),
                "",
                f"windowed : shape {arr.shape}, dtype {arr.dtype}",
                f"full     : shape {full.shape}, dtype {full.dtype}",
                err,
            ]
        )
        ex1 = Example(
            "arch-data-ingestion",
            "Lazy Parquet scan with predicate pushdown into a NumPy array",
            "The loader never reads the whole file: the instrument and date filters travel into the Parquet "
            "scan, and the engine receives a plain float64 array.",
            [
                Step(
                    "pl.scan_parquet + load_returns",
                    code1,
                    out1,
                    call_lang="python",
                    result_lang="text",
                )
            ],
            f"The query plan shows the date and instrument predicates as a SELECTION on the Parquet scan, so "
            f"filtering happens while reading. The windowed load returns {arr.shape[0]} observations against "
            f"{full.shape[0]} for the full history, both as float64 arrays, and an unknown instrument raises a "
            f"clear error instead of returning an empty array.",
        )

        good = dict(
            var_pct=0.02,
            var_abs=2e4,
            cvar_pct=0.03,
            cvar_abs=3e4,
            mu=0.0004,
            sigma=0.012,
            n_simulations=1000,
            confidence_level=0.99,
            horizon_days=1,
            loss_dist=[0.01, 0.02, 0.03],
        )
        out_path = Path(tmp) / "result.parquet"
        write_result_parquet(good, out_path, "task-1")
        schema = pq.read_schema(out_path)
        codec = pq.ParquetFile(out_path).metadata.row_group(0).column(0).compression
        try:
            write_result_parquet(
                {**good, "var_pct": "not-a-number"}, Path(tmp) / "bad.parquet", "task-2"
            )
            bad = "no error"
        except Exception as exc:  # noqa: BLE001 - the example prints whatever pyarrow raises
            bad = f"{type(exc).__name__}: {exc}"
        code2 = (
            "write_result_parquet(result, 'result.parquet', task_id='task-1')\n"
            "print(pq.read_schema('result.parquet'))\n"
            "print(pq.ParquetFile('result.parquet').metadata.row_group(0).column(0).compression)\n"
            "write_result_parquet({**result, 'var_pct': 'not-a-number'}, 'bad.parquet', 'task-2')"
        )
        out2 = "\n".join(
            [
                "\n".join(f"{f.name}: {f.type}" for f in schema),
                f"compression: {codec}",
                bad,
            ]
        )
        ex2 = Example(
            "arch-data-ingestion",
            "Schema-enforced Parquet results with PyArrow",
            "Results are written with an explicit schema, so a wrongly typed value fails loudly rather than being coerced.",
            [Step("write_result_parquet", code2, out2, call_lang="python", result_lang="text")],
            f"The file carries an explicit eleven-column schema (scalar metrics plus the full loss distribution as "
            f"a list of doubles) and is compressed with {codec}. Passing a string where a double is expected "
            f"raises {bad.split(':')[0]} rather than silently writing a corrupt column.",
        )
    return [ex1, ex2]


def ex_storage() -> list[Example]:
    import boto3
    import pyarrow.parquet as pq
    from moto import mock_aws

    from api.routes import caching
    from config import get_settings
    from engine.montecarlo import run_monte_carlo_var
    from storage import s3 as s3mod

    body = {"returns": [0.01, -0.02], "portfolio_value": 1e6, "confidence_level": 0.99}
    k1 = caching._cache_key("market-risk", body)
    k2 = caching._cache_key("market-risk", dict(reversed(list(body.items()))))
    k3 = caching._cache_key("market-risk", {**body, "confidence_level": 0.95})
    k4 = caching._cache_key("credit-risk", body)
    miss = asyncio.run(caching._cache_get("market-risk", {"never": "cached"}))
    code1 = (
        "body = {'returns': [0.01, -0.02], 'portfolio_value': 1e6, 'confidence_level': 0.99}\n"
        "k1 = _cache_key('market-risk', body)\n"
        "k2 = _cache_key('market-risk', dict(reversed(body.items())))   # same fields, other order\n"
        "k3 = _cache_key('market-risk', {**body, 'confidence_level': 0.95})\n"
        "k4 = _cache_key('credit-risk', body)\n"
        "await _cache_get('market-risk', {'never': 'cached'})            # no Redis reachable"
    )
    out1 = "\n".join(
        [
            f"k1 = {k1}",
            f"k1 == k2 (field order ignored)   : {k1 == k2}",
            f"k1 == k3 (other confidence level): {k1 == k3}",
            f"k1 == k4 (other domain)          : {k1 == k4}",
            f"_cache_get with Redis unreachable: {miss!r}",
        ]
    )
    ex1 = Example(
        "arch-storage",
        "Deterministic cache keys that fail open",
        "The Redis cache key is a SHA-256 over the canonical request, and a cache that cannot be reached "
        "degrades to a miss.",
        [
            Step(
                "caching._cache_key / _cache_get",
                code1,
                out1,
                call_lang="python",
                result_lang="text",
            )
        ],
        "Key order in the JSON body does not change the key, while any change of parameter or domain does, so "
        "equivalent requests share one cached result and different ones never collide. With no Redis available "
        "the lookup returns None, a plain cache miss, so an unreachable cache slows a request down instead of "
        "failing it.",
    )

    cfg = get_settings()
    returns = generate_gbm_returns(252, seed=3)
    result = run_monte_carlo_var(returns, 1_000_000, 0.99, 1, 200_000, seed=42)
    result["horizon_days"] = 1
    with mock_aws():
        s3 = boto3.client("s3", region_name="eu-west-1")
        s3.create_bucket(
            Bucket=cfg.s3_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"}
        )
        task_id = "abcdef12-3456-7890-abcd-ef1234567890"
        key = s3mod.write_result_to_s3(dict(result), task_id)
        data = s3.get_object(Bucket=cfg.s3_bucket, Key=key)["Body"].read()
        table = pq.read_table(io.BytesIO(data))
        url = s3mod.generate_presigned_url(key)
        hydrated = s3mod.hydrate_presigned_url({"s3_key": key, "n_simulations": 200_000})
    code2 = (
        "result = run_monte_carlo_var(returns, 1_000_000, 0.99, 1, 200_000, seed=42)   # 200,000 > threshold\n"
        "key  = write_result_to_s3(result, task_id)\n"
        "obj  = s3.get_object(Bucket=bucket, Key=key)\n"
        "url  = generate_presigned_url(key)\n"
        "hydrate_presigned_url({'s3_key': key, 'n_simulations': 200_000})"
    )
    out2 = "\n".join(
        [
            f"offload threshold (config)   : {cfg.s3_result_offload_threshold:,} simulations",
            f"s3 key                       : {key}",
            f"object                       : Parquet, ~{len(data) / 1e6:.1f} MB, {table.num_rows} row, "
            f"loss_dist of {len(table.column('loss_dist')[0]):,} values",
            f"presigned url (without query): {url.split('?')[0]}",
            f"hydrated result keys         : {sorted(hydrated)}",
        ]
    )
    ex2 = Example(
        "arch-storage",
        "Large results go to S3 and come back as a presigned URL",
        "Above the offload threshold the worker writes the full result, loss distribution included, to S3 as "
        "Parquet. The API attaches a fresh presigned URL whenever a result is served. AWS is mocked with moto.",
        [Step("storage.s3", code2, out2, call_lang="python", result_lang="text")],
        f"A 200,000-path run is above the {cfg.s3_result_offload_threshold:,}-simulation threshold, so the full "
        f"result is stored as a single-row Parquet object under results/<prefix>/<task_id>.parquet with the "
        f"200,000-value loss distribution intact, and what travels through the Celery result backend is the "
        f"s3_key. hydrate_presigned_url turns that key into a time-limited link at the moment a client asks, "
        f"so the link is never stale.",
    )
    return [ex1, ex2]


def request_counts(metrics_text: str) -> dict[str, float]:
    """http_requests_total samples from a /metrics scrape, keyed by their label set."""
    counts: dict[str, float] = {}
    for line in metrics_text.splitlines():
        m = re.match(r"http_requests_total(\{.*\}) ([0-9.e+]+)$", line)
        if m:
            counts[m.group(1)] = float(m.group(2))
    return counts


async def ex_observability() -> list[Example]:
    from api.middleware.auth import create_access_token
    from engine.montecarlo import run_monte_carlo_var
    from observability.setup import track_computation

    returns = generate_gbm_returns(252, seed=5).tolist()
    base = {
        "portfolio_value": 1_000_000,
        "returns": returns,
        "confidence_level": 0.99,
        "horizon_days": 1,
        "n_simulations": 50_000,
    }
    ph = {"returns": "252 daily log-returns: generate_gbm_returns(252, seed=5)"}
    ent = create_access_token("dave", "enterprise")
    steps: list[Step] = []
    details: list[dict[str, Any]] = []
    async with gateway_client(celery=True) as client:
        api = Api(client, {})
        for label, body, ph_ in (
            (
                "confidence_level outside the regulatory range",
                {**base, "confidence_level": 0.5},
                ph,
            ),
            ("fewer than 30 observations", {**base, "returns": returns[:10]}, None),
        ):
            step, status, resp = await api.raw("/api/v1/var/compute", body, ent, ph_, name=label)
            err = resp["detail"][0]
            err = {k: err[k] for k in ("type", "loc", "msg")}
            step.result = pretty({"detail": [err]})
            if ph_ is None:
                step.call = "POST /api/v1/var/compute\n" + show_params(
                    {**body, "returns": None}, {"returns": "10 daily log-returns"}
                )
            steps.append(step)
            details.append(err)
        # A bare NaN token is not valid JSON but json.loads accepts it, so it has to be
        # rejected by validation rather than reach the engine.
        raw = json.dumps({**base, "returns": returns}).replace(str(returns[0]), "NaN", 1)
        resp = await client.post(
            "/api/v1/var/compute",
            content=raw,
            headers={"Authorization": f"Bearer {ent}", "Content-Type": "application/json"},
        )
        err = {k: resp.json()["detail"][0][k] for k in ("type", "loc", "msg")}
        steps.append(
            Step(
                "a NaN in the returns",
                "POST /api/v1/var/compute\n"
                + show_params(
                    {**base, "returns": None},
                    {"returns": "252 daily log-returns, the first one replaced by NaN"},
                ),
                pretty({"detail": [err]}),
                status=resp.status_code,
            )
        )
        details.append(err)
    ex1 = Example(
        "arch-observability",
        "Input validation: regulatory bounds enforced at the edge",
        "Bad input is stopped by the Pydantic schema before a job exists. Three requests break the rules in "
        "different ways.",
        steps,
        f"All three requests return {steps[0].status}. A confidence level of 0.5 is rejected with a message that "
        f"lists the conventional values (0.95 internal, 0.99 Basel III, 0.975 FRTB ES) and the allowed range "
        f"0.90 to 0.9999; a 10-observation series is rejected because the minimum is 30; and a NaN inside the "
        f"returns is refused with the same status. The error carries the field location, so a client can "
        f"point at the offending parameter.",
    )

    async with gateway_client() as client:
        api = Api(client, {})
        before = request_counts((await client.get("/metrics")).text)
        for _ in range(3):
            await api.raw(
                "/api/v1/credit-risk/expected_loss_el_computation",
                {"pd": 0.02, "lgd": 0.45, "ead": 1e6},
                ent,
            )
        await api.raw("/api/v1/credit-risk/expected_loss_el_computation", {}, ent)
        with track_computation(0.99, 1, 50_000):
            run_monte_carlo_var(generate_gbm_returns(252, seed=5), 1e6, 0.99, 1, 50_000, seed=1)
        metrics = await client.get("/metrics")
    lines = metrics.text.splitlines()
    custom = []
    for line in lines:
        if line.startswith("pyvar_") and "_bucket" not in line and "_created" not in line:
            name, value = line.rsplit(" ", 1)
            if "_sum" in name and "duration" in name:
                custom.append(f"{name} <elapsed seconds, varies per run>")
            else:
                custom.append(f"{name} {float(value):g}")
    after = request_counts(metrics.text)
    increase = {k: after[k] - before.get(k, 0) for k in after if after[k] - before.get(k, 0)}
    code2 = (
        "# scrape, send three valid calls and one 422, run a 50,000-path VaR inside track_computation()\n"
        "with track_computation(0.99, 1, 50_000):\n"
        "    run_monte_carlo_var(returns, 1e6, 0.99, 1, 50_000, seed=1)\n"
        "GET /metrics"
    )
    out2 = "\n".join(
        custom
        + [
            *[
                f"http_requests_total{labels} +{int(delta)}"
                for labels, delta in sorted(increase.items())
            ]
        ]
    )
    ex2 = Example(
        "arch-observability",
        "Prometheus metrics for computations and HTTP traffic",
        "The app exposes /metrics. Domain metrics are recorded around the engine call, and request counters "
        "come from the HTTP instrumentation.",
        [Step("GET /metrics", code2, out2, call_lang="text", result_lang="text")],
        "Between two scrapes, three successful calls and one rejected one raise the HTTP counters by three 2xx and "
        "one 4xx, labelled with the route template (not the raw URL), so a dashboard groups by endpoint. "
        "The computation histogram is labelled by confidence level and horizon, and the simulation-count "
        "histogram records the 50,000 paths of the run, which is what a Grafana panel of latency per "
        "simulation size is built on.",
    )
    return [ex1, ex2]


# ── pyvar-mcp examples ───────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def ex_mcp() -> list[Example]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from api.middleware.auth import create_access_token

    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        async with AsyncClient(timeout=1) as probe:
            for _ in range(120):
                try:
                    await probe.get(f"http://127.0.0.1:{port}/health")
                    break
                except HTTPError:
                    await asyncio.sleep(0.5)
            else:
                raise RuntimeError("local pyvar API did not start")
        env = {
            **os.environ,
            "PYVAR_API_KEY": create_access_token("example-mcp", "enterprise"),
            "PYVAR_API_BASE_URL": f"http://127.0.0.1:{port}",
        }
        params = StdioServerParameters(
            command=str(Path(sys.executable).parent / "pyvar-mcp"), env=env
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            listing = await session.call_tool("list_pyvar_functions", {"domain": "alm"})
            functions = json.loads(listing.content[0].text)["functions"]
            args = {
                "domain": "credit-risk",
                "function_name": "expected_loss_el_computation",
                "params": {"pd": 0.02, "lgd": 0.45, "ead": 1_000_000},
            }
            ok = await session.call_tool("call_pyvar_function", args)
            named = await session.call_tool(
                "expected_loss_el_computation", {"pd": 0.02, "lgd": 0.45, "ead": 1_000_000}
            )
            missing = await session.call_tool(
                "call_pyvar_function", {**args, "params": {"pd": 0.02, "lgd": 0.45}}
            )
            invalid = await session.call_tool(
                "call_pyvar_function",
                {**args, "params": {"pd": 1.7, "lgd": 0.45, "ead": 1_000_000}},
            )
            unknown = await session.call_tool(
                "call_pyvar_function",
                {"domain": "alm", "function_name": "no_such_function", "params": {}},
            )
    finally:
        server.terminate()
        server.wait(timeout=15)

    generic = [t.name for t in tools[:2]]
    shown = functions[:2]
    out1 = "\n".join(
        [
            f"tools exposed by the server : {len(tools)} ({len(tools) - 2} named + {', '.join(generic)})",
            f"functions in domain 'alm'   : {len(functions)}",
            "first two entries:",
            pretty(shown),
        ]
    )
    ex1 = Example(
        "pyvar-mcp",
        "Discovering the catalogue from Claude Code",
        "The MCP server starts over stdio and exposes every pyvar function as a tool, plus a generic "
        "discovery tool. This session talks to a locally running pyvar API.",
        [
            Step(
                "tools/list + list_pyvar_functions",
                'list_pyvar_functions(domain="alm")',
                out1,
                call_lang="text",
                result_lang="text",
            )
        ],
        f"The server advertises {len(tools)} tools: one named tool per catalogued function ({len(tools) - 2}) and "
        f"the two generic ones. list_pyvar_functions returns each function's name, one-line summary and "
        f"required parameter names, filtered to a domain, so the model can find the right function without "
        f"holding 385 schemas in context.",
    )

    def text(res: Any) -> str:
        return str(res.content[0].text)

    steps2 = [
        Step("call_pyvar_function", pretty(args), text(ok), call_lang="json", result_lang="json"),
        Step(
            "same function as a named tool",
            "expected_loss_el_computation(pd=0.02, lgd=0.45, ead=1000000)",
            text(named),
            call_lang="text",
            result_lang="json",
        ),
        Step(
            "missing a required parameter",
            pretty({**args, "params": {"pd": 0.02, "lgd": 0.45}}),
            text(missing),
            call_lang="json",
            result_lang="text",
        ),
        Step(
            "a value the API rejects",
            pretty({**args, "params": {"pd": 1.7, "lgd": 0.45, "ead": 1_000_000}}),
            text(invalid),
            call_lang="json",
            result_lang="text",
        ),
        Step(
            "an unknown function",
            pretty({"domain": "alm", "function_name": "no_such_function", "params": {}}),
            text(unknown),
            call_lang="json",
            result_lang="text",
        ),
    ]
    ex2 = Example(
        "pyvar-mcp",
        "Calling a function, and what errors look like",
        "The generic call tool and the named tool reach the same endpoint. Mistakes come back as readable tool "
        "results, not protocol failures.",
        steps2,
        f"The generic tool and the named tool return identical results (expected loss of "
        f"{json.loads(text(ok))['el']:,.0f}). A missing parameter is caught before any request is made, with the "
        f"expected parameter names listed; a value outside the allowed range comes back from the API as an HTTP 422 "
        f"message; an unknown function name points the model back to list_pyvar_functions. Each is flagged "
        f"is_error, so the model can read it and correct the call.",
    )
    return [ex1, ex2]


# ── Rendering ────────────────────────────────────────────────────────────────

PLUGINS: list[tuple[str, str, str]] = [
    ("market-risk", "pyvar-market-risk", "VaR, Expected Shortfall, backtesting"),
    ("credit-risk", "pyvar-credit-risk", "PD/LGD/EAD, credit VaR, scoring"),
    ("liquidity-risk", "pyvar-liquidity-risk", "LCR, NSFR, survival horizon"),
    ("operational-risk", "pyvar-operational-risk", "SMA capital, KRIs"),
    ("portfolio-analytics", "pyvar-portfolio-analytics", "allocation and performance statistics"),
    ("regulatory", "pyvar-regulatory", "Basel III/IV capital tests"),
    ("derivatives", "pyvar-derivatives", "options and fixed income"),
    ("alm", "pyvar-alm", "duration gap, repricing, IRRBB"),
    ("arch-api-gateway", "pyvar-arch-api-gateway", "authentication, tiers, rate limits"),
    ("arch-compute", "pyvar-arch-compute", "the Numba Monte Carlo engine"),
    ("arch-data-ingestion", "pyvar-arch-data-ingestion", "Polars and PyArrow I/O"),
    ("arch-storage", "pyvar-arch-storage", "Redis cache and S3 results"),
    ("arch-observability", "pyvar-arch-observability", "validation and Prometheus metrics"),
    ("pyvar-mcp", "pyvar-mcp", "385 functions as MCP tools"),
]


def render(examples: list[Example], with_mcp: bool) -> str:
    out: list[str] = [
        "# pyvar plugin examples\n",
        "Two worked examples for each of pyvar's Claude Code plugins: the eight domain skills, the five "
        "architecture skills and the `pyvar-mcp` server. Every request, response and number below was produced "
        "by running the real pyvar code, and the prose is generated from those results by "
        "`scripts/generate_plugin_examples.py`.\n",
        "## How these were produced\n",
        "- **Domain plugins** POST to the real FastAPI app (`create_app()` behind an in-process HTTP transport), "
        "authenticated with a JWT, exactly as the endpoints are called in production.",
        "- **Architecture plugins** call the real modules: the gateway routes and middleware, "
        "`engine.montecarlo`, `ingestion.loader`, `storage.s3` and `observability.setup`. The Celery queue "
        "and the audit database are replaced by stand-ins where a request would otherwise need them, and AWS "
        "is mocked with moto.",
        "- **pyvar-mcp** is the real MCP server, started over stdio and pointed at a local pyvar API.",
        "- All inputs are synthetic (`ingestion.fixtures.generate_gbm_returns`), with the seed shown next to "
        "each call. No real market data and no real AWS services are used.\n",
        "To regenerate this file: `python scripts/generate_plugin_examples.py`.\n",
    ]
    for key, plugin, blurb in PLUGINS:
        mine = [e for e in examples if e.plugin == key]
        if not mine:
            continue
        out.append(f"## {plugin}\n")
        out.append(f"*{blurb}*\n")
        for i, ex in enumerate(mine, 1):
            out.append(f"### Example {i}: {ex.title}\n")
            out.append(ex.why + "\n")
            for st in ex.steps:
                status = f" (HTTP {st.status})" if st.status is not None else ""
                out.append(f"**{st.name}**\n")
                out.append(f"```{st.call_lang}\n{st.call}\n```\n")
                out.append(f"Result{status}:\n")
                out.append(f"```{st.result_lang}\n{st.result}\n```\n")
            out.append(f"**What to notice.** {ex.reading}\n")
    if not with_mcp:
        out.append("*(The pyvar-mcp examples were skipped in this run: `--skip-mcp`.)*\n")
    return "\n".join(out)


async def main_async(skip_mcp: bool) -> list[Example]:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    from api.middleware.auth import create_access_token

    examples: list[Example] = []
    app = get_app()
    tokens = {t: create_access_token(f"example-{t}", t) for t in ("free", "pro", "enterprise")}
    fresh = Limiter(key_func=get_remote_address, storage_uri="memory://")
    with patch("api.middleware.rate_limit._limiter", fresh), patch("sentry_sdk.init"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            api = Api(client, tokens)
            for fn in DOMAIN_EXAMPLES:
                examples.extend(await fn(api))
    examples.extend(await ex_api_gateway())
    examples.extend(ex_compute())
    examples.extend(ex_data_ingestion())
    examples.extend(ex_storage_in_thread())
    examples.extend(await ex_observability())
    if not skip_mcp:
        examples.extend(await ex_mcp())
    return examples


def ex_storage_in_thread() -> list[Example]:
    """ex_storage drives its own event loop (asyncio.run); keep it out of the running one."""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(ex_storage).result()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default=str(ROOT / "docs" / "plugin-examples.md"))
    parser.add_argument("--skip-mcp", action="store_true")
    args = parser.parse_args()
    examples = asyncio.run(main_async(args.skip_mcp))
    Path(args.out).write_text(render(examples, not args.skip_mcp))
    print(
        f"wrote {args.out}: {len(examples)} examples, {sum(len(e.steps) for e in examples)} calls"
    )


if __name__ == "__main__":
    main()

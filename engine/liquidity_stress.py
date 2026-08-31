"""engine/liquidity_stress.py — liquidity stress scenarios and survival analytics.

Implements the stress-testing sub-domain: idiosyncratic, market-wide and
combined run-off scenarios, the survival-horizon calculator, intraday liquidity
monitoring and stress, the ILAAP stress framework, and Liquidity VaR (LiqVaR).

LiqVaR uses a Monte Carlo simulation of stressed net outflows; per CLAUDE.md
§3.1 RULE 3 all random numbers are pre-drawn in pure Python and the summing
kernel is a stateless ``@njit(cache=True)`` function operating on float64
arrays only.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numba import njit, prange
from scipy import stats

__all__ = [
    "liquidity_stress_scenario",
    "idiosyncratic_stress_scenario",
    "market_wide_stress_scenario",
    "combined_stress_scenario",
    "survival_horizon_calculator",
    "intraday_liquidity_monitor",
    "intraday_liquidity_stress_test",
    "ilaap_stress_testing_framework",
    "liquidity_var_liqvar",
]


@njit(parallel=True, cache=True)
def _simulate_net_outflows(
    base_outflow: float,
    shocks: np.ndarray,
    vol: float,
) -> np.ndarray:
    """Simulate stressed net-outflow draws (RULE 3/5: pre-drawn shocks, array out).

    Each draw is ``base_outflow * (1 + vol * z)`` floored at zero. The shock
    array is pre-drawn N(0,1) in pure Python; the kernel only scales it.
    """
    n = shocks.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in prange(n):
        val = base_outflow * (1.0 + vol * shocks[i])
        out[i] = val if val > 0.0 else 0.0
    return out


def _apply_runoff(
    balances: np.ndarray,
    runoff_rates: np.ndarray,
) -> np.ndarray:
    """Outflow per category = balance * run-off rate (pure NumPy helper)."""
    return np.asarray(balances * runoff_rates, dtype=np.float64)


def liquidity_stress_scenario(
    balances: np.ndarray,
    runoff_rates: np.ndarray,
    hqla: float,
    inflows: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Generic single liquidity stress scenario.

    Applies category-specific run-off rates to funding balances to derive
    stressed outflows, nets inflows, and tests whether HQLA covers the net
    stressed outflow.

    Args:
        balances: Outstanding balance of each funding category.
        runoff_rates: Stressed run-off rate per category, each in [0, 1].
        hqla: Available high-quality liquid assets (post-haircut).
        inflows: Stressed contractual inflows over the horizon.

    Returns:
        Dict with ``stressed_outflow``, ``net_outflow``, ``surplus_deficit``
        (HQLA - net outflow) and a ``survives`` flag.

    Raises:
        ValueError: If lengths differ or run-off rates lie outside [0, 1].
    """
    bal = np.asarray(balances, dtype=np.float64)
    rates = np.asarray(runoff_rates, dtype=np.float64)
    if bal.shape != rates.shape:
        raise ValueError("balances and runoff_rates must have equal length")
    if np.any(rates < 0.0) or np.any(rates > 1.0):
        raise ValueError("runoff_rates must lie in [0, 1]")

    outflow = float(np.sum(_apply_runoff(bal, rates)))
    net = outflow - inflows
    surplus = hqla - net
    return {
        "stressed_outflow": round(outflow, 2),
        "net_outflow": round(net, 2),
        "surplus_deficit": round(surplus, 2),
        "survives": bool(surplus >= 0.0),
    }


def idiosyncratic_stress_scenario(
    retail_deposits: float,
    wholesale_funding: float,
    hqla: float,
    retail_runoff: float = 0.10,
    wholesale_runoff: float = 1.00,
) -> dict:  # type: ignore[type-arg]
    """Idiosyncratic (name-specific) stress scenario.

    Models a firm-specific crisis (e.g. rating downgrade): partial retail
    deposit flight and complete loss of wholesale funding rollover. Wholesale
    run-off defaults to 100% — the hallmark of a name-specific shock.

    Args:
        retail_deposits: Retail deposit balance.
        wholesale_funding: Wholesale funding balance.
        hqla: Available HQLA.
        retail_runoff: Retail run-off rate (default 10%).
        wholesale_runoff: Wholesale run-off rate (default 100%).

    Returns:
        Dict with ``stressed_outflow``, ``surplus_deficit`` and ``survives``.

    Raises:
        ValueError: If run-off rates lie outside [0, 1].
    """
    if not (0.0 <= retail_runoff <= 1.0 and 0.0 <= wholesale_runoff <= 1.0):
        raise ValueError("run-off rates must lie in [0, 1]")
    outflow = retail_deposits * retail_runoff + wholesale_funding * wholesale_runoff
    surplus = hqla - outflow
    return {
        "stressed_outflow": round(float(outflow), 2),
        "surplus_deficit": round(float(surplus), 2),
        "survives": bool(surplus >= 0.0),
        "scenario": "idiosyncratic",
    }


def market_wide_stress_scenario(
    hqla_by_level: np.ndarray,
    market_haircuts: np.ndarray,
    outflow: float,
) -> dict:  # type: ignore[type-arg]
    """Market-wide stress scenario.

    Models a system-wide crisis where HQLA monetisation value falls due to
    widened market haircuts (flight to quality, fire-sale discounts). Outflows
    are met from the haircut-reduced HQLA value.

    Args:
        hqla_by_level: HQLA market value per level (e.g. [L1, L2A, L2B]).
        market_haircuts: Additional stressed haircut per level, each in [0, 1].
        outflow: Stressed net cash outflow over the horizon.

    Returns:
        Dict with ``stressed_hqla`` (post additional haircut), ``surplus_deficit``
        and ``survives``.

    Raises:
        ValueError: If lengths differ or haircuts lie outside [0, 1].
    """
    hqla = np.asarray(hqla_by_level, dtype=np.float64)
    hc = np.asarray(market_haircuts, dtype=np.float64)
    if hqla.shape != hc.shape:
        raise ValueError("hqla_by_level and market_haircuts must have equal length")
    if np.any(hc < 0.0) or np.any(hc > 1.0):
        raise ValueError("market_haircuts must lie in [0, 1]")

    stressed_hqla = float(np.sum(hqla * (1.0 - hc)))
    surplus = stressed_hqla - outflow
    return {
        "stressed_hqla": round(stressed_hqla, 2),
        "surplus_deficit": round(surplus, 2),
        "survives": bool(surplus >= 0.0),
        "scenario": "market_wide",
    }


def combined_stress_scenario(
    retail_deposits: float,
    wholesale_funding: float,
    hqla_by_level: np.ndarray,
    market_haircuts: np.ndarray,
    retail_runoff: float = 0.15,
    wholesale_runoff: float = 1.00,
    inflows: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Combined idiosyncratic + market-wide stress scenario.

    This is NOT the BCBS 238 reference combined scenario: BCBS 238's own
    combined idiosyncratic + market-wide scenario (§II paras 19-20) runs off
    the LCR's own regulator-set retail run-off categories (3%/5%/10%
    depending on deposit stability), whereas this function applies its own
    flat 15% retail / 100% wholesale run-off convention instead.

    Models a firm-specific shock occurring inside a market-wide crisis:
    liability run-off is aggravated (default 15% retail, 100% wholesale)
    *and* HQLA value is reduced by stressed market haircuts, simultaneously.
    (Found during the Tier 3 #2 audit — a prior version of this docstring
    incorrectly claimed this was the Basel/EBA reference scenario.)

    Args:
        retail_deposits: Retail deposit balance.
        wholesale_funding: Wholesale funding balance.
        hqla_by_level: HQLA market value per level.
        market_haircuts: Additional stressed haircut per level, each in [0, 1].
        retail_runoff: Retail run-off rate (default 15%).
        wholesale_runoff: Wholesale run-off rate (default 100%).
        inflows: Stressed contractual inflows.

    Returns:
        Dict with ``stressed_outflow``, ``stressed_hqla``, ``net_outflow``,
        ``surplus_deficit`` and ``survives``. The combined deficit is never
        better than either component scenario alone.

    Raises:
        ValueError: If shapes or rates are invalid.
    """
    mw = market_wide_stress_scenario(hqla_by_level, market_haircuts, 0.0)
    if not (0.0 <= retail_runoff <= 1.0 and 0.0 <= wholesale_runoff <= 1.0):
        raise ValueError("run-off rates must lie in [0, 1]")

    outflow = retail_deposits * retail_runoff + wholesale_funding * wholesale_runoff
    net = outflow - inflows
    stressed_hqla = mw["stressed_hqla"]
    surplus = stressed_hqla - net
    return {
        "stressed_outflow": round(float(outflow), 2),
        "stressed_hqla": round(float(stressed_hqla), 2),
        "net_outflow": round(float(net), 2),
        "surplus_deficit": round(float(surplus), 2),
        "survives": bool(surplus >= 0.0),
        "scenario": "combined",
    }


def survival_horizon_calculator(
    hqla: float,
    daily_net_outflows: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Survival horizon — days until cumulative net outflow exhausts HQLA.

    Walks forward through the daily net-outflow path subtracting from the HQLA
    counterbalancing capacity. The survival horizon is the last day on which the
    remaining buffer is still non-negative.

    Args:
        hqla: Opening counterbalancing capacity (HQLA).
        daily_net_outflows: Array of daily net cash outflows (positive = drain).

    Returns:
        Dict with ``survival_days`` (int; -1 if exhausted before day 1, or
        ``len`` if it survives the whole path) and ``terminal_buffer``.

    Raises:
        ValueError: If the outflow path is empty.
    """
    outflows = np.asarray(daily_net_outflows, dtype=np.float64)
    if outflows.size == 0:
        raise ValueError("daily_net_outflows must be non-empty")

    buffer = hqla
    survival_days = outflows.size  # survives entire path unless broken
    for day in range(outflows.size):
        buffer -= outflows[day]
        if buffer < 0.0:
            survival_days = day  # exhausted during this day -> survived `day` full days
            break
    return {
        "survival_days": int(survival_days),
        "terminal_buffer": round(float(buffer), 2),
        "hqla": round(float(hqla), 2),
    }


def intraday_liquidity_monitor(
    timestamps: np.ndarray,
    net_flows: np.ndarray,
    opening_balance: float,
) -> dict:  # type: ignore[type-arg]
    """Intraday liquidity monitor (BCBS 248).

    Of the two figures reported, only ``net_debit_peak`` (the largest negative
    cumulative position) is the genuine BCBS 248 "largest net debit position"
    monitoring tool — ``max_usage`` is this codebase's own additional metric,
    not one of BCBS 248's own monitoring tools.

    Tracks the intraday liquidity position from time-stamped net payment flows
    and reports the peak usage (largest negative intraday position relative to
    the opening balance) and the largest net debit position.

    Args:
        timestamps: Monotonic intraday timestamps (seconds/minutes from open).
        net_flows: Net payment flow at each timestamp (credit +, debit -).
        opening_balance: Available intraday liquidity at start of day.

    Returns:
        Dict with ``max_usage`` (largest drop below opening), ``min_balance``,
        ``net_debit_peak`` and ``closing_balance``.

    Raises:
        ValueError: If lengths differ or timestamps are non-monotonic.
    """
    ts = np.asarray(timestamps, dtype=np.float64)
    flows = np.asarray(net_flows, dtype=np.float64)
    if ts.shape != flows.shape:
        raise ValueError("timestamps and net_flows must have equal length")
    if ts.size > 1 and np.any(np.diff(ts) < 0.0):
        raise ValueError("timestamps must be monotonically non-decreasing")

    balance_path = opening_balance + np.cumsum(flows)
    min_balance = float(np.min(balance_path)) if balance_path.size else opening_balance
    max_usage = max(0.0, opening_balance - min_balance)
    net_debit_peak = max(0.0, -min_balance)
    return {
        "max_usage": round(max_usage, 2),
        "min_balance": round(min_balance, 2),
        "net_debit_peak": round(net_debit_peak, 2),
        "closing_balance": round(
            float(balance_path[-1]) if balance_path.size else opening_balance, 2
        ),
    }


def intraday_liquidity_stress_test(
    net_flows: np.ndarray,
    opening_balance: float,
    delay_factor: float = 0.5,
    inflow_delay_shock: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Intraday liquidity stress test (BCBS 248 stress scenarios).

    This is this codebase's own internal stress design — delaying a fraction
    of positive intraday inflows — set in the context of BCBS 248's intraday-
    liquidity monitoring framework; it is not BCBS 248's own prescribed stress
    design.

    Stresses the intraday profile by delaying a fraction of *inflows* (positive
    flows): a ``delay_factor`` of expected inflows is removed from the intraday
    path, sharpening the peak liquidity requirement. Reports the stressed peak
    usage and whether the opening buffer plus any additional shock survives.

    Args:
        net_flows: Net payment flow at each intraday step (credit +, debit -).
        opening_balance: Available intraday liquidity at start of day.
        delay_factor: Fraction of positive inflows delayed beyond the horizon,
            in [0, 1].
        inflow_delay_shock: Extra absolute liquidity reserved against the shock.

    Returns:
        Dict with ``stressed_max_usage``, ``stressed_min_balance`` and a
        ``survives`` flag.

    Raises:
        ValueError: If ``delay_factor`` lies outside [0, 1].
    """
    if not 0.0 <= delay_factor <= 1.0:
        raise ValueError("delay_factor must lie in [0, 1]")
    flows = np.asarray(net_flows, dtype=np.float64)
    stressed = flows.copy()
    # Delay (remove) a fraction of inflows from the intraday path.
    inflow_mask = stressed > 0.0
    stressed[inflow_mask] = stressed[inflow_mask] * (1.0 - delay_factor)

    balance_path = opening_balance - inflow_delay_shock + np.cumsum(stressed)
    min_balance = float(np.min(balance_path)) if balance_path.size else opening_balance
    max_usage = max(0.0, (opening_balance - inflow_delay_shock) - min_balance)
    return {
        "stressed_max_usage": round(max_usage, 2),
        "stressed_min_balance": round(min_balance, 2),
        "survives": bool(min_balance >= 0.0),
    }


def ilaap_stress_testing_framework(
    scenarios: dict[str, Any],
) -> dict:  # type: ignore[type-arg]
    """ILAAP stress-testing framework aggregator.

    Aggregates the outcomes of multiple named liquidity stress scenarios into an
    ILAAP-style summary: the binding (worst) scenario, the count of scenarios
    breached, and overall adequacy. Each scenario value must expose a
    ``surplus_deficit`` figure (as produced by the scenario functions above).

    Args:
        scenarios: Mapping ``name -> {"surplus_deficit": float, ...}``.

    Returns:
        Dict with ``binding_scenario``, ``worst_surplus_deficit``,
        ``num_breached`` and ``adequate`` (all scenarios survive).

    Raises:
        ValueError: If ``scenarios`` is empty or a value lacks
            ``surplus_deficit``.
    """
    if not scenarios:
        raise ValueError("scenarios must be non-empty")

    worst_name = ""
    worst_val = np.inf
    num_breached = 0
    for name, res in scenarios.items():
        if "surplus_deficit" not in res:
            raise ValueError(f"scenario '{name}' missing 'surplus_deficit'")
        sd = float(res["surplus_deficit"])
        if sd < 0.0:
            num_breached += 1
        if sd < worst_val:
            worst_val = sd
            worst_name = name
    return {
        "binding_scenario": worst_name,
        "worst_surplus_deficit": round(float(worst_val), 2),
        "num_breached": num_breached,
        "adequate": bool(num_breached == 0),
    }


def liquidity_var_liqvar(
    base_outflow: float,
    outflow_vol: float,
    confidence_level: float = 0.99,
    n_simulations: int = 100_000,
    seed: int | None = 42,
) -> dict:  # type: ignore[type-arg]
    """Liquidity VaR (LiqVaR) by Monte Carlo simulation of stressed net outflows.

    Simulates the distribution of stressed net cash outflows as
    ``base_outflow * (1 + vol * Z)`` and reads the loss quantile at the
    confidence level. LiqVaR is the outflow level not exceeded with the given
    confidence — the liquidity analogue of market VaR.

    Per CLAUDE.md §3.1 RULE 3 the N(0,1) shocks are pre-drawn in pure Python and
    passed to the JIT kernel; an analytic normal quantile is also returned for
    validation.

    Args:
        base_outflow: Expected net cash outflow.
        outflow_vol: Relative volatility of net outflow (>= 0).
        confidence_level: Confidence in [0.90, 0.9999].
        n_simulations: Number of Monte Carlo draws.
        seed: RNG seed for reproducibility.

    Returns:
        Dict with ``liqvar`` (simulated quantile), ``liqvar_analytic`` (normal
        closed form), ``expected_outflow`` and ``confidence_level``.

    Raises:
        ValueError: If volatility is negative or confidence is out of range.
    """
    if outflow_vol < 0.0:
        raise ValueError("outflow_vol must be non-negative")
    if not 0.90 <= confidence_level <= 0.9999:
        raise ValueError("confidence_level must lie in [0.90, 0.9999]")

    if seed is not None:
        np.random.seed(seed)
    shocks = np.random.randn(n_simulations)
    draws = _simulate_net_outflows(base_outflow, shocks, outflow_vol)
    draws.sort()
    idx = min(int(np.floor(confidence_level * n_simulations)), n_simulations - 1)
    liqvar = float(draws[idx])

    z = float(stats.norm.ppf(confidence_level))
    liqvar_analytic = float(max(base_outflow * (1.0 + outflow_vol * z), 0.0))
    return {
        "liqvar": round(liqvar, 2),
        "liqvar_analytic": round(liqvar_analytic, 2),
        "expected_outflow": round(float(base_outflow), 2),
        "confidence_level": confidence_level,
        "n_simulations": n_simulations,
    }

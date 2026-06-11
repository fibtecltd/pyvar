"""engine/alm_ftp.py — Funds Transfer Pricing & strategic ALM analytics.

Funds transfer pricing of individual deals, FTP (matched-maturity) curve
construction, structural-hedge optimisation, an ALM stress test across the six
IRRBB shocks, and a balance-sheet projection model.

Structural-hedge optimisation uses SciPy bounded least-squares; everything else
is vectorised NumPy in pure-Python wrappers (CLAUDE.md §3.1 satisfied trivially).
"""

from __future__ import annotations

import numpy as np
from scipy import optimize

from engine.alm_nii_eve import eve_sensitivity_analysis

__all__ = [
    "funds_transfer_pricing_ftp",
    "ftp_curve_construction",
    "structural_hedge_optimisation",
    "alm_stress_test",
    "balance_sheet_projection_model",
]


def funds_transfer_pricing_ftp(
    notional: float,
    customer_rate: float,
    ftp_rate: float,
    liquidity_premium: float = 0.0,
    is_asset: bool = True,
) -> dict:  # type: ignore[type-arg]
    """Funds-transfer-price a single deal into margin components.

    For an asset, the lending unit earns ``customer_rate − ftp_rate`` (credit /
    commercial margin) while the central treasury earns the FTP minus its cost.
    A liquidity premium is charged on the FTP. Margins sum to the total spread.

    Args:
        notional: Deal notional (currency).
        customer_rate: Rate charged to / paid to the customer (decimal).
        ftp_rate: Matched-maturity transfer rate (decimal).
        liquidity_premium: Liquidity charge added to the FTP (decimal).
        is_asset: True for an asset (loan), False for a liability (deposit).

    Returns:
        Dict with ``commercial_margin``, ``funding_value``, ``total_spread`` (all
        in currency per annum).

    Raises:
        ValueError: If ``notional`` is non-positive.
    """
    if notional <= 0:
        raise ValueError("notional must be positive")
    all_in_ftp = ftp_rate + liquidity_premium
    if is_asset:
        commercial = (customer_rate - all_in_ftp) * notional
    else:  # liability: unit earns FTP minus the rate paid to customer
        commercial = (all_in_ftp - customer_rate) * notional
    funding = all_in_ftp * notional
    return {
        "commercial_margin": round(float(commercial), 6),
        "funding_value": round(float(funding), 6),
        "total_spread": round(float(abs(customer_rate - all_in_ftp) * notional), 6),
    }


def ftp_curve_construction(
    tenors: np.ndarray,
    base_curve: np.ndarray,
    liquidity_spreads: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Construct a matched-maturity FTP curve = base curve + liquidity spread.

    Each tenor's transfer rate adds a term-liquidity spread to the base funding
    curve. The curve is non-decreasing in the spread component by construction.

    Args:
        tenors: Tenor points in years (ascending).
        base_curve: Base funding rate per tenor (decimal).
        liquidity_spreads: Term-liquidity spread per tenor (decimal).

    Returns:
        Dict with ``ftp_curve`` per tenor and the ``tenors``.

    Raises:
        ValueError: If array lengths are inconsistent.
    """
    t = np.asarray(tenors, dtype=np.float64)
    base = np.asarray(base_curve, dtype=np.float64)
    liq = np.asarray(liquidity_spreads, dtype=np.float64)
    if not (t.size == base.size == liq.size):
        raise ValueError("tenors, base_curve, liquidity_spreads must match length")
    ftp = base + liq
    return {
        "ftp_curve": [round(float(r), 10) for r in ftp],
        "tenors": t.tolist(),
    }


def structural_hedge_optimisation(
    target_duration: float,
    instrument_durations: np.ndarray,
    instrument_max_notional: np.ndarray,
    equity_notional: float,
) -> dict:  # type: ignore[type-arg]
    """Optimise a structural hedge to a target equity duration.

    Solves for non-negative hedge notionals (bounded by per-instrument caps)
    that bring the dollar-duration of the hedge as close as possible to the
    target ``equity_notional · target_duration``.

    Args:
        target_duration: Desired equity duration (years).
        instrument_durations: Duration of each hedge instrument (years).
        instrument_max_notional: Max notional per instrument (currency).
        equity_notional: Equity notional to hedge (currency).

    Returns:
        Dict with ``hedge_notionals``, ``achieved_duration`` and ``residual``.

    Raises:
        ValueError: If array lengths mismatch or equity non-positive.
    """
    d = np.asarray(instrument_durations, dtype=np.float64)
    cap = np.asarray(instrument_max_notional, dtype=np.float64)
    if d.size != cap.size:
        raise ValueError("instrument arrays must match length")
    if equity_notional <= 0:
        raise ValueError("equity_notional must be positive")

    target_dollar_dur = equity_notional * target_duration

    def resid(x: np.ndarray) -> np.ndarray:
        return np.array([float(np.dot(d, x)) - target_dollar_dur])

    sol = optimize.lsq_linear(
        d.reshape(1, -1), np.array([target_dollar_dur]), bounds=(0.0, cap)
    )
    notionals = sol.x
    achieved_dollar = float(np.dot(d, notionals))
    achieved_dur = achieved_dollar / equity_notional
    return {
        "hedge_notionals": [round(float(n), 6) for n in notionals],
        "achieved_duration": round(float(achieved_dur), 6),
        "residual": round(float(achieved_dollar - target_dollar_dur), 6),
    }


def alm_stress_test(
    net_cashflows: np.ndarray,
    times: np.ndarray,
    base_rates: np.ndarray,
    tier1_capital: float,
    parallel_bps: float = 200.0,
) -> dict:  # type: ignore[type-arg]
    """Run an ALM stress test: worst-case EVE decline vs Tier-1 capital.

    [REGULATORY] BCBS d368. Computes ΔEVE across the six standard shocks and
    expresses the worst-case loss as a fraction of Tier-1 capital (the
    supervisory outlier ratio).

    Args:
        net_cashflows: Net banking-book cashflow per bucket.
        times: Bucket times in years.
        base_rates: Base zero rate per bucket (decimal).
        tier1_capital: Tier-1 capital (currency, > 0).
        parallel_bps: Parallel shock magnitude (bps).

    Returns:
        Dict with ``worst_case_eve``, ``eve_capital_ratio`` and
        ``breaches_15pct``.

    Raises:
        ValueError: If ``tier1_capital`` is non-positive.
    """
    if tier1_capital <= 0:
        raise ValueError("tier1_capital must be positive")
    sens = eve_sensitivity_analysis(net_cashflows, times, base_rates, parallel_bps=parallel_bps)
    worst = sens["worst_case"]
    ratio = abs(min(worst, 0.0)) / tier1_capital
    return {
        "worst_case_eve": round(float(worst), 6),
        "eve_capital_ratio": round(float(ratio), 8),
        "breaches_15pct": bool(ratio > 0.15),
        "scenario_results": sens["delta_eve"],
    }


def balance_sheet_projection_model(
    initial_assets: float,
    initial_liabilities: float,
    asset_growth_rate: float,
    liability_growth_rate: float,
    asset_yield: float,
    liability_cost: float,
    n_years: int,
) -> dict:  # type: ignore[type-arg]
    """Project the balance sheet and NII forward over ``n_years``.

    Assets and liabilities grow geometrically; equity is the residual; NII each
    year is ``assets·yield − liabilities·cost``. Returns the projected paths.

    Args:
        initial_assets: Opening total assets (currency).
        initial_liabilities: Opening total liabilities (currency).
        asset_growth_rate: Annual asset growth (decimal).
        liability_growth_rate: Annual liability growth (decimal).
        asset_yield: Average asset yield (decimal).
        liability_cost: Average liability cost (decimal).
        n_years: Projection horizon (years, >= 1).

    Returns:
        Dict with ``assets``, ``liabilities``, ``equity`` and ``nii`` paths.

    Raises:
        ValueError: If ``n_years`` < 1.
    """
    if n_years < 1:
        raise ValueError("n_years must be >= 1")

    years = np.arange(1, n_years + 1, dtype=np.float64)
    assets = initial_assets * (1.0 + asset_growth_rate) ** years
    liabs = initial_liabilities * (1.0 + liability_growth_rate) ** years
    equity = assets - liabs
    nii = assets * asset_yield - liabs * liability_cost
    return {
        "assets": [round(float(a), 4) for a in assets],
        "liabilities": [round(float(l), 4) for l in liabs],
        "equity": [round(float(e), 4) for e in equity],
        "nii": [round(float(n), 4) for n in nii],
    }

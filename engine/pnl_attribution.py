"""engine/pnl_attribution.py — P&L explain & attribution (Market Risk).

A first/second-order Taylor "P&L explain" decomposes the change in portfolio
value into Greek-driven components (delta, gamma, vega, theta, rho) plus
risk-class attributions (FX, rates, credit) and an unexplained residual. Also
includes the FRTB P&L Attribution Test (PAT).

The FRTB PAT thresholds are REGULATORY (CLAUDE.md §4.4, BCBS FRTB §9.5) and are
used verbatim: Spearman |corr| >= 0.80 and ratio in [0.8, 1.2] for green;
|corr| >= 0.70 and ratio in [0.6, 1.5] for amber; otherwise red (IMA loss).
"""

from __future__ import annotations

import numpy as np
from scipy import stats

__all__ = [
    "greeks_based_pnl_explain",
    "pnl_attribution_test_frtb_pat",
    "theta_carry_attribution",
]


def greeks_based_pnl_explain(
    delta: float,
    gamma: float,
    vega: float,
    theta: float,
    rho: float,
    spot_move: float,
    vol_move: float,
    time_step: float,
    rate_move: float,
    actual_pnl: float,
) -> dict:  # type: ignore[type-arg]
    """Second-order Greeks P&L explain.

    Predicted P&L = Δ·dS + ½Γ·dS² + ν·dσ + Θ·dt + ρ·dr. The unexplained residual
    is ``actual_pnl − predicted`` — the quantity the FRTB PAT scrutinises.

    Args:
        delta: Portfolio delta (∂V/∂S).
        gamma: Portfolio gamma (∂²V/∂S²).
        vega: Portfolio vega (∂V/∂σ).
        theta: Portfolio theta (∂V/∂t, per the same time unit as ``time_step``).
        rho: Portfolio rho (∂V/∂r).
        spot_move: Realised underlying move dS.
        vol_move: Realised volatility move dσ.
        time_step: Elapsed time dt.
        rate_move: Realised rate move dr.
        actual_pnl: Observed (hypothetical) P&L for the period.

    Returns:
        Dict with per-Greek ``components``, total ``predicted_pnl``,
        ``actual_pnl`` and ``unexplained``.
    """
    components = {
        "delta_pnl": delta * spot_move,
        "gamma_pnl": 0.5 * gamma * spot_move * spot_move,
        "vega_pnl": vega * vol_move,
        "theta_pnl": theta * time_step,
        "rho_pnl": rho * rate_move,
    }
    predicted = float(sum(components.values()))
    return {
        "components": {k: round(float(v), 8) for k, v in components.items()},
        "predicted_pnl": round(predicted, 8),
        "actual_pnl": round(float(actual_pnl), 8),
        "unexplained": round(float(actual_pnl) - predicted, 8),
    }


def pnl_attribution_test_frtb_pat(
    risk_theoretical_pnl: np.ndarray,
    hypothetical_pnl: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """FRTB P&L Attribution Test (PAT) — Spearman correlation and ratio test.

    Jointly evaluates the Spearman rank correlation between risk-theoretical P&L
    (RTPL) and hypothetical P&L (HPL) and the volatility ratio
    ``std(RTPL)/std(HPL)``, assigning the Basel traffic-light zone. These
    thresholds are set by the Basel Committee and are not parameterised.

    Args:
        risk_theoretical_pnl: Daily RTPL series (model-based).
        hypothetical_pnl: Daily HPL series (full-revaluation).

    Returns:
        Dict with ``spearman_corr``, ``ratio`` and ``zone``
        (``green``/``amber``/``red``).

    Raises:
        ValueError: If the two series differ in length or have < 2 points.
    """
    rtpl = np.asarray(risk_theoretical_pnl, dtype=np.float64)
    hpl = np.asarray(hypothetical_pnl, dtype=np.float64)
    if rtpl.size != hpl.size or rtpl.size < 2:
        raise ValueError("series must be equal length with at least 2 observations")

    corr = float(stats.spearmanr(rtpl, hpl).correlation)
    hpl_std = float(np.std(hpl))
    ratio = float(np.std(rtpl) / hpl_std) if hpl_std > 0.0 else float("inf")

    abs_corr = abs(corr)
    # BCBS FRTB §9.5 traffic-light thresholds (regulatory — do not parameterise).
    green = abs_corr >= 0.80 and 0.8 <= ratio <= 1.2
    amber = abs_corr >= 0.70 and 0.6 <= ratio <= 1.5
    if green:
        zone = "green"
    elif amber:
        zone = "amber"
    else:
        zone = "red"
    return {
        "spearman_corr": round(corr, 6),
        "ratio": round(ratio, 6),
        "zone": zone,
    }


def theta_carry_attribution(
    theta: float,
    time_step: float,
    funding_cost: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Theta / carry attribution.

    Isolates the deterministic time-decay (carry) component of P&L,
    ``theta · dt``, optionally net of a funding cost over the same period.

    Args:
        theta: Portfolio theta (∂V/∂t, per the same unit as ``time_step``).
        time_step: Elapsed time dt.
        funding_cost: Funding cost accrued over the period (currency).

    Returns:
        Dict with ``theta_pnl``, ``funding_cost`` and net ``carry_pnl``.
    """
    theta_pnl = theta * time_step
    return {
        "theta_pnl": round(float(theta_pnl), 8),
        "funding_cost": round(float(funding_cost), 8),
        "carry_pnl": round(float(theta_pnl) - float(funding_cost), 8),
    }

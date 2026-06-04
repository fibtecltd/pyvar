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
    "gamma_pnl_attribution",
    "vega_pnl_attribution",
    "fx_pnl_attribution",
    "rates_pnl_attribution",
    "credit_pnl_attribution",
    "residual_pnl_unexplained",
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


def gamma_pnl_attribution(gamma: float, spot_move: float) -> dict:  # type: ignore[type-arg]
    """Gamma (convexity) P&L component: ``½ · Γ · dS²``.

    Args:
        gamma: Portfolio gamma (∂²V/∂S²).
        spot_move: Realised underlying move dS.

    Returns:
        Dict with ``gamma_pnl``.
    """
    return {"gamma_pnl": round(0.5 * gamma * spot_move * spot_move, 8)}


def vega_pnl_attribution(vega: float, vol_move: float) -> dict:  # type: ignore[type-arg]
    """Vega P&L component: ``ν · dσ``.

    Args:
        vega: Portfolio vega (∂V/∂σ).
        vol_move: Realised volatility move dσ.

    Returns:
        Dict with ``vega_pnl``.
    """
    return {"vega_pnl": round(vega * vol_move, 8)}


def fx_pnl_attribution(
    fx_deltas: np.ndarray,
    fx_moves: np.ndarray,
    currency_names: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """FX P&L attribution across currency pairs.

    Total FX P&L = Σ fx_delta_i · dFX_i, additive across currencies.

    Args:
        fx_deltas: P&L per unit move of each FX rate.
        fx_moves: Realised move in each FX rate.
        currency_names: Optional labels; default ``ccy_0, ...``.

    Returns:
        Dict with ``total_fx_pnl`` and per-currency ``fx_pnl``.

    Raises:
        ValueError: If lengths mismatch.
    """
    d = np.asarray(fx_deltas, dtype=np.float64)
    m = np.asarray(fx_moves, dtype=np.float64)
    if d.size != m.size:
        raise ValueError("fx_deltas and fx_moves must have the same length")
    if currency_names is None:
        currency_names = [f"ccy_{i}" for i in range(d.size)]
    pnl = d * m
    return {
        "total_fx_pnl": round(float(np.sum(pnl)), 8),
        "fx_pnl": {currency_names[i]: round(float(pnl[i]), 8) for i in range(d.size)},
    }


def rates_pnl_attribution(
    key_rate_sensitivities: np.ndarray,
    yield_moves_bp: np.ndarray,
    tenor_names: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Interest-rate P&L attribution by key-rate tenor.

    Total rates P&L = Σ sensitivity_t · dyield_bp_t, where each sensitivity is
    P&L per +1bp move at that tenor. Additive across the key-rate ladder.

    Args:
        key_rate_sensitivities: P&L per +1bp move at each tenor.
        yield_moves_bp: Realised yield move (in basis points) at each tenor.
        tenor_names: Optional labels; default ``tenor_0, ...``.

    Returns:
        Dict with ``total_rates_pnl`` and per-tenor ``rates_pnl``.

    Raises:
        ValueError: If lengths mismatch.
    """
    s = np.asarray(key_rate_sensitivities, dtype=np.float64)
    m = np.asarray(yield_moves_bp, dtype=np.float64)
    if s.size != m.size:
        raise ValueError("sensitivities and yield_moves_bp must have the same length")
    if tenor_names is None:
        tenor_names = [f"tenor_{i}" for i in range(s.size)]
    pnl = s * m
    return {
        "total_rates_pnl": round(float(np.sum(pnl)), 8),
        "rates_pnl": {tenor_names[i]: round(float(pnl[i]), 8) for i in range(s.size)},
    }


def credit_pnl_attribution(
    cs01_sensitivities: np.ndarray,
    spread_moves_bp: np.ndarray,
    name_labels: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Credit P&L attribution by issuer / curve.

    Total credit P&L = Σ cs01_i · dspread_bp_i, additive across credit names.

    Args:
        cs01_sensitivities: P&L per +1bp credit-spread move per name.
        spread_moves_bp: Realised spread move (basis points) per name.
        name_labels: Optional labels; default ``name_0, ...``.

    Returns:
        Dict with ``total_credit_pnl`` and per-name ``credit_pnl``.

    Raises:
        ValueError: If lengths mismatch.
    """
    c = np.asarray(cs01_sensitivities, dtype=np.float64)
    m = np.asarray(spread_moves_bp, dtype=np.float64)
    if c.size != m.size:
        raise ValueError("cs01_sensitivities and spread_moves_bp must have the same length")
    if name_labels is None:
        name_labels = [f"name_{i}" for i in range(c.size)]
    pnl = c * m
    return {
        "total_credit_pnl": round(float(np.sum(pnl)), 8),
        "credit_pnl": {name_labels[i]: round(float(pnl[i]), 8) for i in range(c.size)},
    }


def residual_pnl_unexplained(
    actual_pnl: float,
    explained_components: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Unexplained (residual) P&L.

    Residual = actual P&L − Σ explained components. The residual plus the sum of
    explained components reconstructs the actual P&L exactly; a large residual
    relative to actual P&L flags model incompleteness (an FRTB PAT concern).

    Args:
        actual_pnl: Observed (hypothetical) P&L for the period.
        explained_components: The individual explained P&L components.

    Returns:
        Dict with ``explained_pnl``, ``residual_pnl`` and ``explained_ratio``
        (fraction of actual P&L explained; 0.0 when actual P&L is zero).
    """
    comp = np.asarray(explained_components, dtype=np.float64)
    explained = float(np.sum(comp))
    residual = float(actual_pnl) - explained
    ratio = explained / actual_pnl if actual_pnl != 0.0 else 0.0
    return {
        "explained_pnl": round(explained, 8),
        "residual_pnl": round(residual, 8),
        "explained_ratio": round(float(ratio), 8),
    }

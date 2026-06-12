"""engine/reg_frtb.py — FRTB regulatory capital aggregation (SA & IMA).

Implements the FRTB Capital regulatory sub-domain at the reporting/aggregation
level:
  * FRTB SA Market Risk Capital — sum of sensitivities, default risk charge and
    residual risk add-on across the three correlation scenarios.
  * FRTB IMA Market Risk Capital — ES-based charge with the regulatory multiplier
    plus non-modellable SES and the default risk charge.
  * FRTB P&L Attribution Test — Spearman correlation + variance ratio zones.
  * FRTB Trading Desk Aggregation — desk-level SA/IMA charge consolidation.

Regulatory constants (CLAUDE.md §4): IMA ES at 97.5%; PAT zones green
``|corr|>=0.80 AND ratio in [0.8,1.2]``, amber ``|corr|>=0.70 AND ratio in
[0.6,1.5]``, else red (IMA disqualification). These thresholds are set by the
Basel Committee and must not be parameterised. Aggregation-level functions are
pure typed NumPy/SciPy wrappers.

References: BCBS d457 "Minimum capital requirements for market risk" (Jan 2019).
"""

from __future__ import annotations

import numpy as np
from scipy import stats

__all__ = [
    "frtb_sa_market_risk_capital",
    "frtb_ima_market_risk_capital",
    "frtb_pl_attribution_test",
    "frtb_trading_desk_aggregation",
]

# ── FRTB regulatory constants (BCBS d457) ─────────────────────────────────────
IMA_ES_CONFIDENCE: float = 0.975  # 97.5% ES (§181)
IMA_MULTIPLIER_FLOOR: float = 1.5  # minimum mc multiplier (§189)
# PAT zone thresholds (§g, §183) — DO NOT parameterise.
PAT_GREEN_CORR: float = 0.80
PAT_GREEN_RATIO_LO: float = 0.8
PAT_GREEN_RATIO_HI: float = 1.2
PAT_AMBER_CORR: float = 0.70
PAT_AMBER_RATIO_LO: float = 0.6
PAT_AMBER_RATIO_HI: float = 1.5


def frtb_sa_market_risk_capital(
    sensitivities_charge: float,
    default_risk_charge: float,
    residual_risk_addon: float,
) -> dict:  # type: ignore[type-arg]
    """FRTB Standardised Approach total market-risk capital.

    The SA capital is the simple sum of the Sensitivities-Based Method charge
    (already aggregated across delta/vega/curvature and the three correlation
    scenarios), the Default Risk Charge (DRC) and the Residual Risk Add-On
    (RRAO) (BCBS d457 §2).

    Args:
        sensitivities_charge: Aggregate SBM charge (max over correlation
            scenarios), currency.
        default_risk_charge: Default Risk Charge, currency.
        residual_risk_addon: Residual Risk Add-On, currency.

    Returns:
        Dict with ``sa_capital`` and the three component charges.

    Raises:
        ValueError: If any component is negative.
    """
    if min(sensitivities_charge, default_risk_charge, residual_risk_addon) < 0.0:
        raise ValueError("SA capital components must be non-negative")
    total = sensitivities_charge + default_risk_charge + residual_risk_addon
    return {
        "sa_capital": round(total, 4),
        "sensitivities_charge": round(sensitivities_charge, 4),
        "default_risk_charge": round(default_risk_charge, 4),
        "residual_risk_addon": round(residual_risk_addon, 4),
    }


def frtb_ima_market_risk_capital(
    expected_shortfall: float,
    stressed_es_ratio: float,
    multiplier: float,
    non_modellable_ses: float = 0.0,
    default_risk_charge: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """FRTB Internal Models Approach total market-risk capital.

    The IMA charge combines the multiplier-scaled, stressed-scaled Expected
    Shortfall (the "IMCC" proxy) with the non-modellable risk factor capital
    (SES) and the Default Risk Charge (BCBS d457 §189). The multiplier is
    floored at 1.5.

    Args:
        expected_shortfall: Current-period 97.5% Expected Shortfall, currency.
        stressed_es_ratio: Ratio of stressed ES to current ES (>= 1 typically).
        multiplier: Supervisory multiplier mc (floored at 1.5).
        non_modellable_ses: Aggregate SES capital for NMRFs, currency.
        default_risk_charge: IMA Default Risk Charge, currency.

    Returns:
        Dict with ``ima_capital``, the scaled ``es_charge`` and the
        ``multiplier`` actually applied.

    Raises:
        ValueError: If ES is negative or the stressed ratio is non-positive.
    """
    if expected_shortfall < 0.0:
        raise ValueError("expected_shortfall must be non-negative")
    if stressed_es_ratio <= 0.0:
        raise ValueError("stressed_es_ratio must be positive")
    applied_mult = max(multiplier, IMA_MULTIPLIER_FLOOR)
    es_charge = applied_mult * expected_shortfall * stressed_es_ratio
    ima_capital = es_charge + non_modellable_ses + default_risk_charge
    return {
        "ima_capital": round(ima_capital, 4),
        "es_charge": round(es_charge, 4),
        "multiplier": round(applied_mult, 4),
        "es_confidence": IMA_ES_CONFIDENCE,
        "non_modellable_ses": round(non_modellable_ses, 4),
        "default_risk_charge": round(default_risk_charge, 4),
    }


def frtb_pl_attribution_test(
    risk_theoretical_pnl: np.ndarray,
    hypothetical_pnl: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """FRTB P&L Attribution Test (PAT) — Spearman correlation + variance ratio.

    Jointly evaluates the Spearman rank correlation between risk-theoretical P&L
    (RTPL) and hypothetical P&L (HPL) and the volatility ratio
    ``std(RTPL)/std(HPL)``, assigning the Basel traffic-light zone. The
    thresholds are mandated by BCBS d457 and CLAUDE.md §4.4:
    green ``|corr|>=0.80 AND 0.8<=ratio<=1.2``;
    amber ``|corr|>=0.70 AND 0.6<=ratio<=1.5``; otherwise red (IMA loss).

    Args:
        risk_theoretical_pnl: RTPL series from the risk model.
        hypothetical_pnl: HPL series from full revaluation.

    Returns:
        Dict with ``spearman_corr``, ``ratio``, ``zone`` and ``ima_eligible``.

    Raises:
        ValueError: If the series differ in length or are too short.
    """
    rtpl = np.asarray(risk_theoretical_pnl, dtype=np.float64)
    hpl = np.asarray(hypothetical_pnl, dtype=np.float64)
    if rtpl.size < 2 or rtpl.size != hpl.size:
        raise ValueError("RTPL and HPL must be equal length with >= 2 observations")

    corr = float(stats.spearmanr(rtpl, hpl).correlation)
    hpl_std = float(np.std(hpl))
    ratio = float(np.std(rtpl) / hpl_std) if hpl_std > 0.0 else float("inf")
    abs_corr = abs(corr)

    green = abs_corr >= PAT_GREEN_CORR and PAT_GREEN_RATIO_LO <= ratio <= PAT_GREEN_RATIO_HI
    amber = abs_corr >= PAT_AMBER_CORR and PAT_AMBER_RATIO_LO <= ratio <= PAT_AMBER_RATIO_HI
    if green:
        zone = "green"
    elif amber:
        zone = "amber"
    else:
        zone = "red"
    return {
        "spearman_corr": round(corr, 6),
        "ratio": round(ratio, 6) if np.isfinite(ratio) else float("inf"),
        "zone": zone,
        "ima_eligible": bool(zone != "red"),
    }


def frtb_trading_desk_aggregation(
    desk_sa_charges: np.ndarray,
    desk_ima_charges: np.ndarray,
    desk_ima_eligible: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """FRTB trading-desk capital aggregation.

    Aggregates per-desk capital: IMA-eligible desks contribute their IMA charge,
    non-eligible (PAT-red / backtest-failed) desks fall back to the SA charge.
    The total firm-wide market-risk capital is the sum across desks (BCBS d457
    treats the firm charge as the sum of approved-desk IMA plus SA for the rest).

    Args:
        desk_sa_charges: SA charge per desk (currency).
        desk_ima_charges: IMA charge per desk (currency).
        desk_ima_eligible: Boolean/0-1 array — whether each desk may use IMA.

    Returns:
        Dict with ``total_capital``, ``ima_capital`` (eligible desks),
        ``sa_capital`` (fallback desks), ``n_ima_desks`` and ``n_sa_desks``.

    Raises:
        ValueError: If the arrays differ in length or are empty.
    """
    sa = np.asarray(desk_sa_charges, dtype=np.float64)
    ima = np.asarray(desk_ima_charges, dtype=np.float64)
    eligible = np.asarray(desk_ima_eligible).astype(bool)
    n = sa.size
    if n == 0 or not (ima.size == eligible.size == n):
        raise ValueError("desk arrays must be non-empty and equal length")

    ima_total = float(np.sum(ima[eligible]))
    sa_total = float(np.sum(sa[~eligible]))
    return {
        "total_capital": round(ima_total + sa_total, 4),
        "ima_capital": round(ima_total, 4),
        "sa_capital": round(sa_total, 4),
        "n_ima_desks": int(np.sum(eligible)),
        "n_sa_desks": int(np.sum(~eligible)),
    }

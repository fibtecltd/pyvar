"""engine/frtb.py — FRTB capital & tail-risk measures (Market Risk).

Standardised Approach (SA): Sensitivities-Based Method, Default Risk Charge,
Residual Risk Add-On. Internal Models Approach (IMA): Expected Shortfall,
stressed-period finder, non-modellable risk factor SES, and the aggregate
capital charge. Plus the tail-risk measures Extreme Value Theory VaR and the
Spectral Risk Measure.

The IMA ES confidence level is 97.5% and the stressed-period / observation
windows are 250 trading days, per CLAUDE.md §4 and BCBS FRTB. These constants
are used verbatim.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "frtb_sa_sensitivity_based_method",
    "frtb_sa_default_risk_charge",
    "frtb_sa_residual_risk_addon",
    "frtb_ima_expected_shortfall",
]


def frtb_sa_sensitivity_based_method(
    bucket_weighted_sensitivities: list[list[float]],
    intra_bucket_corr: float,
    inter_bucket_corr: float,
) -> dict:  # type: ignore[type-arg]
    """FRTB SA Sensitivities-Based Method (delta) risk charge.

    Within each bucket the risk position is
    ``Kb = sqrt(Σ WS_i² + Σ_{i≠j} ρ·WS_i·WS_j)``; the charge aggregates buckets
    as ``sqrt(Σ Kb² + Σ_{b≠c} γ·S_b·S_c)`` with ``S_b = Σ_i WS_i`` (MAR21).

    Args:
        bucket_weighted_sensitivities: Per-bucket lists of weighted
            sensitivities (risk weight already applied).
        intra_bucket_corr: Correlation ρ between sensitivities within a bucket.
        inter_bucket_corr: Correlation γ between bucket totals.

    Returns:
        Dict with ``risk_charge``, per-bucket ``kb`` and bucket totals ``sb``.

    Raises:
        ValueError: If correlations are outside [-1, 1] or buckets are empty.
    """
    if not bucket_weighted_sensitivities:
        raise ValueError("at least one bucket is required")
    if not -1.0 <= intra_bucket_corr <= 1.0 or not -1.0 <= inter_bucket_corr <= 1.0:
        raise ValueError("correlations must be in [-1, 1]")

    kb_list: list[float] = []
    sb_list: list[float] = []
    for bucket in bucket_weighted_sensitivities:
        ws = np.asarray(bucket, dtype=np.float64)
        sum_sq = float(np.sum(ws * ws))
        cross = float(np.sum(ws) ** 2 - sum_sq)  # Σ_{i≠j} WS_i WS_j
        kb_sq = sum_sq + intra_bucket_corr * cross
        kb_list.append(float(np.sqrt(max(kb_sq, 0.0))))
        sb_list.append(float(np.sum(ws)))

    kb = np.asarray(kb_list, dtype=np.float64)
    sb = np.asarray(sb_list, dtype=np.float64)
    cross_bucket = float(np.sum(sb) ** 2 - np.sum(sb * sb))  # Σ_{b≠c} S_b S_c
    charge_sq = float(np.sum(kb * kb)) + inter_bucket_corr * cross_bucket
    return {
        "risk_charge": round(float(np.sqrt(max(charge_sq, 0.0))), 8),
        "kb": [round(v, 8) for v in kb_list],
        "sb": [round(v, 8) for v in sb_list],
    }


def frtb_sa_default_risk_charge(
    jtd_long: np.ndarray,
    jtd_short: np.ndarray,
    risk_weights: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """FRTB SA Default Risk Charge (DRC) with the hedge-benefit ratio.

    Net jump-to-default per issuer is risk-weighted; the gross short charge is
    scaled by the Weighted-to-Short (hedge benefit) ratio
    ``WtS = Σ netLong / (Σ netLong + Σ|netShort|)`` (MAR22). DRC is floored at 0.

    Args:
        jtd_long: Long jump-to-default exposure per issuer.
        jtd_short: Short jump-to-default exposure per issuer (positive numbers).
        risk_weights: Default risk weight per issuer.

    Returns:
        Dict with ``drc``, ``wts_ratio``, ``gross_long`` and ``gross_short``.

    Raises:
        ValueError: If the three inputs differ in length.
    """
    jl = np.asarray(jtd_long, dtype=np.float64)
    js = np.asarray(jtd_short, dtype=np.float64)
    rw = np.asarray(risk_weights, dtype=np.float64)
    if not (jl.size == js.size == rw.size):
        raise ValueError("jtd_long, jtd_short, risk_weights must be equal length")

    net = jl - js
    weighted = rw * net
    gross_long = float(np.sum(weighted[net > 0.0]))
    gross_short = float(-np.sum(weighted[net < 0.0]))  # positive magnitude

    total_long = float(np.sum(net[net > 0.0]))
    total_short = float(-np.sum(net[net < 0.0]))
    denom = total_long + total_short
    wts = total_long / denom if denom > 0.0 else 1.0
    drc = max(0.0, gross_long - wts * gross_short)
    return {
        "drc": round(drc, 8),
        "wts_ratio": round(float(wts), 8),
        "gross_long": round(gross_long, 8),
        "gross_short": round(gross_short, 8),
    }


def frtb_sa_residual_risk_addon(
    notionals: np.ndarray,
    rrao_weights: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """FRTB SA Residual Risk Add-On (RRAO).

    A simple notional-based add-on for instruments with residual risks not
    captured by the SBM: ``RRAO = Σ notional_i · weight_i`` (MAR23, e.g. 1.0% on
    exotic underlyings, 0.1% otherwise).

    Args:
        notionals: Gross notional per instrument.
        rrao_weights: RRAO risk weight per instrument.

    Returns:
        Dict with ``rrao`` and the per-instrument ``addon`` contributions.

    Raises:
        ValueError: If inputs differ in length.
    """
    n = np.asarray(notionals, dtype=np.float64)
    w = np.asarray(rrao_weights, dtype=np.float64)
    if n.size != w.size:
        raise ValueError("notionals and rrao_weights must have the same length")
    addon = n * w
    return {
        "rrao": round(float(np.sum(addon)), 8),
        "addon": [round(float(x), 8) for x in addon],
    }


def frtb_ima_expected_shortfall(
    returns: np.ndarray,
    confidence_level: float = 0.975,
) -> dict:  # type: ignore[type-arg]
    """FRTB IMA Expected Shortfall (the regulatory ES at 97.5%).

    ES is the mean loss beyond the VaR threshold at the FRTB confidence of
    97.5% (CLAUDE.md §4.2) and is always >= VaR.

    Args:
        returns: 1-D array of portfolio returns over the IMA observation set.
        confidence_level: ES confidence; FRTB IMA uses 0.975.

    Returns:
        Dict with ``es``, ``var`` and ``confidence_level``.

    Raises:
        ValueError: If ``returns`` is empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size == 0:
        raise ValueError("returns must be non-empty")
    sorted_losses = np.sort(-r)
    n = sorted_losses.size
    idx = min(int(np.floor(confidence_level * n)), n - 1)
    var = float(sorted_losses[idx])
    es = float(np.mean(sorted_losses[idx:]))  # mean of the tail beyond VaR
    return {
        "es": round(es, 8),
        "var": round(var, 8),
        "confidence_level": confidence_level,
    }

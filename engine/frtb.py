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
from scipy import stats

__all__ = [
    "frtb_sa_sensitivity_based_method",
    "frtb_sa_default_risk_charge",
    "frtb_sa_residual_risk_addon",
    "frtb_ima_expected_shortfall",
    "frtb_ima_stressed_period_finder",
    "frtb_ima_non_modellable_risk_factors",
    "frtb_ima_aggregate_capital_charge",
    "extreme_value_theory_var",
    "spectral_risk_measure",
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

    Both the per-bucket ``Kb²`` term and the aggregate sum under the final
    square root are floored at 0 before the square root is taken, guarding
    against a negative value under extreme correlation inputs — a safeguard
    not shown in the MAR21 formula above.

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


def frtb_ima_stressed_period_finder(
    returns: np.ndarray,
    window: int = 250,
    confidence_level: float = 0.975,
) -> dict:  # type: ignore[type-arg]
    """Locate the FRTB IMA stressed period — the worst 250-day ES window.

    FRTB calibrates the stressed ES to the historical window of greatest stress.
    This slides a 250-day window and returns the start index whose Expected
    Shortfall is largest.

    Args:
        returns: Full return history.
        window: Stress window length (FRTB standard 250 trading days).
        confidence_level: ES confidence used to rank windows (0.975).

    Returns:
        Dict with ``stressed_window_start``, ``stressed_es`` and ``n_windows``.

    Raises:
        ValueError: If the history is shorter than one window.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size < window:
        raise ValueError("returns shorter than one window")

    best_start = 0
    best_es = -np.inf
    n_windows = r.size - window + 1
    for start in range(n_windows):
        losses = np.sort(-r[start : start + window])
        idx = min(int(np.floor(confidence_level * window)), window - 1)
        es = float(np.mean(losses[idx:]))
        if es > best_es:
            best_es = es
            best_start = start
    return {
        "stressed_window_start": int(best_start),
        "stressed_es": round(float(best_es), 8),
        "n_windows": int(n_windows),
    }


def frtb_ima_non_modellable_risk_factors(
    individual_ses: np.ndarray,
    rho: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """FRTB IMA non-modellable risk factor (NMRF) capital — aggregate SES.

    Aggregates per-factor stressed capital add-ons (ISES) as
    ``SES = sqrt( (ρ·Σ ISES)² + (1−ρ²)·Σ ISES² )`` (MAR33.16). With ρ = 0 this is
    the Euclidean sum; with ρ = 1 it is the linear (fully correlated) sum.

    Args:
        individual_ses: Per-factor stressed capital add-ons (ISES).
        rho: Prescribed correlation across NMRFs in [0, 1].

    Returns:
        Dict with the aggregate ``ses`` and ``n_factors``.

    Raises:
        ValueError: If ``rho`` is outside [0, 1] or ``individual_ses`` is empty.
    """
    ises = np.asarray(individual_ses, dtype=np.float64)
    if ises.size == 0:
        raise ValueError("individual_ses must be non-empty")
    if not 0.0 <= rho <= 1.0:
        raise ValueError("rho must be in [0, 1]")

    linear = float(np.sum(ises))
    sum_sq = float(np.sum(ises * ises))
    ses = float(np.sqrt((rho * linear) ** 2 + (1.0 - rho * rho) * sum_sq))
    return {"ses": round(ses, 8), "n_factors": int(ises.size)}


def frtb_ima_aggregate_capital_charge(
    imcc: float,
    ses: float,
    default_risk_charge: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """FRTB IMA aggregate capital charge.

    Combines the internally-modelled capital charge (IMCC, from ES), the
    non-modellable SES add-on, and the default risk charge (MAR33.43):
    ``ACC = IMCC + SES + DRC``.

    Args:
        imcc: Internally-modelled capital charge (ES-based).
        ses: Aggregate non-modellable risk factor capital (SES).
        default_risk_charge: Default risk charge (DRC).

    Returns:
        Dict with ``aggregate_capital_charge`` and the components.

    Raises:
        ValueError: If any component is negative.
    """
    if imcc < 0 or ses < 0 or default_risk_charge < 0:
        raise ValueError("capital components must be non-negative")
    total = float(imcc) + float(ses) + float(default_risk_charge)
    return {
        "aggregate_capital_charge": round(total, 8),
        "imcc": round(float(imcc), 8),
        "ses": round(float(ses), 8),
        "drc": round(float(default_risk_charge), 8),
    }


def extreme_value_theory_var(
    returns: np.ndarray,
    threshold_quantile: float = 0.95,
    confidence_level: float = 0.99,
) -> dict:  # type: ignore[type-arg]
    """Extreme Value Theory VaR via Peaks-Over-Threshold (Generalised Pareto).

    Fits a Generalised Pareto Distribution to losses exceeding a high threshold
    u and reads the tail quantile::

        VaR_p = u + (β/ξ) · [ ((n/N_u)(1−p))^{−ξ} − 1 ]

    capturing tail behaviour beyond the empirical sample range.

    Args:
        returns: 1-D array of portfolio returns.
        threshold_quantile: Loss quantile defining the POT threshold (e.g. 0.95).
        confidence_level: VaR confidence in [0.90, 0.9999], above the threshold.

    Returns:
        Dict with ``evt_var``, the GPD shape ``xi`` and scale ``beta``, the
        ``threshold`` and the exceedance count ``n_exceedances``.

    Raises:
        ValueError: If there are too few exceedances or the quantile ordering
            is invalid.
    """
    r = np.asarray(returns, dtype=np.float64)
    if not 0.0 < threshold_quantile < confidence_level < 1.0:
        raise ValueError("require 0 < threshold_quantile < confidence_level < 1")

    losses = -r
    n = losses.size
    u = float(np.quantile(losses, threshold_quantile))
    exceedances = losses[losses > u] - u
    n_u = exceedances.size
    if n_u < 10:
        raise ValueError("too few exceedances for a stable GPD fit (need >= 10)")

    xi, _, beta = stats.genpareto.fit(exceedances, floc=0.0)
    ratio = (n / n_u) * (1.0 - confidence_level)
    if abs(xi) < 1e-8:
        evt_var = u - beta * np.log(ratio)
    else:
        evt_var = u + (beta / xi) * (ratio ** (-xi) - 1.0)
    return {
        "evt_var": round(float(evt_var), 8),
        "xi": round(float(xi), 8),
        "beta": round(float(beta), 8),
        "threshold": round(u, 8),
        "n_exceedances": int(n_u),
    }


def spectral_risk_measure(
    returns: np.ndarray,
    risk_aversion: float = 25.0,
) -> dict:  # type: ignore[type-arg]
    """Spectral risk measure with an exponential risk-aversion spectrum.

    A coherent risk measure that integrates the loss quantile against a
    decreasing risk-spectrum ``φ(p) = k·e^{−k(1−p)} / (1−e^{−k})``, placing more
    weight on the tail as the risk aversion k rises. SRM >= the mean loss and is
    increasing in k.

    Args:
        returns: 1-D array of portfolio returns.
        risk_aversion: Risk-aversion coefficient k > 0 (higher = more tail-weighted).

    Returns:
        Dict with ``spectral_risk``, the ``risk_aversion`` used and the
        ``mean_loss`` (the k→0 limit) for reference.

    Raises:
        ValueError: If ``returns`` is empty or ``risk_aversion`` <= 0.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size == 0:
        raise ValueError("returns must be non-empty")
    if risk_aversion <= 0.0:
        raise ValueError("risk_aversion must be positive")

    sorted_losses = np.sort(-r)  # ascending
    n = sorted_losses.size
    p = (np.arange(n) + 0.5) / n  # midpoint quantile levels
    k = risk_aversion
    phi = k * np.exp(-k * (1.0 - p)) / (1.0 - np.exp(-k))
    weights = phi / np.sum(phi)  # normalise to a discrete probability spectrum
    srm = float(np.sum(weights * sorted_losses))
    return {
        "spectral_risk": round(srm, 8),
        "risk_aversion": round(float(k), 6),
        "mean_loss": round(float(np.mean(sorted_losses)), 8),
    }

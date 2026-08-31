"""engine/reg_solvency.py — Fund regulations: AIFMD, UCITS, Solvency II.

Implements the Fund Regulations regulatory sub-domain:
  * AIFMD risk metrics (leverage under the gross & commitment methods, VaR).
  * UCITS KIID Synthetic Risk and Reward Indicator (SRRI, 1-7).
  * Solvency II SCR Market risk (modular aggregation with the correlation
    matrix and the square-root formula).
  * Solvency II SCR Credit (counterparty default) risk.

Numba rules (CLAUDE.md §3.1): the SCR correlation aggregation
``sqrt(s' C s)`` is a small matrix form done in NumPy in the pure-Python
wrapper; the per-bucket loop where present is a JIT kernel returning a NumPy
array. No randomness involved.

References: AIFMD (Directive 2011/61/EU) Annex IV; Commission Delegated
Regulation (EU) 231/2013 Art. 7-8; UCITS KIID Regulation (EU) 583/2010 / CESR
10-673; Solvency II Delegated Regulation (EU) 2015/35 Art. 164-202.
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "aifmd_risk_metrics",
    "ucits_kiid_risk_indicator",
    "solvency_ii_scr_market_risk",
    "solvency_ii_scr_credit_risk",
]

# UCITS SRRI volatility bucket upper bounds (annualised), CESR 10-673 Box 1.
_SRRI_BANDS: tuple[float, ...] = (0.005, 0.02, 0.05, 0.10, 0.15, 0.25)


@njit(cache=True)
def _scr_aggregate(sub_modules: np.ndarray, corr: np.ndarray) -> float:
    """Square-root SCR aggregation ``sqrt(s' C s)`` (Solvency II standard formula)."""
    n = sub_modules.shape[0]
    acc = 0.0
    for i in range(n):
        for j in range(n):
            acc += sub_modules[i] * corr[i, j] * sub_modules[j]
    return float(np.sqrt(acc)) if acc > 0.0 else 0.0


def aifmd_risk_metrics(
    gross_exposure: float,
    commitment_exposure: float,
    net_asset_value: float,
    var_pct: float | None = None,
) -> dict:  # type: ignore[type-arg]
    """AIFMD Annex IV risk metrics — leverage and (optional) VaR.

    "Substantially leveraged" here is a simple threshold flag (commitment
    leverage > 3x NAV), not AIFMD's full leverage-calculation methodology.

    Computes leverage under the gross method and the commitment method (each as
    a multiple of NAV) per Delegated Regulation 231/2013 Art. 7-8. A fund is
    "substantially leveraged" when commitment leverage exceeds 3x NAV.

    Args:
        gross_exposure: Gross method exposure (sum of absolute positions).
        commitment_exposure: Commitment method exposure (post-netting/hedging).
        net_asset_value: Fund NAV.
        var_pct: Optional fund VaR as a fraction of NAV for reporting.

    Returns:
        Dict with ``gross_leverage``, ``commitment_leverage``,
        ``substantially_leveraged`` and (if supplied) ``var_pct``.

    Raises:
        ValueError: If NAV is non-positive.
    """
    if net_asset_value <= 0.0:
        raise ValueError("net_asset_value must be positive")
    gross_lev = gross_exposure / net_asset_value
    commitment_lev = commitment_exposure / net_asset_value
    result = {
        "gross_leverage": round(gross_lev, 6),
        "commitment_leverage": round(commitment_lev, 6),
        "substantially_leveraged": bool(commitment_lev > 3.0),
    }
    if var_pct is not None:
        result["var_pct"] = round(float(var_pct), 8)
    return result


def ucits_kiid_risk_indicator(
    returns: np.ndarray,
    periods_per_year: int = 52,
) -> dict:  # type: ignore[type-arg]
    """UCITS KIID Synthetic Risk and Reward Indicator (SRRI), 1-7.

    Maps the annualised volatility of (weekly by default) returns to the SRRI
    bucket per CESR 10-673: class 1 (< 0.5%) up to class 7 (>= 25%).

    Args:
        returns: 1-D array of periodic fund returns.
        periods_per_year: Periods per year for annualising volatility (52 for
            weekly, 12 monthly).

    Returns:
        Dict with ``srri`` (int 1-7) and the ``annualised_volatility`` used.

    Raises:
        ValueError: If fewer than 2 observations are supplied.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size < 2:
        raise ValueError("SRRI requires at least 2 observations")
    ann_vol = float(np.std(r, ddof=1) * np.sqrt(periods_per_year))
    srri = 7
    for k, upper in enumerate(_SRRI_BANDS, start=1):
        if ann_vol < upper:
            srri = k
            break
    return {
        "srri": int(srri),
        "annualised_volatility": round(ann_vol, 8),
    }


def solvency_ii_scr_market_risk(
    sub_module_charges: np.ndarray,
    correlation_matrix: np.ndarray,
    sub_module_names: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Solvency II SCR Market risk — standard-formula modular aggregation.

    Aggregates the market sub-module capital charges (interest rate, equity,
    property, spread, currency, concentration) using the prescribed correlation
    matrix and the square-root formula ``SCR = sqrt(s' Corr s)`` (Delegated
    Regulation 2015/35 Art. 164).

    Args:
        sub_module_charges: Capital charge per market sub-module.
        correlation_matrix: Prescribed correlation matrix between sub-modules.
        sub_module_names: Optional labels for the diversification report.

    Returns:
        Dict with ``scr_market``, the ``sum_of_charges`` (undiversified) and the
        ``diversification_benefit``.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    s = np.asarray(sub_module_charges, dtype=np.float64)
    corr = np.asarray(correlation_matrix, dtype=np.float64)
    n = s.size
    if corr.shape != (n, n):
        raise ValueError("correlation_matrix must be (n, n) matching sub_module_charges")
    if sub_module_names is not None and len(sub_module_names) != n:
        raise ValueError("sub_module_names length must match charges")

    scr = _scr_aggregate(np.ascontiguousarray(s), np.ascontiguousarray(corr))
    undiversified = float(np.sum(s))
    return {
        "scr_market": round(float(scr), 4),
        "sum_of_charges": round(undiversified, 4),
        "diversification_benefit": round(undiversified - float(scr), 4),
    }


def solvency_ii_scr_credit_risk(
    exposures: np.ndarray,
    loss_given_default: np.ndarray,
    default_probabilities: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Solvency II SCR counterparty default (credit) risk — Type 1 exposures.

    The sigma used here is the intra-counterparty (independent-Bernoulli)
    variance term only; Delegated Regulation (EU) 2015/35 Art. 201's
    inter-counterparty correlation term is not implemented, so the true
    Art. 201 variance (and SCR) is at least as large as what this function
    returns.

    [REGULATORY] Delegated Regulation (EU) 2015/35 Art. 200(1)-(3) fixes the
    capital charge as a TIERED multiplier on the standard deviation (sigma) of
    the loss distribution, not a flat 3x: SCR = 3*sigma while
    sigma <= 7% of total LGD; SCR = 5*sigma while 7% < sigma/TLGD <= 20%; SCR =
    total LGD (fully capped) once sigma/TLGD exceeds 20%. An earlier version of
    this function exposed a caller-configurable ``risk_factor`` defaulting to a
    flat 3.0 — that understated capital by ~79% on a representative 2-exposure
    case (807 vs. the correct ~1449, entirely from missing the 5x/TLGD tiers).
    The multiplier is fixed by the Delegated Regulation, so it is intentionally
    not a parameter here (same reasoning as CLAUDE.md §4.3/§4.4's Basel
    thresholds: never parameterise regulator-set constants).

    [LIMITATION] The variance (sigma^2) computed here is the intra-counterparty
    term only — an independent-Bernoulli approximation summing each
    counterparty's own default-loss variance. Art. 201's full formula also adds
    an inter-counterparty correlation term (V_inter) between exposures carrying
    different default probabilities, which this implementation does NOT
    compute — that term is generally positive, so the true Art. 201 variance
    (and therefore the true SCR) is at least as large as what this function
    returns. Do not rely on this for statutory Solvency II reporting without an
    actuarial review of that gap.

    Args:
        exposures: Exposure at default per counterparty.
        loss_given_default: LGD fraction per counterparty.
        default_probabilities: PD per counterparty in [0, 1].

    Returns:
        Dict with ``scr_credit``, ``expected_loss`` and ``total_lgd``.

    Raises:
        ValueError: If arrays differ in length / are empty, or PDs out of range.
    """
    ead = np.asarray(exposures, dtype=np.float64)
    lgd_rate = np.asarray(loss_given_default, dtype=np.float64)
    pd = np.asarray(default_probabilities, dtype=np.float64)
    n = ead.size
    if n == 0 or not (lgd_rate.size == pd.size == n):
        raise ValueError("exposure/LGD/PD arrays must be non-empty and equal length")
    if np.any(pd < 0.0) or np.any(pd > 1.0):
        raise ValueError("default_probabilities must be in [0, 1]")

    lgd = ead * lgd_rate
    total_lgd = float(np.sum(lgd))
    expected_loss = float(np.sum(pd * lgd))
    # Variance of loss assuming independent Bernoulli defaults (intra-
    # counterparty term only -- see [LIMITATION] above).
    variance = float(np.sum((lgd**2) * pd * (1.0 - pd)))
    sigma = float(np.sqrt(variance)) if variance > 0.0 else 0.0

    # Art. 200(1)-(3) tiered multiplier -- see [REGULATORY] above.
    if total_lgd <= 0.0:
        scr = 0.0
    else:
        ratio = sigma / total_lgd
        if ratio <= 0.07:
            scr = 3.0 * sigma
        elif ratio <= 0.20:
            scr = 5.0 * sigma
        else:
            scr = total_lgd
    # Capital cannot exceed total exposure at loss.
    scr = min(scr, total_lgd)
    return {
        "scr_credit": round(float(scr), 4),
        "expected_loss": round(expected_loss, 4),
        "total_lgd": round(total_lgd, 4),
    }

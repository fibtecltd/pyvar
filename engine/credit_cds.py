"""engine/credit_cds.py — Credit-default-swap and credit-spread sub-domain.

Implements: bootstrapping a hazard-rate / survival curve from CDS par spreads,
ISDA-standard CDS present-value pricing, the credit-triangle CDS-spread-to-PD
conversion, and a parametric CDS-position VaR.

Numba rules (CLAUDE.md §3.1): the CDS leg-valuation summation kernel is
JIT-compiled, stateless, takes only float64 arrays and returns NumPy arrays;
SciPy / RNG live in the public layer (RULE 3, RULE 5).
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy import stats

__all__ = [
    "credit_spread_curve_bootstrap",
    "cds_pricing_isda_standard",
    "cds_spread_to_pd_conversion",
    "credit_default_swap_var",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _cds_legs(
    accrual: np.ndarray,
    discount: np.ndarray,
    survival: np.ndarray,
    lgd: float,
) -> np.ndarray:
    """Premium-leg risky annuity and protection-leg PV (per unit spread/notional).

    ``survival`` is ``S(t_0..t_n)`` with S(t_0)=1. Returns ``[risky_annuity,
    protection_pv]`` (RULE 5). Premium leg uses end-of-period survival;
    protection leg pays LGD on the marginal default probability per bucket.
    """
    n = accrual.shape[0]
    annuity = 0.0
    protection = 0.0
    for k in range(n):
        annuity += accrual[k] * discount[k] * survival[k + 1]
        dpd = survival[k] - survival[k + 1]
        protection += lgd * discount[k] * dpd
    out = np.empty(2, dtype=np.float64)
    out[0] = annuity
    out[1] = protection
    return out


# ── Public functions ─────────────────────────────────────────────────────────


def credit_spread_curve_bootstrap(
    tenors: np.ndarray,
    par_spreads: np.ndarray,
    recovery_rate: float = 0.4,
) -> dict:  # type: ignore[type-arg]
    """Bootstrap a piecewise-constant hazard / survival curve from CDS spreads.

    Uses the credit-triangle approximation hazard ``lambda(t) = spread(t) / LGD``
    on each tenor, giving survival ``S(t) = exp(-lambda * t)`` with a piecewise
    hazard between consecutive tenors. This is the standard quick bootstrap;
    the full ISDA bootstrap solves leg-PV = 0 per tenor (handled by
    :func:`cds_pricing_isda_standard` when validating).

    Args:
        tenors: Strictly increasing CDS tenors in years (> 0).
        par_spreads: Par CDS spreads per tenor (decimal, >= 0).
        recovery_rate: Recovery rate in ``[0, 1)``.

    Returns:
        Dict with ``hazard_rates`` (piecewise per tenor), ``survival`` at each
        tenor and the cumulative ``default_prob`` (= 1 - survival).

    Raises:
        ValueError: If inputs mismatch, tenors not increasing, or recovery
            invalid.
    """
    t = np.asarray(tenors, dtype=np.float64).ravel()
    s = np.asarray(par_spreads, dtype=np.float64).ravel()
    if t.shape != s.shape or t.size == 0:
        raise ValueError("tenors and par_spreads must match and be non-empty")
    if np.any(t <= 0.0) or np.any(np.diff(t) <= 0.0):
        raise ValueError("tenors must be strictly increasing and positive")
    if not 0.0 <= recovery_rate < 1.0:
        raise ValueError("recovery_rate must be in [0, 1)")
    if np.any(s < 0.0):
        raise ValueError("par_spreads must be non-negative")

    lgd = 1.0 - recovery_rate
    cumulative_hazard_t = s / lgd * t  # lambda(t)*t with lambda = spread/LGD
    survival = np.exp(-cumulative_hazard_t)
    # Piecewise (forward) hazard between consecutive tenors.
    prev_t: np.ndarray = np.concatenate((np.array([0.0], dtype=np.float64), t[:-1]))
    prev_ch: np.ndarray = np.concatenate(
        (np.array([0.0], dtype=np.float64), cumulative_hazard_t[:-1])
    )
    dt = t - prev_t
    fwd_hazard = np.where(dt > 0.0, (cumulative_hazard_t - prev_ch) / dt, 0.0)
    return {
        "hazard_rates": [round(float(h), 10) for h in fwd_hazard],
        "survival": [round(float(v), 10) for v in survival],
        "default_prob": [round(float(1.0 - v), 10) for v in survival],
        "lgd": round(lgd, 8),
    }


def cds_pricing_isda_standard(
    payment_times: np.ndarray,
    accrual_factors: np.ndarray,
    discount_factors: np.ndarray,
    hazard_rate: float,
    contract_spread: float,
    notional: float = 1.0,
    recovery_rate: float = 0.4,
) -> dict:  # type: ignore[type-arg]
    """ISDA-standard CDS present value (protection-buyer perspective).

    PV(buyer) = protection leg - premium leg, where:
      * premium leg = spread * notional * risky annuity
        (``sum_k accrual_k DF_k S_k``),
      * protection leg = LGD * notional * ``sum_k DF_k (S_{k-1} - S_k)``.
    The par spread that zeroes the PV is also returned.

    Args:
        payment_times: ``(n,)`` strictly increasing premium-payment times.
        accrual_factors: ``(n,)`` day-count accrual fractions per period (>= 0).
        discount_factors: ``(n,)`` risk-free discount factors in ``(0, 1]``.
        hazard_rate: Flat hazard rate lambda (>= 0).
        contract_spread: Contractual (running) CDS spread (decimal).
        notional: Contract notional.
        recovery_rate: Recovery rate in ``[0, 1)``.

    Returns:
        Dict with ``pv`` (to the protection buyer), ``premium_leg``,
        ``protection_leg``, ``risky_annuity`` and ``par_spread``.

    Raises:
        ValueError: If inputs mismatch or parameters are invalid.
    """
    t = np.asarray(payment_times, dtype=np.float64).ravel()
    acc = np.asarray(accrual_factors, dtype=np.float64).ravel()
    df = np.asarray(discount_factors, dtype=np.float64).ravel()
    if not (t.shape == acc.shape == df.shape) or t.size == 0:
        raise ValueError("payment_times, accrual_factors, discount_factors must match")
    if np.any(t <= 0.0) or np.any(np.diff(t) <= 0.0):
        raise ValueError("payment_times must be strictly increasing and positive")
    if np.any((df <= 0.0) | (df > 1.0)):
        raise ValueError("discount_factors must lie in (0, 1]")
    if hazard_rate < 0.0:
        raise ValueError("hazard_rate must be non-negative")
    if not 0.0 <= recovery_rate < 1.0:
        raise ValueError("recovery_rate must be in [0, 1)")

    lgd = 1.0 - recovery_rate
    survival = np.empty(t.size + 1, dtype=np.float64)
    survival[0] = 1.0
    survival[1:] = np.exp(-hazard_rate * t)
    legs = _cds_legs(acc, df, survival, lgd)
    risky_annuity = float(legs[0])
    protection_leg = float(legs[1]) * notional
    premium_leg = contract_spread * notional * risky_annuity
    pv_buyer = protection_leg - premium_leg
    par_spread = (float(legs[1]) / risky_annuity) if risky_annuity > 0.0 else 0.0
    return {
        "pv": round(pv_buyer, 8),
        "premium_leg": round(premium_leg, 8),
        "protection_leg": round(protection_leg, 8),
        "risky_annuity": round(risky_annuity, 10),
        "par_spread": round(par_spread, 10),
    }


def cds_spread_to_pd_conversion(
    cds_spread: float,
    maturity: float,
    recovery_rate: float = 0.4,
) -> dict:  # type: ignore[type-arg]
    """Credit-triangle conversion of a CDS spread to PD.

    Hazard ``lambda = spread / (1 - R)``; cumulative default probability to
    maturity is ``PD = 1 - exp(-lambda * T)``. The annualised marginal default
    rate is also returned.

    Args:
        cds_spread: CDS par spread (decimal, e.g. 0.015 = 150 bps, >= 0).
        maturity: Horizon T in years (> 0).
        recovery_rate: Recovery rate in ``[0, 1)``.

    Returns:
        Dict with ``hazard_rate``, cumulative ``pd`` to maturity and the
        ``annual_pd`` (1-year marginal).

    Raises:
        ValueError: If spread/maturity/recovery are invalid.
    """
    if cds_spread < 0.0:
        raise ValueError("cds_spread must be non-negative")
    if maturity <= 0.0:
        raise ValueError("maturity must be positive")
    if not 0.0 <= recovery_rate < 1.0:
        raise ValueError("recovery_rate must be in [0, 1)")

    lgd = 1.0 - recovery_rate
    hazard = cds_spread / lgd
    pd = 1.0 - np.exp(-hazard * maturity)
    annual_pd = 1.0 - np.exp(-hazard)
    return {
        "hazard_rate": round(float(hazard), 10),
        "pd": round(float(pd), 12),
        "annual_pd": round(float(annual_pd), 12),
        "maturity": maturity,
    }


def credit_default_swap_var(
    notional: float,
    risky_annuity: float,
    spread_volatility: float,
    confidence_level: float = 0.99,
    horizon_days: int = 1,
    position: str = "long_protection",
) -> dict:  # type: ignore[type-arg]
    """Parametric VaR of a single-name CDS position from spread risk.

    The first-order MtM sensitivity to the credit spread is the spread DV01
    ``= notional * risky_annuity`` (per unit spread). With a normal daily spread
    move of volatility ``sigma_s``, the VaR is
    ``z * sigma_s * sqrt(horizon) * spread_DV01``.

    Args:
        notional: CDS notional.
        risky_annuity: Risky annuity (RPV01) of the contract (>= 0).
        spread_volatility: Daily absolute spread volatility (decimal, e.g.
            0.0005 = 5 bps/day).
        confidence_level: VaR confidence in ``[0.90, 0.9999]``.
        horizon_days: Risk horizon in trading days (sqrt-time scaling).
        position: ``"long_protection"`` or ``"short_protection"`` (affects only
            the sign of ``pnl_sensitivity``; VaR magnitude is identical).

    Returns:
        Dict with ``var`` (positive loss), ``spread_dv01`` and ``z_score``.

    Raises:
        ValueError: If inputs are invalid or position unknown.
    """
    if notional < 0.0 or risky_annuity < 0.0:
        raise ValueError("notional and risky_annuity must be non-negative")
    if spread_volatility < 0.0:
        raise ValueError("spread_volatility must be non-negative")
    if not 0.90 <= confidence_level <= 0.9999:
        raise ValueError("confidence_level must be in [0.90, 0.9999]")
    if position not in ("long_protection", "short_protection"):
        raise ValueError("position must be long_protection or short_protection")

    spread_dv01 = notional * risky_annuity
    z = float(stats.norm.ppf(confidence_level))
    var = z * spread_volatility * np.sqrt(horizon_days) * spread_dv01
    sign = 1.0 if position == "long_protection" else -1.0
    return {
        "var": round(float(var), 6),
        "spread_dv01": round(float(spread_dv01), 8),
        "z_score": round(z, 6),
        "pnl_sensitivity": round(sign * float(spread_dv01), 8),
        "confidence_level": confidence_level,
    }

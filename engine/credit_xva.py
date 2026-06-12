"""engine/credit_xva.py — Valuation-adjustment (XVA) sub-domain.

Implements the XVA family: Credit (CVA), Debit (DVA), Funding (FVA), Capital
(KVA) and Margin (MVA) valuation adjustments, the total XVA aggregation, CVA
sensitivities (CVA Greeks) and the wrong-way-risk adjustment.

All adjustments use a discretised expected-exposure profile and a hazard-rate
default model:
  * Marginal default probability over ``[t_{k-1}, t_k]`` is
    ``S(t_{k-1}) - S(t_k)`` with survival ``S(t) = exp(-lambda t)`` and hazard
    ``lambda = spread / (1 - R)``.

Numba rules (CLAUDE.md §3.1): the discrete CVA summation kernel is JIT-compiled,
stateless and returns NumPy arrays; public wrappers convert to Python types.
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "credit_valuation_adjustment_cva",
    "debt_valuation_adjustment_dva",
    "funding_valuation_adjustment_fva",
    "capital_valuation_adjustment_kva",
    "margin_valuation_adjustment_mva",
    "xva_aggregation",
    "cva_sensitivity_cva_greeks",
    "wrong_way_risk_adjustment",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _discrete_cva(
    epe: np.ndarray,
    discount: np.ndarray,
    survival: np.ndarray,
    lgd: float,
) -> float:
    """Discrete unilateral CVA = LGD * sum_k EPE_k * DF_k * dPD_k.

    ``survival`` holds S(t_0..t_n) with S(t_0)=1; the marginal default
    probability in each bucket is S(t_{k-1}) - S(t_k).
    """
    n = epe.shape[0]
    total = 0.0
    for k in range(n):
        dpd = survival[k] - survival[k + 1]
        total += epe[k] * discount[k] * dpd
    return lgd * total


# ── Helpers ──────────────────────────────────────────────────────────────────


def _survival_curve(time_steps: np.ndarray, hazard: float) -> np.ndarray:
    """Survival probabilities at grid boundaries from a flat hazard rate.

    Returns an ``(n+1,)`` array ``S(0), S(t_1), ..., S(t_n)`` with ``S(0)=1``.
    """
    s = np.empty(time_steps.size + 1, dtype=np.float64)
    s[0] = 1.0
    s[1:] = np.exp(-hazard * time_steps)
    return s


def _validate_profile(epe: np.ndarray, t: np.ndarray, discount: np.ndarray) -> None:
    """Shared validation for XVA exposure-profile inputs."""
    if not (epe.shape == t.shape == discount.shape) or epe.size == 0:
        raise ValueError("epe, time_steps, discount_factors must share a non-empty shape")
    if np.any(np.diff(t) <= 0.0) or np.any(t <= 0.0):
        raise ValueError("time_steps must be strictly increasing and positive")
    if np.any((discount <= 0.0) | (discount > 1.0)):
        raise ValueError("discount_factors must lie in (0, 1]")


# ── Public functions ─────────────────────────────────────────────────────────


def credit_valuation_adjustment_cva(
    expected_exposure: np.ndarray,
    time_steps: np.ndarray,
    discount_factors: np.ndarray,
    credit_spread: float,
    recovery_rate: float = 0.4,
) -> dict:  # type: ignore[type-arg]
    """Unilateral Credit Valuation Adjustment.

    The market price of counterparty default risk:
    ``CVA = LGD * sum_k EPE_k * DF_k * (S_{k-1} - S_k)`` with LGD = 1 - R and a
    flat hazard ``lambda = spread / LGD`` (credit-triangle approximation).

    Args:
        expected_exposure: ``(n,)`` discounted-or-not EPE per bucket (>= 0).
        time_steps: ``(n,)`` strictly increasing bucket end-times (years).
        discount_factors: ``(n,)`` risk-free discount factors in ``(0, 1]``.
        credit_spread: Counterparty CDS spread (decimal, e.g. 0.01 = 100 bps).
        recovery_rate: Counterparty recovery rate in ``[0, 1)``.

    Returns:
        Dict with ``cva``, ``lgd``, ``hazard_rate`` and ``n_buckets``.

    Raises:
        ValueError: If profiles mismatch or recovery / spread are invalid.
    """
    epe = np.asarray(expected_exposure, dtype=np.float64).ravel()
    t = np.asarray(time_steps, dtype=np.float64).ravel()
    df = np.asarray(discount_factors, dtype=np.float64).ravel()
    _validate_profile(epe, t, df)
    if not 0.0 <= recovery_rate < 1.0:
        raise ValueError("recovery_rate must be in [0, 1)")
    if credit_spread < 0.0:
        raise ValueError("credit_spread must be non-negative")
    if np.any(epe < 0.0):
        raise ValueError("expected_exposure must be non-negative")

    lgd = 1.0 - recovery_rate
    hazard = credit_spread / lgd if lgd > 0.0 else 0.0
    survival = _survival_curve(t, hazard)
    cva = _discrete_cva(epe, df, survival, lgd)
    return {
        "cva": round(float(cva), 6),
        "lgd": round(lgd, 8),
        "hazard_rate": round(hazard, 10),
        "n_buckets": int(epe.size),
    }


def debt_valuation_adjustment_dva(
    expected_negative_exposure: np.ndarray,
    time_steps: np.ndarray,
    discount_factors: np.ndarray,
    own_credit_spread: float,
    own_recovery_rate: float = 0.4,
) -> dict:  # type: ignore[type-arg]
    """Debit Valuation Adjustment — the symmetric own-default benefit.

    DVA mirrors CVA using the *negative* expected exposure (the amount the bank
    owes) and the bank's *own* credit spread. It is a gain to the reporting
    entity (own default extinguishes a liability).

    Args:
        expected_negative_exposure: ``(n,)`` ENE per bucket (>= 0, magnitude).
        time_steps: ``(n,)`` strictly increasing bucket end-times.
        discount_factors: ``(n,)`` discount factors in ``(0, 1]``.
        own_credit_spread: The bank's own CDS spread (decimal).
        own_recovery_rate: The bank's own recovery rate in ``[0, 1)``.

    Returns:
        Dict with ``dva`` (reported as a positive magnitude), ``lgd`` and
        ``hazard_rate``.

    Raises:
        ValueError: If profiles mismatch or parameters are invalid.
    """
    result = credit_valuation_adjustment_cva(
        expected_negative_exposure,
        time_steps,
        discount_factors,
        own_credit_spread,
        own_recovery_rate,
    )
    return {
        "dva": result["cva"],
        "lgd": result["lgd"],
        "hazard_rate": result["hazard_rate"],
        "n_buckets": result["n_buckets"],
    }


def funding_valuation_adjustment_fva(
    expected_exposure: np.ndarray,
    time_steps: np.ndarray,
    discount_factors: np.ndarray,
    funding_spread: float,
    survival_probability: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Funding Valuation Adjustment — cost of funding uncollateralised exposure.

    ``FVA = funding_spread * sum_k EPE_k * DF_k * S_k * dt_k`` — the present
    value of the funding-spread carry on the expected exposure over each
    interval, conditional on counterparty survival.

    Args:
        expected_exposure: ``(n,)`` EPE per bucket (>= 0).
        time_steps: ``(n,)`` strictly increasing bucket end-times (years).
        discount_factors: ``(n,)`` discount factors in ``(0, 1]``.
        funding_spread: Bank funding spread over risk-free (decimal).
        survival_probability: Optional ``(n,)`` counterparty survival at each
            bucket end; defaults to all-ones (no default conditioning).

    Returns:
        Dict with ``fva`` and ``n_buckets``.

    Raises:
        ValueError: If profiles mismatch or the spread is negative.
    """
    epe = np.asarray(expected_exposure, dtype=np.float64).ravel()
    t = np.asarray(time_steps, dtype=np.float64).ravel()
    df = np.asarray(discount_factors, dtype=np.float64).ravel()
    _validate_profile(epe, t, df)
    if funding_spread < 0.0:
        raise ValueError("funding_spread must be non-negative")
    if np.any(epe < 0.0):
        raise ValueError("expected_exposure must be non-negative")

    if survival_probability is None:
        surv = np.ones_like(epe)
    else:
        surv = np.asarray(survival_probability, dtype=np.float64).ravel()
        if surv.shape != epe.shape:
            raise ValueError("survival_probability must match exposure shape")

    dt = np.diff(np.concatenate(([0.0], t)))
    fva = funding_spread * float(np.sum(epe * df * surv * dt))
    return {
        "fva": round(fva, 6),
        "n_buckets": int(epe.size),
    }


def capital_valuation_adjustment_kva(
    capital_profile: np.ndarray,
    time_steps: np.ndarray,
    discount_factors: np.ndarray,
    cost_of_capital: float = 0.10,
) -> dict:  # type: ignore[type-arg]
    """Capital Valuation Adjustment — lifetime cost of regulatory capital.

    ``KVA = cost_of_capital * sum_k K_k * DF_k * dt_k`` — the present value of
    the shareholders' required return on the regulatory capital held against the
    trade over its life.

    Args:
        capital_profile: ``(n,)`` regulatory capital held per bucket (>= 0).
        time_steps: ``(n,)`` strictly increasing bucket end-times (years).
        discount_factors: ``(n,)`` discount factors in ``(0, 1]``.
        cost_of_capital: Hurdle rate / cost of capital (decimal, e.g. 0.10).

    Returns:
        Dict with ``kva`` and ``n_buckets``.

    Raises:
        ValueError: If profiles mismatch or the cost of capital is negative.
    """
    cap = np.asarray(capital_profile, dtype=np.float64).ravel()
    t = np.asarray(time_steps, dtype=np.float64).ravel()
    df = np.asarray(discount_factors, dtype=np.float64).ravel()
    _validate_profile(cap, t, df)
    if cost_of_capital < 0.0:
        raise ValueError("cost_of_capital must be non-negative")
    if np.any(cap < 0.0):
        raise ValueError("capital_profile must be non-negative")

    dt = np.diff(np.concatenate(([0.0], t)))
    kva = cost_of_capital * float(np.sum(cap * df * dt))
    return {
        "kva": round(kva, 6),
        "n_buckets": int(cap.size),
    }


def margin_valuation_adjustment_mva(
    initial_margin_profile: np.ndarray,
    time_steps: np.ndarray,
    discount_factors: np.ndarray,
    margin_funding_spread: float,
) -> dict:  # type: ignore[type-arg]
    """Margin Valuation Adjustment — funding cost of posted initial margin.

    ``MVA = spread * sum_k IM_k * DF_k * dt_k`` — present value of the carry on
    posting (and funding) initial margin that earns less than the bank's funding
    cost over the trade's life.

    Args:
        initial_margin_profile: ``(n,)`` expected initial margin posted per
            bucket (>= 0).
        time_steps: ``(n,)`` strictly increasing bucket end-times (years).
        discount_factors: ``(n,)`` discount factors in ``(0, 1]``.
        margin_funding_spread: Spread between funding cost and margin remuneration.

    Returns:
        Dict with ``mva`` and ``n_buckets``.

    Raises:
        ValueError: If profiles mismatch or the spread is negative.
    """
    im = np.asarray(initial_margin_profile, dtype=np.float64).ravel()
    t = np.asarray(time_steps, dtype=np.float64).ravel()
    df = np.asarray(discount_factors, dtype=np.float64).ravel()
    _validate_profile(im, t, df)
    if margin_funding_spread < 0.0:
        raise ValueError("margin_funding_spread must be non-negative")
    if np.any(im < 0.0):
        raise ValueError("initial_margin_profile must be non-negative")

    dt = np.diff(np.concatenate(([0.0], t)))
    mva = margin_funding_spread * float(np.sum(im * df * dt))
    return {
        "mva": round(mva, 6),
        "n_buckets": int(im.size),
    }


def xva_aggregation(
    cva: float,
    dva: float = 0.0,
    fva: float = 0.0,
    kva: float = 0.0,
    mva: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Aggregate the XVA components into a total valuation adjustment.

    Sign convention (cost to the bank is positive, reducing the trade value):
    ``total_xva = CVA - DVA + FVA + KVA + MVA``. DVA is a benefit and so enters
    negatively. The adjusted price is ``risk_free_price - total_xva`` downstream.

    Args:
        cva: Credit valuation adjustment (cost, >= 0).
        dva: Debit valuation adjustment (benefit, >= 0).
        fva: Funding valuation adjustment (cost).
        kva: Capital valuation adjustment (cost).
        mva: Margin valuation adjustment (cost).

    Returns:
        Dict with ``total_xva`` and a ``components`` breakdown.

    Raises:
        ValueError: If any component is non-finite.
    """
    components = {"cva": cva, "dva": dva, "fva": fva, "kva": kva, "mva": mva}
    for name, val in components.items():
        if not np.isfinite(val):
            raise ValueError(f"{name} must be finite")
    total = cva - dva + fva + kva + mva
    return {
        "total_xva": round(float(total), 6),
        "components": {k: round(float(v), 6) for k, v in components.items()},
    }


def cva_sensitivity_cva_greeks(
    expected_exposure: np.ndarray,
    time_steps: np.ndarray,
    discount_factors: np.ndarray,
    credit_spread: float,
    recovery_rate: float = 0.4,
    spread_bump: float = 0.0001,
) -> dict:  # type: ignore[type-arg]
    """CVA sensitivities — CS01 (credit delta) and exposure delta.

    Computes the base CVA and:
      * ``cs01``: the change in CVA for a +1 bp parallel shift in the credit
        spread (finite-difference), the dominant CVA Greek for capital and
        hedging.
      * ``exposure_delta``: sensitivity to a 1% uniform scaling of the EPE
        profile (linear, so exact = CVA * 0.01).

    Args:
        expected_exposure: ``(n,)`` EPE per bucket (>= 0).
        time_steps: ``(n,)`` strictly increasing bucket end-times (years).
        discount_factors: ``(n,)`` discount factors in ``(0, 1]``.
        credit_spread: Counterparty CDS spread (decimal).
        recovery_rate: Counterparty recovery rate in ``[0, 1)``.
        spread_bump: Spread shift for the CS01 bump (default 1 bp).

    Returns:
        Dict with ``cva``, ``cs01`` (per ``spread_bump``) and ``exposure_delta``.

    Raises:
        ValueError: If profiles mismatch or parameters are invalid.
    """
    base = credit_valuation_adjustment_cva(
        expected_exposure, time_steps, discount_factors, credit_spread, recovery_rate
    )
    bumped = credit_valuation_adjustment_cva(
        expected_exposure,
        time_steps,
        discount_factors,
        credit_spread + spread_bump,
        recovery_rate,
    )
    cs01 = bumped["cva"] - base["cva"]
    return {
        "cva": base["cva"],
        "cs01": round(float(cs01), 8),
        "exposure_delta": round(base["cva"] * 0.01, 8),
        "spread_bump": spread_bump,
    }


def wrong_way_risk_adjustment(
    base_cva: float,
    correlation: float,
    exposure_volatility: float = 0.3,
) -> dict:  # type: ignore[type-arg]
    """Wrong-way-risk (WWR) multiplicative adjustment to CVA.

    When exposure rises as the counterparty's credit deteriorates (positive
    correlation), CVA is understated. A first-order alpha multiplier
    ``alpha = 1 + correlation * exposure_volatility`` (clamped >= 0) scales the
    base CVA; negative correlation gives right-way risk (alpha < 1).

    Args:
        base_cva: Independence-assumption CVA (>= 0).
        correlation: Exposure/credit correlation in ``[-1, 1]``.
        exposure_volatility: Relative exposure volatility (>= 0) controlling the
            adjustment magnitude.

    Returns:
        Dict with ``adjusted_cva``, the ``alpha`` multiplier and the
        ``wwr_addon`` (= adjusted - base).

    Raises:
        ValueError: If correlation is out of range or inputs are negative.
    """
    if not -1.0 <= correlation <= 1.0:
        raise ValueError("correlation must be in [-1, 1]")
    if base_cva < 0.0:
        raise ValueError("base_cva must be non-negative")
    if exposure_volatility < 0.0:
        raise ValueError("exposure_volatility must be non-negative")

    alpha = max(1.0 + correlation * exposure_volatility, 0.0)
    adjusted = alpha * base_cva
    return {
        "adjusted_cva": round(adjusted, 6),
        "alpha": round(alpha, 8),
        "wwr_addon": round(adjusted - base_cva, 6),
    }

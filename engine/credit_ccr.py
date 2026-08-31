"""engine/credit_ccr.py — Counterparty Credit Risk exposure sub-domain.

Implements counterparty-exposure metrics: generic CCR exposure, the legacy
Current Exposure Method (CEM), the Basel Standardised Approach (SA-CCR), the
Potential Future Exposure (PFE) profile, Expected Positive Exposure (EPE),
regulatory Effective EPE (EEPE) and the supervisory collateral-haircut
calculation.

Numba rules (CLAUDE.md §3.1): exposure-path simulation pre-draws all randomness
in pure Python (RULE 3) and passes float64 arrays to the JIT kernel, which
returns only arrays (RULE 5).
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "counterparty_credit_risk_ccr_exposure",
    "current_exposure_method_cem",
    "standardised_approach_ccr_sa_ccr",
    "potential_future_exposure_pfe",
    "expected_positive_exposure_epe",
    "effective_epe_regulatory",
    "collateral_haircut_calculation",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _exposure_profile(mtm_paths: np.ndarray, quantile: float) -> np.ndarray:
    """Per-time-step expected exposure and the PFE quantile.

    ``mtm_paths`` is ``(n_paths, n_steps)`` mark-to-market. Exposure is
    ``max(MtM, 0)``. Returns a ``(2, n_steps)`` array: row 0 = EE (mean positive
    exposure), row 1 = PFE (quantile of positive exposure).
    """
    n_paths = mtm_paths.shape[0]
    n_steps = mtm_paths.shape[1]
    out = np.zeros((2, n_steps), dtype=np.float64)
    for t in range(n_steps):
        col = np.empty(n_paths, dtype=np.float64)
        ssum = 0.0
        for p in range(n_paths):
            v = mtm_paths[p, t]
            ex = v if v > 0.0 else 0.0
            col[p] = ex
            ssum += ex
        out[0, t] = ssum / n_paths
        col.sort()
        idx = int(np.floor(quantile * n_paths))
        if idx > n_paths - 1:
            idx = n_paths - 1
        out[1, t] = col[idx]
    return out


# ── Public functions ─────────────────────────────────────────────────────────


def counterparty_credit_risk_ccr_exposure(
    mark_to_market: float,
    add_on: float,
    collateral: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Generic CCR exposure = current exposure + add-on, net of collateral.

    ``Exposure = max(MtM - collateral, 0) + add_on``. The current exposure is
    floored at zero (a counterparty owing you nothing has no replacement cost).

    Args:
        mark_to_market: Current MtM of the netting set (positive = in-the-money
            to the reporting bank).
        add_on: Potential-future-exposure add-on (>= 0).
        collateral: Collateral held against the exposure (>= 0).

    Returns:
        Dict with ``current_exposure``, ``add_on`` and total ``exposure``.

    Raises:
        ValueError: If add-on or collateral are negative.
    """
    if add_on < 0.0:
        raise ValueError("add_on must be non-negative")
    if collateral < 0.0:
        raise ValueError("collateral must be non-negative")

    current = max(mark_to_market - collateral, 0.0)
    return {
        "current_exposure": round(current, 6),
        "add_on": round(add_on, 6),
        "exposure": round(current + add_on, 6),
    }


def current_exposure_method_cem(
    mark_to_market: float,
    notional: float,
    add_on_factor: float,
) -> dict:  # type: ignore[type-arg]
    """Basel I/II Current Exposure Method (CEM) EAD.

    ``EAD = max(MtM, 0) + notional * add_on_factor``. The add-on factor is the
    supervisory percentage by asset class and residual maturity (e.g. 0.5% IR
    < 1y, 1.5% IR 1-5y, 6% equity). CEM is superseded by SA-CCR but retained for
    legacy reporting.

    Args:
        mark_to_market: Current MtM (replacement cost component).
        notional: Trade / netting-set notional (>= 0).
        add_on_factor: Supervisory add-on factor in ``[0, 1]``.

    Returns:
        Dict with ``replacement_cost``, ``potential_future_exposure`` and total
        ``ead``.

    Raises:
        ValueError: If notional is negative or the factor is out of range.
    """
    if notional < 0.0:
        raise ValueError("notional must be non-negative")
    if not 0.0 <= add_on_factor <= 1.0:
        raise ValueError("add_on_factor must be in [0, 1]")

    rc = max(mark_to_market, 0.0)
    pfe = notional * add_on_factor
    return {
        "replacement_cost": round(rc, 6),
        "potential_future_exposure": round(pfe, 6),
        "ead": round(rc + pfe, 6),
    }


def standardised_approach_ccr_sa_ccr(
    mark_to_market: float,
    collateral: float,
    add_on_aggregate: float,
    alpha: float = 1.4,
) -> dict:  # type: ignore[type-arg]
    """Basel SA-CCR EAD (CRE52).

    ``EAD = alpha * (RC + PFE)`` where the replacement cost is
    ``RC = max(MtM - collateral, 0)`` (unmargined) and ``PFE = multiplier *
    AddOn_aggregate`` with the regulatory recognition-of-excess-collateral
    multiplier ``multiplier = min(1, 0.05 + 0.95 * exp((MtM - C)/(1.9 * AddOn)))``.
    The supervisory ``alpha`` is 1.4.

    Args:
        mark_to_market: Current netting-set MtM.
        collateral: Net collateral held (>= 0).
        add_on_aggregate: Aggregate asset-class add-on (>= 0).
        alpha: Supervisory scaling factor (default 1.4).

    Returns:
        Dict with ``replacement_cost``, ``multiplier``, ``pfe`` and ``ead``.

    Raises:
        ValueError: If collateral, add-on or alpha are invalid.
    """
    if collateral < 0.0:
        raise ValueError("collateral must be non-negative")
    if add_on_aggregate < 0.0:
        raise ValueError("add_on_aggregate must be non-negative")
    if alpha <= 0.0:
        raise ValueError("alpha must be positive")

    rc = max(mark_to_market - collateral, 0.0)
    net = mark_to_market - collateral
    if add_on_aggregate > 0.0:
        multiplier = min(1.0, 0.05 + 0.95 * np.exp(net / (1.9 * add_on_aggregate)))
    else:
        multiplier = 1.0
    pfe = multiplier * add_on_aggregate
    ead = alpha * (rc + pfe)
    return {
        "replacement_cost": round(rc, 6),
        "multiplier": round(float(multiplier), 10),
        "pfe": round(float(pfe), 6),
        "ead": round(float(ead), 6),
        "alpha": alpha,
    }


def potential_future_exposure_pfe(
    initial_value: float,
    volatility: float,
    time_steps: np.ndarray,
    quantile: float = 0.95,
    drift: float = 0.0,
    n_paths: int = 20_000,
    seed: int = 909,
) -> dict:  # type: ignore[type-arg]
    """Potential Future Exposure profile via Monte-Carlo (arithmetic BM proxy).

    Simulates the netting-set value as ``V_t = V_0 + drift*t + sigma*sqrt(t)*Z``
    and reports the per-step PFE (high quantile of positive exposure) and the
    peak PFE. Randomness is pre-drawn in pure Python (RULE 3).

    PFE at each time step is the empirical quantile of the simulated exposure
    distribution rather than a closed-form expression, so results carry
    Monte Carlo sampling noise that varies with ``n_paths`` and ``seed``.

    Args:
        initial_value: Current netting-set value V_0.
        volatility: Per-sqrt-time value volatility sigma (>= 0).
        time_steps: Strictly positive time points (years) at which to profile.
        quantile: PFE confidence in ``(0, 1)`` (default 95%).
        drift: Per-unit-time drift of the value process.
        n_paths: Number of Monte-Carlo paths.
        seed: RNG seed.

    Returns:
        Dict with ``ee`` (expected exposure per step), ``pfe`` (per step),
        ``peak_pfe`` and the ``time_steps``.

    Raises:
        ValueError: If volatility is negative, steps non-positive, or quantile
            out of range.
    """
    t = np.asarray(time_steps, dtype=np.float64).ravel()
    if t.size == 0 or np.any(t <= 0.0):
        raise ValueError("time_steps must be positive and non-empty")
    if volatility < 0.0:
        raise ValueError("volatility must be non-negative")
    if not 0.0 < quantile < 1.0:
        raise ValueError("quantile must be in (0, 1)")

    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_paths, t.size)).astype(np.float64)
    mtm = initial_value + drift * t[None, :] + volatility * np.sqrt(t)[None, :] * z
    profile = _exposure_profile(np.ascontiguousarray(mtm), quantile)
    ee = profile[0]
    pfe = profile[1]
    return {
        "ee": [round(float(v), 6) for v in ee],
        "pfe": [round(float(v), 6) for v in pfe],
        "peak_pfe": round(float(np.max(pfe)), 6),
        "time_steps": [float(x) for x in t],
        "quantile": quantile,
    }


def expected_positive_exposure_epe(
    expected_exposure: np.ndarray,
    time_steps: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Expected Positive Exposure — time-weighted average expected exposure.

    EPE is the time-average of the expected-exposure profile over the horizon
    (CRE53): ``EPE = (1/T) * integral_0^T EE(t) dt`` approximated by the
    trapezoidal rule on the supplied grid.

    Args:
        expected_exposure: ``(n,)`` expected-exposure profile EE(t) (>= 0).
        time_steps: ``(n,)`` strictly increasing time points (years), starting
            at or after 0.

    Returns:
        Dict with ``epe`` (time-weighted average) and the ``horizon``.

    Raises:
        ValueError: If arrays mismatch, are too short, or times not increasing.
    """
    ee = np.asarray(expected_exposure, dtype=np.float64).ravel()
    t = np.asarray(time_steps, dtype=np.float64).ravel()
    if ee.shape != t.shape or ee.size < 2:
        raise ValueError("expected_exposure and time_steps must match (>=2 points)")
    if np.any(np.diff(t) <= 0.0):
        raise ValueError("time_steps must be strictly increasing")
    if np.any(ee < 0.0):
        raise ValueError("expected_exposure must be non-negative")

    horizon = float(t[-1] - t[0])
    integral = float(np.trapezoid(ee, t))
    epe = integral / horizon if horizon > 0.0 else float(ee[0])
    return {
        "epe": round(epe, 6),
        "horizon": round(horizon, 8),
    }


def effective_epe_regulatory(
    expected_exposure: np.ndarray,
    time_steps: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Basel Effective EPE (EEPE) with the non-decreasing Effective EE profile.

    The Effective Expected Exposure is the running maximum of EE
    ``EEE(t) = max(EEE(t-1), EE(t))`` (it never decreases, capturing roll-over
    risk). EEPE is the time-weighted average of EEE over the first year (CRE53).
    EAD = alpha * EEPE downstream.

    Args:
        expected_exposure: ``(n,)`` expected-exposure profile (>= 0).
        time_steps: ``(n,)`` strictly increasing time points (years).

    Returns:
        Dict with ``eee`` (effective EE profile), ``eepe`` (time-weighted avg)
        and the ``horizon``.

    Raises:
        ValueError: If arrays mismatch, too short, or times not increasing.
    """
    ee = np.asarray(expected_exposure, dtype=np.float64).ravel()
    t = np.asarray(time_steps, dtype=np.float64).ravel()
    if ee.shape != t.shape or ee.size < 2:
        raise ValueError("expected_exposure and time_steps must match (>=2 points)")
    if np.any(np.diff(t) <= 0.0):
        raise ValueError("time_steps must be strictly increasing")
    if np.any(ee < 0.0):
        raise ValueError("expected_exposure must be non-negative")

    eee = np.maximum.accumulate(ee)
    horizon = float(t[-1] - t[0])
    integral = float(np.trapezoid(eee, t))
    eepe = integral / horizon if horizon > 0.0 else float(eee[0])
    return {
        "eee": [round(float(v), 6) for v in eee],
        "eepe": round(eepe, 6),
        "horizon": round(horizon, 8),
    }


def collateral_haircut_calculation(
    collateral_value: float,
    haircut_collateral: float,
    haircut_fx: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Supervisory collateral haircut under the comprehensive approach (CRE22).

    The adjusted collateral value is
    ``C_adj = C * (1 - H_c - H_fx)`` where ``H_c`` is the market-price-volatility
    haircut and ``H_fx`` the currency-mismatch haircut (8% standard). The
    adjusted value is floored at zero.

    Args:
        collateral_value: Nominal collateral market value (>= 0).
        haircut_collateral: Collateral volatility haircut in ``[0, 1]``.
        haircut_fx: Currency-mismatch haircut in ``[0, 1]``.

    Returns:
        Dict with ``adjusted_collateral``, ``total_haircut`` and the original
        ``collateral_value``.

    Raises:
        ValueError: If collateral is negative or haircuts are out of range.
    """
    if collateral_value < 0.0:
        raise ValueError("collateral_value must be non-negative")
    if not 0.0 <= haircut_collateral <= 1.0:
        raise ValueError("haircut_collateral must be in [0, 1]")
    if not 0.0 <= haircut_fx <= 1.0:
        raise ValueError("haircut_fx must be in [0, 1]")

    total_haircut = min(haircut_collateral + haircut_fx, 1.0)
    adjusted = collateral_value * (1.0 - total_haircut)
    return {
        "adjusted_collateral": round(max(adjusted, 0.0), 6),
        "total_haircut": round(total_haircut, 8),
        "collateral_value": round(collateral_value, 6),
    }

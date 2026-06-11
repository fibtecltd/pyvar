"""engine/alm_duration.py — ALM duration & gap analytics (ALM & Balance Sheet).

Duration-gap analysis, balance-sheet Macaulay/modified/effective duration,
convexity gap, NII rate-shock sensitivity and a baseline NII projection.

Pure-Python vectorised NumPy wrappers (CLAUDE.md §3.1 satisfied trivially — no
JIT regions). Durations in years; currency amounts for NII/EVE.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "duration_gap_analysis",
    "macaulay_duration_balance_sheet",
    "modified_duration_balance_sheet",
    "effective_duration_alm",
    "convexity_gap",
    "nii_sensitivity_rate_shock",
    "nii_simulation_baseline",
]


def _pv_weighted_duration(cashflows: np.ndarray, times: np.ndarray, rate: float) -> tuple[float, float]:
    """Return (price, Macaulay duration) for continuously-discounted cashflows."""
    df = np.exp(-rate * times)
    pv = cashflows * df
    price = float(np.sum(pv))
    duration = float(np.sum(times * pv) / price) if price != 0 else 0.0
    return price, duration


def macaulay_duration_balance_sheet(
    cashflows: np.ndarray,
    times: np.ndarray,
    discount_rate: float,
) -> dict:  # type: ignore[type-arg]
    """Macaulay duration of a balance-sheet cashflow stream (years).

    Args:
        cashflows: Cashflow amounts.
        times: Cashflow times in years.
        discount_rate: Continuous discount rate (decimal).

    Returns:
        Dict with ``macaulay_duration`` and ``present_value``.

    Raises:
        ValueError: If arrays differ in length.
    """
    cf = np.asarray(cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    if cf.size != t.size:
        raise ValueError("cashflows and times must match length")
    pv, dur = _pv_weighted_duration(cf, t, discount_rate)
    return {"macaulay_duration": round(dur, 8), "present_value": round(pv, 6)}


def modified_duration_balance_sheet(
    cashflows: np.ndarray,
    times: np.ndarray,
    discount_rate: float,
    frequency: int = 1,
) -> dict:  # type: ignore[type-arg]
    """Modified duration of a balance-sheet position.

    ``D_mod = D_mac / (1 + y/m)``; with continuous discounting (frequency large)
    modified ≈ Macaulay.

    Args:
        cashflows: Cashflow amounts.
        times: Cashflow times in years.
        discount_rate: Discount rate (decimal).
        frequency: Compounding frequency per year.

    Returns:
        Dict with ``modified_duration``, ``macaulay_duration``, ``present_value``.

    Raises:
        ValueError: If arrays differ in length.
    """
    mac = macaulay_duration_balance_sheet(cashflows, times, discount_rate)
    mod = mac["macaulay_duration"] / (1.0 + discount_rate / frequency)
    return {
        "modified_duration": round(float(mod), 8),
        "macaulay_duration": mac["macaulay_duration"],
        "present_value": mac["present_value"],
    }


def effective_duration_alm(
    pv_base: float,
    pv_up: float,
    pv_down: float,
    rate_shock: float,
) -> dict:  # type: ignore[type-arg]
    """Effective duration of an ALM position from re-valued PVs under a shock.

    ``D_eff = (PV− − PV+) / (2 · PV0 · Δy)`` — captures optionality in deposits,
    prepayments and caps/floors that analytic duration misses.

    Args:
        pv_base: Present value at base rates.
        pv_up: Present value after +``rate_shock``.
        pv_down: Present value after −``rate_shock``.
        rate_shock: Parallel rate shock (decimal).

    Returns:
        Dict with ``effective_duration``.

    Raises:
        ValueError: If ``pv_base`` or ``rate_shock`` is non-positive.
    """
    if pv_base <= 0 or rate_shock <= 0:
        raise ValueError("pv_base and rate_shock must be positive")
    eff = (pv_down - pv_up) / (2.0 * pv_base * rate_shock)
    return {"effective_duration": round(float(eff), 8)}


def duration_gap_analysis(
    asset_duration: float,
    liability_duration: float,
    total_assets: float,
    total_liabilities: float,
    rate_shock: float = 0.01,
) -> dict:  # type: ignore[type-arg]
    """Duration-gap analysis of the banking book.

    Duration gap ``DGAP = D_A − (L/A)·D_L``. The change in economic value of
    equity for a rate shock is approximately ``ΔEVE ≈ −DGAP · A · Δy``.

    Args:
        asset_duration: Weighted asset duration (years).
        liability_duration: Weighted liability duration (years).
        total_assets: Total assets (currency).
        total_liabilities: Total liabilities (currency).
        rate_shock: Parallel rate shock (decimal).

    Returns:
        Dict with ``duration_gap``, ``leverage_adjusted_gap``, ``delta_eve`` and
        ``equity``.

    Raises:
        ValueError: If ``total_assets`` is non-positive.
    """
    if total_assets <= 0:
        raise ValueError("total_assets must be positive")
    lev = total_liabilities / total_assets
    dgap = asset_duration - lev * liability_duration
    delta_eve = -dgap * total_assets * rate_shock
    return {
        "duration_gap": round(float(dgap), 8),
        "leverage_adjusted_gap": round(float(lev * liability_duration), 8),
        "delta_eve": round(float(delta_eve), 6),
        "equity": round(float(total_assets - total_liabilities), 6),
    }


def convexity_gap(
    asset_convexity: float,
    liability_convexity: float,
    total_assets: float,
    total_liabilities: float,
) -> dict:  # type: ignore[type-arg]
    """Convexity gap of the banking book.

    ``CGAP = C_A − (L/A)·C_L`` — the second-order term refining the
    duration-gap EVE estimate ``ΔEVE ≈ A(−DGAP·Δy + ½·CGAP·Δy²)``.

    Args:
        asset_convexity: Weighted asset convexity.
        liability_convexity: Weighted liability convexity.
        total_assets: Total assets (currency).
        total_liabilities: Total liabilities (currency).

    Returns:
        Dict with ``convexity_gap``.

    Raises:
        ValueError: If ``total_assets`` is non-positive.
    """
    if total_assets <= 0:
        raise ValueError("total_assets must be positive")
    lev = total_liabilities / total_assets
    cgap = asset_convexity - lev * liability_convexity
    return {"convexity_gap": round(float(cgap), 8)}


def nii_sensitivity_rate_shock(
    rate_sensitive_assets: float,
    rate_sensitive_liabilities: float,
    rate_shock: float,
) -> dict:  # type: ignore[type-arg]
    """Net interest income sensitivity to a parallel rate shock.

    ``ΔNII ≈ (RSA − RSL) · Δrate`` where ``RSA − RSL`` is the cumulative
    one-year repricing gap. A positive gap gains NII when rates rise.

    Args:
        rate_sensitive_assets: Assets repricing within the horizon (currency).
        rate_sensitive_liabilities: Liabilities repricing within the horizon.
        rate_shock: Parallel rate shock (decimal).

    Returns:
        Dict with ``delta_nii``, ``repricing_gap``.
    """
    gap = rate_sensitive_assets - rate_sensitive_liabilities
    delta_nii = gap * rate_shock
    return {"delta_nii": round(float(delta_nii), 6), "repricing_gap": round(float(gap), 6)}


def nii_simulation_baseline(
    asset_balances: np.ndarray,
    asset_rates: np.ndarray,
    liability_balances: np.ndarray,
    liability_rates: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Baseline (current-rate) net-interest-income projection.

    ``NII = Σ A_i·r^A_i − Σ L_j·r^L_j`` over the projection horizon.

    Args:
        asset_balances: Balance per interest-earning asset bucket.
        asset_rates: Yield per asset bucket (decimal).
        liability_balances: Balance per interest-bearing liability bucket.
        liability_rates: Cost per liability bucket (decimal).

    Returns:
        Dict with ``nii``, ``interest_income``, ``interest_expense``.

    Raises:
        ValueError: If paired arrays differ in length.
    """
    ab = np.asarray(asset_balances, dtype=np.float64)
    ar = np.asarray(asset_rates, dtype=np.float64)
    lb = np.asarray(liability_balances, dtype=np.float64)
    lr = np.asarray(liability_rates, dtype=np.float64)
    if ab.size != ar.size or lb.size != lr.size:
        raise ValueError("balances and rates must match length within each side")

    income = float(np.sum(ab * ar))
    expense = float(np.sum(lb * lr))
    return {
        "nii": round(income - expense, 6),
        "interest_income": round(income, 6),
        "interest_expense": round(expense, 6),
    }

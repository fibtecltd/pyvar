"""engine/alm_behavioural.py — Behavioural & prepayment models (ALM).

Mortgage prepayment (PSA-style SMM/CPR), behavioural modelling of non-maturity
deposits (NMD core/non-core split and run-off), NMD stability, core-deposit
duration and the constant prepayment rate (CPR).

Numba rules (CLAUDE.md §3.1): the month-by-month prepayment cashflow projection
is a stateless @njit(cache=True) kernel returning a float64 array; behavioural
deposit logic is light vectorised NumPy in the wrappers.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

__all__ = [
    "prepayment_model_mortgages",
    "behavioural_modelling_nmds",
    "non_maturity_deposit_stability",
    "core_deposit_duration",
    "loan_prepayment_rate_cpr",
]


def loan_prepayment_rate_cpr(
    smm: float | None = None,
    cpr: float | None = None,
) -> dict:  # type: ignore[type-arg]
    """Convert between single-monthly mortality (SMM) and CPR.

    ``CPR = 1 − (1 − SMM)^12`` and ``SMM = 1 − (1 − CPR)^{1/12}``. Provide exactly
    one of the two.

    Args:
        smm: Single monthly mortality (decimal), if converting SMM→CPR.
        cpr: Constant prepayment rate (decimal), if converting CPR→SMM.

    Returns:
        Dict with both ``cpr`` and ``smm``.

    Raises:
        ValueError: If not exactly one input is provided or out of [0, 1).
    """
    if (smm is None) == (cpr is None):
        raise ValueError("provide exactly one of smm or cpr")
    if smm is not None:
        if not 0.0 <= smm < 1.0:
            raise ValueError("smm must be in [0, 1)")
        cpr_v = 1.0 - (1.0 - smm) ** 12
        smm_v = smm
    else:
        if not 0.0 <= cpr < 1.0:  # type: ignore[operator]
            raise ValueError("cpr must be in [0, 1)")
        cpr_v = float(cpr)  # type: ignore[arg-type]
        smm_v = 1.0 - (1.0 - cpr_v) ** (1.0 / 12.0)
    return {"cpr": round(float(cpr_v), 8), "smm": round(float(smm_v), 8)}


@njit(cache=True)
def _amortise_with_prepay(
    principal: float,
    monthly_rate: float,
    n_months: int,
    smm: float,
) -> np.ndarray:
    """Project month-by-month total cashflow with constant SMM prepayment.

    Returns a float64 array of total cashflows (scheduled P&I + prepayment).
    """
    out = np.empty(n_months, dtype=np.float64)
    balance = principal
    # level payment for the fully-amortising schedule
    if monthly_rate > 0.0:
        pmt = principal * monthly_rate / (1.0 - (1.0 + monthly_rate) ** (-n_months))
    else:
        pmt = principal / n_months
    for m in range(n_months):
        interest = balance * monthly_rate
        sched_principal = pmt - interest
        if sched_principal > balance:
            sched_principal = balance
        balance_after_sched = balance - sched_principal
        prepay = balance_after_sched * smm
        out[m] = interest + sched_principal + prepay
        balance = balance_after_sched - prepay
        if balance < 0.0:
            balance = 0.0
    return out


def prepayment_model_mortgages(
    principal: float,
    annual_rate: float,
    term_years: int,
    cpr: float,
) -> dict:  # type: ignore[type-arg]
    """Project mortgage cashflows under a constant CPR prepayment assumption.

    Note: cashflows come from a month-by-month recursive amortisation loop
    (interest, then scheduled principal, then prepayment on the remaining
    balance each month), not a single closed-form cashflow expression.

    Higher CPR shortens the weighted-average life (WAL) of the pool.

    Args:
        principal: Initial pool balance.
        annual_rate: Annual mortgage coupon (decimal).
        term_years: Original term in years.
        cpr: Constant prepayment rate (decimal).

    Returns:
        Dict with ``total_cashflow``, ``weighted_average_life`` (years) and the
        equivalent monthly ``smm``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if principal <= 0 or term_years < 1:
        raise ValueError("principal must be > 0 and term_years >= 1")
    if not 0.0 <= cpr < 1.0:
        raise ValueError("cpr must be in [0, 1)")

    smm = 1.0 - (1.0 - cpr) ** (1.0 / 12.0)
    n_months = term_years * 12
    monthly_rate = annual_rate / 12.0
    cashflows = _amortise_with_prepay(principal, monthly_rate, n_months, smm)
    months = np.arange(1, n_months + 1, dtype=np.float64)
    # WAL on principal portion approximated using total cashflows
    total_cf = float(np.sum(cashflows))
    wal = float(np.sum(months / 12.0 * cashflows) / total_cf) if total_cf > 0 else 0.0
    return {
        "total_cashflow": round(total_cf, 4),
        "weighted_average_life": round(wal, 6),
        "smm": round(float(smm), 8),
    }


def behavioural_modelling_nmds(
    total_balance: float,
    core_fraction: float,
    core_runoff_rate: float,
    non_core_runoff_rate: float,
    horizon_years: float = 5.0,
) -> dict:  # type: ignore[type-arg]
    """Model non-maturity-deposit (NMD) run-off splitting core / non-core.

    [REGULATORY] BCBS d368 NMD treatment. Core deposits are stable and decay
    slowly; non-core (volatile) deposits run off quickly. Returns the projected
    surviving balance and the effective average life.

    Args:
        total_balance: Total NMD balance (currency).
        core_fraction: Fraction deemed core in [0, 1].
        core_runoff_rate: Annual run-off rate of core deposits (decimal).
        non_core_runoff_rate: Annual run-off rate of non-core (decimal).
        horizon_years: Projection horizon (years).

    Returns:
        Dict with ``core_balance``, ``non_core_balance``, ``surviving_balance``
        and ``effective_life``.

    Raises:
        ValueError: If ``core_fraction`` not in [0, 1].
    """
    if not 0.0 <= core_fraction <= 1.0:
        raise ValueError("core_fraction must be in [0, 1]")
    core = total_balance * core_fraction
    non_core = total_balance * (1.0 - core_fraction)
    core_surv = core * math.exp(-core_runoff_rate * horizon_years)
    non_core_surv = non_core * math.exp(-non_core_runoff_rate * horizon_years)
    surviving = core_surv + non_core_surv
    # effective life = balance-weighted 1/runoff (mean residence time)
    eff_life = 0.0
    if total_balance > 0:
        core_life = 1.0 / core_runoff_rate if core_runoff_rate > 0 else horizon_years
        nc_life = 1.0 / non_core_runoff_rate if non_core_runoff_rate > 0 else horizon_years
        eff_life = (core * core_life + non_core * nc_life) / total_balance
    return {
        "core_balance": round(float(core), 6),
        "non_core_balance": round(float(non_core), 6),
        "surviving_balance": round(float(surviving), 6),
        "effective_life": round(float(eff_life), 6),
    }


def non_maturity_deposit_stability(
    balance_history: np.ndarray,
    confidence_level: float = 0.99,
) -> dict:  # type: ignore[type-arg]
    """Estimate the stable (core) portion of NMDs from a balance history.

    Stable balance = the low percentile of the historical balance series (the
    level retained with ``confidence_level`` probability); the volatile portion
    is the remainder versus the current balance.

    Args:
        balance_history: Historical deposit balances (>= 2 observations).
        confidence_level: Confidence for the stable floor in [0.5, 1).

    Returns:
        Dict with ``stable_balance``, ``volatile_balance`` and
        ``stable_fraction``.

    Raises:
        ValueError: If fewer than 2 observations or bad confidence.
    """
    b = np.asarray(balance_history, dtype=np.float64)
    if b.size < 2:
        raise ValueError("need at least 2 balance observations")
    if not 0.5 <= confidence_level < 1.0:
        raise ValueError("confidence_level must be in [0.5, 1)")

    stable = float(np.percentile(b, (1.0 - confidence_level) * 100.0))
    current = float(b[-1])
    volatile = max(current - stable, 0.0)
    frac = stable / current if current != 0 else 0.0
    return {
        "stable_balance": round(stable, 6),
        "volatile_balance": round(volatile, 6),
        "stable_fraction": round(float(frac), 8),
    }


def core_deposit_duration(
    core_balance: float,
    decay_rate: float,
    discount_rate: float,
    max_years: float = 30.0,
) -> dict:  # type: ignore[type-arg]
    """Effective duration of core deposits modelled as a decaying annuity.

    Note: duration is computed as a discrete monthly Riemann sum over the
    exponential run-off schedule, not a closed-form integral of the
    continuous decay function.

    Core deposits run off at ``decay_rate`` (exponential). The duration is the
    PV-weighted average life of the run-off cashflows discounted at
    ``discount_rate`` — typically multi-year, which is why NMDs anchor the
    liability side of the duration gap.

    Args:
        core_balance: Core deposit balance (currency).
        decay_rate: Annual exponential decay rate (decimal, > 0).
        discount_rate: Discount rate (decimal, >= 0).
        max_years: Truncation horizon for the run-off integral.

    Returns:
        Dict with ``core_deposit_duration`` (years) and ``present_value``.

    Raises:
        ValueError: If ``decay_rate`` is non-positive.
    """
    if decay_rate <= 0:
        raise ValueError("decay_rate must be positive")
    if core_balance < 0:
        raise ValueError("core_balance must be >= 0")

    times = np.arange(1.0 / 12.0, max_years + 1e-9, 1.0 / 12.0)
    runoff = core_balance * decay_rate * np.exp(-decay_rate * times) / 12.0
    df = np.exp(-discount_rate * times)
    pv = runoff * df
    total_pv = float(np.sum(pv))
    duration = float(np.sum(times * pv) / total_pv) if total_pv > 0 else 0.0
    return {"core_deposit_duration": round(duration, 6), "present_value": round(total_pv, 6)}

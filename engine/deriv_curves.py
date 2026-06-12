"""engine/deriv_curves.py — Yield-curve construction (Derivatives & Pricing).

Nelson-Siegel and Nelson-Siegel-Svensson parametric fits, bootstrap of a zero
curve from par instruments, a par swap-rate curve, an OIS (SONIA/SOFR) discount
curve, a forward-rate-agreement pricer and a vanilla interest-rate-swap pricer.

Curve fitting uses SciPy least-squares / closed-form bootstrap in pure Python
(no @njit needed — the work is small and vectorised, CLAUDE.md §3.1 satisfied
trivially).
"""

from __future__ import annotations

import numpy as np
from scipy import optimize

__all__ = [
    "nelson_siegel_curve_fit",
    "nelson_siegel_svensson_curve",
    "bootstrap_yield_curve",
    "swap_rate_curve",
    "ois_curve_sonia_sofr",
    "forward_rate_agreement_fra",
    "interest_rate_swap_irs_pricer",
]


def _ns_yield(t: np.ndarray, beta0: float, beta1: float, beta2: float, tau: float) -> np.ndarray:
    """Nelson-Siegel yield for maturities ``t``."""
    t = np.where(t <= 0, 1e-8, t)
    factor = (1.0 - np.exp(-t / tau)) / (t / tau)
    return beta0 + beta1 * factor + beta2 * (factor - np.exp(-t / tau))


def nelson_siegel_curve_fit(
    maturities: np.ndarray,
    yields: np.ndarray,
    tau_init: float = 1.5,
) -> dict:  # type: ignore[type-arg]
    """Fit a Nelson-Siegel curve to observed yields.

    Parameters: ``beta0`` (level), ``beta1`` (slope), ``beta2`` (curvature),
    ``tau`` (decay). ``beta0 + beta1`` is the instantaneous short rate and
    ``beta0`` is the asymptotic long rate.

    Args:
        maturities: Observed maturities in years (> 0).
        yields: Observed yields (decimal) at those maturities.
        tau_init: Initial guess for the decay parameter.

    Returns:
        Dict with ``beta0``, ``beta1``, ``beta2``, ``tau`` and the fit
        ``rmse``.

    Raises:
        ValueError: If arrays differ or are too short.
    """
    t = np.asarray(maturities, dtype=np.float64)
    y = np.asarray(yields, dtype=np.float64)
    if t.size != y.size or t.size < 4:
        raise ValueError("need matching arrays with >= 4 points")

    def resid(p: np.ndarray) -> np.ndarray:
        return _ns_yield(t, p[0], p[1], p[2], p[3]) - y

    p0 = np.array([y[-1], y[0] - y[-1], 0.0, tau_init])
    sol = optimize.least_squares(resid, p0, bounds=([-1, -1, -1, 1e-3], [1, 1, 1, 30]))
    rmse = float(np.sqrt(np.mean(resid(sol.x) ** 2)))
    return {
        "beta0": round(float(sol.x[0]), 8),
        "beta1": round(float(sol.x[1]), 8),
        "beta2": round(float(sol.x[2]), 8),
        "tau": round(float(sol.x[3]), 8),
        "rmse": round(rmse, 10),
    }


def nelson_siegel_svensson_curve(
    maturities: np.ndarray,
    yields: np.ndarray,
    tau1_init: float = 1.5,
    tau2_init: float = 8.0,
) -> dict:  # type: ignore[type-arg]
    """Fit the Nelson-Siegel-Svensson (six-parameter) curve.

    Adds a second curvature hump (``beta3``, ``tau2``) to Nelson-Siegel, giving
    a closer fit to longer/more complex term structures.

    Args:
        maturities: Observed maturities in years (> 0).
        yields: Observed yields (decimal).
        tau1_init: Initial first decay parameter.
        tau2_init: Initial second decay parameter.

    Returns:
        Dict with ``beta0``..``beta3``, ``tau1``, ``tau2`` and ``rmse``.

    Raises:
        ValueError: If arrays differ or are too short.
    """
    t = np.asarray(maturities, dtype=np.float64)
    y = np.asarray(yields, dtype=np.float64)
    if t.size != y.size or t.size < 6:
        raise ValueError("need matching arrays with >= 6 points")

    def nss(p: np.ndarray) -> np.ndarray:
        b0, b1, b2, b3, ta1, ta2 = p
        tt = np.where(t <= 0, 1e-8, t)
        f1 = (1.0 - np.exp(-tt / ta1)) / (tt / ta1)
        f2 = (1.0 - np.exp(-tt / ta2)) / (tt / ta2)
        return np.asarray(
            b0 + b1 * f1 + b2 * (f1 - np.exp(-tt / ta1)) + b3 * (f2 - np.exp(-tt / ta2))
        )

    def resid(p: np.ndarray) -> np.ndarray:
        return nss(p) - y

    p0 = np.array([y[-1], y[0] - y[-1], 0.0, 0.0, tau1_init, tau2_init])
    sol = optimize.least_squares(
        resid, p0, bounds=([-1, -1, -1, -1, 1e-3, 1e-3], [1, 1, 1, 1, 30, 30])
    )
    rmse = float(np.sqrt(np.mean(resid(sol.x) ** 2)))
    return {
        "beta0": round(float(sol.x[0]), 8),
        "beta1": round(float(sol.x[1]), 8),
        "beta2": round(float(sol.x[2]), 8),
        "beta3": round(float(sol.x[3]), 8),
        "tau1": round(float(sol.x[4]), 8),
        "tau2": round(float(sol.x[5]), 8),
        "rmse": round(rmse, 10),
    }


def bootstrap_yield_curve(
    par_rates: np.ndarray,
    maturities: np.ndarray,
    frequency: int = 1,
    face_value: float = 1.0,
) -> dict:  # type: ignore[type-arg]
    """Bootstrap zero (spot) rates from par-coupon bond rates.

    Sequentially solves for each discount factor so each par bond prices to par,
    then converts discount factors to continuously-compounded zero rates.

    Args:
        par_rates: Par coupon rate per maturity (decimal).
        maturities: Maturities in years, ascending, evenly spaced by 1/freq.
        frequency: Coupon frequency per year.
        face_value: Par value (defaults to 1).

    Returns:
        Dict with ``zero_rates`` (continuous) and ``discount_factors``.

    Raises:
        ValueError: If arrays differ in length.
    """
    par = np.asarray(par_rates, dtype=np.float64)
    t = np.asarray(maturities, dtype=np.float64)
    if par.size != t.size:
        raise ValueError("par_rates and maturities must match length")

    n = par.size
    dfs = np.zeros(n, dtype=np.float64)
    for i in range(n):
        coupon = par[i] * face_value / frequency
        coupon_sum = 0.0
        for j in range(i):
            coupon_sum += coupon * dfs[j]
        dfs[i] = (face_value - coupon_sum) / (face_value + coupon)
    zero_rates = -np.log(dfs) / t
    return {
        "zero_rates": [round(float(z), 10) for z in zero_rates],
        "discount_factors": [round(float(d), 10) for d in dfs],
    }


def swap_rate_curve(
    discount_factors: np.ndarray,
    maturities: np.ndarray,
    frequency: int = 1,
) -> dict:  # type: ignore[type-arg]
    """Par swap rates implied by a discount-factor curve.

    For each tenor, ``swap_rate = (1 − DF(T)) / (Σ τ · DF)`` — the fixed rate
    that makes a par swap have zero value.

    Args:
        discount_factors: Discount factor per maturity (descending in (0, 1]).
        maturities: Maturities in years, ascending.
        frequency: Fixed-leg payment frequency per year.

    Returns:
        Dict with ``swap_rates`` per maturity.

    Raises:
        ValueError: If arrays differ in length.
    """
    df = np.asarray(discount_factors, dtype=np.float64)
    t = np.asarray(maturities, dtype=np.float64)
    if df.size != t.size:
        raise ValueError("discount_factors and maturities must match length")

    tau = 1.0 / frequency
    swap_rates = []
    annuity = 0.0
    for i in range(df.size):
        annuity += tau * df[i]
        rate = (1.0 - df[i]) / annuity if annuity > 0 else 0.0
        swap_rates.append(round(float(rate), 10))
    return {"swap_rates": swap_rates}


def ois_curve_sonia_sofr(
    ois_rates: np.ndarray,
    maturities: np.ndarray,
    frequency: int = 1,
) -> dict:  # type: ignore[type-arg]
    """Build an OIS (SONIA/SOFR) discount curve from quoted OIS swap rates.

    OIS swaps pay annually against compounded overnight; the discount curve is
    bootstrapped exactly as for par swaps (single-curve OIS-discounting).

    Args:
        ois_rates: Quoted OIS rate per maturity (decimal).
        maturities: Maturities in years, ascending.
        frequency: Fixed-leg payment frequency per year.

    Returns:
        Dict with ``discount_factors`` and continuous ``zero_rates``.

    Raises:
        ValueError: If arrays differ in length.
    """
    rates = np.asarray(ois_rates, dtype=np.float64)
    t = np.asarray(maturities, dtype=np.float64)
    if rates.size != t.size:
        raise ValueError("ois_rates and maturities must match length")

    tau = 1.0 / frequency
    n = rates.size
    dfs = np.zeros(n, dtype=np.float64)
    annuity = 0.0
    for i in range(n):
        # rate_i * tau * (annuity + tau*DF_i) + DF_i = 1  =>  solve for DF_i
        dfs[i] = (1.0 - rates[i] * annuity) / (1.0 + rates[i] * tau)
        annuity += tau * dfs[i]
    zero_rates = -np.log(dfs) / t
    return {
        "discount_factors": [round(float(d), 10) for d in dfs],
        "zero_rates": [round(float(z), 10) for z in zero_rates],
    }


def forward_rate_agreement_fra(
    notional: float,
    fra_rate: float,
    forward_rate: float,
    start: float,
    end: float,
    discount_factor: float,
) -> dict:  # type: ignore[type-arg]
    """Mark-to-market value of a forward rate agreement (long = pay fixed).

    ``Value = notional · (forward − fra_rate) · accrual · DF(end)``. Zero value
    when the contracted FRA rate equals the projected forward.

    Args:
        notional: Contract notional.
        fra_rate: Contracted (fixed) FRA rate (decimal).
        forward_rate: Projected forward rate over [start, end] (decimal).
        start: Accrual start in years.
        end: Accrual end in years (> start).
        discount_factor: Discount factor to the settlement (end) date.

    Returns:
        Dict with ``value`` and the ``accrual`` fraction.

    Raises:
        ValueError: If ``end <= start``.
    """
    if end <= start:
        raise ValueError("end must exceed start")
    accrual = end - start
    value = notional * (forward_rate - fra_rate) * accrual * discount_factor
    return {"value": round(float(value), 6), "accrual": round(float(accrual), 8)}


def interest_rate_swap_irs_pricer(
    notional: float,
    fixed_rate: float,
    forward_rates: np.ndarray,
    discount_factors: np.ndarray,
    accruals: np.ndarray,
    pay_fixed: bool = True,
) -> dict:  # type: ignore[type-arg]
    """Price a vanilla fixed-vs-float interest-rate swap.

    Float leg PV = ``notional · Σ fwd_i · τ_i · DF_i``; fixed leg PV =
    ``notional · fixed · Σ τ_i · DF_i``. Swap value to the payer is
    ``float − fixed``. The par (break-even) fixed rate is also returned.

    Args:
        notional: Swap notional.
        fixed_rate: Fixed-leg rate (decimal).
        forward_rates: Projected float index rate per period (decimal).
        discount_factors: Discount factor per payment date.
        accruals: Year-fraction per period.
        pay_fixed: True for payer swap (long float), False for receiver.

    Returns:
        Dict with ``value``, ``par_rate``, ``annuity``, leg PVs.

    Raises:
        ValueError: If array lengths are inconsistent.
    """
    fwd = np.asarray(forward_rates, dtype=np.float64)
    df = np.asarray(discount_factors, dtype=np.float64)
    tau = np.asarray(accruals, dtype=np.float64)
    if not (fwd.size == df.size == tau.size):
        raise ValueError("forward_rates, discount_factors, accruals must match length")

    annuity = float(np.sum(tau * df))
    float_pv = notional * float(np.sum(fwd * tau * df))
    fixed_pv = notional * fixed_rate * annuity
    value = (float_pv - fixed_pv) if pay_fixed else (fixed_pv - float_pv)
    par_rate = float_pv / (notional * annuity) if annuity > 0 else 0.0
    return {
        "value": round(float(value), 6),
        "par_rate": round(float(par_rate), 10),
        "annuity": round(float(annuity), 10),
        "float_pv": round(float(float_pv), 6),
        "fixed_pv": round(float(fixed_pv), 6),
    }

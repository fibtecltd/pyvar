"""engine/deriv_rates.py — Swaps & rate-option pricers (Derivatives & Pricing).

Cross-currency swap, overnight index swap, total return swap, credit default
swap, equity swap, Black caplet/floorlet, cap/floor, Black swaption and a
SABR-vol swaption.

Light vectorised NumPy / SciPy normal-CDF computations done in pure-Python
wrappers (CLAUDE.md §3.1 satisfied trivially — no JIT regions).
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats

from engine.deriv_stoch_vol import sabr_volatility_model

__all__ = [
    "cross_currency_swap_pricer",
    "overnight_index_swap_ois",
    "total_return_swap_trs",
    "credit_default_swap_cds_pricer",
    "equity_swap_pricer",
    "caplet_floorlet_pricer_black",
    "cap_floor_pricer",
    "swaption_pricer_black",
    "swaption_pricer_sabr",
]


def cross_currency_swap_pricer(
    notional_dom: float,
    notional_for: float,
    fixed_rate_dom: float,
    fixed_rate_for: float,
    df_dom: np.ndarray,
    df_for: np.ndarray,
    accruals: np.ndarray,
    fx_spot: float,
    pay_domestic: bool = True,
) -> dict:  # type: ignore[type-arg]
    """Price a fixed-fixed cross-currency swap (with notional exchange).

    Values each leg in its own currency (coupons + final notional), converts the
    foreign leg at the FX spot, and nets. Pay-domestic = pay the domestic leg,
    receive the foreign leg.

    Args:
        notional_dom: Domestic notional.
        notional_for: Foreign notional.
        fixed_rate_dom: Domestic fixed rate (decimal).
        fixed_rate_for: Foreign fixed rate (decimal).
        df_dom: Domestic discount factors per payment date.
        df_for: Foreign discount factors per payment date.
        accruals: Year-fraction per period (shared schedule).
        fx_spot: Spot FX (domestic per 1 unit foreign).
        pay_domestic: Direction flag.

    Returns:
        Dict with ``value`` (domestic ccy), ``pv_domestic_leg``,
        ``pv_foreign_leg``.

    Raises:
        ValueError: If array lengths are inconsistent.
    """
    dd = np.asarray(df_dom, dtype=np.float64)
    fd = np.asarray(df_for, dtype=np.float64)
    tau = np.asarray(accruals, dtype=np.float64)
    if not (dd.size == fd.size == tau.size):
        raise ValueError("df_dom, df_for, accruals must match length")

    pv_dom = notional_dom * (fixed_rate_dom * float(np.sum(tau * dd)) + dd[-1])
    pv_for = notional_for * (fixed_rate_for * float(np.sum(tau * fd)) + fd[-1])
    pv_for_in_dom = pv_for * fx_spot
    value = (pv_for_in_dom - pv_dom) if pay_domestic else (pv_dom - pv_for_in_dom)
    return {
        "value": round(float(value), 6),
        "pv_domestic_leg": round(float(pv_dom), 6),
        "pv_foreign_leg": round(float(pv_for_in_dom), 6),
    }


def overnight_index_swap_ois(
    notional: float,
    fixed_rate: float,
    compounded_rate: float,
    accrual: float,
    discount_factor: float,
    pay_fixed: bool = True,
) -> dict:  # type: ignore[type-arg]
    """Value a single-period overnight index swap.

    Net cashflow = ``notional · (compounded_overnight − fixed) · accrual``,
    discounted. Zero value when the compounded rate equals the fixed rate.

    Args:
        notional: Swap notional.
        fixed_rate: Fixed OIS rate (decimal).
        compounded_rate: Realised/projected compounded overnight rate (decimal).
        accrual: Year-fraction of the period.
        discount_factor: Discount factor to payment.
        pay_fixed: True if paying fixed (receiving floating).

    Returns:
        Dict with ``value``.

    Raises:
        ValueError: If ``accrual`` is non-positive.
    """
    if accrual <= 0:
        raise ValueError("accrual must be positive")
    net = notional * (compounded_rate - fixed_rate) * accrual * discount_factor
    value = net if pay_fixed else -net
    return {"value": round(float(value), 6)}


def total_return_swap_trs(
    notional: float,
    asset_return: float,
    financing_rate: float,
    accrual: float,
    discount_factor: float,
    receive_total_return: bool = True,
) -> dict:  # type: ignore[type-arg]
    """Value a total-return swap leg.

    The total-return receiver gets the asset's total return and pays a financing
    rate (e.g. SOFR + spread): ``notional · (asset_return − financing·τ) · DF``.

    Args:
        notional: Reference notional.
        asset_return: Period total return of the reference asset (decimal).
        financing_rate: Financing rate (decimal, annual).
        accrual: Year-fraction.
        discount_factor: Discount factor to payment.
        receive_total_return: Direction flag.

    Returns:
        Dict with ``value``.

    Raises:
        ValueError: If ``accrual`` is non-positive.
    """
    if accrual <= 0:
        raise ValueError("accrual must be positive")
    net = notional * (asset_return - financing_rate * accrual) * discount_factor
    value = net if receive_total_return else -net
    return {"value": round(float(value), 6)}


def credit_default_swap_cds_pricer(
    notional: float,
    spread: float,
    hazard_rate: float,
    recovery_rate: float,
    maturity: float,
    discount_rate: float,
    frequency: int = 4,
) -> dict:  # type: ignore[type-arg]
    """Price a CDS via a flat-hazard-rate reduced-form model.

    Premium leg = ``spread · Σ τ · DF · Q``; protection leg =
    ``(1−R) · Σ DF · (Q_{i−1} − Q_i)`` with survival ``Q(t)=e^{−λt}``. The par
    spread zeroes the swap value.

    Args:
        notional: CDS notional.
        spread: Contractual spread (decimal, annual).
        hazard_rate: Constant hazard rate λ (decimal).
        recovery_rate: Recovery rate R in [0, 1).
        maturity: CDS maturity in years.
        discount_rate: Flat continuous discount rate.
        frequency: Premium payment frequency per year.

    Returns:
        Dict with ``value`` (to protection buyer), ``premium_leg``,
        ``protection_leg``, ``par_spread``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if maturity <= 0 or frequency < 1:
        raise ValueError("maturity > 0 and frequency >= 1 required")
    if not 0.0 <= recovery_rate < 1.0:
        raise ValueError("recovery_rate must be in [0, 1)")

    n = max(int(round(maturity * frequency)), 1)
    times = np.array([(i + 1) / frequency for i in range(n)], dtype=np.float64)
    tau = 1.0 / frequency
    df = np.exp(-discount_rate * times)
    surv = np.exp(-hazard_rate * times)
    surv_prev: np.ndarray = np.concatenate((np.array([1.0], dtype=np.float64), surv[:-1]))

    premium_leg = spread * tau * float(np.sum(df * surv)) * notional
    protection_leg = (1.0 - recovery_rate) * float(np.sum(df * (surv_prev - surv))) * notional
    annuity = tau * float(np.sum(df * surv))
    par_spread = (
        (1.0 - recovery_rate) * float(np.sum(df * (surv_prev - surv))) / annuity
        if annuity > 0
        else 0.0
    )
    value = protection_leg - premium_leg  # buyer of protection
    return {
        "value": round(float(value), 6),
        "premium_leg": round(float(premium_leg), 6),
        "protection_leg": round(float(protection_leg), 6),
        "par_spread": round(float(par_spread), 10),
    }


def equity_swap_pricer(
    notional: float,
    equity_return: float,
    funding_rate: float,
    accrual: float,
    discount_factor: float,
    receive_equity: bool = True,
) -> dict:  # type: ignore[type-arg]
    """Value an equity swap leg (equity return vs funding).

    ``notional · (equity_return − funding·τ) · DF`` to the equity receiver.

    Args:
        notional: Reference notional.
        equity_return: Period equity total return (decimal).
        funding_rate: Funding rate (decimal, annual).
        accrual: Year-fraction.
        discount_factor: Discount factor to payment.
        receive_equity: Direction flag.

    Returns:
        Dict with ``value``.

    Raises:
        ValueError: If ``accrual`` is non-positive.
    """
    if accrual <= 0:
        raise ValueError("accrual must be positive")
    net = notional * (equity_return - funding_rate * accrual) * discount_factor
    value = net if receive_equity else -net
    return {"value": round(float(value), 6)}


def _black_option(
    forward: float, strike: float, vol: float, tau: float, df: float, is_call: bool
) -> float:
    """Black-76 undiscounted-forward option value times discount factor."""
    if vol <= 0 or tau <= 0:
        intrinsic = max(forward - strike, 0.0) if is_call else max(strike - forward, 0.0)
        return df * intrinsic
    sqrt_t = math.sqrt(tau)
    d1 = (math.log(forward / strike) + 0.5 * vol * vol * tau) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    if is_call:
        return df * (forward * float(stats.norm.cdf(d1)) - strike * float(stats.norm.cdf(d2)))
    return df * (strike * float(stats.norm.cdf(-d2)) - forward * float(stats.norm.cdf(-d1)))


def caplet_floorlet_pricer_black(
    notional: float,
    forward_rate: float,
    strike: float,
    vol: float,
    expiry: float,
    accrual: float,
    discount_factor: float,
    option_type: str = "caplet",
) -> dict:  # type: ignore[type-arg]
    """Price a single caplet/floorlet under the Black (lognormal) model.

    A caplet is a call on the forward rate; a floorlet is a put. Caplet +
    floorlet (same strike) replicate a payer FRA (put-call parity).

    Args:
        notional: Notional.
        forward_rate: Forward LIBOR/index rate (decimal).
        strike: Cap/floor strike (decimal).
        vol: Black volatility of the forward rate.
        expiry: Time to caplet fixing (years).
        accrual: Year-fraction of the accrual period.
        discount_factor: Discount factor to payment.
        option_type: ``"caplet"`` or ``"floorlet"``.

    Returns:
        Dict with ``price``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("caplet", "floorlet"):
        raise ValueError("option_type must be 'caplet' or 'floorlet'")
    if forward_rate <= 0 or strike <= 0:
        raise ValueError("forward_rate and strike must be positive")
    price = (
        notional
        * accrual
        * _black_option(forward_rate, strike, vol, expiry, discount_factor, option_type == "caplet")
    )
    return {"price": round(float(price), 6)}


def cap_floor_pricer(
    notional: float,
    forward_rates: np.ndarray,
    strike: float,
    vols: np.ndarray,
    expiries: np.ndarray,
    accruals: np.ndarray,
    discount_factors: np.ndarray,
    option_type: str = "cap",
) -> dict:  # type: ignore[type-arg]
    """Price an interest-rate cap/floor as a strip of caplets/floorlets.

    Args:
        notional: Notional.
        forward_rates: Forward rate per caplet period.
        strike: Common strike (decimal).
        vols: Black vol per caplet.
        expiries: Fixing time per caplet (years).
        accruals: Year-fraction per period.
        discount_factors: Discount factor per payment date.
        option_type: ``"cap"`` or ``"floor"``.

    Returns:
        Dict with ``price`` and per-caplet ``caplet_prices``.

    Raises:
        ValueError: If array lengths mismatch or type invalid.
    """
    if option_type not in ("cap", "floor"):
        raise ValueError("option_type must be 'cap' or 'floor'")
    fwd = np.asarray(forward_rates, dtype=np.float64)
    v = np.asarray(vols, dtype=np.float64)
    exp = np.asarray(expiries, dtype=np.float64)
    tau = np.asarray(accruals, dtype=np.float64)
    df = np.asarray(discount_factors, dtype=np.float64)
    if not (fwd.size == v.size == exp.size == tau.size == df.size):
        raise ValueError("all input arrays must match length")

    leg = "caplet" if option_type == "cap" else "floorlet"
    prices = [
        caplet_floorlet_pricer_black(
            notional,
            float(fwd[i]),
            strike,
            float(v[i]),
            float(exp[i]),
            float(tau[i]),
            float(df[i]),
            leg,
        )["price"]
        for i in range(fwd.size)
    ]
    return {"price": round(float(sum(prices)), 6), "caplet_prices": prices}


def swaption_pricer_black(
    notional: float,
    forward_swap_rate: float,
    strike: float,
    vol: float,
    expiry: float,
    annuity: float,
    option_type: str = "payer",
) -> dict:  # type: ignore[type-arg]
    """Price a European swaption under the Black model.

    ``Price = annuity · Black(forward_swap_rate, strike, vol, expiry)``. A payer
    swaption is a call on the swap rate; a receiver swaption is a put.

    Args:
        notional: Swap notional.
        forward_swap_rate: Forward par swap rate (decimal).
        strike: Strike swap rate (decimal).
        vol: Black volatility of the swap rate.
        expiry: Time to swaption expiry (years).
        annuity: PV of a 1-unit fixed annuity (level / PVBP).
        option_type: ``"payer"`` or ``"receiver"``.

    Returns:
        Dict with ``price``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("payer", "receiver"):
        raise ValueError("option_type must be 'payer' or 'receiver'")
    if forward_swap_rate <= 0 or strike <= 0:
        raise ValueError("forward_swap_rate and strike must be positive")
    price = (
        notional
        * annuity
        * _black_option(forward_swap_rate, strike, vol, expiry, 1.0, option_type == "payer")
    )
    return {"price": round(float(price), 6)}


def swaption_pricer_sabr(
    notional: float,
    forward_swap_rate: float,
    strike: float,
    expiry: float,
    annuity: float,
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
    option_type: str = "payer",
) -> dict:  # type: ignore[type-arg]
    """Price a swaption using a SABR-implied Black volatility.

    Computes the SABR lognormal vol for the (forward, strike, expiry) point via
    Hagan's expansion, then plugs it into the Black swaption formula.

    Args:
        notional: Swap notional.
        forward_swap_rate: Forward par swap rate (decimal).
        strike: Strike swap rate (decimal).
        expiry: Time to expiry (years).
        annuity: PV of a 1-unit fixed annuity.
        alpha: SABR initial vol level.
        beta: SABR CEV exponent in [0, 1].
        rho: SABR correlation.
        nu: SABR vol-of-vol.
        option_type: ``"payer"`` or ``"receiver"``.

    Returns:
        Dict with ``price`` and the ``sabr_vol`` used.

    Raises:
        ValueError: If inputs are invalid.
    """
    sabr_vol = sabr_volatility_model(forward_swap_rate, strike, expiry, alpha, beta, rho, nu)[
        "implied_vol"
    ]
    res = swaption_pricer_black(
        notional, forward_swap_rate, strike, sabr_vol, expiry, annuity, option_type
    )
    return {"price": res["price"], "sabr_vol": round(float(sabr_vol), 8)}

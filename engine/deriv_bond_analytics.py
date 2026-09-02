"""engine/deriv_bond_analytics.py — Bond risk analytics (Derivatives & Pricing).

Macaulay/modified/effective duration, convexity, DV01/PVBP, yield-to-maturity,
yield-to-call, asset-swap spread, Z-spread and OAS.

These are light vectorised NumPy / SciPy-root-finding computations done in pure
Python wrappers — no @njit kernel is needed (CLAUDE.md §3.1 is satisfied
trivially as there are no JIT regions to constrain).
"""

from __future__ import annotations

import numpy as np
from scipy import optimize

__all__ = [
    "duration_macaulay",
    "modified_duration",
    "effective_duration",
    "convexity",
    "dv01_pvbp",
    "yield_to_maturity",
    "yield_to_call",
    "asset_swap_spread",
    "z_spread_calculator",
    "oas_option_adjusted_spread",
]


def _price_from_yield(
    cashflows: np.ndarray, times: np.ndarray, yield_rate: float, frequency: int
) -> float:
    """PV of cashflows at a flat periodic yield."""
    discount = (1.0 + yield_rate / frequency) ** (-(times * frequency))
    return float(np.sum(cashflows * discount))


def duration_macaulay(
    cashflows: np.ndarray,
    times: np.ndarray,
    yield_rate: float,
    frequency: int = 2,
) -> dict:  # type: ignore[type-arg]
    """Macaulay duration — PV-weighted average time to cashflows (in years).

    Args:
        cashflows: Cashflow amounts.
        times: Cashflow times in years.
        yield_rate: Annual yield (decimal).
        frequency: Compounding frequency per year.

    Returns:
        Dict with ``macaulay_duration`` and the ``price``.

    Raises:
        ValueError: If arrays differ in length.
    """
    cf = np.asarray(cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    if cf.size != t.size:
        raise ValueError("cashflows and times must match length")

    discount = (1.0 + yield_rate / frequency) ** (-(t * frequency))
    pv = cf * discount
    price = float(np.sum(pv))
    duration = float(np.sum(t * pv) / price) if price != 0 else 0.0
    return {"macaulay_duration": round(duration, 8), "price": round(price, 6)}


def modified_duration(
    cashflows: np.ndarray,
    times: np.ndarray,
    yield_rate: float,
    frequency: int = 2,
) -> dict:  # type: ignore[type-arg]
    """Modified duration = Macaulay duration / (1 + y/m).

    Approximates the percentage price change for a 1-unit yield move:
    ``ΔP/P ≈ −D_mod · Δy``.

    Args:
        cashflows: Cashflow amounts.
        times: Cashflow times in years.
        yield_rate: Annual yield (decimal).
        frequency: Compounding frequency per year.

    Returns:
        Dict with ``modified_duration``, ``macaulay_duration``, ``price``.

    Raises:
        ValueError: If arrays differ in length.
    """
    mac = duration_macaulay(cashflows, times, yield_rate, frequency)
    mod = mac["macaulay_duration"] / (1.0 + yield_rate / frequency)
    return {
        "modified_duration": round(float(mod), 8),
        "macaulay_duration": mac["macaulay_duration"],
        "price": mac["price"],
    }


def effective_duration(
    price_base: float,
    price_up: float,
    price_down: float,
    yield_shock: float,
) -> dict:  # type: ignore[type-arg]
    """Effective duration from re-priced bond values under a parallel shock.

    ``D_eff = (P− − P+) / (2 · P0 · Δy)`` — model-agnostic, so it captures
    embedded optionality (callable/puttable) that analytic duration misses.

    Args:
        price_base: Price at the base yield.
        price_up: Price after +``yield_shock``.
        price_down: Price after −``yield_shock``.
        yield_shock: Size of the parallel yield shock (decimal).

    Returns:
        Dict with ``effective_duration``.

    Raises:
        ValueError: If ``price_base`` or ``yield_shock`` is non-positive.
    """
    if price_base <= 0 or yield_shock <= 0:
        raise ValueError("price_base and yield_shock must be positive")
    eff = (price_down - price_up) / (2.0 * price_base * yield_shock)
    return {"effective_duration": round(float(eff), 8)}


def convexity(
    cashflows: np.ndarray,
    times: np.ndarray,
    yield_rate: float,
    frequency: int = 2,
) -> dict:  # type: ignore[type-arg]
    """Bond convexity — the second-order yield sensitivity (always >= 0 for
    option-free bonds).

    ``C = Σ cf_k · t_k(t_k + 1/m) · (1+y/m)^{-(m t_k + 2)} / P``.

    Args:
        cashflows: Cashflow amounts.
        times: Cashflow times in years.
        yield_rate: Annual yield (decimal).
        frequency: Compounding frequency per year.

    Returns:
        Dict with ``convexity`` and ``price``.

    Raises:
        ValueError: If arrays differ in length.
    """
    cf = np.asarray(cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    if cf.size != t.size:
        raise ValueError("cashflows and times must match length")

    m = frequency
    periods = t * m
    discount = (1.0 + yield_rate / m) ** (-periods)
    price = float(np.sum(cf * discount))
    weight = cf * periods * (periods + 1.0) * (1.0 + yield_rate / m) ** (-(periods + 2.0))
    conv = float(np.sum(weight) / (price * m * m)) if price != 0 else 0.0
    return {"convexity": round(conv, 8), "price": round(price, 6)}


def dv01_pvbp(
    cashflows: np.ndarray,
    times: np.ndarray,
    yield_rate: float,
    frequency: int = 2,
) -> dict:  # type: ignore[type-arg]
    """DV01 / PVBP — price change for a 1 basis-point yield move.

    Computed by central difference of the price function at ±0.5bp.

    Args:
        cashflows: Cashflow amounts.
        times: Cashflow times in years.
        yield_rate: Annual yield (decimal).
        frequency: Compounding frequency per year.

    Returns:
        Dict with ``dv01`` (positive magnitude) and ``price``.

    Raises:
        ValueError: If arrays differ in length.
    """
    cf = np.asarray(cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    if cf.size != t.size:
        raise ValueError("cashflows and times must match length")

    bp = 1e-4
    price = _price_from_yield(cf, t, yield_rate, frequency)
    p_up = _price_from_yield(cf, t, yield_rate + 0.5 * bp, frequency)
    p_dn = _price_from_yield(cf, t, yield_rate - 0.5 * bp, frequency)
    dv01 = p_dn - p_up  # price drop per +1bp, reported positive
    return {"dv01": round(float(dv01), 8), "price": round(price, 6)}


def yield_to_maturity(
    price: float,
    cashflows: np.ndarray,
    times: np.ndarray,
    frequency: int = 2,
) -> dict:  # type: ignore[type-arg]
    """Yield to maturity — the flat rate that discounts cashflows to ``price``.

    Solved by Brent root-finding. Recovers the input yield exactly when ``price``
    was produced by :func:`engine.deriv_bonds.bond_pricer_fixed_coupon`.

    Args:
        price: Observed dirty price.
        cashflows: Cashflow amounts.
        times: Cashflow times in years.
        frequency: Compounding frequency per year.

    Returns:
        Dict with ``ytm``.

    Raises:
        ValueError: If arrays differ or no root is bracketed.
    """
    cf = np.asarray(cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    if cf.size != t.size:
        raise ValueError("cashflows and times must match length")

    def f(y: float) -> float:
        return _price_from_yield(cf, t, y, frequency) - price

    try:
        ytm = optimize.brentq(f, -0.5, 2.0, maxiter=200, xtol=1e-12)
    except ValueError as exc:
        raise ValueError("could not bracket a yield root") from exc
    return {"ytm": round(float(ytm), 10)}


def yield_to_call(
    price: float,
    face_value: float,
    coupon_rate: float,
    call_price: float,
    call_date: float,
    frequency: int = 2,
) -> dict:  # type: ignore[type-arg]
    """Yield to call — yield assuming redemption at the first call date.

    Builds the cashflow stream truncated at ``call_date`` with redemption at
    ``call_price`` and solves for the yield.

    Args:
        price: Observed dirty price.
        face_value: Par value (for coupon sizing).
        coupon_rate: Annual coupon rate (decimal).
        call_price: Redemption price at the call date.
        call_date: Time to the call date in years.
        frequency: Coupon payments per year.

    Returns:
        Dict with ``ytc``.

    Raises:
        ValueError: If ``call_date`` is non-positive.
    """
    if call_date <= 0 or frequency < 1:
        raise ValueError("call_date must be > 0 and frequency >= 1")
    n = max(int(round(call_date * frequency)), 1)
    times = np.array([(i + 1) / frequency for i in range(n)], dtype=np.float64)
    coupon = face_value * coupon_rate / frequency
    cashflows = np.full(n, coupon, dtype=np.float64)
    cashflows[-1] += call_price
    res = yield_to_maturity(price, cashflows, times, frequency)
    return {"ytc": res["ytm"]}


def z_spread_calculator(
    price: float,
    cashflows: np.ndarray,
    times: np.ndarray,
    zero_rates: np.ndarray,
    frequency: int = 2,
) -> dict:  # type: ignore[type-arg]
    """Z-spread — constant spread over the zero curve that reprices the bond.

    Solves for ``z`` such that ``Σ cf_k (1 + (zero_k + z)/m)^{-m t_k} = price``.

    Args:
        price: Observed dirty price.
        cashflows: Cashflow amounts.
        times: Cashflow times in years.
        zero_rates: Zero (spot) rate per cashflow (decimal, annualised).
        frequency: Compounding frequency per year.

    Returns:
        Dict with ``z_spread`` (decimal) and ``z_spread_bps``.

    Raises:
        ValueError: If array lengths are inconsistent.
    """
    cf = np.asarray(cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    z0 = np.asarray(zero_rates, dtype=np.float64)
    if not (cf.size == t.size == z0.size):
        raise ValueError("cashflows, times, zero_rates must match length")

    def f(z: float) -> float:
        df = (1.0 + (z0 + z) / frequency) ** (-(t * frequency))
        return float(np.sum(cf * df)) - price

    spread = optimize.brentq(f, -0.5, 2.0, maxiter=200, xtol=1e-12)
    return {"z_spread": round(float(spread), 10), "z_spread_bps": round(float(spread) * 1e4, 4)}


def asset_swap_spread(
    bond_price: float,
    cashflows: np.ndarray,
    times: np.ndarray,
    swap_rates: np.ndarray,
    face_value: float = 100.0,
    frequency: int = 2,
    use_market_price: bool = False,
) -> dict:  # type: ignore[type-arg]
    """Par-par asset-swap spread.

    The spread equating the bond's net present value to an annuity of the
    swap's fixed-leg PV01: ``ASW = (PV_bond − reference_price) / annuity``,
    expressed in basis points.

    By default (``use_market_price=False``), ``reference_price`` is
    ``face_value`` (par) — this reproduces the function's original,
    par-referenced behaviour exactly and is unchanged for any existing
    caller. Set ``use_market_price=True`` to use the bond's actual dirty
    price instead, matching the standard market convention (O'Kane, 2000,
    "Introduction to Asset Swaps", Lehman Brothers): the spread is only
    equal to the par-referenced figure when the bond happens to trade at
    par, so for any bond away from par the market-convention spread and
    the par-referenced spread differ.

    Args:
        bond_price: Bond dirty price. Used as the reference price only when
            ``use_market_price=True``; otherwise accepted but ignored (the
            default preserves this function's original par-referenced
            behaviour).
        cashflows: Bond cashflows.
        times: Cashflow times (years).
        swap_rates: Per-period swap zero rate (decimal).
        face_value: Par value. Used as the reference price when
            ``use_market_price=False`` (the default).
        frequency: Payment frequency per year.
        use_market_price: If True, use ``bond_price`` (the actual dirty
            price) as the reference price instead of ``face_value``. Default
            False preserves prior behaviour exactly.

    Returns:
        Dict with ``asset_swap_spread`` (decimal) and ``..._bps``.

    Raises:
        ValueError: If arrays differ in length.
    """
    cf = np.asarray(cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    sr = np.asarray(swap_rates, dtype=np.float64)
    if not (cf.size == t.size == sr.size):
        raise ValueError("cashflows, times, swap_rates must match length")

    df = (1.0 + sr / frequency) ** (-(t * frequency))
    pv_bond = float(np.sum(cf * df))
    annuity = float(np.sum(df)) / frequency  # PV of 1 per annum
    reference_price = bond_price if use_market_price else face_value
    asw = (pv_bond - reference_price) / (annuity * face_value)
    return {
        "asset_swap_spread": round(float(asw), 10),
        "asset_swap_spread_bps": round(float(asw) * 1e4, 4),
    }


def oas_option_adjusted_spread(
    market_price: float,
    face_value: float,
    coupon_rate: float,
    short_rate: float,
    rate_vol: float,
    maturity: float,
    call_price: float,
    frequency: int = 1,
) -> dict:  # type: ignore[type-arg]
    """Option-adjusted spread of a callable bond.

    Finds the constant spread added to the short rate on the pricing tree that
    reprices the callable bond to its market price — stripping out the embedded
    option so spreads are comparable across bonds.

    Note: the spread is root-found (Brent's method) against
    ``callable_bond_pricer``'s tree price rather than expressed in closed
    form — the equation above is the condition the solver satisfies, not an
    explicit OAS formula.

    Args:
        market_price: Observed market price of the callable bond.
        face_value: Par value.
        coupon_rate: Annual coupon rate (decimal).
        short_rate: Current short rate (continuous, annual).
        rate_vol: Short-rate volatility.
        maturity: Time to maturity in years.
        call_price: Issuer call strike (per face).
        frequency: Coupon payments / tree steps per year.

    Returns:
        Dict with ``oas`` (decimal) and ``oas_bps``.

    Raises:
        ValueError: If inputs are invalid.
    """
    from engine.deriv_bonds import callable_bond_pricer

    if maturity <= 0 or frequency < 1:
        raise ValueError("maturity must be > 0 and frequency >= 1")

    def f(s: float) -> float:
        p = callable_bond_pricer(
            face_value, coupon_rate, short_rate + s, rate_vol, maturity, call_price, frequency
        )["price"]
        return float(p) - market_price

    oas = optimize.brentq(f, -0.2, 0.5, maxiter=200, xtol=1e-10)
    return {"oas": round(float(oas), 10), "oas_bps": round(float(oas) * 1e4, 4)}

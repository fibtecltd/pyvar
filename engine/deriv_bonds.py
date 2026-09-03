"""engine/deriv_bonds.py — Bond instrument pricers (Derivatives & Pricing).

Fixed-coupon, floating-rate, zero-coupon, inflation-linked, callable, puttable
and convertible bond pricers. Callable/puttable use a backward-induction
short-rate (Black-Derman-Toy-style binomial) tree on the issuer/holder option.

Numba rules (CLAUDE.md §3.1): the callable/puttable backward-induction tree is a
stateless @njit(cache=True) kernel operating on float64 arrays; cashflow
discounting elsewhere is vectorised NumPy in the pure-Python wrappers.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

__all__ = [
    "bond_pricer_fixed_coupon",
    "bond_pricer_floating_rate",
    "zero_coupon_bond_pricer",
    "inflation_linked_bond_pricer",
    "callable_bond_pricer",
    "puttable_bond_pricer",
    "convertible_bond_pricer",
]


def _coupon_schedule(maturity: float, frequency: int) -> np.ndarray:
    """Coupon payment times in years (ascending), last == maturity."""
    n = int(round(maturity * frequency))
    if n < 1:
        n = 1
    return np.array([(i + 1) / frequency for i in range(n)], dtype=np.float64)


def bond_pricer_fixed_coupon(
    face_value: float,
    coupon_rate: float,
    yield_rate: float,
    maturity: float,
    frequency: int = 2,
) -> dict:  # type: ignore[type-arg]
    """Price a fixed-coupon bond by discounting its cashflows at a flat yield.

    Price falls as yield rises (inverse relationship), and equals par when the
    coupon rate equals the yield.

    Args:
        face_value: Redemption (par) value.
        coupon_rate: Annual coupon rate (decimal).
        yield_rate: Annual yield to maturity (decimal, compounded ``frequency``).
        maturity: Time to maturity in years.
        frequency: Coupon payments per year.

    Returns:
        Dict with ``price``, ``clean_price`` and per-period ``cashflows``.

    Raises:
        ValueError: If maturity or frequency is non-positive.
    """
    if maturity <= 0 or frequency < 1:
        raise ValueError("maturity must be > 0 and frequency >= 1")

    times = _coupon_schedule(maturity, frequency)
    coupon = face_value * coupon_rate / frequency
    periodic_yield = yield_rate / frequency
    periods = times * frequency
    discount = (1.0 + periodic_yield) ** (-periods)
    cashflows = np.full(times.size, coupon, dtype=np.float64)
    cashflows[-1] += face_value
    price = float(np.sum(cashflows * discount))
    return {
        "price": round(price, 6),
        "clean_price": round(price, 6),
        "cashflows": cashflows.tolist(),
    }


def bond_pricer_floating_rate(
    face_value: float,
    reference_rates: np.ndarray,
    spread: float,
    discount_rates: np.ndarray,
    maturity: float,
    frequency: int = 4,
) -> dict:  # type: ignore[type-arg]
    """Price a floating-rate note (FRN) from projected forward rates.

    Each coupon is ``(reference_rate + spread) / frequency · face``. On a reset
    date with discount rates equal to the reference rates, an FRN prices near
    par plus the PV of the spread.

    The coupon schedule actually priced is derived from
    ``len(reference_rates)`` (``discount_rates`` must match that length).
    ``maturity`` must be consistent with ``len(reference_rates) / frequency``
    — a caller-supplied ``maturity`` that implies a different number of
    periods is rejected rather than silently ignored.

    Args:
        face_value: Redemption (par) value.
        reference_rates: Projected forward index rate per period (decimal).
            Its length sets the number of coupon periods priced.
        spread: Quoted margin over the index (decimal).
        discount_rates: Per-period zero discount rate (decimal, annualised).
        maturity: Time to maturity in years. Must equal
            ``len(reference_rates) / frequency`` (see note above).
        frequency: Coupon payments per year.

    Returns:
        Dict with ``price`` and ``cashflows``.

    Raises:
        ValueError: If array lengths are inconsistent, or if ``maturity``
            is inconsistent with ``len(reference_rates) / frequency``.
    """
    if maturity <= 0 or frequency < 1:
        raise ValueError("maturity must be > 0 and frequency >= 1")
    ref = np.asarray(reference_rates, dtype=np.float64)
    disc_r = np.asarray(discount_rates, dtype=np.float64)
    if ref.size != disc_r.size:
        raise ValueError("reference_rates and discount_rates must match length")

    n = ref.size
    implied_maturity = n / frequency
    if not math.isclose(maturity, implied_maturity, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError(
            f"maturity ({maturity}) is inconsistent with "
            f"len(reference_rates)/frequency ({implied_maturity}): "
            f"reference_rates has {n} periods at frequency={frequency}"
        )
    times = np.array([(i + 1) / frequency for i in range(n)], dtype=np.float64)
    coupons = face_value * (ref + spread) / frequency
    cashflows = coupons.copy()
    cashflows[-1] += face_value
    discount = (1.0 + disc_r / frequency) ** (-(times * frequency))
    price = float(np.sum(cashflows * discount))
    return {"price": round(price, 6), "cashflows": cashflows.tolist()}


def zero_coupon_bond_pricer(
    face_value: float,
    yield_rate: float,
    maturity: float,
    frequency: int = 2,
) -> dict:  # type: ignore[type-arg]
    """Price a zero-coupon bond: ``face / (1 + y/m)^{m·T}``.

    Args:
        face_value: Redemption (par) value.
        yield_rate: Annual yield (decimal).
        maturity: Time to maturity in years.
        frequency: Compounding frequency per year.

    Returns:
        Dict with ``price`` and the ``discount_factor``.

    Raises:
        ValueError: If maturity or frequency is non-positive.
    """
    if maturity <= 0 or frequency < 1:
        raise ValueError("maturity must be > 0 and frequency >= 1")
    df = (1.0 + yield_rate / frequency) ** (-(maturity * frequency))
    price = face_value * df
    return {"price": round(float(price), 6), "discount_factor": round(float(df), 8)}


def inflation_linked_bond_pricer(
    face_value: float,
    real_coupon_rate: float,
    real_yield: float,
    maturity: float,
    inflation_rate: float,
    frequency: int = 2,
) -> dict:  # type: ignore[type-arg]
    """Price an inflation-linked (real) bond with index-uplifted principal.

    Coupons and principal accrete with cumulative inflation; the resulting
    nominal cashflows are discounted at the real yield (the standard
    real-cashflow / real-yield convention).

    Args:
        face_value: Base (un-indexed) par value.
        real_coupon_rate: Annual real coupon rate (decimal).
        real_yield: Annual real yield (decimal).
        maturity: Time to maturity in years.
        inflation_rate: Assumed annual inflation (decimal).
        frequency: Coupon payments per year.

    Returns:
        Dict with ``price``, ``index_ratio_final`` and ``cashflows``.

    Raises:
        ValueError: If maturity or frequency is non-positive.
    """
    if maturity <= 0 or frequency < 1:
        raise ValueError("maturity must be > 0 and frequency >= 1")
    times = _coupon_schedule(maturity, frequency)
    index_ratio = (1.0 + inflation_rate) ** times
    coupon = face_value * real_coupon_rate / frequency
    cashflows = coupon * index_ratio
    cashflows[-1] += face_value * index_ratio[-1]
    discount = (1.0 + real_yield / frequency) ** (-(times * frequency))
    price = float(np.sum(cashflows * discount))
    return {
        "price": round(price, 6),
        "index_ratio_final": round(float(index_ratio[-1]), 8),
        "cashflows": cashflows.tolist(),
    }


# ── Callable / puttable via short-rate binomial tree ───────────────────────────


@njit(cache=True)
def _bond_option_tree(
    face_value: float,
    coupon: float,
    n_steps: int,
    dt: float,
    r0: float,
    rate_vol: float,
    strike: float,
    is_callable: bool,
) -> float:
    """Backward-induction price of a callable/puttable bond on a BDT-like tree.

    Short rate evolves multiplicatively: ``r(i,j) = r0 · exp(rate_vol·√dt·(2j-i))``.
    At each node the issuer (callable) caps the bond value at the call strike;
    the holder (puttable) floors it at the put strike.
    """
    # terminal payoff = face + final coupon at all nodes
    values = np.empty(n_steps + 1, dtype=np.float64)
    for j in range(n_steps + 1):
        values[j] = face_value + coupon
    for step in range(n_steps - 1, -1, -1):
        for j in range(step + 1):
            r = r0 * math.exp(rate_vol * math.sqrt(dt) * (2.0 * j - step))
            disc = math.exp(-r * dt)
            cont = disc * 0.5 * (values[j] + values[j + 1]) + coupon
            if is_callable:
                values[j] = strike if cont > strike else cont
            else:  # puttable
                values[j] = strike if strike > cont else cont
    return float(values[0])


def callable_bond_pricer(
    face_value: float,
    coupon_rate: float,
    short_rate: float,
    rate_vol: float,
    maturity: float,
    call_price: float,
    frequency: int = 1,
) -> dict:  # type: ignore[type-arg]
    """Price a callable bond (issuer's option) on a short-rate binomial tree.

    A callable bond is worth no more than the equivalent straight bond — the
    embedded call belongs to the issuer.

    Note: the short-rate tree is a simplified multiplicative lattice with
    fixed 0.5/0.5 branch probabilities, not a Black-Derman-Toy tree calibrated
    to an initial term structure, and the coupon is added at every node on
    every step.

    Args:
        face_value: Par value.
        coupon_rate: Annual coupon rate (decimal).
        short_rate: Current short rate (continuous, annual).
        rate_vol: Short-rate volatility.
        maturity: Time to maturity in years.
        call_price: Price at which the issuer may call (per face).
        frequency: Coupon payments per year (tree steps per year).

    Returns:
        Dict with ``price`` and ``straight_price``.

    Raises:
        ValueError: If maturity or frequency is non-positive.
    """
    if maturity <= 0 or frequency < 1:
        raise ValueError("maturity must be > 0 and frequency >= 1")
    n_steps = max(int(round(maturity * frequency)), 1)
    dt = maturity / n_steps
    coupon = face_value * coupon_rate / frequency
    callable_val = _bond_option_tree(
        face_value, coupon, n_steps, dt, short_rate, rate_vol, call_price, True
    )
    straight = _bond_option_tree(face_value, coupon, n_steps, dt, short_rate, rate_vol, 1e18, True)
    return {"price": round(float(callable_val), 6), "straight_price": round(float(straight), 6)}


def puttable_bond_pricer(
    face_value: float,
    coupon_rate: float,
    short_rate: float,
    rate_vol: float,
    maturity: float,
    put_price: float,
    frequency: int = 1,
) -> dict:  # type: ignore[type-arg]
    """Price a puttable bond (holder's option) on a short-rate binomial tree.

    A puttable bond is worth at least the equivalent straight bond — the
    embedded put belongs to the holder.

    Note: uses the same simplified multiplicative short-rate lattice as
    ``callable_bond_pricer`` — fixed 0.5/0.5 branch probabilities, not
    calibrated to a market curve.

    Args:
        face_value: Par value.
        coupon_rate: Annual coupon rate (decimal).
        short_rate: Current short rate (continuous, annual).
        rate_vol: Short-rate volatility.
        maturity: Time to maturity in years.
        put_price: Price at which the holder may put (per face).
        frequency: Coupon payments per year (tree steps per year).

    Returns:
        Dict with ``price`` and ``straight_price``.

    Raises:
        ValueError: If maturity or frequency is non-positive.
    """
    if maturity <= 0 or frequency < 1:
        raise ValueError("maturity must be > 0 and frequency >= 1")
    n_steps = max(int(round(maturity * frequency)), 1)
    dt = maturity / n_steps
    coupon = face_value * coupon_rate / frequency
    puttable_val = _bond_option_tree(
        face_value, coupon, n_steps, dt, short_rate, rate_vol, put_price, False
    )
    straight = _bond_option_tree(
        face_value, coupon, n_steps, dt, short_rate, rate_vol, -1e18, False
    )
    return {"price": round(float(puttable_val), 6), "straight_price": round(float(straight), 6)}


def convertible_bond_pricer(
    face_value: float,
    coupon_rate: float,
    yield_rate: float,
    maturity: float,
    conversion_ratio: float,
    stock_price: float,
    frequency: int = 2,
) -> dict:  # type: ignore[type-arg]
    """Price a convertible bond via the bond-floor + conversion-value maximum.

    Value = max(straight bond floor, conversion value), a simple but standard
    lower-bound decomposition. The convertible is always worth at least its
    conversion value and at least its bond floor.

    Note: this lower-bound decomposition does not model conversion
    optionality, equity volatility, or embedded call/put features of a real
    convertible bond.

    Args:
        face_value: Par value.
        coupon_rate: Annual coupon rate (decimal).
        yield_rate: Straight-bond discount yield (decimal).
        maturity: Time to maturity in years.
        conversion_ratio: Shares received per bond on conversion.
        stock_price: Current share price.
        frequency: Coupon payments per year.

    Returns:
        Dict with ``price``, ``bond_floor`` and ``conversion_value``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if maturity <= 0 or frequency < 1:
        raise ValueError("maturity must be > 0 and frequency >= 1")
    if conversion_ratio < 0 or stock_price < 0:
        raise ValueError("conversion_ratio and stock_price must be non-negative")

    bond_floor = bond_pricer_fixed_coupon(face_value, coupon_rate, yield_rate, maturity, frequency)[
        "price"
    ]
    conversion_value = conversion_ratio * stock_price
    price = max(bond_floor, conversion_value)
    return {
        "price": round(float(price), 6),
        "bond_floor": round(float(bond_floor), 6),
        "conversion_value": round(float(conversion_value), 6),
    }

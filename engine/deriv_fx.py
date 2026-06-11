"""engine/deriv_fx.py — FX derivative pricers (Derivatives & Pricing).

FX forward (covered interest-rate parity) and the Garman-Kohlhagen FX option
model (Black-Scholes with two interest rates).

Closed-form, vectorised pure-Python wrappers using scipy.stats.norm — no @njit
region (CLAUDE.md §3.1 satisfied trivially).
"""

from __future__ import annotations

import math

from scipy import stats

__all__ = [
    "fx_forward_pricer",
    "fx_option_pricer_garman_kohlhagen",
]


def fx_forward_pricer(
    spot: float,
    rate_domestic: float,
    rate_foreign: float,
    tau: float,
    notional: float = 1.0,
    contracted_forward: float | None = None,
) -> dict:  # type: ignore[type-arg]
    """FX forward rate and mark-to-market via covered interest-rate parity.

    ``F = S · e^{(r_dom − r_for)·τ}``. If a contracted forward is supplied, the
    MtM value (domestic ccy) of a long-foreign position is
    ``notional · (F − contracted) · e^{−r_dom·τ}``.

    Args:
        spot: Spot FX (domestic per 1 foreign).
        rate_domestic: Domestic continuous rate.
        rate_foreign: Foreign continuous rate.
        tau: Time to delivery (years, > 0).
        notional: Foreign-currency notional.
        contracted_forward: Optional contracted forward rate for MtM.

    Returns:
        Dict with ``forward_rate`` and (if contracted) ``value``.

    Raises:
        ValueError: If spot or tau is non-positive.
    """
    if spot <= 0 or tau <= 0:
        raise ValueError("spot and tau must be positive")
    forward = spot * math.exp((rate_domestic - rate_foreign) * tau)
    result: dict = {"forward_rate": round(float(forward), 8)}  # type: ignore[type-arg]
    if contracted_forward is not None:
        value = notional * (forward - contracted_forward) * math.exp(-rate_domestic * tau)
        result["value"] = round(float(value), 6)
    return result


def fx_option_pricer_garman_kohlhagen(
    spot: float,
    strike: float,
    rate_domestic: float,
    rate_foreign: float,
    sigma: float,
    tau: float,
    option_type: str = "call",
    notional: float = 1.0,
) -> dict:  # type: ignore[type-arg]
    """Garman-Kohlhagen FX option price.

    Black-Scholes with the foreign rate acting as a continuous dividend yield:
    ``Call = S e^{−r_for τ} N(d1) − K e^{−r_dom τ} N(d2)``. Satisfies FX
    put-call parity ``C − P = S e^{−r_for τ} − K e^{−r_dom τ}``.

    Args:
        spot: Spot FX (domestic per 1 foreign).
        strike: Strike FX.
        rate_domestic: Domestic continuous rate.
        rate_foreign: Foreign continuous rate.
        sigma: FX volatility (> 0).
        tau: Time to maturity (years, > 0).
        option_type: ``"call"`` or ``"put"``.
        notional: Foreign-currency notional.

    Returns:
        Dict with ``price``, ``d1``, ``d2``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")

    sqrt_t = math.sqrt(tau)
    d1 = (math.log(spot / strike) + (rate_domestic - rate_foreign + 0.5 * sigma * sigma) * tau) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    disc_d = math.exp(-rate_domestic * tau)
    disc_f = math.exp(-rate_foreign * tau)
    if option_type == "call":
        price = spot * disc_f * float(stats.norm.cdf(d1)) - strike * disc_d * float(stats.norm.cdf(d2))
    else:
        price = strike * disc_d * float(stats.norm.cdf(-d2)) - spot * disc_f * float(stats.norm.cdf(-d1))
    return {"price": round(float(price) * notional, 8), "d1": round(d1, 8), "d2": round(d2, 8)}

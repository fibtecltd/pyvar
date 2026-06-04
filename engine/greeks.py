"""engine/greeks.py — Sensitivities / Greeks (Market Risk).

Portfolio-level aggregation Greeks (delta, gamma matrix, bucketed vega, bucketed
DV01/CS01) and Black-Scholes option Greeks (rho, theta, charm, volga, vanna).

Black-Scholes Greeks use closed-form expressions; aggregation Greeks are pure
NumPy reductions. No @njit is required here (the work is vectorised and light),
so CLAUDE.md §3.1 is satisfied trivially — there are no JIT kernels to constrain.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

__all__ = [
    "portfolio_delta_aggregated",
    "gamma_cross_gamma_matrix",
    "vega_surface_bucketed",
    "dv01_pv01_bucketed",
    "cs01_credit_spread",
    "rho_interest_rate",
    "theta_time_decay",
    "charm_delta_decay",
]


def portfolio_delta_aggregated(
    deltas: np.ndarray,
    quantities: np.ndarray,
    spot_prices: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Aggregate per-position deltas into a net portfolio delta.

    Net delta = Σ delta_i * quantity_i. When spot prices are supplied the
    cash (dollar) delta Σ delta_i * quantity_i * spot_i is also returned.

    Args:
        deltas: Per-position option delta (∂V/∂S).
        quantities: Signed position size per instrument.
        spot_prices: Optional underlying spot per position for cash delta.

    Returns:
        Dict with ``net_delta`` and (if spots given) ``cash_delta``.

    Raises:
        ValueError: If input lengths are inconsistent.
    """
    d = np.asarray(deltas, dtype=np.float64)
    q = np.asarray(quantities, dtype=np.float64)
    if d.size != q.size:
        raise ValueError("deltas and quantities must have the same length")

    net_delta = float(np.sum(d * q))
    result: dict = {"net_delta": round(net_delta, 8)}  # type: ignore[type-arg]
    if spot_prices is not None:
        s = np.asarray(spot_prices, dtype=np.float64)
        if s.size != d.size:
            raise ValueError("spot_prices must match deltas length")
        result["cash_delta"] = round(float(np.sum(d * q * s)), 4)
    return result


def gamma_cross_gamma_matrix(
    own_gammas: np.ndarray,
    cross_gammas: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Assemble the portfolio gamma / cross-gamma matrix.

    The diagonal holds each underlying's net gamma (∂²V/∂S_i²); off-diagonals
    hold cross-gammas (∂²V/∂S_i∂S_j). The matrix is symmetric (Schwarz's
    theorem) — gamma P&L for a shock vector ds is ``0.5 · ds' G ds``.

    Args:
        own_gammas: Length-U net gamma per underlying (matrix diagonal).
        cross_gammas: Optional ``(U, U)`` cross-gamma matrix; its off-diagonal
            entries are symmetrised into the result. Diagonal is ignored.

    Returns:
        Dict with the symmetric ``gamma_matrix`` and ``is_symmetric`` flag.

    Raises:
        ValueError: If ``cross_gammas`` shape does not match ``own_gammas``.
    """
    g = np.asarray(own_gammas, dtype=np.float64)
    u = g.size
    matrix = np.diag(g).astype(np.float64)
    if cross_gammas is not None:
        cg = np.asarray(cross_gammas, dtype=np.float64)
        if cg.shape != (u, u):
            raise ValueError("cross_gammas must be (U, U) matching own_gammas")
        off = cg.copy()
        np.fill_diagonal(off, 0.0)
        sym_off = 0.5 * (off + off.T)  # enforce symmetry
        matrix = matrix + sym_off
    return {
        "gamma_matrix": matrix.tolist(),
        "is_symmetric": bool(np.allclose(matrix, matrix.T)),
    }


def vega_surface_bucketed(
    vegas: np.ndarray,
    expiry_buckets: np.ndarray,
    strike_buckets: np.ndarray,
    n_expiry: int,
    n_strike: int,
) -> dict:  # type: ignore[type-arg]
    """Aggregate option vegas onto a bucketed (expiry × strike) surface.

    Each option's vega is summed into its (expiry, strike) bucket. Total vega is
    conserved — the surface sum equals the input vega sum.

    Args:
        vegas: Per-option vega (∂V/∂σ).
        expiry_buckets: Per-option expiry bucket index in ``[0, n_expiry)``.
        strike_buckets: Per-option strike bucket index in ``[0, n_strike)``.
        n_expiry: Number of expiry buckets.
        n_strike: Number of strike buckets.

    Returns:
        Dict with the ``surface`` (n_expiry × n_strike) and ``total_vega``.

    Raises:
        ValueError: If lengths mismatch or bucket indices are out of range.
    """
    v = np.asarray(vegas, dtype=np.float64)
    ei = np.asarray(expiry_buckets, dtype=np.int64)
    si = np.asarray(strike_buckets, dtype=np.int64)
    if not (v.size == ei.size == si.size):
        raise ValueError("vegas, expiry_buckets, strike_buckets must be equal length")
    if v.size and (ei.min() < 0 or ei.max() >= n_expiry or si.min() < 0 or si.max() >= n_strike):
        raise ValueError("bucket index out of range")

    surface = np.zeros((n_expiry, n_strike), dtype=np.float64)
    for k in range(v.size):
        surface[ei[k], si[k]] += v[k]
    return {
        "surface": surface.tolist(),
        "total_vega": round(float(np.sum(surface)), 8),
    }


def _d1_d2(
    spot: float, strike: float, rate: float, sigma: float, tau: float, div_yield: float
) -> tuple[float, float, float]:
    """Black-Scholes d1, d2 and √tau (shared by the option Greeks)."""
    sqrt_t = np.sqrt(tau)
    d1 = (np.log(spot / strike) + (rate - div_yield + 0.5 * sigma * sigma) * tau) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return float(d1), float(d2), float(sqrt_t)


def dv01_pv01_bucketed(
    cashflows: np.ndarray,
    times: np.ndarray,
    flat_yield: float,
    bucket_indices: np.ndarray,
    n_buckets: int,
) -> dict:  # type: ignore[type-arg]
    """Tenor-bucketed DV01 / PV01 of a fixed cashflow stream.

    For continuously-discounted cashflows ``PV = Σ cf_k e^{-y t_k}`` the DV01 of
    each cashflow (price change for a +1bp yield move) is
    ``cf_k · t_k · e^{-y t_k} · 1e-4``. Cashflows are summed into tenor buckets;
    the bucket DV01s sum exactly to the total.

    Args:
        cashflows: Cashflow amounts.
        times: Cashflow times in years.
        flat_yield: Flat continuously-compounded discount yield.
        bucket_indices: Tenor bucket index per cashflow in ``[0, n_buckets)``.
        n_buckets: Number of tenor buckets.

    Returns:
        Dict with ``dv01_buckets``, ``total_dv01``, ``total_pv01`` (equal to
        ``total_dv01`` for a 1bp move) and ``pv``.

    Raises:
        ValueError: If lengths mismatch or bucket indices are out of range.
    """
    cf = np.asarray(cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    bi = np.asarray(bucket_indices, dtype=np.int64)
    if not (cf.size == t.size == bi.size):
        raise ValueError("cashflows, times, bucket_indices must be equal length")
    if cf.size and (bi.min() < 0 or bi.max() >= n_buckets):
        raise ValueError("bucket index out of range")

    discount = np.exp(-flat_yield * t)
    pv_k = cf * discount
    dv01_k = cf * t * discount * 1e-4
    buckets = np.zeros(n_buckets, dtype=np.float64)
    for k in range(cf.size):
        buckets[bi[k]] += dv01_k[k]
    total_dv01 = float(np.sum(dv01_k))
    return {
        "dv01_buckets": [round(float(b), 8) for b in buckets],
        "total_dv01": round(total_dv01, 8),
        "total_pv01": round(total_dv01, 8),
        "pv": round(float(np.sum(pv_k)), 6),
    }


def cs01_credit_spread(
    cashflows: np.ndarray,
    times: np.ndarray,
    risk_free_rate: float,
    credit_spread: float,
) -> dict:  # type: ignore[type-arg]
    """CS01 — sensitivity of a risky cashflow stream to a +1bp credit spread move.

    Cashflows are discounted at ``r + s``; CS01 is
    ``Σ cf_k · t_k · e^{-(r+s) t_k} · 1e-4`` — the price drop for a 1bp widening
    of the credit spread.

    Args:
        cashflows: Cashflow amounts.
        times: Cashflow times in years.
        risk_free_rate: Continuously-compounded risk-free rate.
        credit_spread: Continuously-compounded credit spread.

    Returns:
        Dict with ``cs01`` and the risky present value ``pv``.

    Raises:
        ValueError: If ``cashflows`` and ``times`` differ in length.
    """
    cf = np.asarray(cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    if cf.size != t.size:
        raise ValueError("cashflows and times must have the same length")

    discount = np.exp(-(risk_free_rate + credit_spread) * t)
    cs01 = float(np.sum(cf * t * discount * 1e-4))
    return {
        "cs01": round(cs01, 8),
        "pv": round(float(np.sum(cf * discount)), 6),
    }


def rho_interest_rate(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    option_type: str = "call",
    div_yield: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Black-Scholes Rho — option value sensitivity to the interest rate.

    ``Rho_call = K τ e^{-rτ} N(d2)``; ``Rho_put = -K τ e^{-rτ} N(-d2)``.

    Args:
        spot: Underlying spot price.
        strike: Strike price.
        rate: Continuously-compounded risk-free rate.
        sigma: Volatility (annualised).
        tau: Time to maturity in years.
        option_type: ``"call"`` or ``"put"``.
        div_yield: Continuous dividend yield.

    Returns:
        Dict with ``rho`` (per unit rate, i.e. per 1.00 = 100%) and ``d2``.

    Raises:
        ValueError: If ``option_type`` is not call/put or inputs are non-positive.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")

    _, d2, _ = _d1_d2(spot, strike, rate, sigma, tau, div_yield)
    disc = np.exp(-rate * tau)
    if option_type == "call":
        rho = strike * tau * disc * float(stats.norm.cdf(d2))
    else:
        rho = -strike * tau * disc * float(stats.norm.cdf(-d2))
    return {"rho": round(float(rho), 8), "d2": round(d2, 8)}


def theta_time_decay(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    option_type: str = "call",
    div_yield: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Black-Scholes Theta — calendar time decay (∂V/∂calendar = −∂V/∂τ), per year.

    Args:
        spot: Underlying spot price.
        strike: Strike price.
        rate: Continuously-compounded risk-free rate.
        sigma: Volatility (annualised).
        tau: Time to maturity in years.
        option_type: ``"call"`` or ``"put"``.
        div_yield: Continuous dividend yield.

    Returns:
        Dict with ``theta`` (per year) and ``theta_per_day`` (theta / 365).

    Raises:
        ValueError: If ``option_type`` is invalid or inputs are non-positive.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")

    d1, d2, sqrt_t = _d1_d2(spot, strike, rate, sigma, tau, div_yield)
    nd1 = float(stats.norm.pdf(d1))
    disc_r = np.exp(-rate * tau)
    disc_q = np.exp(-div_yield * tau)
    common = -(spot * disc_q * nd1 * sigma) / (2.0 * sqrt_t)
    if option_type == "call":
        theta = (
            common
            - rate * strike * disc_r * float(stats.norm.cdf(d2))
            + div_yield * spot * disc_q * float(stats.norm.cdf(d1))
        )
    else:
        theta = (
            common
            + rate * strike * disc_r * float(stats.norm.cdf(-d2))
            - div_yield * spot * disc_q * float(stats.norm.cdf(-d1))
        )
    return {"theta": round(float(theta), 8), "theta_per_day": round(float(theta) / 365.0, 8)}


def charm_delta_decay(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    option_type: str = "call",
    div_yield: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Charm — sensitivity of delta to time to maturity (∂Δ/∂τ).

    Computed in the time-to-maturity convention so that a finite-difference of
    delta with respect to τ reproduces this value.

    Args:
        spot: Underlying spot price.
        strike: Strike price.
        rate: Continuously-compounded risk-free rate.
        sigma: Volatility (annualised).
        tau: Time to maturity in years.
        option_type: ``"call"`` or ``"put"``.
        div_yield: Continuous dividend yield.

    Returns:
        Dict with ``charm`` (∂Δ/∂τ).

    Raises:
        ValueError: If ``option_type`` is invalid or inputs are non-positive.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")

    d1, _, sqrt_t = _d1_d2(spot, strike, rate, sigma, tau, div_yield)
    nd1 = float(stats.norm.pdf(d1))
    disc_q = np.exp(-div_yield * tau)
    a = np.log(spot / strike)
    b = rate - div_yield + 0.5 * sigma * sigma
    dd1_dtau = b / (sigma * sqrt_t) - (a + b * tau) / (2.0 * sigma * tau * sqrt_t)
    if option_type == "call":
        charm = -div_yield * disc_q * float(stats.norm.cdf(d1)) + disc_q * nd1 * dd1_dtau
    else:
        charm = div_yield * disc_q * float(stats.norm.cdf(-d1)) + disc_q * nd1 * dd1_dtau
    return {"charm": round(float(charm), 8)}

"""engine/deriv_options_vanilla.py — Vanilla option pricers (Derivatives & Pricing).

Closed-form Black-Scholes, its Greeks, the Cox-Ross-Rubinstein binomial tree,
the Boyle trinomial tree, and a plain Monte Carlo terminal-payoff pricer.

Numba rules (CLAUDE.md §3.1) are honoured:
  * @njit kernels (the trees, the MC payoff reduction) are stateless, take only
    float64 scalars / arrays, never import internally, and return NumPy arrays.
  * All randomness is pre-drawn in pure Python before the JIT region.
  * The closed-form Black-Scholes wrapper uses scipy.stats.norm in pure Python.

The module also exports :func:`norm_cdf` / :func:`norm_pdf` — erf-based @njit
implementations of the standard normal CDF/PDF reused by other derivative
modules where a normal CDF is needed inside a JIT region.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit, prange
from scipy import stats

__all__ = [
    "norm_cdf",
    "norm_pdf",
    "black_scholes_european_option",
    "black_scholes_greeks",
    "binomial_tree_option_pricer",
    "trinomial_tree_option_pricer",
    "monte_carlo_option_pricer",
]


# ── JIT helpers: standard normal CDF / PDF (RULE: norm not available in njit) ──


@njit(cache=True)
def norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function (njit-safe).

    Args:
        x: Evaluation point.

    Returns:
        Phi(x) in [0, 1].
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@njit(cache=True)
def norm_pdf(x: float) -> float:
    """Standard normal PDF (njit-safe).

    Args:
        x: Evaluation point.

    Returns:
        phi(x).
    """
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


# ── JIT kernels ───────────────────────────────────────────────────────────────


@njit(cache=True)
def _crr_binomial(
    spot: float,
    strike: float,
    rate: float,
    div_yield: float,
    sigma: float,
    tau: float,
    n_steps: int,
    is_call: bool,
    is_american: bool,
) -> float:
    """Cox-Ross-Rubinstein binomial tree value (backward induction)."""
    dt = tau / n_steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    disc = math.exp(-rate * dt)
    p = (math.exp((rate - div_yield) * dt) - d) / (u - d)

    values = np.empty(n_steps + 1, dtype=np.float64)
    for i in range(n_steps + 1):
        st = spot * (u ** (n_steps - i)) * (d**i)
        if is_call:
            values[i] = st - strike if st > strike else 0.0
        else:
            values[i] = strike - st if strike > st else 0.0

    for step in range(n_steps - 1, -1, -1):
        for i in range(step + 1):
            cont = disc * (p * values[i] + (1.0 - p) * values[i + 1])
            if is_american:
                st = spot * (u ** (step - i)) * (d**i)
                if is_call:
                    exercise = st - strike if st > strike else 0.0
                else:
                    exercise = strike - st if strike > st else 0.0
                values[i] = exercise if exercise > cont else cont
            else:
                values[i] = cont
    return values[0]


@njit(cache=True)
def _trinomial(
    spot: float,
    strike: float,
    rate: float,
    div_yield: float,
    sigma: float,
    tau: float,
    n_steps: int,
    is_call: bool,
    is_american: bool,
) -> float:
    """Boyle trinomial tree value (backward induction)."""
    dt = tau / n_steps
    dx = sigma * math.sqrt(3.0 * dt)
    u = math.exp(dx)
    d = 1.0 / u
    disc = math.exp(-rate * dt)
    nu = rate - div_yield - 0.5 * sigma * sigma
    pu = 0.5 * ((sigma * sigma * dt + nu * nu * dt * dt) / (dx * dx) + nu * dt / dx)
    pd = 0.5 * ((sigma * sigma * dt + nu * nu * dt * dt) / (dx * dx) - nu * dt / dx)
    pm = 1.0 - pu - pd

    size = 2 * n_steps + 1
    # values indexed 0..2*step; node k = j - step at a given step level.
    values = np.empty(size, dtype=np.float64)
    for j in range(size):
        k = j - n_steps  # node index from -n_steps .. +n_steps
        st = spot * math.exp(k * dx)
        if is_call:
            values[j] = st - strike if st > strike else 0.0
        else:
            values[j] = strike - st if strike > st else 0.0

    for step in range(n_steps - 1, -1, -1):
        width = 2 * step + 1
        for j in range(width):
            # child nodes at level step+1: down=j, middle=j+1, up=j+2
            cont = disc * (pd * values[j] + pm * values[j + 1] + pu * values[j + 2])
            if is_american:
                k = j - step
                st = spot * math.exp(k * dx)
                if is_call:
                    exercise = st - strike if st > strike else 0.0
                else:
                    exercise = strike - st if strike > st else 0.0
                values[j] = exercise if exercise > cont else cont
            else:
                values[j] = cont
    return values[0]


@njit(cache=True, parallel=True)
def _mc_terminal_payoff(
    spot: float,
    strike: float,
    rate: float,
    div_yield: float,
    sigma: float,
    tau: float,
    normals: np.ndarray,
    is_call: bool,
) -> np.ndarray:
    """Discounted terminal payoffs from pre-drawn standard normals.

    Returns a float64 array of per-path discounted payoffs (RULE 5: arrays only).
    """
    n = normals.shape[0]
    drift = (rate - div_yield - 0.5 * sigma * sigma) * tau
    vol = sigma * math.sqrt(tau)
    disc = math.exp(-rate * tau)
    out = np.empty(n, dtype=np.float64)
    for i in prange(n):
        st = spot * math.exp(drift + vol * normals[i])
        if is_call:
            payoff = st - strike if st > strike else 0.0
        else:
            payoff = strike - st if strike > st else 0.0
        out[i] = disc * payoff
    return out


# ── Public functions ───────────────────────────────────────────────────────────


def black_scholes_european_option(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    option_type: str = "call",
    div_yield: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Black-Scholes-Merton price of a European option.

    ``Call = S e^{-qτ} N(d1) − K e^{-rτ} N(d2)``; the put follows by parity.
    When ``tau == 0`` the intrinsic value is returned (zero-time limit) and when
    ``sigma == 0`` the discounted-forward intrinsic value is returned.

    Args:
        spot: Underlying spot price.
        strike: Strike price.
        rate: Continuously-compounded risk-free rate.
        sigma: Volatility (annualised, >= 0).
        tau: Time to maturity in years (>= 0).
        option_type: ``"call"`` or ``"put"``.
        div_yield: Continuous dividend yield.

    Returns:
        Dict with ``price``, ``d1``, ``d2``.

    Raises:
        ValueError: If ``option_type`` invalid or spot/strike non-positive.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if sigma < 0 or tau < 0:
        raise ValueError("sigma and tau must be non-negative")

    is_call = option_type == "call"
    if tau == 0.0 or sigma == 0.0:
        fwd = spot * math.exp((rate - div_yield) * tau)
        disc = math.exp(-rate * tau)
        if is_call:
            price = disc * max(fwd - strike, 0.0)
        else:
            price = disc * max(strike - fwd, 0.0)
        return {"price": round(float(price), 8), "d1": 0.0, "d2": 0.0}

    sqrt_t = math.sqrt(tau)
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * sigma * sigma) * tau) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    disc_r = math.exp(-rate * tau)
    disc_q = math.exp(-div_yield * tau)
    if is_call:
        price = spot * disc_q * float(stats.norm.cdf(d1)) - strike * disc_r * float(stats.norm.cdf(d2))
    else:
        price = strike * disc_r * float(stats.norm.cdf(-d2)) - spot * disc_q * float(stats.norm.cdf(-d1))
    return {"price": round(float(price), 8), "d1": round(d1, 8), "d2": round(d2, 8)}


def black_scholes_greeks(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    option_type: str = "call",
    div_yield: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Closed-form Black-Scholes first-order Greeks.

    Returns delta, gamma, vega, theta (per year) and rho. Gamma and vega are
    identical for calls and puts.

    Args:
        spot: Underlying spot price.
        strike: Strike price.
        rate: Continuously-compounded risk-free rate.
        sigma: Volatility (annualised, > 0).
        tau: Time to maturity in years (> 0).
        option_type: ``"call"`` or ``"put"``.
        div_yield: Continuous dividend yield.

    Returns:
        Dict with ``delta``, ``gamma``, ``vega``, ``theta``, ``rho``.

    Raises:
        ValueError: If ``option_type`` invalid or inputs non-positive.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")

    sqrt_t = math.sqrt(tau)
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * sigma * sigma) * tau) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    disc_r = math.exp(-rate * tau)
    disc_q = math.exp(-div_yield * tau)
    pdf_d1 = float(stats.norm.pdf(d1))

    gamma = disc_q * pdf_d1 / (spot * sigma * sqrt_t)
    vega = spot * disc_q * pdf_d1 * sqrt_t
    if option_type == "call":
        delta = disc_q * float(stats.norm.cdf(d1))
        theta = (
            -(spot * disc_q * pdf_d1 * sigma) / (2.0 * sqrt_t)
            - rate * strike * disc_r * float(stats.norm.cdf(d2))
            + div_yield * spot * disc_q * float(stats.norm.cdf(d1))
        )
        rho = strike * tau * disc_r * float(stats.norm.cdf(d2))
    else:
        delta = -disc_q * float(stats.norm.cdf(-d1))
        theta = (
            -(spot * disc_q * pdf_d1 * sigma) / (2.0 * sqrt_t)
            + rate * strike * disc_r * float(stats.norm.cdf(-d2))
            - div_yield * spot * disc_q * float(stats.norm.cdf(-d1))
        )
        rho = -strike * tau * disc_r * float(stats.norm.cdf(-d2))
    return {
        "delta": round(float(delta), 8),
        "gamma": round(float(gamma), 8),
        "vega": round(float(vega), 8),
        "theta": round(float(theta), 8),
        "rho": round(float(rho), 8),
    }


def binomial_tree_option_pricer(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    n_steps: int = 500,
    option_type: str = "call",
    style: str = "european",
    div_yield: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Cox-Ross-Rubinstein binomial tree option price.

    Handles European and American exercise. European prices converge to
    Black-Scholes as ``n_steps`` grows.

    Args:
        spot: Underlying spot price.
        strike: Strike price.
        rate: Continuously-compounded risk-free rate.
        sigma: Volatility (annualised, > 0).
        tau: Time to maturity in years (> 0).
        n_steps: Number of binomial steps (>= 1).
        option_type: ``"call"`` or ``"put"``.
        style: ``"european"`` or ``"american"``.
        div_yield: Continuous dividend yield.

    Returns:
        Dict with ``price``, ``n_steps``, ``style``.

    Raises:
        ValueError: If parameters are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if style not in ("european", "american"):
        raise ValueError("style must be 'european' or 'american'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")
    if n_steps < 1:
        raise ValueError("n_steps must be >= 1")

    price = _crr_binomial(
        spot, strike, rate, div_yield, sigma, tau, int(n_steps),
        option_type == "call", style == "american",
    )
    return {"price": round(float(price), 8), "n_steps": int(n_steps), "style": style}


def trinomial_tree_option_pricer(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    n_steps: int = 300,
    option_type: str = "call",
    style: str = "european",
    div_yield: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Boyle trinomial tree option price.

    Up/middle/down branching converges to Black-Scholes for European options.
    Handles American exercise.

    Args:
        spot: Underlying spot price.
        strike: Strike price.
        rate: Continuously-compounded risk-free rate.
        sigma: Volatility (annualised, > 0).
        tau: Time to maturity in years (> 0).
        n_steps: Number of tree steps (>= 1).
        option_type: ``"call"`` or ``"put"``.
        style: ``"european"`` or ``"american"``.
        div_yield: Continuous dividend yield.

    Returns:
        Dict with ``price``, ``n_steps``, ``style``.

    Raises:
        ValueError: If parameters are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if style not in ("european", "american"):
        raise ValueError("style must be 'european' or 'american'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")
    if n_steps < 1:
        raise ValueError("n_steps must be >= 1")

    price = _trinomial(
        spot, strike, rate, div_yield, sigma, tau, int(n_steps),
        option_type == "call", style == "american",
    )
    return {"price": round(float(price), 8), "n_steps": int(n_steps), "style": style}


def monte_carlo_option_pricer(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    tau: float,
    n_simulations: int = 100_000,
    option_type: str = "call",
    div_yield: float = 0.0,
    seed: int = 12345,
) -> dict:  # type: ignore[type-arg]
    """Monte Carlo price of a European option (terminal GBM payoff).

    Randoms are pre-drawn in pure Python (CLAUDE.md §3.1 RULE 3); the JIT kernel
    only consumes the pre-drawn standard-normal array.

    Args:
        spot: Underlying spot price.
        strike: Strike price.
        rate: Continuously-compounded risk-free rate.
        sigma: Volatility (annualised, > 0).
        tau: Time to maturity in years (> 0).
        n_simulations: Number of Monte Carlo paths.
        option_type: ``"call"`` or ``"put"``.
        div_yield: Continuous dividend yield.
        seed: RNG seed for determinism.

    Returns:
        Dict with ``price``, ``std_error``, ``n_simulations``.

    Raises:
        ValueError: If parameters are invalid.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if spot <= 0 or strike <= 0 or sigma <= 0 or tau <= 0:
        raise ValueError("spot, strike, sigma, tau must be positive")
    if n_simulations < 1:
        raise ValueError("n_simulations must be >= 1")

    rng = np.random.default_rng(seed)
    normals = rng.standard_normal(int(n_simulations)).astype(np.float64)
    payoffs = _mc_terminal_payoff(
        spot, strike, rate, div_yield, sigma, tau, normals, option_type == "call"
    )
    price = float(np.mean(payoffs))
    std_error = float(np.std(payoffs) / math.sqrt(n_simulations))
    return {
        "price": round(price, 8),
        "std_error": round(std_error, 8),
        "n_simulations": int(n_simulations),
    }

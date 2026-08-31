"""engine/deriv_short_rate.py — Short-rate & forward-rate models.

Vasicek, Cox-Ingersoll-Ross (CIR) and Hull-White one-factor short-rate models
(closed-form zero-coupon bond prices + Monte Carlo paths), plus a LIBOR Market
Model (LMM/BGM) forward-rate Monte Carlo simulator.

Numba rules (CLAUDE.md §3.1): the Monte Carlo path kernels are stateless
@njit(cache=True) consuming pre-drawn normals; closed-form bond formulas live in
the pure-Python wrappers.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit, prange

__all__ = [
    "vasicek_interest_rate_model",
    "cox_ingersoll_ross_model",
    "hull_white_short_rate_model",
    "lmm_bgm_rate_model",
]


@njit(cache=True, parallel=True)
def _vasicek_paths(
    r0: float, kappa: float, theta: float, sigma: float, tau: float, normals: np.ndarray
) -> np.ndarray:
    """Terminal short rates for Vasicek from pre-drawn normals."""
    n_paths, n_steps = normals.shape
    dt = tau / n_steps
    sqdt = math.sqrt(dt)
    out = np.empty(n_paths, dtype=np.float64)
    for p in prange(n_paths):
        r = r0
        for k in range(n_steps):
            r = r + kappa * (theta - r) * dt + sigma * sqdt * normals[p, k]
        out[p] = r
    return out


def vasicek_interest_rate_model(
    r0: float,
    kappa: float,
    theta: float,
    sigma: float,
    maturity: float,
    n_steps: int = 100,
    n_simulations: int = 50_000,
    seed: int = 101,
) -> dict:  # type: ignore[type-arg]
    """Vasicek model: closed-form zero-coupon bond price + simulated short rate.

    ``dr = κ(θ−r)dt + σ dW``. The affine ZCB price is ``P = A·e^{−B·r0}``. The
    short rate is Gaussian (can go negative).

    Args:
        r0: Initial short rate.
        kappa: Mean-reversion speed (> 0).
        theta: Long-run mean.
        sigma: Volatility (> 0).
        maturity: Bond maturity in years (> 0).
        n_steps: MC time steps.
        n_simulations: MC paths.
        seed: RNG seed.

    Returns:
        Dict with ``bond_price``, ``mc_mean_rate``, ``B``, ``A``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if kappa <= 0 or sigma <= 0 or maturity <= 0:
        raise ValueError("kappa, sigma, maturity must be positive")

    b = (1.0 - math.exp(-kappa * maturity)) / kappa
    a = math.exp(
        (theta - sigma**2 / (2.0 * kappa**2)) * (b - maturity) - (sigma**2 * b**2) / (4.0 * kappa)
    )
    bond_price = a * math.exp(-b * r0)

    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((int(n_simulations), int(n_steps))).astype(np.float64)
    terminal = _vasicek_paths(r0, kappa, theta, sigma, maturity, normals)
    return {
        "bond_price": round(float(bond_price), 8),
        "mc_mean_rate": round(float(np.mean(terminal)), 8),
        "B": round(float(b), 8),
        "A": round(float(a), 8),
    }


@njit(cache=True, parallel=True)
def _cir_paths(
    r0: float, kappa: float, theta: float, sigma: float, tau: float, normals: np.ndarray
) -> np.ndarray:
    """Terminal short rates for CIR (full-truncation Euler) from normals."""
    n_paths, n_steps = normals.shape
    dt = tau / n_steps
    sqdt = math.sqrt(dt)
    out = np.empty(n_paths, dtype=np.float64)
    for p in prange(n_paths):
        r = r0
        for k in range(n_steps):
            r_pos = r if r > 0.0 else 0.0
            r = r + kappa * (theta - r) * dt + sigma * math.sqrt(r_pos) * sqdt * normals[p, k]
        out[p] = r if r > 0.0 else 0.0
    return out


def cox_ingersoll_ross_model(
    r0: float,
    kappa: float,
    theta: float,
    sigma: float,
    maturity: float,
    n_steps: int = 100,
    n_simulations: int = 50_000,
    seed: int = 102,
) -> dict:  # type: ignore[type-arg]
    """CIR model: closed-form ZCB price + simulated (non-negative) short rate.

    ``dr = κ(θ−r)dt + σ√r dW``. The square-root diffusion keeps ``r >= 0``. The
    Feller condition ``2κθ ≥ σ²`` guarantees strict positivity.

    Note: the Monte Carlo path uses full-truncation Euler discretisation (the
    rate is floored at 0 both inside the square root and for the terminal
    output), not the exact non-central chi-squared CIR transition
    distribution.

    Args:
        r0: Initial short rate (>= 0).
        kappa: Mean-reversion speed (> 0).
        theta: Long-run mean (> 0).
        sigma: Volatility (> 0).
        maturity: Bond maturity in years (> 0).
        n_steps: MC time steps.
        n_simulations: MC paths.
        seed: RNG seed.

    Returns:
        Dict with ``bond_price``, ``mc_mean_rate``, ``feller_satisfied``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if kappa <= 0 or theta <= 0 or sigma <= 0 or maturity <= 0 or r0 < 0:
        raise ValueError("invalid CIR parameters")

    gamma = math.sqrt(kappa**2 + 2.0 * sigma**2)
    denom = (gamma + kappa) * (math.exp(gamma * maturity) - 1.0) + 2.0 * gamma
    b = 2.0 * (math.exp(gamma * maturity) - 1.0) / denom
    a = (2.0 * gamma * math.exp((kappa + gamma) * maturity / 2.0) / denom) ** (
        2.0 * kappa * theta / sigma**2
    )
    bond_price = a * math.exp(-b * r0)

    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((int(n_simulations), int(n_steps))).astype(np.float64)
    terminal = _cir_paths(r0, kappa, theta, sigma, maturity, normals)
    return {
        "bond_price": round(float(bond_price), 8),
        "mc_mean_rate": round(float(np.mean(terminal)), 8),
        "feller_satisfied": bool(2.0 * kappa * theta >= sigma**2),
    }


def hull_white_short_rate_model(
    r0: float,
    kappa: float,
    sigma: float,
    maturity: float,
    theta_const: float = 0.03,
    n_steps: int = 100,
    n_simulations: int = 50_000,
    seed: int = 103,
) -> dict:  # type: ignore[type-arg]
    """Hull-White one-factor model with a constant mean-reversion level.

    ``dr = κ(θ−r)dt + σ dW`` — the extended-Vasicek form; with a constant θ the
    closed-form ZCB price coincides with Vasicek. Returns the analytic bond
    price and a Monte Carlo cross-check.

    Note: with ``theta_const`` held constant this function literally delegates
    to ``vasicek_interest_rate_model`` — it is not a genuine time-dependent
    Hull-White model calibrated to fit an observed market forward curve.

    Args:
        r0: Initial short rate.
        kappa: Mean-reversion speed (> 0).
        sigma: Volatility (> 0).
        maturity: Bond maturity (years, > 0).
        theta_const: Constant mean-reversion level.
        n_steps: MC time steps.
        n_simulations: MC paths.
        seed: RNG seed.

    Returns:
        Dict with ``bond_price``, ``mc_mean_rate``.

    Raises:
        ValueError: If inputs are invalid.
    """
    if kappa <= 0 or sigma <= 0 or maturity <= 0:
        raise ValueError("kappa, sigma, maturity must be positive")
    # With constant theta, Hull-White = Vasicek closed form.
    vas = vasicek_interest_rate_model(
        r0, kappa, theta_const, sigma, maturity, n_steps, n_simulations, seed
    )
    return {"bond_price": vas["bond_price"], "mc_mean_rate": vas["mc_mean_rate"]}


@njit(cache=True, parallel=True)
def _lmm_terminal_rates(
    fwd0: np.ndarray,
    vols: np.ndarray,
    tenor: float,
    tau: float,
    normals: np.ndarray,
) -> np.ndarray:
    """Evolve LMM forward rates under the spot measure to ``tau``.

    ``normals`` is ``(n_paths, n_steps, n_rates)``. Returns ``(n_paths, n_rates)``
    terminal forward rates. Uses a simple log-Euler scheme with drift under the
    spot LIBOR measure.
    """
    n_paths, n_steps, n_rates = normals.shape
    dt = tau / n_steps
    sqdt = math.sqrt(dt)
    out = np.empty((n_paths, n_rates), dtype=np.float64)
    for p in prange(n_paths):
        f = fwd0.copy()
        for step in range(n_steps):
            for i in range(n_rates):
                drift = 0.0
                for j in range(i + 1):
                    drift += (tenor * f[j] * vols[j] * vols[i]) / (1.0 + tenor * f[j])
                f[i] = f[i] * math.exp(
                    (drift - 0.5 * vols[i] * vols[i]) * dt + vols[i] * sqdt * normals[p, step, i]
                )
        for i in range(n_rates):
            out[p, i] = f[i]
    return out


def lmm_bgm_rate_model(
    forward_rates: np.ndarray,
    vols: np.ndarray,
    tenor: float,
    horizon: float,
    n_steps: int = 20,
    n_simulations: int = 20_000,
    seed: int = 104,
) -> dict:  # type: ignore[type-arg]
    """LIBOR Market Model (BGM) forward-rate Monte Carlo simulation.

    Evolves a vector of forward LIBOR rates under the spot measure with the
    standard log-normal BGM drift. Returns the mean terminal forward curve;
    rates stay positive (log-normal dynamics).

    Note: the drift for rate ``i`` sums over ``j = 0..i`` inclusive (including
    rate ``i`` itself) using each earlier rate's already-updated value from the
    same time step rather than its start-of-step value, since rates are
    overwritten sequentially in place — a specific sequential log-Euler
    discretisation choice, not a fully simultaneous update.

    Args:
        forward_rates: Initial forward rates per tenor (decimal, > 0).
        vols: Lognormal vol per forward rate.
        tenor: Accrual length of each forward (years).
        horizon: Simulation horizon (years, > 0).
        n_steps: Time steps to the horizon.
        n_simulations: Number of paths.
        seed: RNG seed.

    Returns:
        Dict with ``mean_terminal_rates`` and ``all_positive``.

    Raises:
        ValueError: If inputs are invalid.
    """
    f0 = np.asarray(forward_rates, dtype=np.float64)
    v = np.asarray(vols, dtype=np.float64)
    if f0.size != v.size:
        raise ValueError("forward_rates and vols must match length")
    if horizon <= 0 or tenor <= 0:
        raise ValueError("horizon and tenor must be positive")
    if np.any(f0 <= 0):
        raise ValueError("forward_rates must be positive")

    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((int(n_simulations), int(n_steps), f0.size)).astype(np.float64)
    terminal = _lmm_terminal_rates(f0, v, tenor, horizon, normals)
    mean_rates = np.mean(terminal, axis=0)
    return {
        "mean_terminal_rates": [round(float(r), 8) for r in mean_rates],
        "all_positive": bool(np.all(terminal > 0)),
    }

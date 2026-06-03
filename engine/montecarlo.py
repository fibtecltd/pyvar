"""
engine/montecarlo.py — Numba JIT Monte Carlo VaR engine

Reasoning:
- @njit(parallel=True) + prange compiles to LLVM machine code, giving
  10-100x speedup over pure Python for the inner simulation loop.
- The function is stateless and accepts/returns plain NumPy arrays,
  making it picklable for Celery workers and compatible with Ray actors.
- We pre-draw all random numbers in one vectorised call (np.random.randn)
  before entering the JIT region — this is faster than drawing inside the loop
  and avoids Numba's limited random number API.
- Returns the FULL sorted loss distribution, not just the scalar VaR,
  so callers can compute CVaR, percentile fans, and scenario analysis
  without re-running the simulation.
"""

import numpy as np
from numba import njit, prange


@njit(parallel=True, cache=True)
def _simulate_paths(
    returns: np.ndarray,  # shape (T,) — historical daily log-returns
    random_shocks: np.ndarray,  # shape (n_sims, horizon) — pre-drawn N(0,1)
    horizon: int,
) -> np.ndarray:
    """
    Core JIT kernel. Simulates n_sims portfolio P&L paths over `horizon` days
    using historical volatility scaling (parametric normal model).

    Each path compounds daily returns drawn from N(mu, sigma) fitted to
    the historical return series.

    Returns: shape (n_sims,) — total P&L for each simulation path.
    """
    mu = np.mean(returns)
    sigma = np.std(returns)
    n_sims = random_shocks.shape[0]

    pnl = np.zeros(n_sims)

    for i in prange(n_sims):  # prange → parallelised across CPU cores
        cumulative = 0.0
        for t in range(horizon):
            daily_return = mu + sigma * random_shocks[i, t]
            cumulative += daily_return
        pnl[i] = cumulative

    return pnl


@njit(cache=True)
def _sorted_losses(pnl: np.ndarray) -> np.ndarray:
    """
    Convert P&L array to sorted loss array (losses are positive values).
    Sorting inside JIT avoids a Python round-trip.
    """
    losses = -pnl  # flip sign: loss = negative P&L
    losses.sort()  # in-place ascending sort
    return losses


def run_monte_carlo_var(
    returns: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.99,
    horizon_days: int = 1,
    n_simulations: int = 100_000,
    seed: int | None = 42,
) -> dict:  # type: ignore[type-arg]
    """
    Public interface for the Monte Carlo VaR engine.

    Args:
        returns:          1-D array of historical daily log-returns (e.g. 252 obs)
        portfolio_value:  Current portfolio value in base currency (£, $, etc.)
        confidence_level: VaR confidence level, e.g. 0.99 for 99% VaR
        horizon_days:     Risk horizon in trading days (1, 5, 10, etc.)
        n_simulations:    Number of Monte Carlo paths (100k is standard)
        seed:             Random seed for reproducibility (None = random)

    Returns:
        dict with:
            var_pct       — VaR as % of portfolio value
            var_abs       — VaR in absolute currency terms
            cvar_pct      — CVaR (Expected Shortfall) as %
            cvar_abs      — CVaR in absolute currency terms
            loss_dist     — Full sorted loss distribution (% of portfolio)
            mu            — Fitted daily mean return
            sigma         — Fitted daily volatility
            n_simulations — Actual paths run
    """
    if seed is not None:
        np.random.seed(seed)

    returns = np.asarray(returns, dtype=np.float64)

    # Pre-draw all random shocks in one vectorised call (faster than inside JIT)
    random_shocks = np.random.randn(n_simulations, horizon_days)

    # Run the JIT-compiled parallel simulation
    pnl = _simulate_paths(returns, random_shocks, horizon_days)

    # Sort losses inside JIT (avoids Python round-trip)
    sorted_losses = _sorted_losses(pnl)

    # Compute VaR at confidence level
    var_idx = int(np.floor(confidence_level * n_simulations))
    var_idx = min(var_idx, n_simulations - 1)

    var_pct = float(sorted_losses[var_idx])
    cvar_pct = float(np.mean(sorted_losses[var_idx:]))  # Expected Shortfall

    return {
        "var_pct": round(var_pct, 6),
        "var_abs": round(var_pct * portfolio_value, 2),
        "cvar_pct": round(cvar_pct, 6),
        "cvar_abs": round(cvar_pct * portfolio_value, 2),
        "loss_dist": sorted_losses.tolist(),  # full distribution
        "mu": round(float(np.mean(returns)), 8),
        "sigma": round(float(np.std(returns)), 8),
        "n_simulations": n_simulations,
        "confidence_level": confidence_level,
        "horizon_days": horizon_days,
    }

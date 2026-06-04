"""engine/stress.py — Stress testing & scenario analysis (Market Risk).

First-order (delta) stress framework: portfolio P&L under a scenario is the dot
product of risk-factor exposures with factor shocks, ``pnl = exposures · shock``.
This covers historical replay, hypothetical multi-factor scenarios, reverse
stress, sensitivity profiles, sector shocks, correlated macro scenario
generation, and contagion propagation.

Numba rules (CLAUDE.md §3.1): all randomness for scenario generation is drawn
in pure Python (np.random) before any compiled region; these wrappers are pure
NumPy/SciPy and return Python types.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "historical_scenario_replay",
    "hypothetical_multi_factor_scenario",
    "reverse_stress_testing",
    "sensitivity_stress_profile",
    "sector_stress_scenario",
    "macro_scenario_generator",
    "contagion_stress_scenario",
]


def historical_scenario_replay(
    exposures: np.ndarray,
    historical_factor_returns: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Replay historical factor moves against the current portfolio.

    Applies each historical day's factor returns to the current exposures and
    reports the resulting P&L path, identifying the single worst day.

    Args:
        exposures: Length-F currency P&L per unit move of each risk factor.
        historical_factor_returns: ``(T, F)`` matrix of historical factor moves.

    Returns:
        Dict with ``worst_loss``, ``worst_scenario_index``, ``best_gain``,
        ``mean_pnl`` and the full ``pnl_path``.

    Raises:
        ValueError: If the factor dimensions are inconsistent.
    """
    e = np.asarray(exposures, dtype=np.float64)
    h = np.asarray(historical_factor_returns, dtype=np.float64)
    if h.ndim != 2 or h.shape[1] != e.size:
        raise ValueError("historical_factor_returns must be (T, F) matching exposures")

    pnl_path = h @ e
    worst_idx = int(np.argmin(pnl_path))
    return {
        "worst_loss": round(float(pnl_path[worst_idx]), 4),
        "worst_scenario_index": worst_idx,
        "best_gain": round(float(np.max(pnl_path)), 4),
        "mean_pnl": round(float(np.mean(pnl_path)), 4),
        "pnl_path": [round(float(p), 4) for p in pnl_path],
    }


def hypothetical_multi_factor_scenario(
    exposures: np.ndarray,
    shocks: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """P&L under a single hypothetical multi-factor shock.

    First-order P&L = Σ exposure_i * shock_i. Used for ad-hoc "what if" scenarios
    such as a simultaneous equity sell-off and rates spike.

    Args:
        exposures: Length-F currency P&L per unit factor move.
        shocks: Length-F factor shocks (same units as the historical moves).

    Returns:
        Dict with total ``pnl`` and per-factor ``factor_pnl`` contributions.

    Raises:
        ValueError: If exposures and shocks differ in length.
    """
    e = np.asarray(exposures, dtype=np.float64)
    s = np.asarray(shocks, dtype=np.float64)
    if e.size != s.size:
        raise ValueError("exposures and shocks must have the same length")

    factor_pnl = e * s
    return {
        "pnl": round(float(np.sum(factor_pnl)), 4),
        "factor_pnl": [round(float(p), 4) for p in factor_pnl],
    }


def reverse_stress_testing(
    exposures: np.ndarray,
    factor_cov: np.ndarray,
    target_loss: float,
) -> dict:  # type: ignore[type-arg]
    """Reverse stress test — find the most plausible scenario causing a target loss.

    Among all factor shocks producing the given loss, the most plausible (lowest
    Mahalanobis magnitude under the factor covariance) lies along ``-Σ e``. The
    closed-form solution for loss L is ``s* = -(L / e'Σe) · Σ e`` with magnitude
    ``m = L / sqrt(e'Σe)``.

    Args:
        exposures: Length-F currency P&L per unit factor move.
        factor_cov: ``(F, F)`` factor covariance matrix (SPD).
        target_loss: Desired loss magnitude (positive number).

    Returns:
        Dict with the ``shock`` vector, its Mahalanobis ``magnitude``, and the
        ``achieved_loss`` (which reproduces ``-target_loss`` P&L).

    Raises:
        ValueError: If shapes mismatch or ``target_loss`` <= 0.
    """
    e = np.asarray(exposures, dtype=np.float64)
    cov = np.asarray(factor_cov, dtype=np.float64)
    if cov.shape != (e.size, e.size):
        raise ValueError("factor_cov must be (F, F) matching exposures")
    if target_loss <= 0.0:
        raise ValueError("target_loss must be positive")

    cov_e = cov @ e
    quad = float(e @ cov_e)  # e' Σ e
    if quad <= 0.0:
        raise ValueError("e' Σ e must be positive (non-degenerate exposures)")

    shock = -(target_loss / quad) * cov_e
    achieved_loss = float(e @ shock)  # should equal -target_loss
    magnitude = target_loss / np.sqrt(quad)
    return {
        "shock": [round(float(s), 8) for s in shock],
        "magnitude": round(float(magnitude), 8),
        "achieved_loss": round(achieved_loss, 4),
        "target_loss": round(float(target_loss), 4),
    }


def sensitivity_stress_profile(
    exposures: np.ndarray,
    factor_index: int,
    shock_grid: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """One-factor sensitivity stress profile.

    Sweeps a single risk factor across a grid of shocks (holding others flat)
    and returns the P&L profile — the building block of a stress "ladder".

    Args:
        exposures: Length-F currency P&L per unit factor move.
        factor_index: Index of the factor to stress.
        shock_grid: 1-D grid of shock values to apply to that factor.

    Returns:
        Dict with ``shock_grid`` and the matching ``pnl_profile``.

    Raises:
        ValueError: If ``factor_index`` is out of range.
    """
    e = np.asarray(exposures, dtype=np.float64)
    grid = np.asarray(shock_grid, dtype=np.float64)
    if not 0 <= factor_index < e.size:
        raise ValueError("factor_index out of range")

    pnl_profile = e[factor_index] * grid
    return {
        "shock_grid": [round(float(g), 8) for g in grid],
        "pnl_profile": [round(float(p), 4) for p in pnl_profile],
        "factor_index": factor_index,
    }


def sector_stress_scenario(
    sector_exposures: np.ndarray,
    sector_shocks: np.ndarray,
    sector_names: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Sector-level stress scenario.

    Applies a shock to each sector's net exposure and aggregates. Total P&L is
    the exact sum of per-sector P&L (additivity by construction).

    Args:
        sector_exposures: Currency P&L per unit move, per sector.
        sector_shocks: Shock applied to each sector.
        sector_names: Optional sector labels; default ``sector_0, ...``.

    Returns:
        Dict with ``total_pnl`` and per-sector ``sector_pnl`` (name -> P&L).

    Raises:
        ValueError: If exposures and shocks differ in length.
    """
    e = np.asarray(sector_exposures, dtype=np.float64)
    s = np.asarray(sector_shocks, dtype=np.float64)
    if e.size != s.size:
        raise ValueError("sector_exposures and sector_shocks must match in length")
    if sector_names is None:
        sector_names = [f"sector_{i}" for i in range(e.size)]

    sector_pnl = e * s
    return {
        "total_pnl": round(float(np.sum(sector_pnl)), 4),
        "sector_pnl": {sector_names[i]: round(float(sector_pnl[i]), 4) for i in range(e.size)},
    }


def macro_scenario_generator(
    factor_cov: np.ndarray,
    n_scenarios: int = 10_000,
    seed: int | None = 42,
) -> dict:  # type: ignore[type-arg]
    """Generate correlated macro factor scenarios via the Cholesky factor.

    Draws standard-normal innovations in pure Python (CLAUDE.md §3.1 RULE 3) and
    colours them with the Cholesky factor of the supplied covariance so the
    generated scenarios reproduce the target factor correlation structure.

    Args:
        factor_cov: ``(F, F)`` macro-factor covariance matrix (SPD).
        n_scenarios: Number of scenarios to generate.
        seed: RNG seed for reproducibility (None = non-deterministic).

    Returns:
        Dict with the generated ``scenarios`` (list of F-vectors), the
        ``sample_cov`` of the draws, and ``n_scenarios``.

    Raises:
        ValueError: If ``factor_cov`` is not square or not positive definite.
    """
    cov = np.asarray(factor_cov, dtype=np.float64)
    if cov.ndim != 2 or cov.shape[0] != cov.shape[1]:
        raise ValueError("factor_cov must be a square matrix")
    try:
        chol = np.linalg.cholesky(cov)
    except np.linalg.LinAlgError as exc:
        raise ValueError("factor_cov must be positive definite") from exc

    rng = np.random.default_rng(seed)
    innovations = rng.standard_normal(size=(n_scenarios, cov.shape[0]))  # pre-drawn
    scenarios = innovations @ chol.T
    sample_cov = np.cov(scenarios, rowvar=False)
    return {
        "scenarios": scenarios.tolist(),
        "sample_cov": np.atleast_2d(sample_cov).tolist(),
        "n_scenarios": int(n_scenarios),
    }


def contagion_stress_scenario(
    initial_shock: np.ndarray,
    contagion_matrix: np.ndarray,
    rounds: int = 3,
) -> dict:  # type: ignore[type-arg]
    """Propagate an initial shock through a contagion (spillover) network.

    Each round, the current shock spills to connected nodes via the contagion
    matrix C; the cumulative shock is ``shock + C·shock + C²·shock + ...`` over
    the requested rounds — a truncated Neumann series of the spillover operator.

    Args:
        initial_shock: Length-N initial shock per node/asset.
        contagion_matrix: ``(N, N)`` spillover coefficients (C[i, j] = effect of
            node j on node i).
        rounds: Number of propagation rounds (``0`` returns the initial shock).

    Returns:
        Dict with the ``amplified_shock`` and the ``amplification_factor``
        (L2 norm ratio vs the initial shock).

    Raises:
        ValueError: If shapes are inconsistent or ``rounds`` < 0.
    """
    x0 = np.asarray(initial_shock, dtype=np.float64)
    c = np.asarray(contagion_matrix, dtype=np.float64)
    if c.shape != (x0.size, x0.size):
        raise ValueError("contagion_matrix must be (N, N) matching initial_shock")
    if rounds < 0:
        raise ValueError("rounds must be >= 0")

    cumulative = x0.copy()
    current = x0.copy()
    for _ in range(rounds):
        current = c @ current
        cumulative = cumulative + current

    initial_norm = float(np.linalg.norm(x0))
    amp = float(np.linalg.norm(cumulative)) / initial_norm if initial_norm > 0.0 else 0.0
    return {
        "amplified_shock": [round(float(v), 8) for v in cumulative],
        "amplification_factor": round(amp, 8),
        "rounds": int(rounds),
    }

"""engine/oprisk_scenario.py — OpRisk scenario analysis.

Implements the scenario-analysis sub-domain: the headline scenario-analysis
capital estimate, expert elicitation aggregation, and severity / frequency
estimation from expert judgement. Scenario analysis supplements sparse internal
loss data for rare high-impact tail events under the AMA / SMA frameworks.

Severity calibration from percentile estimates uses a lognormal closed form and
the scenario capital uses a small Monte Carlo. Per CLAUDE.md §3.1 RULE 3 any
random draws are generated in pure Python (NumPy); the routines here are
otherwise light analytics so no @njit kernel is required.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

__all__ = [
    "scenario_analysis_oprisk",
    "scenario_expert_elicitation_model",
    "scenario_severity_estimation",
    "scenario_frequency_estimation",
]


def scenario_frequency_estimation(
    expected_events_per_year: float,
    occurrences: int | None = None,
    observation_years: float | None = None,
) -> dict:  # type: ignore[type-arg]
    """Estimate a scenario's annual frequency (Poisson lambda).

    Uses the expert's expected events per year directly, or — if historical
    occurrence data is supplied — the empirical rate ``occurrences /
    observation_years``. The result is the Poisson lambda feeding the scenario's
    compound loss.

    Args:
        expected_events_per_year: Expert estimate of the annual event rate.
        occurrences: Optional observed event count.
        observation_years: Optional observation window in years (> 0).

    Returns:
        Dict with ``lambda`` and ``source`` (``"expert"`` or ``"empirical"``).

    Raises:
        ValueError: If estimates are negative or the observation window is
            non-positive when occurrences are given.
    """
    if expected_events_per_year < 0:
        raise ValueError("expected_events_per_year must be non-negative")
    if occurrences is not None:
        if observation_years is None or observation_years <= 0:
            raise ValueError("observation_years must be positive when occurrences given")
        if occurrences < 0:
            raise ValueError("occurrences must be non-negative")
        lam = occurrences / observation_years
        source = "empirical"
    else:
        lam = expected_events_per_year
        source = "expert"
    return {"lambda": round(float(lam), 6), "source": source}


def scenario_severity_estimation(
    typical_loss: float,
    worst_case_loss: float,
    worst_case_percentile: float = 0.99,
) -> dict:  # type: ignore[type-arg]
    """Calibrate a lognormal severity from expert typical / worst-case losses.

    Treats ``typical_loss`` as the lognormal median (so ``mu = ln(typical)``) and
    solves for ``sigma`` from the worst-case percentile:
    ``sigma = (ln(worst) − mu) / z_p``. This is the standard two-point expert
    calibration for scenario severities.

    Args:
        typical_loss: Median ("typical") loss (> 0).
        worst_case_loss: High-percentile loss (> typical).
        worst_case_percentile: Percentile of the worst case, in (0.5, 1).

    Returns:
        Dict with ``mu``, ``sigma`` and the implied ``mean_severity``.

    Raises:
        ValueError: If losses are non-positive, worst <= typical, or the
            percentile is outside (0.5, 1).
    """
    if typical_loss <= 0 or worst_case_loss <= 0:
        raise ValueError("losses must be positive")
    if worst_case_loss <= typical_loss:
        raise ValueError("worst_case_loss must exceed typical_loss")
    if not 0.5 < worst_case_percentile < 1.0:
        raise ValueError("worst_case_percentile must lie in (0.5, 1)")

    mu = float(np.log(typical_loss))
    z = float(stats.norm.ppf(worst_case_percentile))
    sigma = (float(np.log(worst_case_loss)) - mu) / z
    mean_sev = float(np.exp(mu + 0.5 * sigma**2))
    return {
        "mu": round(mu, 6),
        "sigma": round(sigma, 6),
        "mean_severity": round(mean_sev, 4),
    }


def scenario_expert_elicitation_model(
    expert_estimates: np.ndarray,
    expert_weights: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Aggregate expert loss estimates into a consensus with dispersion.

    Combines multiple experts' point estimates into a weighted consensus and
    reports the dispersion (weighted standard deviation) as a confidence proxy —
    wide disagreement signals an unreliable scenario.

    Args:
        expert_estimates: Each expert's loss estimate.
        expert_weights: Optional credibility weights (default equal).

    Returns:
        Dict with ``consensus`` (weighted mean), ``dispersion`` and
        ``coefficient_of_variation``.

    Raises:
        ValueError: If estimates are empty or weights mismatch / sum to zero.
    """
    est = np.asarray(expert_estimates, dtype=np.float64)
    if est.size == 0:
        raise ValueError("expert_estimates must be non-empty")
    if expert_weights is None:
        w = np.ones_like(est)
    else:
        w = np.asarray(expert_weights, dtype=np.float64)
        if w.shape != est.shape:
            raise ValueError("expert_weights must match expert_estimates length")
    total_w = float(np.sum(w))
    if total_w <= 0:
        raise ValueError("expert_weights must sum to a positive value")

    consensus = float(np.sum(est * w) / total_w)
    variance = float(np.sum(w * (est - consensus) ** 2) / total_w)
    dispersion = float(np.sqrt(variance))
    cov = dispersion / consensus if consensus != 0 else 0.0
    return {
        "consensus": round(consensus, 4),
        "dispersion": round(dispersion, 4),
        "coefficient_of_variation": round(cov, 6),
    }


def scenario_analysis_oprisk(
    frequency_lambda: float,
    severity_mu: float,
    severity_sigma: float,
    confidence_level: float = 0.999,
    n_years: int = 50_000,
    seed: int | None = 42,
) -> dict:  # type: ignore[type-arg]
    """Scenario-based OpRisk capital via a compound Monte Carlo.

    Builds a single scenario's aggregate annual loss distribution from its
    calibrated frequency and lognormal severity and reads the loss quantile —
    the scenario's contribution to capital. Per RULE 3 randomness is pre-drawn
    in pure Python.

    Args:
        frequency_lambda: Poisson annual frequency (> 0).
        severity_mu: Lognormal log-mean severity.
        severity_sigma: Lognormal log-std severity (> 0).
        confidence_level: Capital confidence in [0.90, 0.9999].
        n_years: Number of simulated years.
        seed: RNG seed for reproducibility.

    Returns:
        Dict with ``scenario_var`` (quantile), ``expected_loss`` and
        ``expected_shortfall``.

    Raises:
        ValueError: If lambda/sigma are non-positive or confidence is out of
            range.
    """
    if frequency_lambda <= 0:
        raise ValueError("frequency_lambda must be positive")
    if severity_sigma <= 0:
        raise ValueError("severity_sigma must be positive")
    if not 0.90 <= confidence_level <= 0.9999:
        raise ValueError("confidence_level must lie in [0.90, 0.9999]")

    rng = np.random.default_rng(seed)
    counts = rng.poisson(frequency_lambda, size=n_years)
    annual = np.empty(n_years, dtype=np.float64)
    for y in range(n_years):
        c = int(counts[y])
        if c == 0:
            annual[y] = 0.0
        else:
            annual[y] = float(np.sum(rng.lognormal(severity_mu, severity_sigma, size=c)))
    annual.sort()
    idx = min(int(np.floor(confidence_level * n_years)), n_years - 1)
    return {
        "scenario_var": round(float(annual[idx]), 2),
        "expected_loss": round(float(np.mean(annual)), 2),
        "expected_shortfall": round(float(np.mean(annual[idx:])), 2),
        "confidence_level": confidence_level,
    }

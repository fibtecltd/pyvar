"""engine/oprisk_lda.py — Loss Distribution Approach (LDA) core.

Implements the actuarial LDA engine: distribution fitting (frequency and
severity), the compound loss distribution (frequency ⊗ severity), Monte Carlo
OpVaR / OpRisk capital, the AMA wrapper, and the generic OpVaR reader.

LDA is genuinely array-heavy Monte Carlo, so the inner aggregation of per-year
loss draws is an ``@njit`` kernel (CLAUDE.md §3.1): stateless, float64 arrays
only, ``cache=True``. Per RULE 3 the Poisson frequencies and severity draws are
generated in pure Python (NumPy / SciPy) BEFORE entering the JIT region, then
passed as flat arrays with an index layout the kernel sums.
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "frequency_distribution_fitting",
    "severity_distribution_fitting",
    "compound_loss_distribution",
    "monte_carlo_oprisk_capital",
    "operational_var_opvar",
    "loss_distribution_approach_lda",
    "advanced_measurement_approach_ama",
]


@njit(cache=True)
def _aggregate_annual_losses(
    severities: np.ndarray,
    counts: np.ndarray,
) -> np.ndarray:
    """Sum pre-drawn severity draws into per-year aggregate losses.

    ``counts[y]`` is the number of loss events simulated for year ``y``; the
    matching severities are laid out contiguously in ``severities`` (RULE 3:
    drawn in pure Python first). The kernel walks the flat array once — a pure
    loop-carried sum, returning a float64 array (RULE 5).
    """
    n_years = counts.shape[0]
    annual = np.zeros(n_years, dtype=np.float64)
    pos = 0
    for y in range(n_years):
        c = counts[y]
        total = 0.0
        for _ in range(c):
            total += severities[pos]
            pos += 1
        annual[y] = total
    return annual


def frequency_distribution_fitting(
    annual_event_counts: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Fit a Poisson frequency distribution to annual loss-event counts.

    The Poisson MLE for lambda is the sample mean of annual counts. Also reports
    the variance-to-mean ratio (dispersion) — a value far above 1 signals
    over-dispersion and a possible negative-binomial alternative.

    Args:
        annual_event_counts: Observed number of loss events per year.

    Returns:
        Dict with ``distribution`` (``"poisson"``), ``lambda`` (MLE) and
        ``dispersion`` (var/mean).

    Raises:
        ValueError: If the array is empty or contains negative counts.
    """
    counts = np.asarray(annual_event_counts, dtype=np.float64)
    if counts.size == 0:
        raise ValueError("annual_event_counts must be non-empty")
    if np.any(counts < 0):
        raise ValueError("counts must be non-negative")

    lam = float(np.mean(counts))
    var = float(np.var(counts))
    dispersion = var / lam if lam > 0 else 0.0
    return {
        "distribution": "poisson",
        "lambda": round(lam, 6),
        "dispersion": round(dispersion, 6),
    }


def severity_distribution_fitting(
    loss_amounts: np.ndarray,
    distribution: str = "lognormal",
) -> dict:  # type: ignore[type-arg]
    """Fit a severity distribution to individual loss amounts.

    Supports the lognormal (default, the OpRisk industry standard) by MLE of the
    log-loss mean/sigma. Returns the fitted parameters and the implied mean
    severity.

    Args:
        loss_amounts: Strictly positive individual loss amounts.
        distribution: Severity family; currently ``"lognormal"``.

    Returns:
        Dict with ``distribution``, ``mu``, ``sigma`` and ``mean_severity``.

    Raises:
        ValueError: If losses are non-positive or the family is unsupported.
    """
    losses = np.asarray(loss_amounts, dtype=np.float64)
    if losses.size == 0 or np.any(losses <= 0):
        raise ValueError("loss_amounts must be non-empty and strictly positive")
    if distribution != "lognormal":
        raise ValueError("only 'lognormal' severity is currently supported")

    log_losses = np.log(losses)
    mu = float(np.mean(log_losses))
    sigma = float(np.std(log_losses))
    mean_sev = float(np.exp(mu + 0.5 * sigma**2))
    return {
        "distribution": "lognormal",
        "mu": round(mu, 6),
        "sigma": round(sigma, 6),
        "mean_severity": round(mean_sev, 4),
    }


def compound_loss_distribution(
    frequency_lambda: float,
    severity_mu: float,
    severity_sigma: float,
    n_years: int = 50_000,
    seed: int | None = 42,
) -> dict:  # type: ignore[type-arg]
    """Simulate the compound (aggregate) annual loss distribution.

    The classic frequency ⊗ severity convolution: for each simulated year draw a
    Poisson(lambda) number of events, then that many lognormal(mu, sigma)
    severities, and sum. Per RULE 3 all randomness is pre-drawn in pure Python;
    the per-year aggregation runs in the JIT kernel.

    Args:
        frequency_lambda: Poisson annual event rate (> 0).
        severity_mu: Lognormal log-mean of severities.
        severity_sigma: Lognormal log-std of severities (> 0).
        n_years: Number of simulated years.
        seed: RNG seed for reproducibility.

    Returns:
        Dict with ``mean_annual_loss``, ``std_annual_loss``, ``annual_losses``
        (sorted ascending) and ``n_years``.

    Raises:
        ValueError: If lambda <= 0 or sigma <= 0.
    """
    if frequency_lambda <= 0:
        raise ValueError("frequency_lambda must be positive")
    if severity_sigma <= 0:
        raise ValueError("severity_sigma must be positive")

    rng = np.random.default_rng(seed)
    counts = rng.poisson(frequency_lambda, size=n_years).astype(np.int64)
    total_events = int(np.sum(counts))
    severities = rng.lognormal(severity_mu, severity_sigma, size=total_events)
    annual = _aggregate_annual_losses(severities, counts)
    annual.sort()
    return {
        "mean_annual_loss": round(float(np.mean(annual)), 4),
        "std_annual_loss": round(float(np.std(annual)), 4),
        "annual_losses": annual,
        "n_years": n_years,
    }


def monte_carlo_oprisk_capital(
    frequency_lambda: float,
    severity_mu: float,
    severity_sigma: float,
    confidence_level: float = 0.999,
    n_years: int = 100_000,
    seed: int | None = 42,
) -> dict:  # type: ignore[type-arg]
    """Monte Carlo OpRisk regulatory capital (OpVaR + expected shortfall).

    Builds the compound loss distribution and reads the loss quantile at the
    regulatory confidence (Basel AMA uses 99.9% over a one-year horizon). Capital
    is the unexpected loss = OpVaR minus expected loss.

    Args:
        frequency_lambda: Poisson annual event rate (> 0).
        severity_mu: Lognormal log-mean of severities.
        severity_sigma: Lognormal log-std of severities (> 0).
        confidence_level: Capital confidence (Basel AMA 99.9%); in [0.90, 0.9999].
        n_years: Number of simulated years.
        seed: RNG seed for reproducibility.

    Returns:
        Dict with ``opvar`` (quantile), ``expected_loss``, ``capital`` (UL),
        ``expected_shortfall`` and ``confidence_level``.

    Raises:
        ValueError: If confidence is out of range.
    """
    if not 0.90 <= confidence_level <= 0.9999:
        raise ValueError("confidence_level must lie in [0.90, 0.9999]")

    sim = compound_loss_distribution(
        frequency_lambda, severity_mu, severity_sigma, n_years=n_years, seed=seed
    )
    annual = sim["annual_losses"]
    idx = min(int(np.floor(confidence_level * n_years)), n_years - 1)
    opvar = float(annual[idx])
    expected_loss = float(np.mean(annual))
    es = float(np.mean(annual[idx:]))
    return {
        "opvar": round(opvar, 2),
        "expected_loss": round(expected_loss, 2),
        "capital": round(max(opvar - expected_loss, 0.0), 2),
        "expected_shortfall": round(es, 2),
        "confidence_level": confidence_level,
        "n_years": n_years,
    }


def operational_var_opvar(
    annual_losses: np.ndarray,
    confidence_level: float = 0.999,
) -> dict:  # type: ignore[type-arg]
    """Operational VaR from an empirical aggregate-loss sample.

    Reads the loss quantile at the confidence level directly from a supplied
    (e.g. simulated or historical) annual-loss array — the generic OpVaR reader.

    Args:
        annual_losses: Sample of aggregate annual losses.
        confidence_level: Confidence in [0.90, 0.9999].

    Returns:
        Dict with ``opvar``, ``expected_shortfall`` and ``expected_loss``.

    Raises:
        ValueError: If the sample is empty or confidence is out of range.
    """
    losses = np.asarray(annual_losses, dtype=np.float64)
    if losses.size == 0:
        raise ValueError("annual_losses must be non-empty")
    if not 0.90 <= confidence_level <= 0.9999:
        raise ValueError("confidence_level must lie in [0.90, 0.9999]")

    sorted_losses = np.sort(losses)
    n = sorted_losses.size
    idx = min(int(np.floor(confidence_level * n)), n - 1)
    opvar = float(sorted_losses[idx])
    es = float(np.mean(sorted_losses[idx:]))
    return {
        "opvar": round(opvar, 2),
        "expected_shortfall": round(es, 2),
        "expected_loss": round(float(np.mean(sorted_losses)), 2),
        "confidence_level": confidence_level,
    }


def loss_distribution_approach_lda(
    annual_event_counts: np.ndarray,
    loss_amounts: np.ndarray,
    confidence_level: float = 0.999,
    n_years: int = 100_000,
    seed: int | None = 42,
) -> dict:  # type: ignore[type-arg]
    """End-to-end Loss Distribution Approach capital estimate.

    Fits the frequency (Poisson) and severity (lognormal) distributions from
    historical data, simulates the compound distribution and reads OpVaR /
    capital at the regulatory confidence — the full LDA pipeline in one call.

    Args:
        annual_event_counts: Historical annual loss-event counts.
        loss_amounts: Historical individual loss amounts (positive).
        confidence_level: Capital confidence (Basel AMA 99.9%).
        n_years: Number of simulated years.
        seed: RNG seed for reproducibility.

    Returns:
        Dict with ``frequency`` (fit), ``severity`` (fit), ``opvar``, ``capital``
        and ``expected_loss``.

    Raises:
        ValueError: If inputs are invalid (propagated from the fitters).
    """
    freq = frequency_distribution_fitting(annual_event_counts)
    sev = severity_distribution_fitting(loss_amounts)
    cap = monte_carlo_oprisk_capital(
        freq["lambda"],
        sev["mu"],
        sev["sigma"],
        confidence_level=confidence_level,
        n_years=n_years,
        seed=seed,
    )
    return {
        "frequency": freq,
        "severity": sev,
        "opvar": cap["opvar"],
        "capital": cap["capital"],
        "expected_loss": cap["expected_loss"],
        "confidence_level": confidence_level,
    }


def advanced_measurement_approach_ama(
    annual_event_counts: np.ndarray,
    loss_amounts: np.ndarray,
    expected_loss_covered: bool = True,
    confidence_level: float = 0.999,
    n_years: int = 100_000,
    seed: int | None = 42,
) -> dict:  # type: ignore[type-arg]
    """Advanced Measurement Approach (AMA) capital charge.

    The AMA permits the LDA internal model. Under Basel II §669(b), if a bank can
    demonstrate that expected loss (EL) is already captured in its provisioning /
    pricing, capital may be set to unexpected loss only (OpVaR − EL); otherwise
    capital equals the full OpVaR.

    Args:
        annual_event_counts: Historical annual loss-event counts.
        loss_amounts: Historical individual loss amounts (positive).
        expected_loss_covered: Whether EL is demonstrably covered in provisions.
        confidence_level: Capital confidence (99.9%).
        n_years: Number of simulated years.
        seed: RNG seed for reproducibility.

    Returns:
        Dict with ``ama_capital``, ``opvar``, ``expected_loss`` and
        ``el_covered``.

    Raises:
        ValueError: If inputs are invalid (propagated).
    """
    lda = loss_distribution_approach_lda(
        annual_event_counts,
        loss_amounts,
        confidence_level=confidence_level,
        n_years=n_years,
        seed=seed,
    )
    opvar = lda["opvar"]
    el = lda["expected_loss"]
    capital = lda["capital"] if expected_loss_covered else opvar
    return {
        "ama_capital": round(float(capital), 2),
        "opvar": opvar,
        "expected_loss": el,
        "el_covered": expected_loss_covered,
        "confidence_level": confidence_level,
    }

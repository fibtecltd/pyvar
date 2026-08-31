"""engine/credit_var.py — Portfolio credit-risk models (Credit VaR family).

Implements the portfolio-loss sub-domain: Monte-Carlo Credit VaR under a
Gaussian one-factor copula, the analytical Vasicek large-homogeneous-portfolio
formula, a simplified CreditMetrics migration model, the Merton/KMV
distance-to-default, a default-correlation matrix builder and the
Herfindahl-Hirschman concentration index.

Numba rules (CLAUDE.md §3.1) are honoured exactly:
  * The systematic / idiosyncratic standard-normal draws are produced in pure
    Python (RULE 3) and passed to the JIT kernel as float64 arrays.
  * ``@njit(parallel=True, cache=True)`` is used for the simulation loop with
    ``prange``; kernels return only NumPy arrays.

Regulatory note: Credit VaR is reported with Expected Shortfall computed as the
MEAN loss beyond the VaR threshold (CLAUDE.md §4.2), never the median or max.
"""

from __future__ import annotations

import numpy as np
from numba import njit, prange
from scipy import stats

__all__ = [
    "credit_var_monte_carlo",
    "credit_var_analytical_vasicek",
    "creditmetrics_portfolio_model",
    "kmv_merton_distance_to_default",
    "default_correlation_matrix",
    "credit_concentration_risk_hhi",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(parallel=True, cache=True)
def _simulate_portfolio_losses(
    pd: np.ndarray,
    lgd: np.ndarray,
    ead: np.ndarray,
    sqrt_rho: np.ndarray,
    default_threshold: np.ndarray,
    systematic: np.ndarray,
    idiosyncratic: np.ndarray,
) -> np.ndarray:
    """One-factor Gaussian-copula portfolio loss simulation.

    Asset value ``A_i = sqrt(rho_i) * M + sqrt(1-rho_i) * Z_i`` defaults when it
    falls below ``N^{-1}(PD_i)``. Pre-drawn standard normals ``M`` (systematic)
    and ``Z`` (idiosyncratic) are supplied per RULE 3.

    Args:
        pd: Per-obligor PD (unused directly; threshold pre-computed).
        lgd: Per-obligor LGD.
        ead: Per-obligor EAD.
        sqrt_rho: Per-obligor sqrt of asset correlation.
        default_threshold: Per-obligor ``N^{-1}(PD_i)``.
        systematic: ``(n_sims,)`` systematic factor draws.
        idiosyncratic: ``(n_sims, n_obligors)`` idiosyncratic draws.

    Returns:
        Float64 array of portfolio losses, one per simulation (RULE 5).
    """
    n_sims = systematic.shape[0]
    n_obligors = pd.shape[0]
    losses = np.zeros(n_sims, dtype=np.float64)
    for s in prange(n_sims):
        total = 0.0
        m = systematic[s]
        for i in range(n_obligors):
            sqrt_one_minus = np.sqrt(1.0 - sqrt_rho[i] * sqrt_rho[i])
            asset = sqrt_rho[i] * m + sqrt_one_minus * idiosyncratic[s, i]
            if asset < default_threshold[i]:
                total += lgd[i] * ead[i]
        losses[s] = total
    return losses


@njit(cache=True)
def _var_es_from_sorted(sorted_losses: np.ndarray, confidence_level: float) -> np.ndarray:
    """VaR and ES (mean beyond VaR) from an ascending sorted loss array."""
    n = sorted_losses.shape[0]
    idx = int(np.floor(confidence_level * n))
    if idx > n - 1:
        idx = n - 1
    var = sorted_losses[idx]
    tail_sum = 0.0
    count = 0
    for i in range(idx, n):
        tail_sum += sorted_losses[i]
        count += 1
    es = tail_sum / count if count > 0 else var
    out = np.empty(2, dtype=np.float64)
    out[0] = var
    out[1] = es
    return out


# ── Public functions ─────────────────────────────────────────────────────────


def credit_var_monte_carlo(
    pd: np.ndarray,
    lgd: np.ndarray,
    ead: np.ndarray,
    asset_correlation: float | np.ndarray = 0.15,
    confidence_level: float = 0.999,
    n_simulations: int = 50_000,
    seed: int = 12345,
) -> dict:  # type: ignore[type-arg]
    """Monte-Carlo Credit VaR under a one-factor Gaussian copula.

    Simulates correlated defaults, aggregates ``LGD * EAD`` losses, and reads
    the loss quantile (VaR) and the mean tail loss (ES / CVaR). Expected Loss is
    the simulation mean; Unexpected Loss is ``VaR - EL`` (economic-capital
    convention).

    Args:
        pd: Per-obligor probability of default in ``(0, 1)``.
        lgd: Per-obligor loss given default in ``[0, 1]``.
        ead: Per-obligor exposure at default (>= 0).
        asset_correlation: Scalar or per-obligor asset correlation rho in
            ``[0, 1)``.
        confidence_level: VaR confidence in ``[0.90, 0.9999]`` (Basel 99.9%).
        n_simulations: Number of Monte-Carlo paths.
        seed: RNG seed for reproducibility.

    Returns:
        Dict with ``var``, ``cvar`` (ES, mean beyond VaR), ``el`` (mean loss),
        ``ul`` (= VaR - EL), ``loss_std`` and ``n_simulations``.

    Raises:
        ValueError: If array shapes mismatch or parameters are out of range.
    """
    p = np.asarray(pd, dtype=np.float64)
    lgd_arr = np.asarray(lgd, dtype=np.float64)
    e = np.asarray(ead, dtype=np.float64)
    if not (p.shape == lgd_arr.shape == e.shape) or p.size == 0:
        raise ValueError("pd, lgd, ead must share the same non-empty shape")
    if np.any((p <= 0.0) | (p >= 1.0)):
        raise ValueError("pd must lie in (0, 1)")
    if not 0.90 <= confidence_level <= 0.9999:
        raise ValueError("confidence_level must be in [0.90, 0.9999]")

    n = p.size
    if np.isscalar(asset_correlation):
        rho = np.full(n, float(asset_correlation), dtype=np.float64)  # type: ignore[arg-type]
    else:
        rho = np.asarray(asset_correlation, dtype=np.float64)
        if rho.shape != p.shape:
            raise ValueError("asset_correlation array must match pd shape")
    if np.any((rho < 0.0) | (rho >= 1.0)):
        raise ValueError("asset_correlation must lie in [0, 1)")

    sqrt_rho = np.sqrt(rho)
    threshold = stats.norm.ppf(p).astype(np.float64)

    # RULE 3: pre-draw all randomness in pure Python before the JIT region.
    rng = np.random.default_rng(seed)
    systematic = rng.standard_normal(n_simulations).astype(np.float64)
    idiosyncratic = rng.standard_normal((n_simulations, n)).astype(np.float64)

    losses = _simulate_portfolio_losses(
        p, lgd_arr, e, sqrt_rho, threshold, systematic, idiosyncratic
    )
    sorted_losses = np.sort(losses)
    var, es = _var_es_from_sorted(sorted_losses, confidence_level)
    el = float(np.mean(losses))
    return {
        "var": round(float(var), 6),
        "cvar": round(float(es), 6),
        "el": round(el, 6),
        "ul": round(float(var) - el, 6),
        "loss_std": round(float(np.std(losses)), 6),
        "confidence_level": confidence_level,
        "n_simulations": int(n_simulations),
    }


def credit_var_analytical_vasicek(
    pd: float,
    lgd: float,
    ead_total: float,
    asset_correlation: float = 0.15,
    confidence_level: float = 0.999,
) -> dict:  # type: ignore[type-arg]
    """Analytical Vasicek large-homogeneous-portfolio Credit VaR.

    The Vasicek (2002) asymptotic single-risk-factor loss rate at confidence q is
    ``L(q) = LGD * N( (N^{-1}(PD) + sqrt(rho) N^{-1}(q)) / sqrt(1-rho) )`` — the
    same conditional-default formula underlying the Basel IRB charge. VaR is the
    loss rate times total EAD; UL is the VaR in excess of EL.

    Args:
        pd: Portfolio probability of default in ``(0, 1)``.
        lgd: Loss given default in ``[0, 1]``.
        ead_total: Total portfolio exposure at default (>= 0).
        asset_correlation: Asset correlation rho in ``[0, 1)``.
        confidence_level: VaR confidence in ``[0.90, 0.9999]``.

    Returns:
        Dict with ``var``, ``el``, ``ul``, ``loss_rate_q`` (the worst-case
        conditional default rate) and ``confidence_level``.

    Raises:
        ValueError: If parameters are out of range.
    """
    if not 0.0 < pd < 1.0:
        raise ValueError("pd must be in (0, 1)")
    if not 0.0 <= lgd <= 1.0:
        raise ValueError("lgd must be in [0, 1]")
    if not 0.0 <= asset_correlation < 1.0:
        raise ValueError("asset_correlation must be in [0, 1)")
    if not 0.90 <= confidence_level <= 0.9999:
        raise ValueError("confidence_level must be in [0.90, 0.9999]")

    n_inv_pd = float(stats.norm.ppf(pd))
    n_inv_q = float(stats.norm.ppf(confidence_level))
    rho = asset_correlation
    conditional = (n_inv_pd + np.sqrt(rho) * n_inv_q) / np.sqrt(1.0 - rho)
    loss_rate_q = lgd * float(stats.norm.cdf(conditional))
    var = loss_rate_q * ead_total
    el = pd * lgd * ead_total
    return {
        "var": round(float(var), 6),
        "el": round(float(el), 6),
        "ul": round(float(var) - float(el), 6),
        "loss_rate_q": round(loss_rate_q, 10),
        "confidence_level": confidence_level,
    }


def creditmetrics_portfolio_model(
    exposures: np.ndarray,
    pd: np.ndarray,
    lgd: np.ndarray,
    asset_correlation: float = 0.20,
    confidence_level: float = 0.99,
    n_simulations: int = 20_000,
    seed: int = 2024,
) -> dict:  # type: ignore[type-arg]
    """Simplified CreditMetrics (two-state) portfolio loss distribution.

    A default/no-default reduction of J.P. Morgan's CreditMetrics: latent asset
    returns are driven by a single common factor; an obligor defaults when its
    return breaches ``N^{-1}(PD)``, incurring ``LGD * exposure``. The full model
    uses a multi-state rating-migration matrix — handled separately by
    :func:`engine.credit_scoring.ratings_migration_matrix` — but the loss tail is
    dominated by the default state captured here.

    In implementation this is a direct pass-through to the same one-factor
    Gaussian-copula Monte Carlo engine used by
    :func:`credit_var_monte_carlo` (identical formula, identical code path),
    not a separately coded multi-state model.

    Args:
        exposures: Per-obligor exposure (>= 0).
        pd: Per-obligor PD in ``(0, 1)``.
        lgd: Per-obligor LGD in ``[0, 1]``.
        asset_correlation: Common-factor asset correlation in ``[0, 1)``.
        confidence_level: VaR confidence in ``[0.90, 0.9999]``.
        n_simulations: Number of Monte-Carlo paths.
        seed: RNG seed.

    Returns:
        Dict with ``var``, ``cvar`` (mean beyond VaR), ``el``, ``ul`` and
        ``loss_std``.

    Raises:
        ValueError: If shapes mismatch or parameters are out of range.
    """
    return credit_var_monte_carlo(
        pd=pd,
        lgd=lgd,
        ead=exposures,
        asset_correlation=asset_correlation,
        confidence_level=confidence_level,
        n_simulations=n_simulations,
        seed=seed,
    )


def kmv_merton_distance_to_default(
    asset_value: float,
    debt_face_value: float,
    asset_volatility: float,
    risk_free_rate: float = 0.0,
    asset_drift: float | None = None,
    horizon: float = 1.0,
) -> dict:  # type: ignore[type-arg]
    """Merton / KMV distance-to-default and implied PD.

    In the structural Merton model the firm defaults at horizon T if asset value
    falls below the debt face value. The distance-to-default is
    ``DD = (ln(V/D) + (mu - 0.5 sigma^2) T) / (sigma sqrt(T))`` and the model PD
    (expected default frequency) is ``N(-DD)``.

    Args:
        asset_value: Current market value of firm assets V (> 0).
        debt_face_value: Default boundary / debt face value D (> 0).
        asset_volatility: Annualised asset return volatility sigma (> 0).
        risk_free_rate: Risk-free rate (used when ``asset_drift`` is None).
        asset_drift: Expected asset return mu; defaults to ``risk_free_rate``.
        horizon: Horizon T in years (> 0).

    Returns:
        Dict with ``distance_to_default``, ``pd`` (= ``N(-DD)``) and the
        ``leverage`` ratio ``D/V``.

    Raises:
        ValueError: If values, volatility or horizon are non-positive.
    """
    if asset_value <= 0.0 or debt_face_value <= 0.0:
        raise ValueError("asset_value and debt_face_value must be positive")
    if asset_volatility <= 0.0:
        raise ValueError("asset_volatility must be positive")
    if horizon <= 0.0:
        raise ValueError("horizon must be positive")

    mu = risk_free_rate if asset_drift is None else asset_drift
    dd = (np.log(asset_value / debt_face_value) + (mu - 0.5 * asset_volatility**2) * horizon) / (
        asset_volatility * np.sqrt(horizon)
    )
    pd = float(stats.norm.cdf(-dd))
    return {
        "distance_to_default": round(float(dd), 10),
        "pd": round(pd, 12),
        "leverage": round(debt_face_value / asset_value, 10),
        "horizon": horizon,
    }


def default_correlation_matrix(
    pd: np.ndarray,
    asset_correlation: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Pairwise default correlation from asset correlations (Gaussian copula).

    The default correlation between two obligors is
    ``rho_D = (P(both default) - PD_i PD_j) / sqrt(PD_i(1-PD_i) PD_j(1-PD_j))``
    where the joint default probability is the bivariate normal CDF
    ``Phi_2(N^{-1}(PD_i), N^{-1}(PD_j); rho_A)`` with asset correlation rho_A.

    Args:
        pd: Per-obligor PD in ``(0, 1)``.
        asset_correlation: Symmetric ``(n, n)`` asset-correlation matrix with
            unit diagonal, entries in ``[-1, 1]``.

    Returns:
        Dict with ``matrix`` (nested list of default correlations, unit
        diagonal) and ``n``.

    Raises:
        ValueError: If shapes mismatch or PD is out of range.
    """
    p = np.asarray(pd, dtype=np.float64)
    a = np.asarray(asset_correlation, dtype=np.float64)
    n = p.size
    if n == 0 or a.shape != (n, n):
        raise ValueError("asset_correlation must be (n, n) matching pd")
    if np.any((p <= 0.0) | (p >= 1.0)):
        raise ValueError("pd must lie in (0, 1)")

    thr = stats.norm.ppf(p)
    denom = np.sqrt(p * (1.0 - p))
    out = np.eye(n, dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            rho_a = min(max(a[i, j], -0.999999), 0.999999)
            mean = np.zeros(2)
            cov = np.array([[1.0, rho_a], [rho_a, 1.0]])
            joint = float(stats.multivariate_normal(mean=mean, cov=cov).cdf([thr[i], thr[j]]))
            rho_d = (joint - p[i] * p[j]) / (denom[i] * denom[j])
            out[i, j] = rho_d
            out[j, i] = rho_d
    return {
        "matrix": [[round(float(out[i, j]), 10) for j in range(n)] for i in range(n)],
        "n": int(n),
    }


def credit_concentration_risk_hhi(
    exposures: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Herfindahl-Hirschman concentration index of a credit portfolio.

    ``HHI = sum_i (w_i)^2`` on exposure shares. HHI = 1 means a single-name
    portfolio; HHI = 1/n means perfectly granular. The effective number of
    independent exposures is ``1/HHI`` (the diversification score).

    Args:
        exposures: Per-name exposure amounts (>= 0, at least one positive).

    Returns:
        Dict with ``hhi``, ``effective_n`` (= 1/HHI), ``n_names`` and the
        ``max_share`` (largest single-name concentration).

    Raises:
        ValueError: If exposures are empty, negative, or sum to zero.
    """
    e = np.asarray(exposures, dtype=np.float64)
    if e.size == 0:
        raise ValueError("exposures must be non-empty")
    if np.any(e < 0.0):
        raise ValueError("exposures must be non-negative")
    total = float(np.sum(e))
    if total <= 0.0:
        raise ValueError("exposures must sum to a positive value")

    shares = e / total
    hhi = float(np.sum(shares**2))
    return {
        "hhi": round(hhi, 10),
        "effective_n": round(1.0 / hhi, 6),
        "n_names": int(e.size),
        "max_share": round(float(np.max(shares)), 10),
    }

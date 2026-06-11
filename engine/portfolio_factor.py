"""engine/portfolio_factor.py — Factor models & statistical decomposition.

Implements the Factor Models sub-domain of Portfolio Analytics: Fama-French
3-factor, Carhart 4-factor, Fama-French 5-factor regressions, Principal
Component Analysis, correlation clustering, and a Gaussian regime-detection
(HMM-style 2-state) classifier.

Numba rules (CLAUDE.md §3.1): linear algebra (OLS via normal equations, PCA via
the covariance eigendecomposition) runs in pure-Python wrappers using NumPy.
The regime-detection EM recursion and the correlation-distance loop run in JIT
kernels returning NumPy arrays. All randomness (none needed here — EM is
deterministic from a seeded init) stays in pure Python.

sklearn / statsmodels are intentionally NOT used (unavailable in this
environment); the implementations are self-contained NumPy.
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "fama_french_3_factor_model",
    "carhart_4_factor_model",
    "fama_french_5_factor_model",
    "principal_component_analysis",
    "correlation_clustering",
    "regime_detection_hmm",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _gaussian_em_2state(returns: np.ndarray, n_iter: int) -> np.ndarray:
    """Two-state Gaussian mixture EM for regime detection.

    A stationary (no transition matrix) Gaussian mixture is fitted by EM; the
    low-mean / high-variance component is the "stress" regime. Deterministic
    from a fixed quantile-based initialisation.

    Returns a (2, 3) array of ``[[mu0, var0, pi0], [mu1, var1, pi1]]`` plus the
    responsibilities are recomputed by the wrapper (RULE 5: arrays only).
    """
    n = returns.shape[0]
    # Initialise from the data spread.
    mean_all = 0.0
    for i in range(n):
        mean_all += returns[i]
    mean_all /= n
    var_all = 0.0
    for i in range(n):
        d = returns[i] - mean_all
        var_all += d * d
    var_all /= n
    sd = np.sqrt(var_all)

    mu0 = mean_all + 0.5 * sd
    mu1 = mean_all - 0.5 * sd
    var0 = var_all
    var1 = var_all
    pi0 = 0.5
    pi1 = 0.5

    for _ in range(n_iter):
        s0 = 0.0
        s1 = 0.0
        sm0 = 0.0
        sm1 = 0.0
        sv0 = 0.0
        sv1 = 0.0
        for i in range(n):
            x = returns[i]
            p0 = pi0 / np.sqrt(2.0 * np.pi * var0) * np.exp(-(x - mu0) ** 2 / (2.0 * var0))
            p1 = pi1 / np.sqrt(2.0 * np.pi * var1) * np.exp(-(x - mu1) ** 2 / (2.0 * var1))
            denom = p0 + p1
            if denom <= 0.0:
                r0 = 0.5
            else:
                r0 = p0 / denom
            r1 = 1.0 - r0
            s0 += r0
            s1 += r1
            sm0 += r0 * x
            sm1 += r1 * x
        mu0 = sm0 / s0 if s0 > 0.0 else mu0
        mu1 = sm1 / s1 if s1 > 0.0 else mu1
        for i in range(n):
            x = returns[i]
            p0 = pi0 / np.sqrt(2.0 * np.pi * var0) * np.exp(-(x - mu0) ** 2 / (2.0 * var0))
            p1 = pi1 / np.sqrt(2.0 * np.pi * var1) * np.exp(-(x - mu1) ** 2 / (2.0 * var1))
            denom = p0 + p1
            if denom <= 0.0:
                r0 = 0.5
            else:
                r0 = p0 / denom
            r1 = 1.0 - r0
            sv0 += r0 * (x - mu0) ** 2
            sv1 += r1 * (x - mu1) ** 2
        var0 = sv0 / s0 if s0 > 0.0 else var0
        var1 = sv1 / s1 if s1 > 0.0 else var1
        # Guard against variance collapse.
        if var0 < 1e-12:
            var0 = 1e-12
        if var1 < 1e-12:
            var1 = 1e-12
        pi0 = s0 / n
        pi1 = s1 / n

    out = np.empty((2, 3), dtype=np.float64)
    out[0, 0] = mu0
    out[0, 1] = var0
    out[0, 2] = pi0
    out[1, 0] = mu1
    out[1, 1] = var1
    out[1, 2] = pi1
    return out


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ols(y: np.ndarray, x: np.ndarray, factor_names: list[str]) -> dict:  # type: ignore[type-arg]
    """OLS regression of ``y`` on ``[1, x]`` via least squares.

    Returns alpha, per-factor betas, R-squared and residual std. Pure NumPy
    (no statsmodels dependency).
    """
    n = y.shape[0]
    design = np.column_stack([np.ones(n), x])
    coef, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ coef
    residuals = y - fitted
    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 0.0
    betas = {factor_names[i]: round(float(coef[i + 1]), 8) for i in range(len(factor_names))}
    return {
        "alpha": round(float(coef[0]), 10),
        "betas": betas,
        "r_squared": round(r2, 8),
        "residual_std": round(float(np.std(residuals)), 10),
        "n_obs": int(n),
    }


def _factor_regression(
    excess_returns: np.ndarray,
    factors: np.ndarray,
    factor_names: list[str],
) -> dict:  # type: ignore[type-arg]
    """Validate shapes and run the OLS factor regression."""
    y = np.asarray(excess_returns, dtype=np.float64)
    x = np.atleast_2d(np.asarray(factors, dtype=np.float64))
    if x.shape[0] != y.size:
        x = x.T
    if x.shape[0] != y.size:
        raise ValueError("factors must have one row per observation")
    if x.shape[1] != len(factor_names):
        raise ValueError(f"expected {len(factor_names)} factor columns")
    if y.size <= len(factor_names) + 1:
        raise ValueError("not enough observations for the regression")
    return _ols(y, x, factor_names)


# ── Public functions ──────────────────────────────────────────────────────────


def fama_french_3_factor_model(
    excess_returns: np.ndarray,
    factors: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Fama-French 3-factor regression (MKT, SMB, HML).

    Regresses portfolio excess returns on the market, size (SMB) and value
    (HML) factors. The intercept is the factor alpha.

    Args:
        excess_returns: Portfolio excess returns over the risk-free rate.
        factors: (n_obs, 3) matrix of MKT, SMB, HML factor returns.

    Returns:
        Dict with ``alpha``, ``betas`` (mkt/smb/hml), ``r_squared`` and
        ``residual_std``.

    Raises:
        ValueError: If shapes are inconsistent or too few observations.
    """
    return _factor_regression(excess_returns, factors, ["mkt", "smb", "hml"])


def carhart_4_factor_model(
    excess_returns: np.ndarray,
    factors: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Carhart 4-factor regression (MKT, SMB, HML, MOM).

    Extends Fama-French 3-factor with the momentum (WML/MOM) factor.

    Args:
        excess_returns: Portfolio excess returns over the risk-free rate.
        factors: (n_obs, 4) matrix of MKT, SMB, HML, MOM factor returns.

    Returns:
        Dict with ``alpha``, ``betas`` (mkt/smb/hml/mom), ``r_squared`` and
        ``residual_std``.

    Raises:
        ValueError: If shapes are inconsistent or too few observations.
    """
    return _factor_regression(excess_returns, factors, ["mkt", "smb", "hml", "mom"])


def fama_french_5_factor_model(
    excess_returns: np.ndarray,
    factors: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Fama-French 5-factor regression (MKT, SMB, HML, RMW, CMA).

    Adds profitability (RMW) and investment (CMA) factors to the 3-factor model.

    Args:
        excess_returns: Portfolio excess returns over the risk-free rate.
        factors: (n_obs, 5) matrix of MKT, SMB, HML, RMW, CMA factor returns.

    Returns:
        Dict with ``alpha``, ``betas`` (mkt/smb/hml/rmw/cma), ``r_squared`` and
        ``residual_std``.

    Raises:
        ValueError: If shapes are inconsistent or too few observations.
    """
    return _factor_regression(excess_returns, factors, ["mkt", "smb", "hml", "rmw", "cma"])


def principal_component_analysis(
    returns_matrix: np.ndarray,
    n_components: int | None = None,
) -> dict:  # type: ignore[type-arg]
    """Principal Component Analysis of an asset return matrix.

    Eigendecomposes the covariance matrix to extract orthogonal principal
    components ordered by explained variance.

    Args:
        returns_matrix: (n_obs, n_assets) return matrix.
        n_components: Number of components to return (defaults to all).

    Returns:
        Dict with ``eigenvalues``, ``explained_variance_ratio`` (sums to 1),
        ``cumulative_variance`` and the leading ``components`` (eigenvectors).

    Raises:
        ValueError: If the matrix has fewer than 2 observations or assets.
    """
    m = np.asarray(returns_matrix, dtype=np.float64)
    if m.ndim != 2 or m.shape[0] < 2 or m.shape[1] < 2:
        raise ValueError("returns_matrix must be (n_obs>=2, n_assets>=2)")

    cov = np.cov(m, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]  # descending
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    total = float(np.sum(eigvals))
    evr = eigvals / total if total > 0.0 else np.zeros_like(eigvals)
    k = eigvals.size if n_components is None else min(n_components, eigvals.size)
    return {
        "eigenvalues": [round(float(v), 10) for v in eigvals[:k]],
        "explained_variance_ratio": [round(float(v), 8) for v in evr[:k]],
        "cumulative_variance": [round(float(v), 8) for v in np.cumsum(evr)[:k]],
        "components": [[round(float(x), 8) for x in eigvecs[:, j]] for j in range(k)],
        "n_components": int(k),
    }


def correlation_clustering(
    returns_matrix: np.ndarray,
    n_clusters: int = 2,
) -> dict:  # type: ignore[type-arg]
    """Correlation-based clustering of assets.

    Builds the correlation distance ``sqrt(2(1 - rho))`` and performs simple
    single-linkage agglomerative clustering down to ``n_clusters`` groups —
    grouping assets that co-move.

    Args:
        returns_matrix: (n_obs, n_assets) return matrix.
        n_clusters: Target number of clusters.

    Returns:
        Dict with ``labels`` (cluster id per asset), ``n_clusters`` and the
        ``average_intra_correlation``.

    Raises:
        ValueError: If inputs are inconsistent.
    """
    m = np.asarray(returns_matrix, dtype=np.float64)
    if m.ndim != 2 or m.shape[1] < 1:
        raise ValueError("returns_matrix must be (n_obs, n_assets>=1)")
    n_assets = m.shape[1]
    if not 1 <= n_clusters <= n_assets:
        raise ValueError("n_clusters must be in [1, n_assets]")

    corr = np.atleast_2d(np.corrcoef(m, rowvar=False))
    dist = np.sqrt(np.clip(2.0 * (1.0 - corr), 0.0, None))

    # Single-linkage agglomerative clustering.
    clusters: list[list[int]] = [[i] for i in range(n_assets)]
    while len(clusters) > n_clusters:
        best = (float("inf"), 0, 1)
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                d = min(dist[i, j] for i in clusters[a] for j in clusters[b])
                if d < best[0]:
                    best = (d, a, b)
        _, a, b = best
        clusters[a].extend(clusters[b])
        clusters.pop(b)

    labels = np.empty(n_assets, dtype=np.int64)
    for cid, members in enumerate(clusters):
        for i in members:
            labels[i] = cid

    # Average intra-cluster correlation.
    intra_vals: list[float] = []
    for members in clusters:
        for ii in range(len(members)):
            for jj in range(ii + 1, len(members)):
                intra_vals.append(float(corr[members[ii], members[jj]]))
    avg_intra = float(np.mean(intra_vals)) if intra_vals else 1.0
    return {
        "labels": [int(x) for x in labels],
        "n_clusters": int(len(clusters)),
        "average_intra_correlation": round(avg_intra, 8),
    }


def regime_detection_hmm(
    returns: np.ndarray,
    n_iter: int = 50,
) -> dict:  # type: ignore[type-arg]
    """Two-state Gaussian regime detection (HMM-style mixture).

    Fits a two-component Gaussian mixture by EM and labels each observation by
    its most likely regime. The higher-variance component is reported as the
    "stress" regime — the standard calm/turbulent market characterisation.

    Args:
        returns: 1-D array of per-period returns.
        n_iter: Number of EM iterations.

    Returns:
        Dict with per-regime ``means``, ``variances``, ``weights``, the
        ``stress_regime`` index, the ``regime_labels`` series and the current
        ``current_regime``.

    Raises:
        ValueError: If fewer than 10 observations are supplied.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.size < 10:
        raise ValueError("regime detection requires at least 10 observations")

    params = _gaussian_em_2state(np.ascontiguousarray(r), n_iter)
    mu = params[:, 0]
    var = params[:, 1]
    pi = params[:, 2]

    # Posterior responsibilities and hard labels.
    p0 = pi[0] / np.sqrt(2.0 * np.pi * var[0]) * np.exp(-((r - mu[0]) ** 2) / (2.0 * var[0]))
    p1 = pi[1] / np.sqrt(2.0 * np.pi * var[1]) * np.exp(-((r - mu[1]) ** 2) / (2.0 * var[1]))
    labels = np.where(p1 >= p0, 1, 0)
    stress_regime = int(np.argmax(var))  # higher variance = stress
    return {
        "means": [round(float(x), 10) for x in mu],
        "variances": [round(float(x), 12) for x in var],
        "weights": [round(float(x), 8) for x in pi],
        "stress_regime": stress_regime,
        "regime_labels": [int(x) for x in labels],
        "current_regime": int(labels[-1]),
    }

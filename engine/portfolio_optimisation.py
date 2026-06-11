"""engine/portfolio_optimisation.py — Portfolio construction & optimisation.

Implements the Portfolio Optimisation sub-domain of Portfolio Analytics:
mean-variance (Markowitz), minimum variance, maximum Sharpe, risk parity, equal
weight, Black-Litterman, resampled efficient frontier, robust optimisation,
CVaR-constrained optimisation, and factor-based optimisation.

Numba rules (CLAUDE.md §3.1): pure NumPy/SciPy linear-algebra objectives run in
the pure-Python wrappers. Constrained optimisation calls ``scipy.optimize``
(SLSQP) in pure Python — never inside an @njit kernel. A small @njit helper
evaluates the risk-parity objective gradient-free where it is hot.

Conventions:
  * ``mean_returns`` and ``cov_matrix`` are per-period unless stated.
  * Returned ``weights`` sum to 1.0 (long-only with bounds by default).
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy.optimize import minimize

__all__ = [
    "mean_variance_optimisation",
    "minimum_variance_portfolio",
    "maximum_sharpe_ratio_portfolio",
    "risk_parity_portfolio",
    "equal_weight_portfolio",
    "black_litterman_model",
    "resampled_efficient_frontier",
    "robust_portfolio_optimisation",
    "cvar_constrained_optimisation",
    "factor_based_optimisation",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _risk_parity_objective(weights: np.ndarray, cov: np.ndarray) -> float:
    """Sum of squared pairwise differences between risk contributions.

    Minimised (to zero) when each asset contributes equally to portfolio
    variance. The all-pairs form has a stronger gradient signal than comparing
    to the mean, which helps SLSQP converge to the true ERC point.
    """
    n = weights.shape[0]
    cw = cov @ weights
    rc = np.empty(n, dtype=np.float64)
    for i in range(n):
        rc[i] = weights[i] * cw[i]
    obj = 0.0
    for i in range(n):
        for j in range(n):
            d = rc[i] - rc[j]
            obj += d * d
    return obj


# ── Helpers ───────────────────────────────────────────────────────────────────


def _portfolio_stats(
    weights: np.ndarray,
    mean_returns: np.ndarray,
    cov: np.ndarray,
    risk_free: float,
    periods_per_year: int,
) -> dict:  # type: ignore[type-arg]
    """Annualised return, volatility and Sharpe for a weight vector."""
    ret_p = float(weights @ mean_returns)
    vol_p = float(np.sqrt(max(float(weights @ cov @ weights), 0.0)))
    ann_ret = ret_p * periods_per_year
    ann_vol = vol_p * np.sqrt(periods_per_year)
    sharpe = (ann_ret - risk_free) / ann_vol if ann_vol > 0.0 else 0.0
    return {
        "weights": [round(float(w), 8) for w in weights],
        "return": round(ann_ret, 8),
        "volatility": round(float(ann_vol), 8),
        "sharpe": round(float(sharpe), 8),
    }


def _validate(mean_returns: np.ndarray, cov_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Coerce and shape-check the mean/covariance inputs."""
    mu = np.asarray(mean_returns, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    if mu.ndim != 1 or mu.size < 1:
        raise ValueError("mean_returns must be a non-empty 1-D array")
    if cov.shape != (mu.size, mu.size):
        raise ValueError("cov_matrix must be (n_assets, n_assets) matching mean_returns")
    return mu, cov


# ── Public functions ──────────────────────────────────────────────────────────


def mean_variance_optimisation(
    mean_returns: np.ndarray,
    cov_matrix: np.ndarray,
    risk_aversion: float = 1.0,
    allow_short: bool = False,
    risk_free: float = 0.0,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Mean-variance (Markowitz) optimisation.

    Maximises ``w'μ - 0.5 * λ * w'Σw`` subject to weights summing to 1, with an
    optional long-only constraint.

    Args:
        mean_returns: Per-period expected return per asset.
        cov_matrix: Per-period covariance matrix.
        risk_aversion: Risk-aversion coefficient λ (higher = less risk).
        allow_short: If False, weights are bounded to [0, 1].
        risk_free: Annual risk-free rate for the reported Sharpe.
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``weights``, ``return``, ``volatility``, ``sharpe`` and
        ``success``.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    mu, cov = _validate(mean_returns, cov_matrix)
    n = mu.size

    def neg_utility(w: np.ndarray) -> float:
        return -(w @ mu - 0.5 * risk_aversion * (w @ cov @ w))

    bounds = [(-1.0, 1.0) if allow_short else (0.0, 1.0)] * n
    constraints = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    x0 = np.full(n, 1.0 / n)
    res = minimize(neg_utility, x0, method="SLSQP", bounds=bounds, constraints=constraints)
    w = res.x
    out = _portfolio_stats(w, mu, cov, risk_free, periods_per_year)
    out["success"] = bool(res.success)
    return out


def minimum_variance_portfolio(
    cov_matrix: np.ndarray,
    allow_short: bool = False,
    mean_returns: np.ndarray | None = None,
    risk_free: float = 0.0,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Global minimum-variance portfolio.

    Minimises ``w'Σw`` subject to weights summing to 1. With shorting allowed
    the closed-form solution ``Σ⁻¹1 / (1'Σ⁻¹1)`` is used; long-only uses SLSQP.

    Args:
        cov_matrix: Per-period covariance matrix.
        allow_short: If False, weights are bounded to [0, 1].
        mean_returns: Optional per-period returns for reporting Sharpe.
        risk_free: Annual risk-free rate for the reported Sharpe.
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``weights`` (sum to 1), ``return``, ``volatility``, ``sharpe``.

    Raises:
        ValueError: If the covariance matrix is not square.
    """
    cov = np.asarray(cov_matrix, dtype=np.float64)
    if cov.ndim != 2 or cov.shape[0] != cov.shape[1]:
        raise ValueError("cov_matrix must be square")
    n = cov.shape[0]
    mu = np.zeros(n) if mean_returns is None else np.asarray(mean_returns, dtype=np.float64)

    if allow_short:
        ones = np.ones(n)
        inv = np.linalg.pinv(cov)
        w = inv @ ones / float(ones @ inv @ ones)
    else:
        def port_var(w: np.ndarray) -> float:
            return float(w @ cov @ w)

        bounds = [(0.0, 1.0)] * n
        constraints = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
        res = minimize(
            port_var, np.full(n, 1.0 / n), method="SLSQP", bounds=bounds, constraints=constraints
        )
        w = res.x
    return _portfolio_stats(w, mu, cov, risk_free, periods_per_year)


def maximum_sharpe_ratio_portfolio(
    mean_returns: np.ndarray,
    cov_matrix: np.ndarray,
    risk_free: float = 0.0,
    allow_short: bool = False,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Maximum Sharpe ratio (tangency) portfolio.

    Maximises the annualised Sharpe ratio subject to weights summing to 1.

    Args:
        mean_returns: Per-period expected return per asset.
        cov_matrix: Per-period covariance matrix.
        risk_free: Annual risk-free rate.
        allow_short: If False, weights are bounded to [0, 1].
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``weights``, ``return``, ``volatility``, ``sharpe`` and
        ``success``.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    mu, cov = _validate(mean_returns, cov_matrix)
    n = mu.size
    rf_period = risk_free / periods_per_year

    def neg_sharpe(w: np.ndarray) -> float:
        ret = float(w @ mu) - rf_period
        vol = float(np.sqrt(max(float(w @ cov @ w), 1e-18)))
        return -ret / vol

    bounds = [(-1.0, 1.0) if allow_short else (0.0, 1.0)] * n
    constraints = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    res = minimize(
        neg_sharpe, np.full(n, 1.0 / n), method="SLSQP", bounds=bounds, constraints=constraints
    )
    out = _portfolio_stats(res.x, mu, cov, risk_free, periods_per_year)
    out["success"] = bool(res.success)
    return out


def risk_parity_portfolio(
    cov_matrix: np.ndarray,
    mean_returns: np.ndarray | None = None,
    risk_free: float = 0.0,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Equal risk contribution (risk parity) portfolio.

    Finds long-only weights so each asset contributes equally to portfolio
    variance, by minimising the dispersion of risk contributions.

    Args:
        cov_matrix: Per-period covariance matrix.
        mean_returns: Optional per-period returns for reporting Sharpe.
        risk_free: Annual risk-free rate for the reported Sharpe.
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``weights`` (sum to 1), ``return``, ``volatility``,
        ``sharpe`` and ``risk_contributions``.

    Raises:
        ValueError: If the covariance matrix is not square.
    """
    cov = np.asarray(cov_matrix, dtype=np.float64)
    if cov.ndim != 2 or cov.shape[0] != cov.shape[1]:
        raise ValueError("cov_matrix must be square")
    n = cov.shape[0]
    cov_c = np.ascontiguousarray(cov)
    mu = np.zeros(n) if mean_returns is None else np.asarray(mean_returns, dtype=np.float64)

    bounds = [(1e-6, 1.0)] * n
    constraints = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    res = minimize(
        lambda w: _risk_parity_objective(w, cov_c),
        np.full(n, 1.0 / n),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 1000, "ftol": 1e-12},
    )
    w = res.x / np.sum(res.x)
    cw = cov @ w
    rc = w * cw
    out = _portfolio_stats(w, mu, cov, risk_free, periods_per_year)
    out["risk_contributions"] = [round(float(x), 10) for x in rc]
    return out


def equal_weight_portfolio(
    n_assets: int,
    mean_returns: np.ndarray | None = None,
    cov_matrix: np.ndarray | None = None,
    risk_free: float = 0.0,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Equal-weight (1/N) portfolio.

    Args:
        n_assets: Number of assets.
        mean_returns: Optional per-period returns for reporting.
        cov_matrix: Optional covariance for reporting volatility/Sharpe.
        risk_free: Annual risk-free rate for the reported Sharpe.
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``weights`` (each 1/N), and ``return``/``volatility``/
        ``sharpe`` when inputs supplied.

    Raises:
        ValueError: If ``n_assets`` < 1.
    """
    if n_assets < 1:
        raise ValueError("n_assets must be >= 1")
    w = np.full(n_assets, 1.0 / n_assets)
    if mean_returns is None or cov_matrix is None:
        return {"weights": [round(float(x), 8) for x in w], "n_assets": int(n_assets)}
    mu = np.asarray(mean_returns, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    return _portfolio_stats(w, mu, cov, risk_free, periods_per_year)


def black_litterman_model(
    market_weights: np.ndarray,
    cov_matrix: np.ndarray,
    p_matrix: np.ndarray,
    q_views: np.ndarray,
    risk_aversion: float = 2.5,
    tau: float = 0.05,
    omega: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Black-Litterman posterior expected returns and weights.

    Combines the CAPM-implied equilibrium returns ``Π = λ Σ w_mkt`` with
    investor views ``P E[r] = Q`` to produce posterior expected returns and the
    corresponding mean-variance weights.

    Args:
        market_weights: Market-cap equilibrium weights.
        cov_matrix: Asset covariance matrix.
        p_matrix: (k, n) view pick matrix.
        q_views: (k,) view return vector.
        risk_aversion: Equilibrium risk-aversion λ.
        tau: Scalar on the prior covariance (uncertainty in equilibrium).
        omega: (k, k) view uncertainty; defaults to ``diag(P τΣ Pᵀ)``.

    Returns:
        Dict with ``posterior_returns``, ``weights`` and ``implied_returns``.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    w_mkt = np.asarray(market_weights, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    p = np.atleast_2d(np.asarray(p_matrix, dtype=np.float64))
    q = np.asarray(q_views, dtype=np.float64).reshape(-1)
    n = w_mkt.size
    if cov.shape != (n, n):
        raise ValueError("cov_matrix must match market_weights length")
    if p.shape[1] != n or p.shape[0] != q.size:
        raise ValueError("p_matrix/q_views shapes are inconsistent")

    pi = risk_aversion * cov @ w_mkt  # implied equilibrium returns
    tau_cov = tau * cov
    if omega is None:
        omega = np.diag(np.diag(p @ tau_cov @ p.T))
    else:
        omega = np.asarray(omega, dtype=np.float64)

    inv_tau_cov = np.linalg.pinv(tau_cov)
    inv_omega = np.linalg.pinv(omega)
    posterior_cov = np.linalg.pinv(inv_tau_cov + p.T @ inv_omega @ p)
    posterior_ret = posterior_cov @ (inv_tau_cov @ pi + p.T @ inv_omega @ q)

    # Unconstrained mean-variance weights from posterior returns.
    w = np.linalg.pinv(risk_aversion * cov) @ posterior_ret
    return {
        "posterior_returns": [round(float(x), 10) for x in posterior_ret],
        "implied_returns": [round(float(x), 10) for x in pi],
        "weights": [round(float(x), 8) for x in w],
    }


def resampled_efficient_frontier(
    mean_returns: np.ndarray,
    cov_matrix: np.ndarray,
    n_resamples: int = 50,
    n_obs: int = 250,
    seed: int = 2024,
) -> dict:  # type: ignore[type-arg]
    """Resampled efficient frontier (Michaud) minimum-variance point.

    Bootstraps return samples from the estimated multivariate-normal, solves the
    minimum-variance long-only portfolio on each resample, and averages the
    weights — reducing estimation-error sensitivity. All randomness is pre-drawn
    in pure Python (RULE 3).

    Args:
        mean_returns: Per-period expected return per asset.
        cov_matrix: Per-period covariance matrix.
        n_resamples: Number of bootstrap resamples.
        n_obs: Synthetic sample size per resample.
        seed: RNG seed for determinism.

    Returns:
        Dict with averaged ``weights`` and the ``weight_std`` across resamples.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    mu, cov = _validate(mean_returns, cov_matrix)
    n = mu.size
    rng = np.random.default_rng(seed)
    accum = np.zeros((n_resamples, n), dtype=np.float64)
    for k in range(n_resamples):
        sample = rng.multivariate_normal(mu, cov, size=n_obs)
        sample_cov = np.cov(sample, rowvar=False)
        res = minimize(
            lambda w: float(w @ sample_cov @ w),
            np.full(n, 1.0 / n),
            method="SLSQP",
            bounds=[(0.0, 1.0)] * n,
            constraints=({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},),
        )
        accum[k] = res.x
    avg_w = np.mean(accum, axis=0)
    avg_w = avg_w / np.sum(avg_w)
    return {
        "weights": [round(float(x), 8) for x in avg_w],
        "weight_std": [round(float(x), 8) for x in np.std(accum, axis=0)],
        "n_resamples": int(n_resamples),
    }


def robust_portfolio_optimisation(
    mean_returns: np.ndarray,
    cov_matrix: np.ndarray,
    uncertainty: float = 0.05,
    risk_aversion: float = 1.0,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Robust mean-variance optimisation with a box uncertainty set on means.

    Uses the worst-case expected return ``μ - κ·diag(Σ)^{1/2}`` within an
    ellipsoidal/box uncertainty set (Tütüncü-Koenig style), then solves the
    standard mean-variance problem — producing more conservative weights.

    Args:
        mean_returns: Per-period expected return per asset.
        cov_matrix: Per-period covariance matrix.
        uncertainty: Size κ of the uncertainty set on the mean estimates.
        risk_aversion: Risk-aversion coefficient λ.
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``weights``, ``return``, ``volatility``, ``sharpe`` and the
        ``worst_case_returns`` used.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    mu, cov = _validate(mean_returns, cov_matrix)
    n = mu.size
    worst_mu = mu - uncertainty * np.sqrt(np.clip(np.diag(cov), 0.0, None))

    def neg_utility(w: np.ndarray) -> float:
        return -(w @ worst_mu - 0.5 * risk_aversion * (w @ cov @ w))

    res = minimize(
        neg_utility,
        np.full(n, 1.0 / n),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},),
    )
    out = _portfolio_stats(res.x, mu, cov, 0.0, periods_per_year)
    out["worst_case_returns"] = [round(float(x), 10) for x in worst_mu]
    return out


def cvar_constrained_optimisation(
    scenario_returns: np.ndarray,
    mean_returns: np.ndarray | None = None,
    confidence_level: float = 0.95,
    cvar_limit: float = 0.05,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """CVaR-constrained portfolio optimisation (Rockafellar-Uryasev).

    Maximises expected return subject to the portfolio CVaR (at
    ``confidence_level``) not exceeding ``cvar_limit``, long-only and fully
    invested. CVaR is computed empirically over the supplied scenarios.

    Args:
        scenario_returns: (n_scenarios, n_assets) scenario return matrix.
        mean_returns: Per-asset expected returns; defaults to scenario means.
        confidence_level: CVaR confidence in [0.90, 0.9999].
        cvar_limit: Maximum acceptable portfolio CVaR (positive fraction).
        periods_per_year: Annualisation factor for the reported return.

    Returns:
        Dict with ``weights``, ``expected_return``, ``cvar`` and ``success``.

    Raises:
        ValueError: If the scenario matrix is not 2-D with >= 1 asset.
    """
    scen = np.asarray(scenario_returns, dtype=np.float64)
    if scen.ndim != 2 or scen.shape[1] < 1:
        raise ValueError("scenario_returns must be (n_scenarios, n_assets)")
    n = scen.shape[1]
    mu = scen.mean(axis=0) if mean_returns is None else np.asarray(mean_returns, dtype=np.float64)

    def portfolio_cvar(w: np.ndarray) -> float:
        losses = -(scen @ w)
        var = np.quantile(losses, confidence_level)
        tail = losses[losses >= var]
        return float(np.mean(tail)) if tail.size > 0 else float(var)

    def neg_return(w: np.ndarray) -> float:
        return -float(w @ mu)

    constraints = (
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "ineq", "fun": lambda w: cvar_limit - portfolio_cvar(w)},
    )
    res = minimize(
        neg_return,
        np.full(n, 1.0 / n),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=constraints,
    )
    w = res.x
    return {
        "weights": [round(float(x), 8) for x in w],
        "expected_return": round(float(w @ mu) * periods_per_year, 8),
        "cvar": round(portfolio_cvar(w), 8),
        "success": bool(res.success),
    }


def factor_based_optimisation(
    factor_exposures: np.ndarray,
    factor_cov: np.ndarray,
    specific_var: np.ndarray,
    target_exposures: np.ndarray | None = None,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Factor-based minimum-risk optimisation.

    Builds the asset covariance from a factor model
    ``Σ = B F Bᵀ + diag(specific_var)`` and finds the long-only fully-invested
    minimum-variance portfolio, optionally matching ``target_exposures`` to the
    factors via an equality constraint.

    Args:
        factor_exposures: (n_assets, n_factors) factor loading matrix B.
        factor_cov: (n_factors, n_factors) factor covariance F.
        specific_var: (n_assets,) idiosyncratic variances.
        target_exposures: Optional (n_factors,) target portfolio factor
            exposures to match exactly.
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``weights``, ``volatility``, ``factor_exposures`` (achieved)
        and ``success``.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    b = np.atleast_2d(np.asarray(factor_exposures, dtype=np.float64))
    f = np.asarray(factor_cov, dtype=np.float64)
    spec = np.asarray(specific_var, dtype=np.float64)
    n, k = b.shape
    if f.shape != (k, k) or spec.size != n:
        raise ValueError("factor_cov/specific_var shapes inconsistent with exposures")

    cov = b @ f @ b.T + np.diag(spec)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    if target_exposures is not None:
        tgt = np.asarray(target_exposures, dtype=np.float64)
        if tgt.size != k:
            raise ValueError("target_exposures must have length n_factors")
        constraints.append({"type": "eq", "fun": lambda w, t=tgt: b.T @ w - t})

    res = minimize(
        lambda w: float(w @ cov @ w),
        np.full(n, 1.0 / n),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=tuple(constraints),
    )
    w = res.x
    vol_p = float(np.sqrt(max(float(w @ cov @ w), 0.0)))
    return {
        "weights": [round(float(x), 8) for x in w],
        "volatility": round(vol_p * np.sqrt(periods_per_year), 8),
        "factor_exposures": [round(float(x), 8) for x in (b.T @ w)],
        "success": bool(res.success),
    }

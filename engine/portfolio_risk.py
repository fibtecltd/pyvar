"""engine/portfolio_risk.py — Portfolio risk & active-risk analytics.

Implements the Active Risk Analytics and Portfolio Risk Analytics sub-domains
of Portfolio Analytics: beta, active share, tracking error, residual risk,
turnover, transaction-cost analysis, marginal contribution to risk,
diversification ratio, correlation matrix, concentration (HHI), liquidity-
adjusted portfolio VaR, and Monte Carlo portfolio simulation.

Numba rules (CLAUDE.md §3.1): @njit kernels are stateless, take only float64
arrays / scalars, never import internally, and return NumPy arrays. All
randomness for the Monte Carlo simulation is pre-drawn in pure Python before
the JIT region (RULE 3). Public wrappers convert to Python types and may use
SciPy.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy import stats

__all__ = [
    "portfolio_beta",
    "active_share",
    "tracking_error",
    "residual_risk",
    "portfolio_turnover",
    "transaction_cost_analysis",
    "marginal_contribution_to_risk",
    "diversification_ratio",
    "correlation_matrix_portfolio",
    "concentration_risk_hhi",
    "liquidity_adjusted_portfolio_var",
    "monte_carlo_portfolio_simulation",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _mcr_kernel(weights: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Marginal and component contribution to volatility risk.

    Returns a (2, n) float64 array: row 0 marginal, row 1 component (RULE 5).
    Component contributions sum to the portfolio volatility (Euler).
    """
    n = weights.shape[0]
    cw = cov @ weights
    sigma_sq = 0.0
    for i in range(n):
        sigma_sq += weights[i] * cw[i]
    sigma = np.sqrt(sigma_sq) if sigma_sq > 0.0 else 0.0
    out = np.empty((2, n), dtype=np.float64)
    for i in range(n):
        if sigma > 0.0:
            marginal = cw[i] / sigma
        else:
            marginal = 0.0
        out[0, i] = marginal
        out[1, i] = weights[i] * marginal
    return out


@njit(cache=True, parallel=False)
def _simulate_terminal_pnl(
    weights: np.ndarray,
    draws: np.ndarray,
    initial_value: float,
) -> np.ndarray:
    """Terminal portfolio P&L for each pre-drawn return path.

    Args:
        weights: (n_assets,) portfolio weights.
        draws: (n_sims, horizon, n_assets) pre-drawn per-period asset returns.
        initial_value: portfolio start value.

    Returns:
        (n_sims,) array of terminal P&L (value change), arrays only (RULE 5).
    """
    n_sims = draws.shape[0]
    horizon = draws.shape[1]
    n_assets = draws.shape[2]
    out = np.empty(n_sims, dtype=np.float64)
    for s in range(n_sims):
        growth = 1.0
        for t in range(horizon):
            port_ret = 0.0
            for a in range(n_assets):
                port_ret += weights[a] * draws[s, t, a]
            growth *= 1.0 + port_ret
        out[s] = initial_value * (growth - 1.0)
    return out


# ── Public functions ──────────────────────────────────────────────────────────


def portfolio_beta(
    returns: np.ndarray,
    benchmark_returns: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Portfolio beta — sensitivity of portfolio returns to the benchmark.

    ``beta = cov(r, b) / var(b)``.

    Args:
        returns: 1-D array of portfolio per-period returns.
        benchmark_returns: 1-D array of benchmark per-period returns.

    Returns:
        Dict with ``beta``, ``correlation`` and ``r_squared``.

    Raises:
        ValueError: If arrays differ in length or are empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    b = np.asarray(benchmark_returns, dtype=np.float64)
    if r.size == 0 or r.size != b.size:
        raise ValueError("returns and benchmark_returns must be non-empty and equal length")

    cov = float(np.cov(r, b, bias=True)[0, 1])
    var_b = float(np.var(b))
    beta = cov / var_b if var_b > 0.0 else 0.0
    std_r = float(np.std(r))
    std_b = float(np.std(b))
    corr = cov / (std_r * std_b) if std_r > 0.0 and std_b > 0.0 else 0.0
    return {
        "beta": round(beta, 8),
        "correlation": round(corr, 8),
        "r_squared": round(corr * corr, 8),
    }


def active_share(
    weights: np.ndarray,
    benchmark_weights: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Active share — fraction of holdings differing from the benchmark.

    ``0.5 * sum(|w_i - b_i|)``; 0 means identical to benchmark, 1 means fully
    differentiated (Cremers & Petajisto).

    Args:
        weights: Portfolio weights per asset.
        benchmark_weights: Benchmark weights per asset (same ordering).

    Returns:
        Dict with ``active_share`` in [0, 1].

    Raises:
        ValueError: If arrays differ in length or are empty.
    """
    w = np.asarray(weights, dtype=np.float64)
    b = np.asarray(benchmark_weights, dtype=np.float64)
    if w.size == 0 or w.size != b.size:
        raise ValueError("weights and benchmark_weights must be non-empty and equal length")

    a_share = 0.5 * float(np.sum(np.abs(w - b)))
    return {
        "active_share": round(a_share, 8),
        "n_assets": int(w.size),
    }


def tracking_error(
    returns: np.ndarray,
    benchmark_returns: np.ndarray,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Tracking error — volatility of active (portfolio minus benchmark) return.

    Args:
        returns: 1-D array of portfolio per-period returns.
        benchmark_returns: 1-D array of benchmark per-period returns.
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``tracking_error`` (annualised), ``tracking_error_period``
        and ``mean_active_return``.

    Raises:
        ValueError: If arrays differ in length or are empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    b = np.asarray(benchmark_returns, dtype=np.float64)
    if r.size == 0 or r.size != b.size:
        raise ValueError("returns and benchmark_returns must be non-empty and equal length")

    active = r - b
    te_period = float(np.std(active))
    return {
        "tracking_error": round(te_period * np.sqrt(periods_per_year), 8),
        "tracking_error_period": round(te_period, 10),
        "mean_active_return": round(float(np.mean(active)), 10),
        "periods_per_year": periods_per_year,
    }


def residual_risk(
    returns: np.ndarray,
    benchmark_returns: np.ndarray,
    periods_per_year: int = 252,
) -> dict:  # type: ignore[type-arg]
    """Residual (idiosyncratic) risk — volatility of single-factor regression residuals.

    Regresses portfolio returns on the benchmark (CAPM) and reports the
    standard deviation of the residuals — the risk not explained by beta.

    Args:
        returns: 1-D array of portfolio per-period returns.
        benchmark_returns: 1-D array of benchmark per-period returns.
        periods_per_year: Annualisation factor.

    Returns:
        Dict with ``residual_risk`` (annualised), ``residual_risk_period``,
        ``beta`` and ``alpha`` (per period).

    Raises:
        ValueError: If arrays differ in length or are empty.
    """
    r = np.asarray(returns, dtype=np.float64)
    b = np.asarray(benchmark_returns, dtype=np.float64)
    if r.size == 0 or r.size != b.size:
        raise ValueError("returns and benchmark_returns must be non-empty and equal length")

    cov = float(np.cov(r, b, bias=True)[0, 1])
    var_b = float(np.var(b))
    beta = cov / var_b if var_b > 0.0 else 0.0
    alpha = float(np.mean(r) - beta * np.mean(b))
    residuals = r - (alpha + beta * b)
    res_period = float(np.std(residuals))
    return {
        "residual_risk": round(res_period * np.sqrt(periods_per_year), 8),
        "residual_risk_period": round(res_period, 10),
        "beta": round(beta, 8),
        "alpha": round(alpha, 10),
        "periods_per_year": periods_per_year,
    }


def portfolio_turnover(
    weights_before: np.ndarray,
    weights_after: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Portfolio turnover — one-way traded fraction between two weight vectors.

    ``0.5 * sum(|w_after - w_before|)`` (one-way convention).

    Args:
        weights_before: Pre-rebalance weights.
        weights_after: Post-rebalance weights (same ordering).

    Returns:
        Dict with ``turnover`` (one-way) and ``two_way_turnover``.

    Raises:
        ValueError: If arrays differ in length or are empty.
    """
    wb = np.asarray(weights_before, dtype=np.float64)
    wa = np.asarray(weights_after, dtype=np.float64)
    if wb.size == 0 or wb.size != wa.size:
        raise ValueError("weight vectors must be non-empty and equal length")

    two_way = float(np.sum(np.abs(wa - wb)))
    return {
        "turnover": round(0.5 * two_way, 8),
        "two_way_turnover": round(two_way, 8),
    }


def transaction_cost_analysis(
    trade_prices: np.ndarray,
    benchmark_prices: np.ndarray,
    trade_quantities: np.ndarray,
    side: int = 1,
) -> dict:  # type: ignore[type-arg]
    """Transaction Cost Analysis (TCA) — implementation shortfall vs benchmark.

    Computes per-trade slippage against an arrival/VWAP benchmark and the
    quantity-weighted average slippage in basis points. ``side`` is +1 for
    buys (paying above benchmark is a cost) and -1 for sells.

    This is narrower than Perold's full implementation-shortfall
    decomposition -- there is no delay-cost or unexecuted-share
    opportunity-cost leg, so the result is an execution-slippage metric, not
    a complete IS attribution.

    Args:
        trade_prices: Executed prices per fill.
        benchmark_prices: Benchmark (arrival or VWAP) prices per fill.
        trade_quantities: Executed quantities per fill (non-negative).
        side: +1 for buy orders, -1 for sell orders.

    Returns:
        Dict with ``slippage_bps`` (quantity-weighted), ``total_cost`` (cash)
        and ``n_fills``.

    Raises:
        ValueError: If arrays differ in length, are empty, or ``side`` invalid.
    """
    p = np.asarray(trade_prices, dtype=np.float64)
    bench = np.asarray(benchmark_prices, dtype=np.float64)
    q = np.asarray(trade_quantities, dtype=np.float64)
    if p.size == 0 or not (p.size == bench.size == q.size):
        raise ValueError("price/quantity arrays must be non-empty and equal length")
    if side not in (1, -1):
        raise ValueError("side must be +1 (buy) or -1 (sell)")

    # Cost-positive slippage: buys pay more than benchmark, sells receive less.
    slippage = side * (p - bench)
    total_qty = float(np.sum(q))
    cost_cash = float(np.sum(slippage * q))
    weighted_ref = float(np.sum(bench * q))
    slippage_bps = (cost_cash / weighted_ref) * 1e4 if weighted_ref > 0.0 else 0.0
    return {
        "slippage_bps": round(slippage_bps, 6),
        "total_cost": round(cost_cash, 6),
        "total_quantity": round(total_qty, 6),
        "n_fills": int(p.size),
    }


def marginal_contribution_to_risk(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Marginal and component contribution to portfolio volatility risk.

    Marginal contribution ``(Σw)_i / sigma_p``; component ``w_i * marginal_i``.
    Component contributions sum exactly to the portfolio volatility (Euler).

    Args:
        weights: Portfolio weights per asset.
        cov_matrix: Asset return covariance matrix.

    Returns:
        Dict with ``marginal``, ``component``, ``percent_contribution`` (lists)
        and ``portfolio_volatility``.

    Raises:
        ValueError: If the covariance shape does not match the weights.
    """
    w = np.asarray(weights, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    if cov.shape != (w.size, w.size):
        raise ValueError("cov_matrix must be (n_assets, n_assets) matching weights")

    res = _mcr_kernel(w, np.ascontiguousarray(cov))
    marginal = res[0]
    component = res[1]
    sigma_p = float(np.sum(component))
    pct = component / sigma_p if sigma_p > 0.0 else np.zeros_like(component)
    return {
        "marginal": [round(float(m), 10) for m in marginal],
        "component": [round(float(c), 10) for c in component],
        "percent_contribution": [round(float(p), 8) for p in pct],
        "portfolio_volatility": round(sigma_p, 10),
    }


def diversification_ratio(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Diversification ratio — weighted average vol over portfolio vol.

    ``(w' σ) / sqrt(w' Σ w)`` where ``σ`` is the vector of asset volatilities.
    Always >= 1; higher means more diversification benefit (Choueifaty).

    Args:
        weights: Portfolio weights per asset.
        cov_matrix: Asset return covariance matrix.

    Returns:
        Dict with ``diversification_ratio``, ``weighted_avg_vol`` and
        ``portfolio_volatility``.

    Raises:
        ValueError: If the covariance shape does not match the weights.
    """
    w = np.asarray(weights, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    if cov.shape != (w.size, w.size):
        raise ValueError("cov_matrix must be (n_assets, n_assets) matching weights")

    asset_vol = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    weighted_avg_vol = float(np.sum(np.abs(w) * asset_vol))
    sigma_p = float(np.sqrt(max(float(w @ cov @ w), 0.0)))
    dr = weighted_avg_vol / sigma_p if sigma_p > 0.0 else 0.0
    return {
        "diversification_ratio": round(dr, 8),
        "weighted_avg_vol": round(weighted_avg_vol, 10),
        "portfolio_volatility": round(sigma_p, 10),
    }


def correlation_matrix_portfolio(
    returns_matrix: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Correlation matrix and average pairwise correlation of asset returns.

    Args:
        returns_matrix: (n_obs, n_assets) array of asset return series.

    Returns:
        Dict with ``correlation_matrix`` (nested list), ``average_correlation``
        (mean off-diagonal) and ``n_assets``.

    Raises:
        ValueError: If the matrix has fewer than 2 observations or assets.
    """
    m = np.asarray(returns_matrix, dtype=np.float64)
    if m.ndim != 2 or m.shape[0] < 2 or m.shape[1] < 1:
        raise ValueError("returns_matrix must be (n_obs>=2, n_assets>=1)")

    corr = np.corrcoef(m, rowvar=False)
    corr = np.atleast_2d(corr)
    n = corr.shape[0]
    if n > 1:
        off = corr[~np.eye(n, dtype=bool)]
        avg_corr = float(np.mean(off))
    else:
        avg_corr = 1.0
    return {
        "correlation_matrix": [[round(float(x), 8) for x in row] for row in corr],
        "average_correlation": round(avg_corr, 8),
        "n_assets": int(n),
    }


def concentration_risk_hhi(
    weights: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Concentration risk via the Herfindahl-Hirschman Index (HHI).

    ``HHI = sum(w_i^2)`` on absolute weights normalised to sum to 1. Ranges from
    ``1/n`` (equal weight) to 1 (single holding). The effective number of
    holdings is ``1/HHI``.

    Args:
        weights: Portfolio weights per asset (need not be normalised).

    Returns:
        Dict with ``hhi``, ``effective_n`` and ``normalised_hhi`` (rescaled to
        [0, 1] across the feasible range).

    Raises:
        ValueError: If ``weights`` is empty or sums to zero in absolute terms.
    """
    w = np.asarray(weights, dtype=np.float64)
    if w.size == 0:
        raise ValueError("weights must be non-empty")
    abs_w = np.abs(w)
    total = float(np.sum(abs_w))
    if total == 0.0:
        raise ValueError("weights must not sum to zero in absolute value")

    norm = abs_w / total
    hhi = float(np.sum(norm * norm))
    n = w.size
    eff_n = 1.0 / hhi if hhi > 0.0 else 0.0
    # Normalised HHI maps [1/n, 1] -> [0, 1].
    norm_hhi = (hhi - 1.0 / n) / (1.0 - 1.0 / n) if n > 1 else 1.0
    return {
        "hhi": round(hhi, 8),
        "effective_n": round(eff_n, 6),
        "normalised_hhi": round(norm_hhi, 8),
        "n_assets": int(n),
    }


def liquidity_adjusted_portfolio_var(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
    bid_ask_spreads: np.ndarray,
    portfolio_value: float,
    confidence_level: float = 0.99,
    horizon_days: int = 1,
) -> dict:  # type: ignore[type-arg]
    """Liquidity-adjusted parametric VaR (LVaR).

    Adds a liquidity cost term equal to half the weighted bid-ask spread to the
    parametric delta-normal VaR (Bangia-Diebold-Schuermann simplified add-on),
    capturing the cost of unwinding positions.

    Args:
        weights: Portfolio weights per asset.
        cov_matrix: Asset return covariance matrix (per period).
        bid_ask_spreads: Proportional bid-ask spread per asset (fraction).
        portfolio_value: Current portfolio value in base currency.
        confidence_level: VaR confidence in [0.90, 0.9999].
        horizon_days: Risk horizon (sqrt-time scaling on the market term).

    Returns:
        Dict with ``lvar_pct``, ``lvar_abs``, ``market_var_pct`` and the
        ``liquidity_cost_pct`` add-on.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    w = np.asarray(weights, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    spreads = np.asarray(bid_ask_spreads, dtype=np.float64)
    if cov.shape != (w.size, w.size):
        raise ValueError("cov_matrix must be (n_assets, n_assets) matching weights")
    if spreads.size != w.size:
        raise ValueError("bid_ask_spreads must match weights length")

    sigma_p = float(np.sqrt(max(float(w @ cov @ w), 0.0)))
    z = float(stats.norm.ppf(confidence_level))
    market_var = z * sigma_p * np.sqrt(horizon_days)
    # Half-spread liquidity cost weighted by absolute exposure.
    liq_cost = 0.5 * float(np.sum(np.abs(w) * spreads))
    lvar = market_var + liq_cost
    return {
        "lvar_pct": round(float(lvar), 8),
        "lvar_abs": round(float(lvar) * portfolio_value, 2),
        "market_var_pct": round(float(market_var), 8),
        "liquidity_cost_pct": round(liq_cost, 8),
        "confidence_level": confidence_level,
        "horizon_days": horizon_days,
    }


def monte_carlo_portfolio_simulation(
    weights: np.ndarray,
    mean_returns: np.ndarray,
    cov_matrix: np.ndarray,
    portfolio_value: float = 1.0e6,
    horizon: int = 10,
    n_simulations: int = 10000,
    confidence_level: float = 0.99,
    seed: int = 12345,
) -> dict:  # type: ignore[type-arg]
    """Monte Carlo portfolio simulation of terminal P&L.

    Draws correlated multivariate-normal asset returns (RULE 3: pre-drawn in
    pure Python via Cholesky), compounds them over the horizon in a JIT kernel,
    and reports the simulated VaR / ES of terminal P&L.

    Args:
        weights: Portfolio weights per asset.
        mean_returns: Per-period mean return per asset.
        cov_matrix: Per-period asset return covariance matrix.
        portfolio_value: Starting portfolio value in base currency.
        horizon: Number of periods to simulate forward.
        n_simulations: Number of Monte Carlo paths.
        confidence_level: VaR/ES confidence in [0.90, 0.9999].
        seed: RNG seed for determinism.

    Returns:
        Dict with ``var_abs``, ``cvar_abs``, ``expected_pnl``, ``std_pnl`` and
        ``confidence_level``.

    Raises:
        ValueError: If shapes are inconsistent or sizes are non-positive.
    """
    w = np.asarray(weights, dtype=np.float64)
    mu = np.asarray(mean_returns, dtype=np.float64)
    cov = np.asarray(cov_matrix, dtype=np.float64)
    n_assets = w.size
    if mu.size != n_assets or cov.shape != (n_assets, n_assets):
        raise ValueError("mean_returns and cov_matrix must match weights length")
    if horizon < 1 or n_simulations < 1:
        raise ValueError("horizon and n_simulations must be >= 1")

    # Pre-draw all randomness in pure Python (RULE 3).
    rng = np.random.default_rng(seed)
    # Cholesky factor; jitter the diagonal for numerical PSD safety.
    chol = np.linalg.cholesky(cov + np.eye(n_assets) * 1e-12)
    z = rng.standard_normal(size=(n_simulations, horizon, n_assets))
    draws = mu + z @ chol.T  # broadcast mean; correlated returns
    draws = np.ascontiguousarray(draws, dtype=np.float64)

    pnl = _simulate_terminal_pnl(w, draws, float(portfolio_value))
    losses = -pnl
    sorted_losses = np.sort(losses)
    idx = int(np.floor(confidence_level * n_simulations))
    if idx > n_simulations - 1:
        idx = n_simulations - 1
    var_abs = float(sorted_losses[idx])
    tail = sorted_losses[idx:]
    cvar_abs = float(np.mean(tail)) if tail.size > 0 else var_abs
    return {
        "var_abs": round(var_abs, 2),
        "cvar_abs": round(cvar_abs, 2),
        "expected_pnl": round(float(np.mean(pnl)), 2),
        "std_pnl": round(float(np.std(pnl)), 2),
        "confidence_level": confidence_level,
        "n_simulations": int(n_simulations),
    }

"""tests/test_portfolio_risk.py — numerical-correctness tests for risk analytics.

No mocking (CLAUDE.md §5 RULE 1). Tests assert Euler additivity, beta=1 on
self, active share / turnover bounds, diversification ratio >= 1, HHI bounds,
LVaR >= market VaR, and Monte Carlo determinism + VaR<=CVaR.
"""

import numpy as np
import pytest

from engine.portfolio_risk import (
    active_share,
    concentration_risk_hhi,
    correlation_matrix_portfolio,
    diversification_ratio,
    liquidity_adjusted_portfolio_var,
    marginal_contribution_to_risk,
    monte_carlo_portfolio_simulation,
    portfolio_beta,
    portfolio_turnover,
    residual_risk,
    tracking_error,
    transaction_cost_analysis,
)


@pytest.fixture
def cov_weights():
    rng = np.random.default_rng(7)
    n = 4
    a = rng.normal(0, 1, size=(n, n))
    cov = (a @ a.T) / 100.0
    weights = np.array([0.4, 0.3, 0.2, 0.1])
    return weights, cov


@pytest.fixture
def two_series():
    rng = np.random.default_rng(5)
    r = rng.normal(0.0006, 0.012, size=500)
    b = 0.8 * r + rng.normal(0.0, 0.004, size=500)
    return r, b


# ── Beta ────────────────────────────────────────────────────────────────────


def test_beta_one_on_self(two_series):
    r, _ = two_series
    assert abs(portfolio_beta(r, r)["beta"] - 1.0) < 1e-9


def test_beta_r_squared_unit_interval(two_series):
    r, b = two_series
    res = portfolio_beta(r, b)
    assert 0.0 <= res["r_squared"] <= 1.0


# ── Active share ──────────────────────────────────────────────────────────────


def test_active_share_zero_when_identical():
    w = np.array([0.5, 0.3, 0.2])
    assert active_share(w, w)["active_share"] == 0.0


def test_active_share_one_when_disjoint():
    w = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert abs(active_share(w, b)["active_share"] - 1.0) < 1e-12


# ── Tracking error / residual risk ────────────────────────────────────────────


def test_tracking_error_zero_when_identical(two_series):
    r, _ = two_series
    assert tracking_error(r, r)["tracking_error"] == 0.0


def test_residual_risk_nonneg(two_series):
    r, b = two_series
    assert residual_risk(r, b)["residual_risk"] >= 0.0


# ── Turnover ──────────────────────────────────────────────────────────────────


def test_turnover_full_switch():
    before = np.array([1.0, 0.0])
    after = np.array([0.0, 1.0])
    assert abs(portfolio_turnover(before, after)["turnover"] - 1.0) < 1e-12


def test_turnover_zero_no_change():
    w = np.array([0.5, 0.5])
    assert portfolio_turnover(w, w)["turnover"] == 0.0


# ── TCA ───────────────────────────────────────────────────────────────────────


def test_tca_buy_above_benchmark_positive_cost():
    r = transaction_cost_analysis(
        trade_prices=np.array([101.0, 102.0]),
        benchmark_prices=np.array([100.0, 100.0]),
        trade_quantities=np.array([10.0, 10.0]),
        side=1,
    )
    assert r["slippage_bps"] > 0
    assert r["total_cost"] > 0


def test_tca_sell_below_benchmark_positive_cost():
    r = transaction_cost_analysis(
        trade_prices=np.array([99.0]),
        benchmark_prices=np.array([100.0]),
        trade_quantities=np.array([10.0]),
        side=-1,
    )
    assert r["slippage_bps"] > 0


# ── Marginal contribution to risk ─────────────────────────────────────────────


def test_mcr_components_sum_to_vol(cov_weights):
    w, cov = cov_weights
    r = marginal_contribution_to_risk(w, cov)
    assert abs(sum(r["component"]) - r["portfolio_volatility"]) < 1e-9
    assert abs(sum(r["percent_contribution"]) - 1.0) < 1e-6


# ── Diversification ratio ─────────────────────────────────────────────────────


def test_diversification_ratio_ge_one(cov_weights):
    w, cov = cov_weights
    assert diversification_ratio(w, cov)["diversification_ratio"] >= 1.0 - 1e-9


def test_diversification_ratio_one_for_single_asset():
    r = diversification_ratio(np.array([1.0]), np.array([[0.04]]))
    assert abs(r["diversification_ratio"] - 1.0) < 1e-9


# ── Correlation matrix ────────────────────────────────────────────────────────


def test_correlation_matrix_diagonal_one():
    rng = np.random.default_rng(1)
    m = rng.normal(0, 1, size=(200, 3))
    r = correlation_matrix_portfolio(m)
    for i in range(3):
        assert abs(r["correlation_matrix"][i][i] - 1.0) < 1e-9


# ── HHI ───────────────────────────────────────────────────────────────────────


def test_hhi_equal_weight_is_inverse_n():
    w = np.array([0.25, 0.25, 0.25, 0.25])
    r = concentration_risk_hhi(w)
    assert abs(r["hhi"] - 0.25) < 1e-12
    assert abs(r["effective_n"] - 4.0) < 1e-9
    assert abs(r["normalised_hhi"]) < 1e-12


def test_hhi_single_holding_is_one():
    r = concentration_risk_hhi(np.array([1.0, 0.0, 0.0]))
    assert abs(r["hhi"] - 1.0) < 1e-12


# ── Liquidity-adjusted VaR ────────────────────────────────────────────────────


def test_lvar_ge_market_var(cov_weights):
    w, cov = cov_weights
    spreads = np.array([0.001, 0.002, 0.0015, 0.003])
    r = liquidity_adjusted_portfolio_var(w, cov, spreads, 1e6, confidence_level=0.99)
    assert r["lvar_pct"] >= r["market_var_pct"]
    assert r["liquidity_cost_pct"] > 0


# ── Monte Carlo portfolio simulation ──────────────────────────────────────────


def test_mc_portfolio_deterministic(cov_weights):
    w, cov = cov_weights
    mu = np.full(4, 0.0005)
    r1 = monte_carlo_portfolio_simulation(w, mu, cov, n_simulations=5000, seed=99)
    r2 = monte_carlo_portfolio_simulation(w, mu, cov, n_simulations=5000, seed=99)
    assert r1["var_abs"] == r2["var_abs"]


def test_mc_portfolio_cvar_ge_var(cov_weights):
    w, cov = cov_weights
    mu = np.full(4, 0.0005)
    r = monte_carlo_portfolio_simulation(w, mu, cov, n_simulations=5000, seed=1)
    assert r["cvar_abs"] >= r["var_abs"]

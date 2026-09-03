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


def test_tca_default_unaffected_by_decision_price_feature():
    """Omitting decision_price reproduces the exact pre-change output."""
    p = np.array([100.5, 101.0, 99.8])
    bench = np.array([100.0, 100.0, 100.0])
    q = np.array([10.0, 5.0, 20.0])
    r = transaction_cost_analysis(p, bench, q, side=1)
    assert "delay_cost_bps" not in r
    assert "implementation_shortfall_bps" not in r
    assert set(r.keys()) == {"slippage_bps", "total_cost", "total_quantity", "n_fills"}


def test_tca_delay_cost_scalar_decision_price():
    p = np.array([101.0, 102.0])
    bench = np.array([100.5, 100.5])
    q = np.array([10.0, 5.0])
    decision = 100.0  # scalar decision price shared by both fills
    side = 1

    r = transaction_cost_analysis(p, bench, q, side=side, decision_price=decision)

    dp = np.full(2, decision)
    delay = side * (bench - dp)
    delay_cash = float(np.sum(delay * q))
    weighted_decision_ref = float(np.sum(dp * q))
    expected_delay_bps = delay_cash / weighted_decision_ref * 1e4

    exec_cash = float(np.sum(side * (p - bench) * q))
    expected_is_cash = delay_cash + exec_cash
    expected_is_bps = expected_is_cash / weighted_decision_ref * 1e4

    assert r["delay_cost"] == pytest.approx(delay_cash, rel=1e-8)
    assert r["delay_cost_bps"] == pytest.approx(expected_delay_bps, rel=1e-8)
    assert r["implementation_shortfall"] == pytest.approx(expected_is_cash, rel=1e-8)
    assert r["implementation_shortfall_bps"] == pytest.approx(expected_is_bps, rel=1e-8)

    # Reconciling identity: delay + execution cash == direct decision-price
    # shortfall (Perold's IS for the executed portion).
    direct_shortfall = float(np.sum(side * (p - dp) * q))
    assert r["implementation_shortfall"] == pytest.approx(direct_shortfall, rel=1e-8)


def test_tca_delay_cost_per_fill_decision_price():
    p = np.array([101.0, 99.0])
    bench = np.array([100.5, 99.5])
    q = np.array([10.0, 20.0])
    decision = np.array([100.0, 99.8])
    side = 1

    r = transaction_cost_analysis(p, bench, q, side=side, decision_price=decision)
    direct_shortfall = float(np.sum(side * (p - decision) * q))
    assert r["implementation_shortfall"] == pytest.approx(direct_shortfall, rel=1e-8)


def test_tca_decision_price_length_mismatch_raises():
    with pytest.raises(ValueError):
        transaction_cost_analysis(
            trade_prices=np.array([101.0, 102.0]),
            benchmark_prices=np.array([100.0, 100.0]),
            trade_quantities=np.array([10.0, 10.0]),
            decision_price=np.array([99.0]),
        )


def test_tca_opportunity_cost_adds_to_delay_and_execution():
    p = np.array([101.0, 102.0])
    bench = np.array([100.5, 100.5])
    q = np.array([10.0, 5.0])
    decision = 100.0
    side = 1
    unexecuted_quantity = 20.0
    cancellation_price = 103.0  # price rose further before the rest was cancelled

    r = transaction_cost_analysis(
        p,
        bench,
        q,
        side=side,
        decision_price=decision,
        unexecuted_quantity=unexecuted_quantity,
        cancellation_price=cancellation_price,
    )

    expected_opportunity_cash = side * (cancellation_price - decision) * unexecuted_quantity
    assert r["opportunity_cost"] == pytest.approx(expected_opportunity_cash, rel=1e-8)
    assert expected_opportunity_cash > 0.0  # price rose after cancellation -> real cost

    expected_total = r["implementation_shortfall"] + expected_opportunity_cash
    assert r["total_implementation_shortfall"] == pytest.approx(expected_total, rel=1e-8)

    full_notional = float(np.sum(np.full(2, decision) * q)) + decision * unexecuted_quantity
    expected_total_bps = expected_total / full_notional * 1e4
    assert r["total_implementation_shortfall_bps"] == pytest.approx(expected_total_bps, rel=1e-8)


def test_tca_default_unaffected_by_opportunity_cost_feature():
    """Omitting the opportunity-cost args reproduces exact pre-change output,
    even when decision_price is supplied."""
    p = np.array([101.0, 102.0])
    bench = np.array([100.5, 100.5])
    q = np.array([10.0, 5.0])
    r = transaction_cost_analysis(p, bench, q, side=1, decision_price=100.0)
    assert "opportunity_cost" not in r
    assert "total_implementation_shortfall" not in r


def test_tca_opportunity_cost_partial_args_raises():
    kwargs = dict(
        trade_prices=np.array([101.0]),
        benchmark_prices=np.array([100.5]),
        trade_quantities=np.array([10.0]),
        side=1,
        decision_price=100.0,
    )
    with pytest.raises(ValueError):
        transaction_cost_analysis(**kwargs, unexecuted_quantity=5.0)
    with pytest.raises(ValueError):
        transaction_cost_analysis(**kwargs, cancellation_price=101.0)


def test_tca_opportunity_cost_requires_decision_price():
    with pytest.raises(ValueError):
        transaction_cost_analysis(
            trade_prices=np.array([101.0]),
            benchmark_prices=np.array([100.5]),
            trade_quantities=np.array([10.0]),
            side=1,
            unexecuted_quantity=5.0,
            cancellation_price=101.0,
        )


def test_tca_opportunity_cost_requires_scalar_decision_price():
    with pytest.raises(ValueError):
        transaction_cost_analysis(
            trade_prices=np.array([101.0, 99.0]),
            benchmark_prices=np.array([100.5, 99.5]),
            trade_quantities=np.array([10.0, 20.0]),
            side=1,
            decision_price=np.array([100.0, 99.8]),
            unexecuted_quantity=5.0,
            cancellation_price=101.0,
        )


def test_tca_opportunity_cost_rejects_negative_unexecuted_quantity():
    with pytest.raises(ValueError):
        transaction_cost_analysis(
            trade_prices=np.array([101.0]),
            benchmark_prices=np.array([100.5]),
            trade_quantities=np.array([10.0]),
            side=1,
            decision_price=100.0,
            unexecuted_quantity=-5.0,
            cancellation_price=101.0,
        )


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

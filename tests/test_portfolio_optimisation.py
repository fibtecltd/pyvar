"""tests/test_portfolio_optimisation.py — numerical-correctness tests.

No mocking (CLAUDE.md §5 RULE 1). Tests assert weights sum to 1, non-negativity
under long-only, min-variance volatility is lowest, max-Sharpe dominates equal
weight, risk-parity equalises risk contributions, and Black-Litterman recovers
equilibrium with no views.
"""

import numpy as np
import pytest

from engine.portfolio_optimisation import (
    black_litterman_model,
    cvar_constrained_optimisation,
    equal_weight_portfolio,
    factor_based_optimisation,
    maximum_sharpe_ratio_portfolio,
    mean_variance_optimisation,
    minimum_variance_portfolio,
    resampled_efficient_frontier,
    risk_parity_portfolio,
    robust_portfolio_optimisation,
)


@pytest.fixture
def market():
    rng = np.random.default_rng(7)
    n = 4
    a = rng.normal(0, 1, size=(n, n))
    cov = (a @ a.T) / 100.0 + np.eye(n) * 0.001
    mu = np.array([0.0006, 0.0009, 0.0004, 0.0007])
    return mu, cov


def _sums_to_one(w):
    return abs(sum(w) - 1.0) < 1e-6


# ── Mean-variance ─────────────────────────────────────────────────────────────


def test_mean_variance_weights_sum_to_one(market):
    mu, cov = market
    r = mean_variance_optimisation(mu, cov, risk_aversion=3.0)
    assert _sums_to_one(r["weights"])
    assert all(w >= -1e-6 for w in r["weights"])  # long-only


def test_mean_variance_higher_aversion_lower_vol(market):
    mu, cov = market
    low = mean_variance_optimisation(mu, cov, risk_aversion=0.5)
    high = mean_variance_optimisation(mu, cov, risk_aversion=20.0)
    assert high["volatility"] <= low["volatility"] + 1e-6


# ── Minimum variance ──────────────────────────────────────────────────────────


def test_min_variance_weights_sum_to_one(market):
    _, cov = market
    r = minimum_variance_portfolio(cov)
    assert _sums_to_one(r["weights"])


def test_min_variance_lowest_volatility(market):
    mu, cov = market
    mv = minimum_variance_portfolio(cov, mean_returns=mu)
    ew = equal_weight_portfolio(4, mu, cov)
    assert mv["volatility"] <= ew["volatility"] + 1e-6


def test_min_variance_closed_form_short_allowed(market):
    _, cov = market
    r = minimum_variance_portfolio(cov, allow_short=True)
    assert _sums_to_one(r["weights"])


# ── Maximum Sharpe ────────────────────────────────────────────────────────────


def test_max_sharpe_dominates_equal_weight(market):
    mu, cov = market
    ms = maximum_sharpe_ratio_portfolio(mu, cov)
    ew = equal_weight_portfolio(4, mu, cov)
    assert ms["sharpe"] >= ew["sharpe"] - 1e-6
    assert _sums_to_one(ms["weights"])


# ── Risk parity ───────────────────────────────────────────────────────────────


def test_risk_parity_equalises_contributions(market):
    _, cov = market
    r = risk_parity_portfolio(cov)
    rc = r["risk_contributions"]
    assert max(rc) - min(rc) < 1e-3  # near-equal risk
    assert _sums_to_one(r["weights"])


# ── Equal weight ──────────────────────────────────────────────────────────────


def test_equal_weight_values():
    r = equal_weight_portfolio(5)
    assert all(abs(w - 0.2) < 1e-12 for w in r["weights"])


def test_equal_weight_invalid_n_raises():
    with pytest.raises(ValueError):
        equal_weight_portfolio(0)


# ── Black-Litterman ───────────────────────────────────────────────────────────


def test_black_litterman_no_views_recovers_equilibrium(market):
    mu, cov = market
    w_mkt = np.array([0.25, 0.25, 0.25, 0.25])
    # A view equal to the implied return with huge uncertainty -> posterior ~ pi.
    p = np.array([[1.0, 0.0, 0.0, 0.0]])
    lam = 2.5
    pi = lam * cov @ w_mkt
    q = np.array([pi[0]])
    omega = np.array([[1e6]])
    r = black_litterman_model(w_mkt, cov, p, q, risk_aversion=lam, omega=omega)
    assert abs(r["posterior_returns"][0] - r["implied_returns"][0]) < 1e-3


# ── Resampled frontier ────────────────────────────────────────────────────────


def test_resampled_frontier_weights_sum_to_one(market):
    mu, cov = market
    r = resampled_efficient_frontier(mu, cov, n_resamples=10, n_obs=120, seed=1)
    assert _sums_to_one(r["weights"])


def test_resampled_frontier_deterministic(market):
    mu, cov = market
    r1 = resampled_efficient_frontier(mu, cov, n_resamples=8, n_obs=100, seed=5)
    r2 = resampled_efficient_frontier(mu, cov, n_resamples=8, n_obs=100, seed=5)
    assert r1["weights"] == r2["weights"]


# ── Robust optimisation ───────────────────────────────────────────────────────


def test_robust_uses_worst_case_returns(market):
    mu, cov = market
    r = robust_portfolio_optimisation(mu, cov, uncertainty=0.1)
    assert _sums_to_one(r["weights"])
    # Worst-case returns are below the point estimates.
    assert all(wc <= m + 1e-12 for wc, m in zip(r["worst_case_returns"], mu))


# ── CVaR-constrained ──────────────────────────────────────────────────────────


def test_cvar_constrained_respects_limit():
    rng = np.random.default_rng(3)
    scen = rng.normal(0.0008, 0.02, size=(2000, 3))
    r = cvar_constrained_optimisation(scen, confidence_level=0.95, cvar_limit=0.04)
    assert _sums_to_one(r["weights"])
    if r["success"]:
        assert r["cvar"] <= 0.04 + 1e-4


def test_cvar_lp_matches_brute_force_grid_search():
    """The Rockafellar-Uryasev LP reformulation reaches the true constrained
    optimum: cross-checked against an independent brute-force grid search
    over the 2-asset weight simplex (task #17 portfolio-analytics reimpl).
    """
    rng = np.random.default_rng(99)
    scen = rng.normal(0.001, 0.02, size=(500, 2))
    mu = scen.mean(axis=0)
    conf = 0.95
    limit = 0.03

    def port_cvar(w):
        losses = -(scen @ w)
        var = np.quantile(losses, conf)
        tail = losses[losses >= var]
        return float(np.mean(tail)) if tail.size else float(var)

    best_ret, best_w = -np.inf, None
    for w1 in np.linspace(0.0, 1.0, 5001):
        w = np.array([w1, 1.0 - w1])
        if port_cvar(w) <= limit + 1e-9:
            ret = float(w @ mu)
            if ret > best_ret:
                best_ret, best_w = ret, w

    out = cvar_constrained_optimisation(
        scen, confidence_level=conf, cvar_limit=limit, periods_per_year=1
    )
    assert out["success"]
    assert out["weights"][0] == pytest.approx(best_w[0], abs=2e-4)
    assert out["expected_return"] == pytest.approx(best_ret, abs=1e-5)
    assert out["cvar"] <= limit + 1e-6


def test_cvar_lp_reconciles_var_leq_cvar():
    """CVaR_alpha >= VaR_alpha must hold at the optimum -- a property of the
    tail-mean definition itself, independent of the LP reformulation.
    """
    rng = np.random.default_rng(5)
    scen = rng.normal(0.0005, 0.015, size=(1000, 4))
    out = cvar_constrained_optimisation(scen, confidence_level=0.975, cvar_limit=0.05)
    assert out["var"] <= out["cvar"] + 1e-6


def test_cvar_lp_outperforms_retired_slsqp_on_repo_fixture():
    """Documents a real discrepancy found during the R-U LP migration (task
    #17): on this repo's own pre-existing fixture (test_cvar_constrained_
    respects_limit's rng/scenario setup), the retired SLSQP-on-empirical-
    CVaR implementation terminated after a single non-improving iteration
    at the equal-weight initial guess (SLSQP's finite-difference Jacobian
    of the quantile-based CVaR constraint is effectively flat at that
    point), reporting success=True despite ~40% CVaR budget left unused and
    a materially lower expected return than the true optimum. The LP finds
    the actual constrained optimum (CVaR binds at the limit, higher
    return) -- so the two do NOT numerically match on this fixture; the LP
    result is the correct one (independently confirmed against a brute-
    force grid search in test_cvar_lp_matches_brute_force_grid_search).
    """
    rng = np.random.default_rng(3)
    scen = rng.normal(0.0008, 0.02, size=(2000, 3))
    mu = scen.mean(axis=0)
    conf, limit = 0.95, 0.04

    def port_cvar(w):
        losses = -(scen @ w)
        var = np.quantile(losses, conf)
        tail = losses[losses >= var]
        return float(np.mean(tail)) if tail.size else float(var)

    # The retired implementation, reproduced verbatim for this regression check.
    from scipy.optimize import minimize

    def neg_return(w):
        return -float(w @ mu)

    constraints = (
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "ineq", "fun": lambda w: limit - port_cvar(w)},
    )
    old_res = minimize(
        neg_return,
        np.full(3, 1.0 / 3),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * 3,
        constraints=constraints,
    )
    old_ret = float(old_res.x @ mu)
    old_cvar = port_cvar(old_res.x)

    new_out = cvar_constrained_optimisation(
        scen, confidence_level=conf, cvar_limit=limit, periods_per_year=1
    )

    # The retired solver got stuck at its initial guess on this fixture.
    assert old_res.nit == 1
    assert np.allclose(old_res.x, np.full(3, 1.0 / 3))
    assert old_cvar < limit * 0.7  # far from binding -- budget left on the table

    # The LP finds a strictly better, constraint-binding optimum.
    assert new_out["cvar"] == pytest.approx(limit, abs=1e-6)
    assert new_out["expected_return"] > old_ret + 1e-4


# ── Factor-based ──────────────────────────────────────────────────────────────


def test_factor_based_weights_sum_to_one():
    rng = np.random.default_rng(4)
    b = rng.normal(0, 1, size=(5, 2))
    f = np.array([[0.04, 0.0], [0.0, 0.02]])
    spec = np.full(5, 0.01)
    r = factor_based_optimisation(b, f, spec)
    assert _sums_to_one(r["weights"])


def test_factor_based_matches_target_exposure():
    b = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])
    f = np.array([[0.04, 0.0], [0.0, 0.04]])
    spec = np.full(3, 0.01)
    target = np.array([0.6, 0.4])
    r = factor_based_optimisation(b, f, spec, target_exposures=target)
    if r["success"]:
        assert abs(r["factor_exposures"][0] - 0.6) < 1e-3
        assert abs(r["factor_exposures"][1] - 0.4) < 1e-3

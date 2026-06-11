"""tests/test_credit_var.py — numerical-correctness tests for Credit VaR family.

No mocking of engine functions (CLAUDE.md §5 RULE 1). Verifies: CVaR >= VaR,
VaR >= EL, ES is the mean beyond VaR, determinism with fixed seed, MC converges
to the analytical Vasicek formula, Merton DD monotonicity, and HHI bounds.
"""

import numpy as np
import pytest
from scipy import stats

from engine.credit_var import (
    credit_concentration_risk_hhi,
    credit_var_analytical_vasicek,
    credit_var_monte_carlo,
    creditmetrics_portfolio_model,
    default_correlation_matrix,
    kmv_merton_distance_to_default,
)


def test_mc_credit_var_ordering_and_determinism():
    n = 100
    pd = np.full(n, 0.02)
    lgd = np.full(n, 0.45)
    ead = np.full(n, 1e6)
    a = credit_var_monte_carlo(pd, lgd, ead, 0.15, 0.999, n_simulations=20_000, seed=1)
    b = credit_var_monte_carlo(pd, lgd, ead, 0.15, 0.999, n_simulations=20_000, seed=1)
    assert a == b  # determinism
    assert a["cvar"] >= a["var"] >= a["el"] >= 0.0
    assert abs(a["ul"] - (a["var"] - a["el"])) < 1e-3


def test_mc_el_matches_pd_lgd_ead():
    n = 200
    pd = np.full(n, 0.03)
    lgd = np.full(n, 0.5)
    ead = np.full(n, 1.0)
    r = credit_var_monte_carlo(pd, lgd, ead, 0.10, 0.99, n_simulations=40_000, seed=7)
    expected_el = 0.03 * 0.5 * 1.0 * n
    assert abs(r["el"] - expected_el) / expected_el < 0.05


def test_mc_converges_to_vasicek_for_large_homogeneous():
    # Large homogeneous portfolio MC VaR should approach analytical Vasicek.
    n = 1500
    pd_val, lgd_val, rho = 0.02, 0.45, 0.15
    mc = credit_var_monte_carlo(
        np.full(n, pd_val), np.full(n, lgd_val), np.full(n, 1.0 / n),
        rho, 0.99, n_simulations=40_000, seed=11,
    )
    ana = credit_var_analytical_vasicek(pd_val, lgd_val, 1.0, rho, 0.99)
    assert abs(mc["var"] - ana["var"]) < 0.02  # loss-rate units


def test_vasicek_var_ge_el_and_monotone_confidence():
    low = credit_var_analytical_vasicek(0.02, 0.45, 1e6, 0.15, 0.95)
    high = credit_var_analytical_vasicek(0.02, 0.45, 1e6, 0.15, 0.999)
    assert high["var"] > low["var"] >= low["el"]


def test_vasicek_zero_correlation_equals_el_scaled():
    # With rho=0 the conditional default rate equals PD, so VaR == EL.
    r = credit_var_analytical_vasicek(0.05, 0.6, 1000.0, 0.0, 0.999)
    assert abs(r["var"] - r["el"]) < 1e-6


def test_creditmetrics_matches_mc_engine():
    n = 50
    r = creditmetrics_portfolio_model(
        np.full(n, 1e5), np.full(n, 0.02), np.full(n, 0.45),
        0.2, 0.99, n_simulations=10_000, seed=3,
    )
    assert r["cvar"] >= r["var"] >= r["el"] >= 0.0


def test_merton_dd_increases_pd_decreases_with_assets():
    low_assets = kmv_merton_distance_to_default(110.0, 100.0, 0.3)
    high_assets = kmv_merton_distance_to_default(200.0, 100.0, 0.3)
    assert high_assets["distance_to_default"] > low_assets["distance_to_default"]
    assert high_assets["pd"] < low_assets["pd"]


def test_merton_pd_equals_normal_cdf_neg_dd():
    r = kmv_merton_distance_to_default(150.0, 100.0, 0.25, risk_free_rate=0.03)
    assert abs(r["pd"] - stats.norm.cdf(-r["distance_to_default"])) < 1e-9


def test_default_correlation_lt_asset_correlation():
    # Default correlation is always smaller in magnitude than asset correlation.
    pd = np.array([0.02, 0.02])
    a = np.array([[1.0, 0.3], [0.3, 1.0]])
    r = default_correlation_matrix(pd, a)
    assert 0.0 < r["matrix"][0][1] < 0.3
    assert r["matrix"][0][0] == 1.0


def test_hhi_single_name_is_one():
    r = credit_concentration_risk_hhi(np.array([100.0]))
    assert abs(r["hhi"] - 1.0) < 1e-12
    assert abs(r["effective_n"] - 1.0) < 1e-9


def test_hhi_granular_approaches_one_over_n():
    n = 10
    r = credit_concentration_risk_hhi(np.full(n, 5.0))
    assert abs(r["hhi"] - 1.0 / n) < 1e-12
    assert abs(r["effective_n"] - n) < 1e-9


def test_hhi_rejects_zero_total():
    with pytest.raises(ValueError):
        credit_concentration_risk_hhi(np.array([0.0, 0.0]))

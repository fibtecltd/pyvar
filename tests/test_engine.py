"""
tests/test_engine.py — Unit tests for the Monte Carlo VaR engine

These tests run without Redis, Celery, or a database.
They verify the pure numerical correctness of the engine.
"""

import numpy as np
import pytest

from engine.metrics import compute_breaches, compute_cvar, compute_loss_percentiles
from engine.montecarlo import run_monte_carlo_var

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_returns():
    rng = np.random.default_rng(42)
    return rng.normal(0.0005, 0.012, size=252)


# ── Engine tests ──────────────────────────────────────────────────────────────


def test_var_result_keys(synthetic_returns):
    result = run_monte_carlo_var(synthetic_returns, portfolio_value=1_000_000, n_simulations=10_000)
    expected_keys = {"var_pct", "var_abs", "cvar_pct", "cvar_abs", "loss_dist", "mu", "sigma"}
    assert expected_keys.issubset(result.keys())


def test_var_is_positive_loss(synthetic_returns):
    """VaR should represent a loss (positive value for a portfolio with positive drift)."""
    result = run_monte_carlo_var(synthetic_returns, portfolio_value=1_000_000, n_simulations=10_000)
    assert result["var_pct"] > 0, "VaR should be a positive loss"
    assert result["cvar_pct"] >= result["var_pct"], "CVaR should be >= VaR"


def test_var_scales_with_portfolio_value(synthetic_returns):
    """Absolute VaR should scale linearly with portfolio value."""
    r1 = run_monte_carlo_var(
        synthetic_returns, portfolio_value=1_000_000, n_simulations=10_000, seed=42
    )
    r2 = run_monte_carlo_var(
        synthetic_returns, portfolio_value=2_000_000, n_simulations=10_000, seed=42
    )
    assert (
        abs(r2["var_abs"] - 2 * r1["var_abs"]) < 1.0
    ), "Absolute VaR should double with portfolio value"


def test_cvar_greater_than_var(synthetic_returns):
    result = run_monte_carlo_var(synthetic_returns, portfolio_value=1_000_000, n_simulations=50_000)
    assert result["cvar_pct"] > result["var_pct"], "CVaR (ES) must exceed VaR"


def test_var_99_greater_than_var_95(synthetic_returns):
    """Higher confidence level → larger VaR."""
    r95 = run_monte_carlo_var(
        synthetic_returns, portfolio_value=1e6, confidence_level=0.95, n_simulations=50_000, seed=0
    )
    r99 = run_monte_carlo_var(
        synthetic_returns, portfolio_value=1e6, confidence_level=0.99, n_simulations=50_000, seed=0
    )
    assert r99["var_pct"] > r95["var_pct"], "99% VaR must exceed 95% VaR"


def test_loss_dist_length(synthetic_returns):
    n = 10_000
    result = run_monte_carlo_var(synthetic_returns, portfolio_value=1e6, n_simulations=n)
    assert len(result["loss_dist"]) == n


def test_loss_dist_is_sorted(synthetic_returns):
    result = run_monte_carlo_var(synthetic_returns, portfolio_value=1e6, n_simulations=10_000)
    losses = result["loss_dist"]
    assert losses == sorted(losses), "Loss distribution must be sorted ascending"


def test_deterministic_with_seed(synthetic_returns):
    """Same seed → same result."""
    r1 = run_monte_carlo_var(synthetic_returns, portfolio_value=1e6, n_simulations=10_000, seed=7)
    r2 = run_monte_carlo_var(synthetic_returns, portfolio_value=1e6, n_simulations=10_000, seed=7)
    assert r1["var_pct"] == r2["var_pct"]


# ── Antithetic variates tests (task #15 Phase 1) ────────────────────────────────


def test_antithetic_default_off(synthetic_returns):
    """antithetic defaults to False -- existing callers see unchanged behaviour."""
    r_default = run_monte_carlo_var(
        synthetic_returns, portfolio_value=1e6, n_simulations=10_000, seed=7
    )
    r_explicit_off = run_monte_carlo_var(
        synthetic_returns, portfolio_value=1e6, n_simulations=10_000, seed=7, antithetic=False
    )
    assert r_default["var_pct"] == r_explicit_off["var_pct"]
    assert r_default["cvar_pct"] == r_explicit_off["cvar_pct"]


def test_antithetic_deterministic_with_seed(synthetic_returns):
    r1 = run_monte_carlo_var(
        synthetic_returns, portfolio_value=1e6, n_simulations=10_000, seed=7, antithetic=True
    )
    r2 = run_monte_carlo_var(
        synthetic_returns, portfolio_value=1e6, n_simulations=10_000, seed=7, antithetic=True
    )
    assert r1["var_pct"] == r2["var_pct"]
    assert r1["cvar_pct"] == r2["cvar_pct"]


def test_antithetic_preserves_var_properties(synthetic_returns):
    """Antithetic sampling must not break the core VaR/CVaR properties."""
    result = run_monte_carlo_var(
        synthetic_returns, portfolio_value=1e6, n_simulations=10_000, antithetic=True
    )
    assert result["var_pct"] > 0
    assert result["cvar_pct"] >= result["var_pct"]
    assert len(result["loss_dist"]) == 10_000
    assert result["loss_dist"] == sorted(result["loss_dist"])


@pytest.mark.parametrize("n_simulations", [9_999, 10_000])
def test_antithetic_preserves_path_count(synthetic_returns, n_simulations):
    """Odd n_simulations gets one unmirrored extra draw; shape must still match exactly."""
    result = run_monte_carlo_var(
        synthetic_returns, portfolio_value=1e6, n_simulations=n_simulations, antithetic=True
    )
    assert len(result["loss_dist"]) == n_simulations
    assert result["n_simulations"] == n_simulations


def test_antithetic_reduces_variance_without_bias(synthetic_returns):
    """The actual property motivating Phase 1: at matched n_simulations, antithetic
    sampling should give a materially lower spread of VaR estimates across independent
    seeds than plain MC, while converging to essentially the same central estimate
    (portfolio P&L is a near-linear, monotonic function of the underlying normal
    draws here, which is exactly the regime where antithetic variance reduction is
    real, not just a smaller displayed error -- see run_monte_carlo_var's docstring).
    """
    seeds = range(100)
    n_simulations = 2_000

    plain = np.array(
        [
            run_monte_carlo_var(
                synthetic_returns, portfolio_value=1e6, n_simulations=n_simulations, seed=s
            )["var_pct"]
            for s in seeds
        ]
    )
    antithetic = np.array(
        [
            run_monte_carlo_var(
                synthetic_returns,
                portfolio_value=1e6,
                n_simulations=n_simulations,
                seed=s,
                antithetic=True,
            )["var_pct"]
            for s in seeds
        ]
    )

    assert np.var(antithetic) < np.var(
        plain
    ), "antithetic sampling should reduce VaR estimator variance"
    assert abs(np.mean(antithetic) - np.mean(plain)) < 3 * (
        np.std(plain) / np.sqrt(len(seeds))
    ), "antithetic sampling must not introduce material bias vs. plain MC"


# ── Metrics tests ─────────────────────────────────────────────────────────────


def test_compute_cvar():
    losses = np.linspace(0, 1, 1000)  # uniform 0..1
    cvar = compute_cvar(losses, confidence_level=0.99)
    # For uniform [0,1], CVaR at 99% ≈ mean of top 1% = 0.995
    assert abs(cvar - 0.995) < 0.01


def test_compute_loss_percentiles(synthetic_returns):
    result = run_monte_carlo_var(synthetic_returns, portfolio_value=1e6, n_simulations=10_000)
    losses = np.array(result["loss_dist"])
    pcts = compute_loss_percentiles(losses)
    assert "p0990" in pcts
    assert pcts["p0990"] <= pcts["p0995"]


def test_backtesting_breach_count():
    # Create scenario: VaR always 0.01 (1%), actual losses are 2%
    var_estimates = np.full(250, 0.01)
    actual_returns = np.full(250, -0.02)  # loss = 2% every day
    result = compute_breaches(actual_returns, var_estimates)
    assert result["n_breaches"] == 250
    assert result["basel_zone"] == "red"

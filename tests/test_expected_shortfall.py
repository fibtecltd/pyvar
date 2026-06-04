"""tests/test_expected_shortfall.py — numerical tests for the ES (CVaR) family.

Asserts the regulatory ES properties (CLAUDE.md §4.2): ES >= VaR, ES is the
mean of the tail, ES is monotone in confidence, Euler decompositions sum to
total ES, and stressed ES exceeds calm-period ES.
"""

import numpy as np
import pytest

from engine.expected_shortfall import (
    conditional_var_es,
    cvar_decomposition_euler,
    es_at_multiple_confidence_levels,
    expected_shortfall_contribution,
    historical_expected_shortfall,
    liquidity_adjusted_es,
    monte_carlo_expected_shortfall,
    stressed_expected_shortfall,
)


@pytest.fixture
def returns():
    rng = np.random.default_rng(42)
    return rng.normal(0.0005, 0.012, size=2000)


@pytest.fixture
def cov_weights():
    rng = np.random.default_rng(7)
    a = rng.normal(0, 1, size=(4, 4))
    cov = (a @ a.T) / 100.0
    weights = np.array([0.4, 0.3, 0.2, 0.1])
    return weights, cov


# ── 11. Conditional VaR (CVaR / ES) ───────────────────────────────────────────


def test_conditional_var_es_exceeds_var(returns):
    r = conditional_var_es(returns, 1e6, confidence_level=0.975)
    assert r["es_pct"] >= r["var_pct"]
    assert r["es_pct"] > 0


def test_conditional_var_es_is_tail_mean(returns):
    cl = 0.975
    r = conditional_var_es(returns, 1e6, confidence_level=cl)
    losses = np.sort(-returns)
    idx = int(np.floor(cl * losses.size))
    manual_es = float(np.mean(losses[idx:]))
    assert abs(r["es_pct"] - round(manual_es, 8)) < 1e-8


# ── 12. Historical Expected Shortfall ─────────────────────────────────────────


def test_historical_es_monotone_in_confidence(returns):
    r95 = historical_expected_shortfall(returns, 1e6, confidence_level=0.95)
    r99 = historical_expected_shortfall(returns, 1e6, confidence_level=0.99)
    assert r99["es_pct"] >= r95["es_pct"]


def test_historical_es_empty_raises():
    with pytest.raises(ValueError):
        historical_expected_shortfall(np.array([]), 1e6)


# ── 13. Monte Carlo Expected Shortfall ────────────────────────────────────────


def test_monte_carlo_es_deterministic_and_exceeds_var(returns):
    r1 = monte_carlo_expected_shortfall(returns, 1e6, n_simulations=20_000, seed=11)
    r2 = monte_carlo_expected_shortfall(returns, 1e6, n_simulations=20_000, seed=11)
    assert r1["es_pct"] == r2["es_pct"]
    assert r1["es_pct"] >= r1["var_pct"]


# ── 14. CVaR Decomposition (Euler) ────────────────────────────────────────────


def test_cvar_decomposition_sums_to_total(cov_weights):
    w, cov = cov_weights
    r = cvar_decomposition_euler(w, cov, 1e6, confidence_level=0.975)
    assert abs(sum(r["component"]) - r["es_pct"]) < 1e-8


def test_cvar_decomposition_exceeds_var_level(cov_weights):
    # Gaussian ES factor φ(z)/(1−α) > z, so ES > VaR for the same portfolio.
    w, cov = cov_weights
    r = cvar_decomposition_euler(w, cov, 1e6, confidence_level=0.975)
    assert r["es_pct"] > 0


# ── 15. Stressed Expected Shortfall (FRTB) ────────────────────────────────────


def test_stressed_es_exceeds_calm_period():
    rng = np.random.default_rng(0)
    calm = rng.normal(0.0, 0.01, size=500)
    stress = rng.normal(-0.002, 0.05, size=200)  # higher vol, negative drift
    series = np.concatenate([calm, stress])
    calm_es = stressed_expected_shortfall(series, 0, 500, 1e6)["stressed_es_pct"]
    stress_es = stressed_expected_shortfall(series, 500, 700, 1e6)["stressed_es_pct"]
    assert stress_es > calm_es


def test_stressed_es_invalid_window_raises(returns):
    with pytest.raises(ValueError):
        stressed_expected_shortfall(returns, 100, 50, 1e6)


# ── 16. Liquidity-Adjusted ES (FRTB LAH) ──────────────────────────────────────


def test_liquidity_adjusted_es_no_partials_equals_base():
    r = liquidity_adjusted_es(es_base=0.05, partial_es=[0.0, 0.0], liquidity_horizons=[10, 20, 40])
    assert abs(r["liquidity_adjusted_es"] - 0.05) < 1e-12


def test_liquidity_adjusted_es_increases_with_horizon_buckets():
    base = liquidity_adjusted_es(0.05, [0.0], [10, 20])["liquidity_adjusted_es"]
    more = liquidity_adjusted_es(0.05, [0.03], [10, 60])["liquidity_adjusted_es"]
    assert more > base
    assert more >= 0.05  # never below the base ES


def test_liquidity_adjusted_es_bad_lengths_raise():
    with pytest.raises(ValueError):
        liquidity_adjusted_es(0.05, [0.01, 0.02], [10, 20])  # len mismatch


# ── 17. ES at Multiple Confidence Levels ──────────────────────────────────────


def test_es_at_multiple_levels_monotone(returns):
    r = es_at_multiple_confidence_levels(returns, 1e6, confidence_levels=(0.95, 0.975, 0.99))
    vals = [r["es"]["cl_9500"], r["es"]["cl_9750"], r["es"]["cl_9900"]]
    assert vals == sorted(vals)


# ── 18. Expected Shortfall Contribution ───────────────────────────────────────


def test_es_contribution_sums_to_total():
    rng = np.random.default_rng(3)
    a = rng.normal(0.0, 0.02, size=(2000, 3))
    w = np.array([0.5, 0.3, 0.2])
    r = expected_shortfall_contribution(a, w, 1e6, confidence_level=0.975)
    assert abs(sum(r["contribution"]) - r["es_pct"]) < 1e-8


def test_es_contribution_shape_mismatch_raises():
    with pytest.raises(ValueError):
        expected_shortfall_contribution(np.zeros((10, 3)), np.array([1.0, 0.0]), 1e6)

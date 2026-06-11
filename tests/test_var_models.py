"""tests/test_var_models.py — numerical-correctness tests for the VaR family.

No mocking of engine functions (CLAUDE.md §5 RULE 1). Tests assert risk
properties: VaR > 0, CVaR >= VaR, monotonicity in confidence, linear scaling
with portfolio value, determinism, and analytic reductions.
"""

import numpy as np
import pytest

from engine.var_models import (
    component_var,
    cornish_fisher_var,
    filtered_historical_simulation_var,
    historical_simulation_var,
    incremental_var,
    marginal_var,
    monte_carlo_var_parametric_normal,
    parametric_delta_normal_var,
    var_by_risk_factor,
    var_fan_chart,
)


@pytest.fixture
def returns():
    rng = np.random.default_rng(42)
    return rng.normal(0.0005, 0.012, size=1000)


@pytest.fixture
def cov_weights():
    rng = np.random.default_rng(7)
    n = 4
    a = rng.normal(0, 1, size=(n, n))
    cov = (a @ a.T) / 100.0  # SPD covariance
    weights = np.array([0.4, 0.3, 0.2, 0.1])
    return weights, cov


# ── 1. Monte Carlo VaR (Parametric Normal) ────────────────────────────────────


def test_monte_carlo_var_parametric_normal(returns):
    r = monte_carlo_var_parametric_normal(returns, portfolio_value=1e6, n_simulations=20_000)
    assert r["var_pct"] > 0
    assert r["cvar_pct"] >= r["var_pct"]


# ── 2. Historical Simulation VaR ──────────────────────────────────────────────


def test_historical_simulation_var_positive(returns):
    r = historical_simulation_var(returns, portfolio_value=1e6, confidence_level=0.99)
    assert r["var_pct"] > 0
    assert r["cvar_pct"] >= r["var_pct"]


def test_historical_simulation_var_monotone_confidence(returns):
    r95 = historical_simulation_var(returns, 1e6, confidence_level=0.95)
    r99 = historical_simulation_var(returns, 1e6, confidence_level=0.99)
    assert r99["var_pct"] >= r95["var_pct"]


def test_historical_simulation_var_scales_linearly(returns):
    r1 = historical_simulation_var(returns, 1e6)
    r2 = historical_simulation_var(returns, 2e6)
    assert abs(r2["var_abs"] - 2 * r1["var_abs"]) < 1.0


def test_historical_simulation_var_empty_raises():
    with pytest.raises(ValueError):
        historical_simulation_var(np.array([]), 1e6)


# ── 3. Filtered Historical Simulation VaR ─────────────────────────────────────


def test_filtered_hs_var_positive_and_deterministic(returns):
    r1 = filtered_historical_simulation_var(returns, 1e6)
    r2 = filtered_historical_simulation_var(returns, 1e6)
    assert r1["var_pct"] > 0
    assert r1["cvar_pct"] >= r1["var_pct"]
    assert r1["var_pct"] == r2["var_pct"]  # deterministic, no RNG


def test_filtered_hs_var_requires_two_obs():
    with pytest.raises(ValueError):
        filtered_historical_simulation_var(np.array([0.01]), 1e6)


# ── 4. Parametric Delta-Normal VaR ────────────────────────────────────────────


def test_delta_normal_var_single_asset_matches_closed_form():
    # Single asset variance 0.04 → sigma 0.2; 99% z ≈ 2.326
    r = parametric_delta_normal_var([1.0], [[0.04]], 1e6, confidence_level=0.99)
    expected = 2.3263478740408408 * 0.2
    assert abs(r["var_pct"] - expected) < 1e-6


def test_delta_normal_var_sqrt_time_scaling(cov_weights):
    w, cov = cov_weights
    r1 = parametric_delta_normal_var(w, cov, 1e6, horizon_days=1)
    r10 = parametric_delta_normal_var(w, cov, 1e6, horizon_days=10)
    assert abs(r10["var_pct"] - np.sqrt(10) * r1["var_pct"]) < 1e-8


def test_delta_normal_var_shape_mismatch_raises():
    with pytest.raises(ValueError):
        parametric_delta_normal_var([1.0, 0.0], [[0.04]], 1e6)


# ── 5. Cornish-Fisher VaR ─────────────────────────────────────────────────────


def test_cornish_fisher_reduces_to_normal_when_no_higher_moments(returns):
    r = cornish_fisher_var(returns, 1e6, skewness=0.0, excess_kurtosis=0.0)
    mu, sigma = float(np.mean(returns)), float(np.std(returns))
    z = 2.3263478740408408
    expected = z * sigma - mu
    assert abs(r["var_pct"] - expected) < 1e-6


def test_cornish_fisher_fat_tails_increase_var(returns):
    base = cornish_fisher_var(returns, 1e6, skewness=0.0, excess_kurtosis=0.0)
    fat = cornish_fisher_var(returns, 1e6, skewness=0.0, excess_kurtosis=3.0)
    assert fat["var_pct"] > base["var_pct"]


# ── 6. Component VaR (Euler Allocation) ───────────────────────────────────────


def test_component_var_sums_to_total(cov_weights):
    w, cov = cov_weights
    r = component_var(w, cov, 1e6, confidence_level=0.99)
    assert abs(sum(r["component"]) - r["var_pct"]) < 1e-8  # Euler additivity


# ── 7. Marginal VaR ───────────────────────────────────────────────────────────


def test_marginal_var_times_weight_equals_component(cov_weights):
    w, cov = cov_weights
    m = marginal_var(w, cov, confidence_level=0.99)
    c = component_var(w, cov, 1e6, confidence_level=0.99)
    recomposed = [w[i] * m["marginal"][i] for i in range(len(w))]
    for i in range(len(w)):
        assert abs(recomposed[i] - c["component"][i]) < 1e-8


# ── 8. Incremental VaR ────────────────────────────────────────────────────────


def test_incremental_var_single_asset_equals_full(cov_weights):
    _, cov = cov_weights
    # 1-asset portfolio: removing it leaves VaR 0, so incremental == full VaR
    r = incremental_var(np.array([1.0]), np.array([[0.04]]), 0, 1e6)
    assert abs(r["incremental_pct"] - r["var_full_pct"]) < 1e-12
    assert abs(r["var_without_pct"]) < 1e-12


def test_incremental_var_out_of_range_raises(cov_weights):
    w, cov = cov_weights
    with pytest.raises(ValueError):
        incremental_var(w, cov, 99, 1e6)


# ── 9. VaR by Risk Factor ─────────────────────────────────────────────────────


def test_var_by_risk_factor_sums_to_total(cov_weights):
    b, fcov = cov_weights
    r = var_by_risk_factor(b, fcov, 1e6, confidence_level=0.99)
    assert abs(sum(r["contributions"].values()) - r["var_pct"]) < 1e-8


# ── 10. VaR Fan Chart (Percentile Bands) ──────────────────────────────────────


def test_var_fan_chart_monotone_in_confidence_and_horizon(returns):
    r = var_fan_chart(returns, 1e6, confidence_levels=(0.90, 0.99), horizon_days=10)
    low = r["bands"]["cl_9000"]
    high = r["bands"]["cl_9900"]
    # Higher confidence dominates at every horizon
    assert all(h >= lo for h, lo in zip(high, low))
    # VaR widens with horizon
    assert high[-1] > high[0]

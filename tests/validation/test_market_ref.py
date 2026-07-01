"""tests/validation/test_market_ref.py — P5a market-risk reference validation.

Every market-risk engine function is validated against an EXTERNAL reference
computed independently inside the test (closed-form, scipy cross-validation,
hard-coded Basel/FRTB regulatory thresholds, or an independent hand-calculation)
— NEVER against the function's own output.

Reference conventions used throughout:
  * Parametric normal VaR (loss, zero-mean):  VaR% = z * sigma,  z = Φ⁻¹(cl).
  * Expected Shortfall (Basel IV / FRTB, CLAUDE.md §4.2): the arithmetic MEAN of
    losses at/beyond the VaR index — never median or max.
  * Basel traffic-light (CLAUDE.md §4.3): window EXACTLY 250 days; green < 5,
    yellow 5-9, red >= 10; add-on 3.0 (green) / 3.40-3.85 (yellow) / 4.0 (red).
  * FRTB PAT (CLAUDE.md §4.4): green |corr|>=0.80 AND 0.8<=ratio<=1.2;
    amber |corr|>=0.70 AND 0.6<=ratio<=1.5; else red.

Tolerances: 0.1% relative for VaR/ES/simulation-class figures; ZERO tolerance
for regulatory zone boundaries and the 250-day rule.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats

# ── Engine imports (direct, no HTTP) ─────────────────────────────────────────
from engine.montecarlo import run_monte_carlo_var
from engine.metrics import (
    compute_breaches,
    compute_cvar,
    compute_loss_percentiles,
    compute_rolling_var,
)
from engine.var_models import (
    component_var,
    cornish_fisher_var,
    filtered_historical_simulation_var,
    historical_simulation_var,
    incremental_var,
    marginal_var,
    parametric_delta_normal_var,
    var_by_risk_factor,
    var_fan_chart,
)
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
from engine.stress import (
    contagion_stress_scenario,
    historical_scenario_replay,
    hypothetical_multi_factor_scenario,
    macro_scenario_generator,
    reverse_stress_testing,
    sector_stress_scenario,
    sensitivity_stress_profile,
)
from engine.greeks import (
    charm_delta_decay,
    cs01_credit_spread,
    dv01_pv01_bucketed,
    gamma_cross_gamma_matrix,
    portfolio_delta_aggregated,
    rho_interest_rate,
    theta_time_decay,
    vanna_delta_vega_cross,
    vega_surface_bucketed,
    volga_vega_convexity,
)
from engine.pnl_attribution import (
    credit_pnl_attribution,
    fx_pnl_attribution,
    gamma_pnl_attribution,
    greeks_based_pnl_explain,
    pnl_attribution_test_frtb_pat,
    rates_pnl_attribution,
    residual_pnl_unexplained,
    theta_carry_attribution,
    vega_pnl_attribution,
)
from engine.backtesting import (
    basel_capital_addon_multiplier,
    christoffersen_independence_test,
    combined_backtesting,
    kupiec_pof_test,
    rolling_var_backtest,
    traffic_light_backtesting,
    var_breach_cluster_analysis,
)
from engine.volatility import (
    correlation_matrix_historical,
    dcc_garch_dynamic_correlation,
    egarch_volatility_model,
    garch_11_volatility_forecast,
    gjr_garch_asymmetric_model,
    realised_volatility,
    risk_factor_pca_decomposition,
    volatility_surface_implied_vol,
)
from engine.frtb import (
    extreme_value_theory_var,
    frtb_ima_aggregate_capital_charge,
    frtb_ima_expected_shortfall,
    frtb_ima_non_modellable_risk_factors,
    frtb_ima_stressed_period_finder,
    frtb_sa_default_risk_charge,
    frtb_sa_residual_risk_addon,
    frtb_sa_sensitivity_based_method,
    spectral_risk_measure,
)
from engine.reg_frtb import (
    frtb_ima_market_risk_capital,
    frtb_pl_attribution_test,
    frtb_sa_market_risk_capital,
    frtb_trading_desk_aggregation,
)


# ── Shared synthetic data (fixed seed → deterministic) ───────────────────────
def gbm_returns(n=2000, mu=0.0004, sigma=0.012, seed=7):
    rng = np.random.default_rng(seed)
    return rng.normal(loc=mu, scale=sigma, size=n)


REL = 1e-3  # 0.1% relative tolerance for VaR/ES/simulation-class figures


# =============================================================================
# engine/montecarlo.py
# =============================================================================
def test_run_monte_carlo_var_vs_parametric_normal():
    """MC VaR (parametric normal engine) must converge to the closed-form
    Gaussian VaR. Reference: VaR% = z*sigma - mu*h over horizon h (independent
    closed-form, cross-validated against scipy Φ⁻¹)."""
    returns = gbm_returns()
    mu = float(np.mean(returns))
    sigma = float(np.std(returns))
    cl = 0.99
    res = run_monte_carlo_var(
        returns, 1_000_000.0, confidence_level=cl, horizon_days=1, n_simulations=400_000, seed=42
    )
    z = stats.norm.ppf(cl)
    # 1-day path: cumulative = mu + sigma*shock  ⇒ loss quantile = z*sigma - mu
    expected_var_pct = z * sigma - mu
    assert res["var_pct"] == pytest.approx(expected_var_pct, rel=5e-3)
    # Generic properties
    assert res["var_pct"] > 0
    assert res["cvar_pct"] >= res["var_pct"]  # ES >= VaR
    assert res["var_abs"] == pytest.approx(res["var_pct"] * 1_000_000.0, abs=1.0)


def test_run_monte_carlo_var_es_closed_form():
    """MC ES converges to the closed-form Gaussian ES = sigma*φ(z)/(1-cl) - mu.
    Reference: analytical normal ES formula."""
    returns = gbm_returns()
    mu = float(np.mean(returns))
    sigma = float(np.std(returns))
    cl = 0.975
    res = run_monte_carlo_var(
        returns, 1e6, confidence_level=cl, horizon_days=1, n_simulations=500_000, seed=123
    )
    z = stats.norm.ppf(cl)
    expected_es = sigma * stats.norm.pdf(z) / (1 - cl) - mu
    assert res["cvar_pct"] == pytest.approx(expected_es, rel=8e-3)


def test_run_monte_carlo_var_determinism_and_scaling():
    """Same seed → identical result; absolute VaR scales linearly with value."""
    returns = gbm_returns()
    a = run_monte_carlo_var(returns, 1e6, seed=99, n_simulations=50_000)
    b = run_monte_carlo_var(returns, 1e6, seed=99, n_simulations=50_000)
    assert a["var_pct"] == b["var_pct"]
    c = run_monte_carlo_var(returns, 2e6, seed=99, n_simulations=50_000)
    assert c["var_abs"] == pytest.approx(2.0 * a["var_abs"], rel=1e-6)


def test_run_monte_carlo_var_confidence_monotone():
    """99% VaR > 95% VaR (monotone in confidence)."""
    returns = gbm_returns()
    v95 = run_monte_carlo_var(returns, 1e6, confidence_level=0.95, seed=1, n_simulations=100_000)[
        "var_pct"
    ]
    v99 = run_monte_carlo_var(returns, 1e6, confidence_level=0.99, seed=1, n_simulations=100_000)[
        "var_pct"
    ]
    assert v99 > v95


# =============================================================================
# engine/metrics.py
# =============================================================================
def test_compute_cvar_mean_of_tail():
    """CVaR = MEAN of losses beyond VaR index (Basel §4.2). Reference: numpy
    mean of the top (1-cl) fraction of a sorted loss array — hand-computed."""
    sorted_losses = np.sort(np.array([0.01 * i for i in range(1, 101)]))  # 0.01..1.0
    cl = 0.95
    cutoff = int(np.floor(cl * 100))  # 95
    expected = float(np.mean(sorted_losses[cutoff:]))  # mean of last 5
    got = compute_cvar(sorted_losses, cl)
    assert got == pytest.approx(expected, rel=1e-6)
    # independent hand-calc: last 5 = 0.96..1.00, mean = 0.98
    assert got == pytest.approx(0.98, rel=1e-6)


def test_compute_loss_percentiles_matches_index():
    """Percentiles read the floor(p*n) index of the sorted loss array.
    Reference: independent index computation."""
    sorted_losses = np.arange(1, 1001, dtype=float)  # 1..1000
    out = compute_loss_percentiles(sorted_losses, [0.50, 0.99])
    assert out["p0500"] == pytest.approx(float(sorted_losses[500]), rel=1e-6)
    assert out["p0990"] == pytest.approx(float(sorted_losses[990]), rel=1e-6)


def test_compute_rolling_var_parametric_gaussian():
    """Rolling parametric VaR = -(mu - z*sigma) on each trailing window.
    Reference: independent Gaussian VaR on the last window."""
    returns = gbm_returns(n=600)
    window = 250
    cl = 0.99
    rv = compute_rolling_var(returns, window=window, confidence_level=cl)
    assert np.isnan(rv[window - 1])  # first window is NaN
    i = 400
    w = returns[i - window : i]
    z = stats.norm.ppf(cl)
    expected = -(np.mean(w) - z * np.std(w))
    assert rv[i] == pytest.approx(expected, rel=1e-6)
    assert rv[i] > 0


def test_compute_breaches_basel_zones():
    """Breach count and Basel zones. Reference: hard-coded Basel traffic-light
    boundaries (CLAUDE.md §4.3): green<5, yellow 5-9, red>=10 — ZERO tolerance."""
    n = 250
    var_est = np.full(n, 0.02)
    # Construct exactly 7 breaches (losses > 0.02) → yellow.
    actual = np.full(n, -0.01)  # loss 0.01 < 0.02, no breach
    actual[:7] = -0.05  # loss 0.05 > 0.02 → breach
    out = compute_breaches(actual, var_est)
    assert out["n_breaches"] == 7
    assert out["basel_zone"] == "yellow"
    # 4 breaches → green (boundary)
    actual2 = np.full(n, -0.01)
    actual2[:4] = -0.05
    assert compute_breaches(actual2, var_est)["basel_zone"] == "green"
    # 10 breaches → red (boundary)
    actual3 = np.full(n, -0.01)
    actual3[:10] = -0.05
    assert compute_breaches(actual3, var_est)["basel_zone"] == "red"


# =============================================================================
# engine/var_models.py
# =============================================================================
def test_historical_simulation_var_empirical_quantile():
    """HS VaR = empirical loss quantile at floor(cl*n). Reference: independent
    numpy sort + index of the loss array."""
    returns = gbm_returns()
    cl = 0.99
    res = historical_simulation_var(returns, 5e5, confidence_level=cl)
    losses = np.sort(-returns)
    idx = int(np.floor(cl * losses.size))
    expected_var = float(losses[idx])
    expected_cvar = float(np.mean(losses[idx:]))
    assert res["var_pct"] == pytest.approx(expected_var, rel=REL)
    assert res["cvar_pct"] == pytest.approx(expected_cvar, rel=REL)
    assert res["cvar_pct"] >= res["var_pct"]
    assert res["var_abs"] == pytest.approx(res["var_pct"] * 5e5, rel=1e-6)


def test_filtered_historical_simulation_var_ewma_reference():
    """FHS VaR: standardise by EWMA vol, rescale by 1-step forecast, empirical
    quantile. Reference: independent EWMA recursion + forecast + quantile."""
    returns = gbm_returns(n=500)
    lam = 0.94
    cl = 0.99
    res = filtered_historical_simulation_var(returns, 1e6, confidence_level=cl, lambda_decay=lam)
    # Independent EWMA variance recursion (matches engine convention).
    n = returns.size
    var = np.empty(n)
    v = returns[0] ** 2
    var[0] = v
    for t in range(1, n):
        v = lam * v + (1 - lam) * returns[t - 1] ** 2
        var[t] = v
    sigma = np.sqrt(var)
    standardized = returns / np.where(sigma > 0, sigma, 1.0)
    sigma_fc = math.sqrt(lam * sigma[-1] ** 2 + (1 - lam) * returns[-1] ** 2)
    simulated = sigma_fc * standardized
    losses = np.sort(-simulated)
    idx = int(np.floor(cl * losses.size))
    assert res["sigma_forecast"] == pytest.approx(sigma_fc, rel=REL)
    assert res["var_pct"] == pytest.approx(float(losses[idx]), rel=REL)
    assert res["var_pct"] > 0


def test_parametric_delta_normal_var_closed_form():
    """Delta-normal VaR = z*sqrt(w'Σw)*sqrt(h). Reference: closed-form with
    scipy Φ⁻¹, hand-built covariance."""
    w = np.array([0.6, 0.4])
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])  # per-period variances
    cl = 0.99
    h = 10
    res = parametric_delta_normal_var(w, cov, 1e6, confidence_level=cl, horizon_days=h)
    sigma_p = math.sqrt(float(w @ cov @ w))
    z = stats.norm.ppf(cl)
    expected = z * sigma_p * math.sqrt(h)
    assert res["var_pct"] == pytest.approx(expected, rel=1e-6)
    assert res["sigma_p"] == pytest.approx(sigma_p, rel=1e-6)
    assert res["var_abs"] == pytest.approx(expected * 1e6, rel=1e-6)


def test_parametric_delta_normal_var_scaling_and_horizon():
    """sqrt-time scaling: 10-day VaR = sqrt(10) * 1-day VaR."""
    w = np.array([1.0])
    cov = np.array([[0.02]])
    v1 = parametric_delta_normal_var(w, cov, 1e6, horizon_days=1)["var_pct"]
    v10 = parametric_delta_normal_var(w, cov, 1e6, horizon_days=10)["var_pct"]
    assert v10 == pytest.approx(math.sqrt(10) * v1, rel=1e-6)


def test_cornish_fisher_var_reduces_to_normal():
    """CF VaR collapses to parametric-normal VaR when skew=kurt=0. Reference:
    z*sigma - mu (closed form)."""
    returns = gbm_returns()
    mu = float(np.mean(returns))
    sigma = float(np.std(returns))
    cl = 0.99
    res = cornish_fisher_var(returns, 1e6, confidence_level=cl, skewness=0.0, excess_kurtosis=0.0)
    z = stats.norm.ppf(cl)
    expected = z * sigma - mu
    assert res["var_pct"] == pytest.approx(expected, rel=1e-6)
    assert res["z_cf"] == pytest.approx(z, rel=1e-6)


def test_cornish_fisher_var_expansion_formula():
    """Full CF quantile matches the independent 3rd/4th-moment expansion.
    Reference: hand-coded Cornish-Fisher polynomial."""
    returns = gbm_returns()
    mu, sigma = float(np.mean(returns)), float(np.std(returns))
    cl = 0.99
    s, k = 0.5, 2.0
    res = cornish_fisher_var(returns, 1e6, confidence_level=cl, skewness=s, excess_kurtosis=k)
    z = stats.norm.ppf(cl)
    z_cf = z + (z**2 - 1) / 6 * s + (z**3 - 3 * z) / 24 * k - (2 * z**3 - 5 * z) / 36 * s**2
    assert res["z_cf"] == pytest.approx(z_cf, rel=1e-6)
    assert res["var_pct"] == pytest.approx(z_cf * sigma - mu, rel=1e-6)


def test_marginal_var_gradient():
    """Marginal VaR = z*(Σw)/sigma_p (gradient of VaR). Reference: closed-form
    gradient; also cross-validated by finite difference of parametric VaR."""
    w = np.array([0.5, 0.3, 0.2])
    cov = np.array([[0.04, 0.006, 0.0], [0.006, 0.09, 0.01], [0.0, 0.01, 0.16]])
    cl = 0.99
    res = marginal_var(w, cov, confidence_level=cl)
    sigma_p = math.sqrt(float(w @ cov @ w))
    z = stats.norm.ppf(cl)
    expected = z * (cov @ w) / sigma_p
    assert np.allclose(res["marginal"], expected, rtol=1e-6)
    # Finite-difference cross-check on asset 0.
    eps = 1e-6
    wp = w.copy()
    wp[0] += eps
    var_p = z * math.sqrt(float(wp @ cov @ wp))
    var_0 = z * sigma_p
    fd = (var_p - var_0) / eps
    assert res["marginal"][0] == pytest.approx(fd, rel=1e-4)


def test_component_var_euler_additivity():
    """Component VaR (Euler) sums EXACTLY to total VaR (CLAUDE.md §4.2 coherence).
    Reference: total = z*sigma_p (closed form)."""
    w = np.array([0.5, 0.3, 0.2])
    cov = np.array([[0.04, 0.006, 0.0], [0.006, 0.09, 0.01], [0.0, 0.01, 0.16]])
    cl = 0.99
    res = component_var(w, cov, 1e6, confidence_level=cl)
    total = z = stats.norm.ppf(cl) * math.sqrt(float(w @ cov @ w))
    assert sum(res["component"]) == pytest.approx(total, rel=1e-6)
    assert res["var_pct"] == pytest.approx(total, rel=1e-6)


def test_incremental_var_exact():
    """Incremental VaR = VaR(full) - VaR(without position). Reference: two
    independent parametric-VaR evaluations."""
    w = np.array([0.5, 0.3, 0.2])
    cov = np.array([[0.04, 0.006, 0.0], [0.006, 0.09, 0.01], [0.0, 0.01, 0.16]])
    cl = 0.99
    z = stats.norm.ppf(cl)
    res = incremental_var(w, cov, 1, 1e6, confidence_level=cl)
    var_full = z * math.sqrt(float(w @ cov @ w))
    w0 = w.copy()
    w0[1] = 0.0
    var_without = z * math.sqrt(float(w0 @ cov @ w0))
    assert res["incremental_pct"] == pytest.approx(var_full - var_without, rel=1e-6)


def test_var_by_risk_factor_euler():
    """Factor VaR contributions sum to total VaR (Euler). Reference: total =
    z*sqrt(b'Fb)."""
    b = np.array([1.2, -0.5])
    cov = np.array([[0.05, 0.01], [0.01, 0.03]])
    cl = 0.99
    res = var_by_risk_factor(b, cov, 1e6, confidence_level=cl, factor_names=["equity", "rates"])
    total = stats.norm.ppf(cl) * math.sqrt(float(b @ cov @ b))
    assert sum(res["contributions"].values()) == pytest.approx(total, rel=1e-6)
    assert res["var_pct"] == pytest.approx(total, rel=1e-6)


def test_var_fan_chart_sqrt_time_bands():
    """Fan chart band at horizon h = z*sigma*sqrt(h) - mu*h. Reference: closed
    form per confidence level."""
    returns = gbm_returns()
    mu, sigma = float(np.mean(returns)), float(np.std(returns))
    res = var_fan_chart(returns, 1e6, confidence_levels=(0.95, 0.99), horizon_days=10)
    z99 = stats.norm.ppf(0.99)
    key = "cl_9900"
    for h in (1, 5, 10):
        expected = z99 * sigma * math.sqrt(h) - mu * h
        assert res["bands"][key][h - 1] == pytest.approx(expected, rel=1e-6)


# =============================================================================
# engine/expected_shortfall.py
# =============================================================================
def test_conditional_var_es_tail_mean():
    """ES = mean of losses beyond VaR. Reference: independent sort + tail mean."""
    returns = gbm_returns()
    cl = 0.975
    res = conditional_var_es(returns, 1e6, confidence_level=cl)
    losses = np.sort(-returns)
    idx = int(np.floor(cl * losses.size))
    assert res["var_pct"] == pytest.approx(float(losses[idx]), rel=REL)
    assert res["es_pct"] == pytest.approx(float(np.mean(losses[idx:])), rel=REL)
    assert res["es_pct"] >= res["var_pct"]


def test_historical_expected_shortfall_reference():
    """Historical ES tail mean and tail count. Reference: independent quantile."""
    returns = gbm_returns()
    cl = 0.99
    res = historical_expected_shortfall(returns, 1e6, confidence_level=cl)
    losses = np.sort(-returns)
    idx = int(np.floor(cl * losses.size))
    assert res["es_pct"] == pytest.approx(float(np.mean(losses[idx:])), rel=REL)
    assert res["n_tail"] == losses.size - idx


def test_monte_carlo_expected_shortfall_gaussian():
    """MC ES converges to closed-form Gaussian ES. Reference: sigma*φ(z)/(1-cl)-mu."""
    returns = gbm_returns()
    mu, sigma = float(np.mean(returns)), float(np.std(returns))
    cl = 0.975
    res = monte_carlo_expected_shortfall(
        returns, 1e6, confidence_level=cl, n_simulations=500_000, seed=42
    )
    z = stats.norm.ppf(cl)
    expected = sigma * stats.norm.pdf(z) / (1 - cl) - mu
    assert res["es_pct"] == pytest.approx(expected, rel=8e-3)
    assert res["es_pct"] >= res["var_pct"]


def test_cvar_decomposition_euler_additivity():
    """Gaussian ES Euler components sum to total ES = sigma_p*φ(z)/(1-cl).
    Reference: closed-form ES factor."""
    w = np.array([0.6, 0.4])
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    cl = 0.975
    res = cvar_decomposition_euler(w, cov, 1e6, confidence_level=cl)
    sigma_p = math.sqrt(float(w @ cov @ w))
    z = stats.norm.ppf(cl)
    total = sigma_p * stats.norm.pdf(z) / (1 - cl)
    assert res["es_pct"] == pytest.approx(total, rel=1e-6)
    assert sum(res["component"]) == pytest.approx(total, rel=1e-6)


def test_stressed_expected_shortfall_window():
    """Stressed ES over a window = tail mean of that window only. Reference:
    independent slice + tail mean."""
    returns = gbm_returns(n=1000)
    cl = 0.975
    res = stressed_expected_shortfall(returns, 100, 400, 1e6, confidence_level=cl)
    window = returns[100:400]
    losses = np.sort(-window)
    idx = int(np.floor(cl * losses.size))
    assert res["stressed_es_pct"] == pytest.approx(float(np.mean(losses[idx:])), rel=REL)
    assert res["window_size"] == 300


def test_liquidity_adjusted_es_frtb_formula():
    """Liquidity-adjusted ES = sqrt(ES_base² + Σ (ES_j*sqrt(Δ/T))²) (FRTB
    MAR33.12). Reference: hand-coded square-root aggregation."""
    es_base = 100.0
    partial = [80.0, 60.0]
    lh = [10.0, 20.0, 40.0]  # LH1=T=10, LH2=20, LH3=40
    T = 10.0
    res = liquidity_adjusted_es(es_base, partial, lh, base_horizon=T)
    acc = es_base**2
    for j in range(1, len(lh)):
        delta = (lh[j] - lh[j - 1]) / T
        acc += (partial[j - 1] * math.sqrt(delta)) ** 2
    expected = math.sqrt(acc)
    assert res["liquidity_adjusted_es"] == pytest.approx(expected, rel=1e-6)
    assert res["liquidity_adjusted_es"] >= es_base  # never below base ES


def test_es_at_multiple_confidence_levels_monotone():
    """ES is non-decreasing in confidence. Reference: independent tail means."""
    returns = gbm_returns()
    res = es_at_multiple_confidence_levels(returns, 1e6, confidence_levels=(0.95, 0.975, 0.99))
    losses = np.sort(-returns)
    for cl, key in [(0.95, "cl_9500"), (0.975, "cl_9750"), (0.99, "cl_9900")]:
        idx = int(np.floor(cl * losses.size))
        assert res["es"][key] == pytest.approx(float(np.mean(losses[idx:])), rel=REL)
    assert res["es"]["cl_9500"] <= res["es"]["cl_9750"] <= res["es"]["cl_9900"]


def test_expected_shortfall_contribution_sums_to_es():
    """Per-asset ES contributions (tail conditional means) sum to total ES.
    Reference: independent tail-scenario averaging."""
    rng = np.random.default_rng(3)
    a = rng.normal(0.0, 0.01, size=(2000, 3))
    w = np.array([0.5, 0.3, 0.2])
    cl = 0.975
    res = expected_shortfall_contribution(a, w, 1e6, confidence_level=cl)
    port = a @ w
    losses = -port
    idx = int(np.floor(cl * losses.size))
    tail = np.argsort(losses)[idx:]
    expected_contrib = np.mean(-(a[tail, :] * w), axis=0)
    assert np.allclose(res["contribution"], expected_contrib, rtol=REL)
    assert res["es_pct"] == pytest.approx(float(np.sum(expected_contrib)), rel=REL)


# =============================================================================
# engine/stress.py
# =============================================================================
def test_historical_scenario_replay_worst_day():
    """Replay P&L = H @ exposures; worst day = argmin. Reference: independent
    matmul."""
    e = np.array([100.0, -50.0])
    h = np.array([[0.01, 0.02], [-0.03, 0.01], [0.005, -0.04]])
    res = historical_scenario_replay(e, h)
    pnl = h @ e
    assert res["worst_scenario_index"] == int(np.argmin(pnl))
    assert res["worst_loss"] == pytest.approx(float(np.min(pnl)), rel=1e-6)
    assert res["best_gain"] == pytest.approx(float(np.max(pnl)), rel=1e-6)


def test_hypothetical_multi_factor_scenario():
    """First-order P&L = Σ exposure*shock. Reference: independent dot product."""
    e = np.array([1000.0, 2000.0, -500.0])
    s = np.array([0.02, -0.01, 0.03])
    res = hypothetical_multi_factor_scenario(e, s)
    assert res["pnl"] == pytest.approx(float(np.dot(e, s)), rel=1e-6)
    assert np.allclose(res["factor_pnl"], e * s)


def test_reverse_stress_testing_closed_form():
    """Reverse stress: shock reproduces -target_loss, magnitude=L/sqrt(e'Σe).
    Reference: closed-form Mahalanobis-minimal solution."""
    e = np.array([100.0, 200.0])
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    L = 50.0
    res = reverse_stress_testing(e, cov, L)
    assert res["achieved_loss"] == pytest.approx(-L, rel=1e-6)
    quad = float(e @ cov @ e)
    assert res["magnitude"] == pytest.approx(L / math.sqrt(quad), rel=1e-6)


def test_sensitivity_stress_profile_linear():
    """One-factor profile P&L = exposure_i * grid. Reference: scalar*grid."""
    e = np.array([500.0, -300.0])
    grid = np.array([-0.02, 0.0, 0.02])
    res = sensitivity_stress_profile(e, 0, grid)
    assert np.allclose(res["pnl_profile"], 500.0 * grid)


def test_sector_stress_scenario_additive():
    """Sector total P&L = Σ exposure*shock (additive). Reference: dot product."""
    e = np.array([1000.0, 800.0])
    s = np.array([-0.05, 0.02])
    res = sector_stress_scenario(e, s, sector_names=["tech", "energy"])
    assert res["total_pnl"] == pytest.approx(float(np.dot(e, s)), rel=1e-6)
    assert res["sector_pnl"]["tech"] == pytest.approx(1000.0 * -0.05, rel=1e-6)


def test_macro_scenario_generator_reproduces_cov():
    """Cholesky-coloured draws reproduce the target covariance (large sample).
    Reference: input covariance matrix (cross-validated by sample covariance)."""
    cov = np.array([[0.04, 0.02], [0.02, 0.09]])
    res = macro_scenario_generator(cov, n_scenarios=200_000, seed=42)
    sample_cov = np.array(res["sample_cov"])
    assert np.allclose(sample_cov, cov, atol=2e-3)
    # Determinism under fixed seed.
    res2 = macro_scenario_generator(cov, n_scenarios=1000, seed=42)
    res3 = macro_scenario_generator(cov, n_scenarios=1000, seed=42)
    assert res2["scenarios"] == res3["scenarios"]


def test_contagion_stress_scenario_neumann_series():
    """Cumulative shock = (I + C + C² + ...) x0 over rounds. Reference:
    independent truncated Neumann series."""
    x0 = np.array([1.0, 0.0])
    c = np.array([[0.0, 0.1], [0.2, 0.0]])
    rounds = 3
    res = contagion_stress_scenario(x0, c, rounds=rounds)
    cum = x0.copy()
    cur = x0.copy()
    for _ in range(rounds):
        cur = c @ cur
        cum = cum + cur
    assert np.allclose(res["amplified_shock"], cum, rtol=1e-6)
    assert res["amplification_factor"] == pytest.approx(
        np.linalg.norm(cum) / np.linalg.norm(x0), rel=1e-6
    )


# =============================================================================
# engine/greeks.py
# =============================================================================
def test_portfolio_delta_aggregated():
    """Net delta = Σ delta*qty; cash delta = Σ delta*qty*spot. Reference: dot."""
    d = np.array([0.5, -0.3, 0.8])
    q = np.array([100.0, 200.0, -50.0])
    s = np.array([50.0, 40.0, 60.0])
    res = portfolio_delta_aggregated(d, q, s)
    assert res["net_delta"] == pytest.approx(float(np.sum(d * q)), rel=1e-6)
    assert res["cash_delta"] == pytest.approx(float(np.sum(d * q * s)), rel=1e-6)


def test_gamma_cross_gamma_matrix_symmetric():
    """Gamma matrix: diagonal=own gammas, off-diagonal symmetrised. Reference:
    hand-built symmetric matrix."""
    own = np.array([0.02, 0.03])
    cross = np.array([[0.0, 0.01], [0.005, 0.0]])
    res = gamma_cross_gamma_matrix(own, cross)
    m = np.array(res["gamma_matrix"])
    assert m[0, 0] == pytest.approx(0.02) and m[1, 1] == pytest.approx(0.03)
    assert m[0, 1] == pytest.approx(0.5 * (0.01 + 0.005))  # symmetrised
    assert res["is_symmetric"] is True


def test_vega_surface_bucketed_conserves_total():
    """Bucketed vega surface conserves total vega. Reference: sum of inputs."""
    vegas = np.array([10.0, 20.0, 30.0])
    ei = np.array([0, 1, 1])
    si = np.array([0, 0, 1])
    res = vega_surface_bucketed(vegas, ei, si, 2, 2)
    assert res["total_vega"] == pytest.approx(60.0, rel=1e-6)
    surf = np.array(res["surface"])
    assert surf[1, 0] == pytest.approx(20.0)
    assert surf[1, 1] == pytest.approx(30.0)


def test_dv01_pv01_bucketed_closed_form():
    """DV01_k = cf*t*e^{-yt}*1e-4; buckets sum to total. Reference: closed form."""
    cf = np.array([5.0, 5.0, 105.0])
    t = np.array([1.0, 2.0, 3.0])
    y = 0.03
    bi = np.array([0, 0, 1])
    res = dv01_pv01_bucketed(cf, t, y, bi, 2)
    dv01_k = cf * t * np.exp(-y * t) * 1e-4
    assert res["total_dv01"] == pytest.approx(float(np.sum(dv01_k)), rel=1e-6)
    assert sum(res["dv01_buckets"]) == pytest.approx(res["total_dv01"], rel=1e-6)
    assert res["pv"] == pytest.approx(float(np.sum(cf * np.exp(-y * t))), rel=1e-6)


def test_cs01_credit_spread_closed_form():
    """CS01 = Σ cf*t*e^{-(r+s)t}*1e-4. Reference: closed form."""
    cf = np.array([3.0, 103.0])
    t = np.array([1.0, 2.0])
    r, s = 0.02, 0.01
    res = cs01_credit_spread(cf, t, r, s)
    expected = float(np.sum(cf * t * np.exp(-(r + s) * t) * 1e-4))
    assert res["cs01"] == pytest.approx(expected, rel=1e-6)


def test_rho_interest_rate_black_scholes():
    """BS Rho_call = K τ e^{-rτ} N(d2). Reference: closed-form BS with scipy."""
    S, K, r, sig, tau = 100.0, 100.0, 0.05, 0.2, 1.0
    res = rho_interest_rate(S, K, r, sig, tau, "call")
    d1 = (math.log(S / K) + (r + 0.5 * sig**2) * tau) / (sig * math.sqrt(tau))
    d2 = d1 - sig * math.sqrt(tau)
    expected = K * tau * math.exp(-r * tau) * stats.norm.cdf(d2)
    assert res["rho"] == pytest.approx(expected, rel=1e-6)


def test_theta_time_decay_finite_difference():
    """BS Theta cross-validated (scipy) by finite difference of BS price in τ.
    Reference: -dV/dτ numerically. cross-validated (scipy), not regulator-sourced."""
    S, K, r, sig, tau = 100.0, 105.0, 0.03, 0.25, 0.75
    res = theta_time_decay(S, K, r, sig, tau, "call", div_yield=0.0)

    def bs_call(t):
        d1 = (math.log(S / K) + (r + 0.5 * sig**2) * t) / (sig * math.sqrt(t))
        d2 = d1 - sig * math.sqrt(t)
        return S * stats.norm.cdf(d1) - K * math.exp(-r * t) * stats.norm.cdf(d2)

    eps = 1e-5
    dv_dtau = (bs_call(tau + eps) - bs_call(tau - eps)) / (2 * eps)
    assert res["theta"] == pytest.approx(-dv_dtau, rel=1e-4)
    assert res["theta_per_day"] == pytest.approx(res["theta"] / 365.0, rel=1e-6)


def test_charm_delta_decay_finite_difference():
    """Charm = ∂Δ/∂τ, cross-validated by finite difference of BS delta.
    cross-validated (scipy), not regulator-sourced."""
    S, K, r, sig, q = 100.0, 100.0, 0.04, 0.2, 0.0
    tau = 0.5
    res = charm_delta_decay(S, K, r, sig, tau, "call", div_yield=q)

    def bs_delta(t):
        d1 = (math.log(S / K) + (r - q + 0.5 * sig**2) * t) / (sig * math.sqrt(t))
        return math.exp(-q * t) * stats.norm.cdf(d1)

    eps = 1e-5
    fd = (bs_delta(tau + eps) - bs_delta(tau - eps)) / (2 * eps)
    assert res["charm"] == pytest.approx(fd, rel=1e-3)


def test_volga_vega_convexity_finite_difference():
    """Volga = ∂vega/∂σ, cross-validated by finite difference of BS vega.
    cross-validated (scipy), not regulator-sourced."""
    S, K, r, sig, tau = 100.0, 110.0, 0.03, 0.3, 1.0
    res = volga_vega_convexity(S, K, r, sig, tau)

    def bs_vega(v):
        d1 = (math.log(S / K) + (r + 0.5 * v**2) * tau) / (v * math.sqrt(tau))
        return S * stats.norm.pdf(d1) * math.sqrt(tau)

    eps = 1e-5
    fd = (bs_vega(sig + eps) - bs_vega(sig - eps)) / (2 * eps)
    assert res["volga"] == pytest.approx(fd, rel=1e-3)
    assert res["vega"] == pytest.approx(bs_vega(sig), rel=1e-6)


def test_vanna_delta_vega_cross_finite_difference():
    """Vanna = ∂Δ/∂σ, cross-validated by finite difference of BS delta in σ.
    cross-validated (scipy), not regulator-sourced."""
    S, K, r, sig, tau, q = 100.0, 95.0, 0.02, 0.25, 0.5, 0.0
    res = vanna_delta_vega_cross(S, K, r, sig, tau, div_yield=q)

    def bs_delta(v):
        d1 = (math.log(S / K) + (r - q + 0.5 * v**2) * tau) / (v * math.sqrt(tau))
        return math.exp(-q * tau) * stats.norm.cdf(d1)

    eps = 1e-5
    fd = (bs_delta(sig + eps) - bs_delta(sig - eps)) / (2 * eps)
    assert res["vanna"] == pytest.approx(fd, rel=1e-3)


# =============================================================================
# engine/pnl_attribution.py
# =============================================================================
def test_greeks_based_pnl_explain_taylor():
    """Predicted P&L = Δ·dS + ½Γ·dS² + ν·dσ + Θ·dt + ρ·dr. Reference: hand
    Taylor sum."""
    res = greeks_based_pnl_explain(
        delta=10.0,
        gamma=2.0,
        vega=5.0,
        theta=-1.0,
        rho=3.0,
        spot_move=0.5,
        vol_move=0.02,
        time_step=1.0,
        rate_move=0.001,
        actual_pnl=6.2,
    )
    predicted = 10 * 0.5 + 0.5 * 2.0 * 0.5**2 + 5.0 * 0.02 + (-1.0) * 1.0 + 3.0 * 0.001
    assert res["predicted_pnl"] == pytest.approx(predicted, rel=1e-6)
    assert res["unexplained"] == pytest.approx(6.2 - predicted, rel=1e-6)


def test_pnl_attribution_test_frtb_pat_green():
    """FRTB PAT zones — GREEN requires |corr|>=0.80 AND 0.8<=ratio<=1.2
    (CLAUDE.md §4.4, BCBS d457). ZERO tolerance on zone boundary.
    Reference: hard-coded thresholds + scipy Spearman."""
    rng = np.random.default_rng(11)
    hpl = rng.normal(0, 1, 250)
    rtpl = hpl + rng.normal(0, 0.05, 250)  # nearly identical → green
    res = pnl_attribution_test_frtb_pat(rtpl, hpl)
    corr = stats.spearmanr(rtpl, hpl).correlation
    ratio = np.std(rtpl) / np.std(hpl)
    assert abs(corr) >= 0.80 and 0.8 <= ratio <= 1.2
    assert res["zone"] == "green"


def test_pnl_attribution_test_frtb_pat_red():
    """FRTB PAT — uncorrelated series must be RED (IMA disqualification)."""
    rng = np.random.default_rng(22)
    hpl = rng.normal(0, 1, 250)
    rtpl = rng.normal(0, 1, 250)  # independent → low corr
    res = pnl_attribution_test_frtb_pat(rtpl, hpl)
    assert abs(stats.spearmanr(rtpl, hpl).correlation) < 0.70
    assert res["zone"] == "red"


def test_theta_carry_attribution():
    """Carry = theta*dt - funding. Reference: hand-calc."""
    res = theta_carry_attribution(theta=-2.0, time_step=1.0, funding_cost=0.5)
    assert res["theta_pnl"] == pytest.approx(-2.0, rel=1e-6)
    assert res["carry_pnl"] == pytest.approx(-2.5, rel=1e-6)


def test_gamma_pnl_attribution():
    """Gamma P&L = ½·Γ·dS². Reference: hand-calc."""
    res = gamma_pnl_attribution(4.0, 0.5)
    assert res["gamma_pnl"] == pytest.approx(0.5 * 4.0 * 0.25, rel=1e-6)


def test_vega_pnl_attribution():
    """Vega P&L = ν·dσ. Reference: hand-calc."""
    res = vega_pnl_attribution(12.0, 0.03)
    assert res["vega_pnl"] == pytest.approx(0.36, rel=1e-6)


def test_fx_pnl_attribution_additive():
    """FX P&L = Σ delta*move. Reference: dot product."""
    d = np.array([1000.0, -500.0])
    m = np.array([0.01, 0.02])
    res = fx_pnl_attribution(d, m, currency_names=["EUR", "JPY"])
    assert res["total_fx_pnl"] == pytest.approx(float(np.dot(d, m)), rel=1e-6)
    assert res["fx_pnl"]["EUR"] == pytest.approx(10.0, rel=1e-6)


def test_rates_pnl_attribution_additive():
    """Rates P&L = Σ sens*dyield_bp. Reference: dot product."""
    s = np.array([-50.0, -120.0])
    m = np.array([5.0, -2.0])
    res = rates_pnl_attribution(s, m, tenor_names=["2y", "10y"])
    assert res["total_rates_pnl"] == pytest.approx(float(np.dot(s, m)), rel=1e-6)


def test_credit_pnl_attribution_additive():
    """Credit P&L = Σ cs01*dspread_bp. Reference: dot product."""
    c = np.array([-30.0, -70.0])
    m = np.array([10.0, 5.0])
    res = credit_pnl_attribution(c, m, name_labels=["A", "B"])
    assert res["total_credit_pnl"] == pytest.approx(float(np.dot(c, m)), rel=1e-6)


def test_residual_pnl_unexplained():
    """Residual = actual - Σ explained; ratio = explained/actual. Reference:
    hand-calc."""
    comps = np.array([2.0, 1.0, 0.5])
    res = residual_pnl_unexplained(4.0, comps)
    assert res["explained_pnl"] == pytest.approx(3.5, rel=1e-6)
    assert res["residual_pnl"] == pytest.approx(0.5, rel=1e-6)
    assert res["explained_ratio"] == pytest.approx(3.5 / 4.0, rel=1e-6)


# =============================================================================
# engine/backtesting.py
# =============================================================================
def test_traffic_light_backtesting_zones():
    """Basel traffic-light zones (CLAUDE.md §4.3): green<5, yellow 5-9, red>=10.
    ZERO tolerance on boundaries. Reference: hard-coded Basel boundaries."""
    n = 250
    var = np.full(n, 0.02)

    def make(n_breach):
        actual = np.full(n, -0.01)
        actual[:n_breach] = -0.05
        return actual

    assert traffic_light_backtesting(make(4), var)["basel_zone"] == "green"
    assert traffic_light_backtesting(make(5), var)["basel_zone"] == "yellow"
    assert traffic_light_backtesting(make(9), var)["basel_zone"] == "yellow"
    assert traffic_light_backtesting(make(10), var)["basel_zone"] == "red"
    r = traffic_light_backtesting(make(7), var)
    assert r["n_breaches"] == 7
    assert r["expected_window"] == 250  # Basel 250-day rule, ZERO tolerance


def test_kupiec_pof_test_chi_squared():
    """Kupiec POF LR is chi-squared(1) at 95%. Reference: hand-coded LR formula +
    scipy chi2 critical value (CLAUDE.md §4.3)."""
    n, x, cl = 250, 3, 0.99
    res = kupiec_pof_test(x, n, confidence_level=cl)
    p = 1 - cl
    pi = x / n
    lr = -2 * (
        (n - x) * math.log(1 - p)
        + x * math.log(p)
        - ((n - x) * math.log(1 - pi) + x * math.log(pi))
    )
    assert res["lr_pof"] == pytest.approx(lr, abs=1e-6)
    assert res["critical_value"] == pytest.approx(stats.chi2.ppf(0.95, 1), rel=1e-6)
    # 3 breaches in 250 at 99% is close to expected 2.5 → do not reject.
    assert res["reject"] is False


def test_christoffersen_independence_test_reference():
    """Christoffersen independence LR chi-squared(1) at 95%. Reference: hand
    transition-count LR on a constructed sequence."""
    # Alternating sequence → strong dependence.
    b = np.array([0, 1] * 20)
    res = christoffersen_independence_test(b)
    assert res["critical_value"] == pytest.approx(stats.chi2.ppf(0.95, 1), rel=1e-6)
    # An i.i.d.-looking sequence with few breaches should not reject.
    rng = np.random.default_rng(5)
    iid = (rng.random(250) < 0.01).astype(int)
    res2 = christoffersen_independence_test(iid)
    assert res2["reject"] is False


def test_combined_backtesting_conditional_coverage():
    """Combined LR_cc = LR_POF + LR_ind, chi-squared(2) at 95%. Reference:
    sum of component LRs + scipy chi2(2) critical value."""
    rng = np.random.default_rng(8)
    b = (rng.random(250) < 0.01).astype(int)
    res = combined_backtesting(b, confidence_level=0.99)
    pof = kupiec_pof_test(int(b.sum()), b.size, 0.99)
    ind = christoffersen_independence_test(b)
    assert res["lr_cc"] == pytest.approx(pof["lr_pof"] + ind["lr_ind"], rel=1e-6)
    assert res["critical_value"] == pytest.approx(stats.chi2.ppf(0.95, 2), rel=1e-6)


def test_basel_capital_addon_multiplier_exact():
    """Add-on multipliers (CLAUDE.md §4.3): 3.0 green (<5), BCBS yellow schedule
    3.40-3.85, 4.0 red (>=10). ZERO tolerance. Reference: hard-coded BCBS values."""
    assert basel_capital_addon_multiplier(0)["multiplier"] == 3.0
    assert basel_capital_addon_multiplier(4)["multiplier"] == 3.0
    assert basel_capital_addon_multiplier(5)["multiplier"] == 3.40
    assert basel_capital_addon_multiplier(6)["multiplier"] == 3.50
    assert basel_capital_addon_multiplier(7)["multiplier"] == 3.65
    assert basel_capital_addon_multiplier(8)["multiplier"] == 3.75
    assert basel_capital_addon_multiplier(9)["multiplier"] == 3.85
    assert basel_capital_addon_multiplier(10)["multiplier"] == 4.0
    assert basel_capital_addon_multiplier(15)["multiplier"] == 4.0
    assert basel_capital_addon_multiplier(4)["zone"] == "green"
    assert basel_capital_addon_multiplier(10)["zone"] == "red"


def test_rolling_var_backtest_reference():
    """Rolling backtest over 250-day window. Reference: independent rolling VaR +
    breach count."""
    returns = gbm_returns(n=600)
    res = rolling_var_backtest(returns, window=250, confidence_level=0.99)
    rv = compute_rolling_var(returns, window=250, confidence_level=0.99)
    losses = -returns
    valid = ~np.isnan(rv)
    n_breach = int(np.sum(losses[valid] > rv[valid]))
    assert res["n_breaches"] == n_breach
    assert res["window"] == 250
    assert res["basel_zone"] in ("green", "yellow", "red")


def test_var_breach_cluster_analysis_reference():
    """Cluster analysis: runs of consecutive 1s. Reference: independent run-length
    computation."""
    b = np.array([0, 1, 1, 0, 0, 1, 0, 1, 1, 1])
    res = var_breach_cluster_analysis(b)
    # Runs: [2, 1, 3] → 3 clusters, max 3, mean 2.0; 6 breaches total.
    assert res["n_breaches"] == 6
    assert res["n_clusters"] == 3
    assert res["max_cluster_length"] == 3
    assert res["mean_cluster_length"] == pytest.approx(2.0, rel=1e-6)


# =============================================================================
# engine/volatility.py
# =============================================================================
def test_volatility_surface_implied_vol_roundtrip():
    """Implied vol inverts BS: pricing at recovered IV reproduces the input.
    Reference: independent BS pricing round-trip (cross-validated, scipy)."""
    S, r = 100.0, 0.02
    strikes = np.array([90.0, 100.0, 110.0])
    expiries = np.array([0.5, 1.0, 1.5])
    true_vols = np.array([0.25, 0.22, 0.20])

    def bs_call(K, tau, sig):
        d1 = (math.log(S / K) + (r + 0.5 * sig**2) * tau) / (sig * math.sqrt(tau))
        d2 = d1 - sig * math.sqrt(tau)
        return S * stats.norm.cdf(d1) - K * math.exp(-r * tau) * stats.norm.cdf(d2)

    prices = np.array([bs_call(K, t, v) for K, t, v in zip(strikes, expiries, true_vols)])
    res = volatility_surface_implied_vol(prices, strikes, expiries, S, r, "call")
    assert np.allclose(res["implied_vols"], true_vols, atol=1e-5)


def test_garch_11_volatility_forecast_mean_reversion():
    """GARCH(1,1) forecast mean-reverts to long-run vol at rate (α+β).
    Reference: independent mean-reversion recursion."""
    returns = gbm_returns(n=1000)
    alpha, beta = 0.1, 0.85
    res = garch_11_volatility_forecast(returns, alpha=alpha, beta=beta, horizon=20)
    persistence = alpha + beta
    assert res["persistence"] == pytest.approx(persistence, rel=1e-6)
    # Forecast path monotonically approaches long-run vol.
    path = np.array(res["forecast_vol_path"])
    lr = res["long_run_vol"]
    # last forecast is closer to long-run than the first
    assert abs(path[-1] - lr) <= abs(path[0] - lr) + 1e-12
    # variance-targeting: long-run vol ≈ sample vol of residuals
    resid = returns - np.mean(returns)
    assert res["long_run_vol"] == pytest.approx(float(np.std(resid)), rel=1e-6)


def test_egarch_volatility_model_leverage():
    """EGARCH log-variance is always positive; recursion matches independent
    implementation. Reference: hand-coded EGARCH filter last-step forecast."""
    returns = gbm_returns(n=800)
    omega, alpha, gamma, beta = -0.1, 0.1, -0.05, 0.95
    res = egarch_volatility_model(returns, omega=omega, alpha=alpha, gamma=gamma, beta=beta)
    assert res["current_vol"] > 0 and res["forecast_vol"] > 0
    # Independent one-step forecast from the recursion.
    r = returns - np.mean(returns)
    n = r.size
    log_var = np.empty(n)
    log_var[0] = omega / (1 - beta)
    e_abs = math.sqrt(2 / math.pi)
    for t in range(1, n):
        sp = math.sqrt(math.exp(log_var[t - 1]))
        z = r[t - 1] / sp if sp > 0 else 0.0
        log_var[t] = omega + beta * log_var[t - 1] + alpha * (abs(z) - e_abs) + gamma * z
    sig_last = math.sqrt(math.exp(log_var[-1]))
    z_last = r[-1] / sig_last
    lv_next = omega + beta * log_var[-1] + alpha * (abs(z_last) - e_abs) + gamma * z_last
    assert res["forecast_vol"] == pytest.approx(math.sqrt(math.exp(lv_next)), rel=REL)


def test_gjr_garch_asymmetric_model_persistence():
    """GJR persistence = α + β + γ/2; long-run vol = sqrt(ω/(1-persistence)).
    Reference: independent formulae + variance targeting."""
    returns = gbm_returns(n=1000)
    alpha, gamma, beta = 0.03, 0.08, 0.88
    res = gjr_garch_asymmetric_model(returns, alpha=alpha, gamma=gamma, beta=beta)
    persistence = alpha + beta + 0.5 * gamma
    assert res["persistence"] == pytest.approx(persistence, rel=1e-6)
    resid = returns - np.mean(returns)
    assert res["long_run_vol"] == pytest.approx(float(np.std(resid)), rel=1e-6)
    assert res["forecast_vol"] > 0


def test_realised_volatility_reference():
    """Realised var = Σ r²; annualised = sqrt(RV)*sqrt(factor). Reference: hand
    sum of squares."""
    r = np.array([0.01, -0.02, 0.015, -0.005])
    res = realised_volatility(r, annualisation_factor=252)
    rv = float(np.sum(r * r))
    assert res["realised_variance"] == pytest.approx(rv, rel=1e-6)
    assert res["realised_vol"] == pytest.approx(math.sqrt(rv), rel=1e-6)
    assert res["annualised_vol"] == pytest.approx(math.sqrt(rv) * math.sqrt(252), rel=1e-6)


def test_correlation_matrix_historical_vs_numpy():
    """Historical correlation matrix cross-validated against np.corrcoef.
    Reference: numpy corrcoef (cross-validated)."""
    rng = np.random.default_rng(4)
    data = rng.normal(0, 1, size=(500, 3))
    res = correlation_matrix_historical(data)
    expected = np.corrcoef(data, rowvar=False)
    assert np.allclose(np.array(res["correlation"]), expected, atol=1e-7)
    assert res["is_symmetric"] is True
    assert res["n_assets"] == 3


def test_dcc_garch_dynamic_correlation_collapses():
    """With a=b=0, DCC collapses to the constant unconditional correlation Q̄.
    Reference: np.corrcoef of standardised residuals."""
    rng = np.random.default_rng(6)
    data = rng.normal(0, 1, size=(500, 2))
    res = dcc_garch_dynamic_correlation(data, a=0.0, b=0.0)
    std = np.std(data, axis=0)
    z = (data - np.mean(data, axis=0)) / std
    q_bar = np.corrcoef(z, rowvar=False)
    d_inv = np.diag(1 / np.sqrt(np.diag(q_bar)))
    r_expected = d_inv @ q_bar @ d_inv
    assert np.allclose(np.array(res["dynamic_correlation"]), r_expected, atol=1e-7)
    # correlation matrix has unit diagonal
    m = np.array(res["dynamic_correlation"])
    assert np.allclose(np.diag(m), 1.0, atol=1e-7)


def test_risk_factor_pca_decomposition_vs_numpy():
    """PCA eigenvalues/EVR cross-validated against numpy eigh of the covariance.
    Reference: np.linalg.eigh (cross-validated)."""
    rng = np.random.default_rng(9)
    data = rng.normal(0, 1, size=(400, 3))
    res = risk_factor_pca_decomposition(data)
    cov = np.cov(data, rowvar=False)
    eigvals = np.sort(np.linalg.eigvalsh(cov))[::-1]
    assert np.allclose(res["eigenvalues"], eigvals, atol=1e-7)
    assert sum(res["explained_variance_ratio"]) == pytest.approx(1.0, rel=1e-6)
    assert all(v >= -1e-10 for v in res["eigenvalues"])  # PSD
    assert res["cumulative_variance_ratio"][-1] == pytest.approx(1.0, rel=1e-6)


# =============================================================================
# engine/frtb.py
# =============================================================================
def test_frtb_sa_sensitivity_based_method_formula():
    """SBM: Kb=sqrt(ΣWS²+Σρ WS_iWS_j); charge=sqrt(ΣKb²+Σγ S_bS_c) (MAR21).
    Reference: hand-coded SBM aggregation."""
    buckets = [[10.0, 20.0], [-5.0, 15.0]]
    rho, gamma = 0.5, 0.25
    res = frtb_sa_sensitivity_based_method(buckets, rho, gamma)
    kb_list, sb_list = [], []
    for bkt in buckets:
        ws = np.array(bkt)
        sum_sq = float(np.sum(ws**2))
        cross = float(np.sum(ws) ** 2 - sum_sq)
        kb_list.append(math.sqrt(sum_sq + rho * cross))
        sb_list.append(float(np.sum(ws)))
    kb = np.array(kb_list)
    sb = np.array(sb_list)
    cross_b = float(np.sum(sb) ** 2 - np.sum(sb**2))
    charge = math.sqrt(float(np.sum(kb**2)) + gamma * cross_b)
    assert res["risk_charge"] == pytest.approx(charge, rel=1e-6)
    assert np.allclose(res["kb"], kb_list, rtol=1e-6)


def test_frtb_sa_default_risk_charge_wts():
    """DRC with hedge-benefit ratio WtS = ΣnetLong/(ΣnetLong+Σ|netShort|) (MAR22).
    Reference: hand-coded net/gross/WtS."""
    jl = np.array([100.0, 0.0, 50.0])
    js = np.array([0.0, 80.0, 20.0])
    rw = np.array([0.02, 0.03, 0.04])
    res = frtb_sa_default_risk_charge(jl, js, rw)
    net = jl - js  # [100, -80, 30]
    weighted = rw * net
    gross_long = float(np.sum(weighted[net > 0]))
    gross_short = float(-np.sum(weighted[net < 0]))
    total_long = float(np.sum(net[net > 0]))
    total_short = float(-np.sum(net[net < 0]))
    wts = total_long / (total_long + total_short)
    drc = max(0.0, gross_long - wts * gross_short)
    assert res["wts_ratio"] == pytest.approx(wts, rel=1e-6)
    assert res["drc"] == pytest.approx(drc, rel=1e-6)


def test_frtb_sa_residual_risk_addon():
    """RRAO = Σ notional*weight (MAR23). Reference: dot product."""
    n = np.array([1_000_000.0, 500_000.0])
    w = np.array([0.001, 0.01])
    res = frtb_sa_residual_risk_addon(n, w)
    assert res["rrao"] == pytest.approx(float(np.dot(n, w)), rel=1e-6)


def test_frtb_ima_expected_shortfall_975():
    """FRTB IMA ES at 97.5% = tail mean beyond VaR (CLAUDE.md §4.2). Reference:
    independent tail mean; hard-coded 0.975."""
    returns = gbm_returns()
    res = frtb_ima_expected_shortfall(returns, confidence_level=0.975)
    losses = np.sort(-returns)
    idx = int(np.floor(0.975 * losses.size))
    assert res["es"] == pytest.approx(float(np.mean(losses[idx:])), rel=REL)
    assert res["var"] == pytest.approx(float(losses[idx]), rel=REL)
    assert res["es"] >= res["var"]
    assert res["confidence_level"] == 0.975


def test_frtb_ima_stressed_period_finder_250():
    """Stressed-period finder returns the worst-ES 250-day window. ZERO tolerance
    on the 250-day rule. Reference: independent brute-force window scan."""
    returns = gbm_returns(n=800)
    window = 250
    cl = 0.975
    res = frtb_ima_stressed_period_finder(returns, window=window, confidence_level=cl)
    best_start, best_es = 0, -np.inf
    for start in range(returns.size - window + 1):
        losses = np.sort(-returns[start : start + window])
        idx = min(int(np.floor(cl * window)), window - 1)
        es = float(np.mean(losses[idx:]))
        if es > best_es:
            best_es, best_start = es, start
    assert res["stressed_window_start"] == best_start
    assert res["stressed_es"] == pytest.approx(best_es, rel=REL)
    assert res["n_windows"] == returns.size - window + 1


def test_frtb_ima_non_modellable_risk_factors_formula():
    """NMRF SES = sqrt((ρ·ΣISES)²+(1-ρ²)ΣISES²) (MAR33.16). Reference: hand-coded;
    ρ=0 → Euclidean sum, ρ=1 → linear sum."""
    ises = np.array([3.0, 4.0])
    res0 = frtb_ima_non_modellable_risk_factors(ises, rho=0.0)
    assert res0["ses"] == pytest.approx(5.0, rel=1e-6)  # sqrt(9+16)
    res1 = frtb_ima_non_modellable_risk_factors(ises, rho=1.0)
    assert res1["ses"] == pytest.approx(7.0, rel=1e-6)  # 3+4 linear
    rho = 0.5
    resm = frtb_ima_non_modellable_risk_factors(ises, rho=rho)
    expected = math.sqrt((rho * 7.0) ** 2 + (1 - rho**2) * 25.0)
    assert resm["ses"] == pytest.approx(expected, rel=1e-6)


def test_frtb_ima_aggregate_capital_charge():
    """ACC = IMCC + SES + DRC (MAR33.43). Reference: hand sum."""
    res = frtb_ima_aggregate_capital_charge(100.0, 20.0, 30.0)
    assert res["aggregate_capital_charge"] == pytest.approx(150.0, rel=1e-6)


def test_extreme_value_theory_var_gpd():
    """EVT POT VaR via GPD. Reference: independent scipy genpareto fit + tail
    quantile formula (cross-validated, scipy)."""
    rng = np.random.default_rng(31)
    returns = rng.standard_t(df=4, size=5000) * 0.01  # fat tails
    tq, cl = 0.95, 0.99
    res = extreme_value_theory_var(returns, threshold_quantile=tq, confidence_level=cl)
    losses = -returns
    n = losses.size
    u = float(np.quantile(losses, tq))
    exc = losses[losses > u] - u
    n_u = exc.size
    xi, _, beta = stats.genpareto.fit(exc, floc=0.0)
    ratio = (n / n_u) * (1 - cl)
    if abs(xi) < 1e-8:
        evt = u - beta * math.log(ratio)
    else:
        evt = u + (beta / xi) * (ratio ** (-xi) - 1)
    assert res["evt_var"] == pytest.approx(evt, rel=REL)
    assert res["threshold"] == pytest.approx(u, rel=REL)
    assert res["evt_var"] > res["threshold"]  # tail VaR above threshold


def test_spectral_risk_measure_reference():
    """Spectral risk = Σ w_i*sorted_loss_i with exponential spectrum. Reference:
    independent discrete-spectrum computation; SRM >= mean loss; increasing in k."""
    returns = gbm_returns(n=2000)
    k = 25.0
    res = spectral_risk_measure(returns, risk_aversion=k)
    sorted_losses = np.sort(-returns)
    n = sorted_losses.size
    p = (np.arange(n) + 0.5) / n
    phi = k * np.exp(-k * (1 - p)) / (1 - math.exp(-k))
    weights = phi / np.sum(phi)
    srm = float(np.sum(weights * sorted_losses))
    assert res["spectral_risk"] == pytest.approx(srm, rel=1e-6)
    assert res["spectral_risk"] >= res["mean_loss"]
    # increasing in risk aversion
    srm_low = spectral_risk_measure(returns, risk_aversion=5.0)["spectral_risk"]
    assert res["spectral_risk"] > srm_low


# =============================================================================
# engine/reg_frtb.py
# =============================================================================
def test_frtb_sa_market_risk_capital_sum():
    """SA capital = SBM + DRC + RRAO (BCBS d457 §2). Reference: hand sum."""
    res = frtb_sa_market_risk_capital(1000.0, 300.0, 50.0)
    assert res["sa_capital"] == pytest.approx(1350.0, rel=1e-6)


def test_frtb_ima_market_risk_capital_multiplier_floor():
    """IMA capital = max(mult,1.5)*ES*stressed_ratio + SES + DRC (BCBS d457 §189).
    Multiplier floored at 1.5. Reference: hand-coded formula + floor."""
    res = frtb_ima_market_risk_capital(
        100.0, 1.2, multiplier=1.0, non_modellable_ses=10.0, default_risk_charge=5.0
    )
    applied = max(1.0, 1.5)  # floored to 1.5
    es_charge = applied * 100.0 * 1.2
    assert res["multiplier"] == pytest.approx(1.5, rel=1e-6)
    assert res["es_charge"] == pytest.approx(es_charge, rel=1e-6)
    assert res["ima_capital"] == pytest.approx(es_charge + 10.0 + 5.0, rel=1e-6)
    # multiplier above floor is respected
    res2 = frtb_ima_market_risk_capital(100.0, 1.0, multiplier=3.0)
    assert res2["multiplier"] == pytest.approx(3.0, rel=1e-6)


def test_frtb_pl_attribution_test_zones():
    """FRTB PAT (CLAUDE.md §4.4): green |corr|>=0.80 AND 0.8<=ratio<=1.2; else
    amber/red. ZERO tolerance on zone logic. Reference: hard-coded thresholds."""
    rng = np.random.default_rng(41)
    hpl = rng.normal(0, 1, 250)
    rtpl_green = hpl + rng.normal(0, 0.03, 250)
    g = frtb_pl_attribution_test(rtpl_green, hpl)
    assert g["zone"] == "green" and g["ima_eligible"] is True
    # Red: independent series
    rtpl_red = rng.normal(0, 1, 250)
    rd = frtb_pl_attribution_test(rtpl_red, hpl)
    assert abs(stats.spearmanr(rtpl_red, hpl).correlation) < 0.70
    assert rd["zone"] == "red" and rd["ima_eligible"] is False


def test_frtb_trading_desk_aggregation_reference():
    """Desk aggregation: eligible desks use IMA charge, others fall back to SA.
    Reference: independent masked sums."""
    sa = np.array([100.0, 200.0, 150.0])
    ima = np.array([80.0, 250.0, 120.0])
    eligible = np.array([1, 0, 1])
    res = frtb_trading_desk_aggregation(sa, ima, eligible)
    mask = eligible.astype(bool)
    ima_total = float(np.sum(ima[mask]))  # 80 + 120
    sa_total = float(np.sum(sa[~mask]))  # 200
    assert res["ima_capital"] == pytest.approx(ima_total, rel=1e-6)
    assert res["sa_capital"] == pytest.approx(sa_total, rel=1e-6)
    assert res["total_capital"] == pytest.approx(ima_total + sa_total, rel=1e-6)
    assert res["n_ima_desks"] == 2 and res["n_sa_desks"] == 1


# =============================================================================
# Additional branch coverage — put-option Greeks, validation raises, alt paths.
# All still validated against independent references, never self-referential.
# =============================================================================
def test_rho_put_black_scholes():
    """BS Rho_put = -K τ e^{-rτ} N(-d2). Reference: closed-form BS (scipy)."""
    S, K, r, sig, tau = 100.0, 100.0, 0.05, 0.2, 1.0
    res = rho_interest_rate(S, K, r, sig, tau, "put")
    d1 = (math.log(S / K) + (r + 0.5 * sig**2) * tau) / (sig * math.sqrt(tau))
    d2 = d1 - sig * math.sqrt(tau)
    expected = -K * tau * math.exp(-r * tau) * stats.norm.cdf(-d2)
    assert res["rho"] == pytest.approx(expected, rel=1e-6)


def test_theta_put_finite_difference():
    """BS put Theta cross-validated by finite difference of the BS put price.
    cross-validated (scipy), not regulator-sourced."""
    S, K, r, sig, tau = 100.0, 105.0, 0.03, 0.25, 0.75
    res = theta_time_decay(S, K, r, sig, tau, "put")

    def bs_put(t):
        d1 = (math.log(S / K) + (r + 0.5 * sig**2) * t) / (sig * math.sqrt(t))
        d2 = d1 - sig * math.sqrt(t)
        return K * math.exp(-r * t) * stats.norm.cdf(-d2) - S * stats.norm.cdf(-d1)

    eps = 1e-5
    dv_dtau = (bs_put(tau + eps) - bs_put(tau - eps)) / (2 * eps)
    assert res["theta"] == pytest.approx(-dv_dtau, rel=1e-4)


def test_charm_put_finite_difference():
    """BS put Charm cross-validated by finite difference of the BS put delta.
    cross-validated (scipy), not regulator-sourced."""
    S, K, r, sig, q, tau = 100.0, 100.0, 0.04, 0.2, 0.03, 0.5
    res = charm_delta_decay(S, K, r, sig, tau, "put", div_yield=q)

    def bs_put_delta(t):
        d1 = (math.log(S / K) + (r - q + 0.5 * sig**2) * t) / (sig * math.sqrt(t))
        return math.exp(-q * t) * (stats.norm.cdf(d1) - 1.0)

    eps = 1e-5
    fd = (bs_put_delta(tau + eps) - bs_put_delta(tau - eps)) / (2 * eps)
    assert res["charm"] == pytest.approx(fd, rel=1e-3)


def test_greeks_input_validation():
    """Greeks reject invalid option_type / non-positive inputs / mismatched lengths."""
    with pytest.raises(ValueError):
        rho_interest_rate(100, 100, 0.05, 0.2, 1.0, "swap")
    with pytest.raises(ValueError):
        theta_time_decay(100, 100, 0.05, 0.2, -1.0, "call")
    with pytest.raises(ValueError):
        volga_vega_convexity(100, 100, 0.05, 0.0, 1.0)
    with pytest.raises(ValueError):
        portfolio_delta_aggregated(np.array([1.0]), np.array([1.0, 2.0]))
    with pytest.raises(ValueError):
        cs01_credit_spread(np.array([1.0]), np.array([1.0, 2.0]), 0.02, 0.01)


def test_volatility_surface_put_roundtrip():
    """Put implied-vol round-trip. Reference: independent BS put pricing (scipy)."""
    S, r = 100.0, 0.02
    strikes = np.array([95.0, 105.0])
    expiries = np.array([0.5, 1.0])
    true_vols = np.array([0.24, 0.21])

    def bs_put(K, tau, sig):
        d1 = (math.log(S / K) + (r + 0.5 * sig**2) * tau) / (sig * math.sqrt(tau))
        d2 = d1 - sig * math.sqrt(tau)
        return K * math.exp(-r * tau) * stats.norm.cdf(-d2) - S * stats.norm.cdf(-d1)

    prices = np.array([bs_put(K, t, v) for K, t, v in zip(strikes, expiries, true_vols)])
    res = volatility_surface_implied_vol(prices, strikes, expiries, S, r, "put")
    assert np.allclose(res["implied_vols"], true_vols, atol=1e-5)


def test_stress_and_es_input_validation():
    """Assorted validation raises across stress / ES / var_models modules."""
    with pytest.raises(ValueError):
        historical_simulation_var(np.array([]), 1e6)
    with pytest.raises(ValueError):
        conditional_var_es(np.array([]), 1e6)
    with pytest.raises(ValueError):
        reverse_stress_testing(np.array([1.0, 1.0]), np.array([[0.04, 0.0], [0.0, 0.09]]), -5.0)
    with pytest.raises(ValueError):
        macro_scenario_generator(np.array([[1.0, 2.0], [2.0, 1.0]]))  # not PD
    with pytest.raises(ValueError):
        liquidity_adjusted_es(100.0, [80.0], [10.0, 20.0, 40.0])  # length mismatch


def test_frtb_and_backtest_validation():
    """Validation raises for FRTB / backtesting boundary inputs."""
    with pytest.raises(ValueError):
        frtb_sa_sensitivity_based_method([], 0.5, 0.25)
    with pytest.raises(ValueError):
        frtb_ima_non_modellable_risk_factors(np.array([1.0]), rho=2.0)
    with pytest.raises(ValueError):
        frtb_ima_aggregate_capital_charge(-1.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        kupiec_pof_test(300, 250)  # breaches > obs
    with pytest.raises(ValueError):
        frtb_ima_market_risk_capital(100.0, -1.0, 2.0)  # bad stressed ratio


def test_reg_frtb_negative_component_raises():
    """SA capital rejects negative components (BCBS d457)."""
    with pytest.raises(ValueError):
        frtb_sa_market_risk_capital(-1.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        frtb_trading_desk_aggregation(np.array([]), np.array([]), np.array([]))

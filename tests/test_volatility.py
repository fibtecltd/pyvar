"""tests/test_volatility.py — numerical tests for volatility & correlation models.

Implied vol: round-trip recovery. GARCH family: stationarity, mean-reversion of
the forecast to the long-run level, and positivity of conditional variance.
"""

import numpy as np
import pytest

from engine.volatility import (
    correlation_matrix_historical,
    dcc_garch_dynamic_correlation,
    egarch_volatility_model,
    garch_11_volatility_forecast,
    gjr_garch_asymmetric_model,
    realised_volatility,
    volatility_surface_implied_vol,
)


def _bs_call(S, K, r, sigma, tau):
    from scipy import stats

    sqrt_t = np.sqrt(tau)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * tau) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return S * stats.norm.cdf(d1) - K * np.exp(-r * tau) * stats.norm.cdf(d2)


# ── 52. Volatility Surface (Implied Vol) ──────────────────────────────────────


def test_implied_vol_round_trip():
    S, r = 100.0, 0.02
    true_vols = np.array([0.15, 0.20, 0.30])
    strikes = np.array([90.0, 100.0, 110.0])
    expiries = np.array([0.5, 1.0, 1.5])
    prices = np.array([_bs_call(S, k, r, v, t) for k, v, t in zip(strikes, true_vols, expiries)])
    r_out = volatility_surface_implied_vol(prices, strikes, expiries, S, r, "call")
    assert np.allclose(r_out["implied_vols"], true_vols, atol=1e-4)


def test_implied_vol_length_mismatch_raises():
    with pytest.raises(ValueError):
        volatility_surface_implied_vol(
            np.array([1.0]), np.array([100.0, 90.0]), np.array([1.0]), 100.0, 0.02
        )


# ── 53. GARCH(1,1) Volatility Forecast ────────────────────────────────────────


def test_garch_forecast_mean_reverts_to_long_run():
    rng = np.random.default_rng(1)
    returns = rng.normal(0.0, 0.02, size=1000)
    r = garch_11_volatility_forecast(returns, alpha=0.08, beta=0.90, horizon=200)
    path = r["forecast_vol_path"]
    # The far-horizon forecast should converge to the long-run volatility.
    assert abs(path[-1] - r["long_run_vol"]) < abs(path[0] - r["long_run_vol"]) + 1e-12
    assert abs(path[-1] - r["long_run_vol"]) < 1e-4


def test_garch_non_stationary_raises():
    with pytest.raises(ValueError):
        garch_11_volatility_forecast(np.random.default_rng(0).normal(size=100), alpha=0.5, beta=0.6)


# ── 54. EGARCH Volatility Model ───────────────────────────────────────────────


def test_egarch_positive_and_leverage_asymmetry():
    rng = np.random.default_rng(2)
    base = rng.normal(0.0, 0.02, size=500)
    neg = base.copy()
    pos = base.copy()
    neg[-1] = -0.10  # large negative shock
    pos[-1] = 0.10  # mirror positive shock
    r_neg = egarch_volatility_model(neg, gamma=-0.1)
    r_pos = egarch_volatility_model(pos, gamma=-0.1)
    assert r_neg["current_vol"] > 0 and r_neg["forecast_vol"] > 0
    # gamma < 0 => negative shock implies a higher next-period vol
    assert r_neg["forecast_vol"] > r_pos["forecast_vol"]


def test_egarch_non_stationary_raises():
    with pytest.raises(ValueError):
        egarch_volatility_model(np.random.default_rng(0).normal(size=100), beta=1.0)


# ── 55. GJR-GARCH Asymmetric Model ────────────────────────────────────────────


def test_gjr_garch_negative_shock_raises_vol_more():
    rng = np.random.default_rng(3)
    base = rng.normal(0.0, 0.02, size=500)
    neg, pos = base.copy(), base.copy()
    neg[-1], pos[-1] = -0.10, 0.10
    r_neg = gjr_garch_asymmetric_model(neg, gamma=0.1)
    r_pos = gjr_garch_asymmetric_model(pos, gamma=0.1)
    assert r_neg["forecast_vol"] > r_pos["forecast_vol"]  # gamma>0 leverage


def test_gjr_garch_non_stationary_raises():
    with pytest.raises(ValueError):
        gjr_garch_asymmetric_model(np.random.default_rng(0).normal(size=100), alpha=0.6, beta=0.6)


# ── 56. Realised Volatility ───────────────────────────────────────────────────


def test_realised_vol_annualisation_and_scaling():
    rng = np.random.default_rng(4)
    r = rng.normal(0.0, 0.01, size=78)
    base = realised_volatility(r, annualisation_factor=252)
    scaled = realised_volatility(2 * r, annualisation_factor=252)
    assert abs(scaled["realised_vol"] - 2 * base["realised_vol"]) < 1e-10
    assert abs(base["annualised_vol"] - base["realised_vol"] * np.sqrt(252)) < 1e-9


# ── 57. Correlation Matrix (Historical) ───────────────────────────────────────


def test_correlation_matrix_diagonal_and_symmetric():
    rng = np.random.default_rng(5)
    data = rng.normal(0, 1, size=(500, 3))
    r = correlation_matrix_historical(data)
    m = np.array(r["correlation"])
    assert r["is_symmetric"]
    assert np.allclose(np.diag(m), 1.0)


# ── 58. DCC-GARCH Dynamic Correlation ─────────────────────────────────────────


def test_dcc_reduces_to_constant_correlation_when_a_b_zero():
    rng = np.random.default_rng(6)
    data = rng.normal(0, 1, size=(800, 3))
    r = dcc_garch_dynamic_correlation(data, a=0.0, b=0.0)
    m = np.array(r["dynamic_correlation"])
    z = (data - data.mean(0)) / data.std(0)
    assert np.allclose(m, np.corrcoef(z, rowvar=False), atol=1e-8)


def test_dcc_invalid_params_raise():
    with pytest.raises(ValueError):
        dcc_garch_dynamic_correlation(np.zeros((10, 2)), a=0.6, b=0.6)

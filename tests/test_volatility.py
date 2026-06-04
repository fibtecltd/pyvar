"""tests/test_volatility.py — numerical tests for volatility & correlation models.

Implied vol: round-trip recovery. GARCH family: stationarity, mean-reversion of
the forecast to the long-run level, and positivity of conditional variance.
"""

import numpy as np
import pytest

from engine.volatility import garch_11_volatility_forecast, volatility_surface_implied_vol


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

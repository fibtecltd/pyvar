"""tests/test_greeks.py — numerical tests for the Greeks family.

Aggregation Greeks: additivity and conservation. Black-Scholes Greeks: signs
and finite-difference agreement against re-priced option values.
"""

import numpy as np
import pytest
from scipy import stats

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


def _bs_price(S, K, r, sigma, tau, opt="call", q=0.0):
    sqrt_t = np.sqrt(tau)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * tau) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if opt == "call":
        return S * np.exp(-q * tau) * stats.norm.cdf(d1) - K * np.exp(-r * tau) * stats.norm.cdf(d2)
    return K * np.exp(-r * tau) * stats.norm.cdf(-d2) - S * np.exp(-q * tau) * stats.norm.cdf(-d1)


def _bs_delta(S, K, r, sigma, tau, opt="call", q=0.0):
    sqrt_t = np.sqrt(tau)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * tau) / (sigma * sqrt_t)
    return np.exp(-q * tau) * (stats.norm.cdf(d1) if opt == "call" else stats.norm.cdf(d1) - 1.0)


def _bs_vega(S, K, r, sigma, tau, q=0.0):
    sqrt_t = np.sqrt(tau)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * tau) / (sigma * sqrt_t)
    return S * np.exp(-q * tau) * stats.norm.pdf(d1) * sqrt_t


# ── 26. Portfolio Delta (Aggregated) ──────────────────────────────────────────


def test_portfolio_delta_additive():
    d = np.array([0.5, -0.3, 0.8])
    q = np.array([100.0, 200.0, -50.0])
    r = portfolio_delta_aggregated(d, q)
    assert abs(r["net_delta"] - (0.5 * 100 - 0.3 * 200 + 0.8 * -50)) < 1e-9


def test_portfolio_delta_cash_delta():
    d = np.array([0.5, 1.0])
    q = np.array([10.0, 10.0])
    s = np.array([100.0, 50.0])
    r = portfolio_delta_aggregated(d, q, spot_prices=s)
    assert abs(r["cash_delta"] - (0.5 * 10 * 100 + 1.0 * 10 * 50)) < 1e-6


def test_portfolio_delta_length_mismatch_raises():
    with pytest.raises(ValueError):
        portfolio_delta_aggregated(np.array([0.5]), np.array([1.0, 2.0]))


# ── 27. Gamma and Cross-Gamma Matrix ──────────────────────────────────────────


def test_gamma_matrix_diagonal_and_symmetric():
    own = np.array([0.01, 0.02, 0.03])
    cross = np.array([[0.0, 0.005, 0.0], [0.005, 0.0, 0.001], [0.0, 0.001, 0.0]])
    r = gamma_cross_gamma_matrix(own, cross)
    m = np.array(r["gamma_matrix"])
    assert r["is_symmetric"]
    assert np.allclose(np.diag(m), own)


def test_gamma_matrix_bad_cross_shape_raises():
    with pytest.raises(ValueError):
        gamma_cross_gamma_matrix(np.array([0.01, 0.02]), np.zeros((3, 3)))


# ── 28. Vega Surface (Bucketed) ───────────────────────────────────────────────


def test_vega_surface_conserves_total():
    vegas = np.array([10.0, 20.0, 5.0, 15.0])
    ei = np.array([0, 1, 0, 1])
    si = np.array([0, 1, 1, 0])
    r = vega_surface_bucketed(vegas, ei, si, n_expiry=2, n_strike=2)
    assert abs(r["total_vega"] - 50.0) < 1e-9
    surface = np.array(r["surface"])
    assert abs(surface[0, 0] - 10.0) < 1e-9  # only first option in (0,0)


def test_vega_surface_out_of_range_raises():
    with pytest.raises(ValueError):
        vega_surface_bucketed(np.array([1.0]), np.array([5]), np.array([0]), 2, 2)


# ── 29. DV01 / PV01 (Tenor Bucketed) ──────────────────────────────────────────


def test_dv01_buckets_sum_to_total_and_positive():
    cf = np.array([5.0, 5.0, 105.0])  # 5% annual coupon bond, 3y
    t = np.array([1.0, 2.0, 3.0])
    bi = np.array([0, 0, 1])
    r = dv01_pv01_bucketed(cf, t, 0.03, bi, n_buckets=2)
    assert abs(sum(r["dv01_buckets"]) - r["total_dv01"]) < 1e-10
    assert r["total_dv01"] > 0
    assert abs(r["total_pv01"] - r["total_dv01"]) < 1e-12


def test_dv01_bad_bucket_raises():
    with pytest.raises(ValueError):
        dv01_pv01_bucketed(np.array([1.0]), np.array([1.0]), 0.03, np.array([5]), 2)


# ── 30. CS01 Credit Spread DV01 ───────────────────────────────────────────────


def test_cs01_positive_and_increases_with_maturity():
    cf_short = np.array([100.0])
    cf_long = np.array([100.0])
    r_short = cs01_credit_spread(cf_short, np.array([1.0]), 0.02, 0.01)
    r_long = cs01_credit_spread(cf_long, np.array([5.0]), 0.02, 0.01)
    assert r_short["cs01"] > 0
    assert r_long["cs01"] > r_short["cs01"]  # longer tenor → more spread risk


# ── 31. Rho (Interest Rate Sensitivity) ───────────────────────────────────────


def test_rho_matches_finite_difference():
    S, K, r, sig, tau = 100.0, 100.0, 0.03, 0.2, 1.0
    h = 1e-5
    fd = (_bs_price(S, K, r + h, sig, tau) - _bs_price(S, K, r - h, sig, tau)) / (2 * h)
    assert abs(rho_interest_rate(S, K, r, sig, tau)["rho"] - fd) < 1e-3


def test_rho_call_positive_put_negative():
    args = (100.0, 100.0, 0.03, 0.2, 1.0)
    assert rho_interest_rate(*args, option_type="call")["rho"] > 0
    assert rho_interest_rate(*args, option_type="put")["rho"] < 0


# ── 32. Theta (Time Decay) ────────────────────────────────────────────────────


def test_theta_matches_finite_difference():
    S, K, r, sig, tau = 100.0, 100.0, 0.03, 0.2, 1.0
    h = 1e-5
    # theta = -dV/dtau (calendar decay)
    fd = -(_bs_price(S, K, r, sig, tau + h) - _bs_price(S, K, r, sig, tau - h)) / (2 * h)
    assert abs(theta_time_decay(S, K, r, sig, tau)["theta"] - fd) < 1e-3


# ── 33. Charm (Delta Decay) ───────────────────────────────────────────────────


def test_charm_matches_finite_difference_of_delta():
    S, K, r, sig, tau = 100.0, 105.0, 0.03, 0.25, 0.75
    h = 1e-5
    fd = (_bs_delta(S, K, r, sig, tau + h) - _bs_delta(S, K, r, sig, tau - h)) / (2 * h)
    assert abs(charm_delta_decay(S, K, r, sig, tau)["charm"] - fd) < 1e-3


# ── 34. Volga (Vega Convexity) ────────────────────────────────────────────────


def test_volga_matches_finite_difference_of_vega():
    S, K, r, sig, tau = 100.0, 110.0, 0.03, 0.2, 1.0
    h = 1e-5
    fd = (_bs_vega(S, K, r, sig + h, tau) - _bs_vega(S, K, r, sig - h, tau)) / (2 * h)
    assert abs(volga_vega_convexity(S, K, r, sig, tau)["volga"] - fd) < 1e-2


# ── 35. Vanna (Delta-Vega Cross) ──────────────────────────────────────────────


def test_vanna_matches_finite_difference_of_vega_wrt_spot():
    S, K, r, sig, tau = 100.0, 110.0, 0.03, 0.2, 1.0
    h = 1e-3
    fd = (_bs_vega(S + h, K, r, sig, tau) - _bs_vega(S - h, K, r, sig, tau)) / (2 * h)
    assert abs(vanna_delta_vega_cross(S, K, r, sig, tau)["vanna"] - fd) < 1e-3

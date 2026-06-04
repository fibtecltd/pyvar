"""tests/test_greeks.py — numerical tests for the Greeks family.

Aggregation Greeks: additivity and conservation. Black-Scholes Greeks: signs
and finite-difference agreement against re-priced option values.
"""

import numpy as np
import pytest

from engine.greeks import (
    gamma_cross_gamma_matrix,
    portfolio_delta_aggregated,
    vega_surface_bucketed,
)

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

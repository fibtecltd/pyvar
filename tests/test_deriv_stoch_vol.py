"""tests/test_deriv_stoch_vol.py — numerical-correctness tests for vol models.

No mocking. Verifies Heston→BS limit (low vol-of-vol), SABR ATM positivity,
Dupire surface shape & non-negativity, MC determinism and put-call parity for
the Lévy models, and displaced-diffusion→BS reduction at zero displacement.
"""

import math

import numpy as np
import pytest

from engine.deriv_options_vanilla import black_scholes_european_option
from engine.deriv_stoch_vol import (
    displaced_diffusion_model,
    heston_stochastic_volatility_model,
    local_volatility_dupire_model,
    normal_inverse_gaussian_model,
    rough_volatility_rbergomi_model,
    sabr_volatility_model,
    variance_gamma_model,
)


def test_heston_approaches_bs_low_volvol():
    # v0 = theta, tiny vol-of-vol → BS with vol sqrt(theta)
    theta = 0.04
    h = heston_stochastic_volatility_model(
        100.0, 100.0, 0.03, 1.0, v0=theta, kappa=2.0, theta=theta, sigma=0.01, rho=0.0
    )["price"]
    bs = black_scholes_european_option(100.0, 100.0, 0.03, math.sqrt(theta), 1.0, "call")["price"]
    assert h == pytest.approx(bs, abs=0.15)


def test_heston_price_positive():
    h = heston_stochastic_volatility_model(
        100.0, 90.0, 0.03, 1.0, v0=0.04, kappa=1.5, theta=0.04, sigma=0.5, rho=-0.6
    )
    assert h["price"] > 0


def test_sabr_atm_positive_and_reasonable():
    v = sabr_volatility_model(0.03, 0.03, 1.0, alpha=0.02, beta=0.5, rho=-0.3, nu=0.4)[
        "implied_vol"
    ]
    assert v > 0


def test_sabr_smile_shape():
    base = sabr_volatility_model(100.0, 100.0, 1.0, alpha=0.2, beta=1.0, rho=-0.3, nu=0.5)[
        "implied_vol"
    ]
    wing = sabr_volatility_model(100.0, 80.0, 1.0, alpha=0.2, beta=1.0, rho=-0.3, nu=0.5)[
        "implied_vol"
    ]
    assert wing > base  # negative rho lifts downside strikes


def test_dupire_surface_shape_and_nonneg():
    strikes = np.array([80.0, 90.0, 100.0, 110.0, 120.0])
    maturities = np.array([0.5, 1.0, 1.5])
    surface = np.zeros((3, 5))
    for i, t in enumerate(maturities):
        for j, k in enumerate(strikes):
            surface[i, j] = black_scholes_european_option(100.0, k, 0.02, 0.2, t, "call")["price"]
    res = local_volatility_dupire_model(strikes, maturities, surface, rate=0.02, spot=100.0)
    loc = np.array(res["local_vol"])
    assert loc.shape == (2, 3)
    assert np.all(loc >= 0)


def test_rbergomi_price_positive_and_deterministic():
    a = rough_volatility_rbergomi_model(100.0, 100.0, 0.02, 1.0, n_simulations=20_000, seed=5)
    b = rough_volatility_rbergomi_model(100.0, 100.0, 0.02, 1.0, n_simulations=20_000, seed=5)
    assert a["price"] > 0
    assert a["price"] == b["price"]


def test_rbergomi_volterra_driver_matches_hand_calc():
    """Regression test for the autocovariance-structure bug (task #18): a
    previous version passed a broad option-price-band sanity check even
    though it silently froze each increment's weight at the moment it was
    drawn instead of recomputing it (as a gap to the current time) at every
    later step -- right marginal variance at any single time, wrong
    autocovariance between different times, invisible to a single-price-band
    test. A unit-impulse input makes the difference exact and hand-
    computable: only a correctly gap-based kernel decays after the impulse;
    the broken, frozen-weight kernel stays constant.
    """
    from engine.deriv_stoch_vol import _rbergomi_volterra_driver

    hurst = 0.1
    dt = 0.02
    n_steps = 10
    z_v = np.zeros(n_steps, dtype=np.float64)
    z_v[0] = 1.0  # unit impulse at the very first increment, silence elsewhere

    driver = _rbergomi_volterra_driver(hurst, z_v, dt)

    # Hand-computed reference: only k=0 contributes, weight = gap^(H-0.5)
    # where gap = t_now - 0 = (step+1)*dt, recomputed at every step.
    expected = np.array(
        [((step + 1) * dt) ** (hurst - 0.5) * math.sqrt(dt) for step in range(n_steps)]
    )
    np.testing.assert_allclose(driver, expected, rtol=1e-10)

    # Defining signature of a correct (gap-based) kernel: after a single
    # impulse the driver decays monotonically (H < 0.5 => weight shrinks as
    # the gap to t_now grows). A frozen-weight kernel stays constant after
    # step 0 -- that's exactly the bug this guards against.
    assert np.all(np.diff(driver) < 0.0)


def test_variance_gamma_put_call_parity():
    c = variance_gamma_model(
        100.0, 100.0, 0.03, 1.0, n_simulations=200_000, option_type="call", seed=3
    )["price"]
    p = variance_gamma_model(
        100.0, 100.0, 0.03, 1.0, n_simulations=200_000, option_type="put", seed=3
    )["price"]
    parity = 100.0 - 100.0 * math.exp(-0.03 * 1.0)
    assert (c - p) == pytest.approx(parity, abs=0.2)


def test_nig_price_positive():
    r = normal_inverse_gaussian_model(100.0, 100.0, 0.03, 1.0, n_simulations=100_000, seed=4)
    assert r["price"] > 0


def test_displaced_diffusion_reduces_to_bs():
    dd = displaced_diffusion_model(
        100.0, 100.0, 0.05, 0.2, 1.0, displacement=0.0, option_type="call"
    )["price"]
    bs = black_scholes_european_option(100.0, 100.0, 0.05, 0.2, 1.0, "call")["price"]
    assert dd == pytest.approx(bs, abs=1e-8)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        sabr_volatility_model(100.0, 100.0, 1.0, alpha=0.2, beta=1.5, rho=0.0, nu=0.4)
    with pytest.raises(ValueError):
        normal_inverse_gaussian_model(100.0, 100.0, 0.03, 1.0, alpha=3.0, beta=-5.0)

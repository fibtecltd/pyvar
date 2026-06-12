"""tests/test_deriv_options_exotic.py — numerical-correctness tests for exotics.

No mocking. Verifies digital bounds, barrier in-out parity, Asian < vanilla,
lookback >= vanilla, American >= European (LSM), Bermudan between the two,
basket diversification, spread→Margrabe, and determinism with fixed seeds.
"""

import math

import numpy as np
import pytest

from engine.deriv_options_exotic import (
    american_option_lsm,
    asian_option_pricer,
    barrier_option_pricer,
    basket_option_pricer,
    bermudan_option_pricer,
    chooser_option_pricer,
    compound_option_pricer,
    digital_option_pricer,
    lookback_option_pricer,
    rainbow_option_pricer,
    spread_option_kirk_approximation,
)
from engine.deriv_options_vanilla import black_scholes_european_option

S, K, R, SIG, T = 100.0, 100.0, 0.05, 0.2, 1.0


def test_digital_bounded_by_discounted_payout():
    d = digital_option_pricer(S, K, R, SIG, T, "call", payout=1.0)["price"]
    assert 0 < d < math.exp(-R * T)


def test_digital_call_put_sum_to_discounted_payout():
    c = digital_option_pricer(S, K, R, SIG, T, "call")["price"]
    p = digital_option_pricer(S, K, R, SIG, T, "put")["price"]
    assert (c + p) == pytest.approx(math.exp(-R * T), abs=1e-6)


def test_barrier_in_out_parity():
    ki = barrier_option_pricer(S, K, 90.0, R, SIG, T, "call", "down-and-in")["price"]
    ko = barrier_option_pricer(S, K, 90.0, R, SIG, T, "call", "down-and-out")["price"]
    vanilla = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    assert (ki + ko) == pytest.approx(vanilla, abs=1e-4)


def test_barrier_knockout_le_vanilla():
    ko = barrier_option_pricer(S, K, 90.0, R, SIG, T, "call", "down-and-out")["price"]
    vanilla = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    assert ko <= vanilla + 1e-6


def test_asian_cheaper_than_vanilla():
    asian = asian_option_pricer(S, K, R, SIG, T, n_simulations=80_000, option_type="call", seed=2)[
        "price"
    ]
    vanilla = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    assert 0 < asian < vanilla


def test_lookback_ge_vanilla():
    lb = lookback_option_pricer(
        S, K, R, SIG, T, n_simulations=60_000, option_type="call", strike_type="fixed", seed=2
    )["price"]
    vanilla = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    assert lb >= vanilla - 0.5


def test_american_put_ge_european():
    am = american_option_lsm(S, K, R, SIG, T, n_simulations=80_000, option_type="put", seed=3)[
        "price"
    ]
    eu = black_scholes_european_option(S, K, R, SIG, T, "put")["price"]
    assert am >= eu - 0.1  # LSM is a lower bound, allow MC noise


def test_bermudan_between_european_and_american():
    eu = black_scholes_european_option(S, K, R, SIG, T, "put")["price"]
    berm = bermudan_option_pricer(
        S, K, R, SIG, T, exercise_dates=4, n_simulations=80_000, option_type="put", seed=3
    )["price"]
    am = american_option_lsm(
        S, K, R, SIG, T, n_steps=48, n_simulations=80_000, option_type="put", seed=3
    )["price"]
    assert eu - 0.2 <= berm <= am + 0.3


def test_basket_le_weighted_singles():
    spots = np.array([100.0, 100.0])
    weights = np.array([0.5, 0.5])
    sigmas = np.array([0.2, 0.2])
    corr = np.array([[1.0, 0.3], [0.3, 1.0]])
    basket = basket_option_pricer(
        spots, weights, K, R, sigmas, T, corr, n_simulations=80_000, seed=4
    )["price"]
    single = black_scholes_european_option(100.0, K, R, 0.2, T, "call")["price"]
    assert 0 < basket <= single + 0.5


def test_rainbow_bestof_ge_worstof():
    spots = np.array([100.0, 100.0])
    sigmas = np.array([0.2, 0.25])
    corr = np.array([[1.0, 0.4], [0.4, 1.0]])
    best = rainbow_option_pricer(
        spots, K, R, sigmas, T, corr, n_simulations=80_000, rainbow_type="best-of", seed=5
    )["price"]
    worst = rainbow_option_pricer(
        spots, K, R, sigmas, T, corr, n_simulations=80_000, rainbow_type="worst-of", seed=5
    )["price"]
    assert best >= worst


def test_spread_margrabe_zero_strike():
    # Kirk with strike 0 = Margrabe exchange option
    price = spread_option_kirk_approximation(100.0, 95.0, 0.0, R, 0.2, 0.25, 0.5, T, "call")[
        "price"
    ]
    # Margrabe closed form
    sig = math.sqrt(0.2**2 - 2 * 0.5 * 0.2 * 0.25 + 0.25**2)
    d1 = (math.log(100.0 / 95.0) + 0.5 * sig**2 * T) / (sig * math.sqrt(T))
    from scipy.stats import norm

    # function treats spot1/spot2 as forwards and discounts once (Black-76)
    margrabe = math.exp(-R * T) * (100.0 * norm.cdf(d1) - 95.0 * norm.cdf(d1 - sig * math.sqrt(T)))
    assert price == pytest.approx(margrabe, abs=1e-4)


def test_compound_price_positive():
    c = compound_option_pricer(100.0, 100.0, 5.0, R, SIG, 0.5, 1.0, n_simulations=80_000, seed=6)
    assert c["price"] > 0


def test_chooser_ge_call_and_put():
    res = chooser_option_pricer(100.0, 100.0, R, SIG, 0.5, 1.0)
    assert res["price"] >= res["call_value"]
    assert res["price"] >= res["put_value"]


def test_asian_deterministic():
    a = asian_option_pricer(S, K, R, SIG, T, n_simulations=40_000, seed=9)["price"]
    b = asian_option_pricer(S, K, R, SIG, T, n_simulations=40_000, seed=9)["price"]
    assert a == b


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        barrier_option_pricer(S, K, 90.0, R, SIG, T, "call", "sideways")
    with pytest.raises(ValueError):
        compound_option_pricer(100.0, 100.0, 5.0, R, SIG, 1.0, 0.5)

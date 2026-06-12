"""tests/test_deriv_options_vanilla.py — numerical-correctness tests.

No mocking of engine functions (CLAUDE.md §5 RULE 1). Verifies put-call parity,
tree→Black-Scholes convergence, American >= European, zero-vol intrinsic value,
determinism, and Monte Carlo convergence to closed form.
"""

import math

import pytest

from engine.deriv_options_vanilla import (
    binomial_tree_option_pricer,
    black_scholes_european_option,
    black_scholes_greeks,
    monte_carlo_option_pricer,
    trinomial_tree_option_pricer,
)

S, K, R, SIG, T, Q = 100.0, 100.0, 0.05, 0.2, 1.0, 0.0


def test_bs_put_call_parity():
    c = black_scholes_european_option(S, K, R, SIG, T, "call", Q)["price"]
    p = black_scholes_european_option(S, K, R, SIG, T, "put", Q)["price"]
    # C - P = S e^{-qT} - K e^{-rT}
    assert c - p == pytest.approx(S * math.exp(-Q * T) - K * math.exp(-R * T), abs=1e-6)


def test_bs_known_atm_value():
    # ATM call S=K=100, r=0.05, sig=0.2, T=1 ≈ 10.4506
    c = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    assert c == pytest.approx(10.4506, abs=1e-3)


def test_bs_zero_vol_intrinsic():
    # sigma=0 -> discounted forward intrinsic
    c = black_scholes_european_option(110.0, 100.0, 0.0, 0.0, 1.0, "call")["price"]
    assert c == pytest.approx(10.0, abs=1e-8)


def test_bs_call_price_positive_and_monotone_in_spot():
    p1 = black_scholes_european_option(90.0, K, R, SIG, T, "call")["price"]
    p2 = black_scholes_european_option(110.0, K, R, SIG, T, "call")["price"]
    assert 0 < p1 < p2


def test_greeks_signs():
    g_call = black_scholes_greeks(S, K, R, SIG, T, "call")
    g_put = black_scholes_greeks(S, K, R, SIG, T, "put")
    assert 0 < g_call["delta"] < 1
    assert -1 < g_put["delta"] < 0
    assert g_call["gamma"] > 0
    assert g_call["vega"] > 0
    assert g_call["theta"] < 0  # long call decays


def test_binomial_converges_to_bs():
    bs = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    tree = binomial_tree_option_pricer(S, K, R, SIG, T, n_steps=2000, option_type="call")["price"]
    assert tree == pytest.approx(bs, abs=0.02)


def test_trinomial_converges_to_bs():
    bs = black_scholes_european_option(S, K, R, SIG, T, "put")["price"]
    tree = trinomial_tree_option_pricer(S, K, R, SIG, T, n_steps=800, option_type="put")["price"]
    assert tree == pytest.approx(bs, abs=0.02)


def test_american_geq_european_put():
    eu = binomial_tree_option_pricer(
        S, K, R, SIG, T, n_steps=500, option_type="put", style="european"
    )["price"]
    am = binomial_tree_option_pricer(
        S, K, R, SIG, T, n_steps=500, option_type="put", style="american"
    )["price"]
    assert am >= eu - 1e-9


def test_american_call_no_dividend_equals_european():
    # American call on a non-dividend stock = European call
    eu = binomial_tree_option_pricer(
        S, K, R, SIG, T, n_steps=600, option_type="call", style="european"
    )["price"]
    am = binomial_tree_option_pricer(
        S, K, R, SIG, T, n_steps=600, option_type="call", style="american"
    )["price"]
    assert am == pytest.approx(eu, abs=1e-2)


def test_monte_carlo_converges_to_bs():
    bs = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    mc = monte_carlo_option_pricer(
        S, K, R, SIG, T, n_simulations=200_000, option_type="call", seed=1
    )["price"]
    assert mc == pytest.approx(bs, abs=0.1)


def test_monte_carlo_deterministic_with_seed():
    a = monte_carlo_option_pricer(S, K, R, SIG, T, n_simulations=50_000, seed=99)["price"]
    b = monte_carlo_option_pricer(S, K, R, SIG, T, n_simulations=50_000, seed=99)["price"]
    assert a == b


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        black_scholes_european_option(S, K, R, SIG, T, "swap")
    with pytest.raises(ValueError):
        binomial_tree_option_pricer(S, K, R, SIG, T, n_steps=0)

"""tests/test_deriv_bonds.py — numerical-correctness tests for bond instruments.

No mocking. Verifies par pricing when coupon==yield, price↓ as yield↑, zero
discount-factor bounds, callable<=straight<=puttable, and convertible floor.
"""

import pytest

from engine.deriv_bonds import (
    bond_pricer_fixed_coupon,
    bond_pricer_floating_rate,
    callable_bond_pricer,
    convertible_bond_pricer,
    inflation_linked_bond_pricer,
    puttable_bond_pricer,
    zero_coupon_bond_pricer,
)


def test_fixed_coupon_par_when_coupon_equals_yield():
    p = bond_pricer_fixed_coupon(100.0, 0.05, 0.05, 10.0, frequency=2)["price"]
    assert p == pytest.approx(100.0, abs=1e-4)


def test_fixed_coupon_price_falls_as_yield_rises():
    low = bond_pricer_fixed_coupon(100.0, 0.05, 0.04, 10.0)["price"]
    high = bond_pricer_fixed_coupon(100.0, 0.05, 0.06, 10.0)["price"]
    assert low > 100.0 > high


def test_zero_coupon_discount_bounds():
    r = zero_coupon_bond_pricer(100.0, 0.05, 5.0)
    assert 0 < r["price"] < 100.0
    assert 0 < r["discount_factor"] < 1.0


def test_floating_rate_near_par_at_reset():
    n = 8
    ref = [0.03] * n
    disc = [0.03] * n
    p = bond_pricer_floating_rate(100.0, ref, 0.0, disc, 2.0, frequency=4)["price"]
    assert p == pytest.approx(100.0, abs=1e-4)


# ── maturity/len(reference_rates) consistency check (caveat-triage batch 2) ──
# maturity previously was validated only as >0 and never reconciled against
# the actual number of periods priced (len(reference_rates)/frequency).


def test_floating_rate_rejects_maturity_inconsistent_with_period_count():
    n = 8  # 8 periods at frequency=4 implies maturity=2.0, not 3.0
    ref = [0.03] * n
    disc = [0.03] * n
    with pytest.raises(ValueError):
        bond_pricer_floating_rate(100.0, ref, 0.0, disc, 3.0, frequency=4)


def test_floating_rate_accepts_maturity_consistent_with_period_count():
    n = 8
    ref = [0.03] * n
    disc = [0.03] * n
    # Must not raise -- this is the exact case test_floating_rate_near_par_at_reset
    # already relies on (8 periods at frequency=4 == maturity 2.0).
    p = bond_pricer_floating_rate(100.0, ref, 0.0, disc, 2.0, frequency=4)["price"]
    assert p == pytest.approx(100.0, abs=1e-4)


def test_inflation_linked_uplift_increases_price_vs_zero_inflation():
    base = inflation_linked_bond_pricer(100.0, 0.02, 0.02, 10.0, inflation_rate=0.0)["price"]
    infl = inflation_linked_bond_pricer(100.0, 0.02, 0.02, 10.0, inflation_rate=0.03)["price"]
    assert infl > base
    assert base == pytest.approx(100.0, abs=1e-4)


def test_callable_le_straight():
    r = callable_bond_pricer(100.0, 0.06, 0.05, 0.15, 10.0, call_price=101.0, frequency=2)
    assert r["price"] <= r["straight_price"] + 1e-6


def test_puttable_ge_straight():
    r = puttable_bond_pricer(100.0, 0.04, 0.05, 0.15, 10.0, put_price=99.0, frequency=2)
    assert r["price"] >= r["straight_price"] - 1e-6


def test_convertible_at_least_floor_and_conversion():
    r = convertible_bond_pricer(100.0, 0.03, 0.05, 5.0, conversion_ratio=2.0, stock_price=60.0)
    assert r["price"] >= r["bond_floor"]
    assert r["price"] >= r["conversion_value"]
    assert r["conversion_value"] == pytest.approx(120.0)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        bond_pricer_fixed_coupon(100.0, 0.05, 0.05, 0.0)
    with pytest.raises(ValueError):
        bond_pricer_floating_rate(100.0, [0.03], 0.0, [0.03, 0.03], 1.0)

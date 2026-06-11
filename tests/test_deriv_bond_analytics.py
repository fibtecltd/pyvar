"""tests/test_deriv_bond_analytics.py — numerical-correctness tests.

No mocking. Verifies duration signs/ordering, convexity >= 0, DV01 positivity,
YTM round-trips the pricing yield, and Z-spread is ~0 when bond is priced off
its own curve.
"""

import numpy as np
import pytest

from engine.deriv_bond_analytics import (
    asset_swap_spread,
    convexity,
    duration_macaulay,
    dv01_pvbp,
    effective_duration,
    modified_duration,
    oas_option_adjusted_spread,
    yield_to_call,
    yield_to_maturity,
    z_spread_calculator,
)
from engine.deriv_bonds import bond_pricer_fixed_coupon


def _bond_cf(face, coupon_rate, maturity, freq):
    n = int(maturity * freq)
    times = np.array([(i + 1) / freq for i in range(n)])
    cf = np.full(n, face * coupon_rate / freq)
    cf[-1] += face
    return cf, times


def test_macaulay_duration_positive_less_than_maturity():
    cf, t = _bond_cf(100.0, 0.05, 10.0, 2)
    d = duration_macaulay(cf, t, 0.05, 2)["macaulay_duration"]
    assert 0 < d < 10.0


def test_modified_less_than_macaulay():
    cf, t = _bond_cf(100.0, 0.05, 10.0, 2)
    mac = duration_macaulay(cf, t, 0.05, 2)["macaulay_duration"]
    mod = modified_duration(cf, t, 0.05, 2)["modified_duration"]
    assert mod < mac


def test_zero_coupon_macaulay_equals_maturity():
    cf = np.array([100.0])
    t = np.array([5.0])
    d = duration_macaulay(cf, t, 0.04, 1)["macaulay_duration"]
    assert d == pytest.approx(5.0, abs=1e-8)


def test_convexity_positive():
    cf, t = _bond_cf(100.0, 0.05, 10.0, 2)
    c = convexity(cf, t, 0.05, 2)["convexity"]
    assert c > 0


def test_dv01_positive():
    cf, t = _bond_cf(100.0, 0.05, 10.0, 2)
    d = dv01_pvbp(cf, t, 0.05, 2)["dv01"]
    assert d > 0


def test_effective_duration_callable_signs():
    eff = effective_duration(100.0, 98.0, 102.0, 0.01)["effective_duration"]
    assert eff == pytest.approx((102.0 - 98.0) / (2.0 * 100.0 * 0.01), abs=1e-9)


def test_ytm_roundtrip():
    cf, t = _bond_cf(100.0, 0.06, 8.0, 2)
    price = bond_pricer_fixed_coupon(100.0, 0.06, 0.045, 8.0, 2)["price"]
    ytm = yield_to_maturity(price, cf, t, 2)["ytm"]
    assert ytm == pytest.approx(0.045, abs=1e-6)


def test_ytc_reasonable():
    price = 102.0
    ytc = yield_to_call(price, 100.0, 0.06, 101.0, 5.0, 2)["ytc"]
    assert -0.1 < ytc < 0.2


def test_zspread_zero_when_priced_off_curve():
    cf, t = _bond_cf(100.0, 0.05, 5.0, 2)
    zero_rates = np.full(cf.size, 0.05)
    df = (1.0 + zero_rates / 2) ** (-(t * 2))
    price = float(np.sum(cf * df))
    z = z_spread_calculator(price, cf, t, zero_rates, 2)["z_spread"]
    assert z == pytest.approx(0.0, abs=1e-6)


def test_asset_swap_spread_runs():
    cf, t = _bond_cf(100.0, 0.05, 5.0, 2)
    swap_rates = np.full(cf.size, 0.04)
    r = asset_swap_spread(101.0, cf, t, swap_rates, 100.0, 2)
    assert "asset_swap_spread_bps" in r


def test_oas_reprices_callable():
    fair = oas_option_adjusted_spread(
        market_price=95.0, face_value=100.0, coupon_rate=0.05, short_rate=0.05,
        rate_vol=0.15, maturity=10.0, call_price=101.0, frequency=2,
    )
    assert -0.05 < fair["oas"] < 0.1


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        duration_macaulay(np.array([1.0, 2.0]), np.array([1.0]), 0.05, 2)
    with pytest.raises(ValueError):
        effective_duration(0.0, 98.0, 102.0, 0.01)

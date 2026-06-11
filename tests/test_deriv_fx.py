"""tests/test_deriv_fx.py — numerical-correctness tests for FX derivatives.

No mocking. Verifies covered-interest-parity forward, FX put-call parity, and
zero MtM when contracted forward equals fair forward.
"""

import math

import pytest

from engine.deriv_fx import fx_forward_pricer, fx_option_pricer_garman_kohlhagen


def test_fx_forward_covered_parity():
    f = fx_forward_pricer(1.25, 0.04, 0.02, 1.0)["forward_rate"]
    assert f == pytest.approx(1.25 * math.exp((0.04 - 0.02) * 1.0), abs=1e-8)


def test_fx_forward_zero_mtm_at_fair():
    fair = fx_forward_pricer(1.25, 0.04, 0.02, 1.0)["forward_rate"]
    v = fx_forward_pricer(1.25, 0.04, 0.02, 1.0, notional=1e6, contracted_forward=fair)["value"]
    # fair forward is reported rounded to 8dp; residual is pure rounding on 1e6 notional
    assert v == pytest.approx(0.0, abs=1e-2)


def test_gk_put_call_parity():
    c = fx_option_pricer_garman_kohlhagen(1.25, 1.20, 0.04, 0.02, 0.1, 1.0, "call")["price"]
    p = fx_option_pricer_garman_kohlhagen(1.25, 1.20, 0.04, 0.02, 0.1, 1.0, "put")["price"]
    parity = 1.25 * math.exp(-0.02) - 1.20 * math.exp(-0.04)
    assert (c - p) == pytest.approx(parity, abs=1e-6)


def test_gk_price_positive():
    c = fx_option_pricer_garman_kohlhagen(1.25, 1.25, 0.04, 0.02, 0.1, 1.0, "call")["price"]
    assert c > 0


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        fx_forward_pricer(0.0, 0.04, 0.02, 1.0)
    with pytest.raises(ValueError):
        fx_option_pricer_garman_kohlhagen(1.25, 1.2, 0.04, 0.02, 0.1, 1.0, "swap")

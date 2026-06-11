"""tests/test_deriv_rates.py — numerical-correctness tests for swaps/rate options.

No mocking. Verifies CDS par-spread zeroes value, caplet+floorlet parity, cap =
sum of caplets, swaption positivity & payer-receiver parity, SABR swaption uses
positive vol.
"""

import numpy as np
import pytest

from engine.deriv_rates import (
    cap_floor_pricer,
    caplet_floorlet_pricer_black,
    credit_default_swap_cds_pricer,
    cross_currency_swap_pricer,
    equity_swap_pricer,
    overnight_index_swap_ois,
    swaption_pricer_black,
    swaption_pricer_sabr,
    total_return_swap_trs,
)


def test_cds_par_spread_zeroes_value():
    par = credit_default_swap_cds_pricer(1e7, 0.0, 0.02, 0.4, 5.0, 0.03)["par_spread"]
    at_par = credit_default_swap_cds_pricer(1e7, par, 0.02, 0.4, 5.0, 0.03)["value"]
    assert at_par == pytest.approx(0.0, abs=1.0)


def test_cds_protection_leg_positive():
    r = credit_default_swap_cds_pricer(1e7, 0.01, 0.03, 0.4, 5.0, 0.03)
    assert r["protection_leg"] > 0


def test_ois_zero_at_par():
    v = overnight_index_swap_ois(1e6, 0.03, 0.03, 0.25, 0.99)["value"]
    assert v == pytest.approx(0.0, abs=1e-9)


def test_trs_and_equity_swap_direction():
    a = total_return_swap_trs(1e6, 0.05, 0.03, 1.0, 0.97, True)["value"]
    b = total_return_swap_trs(1e6, 0.05, 0.03, 1.0, 0.97, False)["value"]
    assert a == pytest.approx(-b)
    e = equity_swap_pricer(1e6, 0.05, 0.03, 1.0, 0.97, True)["value"]
    assert e == pytest.approx(a)


def test_caplet_floorlet_parity():
    cap = caplet_floorlet_pricer_black(1e6, 0.03, 0.03, 0.2, 1.0, 0.25, 0.97, "caplet")["price"]
    flo = caplet_floorlet_pricer_black(1e6, 0.03, 0.03, 0.2, 1.0, 0.25, 0.97, "floorlet")["price"]
    # at the money forward == strike => caplet == floorlet
    assert cap == pytest.approx(flo, abs=1e-6)


def test_cap_equals_sum_of_caplets():
    fwd = np.array([0.03, 0.032, 0.034])
    vols = np.array([0.2, 0.2, 0.2])
    exp = np.array([0.5, 1.0, 1.5])
    tau = np.array([0.5, 0.5, 0.5])
    df = np.array([0.985, 0.97, 0.955])
    res = cap_floor_pricer(1e6, fwd, 0.03, vols, exp, tau, df, "cap")
    assert res["price"] == pytest.approx(sum(res["caplet_prices"]), abs=1e-6)


def test_swaption_payer_positive_and_parity():
    payer = swaption_pricer_black(1e6, 0.03, 0.03, 0.25, 1.0, 4.0, "payer")["price"]
    receiver = swaption_pricer_black(1e6, 0.03, 0.03, 0.25, 1.0, 4.0, "receiver")["price"]
    assert payer > 0
    # ATM: payer == receiver
    assert payer == pytest.approx(receiver, abs=1e-6)


def test_sabr_swaption_positive():
    r = swaption_pricer_sabr(1e6, 0.03, 0.035, 1.0, 4.0, alpha=0.02, beta=0.5, rho=-0.2, nu=0.4, option_type="payer")
    assert r["price"] >= 0
    assert r["sabr_vol"] > 0


def test_xccy_swap_runs():
    df_dom = np.array([0.97, 0.94, 0.90])
    df_for = np.array([0.98, 0.96, 0.93])
    tau = np.array([1.0, 1.0, 1.0])
    r = cross_currency_swap_pricer(1e6, 1.2e6, 0.03, 0.025, df_dom, df_for, tau, 0.83, True)
    assert "value" in r


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        caplet_floorlet_pricer_black(1e6, 0.03, 0.03, 0.2, 1.0, 0.25, 0.97, "swap")
    with pytest.raises(ValueError):
        credit_default_swap_cds_pricer(1e7, 0.01, 0.02, 1.5, 5.0, 0.03)

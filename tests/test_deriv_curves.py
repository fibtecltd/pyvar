"""tests/test_deriv_curves.py — numerical-correctness tests for curves.

No mocking. Verifies NS/NSS recover data, bootstrap→reprice par bonds, OIS curve
DFs in (0,1] and decreasing, swap-rate consistency, FRA zero at par, IRS par
rate zeroes the swap value.
"""

import numpy as np
import pytest

from engine.deriv_curves import (
    bootstrap_yield_curve,
    forward_rate_agreement_fra,
    interest_rate_swap_irs_pricer,
    nelson_siegel_curve_fit,
    nelson_siegel_svensson_curve,
    ois_curve_sonia_sofr,
    swap_rate_curve,
)


def test_nelson_siegel_recovers_synthetic():
    t = np.array([0.25, 0.5, 1, 2, 3, 5, 7, 10])
    # build yields from known NS params
    from engine.deriv_curves import _ns_yield

    y = _ns_yield(t, 0.04, -0.02, 0.01, 1.5)
    fit = nelson_siegel_curve_fit(t, y)
    assert fit["rmse"] < 1e-4
    assert fit["beta0"] == pytest.approx(0.04, abs=1e-3)


def test_nss_fits_better_than_floor():
    t = np.array([0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30])
    y = np.array([0.02, 0.022, 0.025, 0.028, 0.03, 0.032, 0.033, 0.034, 0.035, 0.035])
    fit = nelson_siegel_svensson_curve(t, y)
    assert fit["rmse"] < 0.01


def test_bootstrap_reprices_par():
    maturities = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    par_rates = np.array([0.02, 0.025, 0.03, 0.032, 0.035])
    res = bootstrap_yield_curve(par_rates, maturities, frequency=1)
    dfs = np.array(res["discount_factors"])
    # reprice the 5y par bond: coupons + redemption should equal par (1.0)
    coupon = par_rates[-1]
    pv = coupon * np.sum(dfs) + 1.0 * dfs[-1]
    assert pv == pytest.approx(1.0, abs=1e-9)
    assert np.all(np.diff(dfs) < 0)  # DFs decreasing


def test_ois_curve_df_bounds_and_monotone():
    maturities = np.array([1.0, 2.0, 3.0, 5.0])
    ois = np.array([0.03, 0.032, 0.034, 0.036])
    res = ois_curve_sonia_sofr(ois, maturities, frequency=1)
    dfs = np.array(res["discount_factors"])
    assert np.all((dfs > 0) & (dfs <= 1.0))
    assert np.all(np.diff(dfs) < 0)


def test_swap_rate_curve_flat_curve():
    # flat 4% continuous => DF = exp(-0.04 t)
    t = np.array([1.0, 2.0, 3.0])
    df = np.exp(-0.04 * t)
    res = swap_rate_curve(df, t, frequency=1)
    assert all(r > 0 for r in res["swap_rates"])


def test_fra_zero_at_par():
    v = forward_rate_agreement_fra(1e6, 0.03, 0.03, 0.5, 0.75, 0.98)["value"]
    assert v == pytest.approx(0.0, abs=1e-9)


def test_fra_positive_when_forward_above_fixed():
    v = forward_rate_agreement_fra(1e6, 0.03, 0.04, 0.5, 0.75, 0.98)["value"]
    assert v > 0


def test_irs_par_rate_zeroes_value():
    fwd = np.array([0.03, 0.032, 0.034, 0.036])
    df = np.array([0.97, 0.94, 0.90, 0.86])
    tau = np.array([1.0, 1.0, 1.0, 1.0])
    par = interest_rate_swap_irs_pricer(1e6, 0.0, fwd, df, tau, True)["par_rate"]
    at_par = interest_rate_swap_irs_pricer(1e6, par, fwd, df, tau, True)["value"]
    assert at_par == pytest.approx(0.0, abs=1e-3)


def test_irs_payer_receiver_opposite():
    fwd = np.array([0.03, 0.032])
    df = np.array([0.97, 0.94])
    tau = np.array([1.0, 1.0])
    payer = interest_rate_swap_irs_pricer(1e6, 0.04, fwd, df, tau, True)["value"]
    receiver = interest_rate_swap_irs_pricer(1e6, 0.04, fwd, df, tau, False)["value"]
    assert payer == pytest.approx(-receiver, abs=1e-6)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        nelson_siegel_curve_fit(np.array([1.0, 2.0]), np.array([0.02, 0.03]))
    with pytest.raises(ValueError):
        forward_rate_agreement_fra(1e6, 0.03, 0.03, 0.75, 0.5, 0.98)

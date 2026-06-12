"""tests/test_credit_cds.py — numerical-correctness tests for CDS/credit-spread.

No mocking. Verifies: survival is decreasing in tenor, bootstrap round-trips via
the credit triangle, CDS PV is zero at the par spread, spread-to-PD monotone in
spread and bounded, CDS VaR scales with sqrt-time and confidence.
"""

import numpy as np
import pytest

from engine.credit_cds import (
    cds_pricing_isda_standard,
    cds_spread_to_pd_conversion,
    credit_default_swap_var,
    credit_spread_curve_bootstrap,
)


def test_bootstrap_survival_decreasing():
    t = np.array([1.0, 3.0, 5.0])
    s = np.array([0.01, 0.012, 0.015])
    r = credit_spread_curve_bootstrap(t, s)
    surv = r["survival"]
    assert surv[0] > surv[1] > surv[2]
    assert all(0.0 < v <= 1.0 for v in surv)


def test_bootstrap_credit_triangle_value():
    # Single tenor: survival = exp(-spread/LGD * t).
    r = credit_spread_curve_bootstrap(np.array([5.0]), np.array([0.01]), recovery_rate=0.4)
    expected = np.exp(-(0.01 / 0.6) * 5.0)
    assert abs(r["survival"][0] - expected) < 1e-9


def test_cds_pv_zero_at_par_spread():
    t = np.array([0.5, 1.0, 1.5, 2.0])
    acc = np.array([0.5, 0.5, 0.5, 0.5])
    df = np.exp(-0.02 * t)
    hazard = 0.025
    priced = cds_pricing_isda_standard(t, acc, df, hazard, contract_spread=0.0, notional=1e7)
    par = priced["par_spread"]
    at_par = cds_pricing_isda_standard(t, acc, df, hazard, contract_spread=par, notional=1e7)
    assert abs(at_par["pv"]) < 1e-2  # PV ~ 0 at the par spread


def test_cds_pv_positive_when_spread_below_par():
    t = np.array([1.0, 2.0])
    acc = np.array([1.0, 1.0])
    df = np.array([0.98, 0.96])
    priced = cds_pricing_isda_standard(t, acc, df, 0.03, contract_spread=0.0, notional=1.0)
    # Buyer pays zero premium but gets protection -> PV strongly positive.
    assert priced["pv"] > 0.0


def test_spread_to_pd_monotone_and_bounded():
    low = cds_spread_to_pd_conversion(0.005, 5.0)
    high = cds_spread_to_pd_conversion(0.03, 5.0)
    assert 0.0 < low["pd"] < high["pd"] < 1.0
    # Credit-triangle closed form.
    expected = 1.0 - np.exp(-(0.03 / 0.6) * 5.0)
    assert abs(high["pd"] - expected) < 1e-9


def test_cds_var_sqrt_time_and_confidence_scaling():
    base = credit_default_swap_var(1e7, 4.0, 0.0005, 0.99, horizon_days=1)
    ten_day = credit_default_swap_var(1e7, 4.0, 0.0005, 0.99, horizon_days=10)
    assert abs(ten_day["var"] - base["var"] * np.sqrt(10)) < 1e-3
    higher = credit_default_swap_var(1e7, 4.0, 0.0005, 0.999, horizon_days=1)
    assert higher["var"] > base["var"]


def test_cds_var_position_sign():
    long_p = credit_default_swap_var(1e7, 4.0, 0.0005, position="long_protection")
    short_p = credit_default_swap_var(1e7, 4.0, 0.0005, position="short_protection")
    assert long_p["var"] == short_p["var"]  # magnitude identical
    assert long_p["pnl_sensitivity"] == -short_p["pnl_sensitivity"]


def test_cds_var_rejects_bad_position():
    with pytest.raises(ValueError):
        credit_default_swap_var(1e7, 4.0, 0.0005, position="naked")

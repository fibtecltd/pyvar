"""tests/test_credit_capital.py — numerical-correctness tests for Basel capital.

Verifies the IRB risk-weight function against published Basel properties:
correlation bounds [0.12, 0.24], maturity adjustment = 1 at M=2.5, monotone
RWA in PD/LGD, SME relief reduces correlation, and linear EAD scaling.
"""

import numpy as np
import pytest
from scipy import stats

from engine.credit_capital import (
    basel_standardised_approach_rwa,
    irb_advanced_approach_capital,
    irb_foundation_approach_capital,
    maturity_adjustment_basel_irb,
    sme_correlation_factor_basel,
)


def test_irb_correlation_within_basel_bounds():
    # Correlation must lie in [0.12, 0.24] for all PD.
    for pd in (0.0003, 0.01, 0.05, 0.2, 0.99):
        r = irb_advanced_approach_capital(pd, 0.45, 1e6)["correlation"]
        assert 0.12 - 1e-9 <= r <= 0.24 + 1e-9


def test_maturity_adjustment_at_2p5_drops_linear_term():
    # At M=2.5 the (M-2.5) term vanishes so MA = 1/(1-1.5b) >= 1.
    r = maturity_adjustment_basel_irb(pd=0.01, maturity=2.5)
    b = r["b"]
    assert abs(r["maturity_adjustment"] - 1.0 / (1.0 - 1.5 * b)) < 1e-9
    assert r["maturity_adjustment"] >= 1.0


def test_maturity_adjustment_monotone_increasing():
    short = maturity_adjustment_basel_irb(0.01, 1.0)["maturity_adjustment"]
    mid = maturity_adjustment_basel_irb(0.01, 2.5)["maturity_adjustment"]
    long = maturity_adjustment_basel_irb(0.01, 5.0)["maturity_adjustment"]
    # MA strictly increases with maturity.
    assert short < mid < long


def test_irb_rwa_monotone_in_pd():
    low = irb_advanced_approach_capital(0.01, 0.45, 1e6, maturity=2.5)["rwa"]
    high = irb_advanced_approach_capital(0.05, 0.45, 1e6, maturity=2.5)["rwa"]
    assert high > low


def test_irb_rwa_linear_in_ead():
    a = irb_advanced_approach_capital(0.02, 0.45, 1e6)["rwa"]
    b = irb_advanced_approach_capital(0.02, 0.45, 2e6)["rwa"]
    assert abs(b - 2.0 * a) < 1e-3


def test_irb_closed_form_capital():
    # Reproduce K directly from the Basel formula at a known point.
    pd, lgd, m = 0.02, 0.45, 2.5
    r = irb_advanced_approach_capital(pd, lgd, 1.0, maturity=m)
    corr = r["correlation"]
    cond = (stats.norm.ppf(pd) + np.sqrt(corr) * stats.norm.ppf(0.999)) / np.sqrt(1 - corr)
    k_expected = (lgd * stats.norm.cdf(cond) - pd * lgd) * r["maturity_adjustment"]
    assert abs(r["k"] - k_expected) < 1e-9


def test_foundation_uses_supervisory_lgd():
    senior = irb_foundation_approach_capital(0.02, 1e6, seniority="senior_unsecured")
    sub = irb_foundation_approach_capital(0.02, 1e6, seniority="subordinated")
    assert senior["lgd_used"] == 0.45
    assert sub["lgd_used"] == 0.75
    assert sub["rwa"] > senior["rwa"]


def test_standardised_rwa_and_crm():
    r = basel_standardised_approach_rwa(ead=1e6, risk_weight=1.0, credit_risk_mitigation=2e5)
    assert abs(r["rwa"] - 8e5) < 1e-6
    assert abs(r["capital_required"] - 8e5 * 0.08) < 1e-6


def test_standardised_zero_weight_sovereign():
    r = basel_standardised_approach_rwa(1e6, 0.0)
    assert r["rwa"] == 0.0


def test_sme_relief_reduces_correlation():
    pd = 0.02
    sme = sme_correlation_factor_basel(pd, annual_sales_millions=5.0)
    large = sme_correlation_factor_basel(pd, annual_sales_millions=50.0)
    assert sme["correlation_sme"] < sme["correlation_corporate"]
    # Largest SME (50m sales) gets the smallest size relief.
    assert large["size_adjustment"] < sme["size_adjustment"] + 1e-12
    assert abs(large["size_adjustment"]) < 1e-9


def test_irb_rejects_bad_pd():
    with pytest.raises(ValueError):
        irb_advanced_approach_capital(0.0, 0.45, 1e6)

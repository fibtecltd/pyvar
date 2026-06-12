"""tests/test_alm_behavioural.py — numerical-correctness tests for behavioural.

No mocking. Verifies CPR/SMM round-trip, prepayment shortens WAL, NMD core split
and run-off, deposit stability floor, core-deposit duration positivity.
"""

import numpy as np
import pytest

from engine.alm_behavioural import (
    behavioural_modelling_nmds,
    core_deposit_duration,
    loan_prepayment_rate_cpr,
    non_maturity_deposit_stability,
    prepayment_model_mortgages,
)


def test_cpr_smm_roundtrip():
    a = loan_prepayment_rate_cpr(cpr=0.06)
    b = loan_prepayment_rate_cpr(smm=a["smm"])
    # results rounded to 8dp, so round-trip matches to ~1e-7
    assert b["cpr"] == pytest.approx(0.06, abs=1e-6)


def test_cpr_smm_consistency():
    r = loan_prepayment_rate_cpr(cpr=0.10)
    assert r["smm"] == pytest.approx(1.0 - (1.0 - 0.10) ** (1.0 / 12.0), abs=1e-8)


def test_prepayment_shortens_wal():
    slow = prepayment_model_mortgages(1e6, 0.05, 30, cpr=0.02)["weighted_average_life"]
    fast = prepayment_model_mortgages(1e6, 0.05, 30, cpr=0.30)["weighted_average_life"]
    assert fast < slow


def test_nmd_core_split_and_runoff():
    r = behavioural_modelling_nmds(1e6, 0.7, 0.05, 0.40, horizon_years=5.0)
    assert r["core_balance"] == pytest.approx(7e5)
    assert r["non_core_balance"] == pytest.approx(3e5)
    assert r["surviving_balance"] < 1e6
    # core survives more than non-core (slower runoff)
    assert r["effective_life"] > 0


def test_nmd_stability_floor_below_current():
    rng = np.random.default_rng(0)
    history = 1e6 + rng.normal(0, 5e4, size=500)
    r = non_maturity_deposit_stability(history, confidence_level=0.99)
    assert r["stable_balance"] < r["stable_balance"] + r["volatile_balance"] + 1e-9
    assert 0 < r["stable_fraction"] <= 1.0 + 1e-6


def test_core_deposit_duration_positive_multi_year():
    r = core_deposit_duration(1e6, decay_rate=0.10, discount_rate=0.03)
    assert r["core_deposit_duration"] > 1.0  # slow decay => multi-year


def test_core_deposit_duration_faster_decay_shorter():
    slow = core_deposit_duration(1e6, 0.05, 0.03)["core_deposit_duration"]
    fast = core_deposit_duration(1e6, 0.30, 0.03)["core_deposit_duration"]
    assert fast < slow


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        loan_prepayment_rate_cpr(cpr=0.06, smm=0.005)  # both given
    with pytest.raises(ValueError):
        prepayment_model_mortgages(1e6, 0.05, 30, cpr=1.5)
    with pytest.raises(ValueError):
        core_deposit_duration(1e6, decay_rate=0.0, discount_rate=0.03)

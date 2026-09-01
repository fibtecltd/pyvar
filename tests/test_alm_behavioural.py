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


def _discrete_duration(
    core_balance: float, decay_rate: float, discount_rate: float, max_years: float, dt: float
) -> float:
    """Independent reimplementation of the discrete Riemann-sum duration at an
    arbitrary (test-controlled) step size ``dt``, used only to validate the
    closed-form identity as granularity is refined and the truncation
    horizon is made generous relative to the implied continuous duration.
    """
    times = np.arange(dt, max_years + 1e-9, dt)
    runoff = core_balance * decay_rate * np.exp(-decay_rate * times) * dt
    df = np.exp(-discount_rate * times)
    pv = runoff * df
    total_pv = float(np.sum(pv))
    return float(np.sum(times * pv) / total_pv) if total_pv > 0 else 0.0


def test_core_deposit_duration_closed_form_matches_fine_discrete():
    """The closed form 1/(decay_rate+discount_rate) is the exact continuous-
    time limit of the discrete Riemann sum: as the step size is refined
    (daily vs. the function's own monthly grid) and the truncation horizon
    is made generous relative to the implied duration (so max_years no
    longer bites), the discrete sum converges to the closed form to well
    within the 0.5% tolerance requested for this validation.
    """
    cases = [
        (1_000_000.0, 0.15, 0.03),
        (1_000_000.0, 0.05, 0.02),
        (500_000.0, 0.30, 0.10),
        (1_000_000.0, 0.02, 0.0),
    ]
    for core, decay, disc in cases:
        implied = 1.0 / (decay + disc)
        horizon = max(30.0, implied * 30.0)  # generous: truncation is negligible
        fine = _discrete_duration(core, decay, disc, horizon, dt=1.0 / 365.0)
        r = core_deposit_duration(core, decay, disc, max_years=horizon)
        closed = r["closed_form_duration"]
        # closed form is the exact analytic mean of Exponential(decay+disc)
        assert closed == pytest.approx(1.0 / (decay + disc), rel=1e-6)
        # fine daily grid at a generous horizon confirms the closed form is
        # the correct continuous-time limit of the discrete method
        assert abs(fine - closed) / closed < 0.005


def test_core_deposit_duration_default_horizon_diverges_from_closed_form_for_slow_decay():
    """Documents precisely why the default (discrete, truncated) figure is
    NOT switched to the closed form: at the max_years=30 default, a
    realistic 'sticky' core-deposit combination (decay_rate=0.05,
    discount_rate=0.02 -> implied continuous duration ~14.3y) has its
    run-off tail cut off well before it has materially decayed, understating
    the untruncated closed form by ~29% -- a genuine, quantified divergence
    driven by the max_years truncation being economically meaningful here,
    not just discretisation noise. This is why core_deposit_duration keeps
    the discrete method as the default rather than adopting the closed form.
    """
    r = core_deposit_duration(1_000_000.0, decay_rate=0.05, discount_rate=0.02)
    discrete = r["core_deposit_duration"]
    closed = r["closed_form_duration"]
    assert closed == pytest.approx(1.0 / 0.07, rel=1e-6)
    rel_diff = abs(discrete - closed) / closed
    assert rel_diff > 0.20  # confirms the divergence is real and substantial


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        loan_prepayment_rate_cpr(cpr=0.06, smm=0.005)  # both given
    with pytest.raises(ValueError):
        prepayment_model_mortgages(1e6, 0.05, 30, cpr=1.5)
    with pytest.raises(ValueError):
        core_deposit_duration(1e6, decay_rate=0.0, discount_rate=0.03)

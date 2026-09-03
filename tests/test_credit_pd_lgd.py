"""tests/test_credit_pd_lgd.py — numerical-correctness tests for PD/LGD/EAD/EL/UL.

No mocking of engine functions (CLAUDE.md §5 RULE 1). Tests assert risk
properties: bounds in [0, 1] for PD/LGD, EL = PD*LGD*EAD closed form, monotone
behaviour, determinism and Basel floor enforcement.
"""

import numpy as np
import pytest

from engine.credit_pd_lgd import (
    downturn_lgd_adjustment,
    expected_loss_el_computation,
    exposure_at_default_ead_calculator,
    loss_given_default_lgd_model,
    probability_of_default_pd_estimation,
    recovery_rate_estimation,
    unexpected_loss_ul_computation,
)


def test_pd_estimation_pooled_frequency_and_floor():
    r = probability_of_default_pd_estimation(
        np.array([2.0, 5.0]), np.array([100.0, 100.0]), floor=0.0003
    )
    # 7 defaults / 200 obligors = 0.035
    assert abs(r["pd_raw"] - 0.035) < 1e-12
    assert r["pd_pooled"] >= r["pd_raw"]
    assert 0.0 <= r["pd_pooled"] <= 1.0


def test_pd_floor_applies_when_no_defaults():
    r = probability_of_default_pd_estimation(np.array([0.0]), np.array([1000.0]))
    assert r["pd_raw"] == 0.0
    assert r["pd_pooled"] == 0.0003


def test_pd_mismatch_raises():
    with pytest.raises(ValueError):
        probability_of_default_pd_estimation(np.array([1.0]), np.array([1.0, 2.0]))


def test_lgd_one_minus_recovery():
    # Recover 60 on 100 exposure -> LGD 0.40
    r = loss_given_default_lgd_model(np.array([60.0]), np.array([100.0]))
    assert abs(r["lgd"] - 0.40) < 1e-12
    assert abs(r["recovery_rate"] - 0.60) < 1e-12


def test_lgd_workout_costs_increase_lgd():
    base = loss_given_default_lgd_model(np.array([60.0]), np.array([100.0]))
    withcost = loss_given_default_lgd_model(
        np.array([60.0]), np.array([100.0]), workout_cost_rate=0.10
    )
    assert withcost["lgd"] > base["lgd"]
    assert 0.0 <= withcost["lgd"] <= 1.0


def test_ead_ccf_formula():
    r = exposure_at_default_ead_calculator(
        drawn=100.0, undrawn=200.0, credit_conversion_factor=0.75
    )
    assert abs(r["ead"] - 250.0) < 1e-12


def test_ead_zero_ccf_equals_drawn():
    r = exposure_at_default_ead_calculator(100.0, 500.0, 0.0)
    assert r["ead"] == 100.0


def test_el_closed_form():
    r = expected_loss_el_computation(pd=0.02, lgd=0.45, ead=1_000_000.0)
    assert abs(r["el"] - 0.02 * 0.45 * 1_000_000.0) < 1e-6
    assert abs(r["el_rate"] - 0.009) < 1e-12


def test_el_rejects_out_of_range_pd():
    with pytest.raises(ValueError):
        expected_loss_el_computation(pd=1.5, lgd=0.4, ead=100.0)


def test_ul_standalone_formula_and_ordering():
    pd = np.array([0.05])
    lgd = np.array([0.5])
    ead = np.array([1000.0])
    r = unexpected_loss_ul_computation(pd, lgd, ead)
    expected = 1000.0 * 0.5 * np.sqrt(0.05 * 0.95)
    assert abs(r["ul"][0] - expected) < 1e-6
    # Perfectly-correlated sum >= independent RSS.
    assert r["ul_sum"] >= r["ul_independent"] - 1e-9


def test_ul_independent_lt_sum_for_multiple():
    pd = np.array([0.05, 0.05])
    lgd = np.array([0.5, 0.5])
    ead = np.array([1000.0, 1000.0])
    r = unexpected_loss_ul_computation(pd, lgd, ead)
    assert r["ul_independent"] < r["ul_sum"]


def test_recovery_rate_discounting_reduces_rate():
    undisc = recovery_rate_estimation(np.array([50.0]), np.array([100.0]))
    disc = recovery_rate_estimation(
        np.array([50.0]), np.array([100.0]), discount_factors=np.array([0.9])
    )
    assert disc["recovery_rate"] < undisc["recovery_rate"]
    assert abs(undisc["recovery_rate"] - 0.5) < 1e-12
    assert abs(undisc["lgd"] - (1.0 - undisc["recovery_rate"])) < 1e-12


def test_downturn_lgd_never_below_long_run():
    r = downturn_lgd_adjustment(lgd_long_run=0.40, downturn_multiplier=1.25)
    assert r["lgd_downturn"] >= 0.40
    assert abs(r["lgd_downturn"] - 0.50) < 1e-12


def test_downturn_lgd_floor_and_cap():
    r = downturn_lgd_adjustment(lgd_long_run=0.95, downturn_multiplier=2.0, floor=0.05)
    assert r["lgd_downturn"] <= 1.0
    with pytest.raises(ValueError):
        downturn_lgd_adjustment(0.4, downturn_multiplier=0.8)


# ── method="additive" (caveat-triage batch 1: EBA/GL/2019/03 fallback) ──────
# The default ("multiplicative") must stay byte-identical to before this
# opt-in was added; "additive" is the fallback formula the function's own
# docstring already documented but never actually implemented.


def test_downturn_lgd_default_method_omits_method_key():
    r = downturn_lgd_adjustment(lgd_long_run=0.40, downturn_multiplier=1.25)
    assert "method" not in r
    assert set(r) == {"lgd_downturn", "lgd_long_run", "multiplier", "floor"}


def test_downturn_lgd_additive_matches_documented_formula():
    lgd_lr, mult = 0.40, 1.25
    r = downturn_lgd_adjustment(lgd_long_run=lgd_lr, downturn_multiplier=mult, method="additive")
    expected = lgd_lr + max(0.0, mult - 1.0) * (1.0 - lgd_lr) * 0.5
    assert r["method"] == "additive"
    assert abs(r["lgd_downturn"] - round(expected, 10)) < 1e-9


def test_downturn_lgd_additive_never_below_long_run_and_capped_at_one():
    below = downturn_lgd_adjustment(lgd_long_run=0.90, downturn_multiplier=1.0, method="additive")
    assert below["lgd_downturn"] >= 0.90  # multiplier=1 -> no add-on, floors at long-run
    capped = downturn_lgd_adjustment(lgd_long_run=0.95, downturn_multiplier=5.0, method="additive")
    assert capped["lgd_downturn"] <= 1.0


def test_downturn_lgd_additive_and_multiplicative_diverge():
    # Same inputs, different method -> different result (proves "additive"
    # isn't silently falling back to the multiplicative path).
    mult = downturn_lgd_adjustment(0.40, downturn_multiplier=1.5)["lgd_downturn"]
    add = downturn_lgd_adjustment(0.40, downturn_multiplier=1.5, method="additive")["lgd_downturn"]
    assert mult != add


def test_downturn_lgd_invalid_method_raises():
    with pytest.raises(ValueError):
        downturn_lgd_adjustment(0.4, downturn_multiplier=1.2, method="bogus")

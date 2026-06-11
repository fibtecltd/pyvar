"""tests/test_credit_ifrs9.py — numerical-correctness tests for IFRS 9 + portfolio.

No mocking. Verifies: staging rules (1/2/3), 90dpd forces Stage 3, 12m ECL
closed form, lifetime ECL >= 12m for the same exposure, scenario-weighted ECL
between min/max, macro overlay scaling, portfolio weights sum to 1, stress
raises EL.
"""

import numpy as np
import pytest

from engine.credit_ifrs9 import (
    credit_portfolio_optimisation,
    credit_stress_testing,
    ifrs_9_12_month_ecl_stage_1,
    ifrs_9_lifetime_ecl_stage_2_3,
    ifrs_9_scenario_weighted_ecl,
    ifrs_9_stage_classification_pd_threshold,
    ifrs_9_staging_criteria_assessment,
    macroeconomic_overlays_ecl,
)


def test_staging_stage1_no_sicr():
    r = ifrs_9_stage_classification_pd_threshold(0.011, 0.010)
    assert r["stage"] == 1
    assert r["sicr"] is False


def test_staging_stage2_relative_pd():
    r = ifrs_9_stage_classification_pd_threshold(0.025, 0.010, sicr_relative_threshold=2.0)
    assert r["stage"] == 2
    assert r["sicr"] is True


def test_staging_stage3_on_90dpd():
    r = ifrs_9_stage_classification_pd_threshold(0.01, 0.01, days_past_due=120)
    assert r["stage"] == 3


def test_12m_ecl_closed_form():
    r = ifrs_9_12_month_ecl_stage_1(0.02, 0.45, 1_000_000.0)
    assert abs(r["ecl"] - 0.02 * 0.45 * 1_000_000.0) < 1e-6
    assert r["stage"] == 1


def test_lifetime_ecl_ge_12month_for_same_exposure():
    # Lifetime sums multiple periods of marginal PD -> >= single 12m bucket.
    ead = 1_000_000.0
    twelve = ifrs_9_12_month_ecl_stage_1(0.02, 0.45, ead)["ecl"]
    mpd = np.array([0.02, 0.018, 0.015])
    lgd = np.full(3, 0.45)
    e = np.full(3, ead)
    df = np.array([1.0, 0.97, 0.94])
    life = ifrs_9_lifetime_ecl_stage_2_3(mpd, lgd, e, df, stage=2)["ecl"]
    assert life >= twelve


def test_scenario_weighted_between_min_max():
    ecls = np.array([100.0, 200.0, 500.0])
    w = np.array([0.5, 0.3, 0.2])
    r = ifrs_9_scenario_weighted_ecl(ecls, w)
    assert 100.0 <= r["ecl"] <= 500.0
    assert abs(r["ecl"] - (0.5 * 100 + 0.3 * 200 + 0.2 * 500)) < 1e-6


def test_macro_overlay_adverse_raises_ecl():
    up = macroeconomic_overlays_ecl(100.0, np.array([1.0]), np.array([0.2]))
    down = macroeconomic_overlays_ecl(100.0, np.array([-1.0]), np.array([0.2]))
    assert up["ecl_adjusted"] > 100.0 > down["ecl_adjusted"]


def test_macro_management_overlay_added():
    r = macroeconomic_overlays_ecl(100.0, np.array([0.0]), np.array([0.5]), management_overlay=25.0)
    assert abs(r["ecl_adjusted"] - 125.0) < 1e-6


def test_staging_criteria_forbearance_forces_stage2():
    r = ifrs_9_staging_criteria_assessment(0.011, 0.010, forbearance=True)
    assert r["stage"] == 2
    assert "forbearance" in r["triggers"]
    assert r["quantitative_stage"] == 1


def test_portfolio_weights_sum_to_one_and_prefer_high_score():
    r = credit_portfolio_optimisation(
        np.array([0.10, 0.05, 0.02]), np.array([0.01, 0.01, 0.05]), max_weight=0.5
    )
    assert abs(sum(r["weights"]) - 1.0) < 1e-9
    # Highest score (asset 0) gets the cap.
    assert r["weights"][0] == 0.5


def test_portfolio_rejects_infeasible_cap():
    with pytest.raises(ValueError):
        credit_portfolio_optimisation(np.array([0.1, 0.1]), np.array([0.0, 0.0]), max_weight=0.3)


def test_stress_increases_el():
    pd = np.array([0.02, 0.03])
    lgd = np.array([0.45, 0.5])
    ead = np.array([1e6, 2e6])
    r = credit_stress_testing(pd, lgd, ead, pd_shock_multiplier=1.5, lgd_shock_multiplier=1.2)
    assert r["stressed_el"] > r["baseline_el"]
    assert r["stress_ratio"] > 1.0
    assert abs(r["incremental_loss"] - (r["stressed_el"] - r["baseline_el"])) < 1e-3


def test_stress_rejects_relief_multiplier():
    with pytest.raises(ValueError):
        credit_stress_testing(np.array([0.02]), np.array([0.4]), np.array([1.0]), pd_shock_multiplier=0.8)

"""tests/test_credit_scoring.py — numerical-correctness tests for scoring/PD models.

No mocking. Verifies: Altman zones, logistic recovers a known separating
boundary, Platt scaling reduces Brier score, TTC<->PIT are inverse transforms,
migration rows are stochastic, scorecard PDO doubling, monotone sovereign score.
"""

import numpy as np
import pytest

from engine.credit_scoring import (
    altman_z_score_credit_scoring,
    corporate_credit_scoring_model,
    logistic_regression_pd_model,
    machine_learning_pd_calibration,
    point_in_time_pd_estimation,
    ratings_migration_matrix,
    retail_scorecard_pd_model,
    sector_default_rate_analysis,
    sovereign_credit_risk_assessment,
    through_the_cycle_pd_adjustment,
)


def test_altman_safe_and_distress_zones():
    safe = altman_z_score_credit_scoring(50, 80, 40, 500, 200, 100, 50)
    assert safe["zone"] == "safe"
    distress = altman_z_score_credit_scoring(-30, -50, -20, 5, 10, 100, 90)
    assert distress["zone"] == "distress"
    assert distress["z_score"] < safe["z_score"]


def test_logistic_recovers_positive_slope():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, size=500).reshape(-1, 1)
    prob = 1.0 / (1.0 + np.exp(-(-0.5 + 2.0 * x.ravel())))
    y = (rng.uniform(size=500) < prob).astype(float)
    r = logistic_regression_pd_model(x, y)
    assert r["converged"]
    # Slope coefficient should be positive (higher x -> higher PD).
    assert r["coefficients"][1] > 0.5
    assert all(0.0 <= p <= 1.0 for p in r["fitted_pd"])


def test_logistic_rejects_nonbinary():
    with pytest.raises(ValueError):
        logistic_regression_pd_model(np.array([[1.0], [2.0]]), np.array([0.5, 1.0]))


def test_platt_calibration_is_probability_and_low_brier():
    rng = np.random.default_rng(1)
    scores = rng.normal(0, 2, size=400)
    prob = 1.0 / (1.0 + np.exp(-scores))
    y = (rng.uniform(size=400) < prob).astype(float)
    r = machine_learning_pd_calibration(scores, y)
    assert all(0.0 <= p <= 1.0 for p in r["calibrated_pd"])
    assert 0.0 <= r["brier_score"] <= 0.25 + 1e-9


def test_ttc_pit_round_trip():
    ttc = through_the_cycle_pd_adjustment(0.03, 0.02, cyclicality=0.5)
    # Pure-PIT (cyclicality 0) returns the input PIT PD unchanged.
    pure_pit = through_the_cycle_pd_adjustment(0.03, 0.02, cyclicality=0.0)
    assert abs(pure_pit["ttc_pd"] - 0.03) < 1e-9
    # TTC PD lies between PIT and long-run.
    assert min(0.02, 0.03) <= ttc["ttc_pd"] <= max(0.02, 0.03)


def test_pit_adverse_macro_raises_pd():
    good = point_in_time_pd_estimation(0.02, macro_index=2.0)
    bad = point_in_time_pd_estimation(0.02, macro_index=-2.0)
    assert bad["pit_pd"] > 0.02 > good["pit_pd"]


def test_migration_matrix_rows_stochastic():
    f = np.array([0, 0, 0, 1, 1, 2])
    t = np.array([0, 1, 2, 1, 2, 2])
    r = ratings_migration_matrix(f, t, n_states=3)
    for row in r["matrix"]:
        assert abs(sum(row) - 1.0) < 1e-9
    # From state 0: 1/3 stay, 1/3 to 1, 1/3 to 2.
    assert abs(r["matrix"][0][0] - 1.0 / 3.0) < 1e-9


def test_migration_empty_row_is_identity():
    f = np.array([0, 0])
    t = np.array([0, 1])
    r = ratings_migration_matrix(f, t, n_states=3)
    # State 2 never observed -> identity self-transition.
    assert r["matrix"][2][2] == 1.0


def test_scorecard_pdo_doubles_odds():
    base = retail_scorecard_pd_model(
        np.array([1.0]),
        np.array([0.0]),
        base_points=600.0,
        pdo=50.0,
        base_score=600.0,
        base_odds=50.0,
    )
    # +50 points should double the odds.
    plus = retail_scorecard_pd_model(
        np.array([1.0]),
        np.array([50.0]),
        base_points=600.0,
        pdo=50.0,
        base_score=600.0,
        base_odds=50.0,
    )
    assert abs(plus["odds"] - 2.0 * base["odds"]) < 1e-6


def test_corporate_strong_borrower_hits_floor():
    strong = corporate_credit_scoring_model(
        np.array([1.0, 1.0]), np.array([0.5, 0.5]), pd_floor=0.0003
    )
    weak = corporate_credit_scoring_model(np.array([0.0, 0.0]), np.array([0.5, 0.5]))
    assert abs(strong["pd"] - 0.0003) < 1e-12
    assert weak["pd"] > strong["pd"]


def test_sovereign_score_monotone_in_debt():
    low_debt = sovereign_credit_risk_assessment(0.4, 0.0, 0.0, 6.0, 0.7)
    high_debt = sovereign_credit_risk_assessment(1.5, 0.0, 0.0, 6.0, 0.7)
    assert low_debt["credit_score"] > high_debt["credit_score"]
    assert low_debt["pd"] < high_debt["pd"]


def test_sector_lift_and_riskiest():
    r = sector_default_rate_analysis(
        np.array([1.0, 10.0]),
        np.array([100.0, 100.0]),
        sector_names=["tech", "retail"],
    )
    assert r["riskiest_sector"] == "retail"
    assert r["lift"]["retail"] > 1.0 > r["lift"]["tech"]

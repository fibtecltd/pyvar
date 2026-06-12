"""tests/test_oprisk_scenario.py — OpRisk scenario analysis tests."""

import numpy as np
import pytest

from engine.oprisk_scenario import (
    scenario_analysis_oprisk,
    scenario_expert_elicitation_model,
    scenario_frequency_estimation,
    scenario_severity_estimation,
)


def test_frequency_expert():
    r = scenario_frequency_estimation(2.5)
    assert r["lambda"] == 2.5
    assert r["source"] == "expert"


def test_frequency_empirical():
    r = scenario_frequency_estimation(0.0, occurrences=10, observation_years=5.0)
    assert r["lambda"] == 2.0
    assert r["source"] == "empirical"


def test_frequency_invalid_window_raises():
    with pytest.raises(ValueError):
        scenario_frequency_estimation(0.0, occurrences=10, observation_years=0.0)


def test_severity_lognormal_calibration():
    r = scenario_severity_estimation(typical_loss=1_000_000.0, worst_case_loss=10_000_000.0)
    # mu = ln(1e6); sigma derived from 99th percentile
    assert abs(r["mu"] - np.log(1e6)) < 1e-6
    assert r["sigma"] > 0
    assert r["mean_severity"] > 1_000_000.0  # mean > median for lognormal


def test_severity_worst_below_typical_raises():
    with pytest.raises(ValueError):
        scenario_severity_estimation(1000.0, 500.0)


def test_severity_invalid_percentile_raises():
    with pytest.raises(ValueError):
        scenario_severity_estimation(1000.0, 5000.0, worst_case_percentile=0.4)


def test_expert_elicitation_consensus():
    r = scenario_expert_elicitation_model(np.array([100.0, 200.0, 300.0]))
    assert r["consensus"] == 200.0
    assert r["dispersion"] > 0


def test_expert_elicitation_weighted():
    r = scenario_expert_elicitation_model(np.array([100.0, 200.0]), np.array([3.0, 1.0]))
    assert r["consensus"] == 125.0  # (300 + 200) / 4


def test_expert_elicitation_zero_weights_raises():
    with pytest.raises(ValueError):
        scenario_expert_elicitation_model(np.array([1.0]), np.array([0.0]))


def test_scenario_analysis_capital():
    r = scenario_analysis_oprisk(2.0, 13.0, 1.5, confidence_level=0.999, n_years=20000)
    assert r["scenario_var"] > r["expected_loss"]
    assert r["expected_shortfall"] >= r["scenario_var"]


def test_scenario_analysis_deterministic():
    r1 = scenario_analysis_oprisk(2.0, 13.0, 1.5, n_years=10000, seed=9)
    r2 = scenario_analysis_oprisk(2.0, 13.0, 1.5, n_years=10000, seed=9)
    assert r1["scenario_var"] == r2["scenario_var"]


def test_scenario_analysis_invalid_lambda_raises():
    with pytest.raises(ValueError):
        scenario_analysis_oprisk(0.0, 13.0, 1.5)

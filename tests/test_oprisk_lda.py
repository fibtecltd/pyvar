"""tests/test_oprisk_lda.py — LDA / AMA / OpVaR numerical-correctness tests.

No mocking of engine functions (CLAUDE.md §5). Asserts LDA properties: OpVaR >
expected loss, ES >= OpVaR, determinism with fixed seed, monotonicity in
confidence, and the frequency ⊗ severity compound structure.
"""

import numpy as np
import pytest

from engine.oprisk_lda import (
    advanced_measurement_approach_ama,
    compound_loss_distribution,
    frequency_distribution_fitting,
    loss_distribution_approach_lda,
    monte_carlo_oprisk_capital,
    operational_var_opvar,
    severity_distribution_fitting,
)


@pytest.fixture
def loss_data():
    rng = np.random.default_rng(0)
    counts = rng.poisson(10, size=20)
    losses = rng.lognormal(8.0, 1.0, size=200)
    return counts, losses


def test_frequency_fit_lambda(loss_data):
    counts, _ = loss_data
    r = frequency_distribution_fitting(counts)
    assert r["distribution"] == "poisson"
    assert abs(r["lambda"] - float(np.mean(counts))) < 1e-6


def test_frequency_fit_empty_raises():
    with pytest.raises(ValueError):
        frequency_distribution_fitting(np.array([]))


def test_severity_fit_lognormal(loss_data):
    _, losses = loss_data
    r = severity_distribution_fitting(losses)
    assert r["distribution"] == "lognormal"
    assert r["mean_severity"] > 0


def test_severity_fit_nonpositive_raises():
    with pytest.raises(ValueError):
        severity_distribution_fitting(np.array([1.0, -2.0]))


def test_severity_fit_unsupported_raises():
    with pytest.raises(ValueError):
        severity_distribution_fitting(np.array([1.0]), distribution="pareto")


def test_compound_distribution_deterministic():
    r1 = compound_loss_distribution(10.0, 8.0, 1.0, n_years=5000, seed=1)
    r2 = compound_loss_distribution(10.0, 8.0, 1.0, n_years=5000, seed=1)
    assert r1["mean_annual_loss"] == r2["mean_annual_loss"]


def test_compound_distribution_mean_scales_with_lambda():
    low = compound_loss_distribution(5.0, 8.0, 0.5, n_years=20000, seed=2)
    high = compound_loss_distribution(20.0, 8.0, 0.5, n_years=20000, seed=2)
    assert high["mean_annual_loss"] > low["mean_annual_loss"]


def test_compound_invalid_lambda_raises():
    with pytest.raises(ValueError):
        compound_loss_distribution(0.0, 8.0, 1.0)


def test_mc_capital_opvar_above_el():
    r = monte_carlo_oprisk_capital(10.0, 8.0, 1.0, confidence_level=0.999, n_years=50000)
    assert r["opvar"] > r["expected_loss"]
    assert abs(r["capital"] - (r["opvar"] - r["expected_loss"])) < 0.05
    assert r["expected_shortfall"] >= r["opvar"]


def test_mc_capital_monotone_confidence():
    r99 = monte_carlo_oprisk_capital(10.0, 8.0, 1.0, confidence_level=0.99, n_years=50000, seed=3)
    r999 = monte_carlo_oprisk_capital(10.0, 8.0, 1.0, confidence_level=0.999, n_years=50000, seed=3)
    assert r999["opvar"] >= r99["opvar"]


def test_mc_capital_invalid_confidence_raises():
    with pytest.raises(ValueError):
        monte_carlo_oprisk_capital(10.0, 8.0, 1.0, confidence_level=0.5)


def test_opvar_empirical_reader():
    losses = np.arange(1.0, 1001.0)
    r = operational_var_opvar(losses, confidence_level=0.99)
    # 99th percentile near 990
    assert 985 <= r["opvar"] <= 995
    assert r["expected_shortfall"] >= r["opvar"]


def test_opvar_empty_raises():
    with pytest.raises(ValueError):
        operational_var_opvar(np.array([]))


def test_lda_pipeline(loss_data):
    counts, losses = loss_data
    r = loss_distribution_approach_lda(counts, losses, n_years=20000, seed=4)
    assert r["opvar"] > r["expected_loss"]
    assert r["frequency"]["distribution"] == "poisson"
    assert r["severity"]["distribution"] == "lognormal"


def test_ama_el_covered_vs_not(loss_data):
    counts, losses = loss_data
    covered = advanced_measurement_approach_ama(counts, losses, True, n_years=20000, seed=5)
    full = advanced_measurement_approach_ama(counts, losses, False, n_years=20000, seed=5)
    # full OpVaR capital >= UL-only capital
    assert full["ama_capital"] >= covered["ama_capital"]
    assert full["ama_capital"] == full["opvar"]

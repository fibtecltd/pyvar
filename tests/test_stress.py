"""tests/test_stress.py — numerical tests for the stress-testing family.

Asserts the defining properties: replay identifies the true worst day, scenario
P&L is linear in shocks, reverse stress reproduces the target loss, sensitivity
profiles are linear in the swept factor, and sector P&L is additive.
"""

import numpy as np
import pytest

from engine.stress import (
    contagion_stress_scenario,
    historical_scenario_replay,
    hypothetical_multi_factor_scenario,
    macro_scenario_generator,
    reverse_stress_testing,
    sector_stress_scenario,
    sensitivity_stress_profile,
)


@pytest.fixture
def spd_cov():
    rng = np.random.default_rng(5)
    a = rng.normal(0, 1, size=(3, 3))
    return a @ a.T + np.eye(3)


# ── 19. Historical Scenario Replay ────────────────────────────────────────────


def test_historical_replay_finds_worst_day():
    exposures = np.array([100.0, 50.0])
    hist = np.array([[0.01, 0.0], [-0.05, -0.02], [0.0, 0.03]])
    r = historical_scenario_replay(exposures, hist)
    # Day 1: 100*-0.05 + 50*-0.02 = -6.0 is the worst
    assert r["worst_scenario_index"] == 1
    assert abs(r["worst_loss"] - (-6.0)) < 1e-9


def test_historical_replay_shape_mismatch_raises():
    with pytest.raises(ValueError):
        historical_scenario_replay(np.array([1.0, 2.0]), np.zeros((4, 3)))


# ── 20. Hypothetical Multi-Factor Scenario ────────────────────────────────────


def test_multi_factor_scenario_is_linear():
    e = np.array([100.0, -50.0, 25.0])
    s = np.array([0.01, 0.02, -0.03])
    r1 = hypothetical_multi_factor_scenario(e, s)
    r2 = hypothetical_multi_factor_scenario(e, 2 * s)
    assert abs(r2["pnl"] - 2 * r1["pnl"]) < 1e-6


# ── 21. Reverse Stress Testing ────────────────────────────────────────────────


def test_reverse_stress_reproduces_target_loss(spd_cov):
    e = np.array([120.0, -80.0, 40.0])
    r = reverse_stress_testing(e, spd_cov, target_loss=10.0)
    shock = np.array(r["shock"])
    # Applying the solved shock to the exposures must yield -target_loss P&L.
    assert abs(float(e @ shock) - (-10.0)) < 1e-4


def test_reverse_stress_negative_target_raises(spd_cov):
    with pytest.raises(ValueError):
        reverse_stress_testing(np.array([1.0, 1.0, 1.0]), spd_cov, target_loss=-5.0)


# ── 22. Sensitivity Stress Profile ────────────────────────────────────────────


def test_sensitivity_profile_linear_in_shock():
    e = np.array([100.0, 50.0])
    grid = np.linspace(-0.1, 0.1, 5)
    r = sensitivity_stress_profile(e, 0, grid)
    profile = r["pnl_profile"]
    # Linear: equal spacing in shock → equal spacing in P&L
    diffs = np.diff(profile)
    assert np.allclose(diffs, diffs[0])


def test_sensitivity_profile_bad_index_raises():
    with pytest.raises(ValueError):
        sensitivity_stress_profile(np.array([1.0]), 5, np.array([0.0]))


# ── 23. Sector Stress Scenario ────────────────────────────────────────────────


def test_sector_stress_total_is_additive():
    e = np.array([200.0, -100.0, 50.0])
    s = np.array([-0.03, 0.02, -0.01])
    r = sector_stress_scenario(e, s, sector_names=["equity", "rates", "credit"])
    assert abs(sum(r["sector_pnl"].values()) - r["total_pnl"]) < 1e-6


# ── 24. Macro Scenario Generator ──────────────────────────────────────────────


def test_macro_scenario_generator_reproduces_covariance(spd_cov):
    r = macro_scenario_generator(spd_cov, n_scenarios=200_000, seed=1)
    sample = np.array(r["sample_cov"])
    assert np.allclose(sample, spd_cov, atol=0.15)  # large sample → close to target


def test_macro_scenario_generator_deterministic(spd_cov):
    r1 = macro_scenario_generator(spd_cov, n_scenarios=1000, seed=9)
    r2 = macro_scenario_generator(spd_cov, n_scenarios=1000, seed=9)
    assert r1["scenarios"] == r2["scenarios"]


def test_macro_scenario_generator_non_psd_raises():
    with pytest.raises(ValueError):
        macro_scenario_generator(np.array([[1.0, 2.0], [2.0, 1.0]]), n_scenarios=10)


# ── 25. Contagion Stress Scenario ─────────────────────────────────────────────


def test_contagion_zero_rounds_returns_initial():
    x0 = np.array([1.0, -2.0, 0.5])
    c = np.array([[0.0, 0.1, 0.0], [0.2, 0.0, 0.1], [0.0, 0.3, 0.0]])
    r = contagion_stress_scenario(x0, c, rounds=0)
    assert np.allclose(r["amplified_shock"], x0)
    assert abs(r["amplification_factor"] - 1.0) < 1e-9


def test_contagion_amplifies_shock():
    x0 = np.array([1.0, 1.0, 1.0])
    c = np.array([[0.0, 0.2, 0.1], [0.2, 0.0, 0.2], [0.1, 0.2, 0.0]])
    r = contagion_stress_scenario(x0, c, rounds=3)
    assert r["amplification_factor"] > 1.0  # positive spillovers amplify

"""tests/test_portfolio_factor.py — numerical-correctness tests for factor models.

No mocking (CLAUDE.md §5 RULE 1). Tests assert OLS recovers known betas, R^2 in
[0,1], PCA explained-variance sums to 1 and orders descending, clustering
recovers obvious groups, and regime detection separates calm/stress variance.
"""

import numpy as np
import pytest

from engine.portfolio_factor import (
    carhart_4_factor_model,
    correlation_clustering,
    fama_french_3_factor_model,
    fama_french_5_factor_model,
    principal_component_analysis,
    regime_detection_hmm,
)


# ── Fama-French / Carhart regressions ─────────────────────────────────────────


def test_ff3_recovers_known_betas():
    rng = np.random.default_rng(1)
    n = 1000
    factors = rng.normal(0, 0.01, size=(n, 3))
    true_beta = np.array([1.2, 0.4, -0.3])
    alpha = 0.0005
    y = alpha + factors @ true_beta + rng.normal(0, 1e-4, size=n)
    r = fama_french_3_factor_model(y, factors)
    assert abs(r["betas"]["mkt"] - 1.2) < 0.02
    assert abs(r["betas"]["smb"] - 0.4) < 0.02
    assert abs(r["betas"]["hml"] + 0.3) < 0.02
    assert 0.0 <= r["r_squared"] <= 1.0


def test_carhart_has_four_betas():
    rng = np.random.default_rng(2)
    n = 500
    factors = rng.normal(0, 0.01, size=(n, 4))
    y = factors @ np.array([1.0, 0.2, 0.1, 0.3]) + rng.normal(0, 1e-4, size=n)
    r = carhart_4_factor_model(y, factors)
    assert set(r["betas"].keys()) == {"mkt", "smb", "hml", "mom"}


def test_ff5_has_five_betas():
    rng = np.random.default_rng(3)
    n = 600
    factors = rng.normal(0, 0.01, size=(n, 5))
    y = factors @ np.array([1.0, 0.2, 0.1, 0.3, -0.2]) + rng.normal(0, 1e-4, size=n)
    r = fama_french_5_factor_model(y, factors)
    assert set(r["betas"].keys()) == {"mkt", "smb", "hml", "rmw", "cma"}


def test_ff3_too_few_obs_raises():
    with pytest.raises(ValueError):
        fama_french_3_factor_model(np.array([0.01, 0.02]), np.zeros((2, 3)))


# ── PCA ───────────────────────────────────────────────────────────────────────


def test_pca_explained_variance_sums_to_one():
    rng = np.random.default_rng(4)
    m = rng.normal(0, 1, size=(500, 4))
    r = principal_component_analysis(m)
    assert abs(sum(r["explained_variance_ratio"]) - 1.0) < 1e-8


def test_pca_eigenvalues_descending():
    rng = np.random.default_rng(5)
    m = rng.normal(0, 1, size=(500, 5))
    r = principal_component_analysis(m, n_components=3)
    ev = r["eigenvalues"]
    assert all(ev[i] >= ev[i + 1] - 1e-9 for i in range(len(ev) - 1))


def test_pca_dominant_component_for_correlated():
    rng = np.random.default_rng(6)
    common = rng.normal(0, 1, size=500)
    m = np.column_stack([common + rng.normal(0, 0.01, 500) for _ in range(4)])
    r = principal_component_analysis(m)
    assert r["explained_variance_ratio"][0] > 0.9  # one dominant factor


# ── Correlation clustering ────────────────────────────────────────────────────


def test_clustering_recovers_two_groups():
    rng = np.random.default_rng(7)
    g1 = rng.normal(0, 1, size=500)
    g2 = rng.normal(0, 1, size=500)
    m = np.column_stack([
        g1 + rng.normal(0, 0.01, 500),
        g1 + rng.normal(0, 0.01, 500),
        g2 + rng.normal(0, 0.01, 500),
        g2 + rng.normal(0, 0.01, 500),
    ])
    r = correlation_clustering(m, n_clusters=2)
    labels = r["labels"]
    assert labels[0] == labels[1]
    assert labels[2] == labels[3]
    assert labels[0] != labels[2]


def test_clustering_invalid_n_raises():
    rng = np.random.default_rng(8)
    m = rng.normal(0, 1, size=(50, 3))
    with pytest.raises(ValueError):
        correlation_clustering(m, n_clusters=5)


# ── Regime detection ──────────────────────────────────────────────────────────


def test_regime_detection_separates_variance():
    rng = np.random.default_rng(9)
    calm = rng.normal(0.001, 0.005, size=400)
    stress = rng.normal(-0.002, 0.03, size=200)
    series = np.concatenate([calm, stress, calm])
    r = regime_detection_hmm(series, n_iter=60)
    # The stress regime has the larger variance by construction.
    assert r["variances"][r["stress_regime"]] == max(r["variances"])
    assert len(r["regime_labels"]) == series.size


def test_regime_detection_too_few_obs_raises():
    with pytest.raises(ValueError):
        regime_detection_hmm(np.array([0.01, 0.02, 0.03]))

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
    m = np.column_stack(
        [
            g1 + rng.normal(0, 0.01, 500),
            g1 + rng.normal(0, 0.01, 500),
            g2 + rng.normal(0, 0.01, 500),
            g2 + rng.normal(0, 0.01, 500),
        ]
    )
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


def _old_hand_rolled_single_linkage(returns_matrix: np.ndarray, n_clusters: int) -> np.ndarray:
    """Independent re-implementation of the pre-SciPy hand-rolled merge loop.

    Kept only in this test file (not in engine/) as the ground truth that the
    SciPy-based ``correlation_clustering`` must reproduce membership-for-
    membership (same single-linkage algorithm, SciPy computes it instead of a
    Python triple-nested loop).
    """
    m = np.asarray(returns_matrix, dtype=np.float64)
    n_assets = m.shape[1]
    corr = np.atleast_2d(np.corrcoef(m, rowvar=False))
    dist = np.sqrt(np.clip(2.0 * (1.0 - corr), 0.0, None))
    clusters: list[list[int]] = [[i] for i in range(n_assets)]
    while len(clusters) > n_clusters:
        best = (float("inf"), 0, 1)
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                d = min(dist[i, j] for i in clusters[a] for j in clusters[b])
                if d < best[0]:
                    best = (d, a, b)
        _, a, b = best
        clusters[a].extend(clusters[b])
        clusters.pop(b)
    labels = np.empty(n_assets, dtype=np.int64)
    for cid, members in enumerate(clusters):
        for i in members:
            labels[i] = cid
    return labels


def _same_partition(l1: np.ndarray, l2: list[int]) -> bool:
    """True iff two label arrays induce the same partition (ids may differ)."""
    n = len(l1)
    for i in range(n):
        for j in range(n):
            if (l1[i] == l1[j]) != (l2[i] == l2[j]):
                return False
    return True


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
def test_clustering_scipy_matches_hand_rolled_membership(seed):
    """The SciPy linkage/fcluster reimplementation must reproduce the exact
    cluster membership of the retired hand-rolled merge loop (task #17,
    portfolio-analytics caveat triage) — only arbitrary label ids may differ.
    """
    rng = np.random.default_rng(seed)
    n_assets = int(rng.integers(3, 8))
    n_obs = int(rng.integers(40, 200))
    m = rng.normal(size=(n_obs, n_assets))
    if n_assets >= 4:
        d1 = rng.normal(size=n_obs)
        d2 = rng.normal(size=n_obs)
        half = n_assets // 2
        cols = [d1 + 0.05 * rng.normal(size=n_obs) for _ in range(half)]
        cols += [d2 + 0.05 * rng.normal(size=n_obs) for _ in range(n_assets - half)]
        m = np.column_stack(cols)
    n_clusters = int(rng.integers(1, n_assets + 1))

    old_labels = _old_hand_rolled_single_linkage(m, n_clusters)
    new_out = correlation_clustering(m, n_clusters=n_clusters)

    assert _same_partition(old_labels, new_out["labels"])
    assert new_out["n_clusters"] == len(set(old_labels.tolist()))


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

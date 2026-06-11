"""tests/test_backtesting.py — numerical tests for VaR backtesting.

Verifies the Basel 250-day traffic-light zones, the Kupiec POF and
Christoffersen independence likelihood-ratio tests (reject behaviour against
constructed good/bad models), and the combined conditional-coverage test.
"""

import numpy as np
import pytest

from engine.backtesting import (
    basel_capital_addon_multiplier,
    christoffersen_independence_test,
    combined_backtesting,
    kupiec_pof_test,
    rolling_var_backtest,
    traffic_light_backtesting,
    var_breach_cluster_analysis,
)

# ── 45. Traffic Light Backtesting (Basel) ─────────────────────────────────────


def test_traffic_light_zones():
    var = np.full(250, 0.02)
    # 3 breaches → green
    ret = np.zeros(250)
    ret[:3] = -0.05
    assert traffic_light_backtesting(ret, var)["basel_zone"] == "green"
    # 7 breaches → yellow
    ret = np.zeros(250)
    ret[:7] = -0.05
    assert traffic_light_backtesting(ret, var)["basel_zone"] == "yellow"
    # 12 breaches → red
    ret = np.zeros(250)
    ret[:12] = -0.05
    r = traffic_light_backtesting(ret, var)
    assert r["basel_zone"] == "red"
    assert r["expected_window"] == 250


def test_traffic_light_length_mismatch_raises():
    with pytest.raises(ValueError):
        traffic_light_backtesting(np.zeros(10), np.zeros(9))


# ── 46. Kupiec Proportion of Failures Test ────────────────────────────────────


def test_kupiec_accepts_correct_coverage():
    # 99% VaR over 1000 days → expect ~10 breaches; 10 should not be rejected
    r = kupiec_pof_test(n_breaches=10, n_observations=1000, confidence_level=0.99)
    assert not r["reject"]


def test_kupiec_rejects_excess_breaches():
    # 60 breaches at 99% over 1000 days is far too many → reject
    r = kupiec_pof_test(n_breaches=60, n_observations=1000, confidence_level=0.99)
    assert r["reject"]


def test_kupiec_invalid_inputs_raise():
    with pytest.raises(ValueError):
        kupiec_pof_test(n_breaches=5, n_observations=0)


# ── 47. Christoffersen Independence Test ──────────────────────────────────────


def test_christoffersen_rejects_clustered_breaches():
    # Breaches all clustered together → strong serial dependence → reject
    b = np.zeros(250, dtype=int)
    b[100:115] = 1  # 15 consecutive breaches
    r = christoffersen_independence_test(b)
    assert r["reject"]


def test_christoffersen_independent_breaches_not_rejected():
    rng = np.random.default_rng(0)
    b = (rng.random(1000) < 0.01).astype(int)  # i.i.d. Bernoulli breaches
    r = christoffersen_independence_test(b)
    assert not r["reject"]


# ── 48. Combined Backtesting (Kupiec + Christoffersen) ────────────────────────


def test_combined_backtesting_is_sum_and_rejects_bad_model():
    b = np.zeros(250, dtype=int)
    b[50:75] = 1  # both too many AND clustered
    r = combined_backtesting(b, confidence_level=0.99)
    assert abs(r["lr_cc"] - (r["lr_pof"] + r["lr_ind"])) < 1e-6
    assert r["reject"]


# ── 49. Basel Capital Add-On Multiplier ───────────────────────────────────────


def test_capital_multiplier_zones():
    assert basel_capital_addon_multiplier(3)["multiplier"] == 3.0  # green
    assert basel_capital_addon_multiplier(3)["zone"] == "green"
    assert basel_capital_addon_multiplier(7)["multiplier"] == 3.65  # yellow schedule
    assert basel_capital_addon_multiplier(12)["multiplier"] == 4.0  # red
    assert basel_capital_addon_multiplier(12)["zone"] == "red"


def test_capital_multiplier_negative_raises():
    with pytest.raises(ValueError):
        basel_capital_addon_multiplier(-1)


# ── 50. Rolling VaR Backtest (250-day) ────────────────────────────────────────


def test_rolling_var_backtest_breach_rate_near_alpha():
    rng = np.random.default_rng(0)
    returns = rng.normal(0.0, 0.01, size=1500)
    r = rolling_var_backtest(returns, window=250, confidence_level=0.99)
    # Well-specified model: breach rate should be in a small band around 1%.
    assert 0.0 <= r["breach_rate_pct"] <= 4.0
    assert r["window"] == 250


def test_rolling_var_backtest_too_short_raises():
    with pytest.raises(ValueError):
        rolling_var_backtest(np.zeros(100), window=250)


# ── 51. VaR Breach Cluster Analysis ───────────────────────────────────────────


def test_breach_cluster_analysis_counts_runs():
    b = np.array([0, 1, 1, 0, 0, 1, 0, 1, 1, 1])
    r = var_breach_cluster_analysis(b)
    assert r["n_breaches"] == 6
    assert r["n_clusters"] == 3
    assert r["max_cluster_length"] == 3

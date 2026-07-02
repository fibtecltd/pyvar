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


# ── P5b: Basel 250-day backtesting ────────────────────────────────────────────
# Regulatory basis: BCBS, "Supervisory framework for the use of 'backtesting' in
# conjunction with the internal models approach to market risk capital
# requirements" (January 1996). Window is EXACTLY 250 trading days; traffic-light
# zones per CLAUDE.md §4.3 (ZERO tolerance): green < 5, yellow 5-9, red >= 10.
# The engine's zone strings are "green" / "yellow" / "red".

_BASEL_WINDOW = 250
_BASEL_CONFIDENCE = 0.99


def _synthetic_daily_pnl(n_days: int = _BASEL_WINDOW, seed: int = 42) -> np.ndarray:
    """250 days of reproducible synthetic daily P&L, normal(mean=0, std=0.01)."""
    rng = np.random.default_rng(seed)
    return rng.normal(loc=0.0, scale=0.01, size=n_days)


def test_p5b_basel_window_is_exactly_250():
    # CLAUDE.md §4.3: EXACTLY 250 trading days (not 252, not 260).
    pnl = _synthetic_daily_pnl()
    assert pnl.size == 250
    var = np.full(250, 0.0233)  # ~99% one-sided VaR for std=0.01 normal (2.326σ)
    result = traffic_light_backtesting(pnl, var)
    assert result["expected_window"] == 250
    assert result["n_observations"] == 250


def test_p5b_breach_count_within_poisson_bounds():
    # 250 days of N(0, 0.01) P&L, seed=42. Compute the 99% VaR from the sample
    # (analytic parametric: 2.326 * std) and count breaches. For a well-specified
    # 99% VaR over 250 days the expected breach count is 250 * 0.01 = 2.5.
    # A 99% Poisson-based tolerance band around lambda=2.5 is [0, 8]; the Basel
    # green zone (< 5) is the operative supervisory bound. Assert both.
    pnl = _synthetic_daily_pnl()
    z_99 = 2.3263478740408408  # inverse standard normal at 0.99
    sample_std = float(np.std(pnl))
    var_level = z_99 * sample_std
    var = np.full(250, var_level)

    result = traffic_light_backtesting(pnl, var)
    n_breaches = result["n_breaches"]
    expected = 250 * (1.0 - _BASEL_CONFIDENCE)  # 2.5

    # Poisson two-sided ~99% band around lambda=2.5.
    assert 0 <= n_breaches <= 8, f"breach count {n_breaches} outside Poisson band"
    # For this seed the well-specified model must land in the Basel green zone.
    assert n_breaches < 5
    assert result["basel_zone"] == "green"
    assert abs(expected - 2.5) < 1e-9


def test_p5b_green_zone_explicit():
    # Engineer EXACTLY 4 breaches → green (< 5).  CLAUDE.md §4.3 ZERO tolerance.
    var = np.full(250, 0.02)
    ret = np.zeros(250)
    ret[:4] = -0.05  # 4 losses exceeding VaR
    result = traffic_light_backtesting(ret, var)
    assert result["n_breaches"] == 4
    assert result["basel_zone"] == "green"


def test_p5b_yellow_zone_explicit():
    # Engineer exactly 5 breaches (lower yellow bound) and 9 (upper yellow bound).
    var = np.full(250, 0.02)
    for k in (5, 9):
        ret = np.zeros(250)
        ret[:k] = -0.05
        result = traffic_light_backtesting(ret, var)
        assert result["n_breaches"] == k
        assert result["basel_zone"] == "yellow"


def test_p5b_red_zone_explicit():
    # Engineer EXACTLY 10 breaches → red (>= 10).  CLAUDE.md §4.3 ZERO tolerance.
    var = np.full(250, 0.02)
    ret = np.zeros(250)
    ret[:10] = -0.05
    result = traffic_light_backtesting(ret, var)
    assert result["n_breaches"] == 10
    assert result["basel_zone"] == "red"


def test_p5b_zone_boundaries_exact_thresholds():
    # Boundary sweep asserting CLAUDE.md §4.3 boundaries verbatim at zero
    # tolerance: 0-4 green, 5-9 yellow, 10+ red.
    var = np.full(250, 0.02)
    expected_zone = {}
    for k in range(0, 5):
        expected_zone[k] = "green"
    for k in range(5, 10):
        expected_zone[k] = "yellow"
    for k in (10, 11, 15, 20):
        expected_zone[k] = "red"

    for k, zone in expected_zone.items():
        ret = np.zeros(250)
        ret[:k] = -0.05
        result = traffic_light_backtesting(ret, var)
        assert result["n_breaches"] == k
        assert result["basel_zone"] == zone, f"{k} breaches → expected {zone}"


def test_p5b_capital_multiplier_matches_zone_boundaries():
    # The add-on multiplier zones must agree with the traffic-light zones at the
    # same §4.3 boundaries: green 3.0, red 4.0.
    assert basel_capital_addon_multiplier(4)["zone"] == "green"
    assert basel_capital_addon_multiplier(4)["multiplier"] == 3.0
    assert basel_capital_addon_multiplier(5)["zone"] == "yellow"
    assert basel_capital_addon_multiplier(9)["zone"] == "yellow"
    assert basel_capital_addon_multiplier(10)["zone"] == "red"
    assert basel_capital_addon_multiplier(10)["multiplier"] == 4.0

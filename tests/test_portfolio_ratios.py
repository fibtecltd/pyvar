"""tests/test_portfolio_ratios.py — numerical-correctness tests for ratios.

No mocking of engine functions (CLAUDE.md §5 RULE 1). Tests assert sign,
scaling, monotonicity and closed-form reductions.
"""

import numpy as np
import pytest

from engine.portfolio_ratios import (
    calmar_ratio,
    information_ratio,
    jensens_alpha,
    omega_ratio,
    sharpe_ratio,
    sortino_ratio,
    tail_ratio,
    treynor_ratio,
    ulcer_index,
)


@pytest.fixture
def returns():
    rng = np.random.default_rng(42)
    return rng.normal(0.0008, 0.012, size=1000)


@pytest.fixture
def bench_returns():
    rng = np.random.default_rng(11)
    return rng.normal(0.0005, 0.010, size=1000)


# ── Sharpe ────────────────────────────────────────────────────────────────────


def test_sharpe_positive_for_positive_mean(returns):
    r = sharpe_ratio(returns, risk_free=0.0, periods_per_year=252)
    assert r["sharpe"] > 0


def test_sharpe_sign_flips_with_negative_returns(returns):
    pos = sharpe_ratio(returns)
    neg = sharpe_ratio(-returns)
    assert np.sign(pos["sharpe"]) == -np.sign(neg["sharpe"])


def test_sharpe_annualisation_scaling(returns):
    r = sharpe_ratio(returns, periods_per_year=252)
    assert abs(r["sharpe"] - r["sharpe_period"] * np.sqrt(252)) < 1e-8


def test_sharpe_empty_raises():
    with pytest.raises(ValueError):
        sharpe_ratio(np.array([]))


# ── Sortino ─────────────────────────────────────────────────────────────────


def test_sortino_geq_sharpe_when_upside_vol_present(returns):
    # Downside deviation <= total std, so Sortino magnitude >= Sharpe magnitude.
    s = sharpe_ratio(returns, periods_per_year=252)
    so = sortino_ratio(returns, periods_per_year=252)
    assert abs(so["sortino"]) >= abs(s["sharpe"]) - 1e-6


def test_sortino_positive(returns):
    assert sortino_ratio(returns)["sortino"] > 0


# ── Calmar ──────────────────────────────────────────────────────────────────


def test_calmar_max_drawdown_in_unit_interval(returns):
    r = calmar_ratio(returns)
    assert 0.0 <= r["max_drawdown"] <= 1.0


def test_calmar_monotone_growth_has_zero_drawdown():
    r = calmar_ratio(np.full(50, 0.01))  # always positive returns
    assert r["max_drawdown"] == 0.0
    assert r["calmar"] == 0.0  # division guard


# ── Information ratio ─────────────────────────────────────────────────────────


def test_information_ratio_zero_when_identical(returns):
    r = information_ratio(returns, returns)
    assert r["information_ratio"] == 0.0
    assert r["tracking_error"] == 0.0


def test_information_ratio_length_mismatch_raises(returns):
    with pytest.raises(ValueError):
        information_ratio(returns, returns[:-1])


# ── Treynor ───────────────────────────────────────────────────────────────────


def test_treynor_beta_one_when_self(returns):
    r = treynor_ratio(returns, returns)
    assert abs(r["beta"] - 1.0) < 1e-9


# ── Jensen's alpha ────────────────────────────────────────────────────────────


def test_jensen_alpha_zero_when_self(returns):
    # Regressing on itself: beta=1, alpha=0.
    r = jensens_alpha(returns, returns, risk_free=0.0)
    assert abs(r["beta"] - 1.0) < 1e-9
    assert abs(r["alpha_period"]) < 1e-12


def test_jensen_alpha_annualisation(returns, bench_returns):
    r = jensens_alpha(returns, bench_returns, periods_per_year=252)
    assert abs(r["alpha"] - r["alpha_period"] * 252) < 1e-8


# ── Omega ─────────────────────────────────────────────────────────────────────


def test_omega_above_one_for_positive_skewed(returns):
    # Positive mean returns -> more gains than losses about 0 -> omega > 1.
    r = omega_ratio(returns, threshold=0.0)
    assert r["omega"] > 1.0


def test_omega_all_gains_is_infinite():
    r = omega_ratio(np.array([0.01, 0.02, 0.03]), threshold=0.0)
    assert r["omega"] == float("inf")


# ── Tail ratio ────────────────────────────────────────────────────────────────


def test_tail_ratio_about_one_for_symmetric():
    rng = np.random.default_rng(3)
    sym = rng.normal(0.0, 0.01, size=100000)
    r = tail_ratio(sym, tail=0.05)
    assert abs(r["tail_ratio"] - 1.0) < 0.1


def test_tail_ratio_invalid_tail_raises(returns):
    with pytest.raises(ValueError):
        tail_ratio(returns, tail=0.6)


# ── Ulcer index ───────────────────────────────────────────────────────────────


def test_ulcer_index_zero_for_monotone_increasing():
    r = ulcer_index(np.array([1.0, 2.0, 3.0, 4.0]), is_equity_curve=True)
    assert r["ulcer_index"] == 0.0


def test_ulcer_index_positive_with_drawdown():
    r = ulcer_index(np.array([100.0, 90.0, 80.0, 95.0]), is_equity_curve=True)
    assert r["ulcer_index"] > 0.0

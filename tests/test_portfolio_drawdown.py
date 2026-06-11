"""tests/test_portfolio_drawdown.py — numerical-correctness tests for drawdowns.

No mocking (CLAUDE.md §5 RULE 1). Tests assert bounds [0, 1], closed-form
cases, ordering CDaR >= DaR, and that max drawdown dominates average drawdown.
"""

import numpy as np
import pytest

from engine.portfolio_drawdown import (
    average_drawdown,
    conditional_drawdown_at_risk,
    drawdown_duration,
    maximum_drawdown,
)


@pytest.fixture
def returns():
    rng = np.random.default_rng(42)
    return rng.normal(0.0003, 0.015, size=1000)


# ── Maximum drawdown ──────────────────────────────────────────────────────────


def test_max_drawdown_in_unit_interval(returns):
    r = maximum_drawdown(returns)
    assert 0.0 <= r["max_drawdown"] <= 1.0


def test_max_drawdown_known_curve():
    # 100 -> 50 is a 50% drawdown.
    eq = np.array([100.0, 120.0, 60.0, 80.0, 130.0])
    r = maximum_drawdown(eq, is_equity_curve=True)
    assert abs(r["max_drawdown"] - 0.5) < 1e-12  # peak 120 -> trough 60
    assert r["peak_index"] == 1
    assert r["trough_index"] == 2


def test_max_drawdown_zero_for_monotone():
    r = maximum_drawdown(np.array([1.0, 2.0, 3.0]), is_equity_curve=True)
    assert r["max_drawdown"] == 0.0


def test_max_drawdown_empty_raises():
    with pytest.raises(ValueError):
        maximum_drawdown(np.array([]))


# ── Average drawdown ──────────────────────────────────────────────────────────


def test_average_le_max_drawdown(returns):
    r = average_drawdown(returns)
    assert r["average_drawdown"] <= r["max_drawdown"] + 1e-12
    assert r["average_drawdown"] >= 0.0


# ── Drawdown duration ─────────────────────────────────────────────────────────


def test_drawdown_duration_known_curve():
    # Underwater for 2 periods (60, 80) after peak at index 1, recovers at 130.
    eq = np.array([100.0, 120.0, 60.0, 80.0, 130.0])
    r = drawdown_duration(eq, is_equity_curve=True)
    assert r["max_duration"] == 2
    assert r["current_duration"] == 0  # recovered to new high at end


def test_drawdown_duration_current_underwater():
    eq = np.array([100.0, 120.0, 90.0, 80.0])
    r = drawdown_duration(eq, is_equity_curve=True)
    assert r["current_duration"] == 2


# ── CDaR ──────────────────────────────────────────────────────────────────────


def test_cdar_ge_dar(returns):
    r = conditional_drawdown_at_risk(returns, confidence_level=0.95)
    assert r["cdar"] >= r["dar"] - 1e-12
    assert r["cdar"] >= 0.0


def test_cdar_le_max_drawdown(returns):
    cd = conditional_drawdown_at_risk(returns, confidence_level=0.95)
    md = maximum_drawdown(returns)
    assert cd["cdar"] <= md["max_drawdown"] + 1e-9


def test_cdar_monotone_in_confidence(returns):
    low = conditional_drawdown_at_risk(returns, confidence_level=0.90)
    high = conditional_drawdown_at_risk(returns, confidence_level=0.99)
    assert high["cdar"] >= low["cdar"] - 1e-9

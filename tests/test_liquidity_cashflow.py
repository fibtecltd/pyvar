"""tests/test_liquidity_cashflow.py — cash-flow ladder and gap analysis tests."""

import numpy as np
import pytest

from engine.liquidity_cashflow import (
    cash_flow_ladder_1_year,
    cash_flow_ladder_30_day,
    funding_tenor_analysis,
    liquidity_gap_analysis,
)


def test_ladder_30_day_cumulative():
    inflows = np.full(30, 10.0)
    outflows = np.full(30, 8.0)
    r = cash_flow_ladder_30_day(inflows, outflows, opening_balance=5.0)
    # net 2/day, cumulative ends at 5 + 60 = 65
    assert r["cumulative_gap"][-1] == 65.0
    assert r["net_gap"][0] == 2.0


def test_ladder_30_day_min_day_shortfall():
    inflows = np.zeros(30)
    outflows = np.full(30, 1.0)
    r = cash_flow_ladder_30_day(inflows, outflows, opening_balance=0.0)
    assert r["min_cumulative"] == -30.0
    assert r["min_day"] == 29


def test_ladder_30_day_wrong_length_raises():
    with pytest.raises(ValueError):
        cash_flow_ladder_30_day(np.zeros(10), np.zeros(10))


def test_ladder_1_year_buckets():
    inflows = np.array([10.0, 5.0, 0, 0, 0, 0, 0, 0])
    outflows = np.array([2.0, 3.0, 0, 0, 0, 0, 0, 0])
    r = cash_flow_ladder_1_year(inflows, outflows)
    assert len(r["buckets"]) == 8
    assert r["cumulative_gap"][-1] == 10.0  # (10-2)+(5-3)=10


def test_ladder_1_year_length_mismatch_raises():
    with pytest.raises(ValueError):
        cash_flow_ladder_1_year(np.zeros(8), np.zeros(7))


def test_gap_analysis_periodic_and_cumulative():
    assets = np.array([100.0, 50.0, 0, 0, 0, 0, 0, 0])
    liab = np.array([60.0, 80.0, 0, 0, 0, 0, 0, 0])
    r = liquidity_gap_analysis(assets, liab)
    assert r["periodic_gap"][0] == 40.0
    assert r["periodic_gap"][1] == -30.0
    assert r["cumulative_gap"][1] == 10.0


def test_gap_analysis_ratio():
    assets = np.array([100.0] + [0.0] * 7)
    liab = np.array([50.0] + [0.0] * 7)
    r = liquidity_gap_analysis(assets, liab)
    assert r["gap_ratio"][0] == 2.0
    assert r["gap_ratio"][1] is None  # 0 liabilities


def test_funding_tenor_weighted_avg():
    r = funding_tenor_analysis(np.array([100.0, 100.0]), np.array([30.0, 90.0]))
    assert r["weighted_avg_tenor_days"] == 60.0
    assert r["short_term_ratio"] == 1.0  # both <= 90


def test_funding_tenor_short_term_ratio():
    r = funding_tenor_analysis(np.array([100.0, 100.0]), np.array([30.0, 365.0]))
    assert r["short_term_ratio"] == 0.5


def test_funding_tenor_zero_total_raises():
    with pytest.raises(ValueError):
        funding_tenor_analysis(np.array([0.0]), np.array([30.0]))


def test_funding_tenor_negative_raises():
    with pytest.raises(ValueError):
        funding_tenor_analysis(np.array([10.0]), np.array([-1.0]))


def test_ladder_30_day_deterministic():
    inflows = np.arange(30, dtype=float)
    outflows = np.arange(30, dtype=float) * 0.5
    r1 = cash_flow_ladder_30_day(inflows, outflows)
    r2 = cash_flow_ladder_30_day(inflows, outflows)
    assert r1["cumulative_gap"] == r2["cumulative_gap"]

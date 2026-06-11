"""tests/test_oprisk_kri.py — KRI library, breach detection, trend tests."""

import numpy as np
import pytest

from engine.oprisk_kri import (
    key_risk_indicator_kri_library,
    kri_threshold_breach_detection,
    kri_trend_analysis,
)


def test_kri_library_registry():
    defs = [
        {"name": "failed_trades", "amber_threshold": 5, "red_threshold": 10, "direction": "higher_breach"},
        {"name": "staffing", "amber_threshold": 0.9, "red_threshold": 0.8, "direction": "lower_breach"},
    ]
    r = key_risk_indicator_kri_library(defs)
    assert r["num_kris"] == 2
    assert "failed_trades" in r["registry"]


def test_kri_library_missing_key_raises():
    with pytest.raises(ValueError):
        key_risk_indicator_kri_library([{"name": "x"}])


def test_kri_library_empty_raises():
    with pytest.raises(ValueError):
        key_risk_indicator_kri_library([])


def test_breach_higher_red():
    r = kri_threshold_breach_detection(12, 5, 10, "higher_breach")
    assert r["status"] == "red"
    assert r["breached"] is True


def test_breach_higher_amber_green():
    assert kri_threshold_breach_detection(7, 5, 10, "higher_breach")["status"] == "amber"
    assert kri_threshold_breach_detection(3, 5, 10, "higher_breach")["status"] == "green"


def test_breach_lower_direction():
    # staffing below red threshold 0.8 -> red
    r = kri_threshold_breach_detection(0.75, 0.9, 0.8, "lower_breach")
    assert r["status"] == "red"
    assert kri_threshold_breach_detection(0.95, 0.9, 0.8, "lower_breach")["status"] == "green"


def test_breach_inconsistent_thresholds_raises():
    with pytest.raises(ValueError):
        kri_threshold_breach_detection(5, 10, 5, "higher_breach")


def test_breach_invalid_direction_raises():
    with pytest.raises(ValueError):
        kri_threshold_breach_detection(5, 5, 10, "sideways")


def test_trend_deteriorating():
    r = kri_trend_analysis(np.array([1.0, 2.0, 3.0, 4.0, 5.0]), higher_is_worse=True)
    assert r["slope"] > 0
    assert r["trend"] == "deteriorating"


def test_trend_improving_when_lower_worse():
    r = kri_trend_analysis(np.array([5.0, 4.0, 3.0, 2.0, 1.0]), higher_is_worse=True)
    assert r["trend"] == "improving"


def test_trend_stable():
    r = kri_trend_analysis(np.array([10.0, 10.0, 10.0, 10.0]))
    assert r["trend"] == "stable"


def test_trend_too_few_obs_raises():
    with pytest.raises(ValueError):
        kri_trend_analysis(np.array([1.0]))

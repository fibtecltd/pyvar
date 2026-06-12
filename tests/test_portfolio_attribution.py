"""tests/test_portfolio_attribution.py — numerical-correctness tests.

No mocking (CLAUDE.md §5 RULE 1). Tests assert Brinson reconciliation (effects
sum to active return), factor + specific reconciliation, currency split
reconciliation, and exposure aggregation.
"""

import numpy as np
import pytest

from engine.portfolio_attribution import (
    currency_attribution,
    factor_exposure_analysis_barra,
    factor_return_attribution,
    gics_sector_exposure,
    return_attribution_brinson,
    sector_attribution,
)

# ── Brinson ───────────────────────────────────────────────────────────────────


def test_brinson_effects_reconcile_to_active_return():
    wp = np.array([0.5, 0.3, 0.2])
    wb = np.array([0.4, 0.4, 0.2])
    rp = np.array([0.02, 0.01, -0.01])
    rb = np.array([0.015, 0.012, -0.005])
    r = return_attribution_brinson(wp, wb, rp, rb)
    total = r["total_allocation"] + r["total_selection"] + r["total_interaction"]
    assert abs(total - r["active_return"]) < 1e-10


def test_brinson_zero_active_when_identical():
    w = np.array([0.5, 0.5])
    ret = np.array([0.01, 0.02])
    r = return_attribution_brinson(w, w, ret, ret)
    assert abs(r["active_return"]) < 1e-12


def test_brinson_length_mismatch_raises():
    with pytest.raises(ValueError):
        return_attribution_brinson(
            np.array([0.5]), np.array([0.5, 0.5]), np.array([0.01]), np.array([0.01])
        )


# ── Factor return attribution ─────────────────────────────────────────────────


def test_factor_attribution_reconciles():
    b = np.array([1.0, 0.5, -0.3])
    fr = np.array([0.02, 0.01, 0.03])
    r = factor_return_attribution(b, fr, specific_return=0.004)
    assert abs(r["total_return"] - (r["factor_total"] + 0.004)) < 1e-12
    assert abs(r["factor_total"] - float(b @ fr)) < 1e-12


# ── Sector attribution ────────────────────────────────────────────────────────


def test_sector_attribution_total_effect():
    wp = np.array([0.6, 0.4])
    wb = np.array([0.5, 0.5])
    rp = np.array([0.03, 0.01])
    rb = np.array([0.02, 0.015])
    r = sector_attribution(wp, wb, rp, rb, sector_names=["Tech", "Energy"])
    te = sum(r["total_effect"].values())
    assert abs(te - r["active_return"]) < 1e-10


# ── Currency attribution ──────────────────────────────────────────────────────


def test_currency_attribution_reconciles():
    lr = np.array([0.02, 0.01])
    fx = np.array([0.005, -0.003])
    w = np.array([0.6, 0.4])
    r = currency_attribution(lr, fx, w)
    base = (1.0 + lr) * (1.0 + fx) - 1.0
    expected_total = float(np.sum(w * base))
    assert abs(r["total_return"] - expected_total) < 1e-10


# ── GICS sector exposure ──────────────────────────────────────────────────────


def test_gics_sector_exposure_aggregates():
    w = np.array([0.3, 0.2, 0.5])
    codes = ["Tech", "Tech", "Energy"]
    r = gics_sector_exposure(w, codes)
    assert abs(r["sector_exposure"]["Tech"] - 0.5) < 1e-12
    assert abs(r["sector_exposure"]["Energy"] - 0.5) < 1e-12
    assert r["largest_sector"] in ("Tech", "Energy")


def test_gics_sector_exposure_length_mismatch_raises():
    with pytest.raises(ValueError):
        gics_sector_exposure(np.array([0.5, 0.5]), ["Tech"])


# ── Barra factor exposure ─────────────────────────────────────────────────────


def test_barra_exposure_aggregation():
    b = np.array([[1.0, 0.0], [0.0, 2.0]])
    w = np.array([0.5, 0.5])
    r = factor_exposure_analysis_barra(b, w, factor_names=["value", "momentum"])
    assert abs(r["factor_exposures"]["value"] - 0.5) < 1e-12
    assert abs(r["factor_exposures"]["momentum"] - 1.0) < 1e-12
    assert r["dominant_factor"] == "momentum"

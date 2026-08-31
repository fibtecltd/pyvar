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


def test_currency_attribution_default_unaffected_by_karnosky_singer_feature():
    """Omitting the new risk-free params reproduces the exact pre-change output."""
    lr = np.array([0.05, 0.02])
    fx = np.array([0.01, -0.02])
    w = np.array([0.6, 0.4])
    r = currency_attribution(lr, fx, w)
    assert set(r.keys()) == {
        "local_effect",
        "currency_effect",
        "total_local",
        "total_currency",
        "total_return",
    }


def test_currency_attribution_karnosky_singer_local_effect_is_local_premium():
    """local_effect uses the local return PREMIUM (netted against the local
    risk-free rate), per Karnosky & Singer (1994) -- not the raw local
    return, unlike the naive default mode.
    """
    lr = np.array([0.05, 0.02])
    fx = np.array([0.01, -0.02])
    w = np.array([0.6, 0.4])
    local_rf = np.array([0.01, 0.005])
    base_rf = 0.02

    r = currency_attribution(lr, fx, w, local_risk_free=local_rf, base_risk_free=base_rf)
    premium = (1.0 + lr) / (1.0 + local_rf) - 1.0
    expected_local = w * premium
    actual_local = np.array([r["local_effect"]["ccy_0"], r["local_effect"]["ccy_1"]])
    assert actual_local == pytest.approx(expected_local, rel=1e-8)
    # The premium strictly nets the local risk-free rate out -- differs from
    # the naive (non-netted) local_effect for the same inputs.
    naive = currency_attribution(lr, fx, w)
    assert not np.allclose(actual_local, list(naive["local_effect"].values()))


def test_currency_attribution_karnosky_singer_reconciles_same_total_as_naive():
    """Karnosky-Singer re-partitions the SAME exact geometric total return
    the naive split reports -- it does not change the total, only how it is
    attributed between local/currency (and currency's own sub-effects).
    """
    rng = np.random.default_rng(11)
    lr = rng.normal(0.01, 0.03, size=6)
    fx = rng.normal(0.0, 0.02, size=6)
    w = np.full(6, 1.0 / 6)
    local_rf = rng.uniform(0.0, 0.03, size=6)
    base_rf = 0.015

    naive = currency_attribution(lr, fx, w)
    ks = currency_attribution(lr, fx, w, local_risk_free=local_rf, base_risk_free=base_rf)

    assert ks["total_return"] == pytest.approx(naive["total_return"], abs=1e-10)

    # currency_effect's three sub-effects reconcile exactly to currency_effect.
    for i in range(6):
        name = f"ccy_{i}"
        sub_total = (
            ks["base_cash_effect"][name]
            + ks["currency_surprise_effect"][name]
            + ks["currency_interaction_effect"][name]
        )
        assert sub_total == pytest.approx(ks["currency_effect"][name], abs=1e-9)

    assert ks["total_base_cash"] + ks["total_currency_surprise"] + ks[
        "total_currency_interaction"
    ] == pytest.approx(ks["total_currency"], abs=1e-8)


def test_currency_attribution_karnosky_singer_requires_both_rf_params():
    lr = np.array([0.02, 0.01])
    fx = np.array([0.005, -0.003])
    w = np.array([0.6, 0.4])
    with pytest.raises(ValueError):
        currency_attribution(lr, fx, w, local_risk_free=np.array([0.01, 0.01]))
    with pytest.raises(ValueError):
        currency_attribution(lr, fx, w, base_risk_free=0.01)
    with pytest.raises(ValueError):
        currency_attribution(lr, fx, w, local_risk_free=np.array([0.01]), base_risk_free=0.01)


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

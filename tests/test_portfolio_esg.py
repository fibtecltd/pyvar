"""tests/test_portfolio_esg.py — numerical-correctness tests for ESG analytics.

No mocking (CLAUDE.md §5 RULE 1). Tests assert no-trade band suppression,
turnover/cost non-negativity, ESG weighted-score correctness and constraint
satisfaction, and carbon emissions reconciliation.
"""

import numpy as np
import pytest

from engine.portfolio_esg import (
    carbon_footprint_attribution,
    esg_score_integration,
    rebalancing_optimiser,
)

# ── Rebalancing optimiser ─────────────────────────────────────────────────────


def test_rebalancing_no_trade_band_suppresses_small():
    cur = np.array([0.50, 0.30, 0.20])
    tgt = np.array([0.51, 0.29, 0.20])  # drifts of 0.01
    cost = np.array([10.0, 10.0, 10.0])
    r = rebalancing_optimiser(cur, tgt, cost, no_trade_band=0.02)
    assert all(t == 0.0 for t in r["trades"])  # all within band
    assert r["total_cost"] == 0.0


def test_rebalancing_trades_and_cost_positive():
    cur = np.array([0.6, 0.4])
    tgt = np.array([0.4, 0.6])
    cost = np.array([20.0, 20.0])
    r = rebalancing_optimiser(cur, tgt, cost)
    assert r["turnover"] > 0
    assert r["total_cost"] > 0


def test_rebalancing_length_mismatch_raises():
    with pytest.raises(ValueError):
        rebalancing_optimiser(np.array([0.5, 0.5]), np.array([1.0]), np.array([10.0]))


def test_rebalancing_derived_band_matches_closed_form():
    """asset_volatility + risk_aversion derives h_i = (0.75*c*sigma^2*w*(1-w)^2/gamma)^(1/3)."""
    cur = np.array([0.5, 0.3, 0.2])
    tgt = np.array([0.55, 0.25, 0.20])
    cost = np.array([10.0, 15.0, 5.0])
    vol = np.array([0.02, 0.03, 0.01])
    gamma = 4.0

    r = rebalancing_optimiser(cur, tgt, cost, asset_volatility=vol, risk_aversion=gamma)
    cost_frac = cost / 1e4
    weight_term = tgt * (1.0 - tgt) ** 2
    expected_band = np.cbrt(0.75 * cost_frac * vol**2 * weight_term / gamma)
    # Engine rounds to 8dp for JSON-friendliness; tolerance accounts for that.
    assert np.array(r["derived_no_trade_band"]) == pytest.approx(expected_band, abs=5e-9)

    # Trades below the derived band must be suppressed, exactly as the
    # scalar-band branch suppresses trades below no_trade_band.
    trades_raw = tgt - cur
    expected_trades = np.where(np.abs(trades_raw) < expected_band, 0.0, trades_raw)
    assert np.array(r["trades"]) == pytest.approx(expected_trades, abs=1e-10)


def test_rebalancing_derived_band_requires_both_params():
    cur = np.array([0.5, 0.5])
    tgt = np.array([0.55, 0.45])
    cost = np.array([10.0, 10.0])
    with pytest.raises(ValueError):
        rebalancing_optimiser(cur, tgt, cost, asset_volatility=np.array([0.02, 0.02]))
    with pytest.raises(ValueError):
        rebalancing_optimiser(cur, tgt, cost, risk_aversion=4.0)
    with pytest.raises(ValueError):
        rebalancing_optimiser(
            cur, tgt, cost, asset_volatility=np.array([0.02, 0.02]), risk_aversion=0.0
        )


def test_rebalancing_default_unaffected_by_derived_band_feature():
    """Omitting the new params reproduces the exact pre-change scalar-band output."""
    cur = np.array([0.5, 0.3, 0.2])
    tgt = np.array([0.45, 0.31, 0.24])
    cost = np.array([10.0, 10.0, 10.0])
    r = rebalancing_optimiser(cur, tgt, cost, no_trade_band=0.02)
    assert "derived_no_trade_band" not in r
    trades = np.array(r["trades"])
    assert trades[1] == 0.0
    assert trades[0] != 0.0 and trades[2] != 0.0


# ── ESG score integration ─────────────────────────────────────────────────────


def test_esg_weighted_score():
    w = np.array([0.5, 0.5])
    esg = np.array([60.0, 80.0])
    r = esg_score_integration(w, esg)
    assert abs(r["portfolio_esg_score"] - 70.0) < 1e-9


def test_esg_constrained_meets_floor():
    rng = np.random.default_rng(2)
    n = 4
    a = rng.normal(0, 1, size=(n, n))
    cov = (a @ a.T) / 100.0 + np.eye(n) * 0.001
    esg = np.array([40.0, 90.0, 55.0, 70.0])
    w = np.full(n, 0.25)
    r = esg_score_integration(w, esg, min_esg_score=75.0, cov_matrix=cov)
    if r["success"]:
        assert r["optimised_esg_score"] >= 75.0 - 1e-4


# ── Carbon footprint ──────────────────────────────────────────────────────────


def test_carbon_emissions_reconcile():
    w = np.array([0.5, 0.3, 0.2])
    ci = np.array([100.0, 200.0, 50.0])
    pv = 10.0
    r = carbon_footprint_attribution(w, ci, pv)
    assert abs(sum(r["contributions"].values()) - r["total_financed_emissions"]) < 1e-6


def test_carbon_waci_correct():
    w = np.array([0.5, 0.5])
    ci = np.array([100.0, 300.0])
    r = carbon_footprint_attribution(w, ci, 1.0)
    assert abs(r["waci"] - 200.0) < 1e-9


def test_carbon_default_unaffected_by_pcaf_feature():
    """Omitting the new PCAF params keeps the same total_financed_emissions
    formula (revenue-intensity x invested-value) as before."""
    w = np.array([0.5, 0.3, 0.2])
    ci = np.array([100.0, 200.0, 50.0])
    pv = 10.0
    r = carbon_footprint_attribution(w, ci, pv)
    assert r["method"] == "revenue_intensity"
    expected = w * pv * ci
    assert sum(r["contributions"].values()) == pytest.approx(float(expected.sum()), abs=1e-6)
    assert "ownership_share" not in r


def test_carbon_pcaf_ownership_share_matches_formula():
    w = np.array([0.5, 0.3, 0.2])
    ci = np.array([100.0, 200.0, 50.0])
    pv = 10.0  # $M
    company_emissions = np.array([50000.0, 120000.0, 8000.0])  # tCO2e, absolute
    company_value = np.array([200.0, 60.0, 40.0])  # $M EVIC/market cap

    r = carbon_footprint_attribution(
        w, ci, pv, company_total_emissions=company_emissions, company_value=company_value
    )
    assert r["method"] == "pcaf_ownership_share"
    invested = w * pv
    expected_share = invested / company_value
    expected_emissions = expected_share * company_emissions
    for i, name in enumerate(["asset_0", "asset_1", "asset_2"]):
        assert r["ownership_share"][name] == pytest.approx(expected_share[i], rel=1e-8)
        assert r["contributions"][name] == pytest.approx(expected_emissions[i], abs=1e-6)
    assert r["total_financed_emissions"] == pytest.approx(float(expected_emissions.sum()), abs=1e-6)
    # WACI leg is unchanged by the mode (still uses carbon_intensities).
    assert r["waci"] == pytest.approx(float(np.sum(w * ci)), rel=1e-8)


def test_carbon_pcaf_ownership_share_never_exceeds_company_total():
    """PCAF sanity check: split a single company's value across several
    investors whose combined invested amount does not exceed the company's
    total value -- their combined financed emissions must not exceed the
    company's own total emissions.
    """
    company_value = 100.0  # $M EVIC
    company_emissions = 40000.0  # tCO2e

    investor_stakes = [20.0, 35.0, 15.0]  # $M invested by 3 separate investors
    assert sum(investor_stakes) <= company_value

    total_financed = 0.0
    for stake in investor_stakes:
        w = np.array([1.0])
        pv = stake
        ci = np.array([999.0])  # irrelevant to the PCAF leg, only feeds WACI
        r = carbon_footprint_attribution(
            w,
            ci,
            pv,
            company_total_emissions=np.array([company_emissions]),
            company_value=np.array([company_value]),
        )
        total_financed += r["total_financed_emissions"]

    assert total_financed <= company_emissions + 1e-6
    # And it should be proportionally close given stakes sum to < company_value.
    expected = sum(investor_stakes) / company_value * company_emissions
    assert total_financed == pytest.approx(expected, rel=1e-6)


def test_carbon_pcaf_requires_both_params():
    w = np.array([0.5, 0.5])
    ci = np.array([100.0, 200.0])
    pv = 10.0
    with pytest.raises(ValueError):
        carbon_footprint_attribution(w, ci, pv, company_total_emissions=np.array([1.0, 2.0]))
    with pytest.raises(ValueError):
        carbon_footprint_attribution(w, ci, pv, company_value=np.array([1.0, 2.0]))
    with pytest.raises(ValueError):
        carbon_footprint_attribution(
            w,
            ci,
            pv,
            company_total_emissions=np.array([1.0, 2.0]),
            company_value=np.array([0.0, 2.0]),
        )

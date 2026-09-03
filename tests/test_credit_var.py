"""tests/test_credit_var.py — numerical-correctness tests for Credit VaR family.

No mocking of engine functions (CLAUDE.md §5 RULE 1). Verifies: CVaR >= VaR,
VaR >= EL, ES is the mean beyond VaR, determinism with fixed seed, MC converges
to the analytical Vasicek formula, Merton DD monotonicity, and HHI bounds.
"""

import numpy as np
import pytest
from scipy import stats

from engine.credit_var import (
    credit_concentration_risk_hhi,
    credit_var_analytical_vasicek,
    credit_var_monte_carlo,
    creditmetrics_portfolio_model,
    default_correlation_matrix,
    kmv_merton_distance_to_default,
)


def test_mc_credit_var_ordering_and_determinism():
    n = 100
    pd = np.full(n, 0.02)
    lgd = np.full(n, 0.45)
    ead = np.full(n, 1e6)
    a = credit_var_monte_carlo(pd, lgd, ead, 0.15, 0.999, n_simulations=20_000, seed=1)
    b = credit_var_monte_carlo(pd, lgd, ead, 0.15, 0.999, n_simulations=20_000, seed=1)
    assert a == b  # determinism
    assert a["cvar"] >= a["var"] >= a["el"] >= 0.0
    assert abs(a["ul"] - (a["var"] - a["el"])) < 1e-3


def test_mc_el_matches_pd_lgd_ead():
    n = 200
    pd = np.full(n, 0.03)
    lgd = np.full(n, 0.5)
    ead = np.full(n, 1.0)
    r = credit_var_monte_carlo(pd, lgd, ead, 0.10, 0.99, n_simulations=40_000, seed=7)
    expected_el = 0.03 * 0.5 * 1.0 * n
    assert abs(r["el"] - expected_el) / expected_el < 0.05


def test_mc_converges_to_vasicek_for_large_homogeneous():
    # Large homogeneous portfolio MC VaR should approach analytical Vasicek.
    n = 1500
    pd_val, lgd_val, rho = 0.02, 0.45, 0.15
    mc = credit_var_monte_carlo(
        np.full(n, pd_val),
        np.full(n, lgd_val),
        np.full(n, 1.0 / n),
        rho,
        0.99,
        n_simulations=40_000,
        seed=11,
    )
    ana = credit_var_analytical_vasicek(pd_val, lgd_val, 1.0, rho, 0.99)
    assert abs(mc["var"] - ana["var"]) < 0.02  # loss-rate units


def test_vasicek_var_ge_el_and_monotone_confidence():
    low = credit_var_analytical_vasicek(0.02, 0.45, 1e6, 0.15, 0.95)
    high = credit_var_analytical_vasicek(0.02, 0.45, 1e6, 0.15, 0.999)
    assert high["var"] > low["var"] >= low["el"]


def test_vasicek_zero_correlation_equals_el_scaled():
    # With rho=0 the conditional default rate equals PD, so VaR == EL.
    r = credit_var_analytical_vasicek(0.05, 0.6, 1000.0, 0.0, 0.999)
    assert abs(r["var"] - r["el"]) < 1e-6


def test_creditmetrics_matches_mc_engine():
    n = 50
    r = creditmetrics_portfolio_model(
        np.full(n, 1e5),
        np.full(n, 0.02),
        np.full(n, 0.45),
        0.2,
        0.99,
        n_simulations=10_000,
        seed=3,
    )
    assert r["cvar"] >= r["var"] >= r["el"] >= 0.0


# ── multi-state CreditMetrics (caveat-triage batch 1) ────────────────────────
# docs/p11-caveat-triage-plan.md: this function was a pure pass-through to
# credit_var_monte_carlo, not a real multi-state model. transition_matrix /
# current_rating / state_loss_pct add a genuine one (Gupton, Finger & Bhatia
# 1997's asset-return discretisation). Default (all three omitted) must stay
# the exact same pass-through as before.


def test_creditmetrics_default_mode_unchanged_key_set():
    n = 20
    r = creditmetrics_portfolio_model(
        np.full(n, 1e5), np.full(n, 0.02), np.full(n, 0.45), 0.2, 0.99, n_simulations=5_000, seed=1
    )
    assert set(r) == {"var", "cvar", "el", "ul", "loss_std", "confidence_level", "n_simulations"}


def test_creditmetrics_multistate_reduces_exactly_to_binary_model():
    """The strongest possible cross-check: construct a multi-state transition
    matrix where each obligor has its OWN rating (a self-transition state
    with 0% loss, plus the shared default state at its own pd) -- this is
    mathematically the identical model as the two-state pass-through, so the
    two code paths must produce BIT-FOR-BIT identical results given the same
    seed (both draw the same systematic/idiosyncratic arrays in the same
    order), not just "close" numbers.
    """
    rng = np.random.default_rng(0)
    n = 25
    pd = rng.uniform(0.01, 0.08, n)
    lgd = rng.uniform(0.3, 0.6, n)
    exposures = rng.uniform(1e5, 1e6, n)
    rho, seed, cl, n_sims = 0.20, 777, 0.99, 20_000

    binary = credit_var_monte_carlo(
        pd=pd,
        lgd=lgd,
        ead=exposures,
        asset_correlation=rho,
        confidence_level=cl,
        n_simulations=n_sims,
        seed=seed,
    )

    n_states = n + 1  # one rating per obligor + the shared default state
    tm = np.zeros((n_states, n_states))
    for i in range(n):
        tm[i, i] = 1.0 - pd[i]
        tm[i, -1] = pd[i]
    tm[-1, -1] = 1.0  # default row must still be row-stochastic
    current_rating = np.arange(n)
    state_loss_pct = np.zeros(n)  # surviving in one's own rating = 0 loss

    multi = creditmetrics_portfolio_model(
        exposures=exposures,
        pd=pd,
        lgd=lgd,
        asset_correlation=rho,
        confidence_level=cl,
        n_simulations=n_sims,
        seed=seed,
        transition_matrix=tm,
        current_rating=current_rating,
        state_loss_pct=state_loss_pct,
    )
    assert multi == binary


def test_creditmetrics_multistate_pd_overrides_transition_matrix_default_probability():
    """pd must OVERRIDE transition_matrix's own default probability, not be
    silently ignored in favour of it. Uses a deliberately WRONG, uniform 0.5
    default probability in a 2-state matrix (unrelated to the much smaller
    per-obligor pd values) -- with n_states=2 the override fully replaces
    the matrix's default column, so if pd correctly drives the threshold,
    results must be bit-for-bit identical to credit_var_monte_carlo (which
    computes the threshold purely from pd). Before the fix this test would
    fail: the multi-state path would instead reflect the wrong 0.5 default
    probability baked into the matrix.
    """
    rng = np.random.default_rng(1)
    n = 20
    pd = rng.uniform(0.01, 0.08, n)  # far from the matrix's 0.5
    lgd = rng.uniform(0.3, 0.6, n)
    exposures = rng.uniform(1e5, 1e6, n)
    rho, seed, cl, n_sims = 0.20, 999, 0.99, 20_000

    binary = credit_var_monte_carlo(
        pd=pd,
        lgd=lgd,
        ead=exposures,
        asset_correlation=rho,
        confidence_level=cl,
        n_simulations=n_sims,
        seed=seed,
    )

    tm = np.array([[0.5, 0.5], [0.0, 1.0]])  # row 0's default prob (0.5) is a decoy
    current_rating = np.zeros(n, dtype=np.int64)
    state_loss_pct = np.array([0.0])  # surviving = 0 loss, matches binary model

    multi = creditmetrics_portfolio_model(
        exposures=exposures,
        pd=pd,
        lgd=lgd,
        asset_correlation=rho,
        confidence_level=cl,
        n_simulations=n_sims,
        seed=seed,
        transition_matrix=tm,
        current_rating=current_rating,
        state_loss_pct=state_loss_pct,
    )
    assert multi == binary


def test_creditmetrics_multistate_worse_transition_matrix_raises_el():
    n = 30
    pd = np.full(n, 0.02)
    lgd = np.full(n, 0.45)
    exposures = np.full(n, 1e5)
    current_rating = np.zeros(n, dtype=np.int64)
    kwargs = dict(
        exposures=exposures,
        pd=pd,
        lgd=lgd,
        asset_correlation=0.20,
        confidence_level=0.99,
        n_simulations=15_000,
        seed=5,
        current_rating=current_rating,
    )

    # 3 states: 0 = current rating, 1 = downgraded (25% loss), 2 = default.
    # "mild": mostly stays put; "severe": much more likely to downgrade.
    tm_mild = np.array([[0.97, 0.01, 0.02], [0.0, 0.98, 0.02], [0.0, 0.0, 1.0]])
    tm_severe = np.array([[0.70, 0.28, 0.02], [0.0, 0.98, 0.02], [0.0, 0.0, 1.0]])
    state_loss_pct = np.array([0.0, 0.25])

    mild = creditmetrics_portfolio_model(
        transition_matrix=tm_mild, state_loss_pct=state_loss_pct, **kwargs
    )
    severe = creditmetrics_portfolio_model(
        transition_matrix=tm_severe, state_loss_pct=state_loss_pct, **kwargs
    )
    assert severe["el"] > mild["el"]
    assert severe["var"] >= mild["var"]


def test_creditmetrics_multistate_partial_args_raises():
    n = 5
    kwargs = dict(exposures=np.full(n, 1e5), pd=np.full(n, 0.02), lgd=np.full(n, 0.45))
    with pytest.raises(ValueError):
        creditmetrics_portfolio_model(**kwargs, transition_matrix=np.eye(2))
    with pytest.raises(ValueError):
        creditmetrics_portfolio_model(**kwargs, current_rating=np.zeros(n, dtype=np.int64))


def test_creditmetrics_multistate_validates_shapes_and_ranges():
    n = 5
    kwargs = dict(exposures=np.full(n, 1e5), pd=np.full(n, 0.02), lgd=np.full(n, 0.45))
    current_rating = np.zeros(n, dtype=np.int64)

    # non-square transition matrix
    with pytest.raises(ValueError):
        creditmetrics_portfolio_model(
            **kwargs,
            transition_matrix=np.ones((2, 3)),
            current_rating=current_rating,
            state_loss_pct=np.array([0.1]),
        )
    # rows don't sum to 1
    with pytest.raises(ValueError):
        creditmetrics_portfolio_model(
            **kwargs,
            transition_matrix=np.array([[0.5, 0.4], [0.0, 1.0]]),
            current_rating=current_rating,
            state_loss_pct=np.array([0.1]),
        )
    # entry out of [0, 1] (offset by a compensating entry so the row still
    # sums to 1 -- must be caught by an explicit entry-range check, not just
    # the row-sum check).
    with pytest.raises(ValueError):
        creditmetrics_portfolio_model(
            **kwargs,
            transition_matrix=np.array([[-0.1, 1.1], [0.0, 1.0]]),
            current_rating=current_rating,
            state_loss_pct=np.array([0.1]),
        )
    # current_rating pointing at the default state itself
    with pytest.raises(ValueError):
        creditmetrics_portfolio_model(
            **kwargs,
            transition_matrix=np.array([[0.9, 0.1], [0.0, 1.0]]),
            current_rating=np.ones(n, dtype=np.int64),
            state_loss_pct=np.array([0.1]),
        )
    # state_loss_pct wrong length
    with pytest.raises(ValueError):
        creditmetrics_portfolio_model(
            **kwargs,
            transition_matrix=np.array([[0.9, 0.1], [0.0, 1.0]]),
            current_rating=current_rating,
            state_loss_pct=np.array([0.1, 0.2]),
        )
    # state_loss_pct out of [0, 1]
    with pytest.raises(ValueError):
        creditmetrics_portfolio_model(
            **kwargs,
            transition_matrix=np.array([[0.9, 0.1], [0.0, 1.0]]),
            current_rating=current_rating,
            state_loss_pct=np.array([1.5]),
        )


def test_merton_dd_increases_pd_decreases_with_assets():
    low_assets = kmv_merton_distance_to_default(110.0, 100.0, 0.3)
    high_assets = kmv_merton_distance_to_default(200.0, 100.0, 0.3)
    assert high_assets["distance_to_default"] > low_assets["distance_to_default"]
    assert high_assets["pd"] < low_assets["pd"]


def test_merton_pd_equals_normal_cdf_neg_dd():
    r = kmv_merton_distance_to_default(150.0, 100.0, 0.25, risk_free_rate=0.03)
    assert abs(r["pd"] - stats.norm.cdf(-r["distance_to_default"])) < 1e-9


def test_default_correlation_lt_asset_correlation():
    # Default correlation is always smaller in magnitude than asset correlation.
    pd = np.array([0.02, 0.02])
    a = np.array([[1.0, 0.3], [0.3, 1.0]])
    r = default_correlation_matrix(pd, a)
    assert 0.0 < r["matrix"][0][1] < 0.3
    assert r["matrix"][0][0] == 1.0


def test_hhi_single_name_is_one():
    r = credit_concentration_risk_hhi(np.array([100.0]))
    assert abs(r["hhi"] - 1.0) < 1e-12
    assert abs(r["effective_n"] - 1.0) < 1e-9


def test_hhi_granular_approaches_one_over_n():
    n = 10
    r = credit_concentration_risk_hhi(np.full(n, 5.0))
    assert abs(r["hhi"] - 1.0 / n) < 1e-12
    assert abs(r["effective_n"] - n) < 1e-9


def test_hhi_rejects_zero_total():
    with pytest.raises(ValueError):
        credit_concentration_risk_hhi(np.array([0.0, 0.0]))

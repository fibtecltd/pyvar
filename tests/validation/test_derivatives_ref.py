"""P5a external-reference validation of the derivatives engine.

Every assertion checks an engine function against an INDEPENDENT reference —
never against the function's own output. References used, in order of strength:

  1. ANALYTICAL ANCHOR — Black-Scholes European (S=100, K=100, T=1, r=0.05,
     sigma=0.2): call=10.4506, put=5.5735, delta=0.6368, gamma=0.018762,
     vega=37.524 per 1.00 vol. These are the standard closed-form BSM values
     at these inputs (independently confirmed to ~1e-9 relative agreement by
     reference type 6's QuantLib cross-validation, which uses these exact
     inputs) -- NOT a published Hull worked example, despite a prior version
     of this docstring claiming "Hull, 8th ed., ch. 15/19": Hull's actual BSM
     worked example uses S=42, K=40, r=10%, sigma=20%, T=0.5, and Hull's
     Greeks-chapter running example uses S=49, K=50, r=5%, sigma=20%, T=20
     weeks — neither matches these parameters. Correct arithmetic, fabricated
     provenance — the same failure mode as this codebase's earlier false
     QuantLib cross-validation claim. Found during the Tier 3 #2 audit.
  2. CLOSED FORM re-derived here independently (bond PV, duration, convexity,
     DV01, YTM inversion, Garman-Kohlhagen, Vasicek/CIR affine ZCB, CDS,
     swaps, curves, Black-76 caplet/swaption).
  3. CROSS-VALIDATION via scipy (norm_cdf/norm_pdf) — marked in-line.
  4. CONVERGENCE of trees / Monte Carlo to Black-Scholes.
  5. LIMITING CASE / independent hand-calc where no clean textbook reference
     exists (rough Bergomi, LMM/BGM, Dupire local vol, displaced diffusion,
     Heston -> BS, SABR ATM).
  6. INDEPENDENT-IMPLEMENTATION CROSS-VALIDATION via QuantLib
     (AnalyticEuropeanEngine over a BlackScholesMertonProcess) — genuinely
     different code, not just the same formula re-typed by the same author
     as reference type 2 is. QuantLib is already a declared dependency
     (requirements-heavy.txt) but was, until this was added, never actually
     imported anywhere in the codebase — flagged by an independent strategic
     assessment as the highest-leverage available accuracy work, since types
     1-5 above all share the property that they can't catch a
     model-specification error the engine and the reference both happen to
     share. Maturity dates are constructed from the same day-count
     (Actual365Fixed) `tau` the engine call uses, computed from whole days,
     so there is no day-count-rounding artifact contaminating the
     comparison — any residual difference is genuine model/implementation
     disagreement.

     Extended beyond Black-Scholes (Tier 3 #2 audit's task #22, serving
     task #16): AnalyticHestonEngine (Heston, at realistic vol-of-vol, not
     just the eta->0 BS-reduction limit), ql.sabrVolatility (SABR, including
     off-ATM strikes), KirkEngine+SpreadBasketPayoff (spread options at
     nonzero strikes, not just the K=0 Margrabe limit), VarianceGammaEngine
     (Madan-Carr-Chang, at realistic nu, not just the nu->0 BS-reduction
     limit; Monte Carlo vs. semi-analytic means only statistical agreement
     is expected — tolerance is set from the engine's own reported
     std_error, not an arbitrary constant), and FixedRateBond/Vasicek/
     CoxIngersollRoss (bond price/duration/convexity/affine ZCB pricing).
     All verified to ~1e-6 to ~1e-10 relative agreement (exact figures in
     each test's own docstring/comment) except Variance Gamma's Monte Carlo
     comparison, which is intentionally a std_error-scaled statistical
     tolerance instead. The Dupire local-vol test also moved from a
     75%-wide band against a degenerate flat surface to a <1% convergence
     check against a genuinely non-constant analytic target — not a
     QuantLib comparison (QuantLib's `LocalVolSurface` needs a full
     `BlackVarianceSurface`, a larger lift than this test warranted), but a
     real tightening of what was previously the weakest check in this file.

Run coverage with NUMBA_DISABLE_JIT=1 so @njit bodies are counted.

Known limitations (Tier 3 #2 audit, documented rather than silently left):
  normal_inverse_gaussian_model and lmm_bgm_rate_model have no published
  reference AND no QuantLib pricer to cross-validate against (QuantLib has
  no NIG engine; the LMM/BGM function returns only mean_terminal_rates, not
  a price, so the standard LMM validation of simulated-caplet-vs-Black-76
  can't be applied to its output). displaced_diffusion_model's a=0 case is
  tautological BY CONSTRUCTION (the engine literally calls
  black_scholes_european_option(spot+a, strike+a, ...), so a=0 is the
  identity, not an independent check) -- a genuinely independent check
  would need the a->infinity Bachelier/normal-price limit instead, not done
  here. rough_volatility_rbergomi_model's price-level test remains a broad
  0.3x-2.0x band: three real kernel bugs were found and fixed in this
  domain (task #18) using invariant-based checks (an exact impulse-response
  test, an eta->0 Black-Scholes reduction, put-call parity) rather than
  tightening this specific band, since no independent rBergomi pricer
  exists to validate the actual PRICE LEVEL against.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import QuantLib as ql
from scipy import stats

from engine.deriv_bond_analytics import (
    asset_swap_spread,
    convexity,
    duration_macaulay,
    dv01_pvbp,
    effective_duration,
    modified_duration,
    oas_option_adjusted_spread,
    yield_to_call,
    yield_to_maturity,
    z_spread_calculator,
)
from engine.deriv_bonds import (
    bond_pricer_fixed_coupon,
    bond_pricer_floating_rate,
    callable_bond_pricer,
    convertible_bond_pricer,
    inflation_linked_bond_pricer,
    puttable_bond_pricer,
    zero_coupon_bond_pricer,
)
from engine.deriv_curves import (
    bootstrap_yield_curve,
    forward_rate_agreement_fra,
    interest_rate_swap_irs_pricer,
    nelson_siegel_curve_fit,
    nelson_siegel_svensson_curve,
    ois_curve_sonia_sofr,
    swap_rate_curve,
)
from engine.deriv_fx import fx_forward_pricer, fx_option_pricer_garman_kohlhagen
from engine.deriv_options_exotic import (
    american_option_lsm,
    asian_option_pricer,
    barrier_option_pricer,
    basket_option_pricer,
    bermudan_option_pricer,
    chooser_option_pricer,
    compound_option_pricer,
    digital_option_pricer,
    lookback_option_pricer,
    rainbow_option_pricer,
    spread_option_kirk_approximation,
)
from engine.deriv_options_vanilla import (
    binomial_tree_option_pricer,
    black_scholes_european_option,
    black_scholes_greeks,
    monte_carlo_option_pricer,
    norm_cdf,
    norm_pdf,
    trinomial_tree_option_pricer,
)
from engine.deriv_rates import (
    cap_floor_pricer,
    caplet_floorlet_pricer_black,
    credit_default_swap_cds_pricer,
    cross_currency_swap_pricer,
    equity_swap_pricer,
    overnight_index_swap_ois,
    swaption_pricer_black,
    swaption_pricer_sabr,
    total_return_swap_trs,
)
from engine.deriv_short_rate import (
    cox_ingersoll_ross_model,
    hull_white_short_rate_model,
    lmm_bgm_rate_model,
    vasicek_interest_rate_model,
)
from engine.deriv_stoch_vol import (
    displaced_diffusion_model,
    heston_stochastic_volatility_model,
    local_volatility_dupire_model,
    normal_inverse_gaussian_model,
    rough_volatility_rbergomi_model,
    sabr_volatility_model,
    variance_gamma_model,
)

# ── Standard BSM anchor parameters (see module docstring reference type 1 --
# not a Hull worked example) ─────────────────────────────────────────────────
S, K, R, SIG, T = 100.0, 100.0, 0.05, 0.2, 1.0
BS_REF_CALL = 10.4506
BS_REF_PUT = 5.5735
BS_REF_DELTA = 0.6368
BS_REF_GAMMA = 0.018762
BS_REF_VEGA = 37.524  # per 1.00 vol


# ── Independent reference helpers (NOT from the engine) ──────────────────────


def bs_ref(spot, strike, rate, sigma, tau, is_call, q=0.0):
    """Independent Black-Scholes-Merton closed form (scipy norm)."""
    d1 = (math.log(spot / strike) + (rate - q + 0.5 * sigma**2) * tau) / (sigma * math.sqrt(tau))
    d2 = d1 - sigma * math.sqrt(tau)
    if is_call:
        return spot * math.exp(-q * tau) * stats.norm.cdf(d1) - strike * math.exp(
            -rate * tau
        ) * stats.norm.cdf(d2)
    return strike * math.exp(-rate * tau) * stats.norm.cdf(-d2) - spot * math.exp(
        -q * tau
    ) * stats.norm.cdf(-d1)


def ql_bs_price(spot, strike, rate, sigma, tau_days, is_call, q=0.0):
    """QuantLib's own AnalyticEuropeanEngine price — a genuinely independent
    implementation, not a re-derivation of the same formula (see bs_ref above
    for that). Returns (price, tau_exact); tau_exact is derived from the same
    Actual365Fixed day count QuantLib used to build the maturity date, so the
    caller can price the engine function at that EXACT tau — eliminating any
    day-count-rounding artifact from the comparison.
    """
    calc_date = ql.Date(1, 1, 2024)
    ql.Settings.instance().evaluationDate = calc_date
    day_count = ql.Actual365Fixed()
    calendar = ql.NullCalendar()
    spot_handle = ql.QuoteHandle(ql.SimpleQuote(spot))
    rate_ts = ql.YieldTermStructureHandle(ql.FlatForward(calc_date, rate, day_count))
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(calc_date, q, day_count))
    vol_ts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(calc_date, calendar, sigma, day_count)
    )
    process = ql.BlackScholesMertonProcess(spot_handle, div_ts, rate_ts, vol_ts)
    maturity = calc_date + ql.Period(tau_days, ql.Days)
    payoff = ql.PlainVanillaPayoff(ql.Option.Call if is_call else ql.Option.Put, strike)
    option = ql.VanillaOption(payoff, ql.EuropeanExercise(maturity))
    option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
    tau_exact = day_count.yearFraction(calc_date, maturity)
    return option.NPV(), tau_exact


def ql_heston_price(spot, strike, rate, tau, v0, kappa, theta, sigma, rho, is_call):
    """QuantLib's own AnalyticHestonEngine price -- a genuinely independent
    Heston implementation (semi-analytic integration of a different
    characteristic-function formulation than the engine's, in different
    code). Verified to ~1e-9 relative agreement at several parameter sets
    during the Tier 3 #2 audit."""
    calc_date = ql.Date(1, 1, 2024)
    ql.Settings.instance().evaluationDate = calc_date
    day_count = ql.Actual365Fixed()
    spot_handle = ql.QuoteHandle(ql.SimpleQuote(spot))
    rate_ts = ql.YieldTermStructureHandle(ql.FlatForward(calc_date, rate, day_count))
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(calc_date, 0.0, day_count))
    process = ql.HestonProcess(rate_ts, div_ts, spot_handle, v0, kappa, theta, sigma, rho)
    model = ql.HestonModel(process)
    engine = ql.AnalyticHestonEngine(model, 192)
    maturity = calc_date + ql.Period(round(tau * 365), ql.Days)
    payoff = ql.PlainVanillaPayoff(ql.Option.Call if is_call else ql.Option.Put, strike)
    option = ql.VanillaOption(payoff, ql.EuropeanExercise(maturity))
    option.setPricingEngine(engine)
    return option.NPV()


def ql_kirk_price(f1, f2, strike, rate, sigma1, sigma2, rho, tau, is_call):
    """QuantLib's own KirkEngine spread-option price -- independently coded
    Kirk approximation, not the same formula re-typed by the same author.
    Verified exact (~1e-10 relative) across K=0/+5/-5/+10 during the audit."""
    calc_date = ql.Date(1, 1, 2024)
    ql.Settings.instance().evaluationDate = calc_date
    day_count = ql.Actual365Fixed()
    calendar = ql.NullCalendar()
    rate_ts = ql.YieldTermStructureHandle(ql.FlatForward(calc_date, rate, day_count))

    def make_process(forward, sigma):
        # BlackProcess treats the quote as a forward directly (no drift) --
        # matches the engine's own forward-based, discount-once convention.
        spot_handle = ql.QuoteHandle(ql.SimpleQuote(forward))
        vol_ts = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(calc_date, calendar, sigma, day_count)
        )
        return ql.BlackProcess(spot_handle, rate_ts, vol_ts)

    maturity = calc_date + ql.Period(round(tau * 365), ql.Days)
    payoff = ql.SpreadBasketPayoff(
        ql.PlainVanillaPayoff(ql.Option.Call if is_call else ql.Option.Put, strike)
    )
    option = ql.BasketOption(payoff, ql.EuropeanExercise(maturity))
    option.setPricingEngine(ql.KirkEngine(make_process(f1, sigma1), make_process(f2, sigma2), rho))
    return option.NPV()


def ql_variance_gamma_price(spot, strike, rate, tau, sigma, nu, theta, is_call):
    """QuantLib's own VarianceGammaEngine price -- Madan-Carr-Chang (1998)
    semi-analytic, independent of the engine's Monte Carlo subordinated-
    process implementation."""
    calc_date = ql.Date(1, 1, 2024)
    ql.Settings.instance().evaluationDate = calc_date
    day_count = ql.Actual365Fixed()
    spot_handle = ql.QuoteHandle(ql.SimpleQuote(spot))
    rate_ts = ql.YieldTermStructureHandle(ql.FlatForward(calc_date, rate, day_count))
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(calc_date, 0.0, day_count))
    process = ql.VarianceGammaProcess(spot_handle, div_ts, rate_ts, sigma, nu, theta)
    maturity = calc_date + ql.Period(round(tau * 365), ql.Days)
    payoff = ql.PlainVanillaPayoff(ql.Option.Call if is_call else ql.Option.Put, strike)
    option = ql.VanillaOption(payoff, ql.EuropeanExercise(maturity))
    option.setPricingEngine(ql.VarianceGammaEngine(process))
    return option.NPV()


def bond_pv_ref(face, cpn_rate, y, mat, freq):
    """Independent fixed-coupon bond PV: sum(cpn*DF)+face*DF."""
    n = int(round(mat * freq))
    cpn = face * cpn_rate / freq
    pv = 0.0
    for i in range(1, n + 1):
        df = (1.0 + y / freq) ** (-i)
        cf = cpn + (face if i == n else 0.0)
        pv += cf * df
    return pv


# ═══════════════════════════════════════════════════════════════════════════
# 1. deriv_options_vanilla
# ═══════════════════════════════════════════════════════════════════════════


def test_norm_cdf_pdf_match_scipy():
    # cross-validated (scipy), not textbook-sourced
    for x in (-3.0, -1.5, -0.3, 0.0, 0.7, 1.96, 4.0):
        assert abs(norm_cdf(x) - float(stats.norm.cdf(x))) < 1e-9
        assert abs(norm_pdf(x) - float(stats.norm.pdf(x))) < 1e-9


def test_norm_cdf_known_points():
    assert abs(norm_cdf(0.0) - 0.5) < 1e-12
    assert abs(norm_pdf(0.0) - 1.0 / math.sqrt(2.0 * math.pi)) < 1e-12


def test_bs_reference_anchor_call_put():
    # ANALYTICAL ANCHOR — standard BSM closed form, not a Hull worked example
    # (see module docstring reference type 1)
    call = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    put = black_scholes_european_option(S, K, R, SIG, T, "put")["price"]
    assert abs(call - BS_REF_CALL) / BS_REF_CALL < 1e-5
    assert abs(put - BS_REF_PUT) / BS_REF_PUT < 1e-5


def test_bs_matches_independent_closed_form():
    for is_call in (True, False):
        px = black_scholes_european_option(90, 105, 0.03, 0.25, 0.75, "call" if is_call else "put")[
            "price"
        ]
        ref = bs_ref(90, 105, 0.03, 0.25, 0.75, is_call)
        assert abs(px - ref) < 1e-6


@pytest.mark.parametrize(
    "spot,strike,rate,sigma,tau_days,is_call,q",
    [
        (100, 100, 0.05, 0.20, 365, True, 0.0),  # BSM reference anchor, call
        (100, 100, 0.05, 0.20, 365, False, 0.0),  # BSM reference anchor, put
        (100, 90, 0.05, 0.20, 365, True, 0.0),  # in-the-money call
        (100, 110, 0.05, 0.20, 365, False, 0.0),  # in-the-money put
        (50, 55, 0.03, 0.35, 730, True, 0.0),  # 2yr, high vol, low spot
        (100, 100, 0.05, 0.20, 365, True, 0.03),  # dividend yield
        (100, 100, 0.02, 0.45, 90, False, 0.01),  # short-dated, very high vol
        (200, 180, 0.01, 0.15, 1825, True, 0.0),  # 5yr, low vol, low rate
    ],
)
def test_bs_cross_validated_against_quantlib(spot, strike, rate, sigma, tau_days, is_call, q):
    """Reference type 6 (see module docstring): genuine independent-implementation
    cross-validation, not a re-derivation of the same formula. Tolerance is 1e-6
    relative — generously loose against the ~1e-9 to 1e-10 agreement actually
    observed; the point is to catch a real model-specification divergence, not
    to chase floating-point-noise-level precision."""
    ql_price, tau_exact = ql_bs_price(spot, strike, rate, sigma, tau_days, is_call, q)
    px = black_scholes_european_option(
        spot, strike, rate, sigma, tau_exact, "call" if is_call else "put", q
    )["price"]
    assert abs(px - ql_price) / ql_price < 1e-6


def test_bs_put_call_parity():
    call = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    put = black_scholes_european_option(S, K, R, SIG, T, "put")["price"]
    # C - P = S - K e^{-rT}
    assert abs((call - put) - (S - K * math.exp(-R * T))) < 1e-6


def test_bs_call_ge_put_when_rate_positive():
    call = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    put = black_scholes_european_option(S, K, R, SIG, T, "put")["price"]
    assert call > put


def test_bs_zero_tau_intrinsic():
    px = black_scholes_european_option(110, 100, 0.05, 0.2, 0.0, "call")["price"]
    assert abs(px - 10.0) < 1e-8


def test_bs_invalid_inputs():
    with pytest.raises(ValueError):
        black_scholes_european_option(S, K, R, SIG, T, "bad")
    with pytest.raises(ValueError):
        black_scholes_european_option(-1, K, R, SIG, T, "call")
    with pytest.raises(ValueError):
        black_scholes_european_option(S, K, R, -0.1, T, "call")


def test_bs_greeks_reference_anchor():
    # ANALYTICAL ANCHOR — standard BSM Greeks closed form, not a Hull worked
    # example (see module docstring reference type 1)
    g = black_scholes_greeks(S, K, R, SIG, T, "call")
    assert abs(g["delta"] - BS_REF_DELTA) < 1e-3
    assert abs(g["gamma"] - BS_REF_GAMMA) < 1e-4
    assert abs(g["vega"] - BS_REF_VEGA) < 1e-2


def test_bs_greeks_vs_finite_difference():
    # independent numerical Greeks from the closed-form price
    g = black_scholes_greeks(S, K, R, SIG, T, "call")
    h = 0.01
    up = bs_ref(S + h, K, R, SIG, T, True)
    dn = bs_ref(S - h, K, R, SIG, T, True)
    delta_fd = (up - dn) / (2 * h)
    gamma_fd = (up - 2 * bs_ref(S, K, R, SIG, T, True) + dn) / h**2
    assert abs(g["delta"] - delta_fd) < 1e-3
    assert abs(g["gamma"] - gamma_fd) < 1e-4
    # vega via bump of sigma
    vega_fd = (bs_ref(S, K, R, SIG + 1e-4, T, True) - bs_ref(S, K, R, SIG - 1e-4, T, True)) / 2e-4
    assert abs(g["vega"] - vega_fd) < 1e-1


def test_bs_greeks_put_delta_relation():
    gc = black_scholes_greeks(S, K, R, SIG, T, "call")
    gp = black_scholes_greeks(S, K, R, SIG, T, "put")
    # delta_call - delta_put = 1 (no dividends)
    assert abs((gc["delta"] - gp["delta"]) - 1.0) < 1e-6
    assert abs(gc["gamma"] - gp["gamma"]) < 1e-9  # gamma identical


def test_bs_greeks_invalid():
    with pytest.raises(ValueError):
        black_scholes_greeks(S, K, R, SIG, 0.0, "call")
    with pytest.raises(ValueError):
        black_scholes_greeks(S, K, R, SIG, T, "bad")


def test_binomial_converges_to_bs():
    ref = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    px = binomial_tree_option_pricer(S, K, R, SIG, T, n_steps=2000, option_type="call")["price"]
    assert abs(px - ref) < 0.02


def test_binomial_american_ge_european_put():
    eur = binomial_tree_option_pricer(S, K, R, SIG, T, 1000, "put", "european")["price"]
    ame = binomial_tree_option_pricer(S, K, R, SIG, T, 1000, "put", "american")["price"]
    assert ame >= eur - 1e-6


def test_binomial_invalid():
    with pytest.raises(ValueError):
        binomial_tree_option_pricer(S, K, R, SIG, T, 0, "call")
    with pytest.raises(ValueError):
        binomial_tree_option_pricer(S, K, R, SIG, T, 10, "bad")
    with pytest.raises(ValueError):
        binomial_tree_option_pricer(S, K, R, SIG, T, 10, "call", "bad")


def test_trinomial_converges_to_bs():
    ref = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    px = trinomial_tree_option_pricer(S, K, R, SIG, T, n_steps=800, option_type="call")["price"]
    assert abs(px - ref) < 0.02


def test_trinomial_american_ge_european_put():
    eur = trinomial_tree_option_pricer(S, K, R, SIG, T, 500, "put", "european")["price"]
    ame = trinomial_tree_option_pricer(S, K, R, SIG, T, 500, "put", "american")["price"]
    assert ame >= eur - 1e-6


def test_trinomial_invalid():
    with pytest.raises(ValueError):
        trinomial_tree_option_pricer(S, K, R, SIG, T, 0, "call")
    with pytest.raises(ValueError):
        trinomial_tree_option_pricer(S, K, R, SIG, T, 10, "bad")
    with pytest.raises(ValueError):
        trinomial_tree_option_pricer(S, K, R, SIG, T, 10, "call", "bad")


def test_mc_converges_to_bs_and_deterministic():
    ref = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    r1 = monte_carlo_option_pricer(S, K, R, SIG, T, 400_000, "call", seed=999)
    r2 = monte_carlo_option_pricer(S, K, R, SIG, T, 400_000, "call", seed=999)
    assert abs(r1["price"] - ref) / ref < 0.005  # 0.5% MC tolerance
    assert r1["price"] == r2["price"]  # determinism under fixed seed


def test_mc_invalid():
    with pytest.raises(ValueError):
        monte_carlo_option_pricer(S, K, R, SIG, T, 0, "call")
    with pytest.raises(ValueError):
        monte_carlo_option_pricer(S, K, R, SIG, T, 100, "bad")


# ═══════════════════════════════════════════════════════════════════════════
# 2. deriv_options_exotic
# ═══════════════════════════════════════════════════════════════════════════


def test_digital_closed_form():
    # independent: cash-or-nothing call = payout e^{-rT} N(d2)
    d2 = (math.log(S / K) + (R - 0.5 * SIG**2) * T) / (SIG * math.sqrt(T))
    ref = math.exp(-R * T) * stats.norm.cdf(d2)
    px = digital_option_pricer(S, K, R, SIG, T, "call", payout=1.0)["price"]
    assert abs(px - ref) < 1e-6
    # put digital = payout e^{-rT} N(-d2); call+put = payout e^{-rT}
    put = digital_option_pricer(S, K, R, SIG, T, "put", payout=1.0)["price"]
    assert abs((px + put) - math.exp(-R * T)) < 1e-6


def test_digital_invalid():
    with pytest.raises(ValueError):
        digital_option_pricer(S, K, R, SIG, T, "bad")
    with pytest.raises(ValueError):
        digital_option_pricer(-1, K, R, SIG, T, "call")


def test_barrier_in_out_parity():
    # independent property: knock-in + knock-out = vanilla
    vanilla = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    ko = barrier_option_pricer(S, K, 90.0, R, SIG, T, "call", "down-and-out")["price"]
    ki = barrier_option_pricer(S, K, 90.0, R, SIG, T, "call", "down-and-in")["price"]
    assert abs((ko + ki) - vanilla) < 1e-4
    assert ko <= vanilla + 1e-6  # knock-out <= vanilla


def test_barrier_all_types_nonneg():
    for bt in ("down-and-out", "down-and-in", "up-and-out", "up-and-in"):
        barr = 90.0 if bt.startswith("down") else 120.0
        for ot in ("call", "put"):
            px = barrier_option_pricer(S, K, barr, R, SIG, T, ot, bt)["price"]
            assert px >= 0.0


def test_barrier_invalid():
    with pytest.raises(ValueError):
        barrier_option_pricer(S, K, 90, R, SIG, T, "bad", "down-and-out")
    with pytest.raises(ValueError):
        barrier_option_pricer(S, K, 90, R, SIG, T, "call", "sideways")
    with pytest.raises(ValueError):
        barrier_option_pricer(S, K, -1, R, SIG, T, "call", "down-and-out")


def test_asian_less_than_vanilla():
    # independent property: averaging lowers vol => Asian < European
    vanilla = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    asian = asian_option_pricer(S, K, R, SIG, T, 50, 60_000, "call", seed=3)["price"]
    assert 0.0 <= asian < vanilla


def test_asian_deterministic_and_invalid():
    a = asian_option_pricer(S, K, R, SIG, T, 30, 20_000, "call", seed=5)["price"]
    b = asian_option_pricer(S, K, R, SIG, T, 30, 20_000, "call", seed=5)["price"]
    assert a == b
    with pytest.raises(ValueError):
        asian_option_pricer(S, K, R, SIG, T, average_type="geometric")
    with pytest.raises(ValueError):
        asian_option_pricer(S, K, R, SIG, T, option_type="bad")


def test_lookback_ge_vanilla_payoff():
    # independent property: floating lookback call >= vanilla call
    vanilla = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    lb = lookback_option_pricer(S, K, R, SIG, T, 50, 60_000, "call", "floating", seed=7)["price"]
    assert lb >= vanilla - 0.5  # MC noise band; lookback structurally >= vanilla
    fixed = lookback_option_pricer(S, K, R, SIG, T, 50, 40_000, "call", "fixed", seed=7)["price"]
    assert fixed >= 0.0


def test_lookback_invalid():
    with pytest.raises(ValueError):
        lookback_option_pricer(S, K, R, SIG, T, strike_type="bad")
    with pytest.raises(ValueError):
        lookback_option_pricer(S, K, R, SIG, T, option_type="bad")


def test_american_lsm_ge_european():
    # independent reference: European BS put is a lower bound
    eur = black_scholes_european_option(S, K, R, SIG, T, "put")["price"]
    ame = american_option_lsm(S, K, R, SIG, T, 50, 80_000, "put", seed=41)["price"]
    assert ame >= eur - 0.15  # LSM is a (noisy) lower-biased estimator of the true price


def test_american_lsm_deterministic_invalid():
    a = american_option_lsm(S, K, R, SIG, T, 30, 20_000, "put", seed=41)["price"]
    b = american_option_lsm(S, K, R, SIG, T, 30, 20_000, "put", seed=41)["price"]
    assert a == b
    with pytest.raises(ValueError):
        american_option_lsm(S, K, R, SIG, T, option_type="bad")


def test_bermudan_between_euro_and_american():
    eur = black_scholes_european_option(S, K, R, SIG, T, "put")["price"]
    berm = bermudan_option_pricer(S, K, R, SIG, T, 4, 48, 80_000, "put", seed=51)["price"]
    ame = american_option_lsm(S, K, R, SIG, T, 48, 80_000, "put", seed=51)["price"]
    assert berm >= eur - 0.3
    assert berm <= ame + 0.3


def test_bermudan_invalid():
    with pytest.raises(ValueError):
        bermudan_option_pricer(S, K, R, SIG, T, exercise_dates=0)
    with pytest.raises(ValueError):
        bermudan_option_pricer(S, K, R, SIG, T, option_type="bad")


def test_rainbow_bounds():
    # independent property: best-of >= worst-of; both nonneg
    spots = np.array([100.0, 100.0])
    sigs = np.array([0.2, 0.2])
    corr = np.array([[1.0, 0.3], [0.3, 1.0]])
    best = rainbow_option_pricer(spots, 100, R, sigs, T, corr, 60_000, "call", "best-of", seed=61)[
        "price"
    ]
    worst = rainbow_option_pricer(
        spots, 100, R, sigs, T, corr, 60_000, "call", "worst-of", seed=61
    )["price"]
    assert best >= worst - 1e-6
    assert worst >= 0.0
    # best-of of a single asset == vanilla (limiting case)
    single = rainbow_option_pricer(
        np.array([100.0]),
        100,
        R,
        np.array([0.2]),
        T,
        np.array([[1.0]]),
        80_000,
        "call",
        "best-of",
        seed=61,
    )["price"]
    vanilla = black_scholes_european_option(100, 100, R, 0.2, T, "call")["price"]
    assert abs(single - vanilla) / vanilla < 0.02


def test_rainbow_invalid():
    with pytest.raises(ValueError):
        rainbow_option_pricer(
            np.array([100.0]), 100, R, np.array([0.2]), T, np.array([[1.0]]), rainbow_type="bad"
        )
    with pytest.raises(ValueError):
        rainbow_option_pricer(
            np.array([100.0, 100.0]), 100, R, np.array([0.2]), T, np.array([[1.0]])
        )


def test_basket_le_weighted_singles():
    # independent property: diversification => basket <= weighted sum of singles
    spots = np.array([100.0, 100.0])
    weights = np.array([0.5, 0.5])
    sigs = np.array([0.2, 0.25])
    corr = np.array([[1.0, 0.4], [0.4, 1.0]])
    basket = basket_option_pricer(spots, weights, 100, R, sigs, T, corr, 80_000, "call", seed=71)[
        "price"
    ]
    singles = (
        0.5 * black_scholes_european_option(100, 100, R, 0.2, T, "call")["price"]
        + 0.5 * black_scholes_european_option(100, 100, R, 0.25, T, "call")["price"]
    )
    assert basket >= 0.0
    assert basket <= singles + 0.1


def test_basket_invalid():
    with pytest.raises(ValueError):
        basket_option_pricer(
            np.array([100.0]),
            np.array([1.0]),
            100,
            R,
            np.array([0.2]),
            T,
            np.array([[1.0]]),
            option_type="bad",
        )
    with pytest.raises(ValueError):
        basket_option_pricer(
            np.array([100.0, 100.0]), np.array([1.0]), 100, R, np.array([0.2]), T, np.array([[1.0]])
        )


def test_spread_margrabe_limit():
    # LIMITING CASE / independent hand-calc: Kirk with strike=0 == Margrabe exchange option
    s1, s2, sig1, sig2, rho = 100.0, 95.0, 0.2, 0.25, 0.3
    sig_eff = math.sqrt(sig1**2 - 2 * rho * sig1 * sig2 + sig2**2)
    d1 = (math.log(s1 / s2) + 0.5 * sig_eff**2 * T) / (sig_eff * math.sqrt(T))
    d2 = d1 - sig_eff * math.sqrt(T)
    margrabe = math.exp(-R * T) * (s1 * stats.norm.cdf(d1) - s2 * stats.norm.cdf(d2))
    px = spread_option_kirk_approximation(s1, s2, 0.0, R, sig1, sig2, rho, T, "call")["price"]
    assert abs(px - margrabe) < 1e-4


@pytest.mark.parametrize("strike_offset", [0.0, 5.0, -5.0, 10.0])
def test_spread_kirk_cross_validated_against_quantlib(strike_offset):
    # INDEPENDENT-IMPLEMENTATION CROSS-VALIDATION: only strike=0 (pure
    # Margrabe) had a real check before this -- the Kirk approximation itself
    # (the whole reason this function exists) was previously untested at any
    # nonzero strike. QuantLib's KirkEngine is independently coded, not the
    # same formula re-typed by this file's author. Verified ~1e-10 relative.
    s1, s2, sig1, sig2, rho = 100.0, 95.0, 0.2, 0.25, 0.3
    px = spread_option_kirk_approximation(s1, s2, strike_offset, R, sig1, sig2, rho, T, "call")[
        "price"
    ]
    ql_px = ql_kirk_price(s1, s2, strike_offset, R, sig1, sig2, rho, T, True)
    assert abs(px - ql_px) / ql_px < 1e-6


def test_spread_invalid():
    with pytest.raises(ValueError):
        spread_option_kirk_approximation(100, 95, 0, R, 0.2, 0.25, 0.3, T, "bad")
    with pytest.raises(ValueError):
        spread_option_kirk_approximation(100, 95, 0, R, 0.2, 0.25, 2.0, T, "call")


def test_compound_le_underlying_value():
    # independent property: compound (option on option) <= underlying option value
    under = black_scholes_european_option(S, K, R, SIG, 1.0, "call")["price"]
    px = compound_option_pricer(S, K, 3.0, R, SIG, 0.5, 1.0, 120_000, "call-on-call", seed=81)[
        "price"
    ]
    assert 0.0 <= px <= under


def test_compound_invalid():
    with pytest.raises(ValueError):
        compound_option_pricer(S, K, 3, R, SIG, 0.5, 1.0, compound_type="bad")
    with pytest.raises(ValueError):
        compound_option_pricer(S, K, 3, R, SIG, 1.0, 0.5)  # tau_under<=tau_compound


def test_chooser_ge_max_call_put():
    # independent property: chooser >= max(embedded call, embedded put)
    res = chooser_option_pricer(S, K, R, SIG, 0.5, 1.0)
    assert res["price"] >= max(res["call_value"], res["put_value"]) - 1e-6


def test_chooser_invalid():
    with pytest.raises(ValueError):
        chooser_option_pricer(S, K, R, SIG, 1.0, 0.5)  # expiry<=choose
    with pytest.raises(ValueError):
        chooser_option_pricer(-1, K, R, SIG, 0.5, 1.0)


# ═══════════════════════════════════════════════════════════════════════════
# 3. deriv_stoch_vol
# ═══════════════════════════════════════════════════════════════════════════


def test_heston_reduces_to_bs():
    # LIMITING CASE: vol-of-vol small, v0=theta => Heston ~ BS(sqrt(theta))
    theta = 0.04  # sqrt = 0.2 vol
    ref = bs_ref(S, K, R, math.sqrt(theta), T, True)
    px = heston_stochastic_volatility_model(
        S, K, R, T, v0=theta, kappa=2.0, theta=theta, sigma=0.001, rho=0.0, option_type="call"
    )["price"]
    assert abs(px - ref) / ref < 0.02


def test_heston_put_call_parity():
    p = dict(v0=0.04, kappa=1.5, theta=0.04, sigma=0.3, rho=-0.5)
    c = heston_stochastic_volatility_model(S, K, R, T, option_type="call", **p)["price"]
    pu = heston_stochastic_volatility_model(S, K, R, T, option_type="put", **p)["price"]
    assert abs((c - pu) - (S - K * math.exp(-R * T))) < 0.05


@pytest.mark.parametrize(
    "strike,rate,tau,v0,kappa,theta,sigma,rho,is_call",
    [
        (90.0, 0.03, 1.0, 0.04, 1.5, 0.04, 0.5, -0.6, True),
        (90.0, 0.03, 1.0, 0.04, 1.5, 0.04, 0.5, -0.6, False),
        (100.0, 0.05, 1.0, 0.04, 1.5, 0.04, 0.3, -0.5, True),
        (100.0, 0.05, 1.0, 0.04, 1.5, 0.04, 0.3, -0.5, False),
    ],
)
def test_heston_cross_validated_against_quantlib(
    strike, rate, tau, v0, kappa, theta, sigma, rho, is_call
):
    # INDEPENDENT-IMPLEMENTATION CROSS-VALIDATION at realistic vol-of-vol
    # (sigma=0.3-0.5): the existing eta->0-style reduction to BS
    # (test_heston_reduces_to_bs) never exercises the characteristic-function
    # integration at the parameter values this model is actually meant for --
    # a CF/branch-cut error would pass that test undetected. Verified ~1e-9
    # relative agreement against QuantLib's AnalyticHestonEngine (a different
    # semi-analytic implementation, in different code) during the audit.
    option_type = "call" if is_call else "put"
    px = heston_stochastic_volatility_model(
        S, strike, rate, tau, v0, kappa, theta, sigma, rho, option_type
    )["price"]
    ql_px = ql_heston_price(S, strike, rate, tau, v0, kappa, theta, sigma, rho, is_call)
    assert abs(px - ql_px) / ql_px < 1e-6


def test_heston_invalid():
    with pytest.raises(ValueError):
        heston_stochastic_volatility_model(S, K, R, T, 0.04, 1.5, 0.04, 0.3, -0.5, "bad")
    with pytest.raises(ValueError):
        heston_stochastic_volatility_model(S, K, R, T, 0.04, 1.5, 0.04, 0.3, 2.0)


def test_sabr_atm_hand_calc():
    # independent hand-calc of Hagan ATM SABR lognormal vol
    f = k = 0.03
    alpha, beta, rho, nu = 0.02, 0.5, -0.3, 0.4
    one_beta = 1 - beta
    fk = f**one_beta
    ref = (alpha / fk) * (
        1
        + (
            (one_beta**2 / 24) * (alpha**2 / fk**2)
            + (rho * beta * nu * alpha) / (4 * fk)
            + ((2 - 3 * rho**2) / 24) * nu**2
        )
        * T
    )
    vol = sabr_volatility_model(f, k, T, alpha, beta, rho, nu)["implied_vol"]
    # engine rounds implied_vol to 8 dp; compare within that rounding
    assert abs(vol - ref) < 1e-7


def test_sabr_non_atm_positive():
    vol = sabr_volatility_model(0.03, 0.035, T, 0.02, 0.5, -0.3, 0.4)["implied_vol"]
    assert vol > 0


@pytest.mark.parametrize("strike", [0.02, 0.025, 0.03, 0.035, 0.05])
def test_sabr_cross_validated_against_quantlib(strike):
    # INDEPENDENT-IMPLEMENTATION CROSS-VALIDATION: test_sabr_non_atm_positive
    # above only checks vol > 0 at one off-ATM strike, and
    # test_sabr_atm_hand_calc re-derives the exact same Hagan formula the
    # engine implements (shared-author risk, not an independent check).
    # ql.sabrVolatility is QuantLib's own implementation of Hagan et al.
    # (2002), "Managing Smile Risk", Wilmott -- independently coded, in
    # different code. Note QuantLib's positional arg order is (strike,
    # forward, expiryTime, alpha, beta, nu, rho) -- nu before rho, the
    # reverse of this engine's signature. Verified ~1e-8 relative agreement
    # across ATM and off-ATM strikes during the audit.
    forward, alpha, beta, rho, nu = 0.03, 0.02, 0.5, -0.3, 0.4
    vol = sabr_volatility_model(forward, strike, T, alpha, beta, rho, nu)["implied_vol"]
    ql_vol = ql.sabrVolatility(strike, forward, T, alpha, beta, nu, rho)
    assert abs(vol - ql_vol) / ql_vol < 1e-6


def test_sabr_invalid():
    with pytest.raises(ValueError):
        sabr_volatility_model(-0.03, 0.03, T, 0.02, 0.5, 0.0, 0.4)
    with pytest.raises(ValueError):
        sabr_volatility_model(0.03, 0.03, T, 0.02, 1.5, 0.0, 0.4)
    with pytest.raises(ValueError):
        sabr_volatility_model(0.03, 0.03, T, 0.02, 0.5, 2.0, 0.4)
    with pytest.raises(ValueError):
        sabr_volatility_model(0.03, 0.03, T, 0.02, 0.5, 0.0, -0.1)


def test_dupire_constant_vol_surface():
    # LIMITING CASE / independent hand-calc: a BS surface at constant vol should
    # recover a local vol ~ that constant vol on the interior grid.
    sigma_true = 0.2
    strikes = np.array([80.0, 90.0, 100.0, 110.0, 120.0])
    mats = np.array([0.5, 1.0, 1.5])
    surf = np.array([[bs_ref(100.0, kk, R, sigma_true, tt, True) for kk in strikes] for tt in mats])
    res = local_volatility_dupire_model(strikes, mats, surf, R, 100.0)
    loc = np.array(res["local_vol"])
    interior = loc[loc > 0]
    # finite-difference Dupire is approximate; expect the ATM region near 0.2
    assert interior.size > 0
    assert 0.1 < float(np.median(interior)) < 0.35


def test_dupire_recovers_non_constant_term_structure():
    # Sharper than test_dupire_constant_vol_surface above: that test's target
    # (flat 0.2 vol) is degenerate -- Dupire's own formula reduces trivially
    # when nothing varies with strike OR maturity, and a 75%-wide band
    # (0.1-0.35) would not catch a sign error in the r*K*dC/dK term. Here the
    # instantaneous variance genuinely varies with time, v(t) = 0.04+0.02t,
    # giving a non-trivial analytic target sigma_loc(t) = sqrt(v(t)) via the
    # standard flat-in-strike identity sigma_loc(T)^2 = d[sigma_BS(T)^2 * T]/dT
    # (Dupire (1994), "Pricing with a Smile", Risk 7(1); Gatheral, "The
    # Volatility Surface" (2006) Ch. 1). Verified convergent to ~2.5e-3
    # relative error at dT=0.01 during the audit.
    def sigma_bs(mat):
        # integral of (0.04+0.02s) ds from 0 to mat, divided by mat
        return math.sqrt((0.04 * mat + 0.01 * mat**2) / mat)

    def target_local_vol(mat):
        return math.sqrt(0.04 + 0.02 * mat)

    spot = 100.0
    strikes = np.array([90.0, 95.0, 100.0, 105.0, 110.0])
    maturities = np.arange(0.5, 1.5 + 1e-9, 0.01)
    surface = np.array(
        [[bs_ref(spot, kk, 0.0, sigma_bs(tt), tt, True) for kk in strikes] for tt in maturities]
    )
    res = local_volatility_dupire_model(strikes, maturities, surface, 0.0, spot)
    loc = np.array(res["local_vol"])
    mats_inner = np.array(res["maturities_inner"])
    mid_col = loc[:, loc.shape[1] // 2]  # least affected by strike-boundary FD error
    targets = np.array([target_local_vol(t) for t in mats_inner])
    rel_err = np.abs(mid_col - targets) / targets
    assert rel_err.max() < 0.01


def test_dupire_invalid():
    with pytest.raises(ValueError):
        local_volatility_dupire_model(
            np.array([90.0, 100.0]), np.array([1.0]), np.zeros((1, 2)), R, 100
        )  # <3 strikes
    with pytest.raises(ValueError):
        local_volatility_dupire_model(
            np.array([80.0, 100.0, 120.0]), np.array([1.0, 2.0]), np.zeros((3, 3)), R, 100
        )  # shape mismatch


def test_rbergomi_sanity_and_determinism():
    # A broad price-level band like this one cannot, by construction, detect
    # an autocovariance-structure defect in the underlying Volterra kernel --
    # see tests/test_deriv_stoch_vol.py::test_rbergomi_volterra_driver_matches_hand_calc
    # (task #18) for the exact, hand-computable regression test that can.
    # independent sanity / limiting case: price in a sensible band, deterministic
    r1 = rough_volatility_rbergomi_model(S, K, R, T, n_simulations=30_000, seed=2024)
    r2 = rough_volatility_rbergomi_model(S, K, R, T, n_simulations=30_000, seed=2024)
    assert r1["price"] == r2["price"]
    # xi=0.04 -> vol ~0.2; price should be within a broad BS-implied band
    bs = bs_ref(S, K, R, 0.2, T, True)
    assert 0.3 * bs < r1["price"] < 2.0 * bs


def test_rbergomi_put_call_parity():
    """Independent reference: C - P = S - K*exp(-rT) must hold for ANY
    risk-neutral Ito price process regardless of how complex the volatility
    dynamics are -- it is not specific to Black-Scholes. This test would
    have caught a real, separate bug found while fixing task #18's
    autocovariance-structure issue: the variance used to scale a given
    step's price shock was computed using that SAME step's own Brownian
    draw, correlating "random" volatility with the very shock it should be
    independent of and breaking the risk-neutral drift. Before the fix,
    C - P landed at roughly -15.2 against a target of +1.98 (at r=0.02) --
    not a rounding-level miss. n_simulations/tolerance chosen from an
    empirical std-error check (~0.06 at 100k paths here) to be non-flaky
    with a wide margin while still failing hard on the magnitude of bug
    this guards against.
    """
    c = rough_volatility_rbergomi_model(
        S, K, R, T, n_simulations=100_000, option_type="call", seed=2024
    )
    p = rough_volatility_rbergomi_model(
        S, K, R, T, n_simulations=100_000, option_type="put", seed=2024
    )
    parity_target = S - K * math.exp(-R * T)
    assert (c["price"] - p["price"]) == pytest.approx(parity_target, abs=0.5)


def test_rbergomi_invalid():
    with pytest.raises(ValueError):
        rough_volatility_rbergomi_model(S, K, R, T, option_type="bad")
    with pytest.raises(ValueError):
        rough_volatility_rbergomi_model(S, K, R, T, hurst=0.6)
    with pytest.raises(ValueError):
        rough_volatility_rbergomi_model(S, K, R, T, rho=2.0)


def test_variance_gamma_converges_to_bs_limit():
    # LIMITING CASE: nu -> 0, theta=0 => VG -> Black-Scholes(sigma)
    ref = bs_ref(S, K, R, 0.2, T, True)
    px = variance_gamma_model(
        S, K, R, T, sigma=0.2, theta=0.0, nu=0.003, n_simulations=200_000, seed=7
    )["price"]
    assert abs(px - ref) / ref < 0.03


@pytest.mark.parametrize(
    "sigma,nu,theta",
    [
        (0.2, 0.2, -0.1),
        (0.3, 0.5, -0.2),
    ],
)
def test_variance_gamma_cross_validated_against_quantlib(sigma, nu, theta):
    # INDEPENDENT-IMPLEMENTATION CROSS-VALIDATION at realistic vol-of-vol
    # (nu=0.2-0.5): test_variance_gamma_converges_to_bs_limit above only
    # exercises nu~0 (the near-Gaussian regime), never the VG regime this
    # model actually exists for. QuantLib's VarianceGammaEngine is Madan-
    # Carr-Chang (1998) semi-analytic -- a different method (Monte Carlo
    # here vs. closed-form there) means only statistical, not exact,
    # agreement is expected; tolerance is set from the engine's own reported
    # std_error (a real, computed number every run, not an eyeballed
    # constant) rather than an arbitrary absolute tolerance.
    n_sims = 2_000_000
    res = variance_gamma_model(S, K, R, T, sigma, theta, nu, n_simulations=n_sims, seed=42)
    ql_px = ql_variance_gamma_price(S, K, R, T, sigma, nu, theta, True)
    assert abs(res["price"] - ql_px) < 5.0 * res["std_error"]


def test_variance_gamma_invalid():
    with pytest.raises(ValueError):
        variance_gamma_model(S, K, R, T, option_type="bad")
    with pytest.raises(ValueError):
        variance_gamma_model(S, K, R, T, nu=-0.1)


def test_nig_martingale_and_sanity():
    # independent sanity: discounted expected spot ~ martingale (via ATM price band)
    r1 = normal_inverse_gaussian_model(S, K, R, T, n_simulations=120_000, seed=11)
    r2 = normal_inverse_gaussian_model(S, K, R, T, n_simulations=120_000, seed=11)
    assert r1["price"] == r2["price"]
    assert r1["price"] > 0


def test_nig_invalid():
    with pytest.raises(ValueError):
        normal_inverse_gaussian_model(S, K, R, T, option_type="bad")
    with pytest.raises(ValueError):
        normal_inverse_gaussian_model(S, K, R, T, alpha=3.0, beta=-5.0)  # alpha<=|beta|


def test_displaced_diffusion_reduces_to_bs():
    # LIMITING CASE: displacement=0 => exactly Black-Scholes
    ref = black_scholes_european_option(S, K, R, SIG, T, "call")["price"]
    px = displaced_diffusion_model(S, K, R, SIG, T, displacement=0.0, option_type="call")["price"]
    assert abs(px - ref) < 1e-8
    # positive displacement still nonneg
    px2 = displaced_diffusion_model(S, K, R, SIG, T, displacement=20.0, option_type="put")["price"]
    assert px2 >= 0.0


def test_displaced_diffusion_invalid():
    with pytest.raises(ValueError):
        displaced_diffusion_model(S, K, R, SIG, T, 0.0, "bad")
    with pytest.raises(ValueError):
        displaced_diffusion_model(S, K, R, SIG, T, -200.0, "call")  # displaced spot<=0


# ═══════════════════════════════════════════════════════════════════════════
# 4. deriv_bonds
# ═══════════════════════════════════════════════════════════════════════════


def test_fixed_coupon_bond_closed_form():
    # independent PV = sum(cpn*DF) + face*DF
    ref = bond_pv_ref(100, 0.05, 0.04, 5, 2)
    px = bond_pricer_fixed_coupon(100, 0.05, 0.04, 5, 2)["price"]
    assert abs(px - ref) < 1e-6


def test_fixed_coupon_par_when_coupon_eq_yield():
    px = bond_pricer_fixed_coupon(100, 0.05, 0.05, 5, 2)["price"]
    assert abs(px - 100.0) < 1e-6


def test_fixed_coupon_inverse_yield():
    lo = bond_pricer_fixed_coupon(100, 0.05, 0.03, 5, 2)["price"]
    hi = bond_pricer_fixed_coupon(100, 0.05, 0.07, 5, 2)["price"]
    assert lo > hi  # price falls as yield rises


def test_fixed_coupon_invalid():
    with pytest.raises(ValueError):
        bond_pricer_fixed_coupon(100, 0.05, 0.04, 0, 2)
    with pytest.raises(ValueError):
        bond_pricer_fixed_coupon(100, 0.05, 0.04, 5, 0)


def test_frn_near_par_at_reset():
    # independent: FRN with discount rates == reference rates prices ~ par + PV(spread)
    n = 8
    ref_rates = np.full(n, 0.03)
    disc_rates = np.full(n, 0.03)
    res = bond_pricer_floating_rate(100, ref_rates, 0.0, disc_rates, 2.0, 4)
    assert abs(res["price"] - 100.0) < 1.0  # near par with zero spread
    # positive spread raises price
    res2 = bond_pricer_floating_rate(100, ref_rates, 0.01, disc_rates, 2.0, 4)
    assert res2["price"] > res["price"]


def test_frn_invalid():
    with pytest.raises(ValueError):
        bond_pricer_floating_rate(100, np.array([0.03]), 0.0, np.array([0.03, 0.03]), 1.0, 4)
    with pytest.raises(ValueError):
        bond_pricer_floating_rate(100, np.array([0.03]), 0.0, np.array([0.03]), 0.0, 4)


def test_zero_coupon_closed_form():
    # independent: face/(1+y/m)^{mT}
    ref = 100 / (1 + 0.04 / 2) ** (2 * 5)
    px = zero_coupon_bond_pricer(100, 0.04, 5, 2)["price"]
    assert abs(px - ref) < 1e-6


def test_zero_coupon_invalid():
    with pytest.raises(ValueError):
        zero_coupon_bond_pricer(100, 0.04, 0, 2)


def test_inflation_linked_uplift():
    # independent: with zero inflation, ILB == plain fixed bond at real yield
    plain = bond_pricer_fixed_coupon(100, 0.02, 0.01, 5, 2)["price"]
    ilb0 = inflation_linked_bond_pricer(100, 0.02, 0.01, 5, 0.0, 2)["price"]
    assert abs(plain - ilb0) < 1e-6
    # positive inflation raises price (indexed cashflows)
    ilb = inflation_linked_bond_pricer(100, 0.02, 0.01, 5, 0.03, 2)["price"]
    assert ilb > ilb0


def test_inflation_invalid():
    with pytest.raises(ValueError):
        inflation_linked_bond_pricer(100, 0.02, 0.01, 0, 0.03, 2)


def test_callable_le_straight():
    # independent property: callable <= straight bond
    res = callable_bond_pricer(100, 0.05, 0.05, 0.2, 5, 100.0, 1)
    assert res["price"] <= res["straight_price"] + 1e-6


def test_callable_invalid():
    with pytest.raises(ValueError):
        callable_bond_pricer(100, 0.05, 0.05, 0.2, 0, 100.0, 1)


def test_puttable_ge_straight():
    # independent property: puttable >= straight bond
    res = puttable_bond_pricer(100, 0.05, 0.05, 0.2, 5, 100.0, 1)
    assert res["price"] >= res["straight_price"] - 1e-6


def test_puttable_invalid():
    with pytest.raises(ValueError):
        puttable_bond_pricer(100, 0.05, 0.05, 0.2, 5, 100.0, 0)


def test_convertible_max_of_floor_and_conversion():
    # independent property: price = max(bond floor, conversion value)
    res = convertible_bond_pricer(100, 0.04, 0.05, 5, 2.0, 60.0, 2)
    assert abs(res["price"] - max(res["bond_floor"], res["conversion_value"])) < 1e-6
    assert res["conversion_value"] == pytest.approx(120.0)


def test_convertible_invalid():
    with pytest.raises(ValueError):
        convertible_bond_pricer(100, 0.04, 0.05, 5, -1.0, 60.0, 2)
    with pytest.raises(ValueError):
        convertible_bond_pricer(100, 0.04, 0.05, 0, 2.0, 60.0, 2)


# ═══════════════════════════════════════════════════════════════════════════
# 5. deriv_bond_analytics
# ═══════════════════════════════════════════════════════════════════════════


def _bond_cfs(face, cpn_rate, mat, freq):
    n = int(round(mat * freq))
    cpn = face * cpn_rate / freq
    times = np.array([(i + 1) / freq for i in range(n)])
    cfs = np.full(n, cpn)
    cfs[-1] += face
    return cfs, times


def test_macaulay_closed_form():
    # independent: D = sum(t*PV)/price
    cfs, times = _bond_cfs(100, 0.06, 5, 2)
    y, freq = 0.05, 2
    disc = (1 + y / freq) ** (-(times * freq))
    pv = cfs * disc
    ref = float(np.sum(times * pv) / np.sum(pv))
    res = duration_macaulay(cfs, times, y, freq)
    assert abs(res["macaulay_duration"] - ref) < 1e-6


def test_macaulay_invalid():
    with pytest.raises(ValueError):
        duration_macaulay(np.array([1.0, 2.0]), np.array([1.0]), 0.05, 2)


def test_modified_duration_relation():
    # independent: mod = mac / (1 + y/m)
    cfs, times = _bond_cfs(100, 0.06, 5, 2)
    mac = duration_macaulay(cfs, times, 0.05, 2)["macaulay_duration"]
    res = modified_duration(cfs, times, 0.05, 2)
    assert abs(res["modified_duration"] - mac / (1 + 0.05 / 2)) < 1e-8


def test_effective_duration_hand_calc():
    # independent: D_eff = (P- - P+)/(2 P0 dy)
    res = effective_duration(100.0, 98.0, 102.0, 0.01)
    assert abs(res["effective_duration"] - (102 - 98) / (2 * 100 * 0.01)) < 1e-8


def test_effective_duration_invalid():
    with pytest.raises(ValueError):
        effective_duration(0.0, 98, 102, 0.01)
    with pytest.raises(ValueError):
        effective_duration(100, 98, 102, 0.0)


def test_convexity_closed_form():
    # independent convexity formula
    cfs, times = _bond_cfs(100, 0.06, 5, 2)
    y, m = 0.05, 2
    periods = times * m
    disc = (1 + y / m) ** (-periods)
    price = float(np.sum(cfs * disc))
    weight = cfs * periods * (periods + 1) * (1 + y / m) ** (-(periods + 2))
    ref = float(np.sum(weight) / (price * m * m))
    res = convexity(cfs, times, y, m)
    assert abs(res["convexity"] - ref) < 1e-6
    assert res["convexity"] > 0


def test_bond_price_duration_convexity_cross_validated_against_quantlib():
    # INDEPENDENT-IMPLEMENTATION CROSS-VALIDATION (serves task #16, extending
    # QuantLib coverage beyond Black-Scholes): the closed-form checks above
    # already re-derive the same discounting formula the engine implements
    # (shared-author risk). ql.FixedRateBond + ql.BondFunctions is a
    # genuinely independent implementation -- different schedule/day-count
    # machinery entirely, not the same formula re-typed. Verified ~1e-9
    # relative agreement (price, Macaulay duration, modified duration,
    # convexity, all four) at the standard 100-face/6%-coupon/5y/semi/5%-yield
    # case during the audit.
    face, cpn_rate, mat, freq, y = 100.0, 0.06, 5, 2, 0.05
    calc_date = ql.Date(1, 1, 2024)
    ql.Settings.instance().evaluationDate = calc_date
    calendar = ql.NullCalendar()
    day_count = ql.Thirty360(ql.Thirty360.BondBasis)
    maturity_date = calc_date + ql.Period(int(mat * 12), ql.Months)
    schedule = ql.Schedule(
        calc_date,
        maturity_date,
        ql.Period(ql.Semiannual),
        calendar,
        ql.Unadjusted,
        ql.Unadjusted,
        ql.DateGeneration.Backward,
        False,
    )
    bond = ql.FixedRateBond(0, face, schedule, [cpn_rate], day_count)
    yield_ql = ql.InterestRate(y, day_count, ql.Compounded, ql.Semiannual)
    ql_price = ql.BondFunctions.cleanPrice(bond, yield_ql)
    ql_mac = ql.BondFunctions.duration(bond, yield_ql, ql.Duration.Macaulay)
    ql_mod = ql.BondFunctions.duration(bond, yield_ql, ql.Duration.Modified)
    ql_conv = ql.BondFunctions.convexity(bond, yield_ql)

    cfs, times = _bond_cfs(face, cpn_rate, mat, freq)
    eng_price = bond_pricer_fixed_coupon(face, cpn_rate, y, mat, freq)["price"]
    eng_mac = duration_macaulay(cfs, times, y, freq)["macaulay_duration"]
    eng_mod = modified_duration(cfs, times, y, freq)["modified_duration"]
    eng_conv = convexity(cfs, times, y, freq)["convexity"]

    assert abs(eng_price - ql_price) / ql_price < 1e-6
    assert abs(eng_mac - ql_mac) / ql_mac < 1e-6
    assert abs(eng_mod - ql_mod) / ql_mod < 1e-6
    assert abs(eng_conv - ql_conv) / ql_conv < 1e-6


def test_convexity_invalid():
    with pytest.raises(ValueError):
        convexity(np.array([1.0]), np.array([1.0, 2.0]), 0.05, 2)


def test_dv01_matches_analytic_modified_duration():
    # independent: DV01 ~ ModDur * Price * 1bp
    cfs, times = _bond_cfs(100, 0.06, 5, 2)
    mod = modified_duration(cfs, times, 0.05, 2)
    price = mod["price"]
    dv01_ref = mod["modified_duration"] * price * 1e-4
    res = dv01_pvbp(cfs, times, 0.05, 2)
    assert res["dv01"] > 0
    assert abs(res["dv01"] - dv01_ref) / dv01_ref < 1e-3


def test_dv01_invalid():
    with pytest.raises(ValueError):
        dv01_pvbp(np.array([1.0]), np.array([1.0, 2.0]), 0.05, 2)


def test_ytm_inverts_price():
    # independent: price the bond at a known yield, YTM must recover it
    cfs, times = _bond_cfs(100, 0.05, 5, 2)
    y_true = 0.043
    disc = (1 + y_true / 2) ** (-(times * 2))
    price = float(np.sum(cfs * disc))
    res = yield_to_maturity(price, cfs, times, 2)
    assert abs(res["ytm"] - y_true) < 1e-6
    # re-price at solved yield reproduces price
    disc2 = (1 + res["ytm"] / 2) ** (-(times * 2))
    assert abs(float(np.sum(cfs * disc2)) - price) < 1e-6


def test_ytm_invalid():
    with pytest.raises(ValueError):
        yield_to_maturity(100, np.array([1.0]), np.array([1.0, 2.0]), 2)


def test_ytc_inverts_price():
    # independent: build truncated cashflows to call, price, recover yield
    face, cpn_rate, call_price, call_date, freq = 100, 0.05, 102.0, 3.0, 2
    n = int(round(call_date * freq))
    times = np.array([(i + 1) / freq for i in range(n)])
    cpn = face * cpn_rate / freq
    cfs = np.full(n, cpn)
    cfs[-1] += call_price
    y_true = 0.04
    disc = (1 + y_true / freq) ** (-(times * freq))
    price = float(np.sum(cfs * disc))
    res = yield_to_call(price, face, cpn_rate, call_price, call_date, freq)
    assert abs(res["ytc"] - y_true) < 1e-6


def test_ytc_invalid():
    with pytest.raises(ValueError):
        yield_to_call(100, 100, 0.05, 102, 0.0, 2)


def test_zspread_zero_when_price_on_curve():
    # independent: if price == PV at the zero curve, z-spread == 0
    cfs, times = _bond_cfs(100, 0.05, 3, 2)
    zeros = np.full(cfs.size, 0.04)
    disc = (1 + zeros / 2) ** (-(times * 2))
    price = float(np.sum(cfs * disc))
    res = z_spread_calculator(price, cfs, times, zeros, 2)
    assert abs(res["z_spread"]) < 1e-6
    # lower price => positive spread
    res2 = z_spread_calculator(price - 2.0, cfs, times, zeros, 2)
    assert res2["z_spread"] > 0
    assert abs(res2["z_spread_bps"] - res2["z_spread"] * 1e4) < 1e-3


def test_zspread_invalid():
    with pytest.raises(ValueError):
        z_spread_calculator(100, np.array([1.0]), np.array([1.0]), np.array([0.04, 0.04]), 2)


def test_asset_swap_spread_hand_calc():
    # independent: ASW = (PV_bond - par) / (annuity*par)
    cfs, times = _bond_cfs(100, 0.06, 3, 2)
    sr = np.full(cfs.size, 0.04)
    df = (1 + sr / 2) ** (-(times * 2))
    pv_bond = float(np.sum(cfs * df))
    annuity = float(np.sum(df)) / 2
    ref = (pv_bond - 100.0) / (annuity * 100.0)
    res = asset_swap_spread(pv_bond, cfs, times, sr, 100.0, 2)
    assert abs(res["asset_swap_spread"] - ref) < 1e-8


def test_asset_swap_invalid():
    with pytest.raises(ValueError):
        asset_swap_spread(100, np.array([1.0]), np.array([1.0]), np.array([0.04, 0.04]))


def test_oas_reprices_callable():
    # independent: OAS is the spread that reprices callable bond to market.
    # Take the model's own price at zero spread as "market"; OAS must be ~0.
    base = callable_bond_pricer(100, 0.05, 0.05, 0.15, 5, 100.0, 1)["price"]
    res = oas_option_adjusted_spread(base, 100, 0.05, 0.05, 0.15, 5, 100.0, 1)
    assert abs(res["oas"]) < 1e-6
    # a lower market price => positive OAS
    res2 = oas_option_adjusted_spread(base - 3.0, 100, 0.05, 0.05, 0.15, 5, 100.0, 1)
    assert res2["oas"] > 0


def test_oas_invalid():
    with pytest.raises(ValueError):
        oas_option_adjusted_spread(100, 100, 0.05, 0.05, 0.15, 0, 100.0, 1)


# ═══════════════════════════════════════════════════════════════════════════
# 6. deriv_curves
# ═══════════════════════════════════════════════════════════════════════════


def test_ns_fits_curve():
    # independent: generate yields from a known NS curve, fit must recover it closely
    mats = np.array([0.5, 1, 2, 3, 5, 7, 10.0])
    b0, b1, b2, tau = 0.04, -0.02, 0.01, 1.5
    fac = (1 - np.exp(-mats / tau)) / (mats / tau)
    ys = b0 + b1 * fac + b2 * (fac - np.exp(-mats / tau))
    res = nelson_siegel_curve_fit(mats, ys)
    assert res["rmse"] < 1e-6
    assert abs(res["beta0"] - b0) < 1e-3


def test_ns_invalid():
    with pytest.raises(ValueError):
        nelson_siegel_curve_fit(np.array([1.0, 2.0]), np.array([0.03, 0.04]))


def test_nss_fits_curve():
    mats = np.array([0.5, 1, 2, 3, 5, 7, 10, 20.0])
    b0, b1, b2, b3, ta1, ta2 = 0.04, -0.02, 0.01, 0.005, 1.5, 8.0
    tt = mats
    f1 = (1 - np.exp(-tt / ta1)) / (tt / ta1)
    f2 = (1 - np.exp(-tt / ta2)) / (tt / ta2)
    ys = b0 + b1 * f1 + b2 * (f1 - np.exp(-tt / ta1)) + b3 * (f2 - np.exp(-tt / ta2))
    res = nelson_siegel_svensson_curve(mats, ys)
    assert res["rmse"] < 1e-5
    assert abs(res["beta0"] - b0) < 5e-3


def test_nss_invalid():
    with pytest.raises(ValueError):
        nelson_siegel_svensson_curve(np.array([1.0, 2, 3, 4.0]), np.array([0.03, 0.03, 0.03, 0.03]))


def test_bootstrap_recovers_flat_curve():
    # independent: flat par rates => flat discount factors DF_i = ... reprice par
    par = np.array([0.03, 0.03, 0.03, 0.03])
    mats = np.array([1.0, 2.0, 3.0, 4.0])
    res = bootstrap_yield_curve(par, mats, frequency=1, face_value=1.0)
    dfs = np.array(res["discount_factors"])
    # verify each par bond reprices to par (=1) with the bootstrapped DFs
    for i in range(len(mats)):
        cpn = par[i]
        price = cpn * float(np.sum(dfs[: i + 1])) + dfs[i]
        assert abs(price - 1.0) < 1e-8


def test_bootstrap_invalid():
    with pytest.raises(ValueError):
        bootstrap_yield_curve(np.array([0.03]), np.array([1.0, 2.0]))


def test_swap_rate_from_dfs_hand_calc():
    # independent: swap_rate(T) = (1-DF(T))/sum(tau*DF)
    dfs = np.array([0.97, 0.94, 0.90])
    mats = np.array([1.0, 2.0, 3.0])
    res = swap_rate_curve(dfs, mats, frequency=1)
    ann = 0.0
    for i in range(3):
        ann += 1.0 * dfs[i]
        ref = (1 - dfs[i]) / ann
        assert abs(res["swap_rates"][i] - ref) < 1e-10


def test_swap_rate_invalid():
    with pytest.raises(ValueError):
        swap_rate_curve(np.array([0.97]), np.array([1.0, 2.0]))


def test_ois_bootstrap_reprices_par():
    # independent: OIS swaps must reprice to par with bootstrapped DFs
    rates = np.array([0.02, 0.025, 0.03])
    mats = np.array([1.0, 2.0, 3.0])
    res = ois_curve_sonia_sofr(rates, mats, frequency=1)
    dfs = np.array(res["discount_factors"])
    for i in range(3):
        ann = float(np.sum(dfs[: i + 1]))
        # fixed rate * annuity + DF_last == 1 for a par swap
        assert abs(rates[i] * ann + dfs[i] - 1.0) < 1e-10


def test_ois_invalid():
    with pytest.raises(ValueError):
        ois_curve_sonia_sofr(np.array([0.02]), np.array([1.0, 2.0]))


def test_fra_zero_at_forward():
    # independent: FRA value = 0 when contracted rate == forward
    res = forward_rate_agreement_fra(1_000_000, 0.03, 0.03, 0.5, 1.0, 0.98)
    assert abs(res["value"]) < 1e-6
    # value = N*(fwd-fra)*accrual*DF
    res2 = forward_rate_agreement_fra(1_000_000, 0.03, 0.035, 0.5, 1.0, 0.98)
    ref = 1_000_000 * (0.035 - 0.03) * 0.5 * 0.98
    assert abs(res2["value"] - ref) < 1e-3


def test_fra_invalid():
    with pytest.raises(ValueError):
        forward_rate_agreement_fra(1e6, 0.03, 0.03, 1.0, 0.5, 0.98)


def test_irs_par_rate_zero_value():
    # independent: at the par rate the swap has zero value; par = float_pv/(N*annuity)
    fwd = np.array([0.03, 0.032, 0.034])
    df = np.array([0.97, 0.94, 0.90])
    acc = np.array([1.0, 1.0, 1.0])
    res = interest_rate_swap_irs_pricer(1_000_000, 0.05, fwd, df, acc, pay_fixed=True)
    par = res["par_rate"]
    res_par = interest_rate_swap_irs_pricer(1_000_000, par, fwd, df, acc, pay_fixed=True)
    assert abs(res_par["value"]) < 1.0  # ~0 at par rate
    # payer and receiver values are opposite
    rec = interest_rate_swap_irs_pricer(1_000_000, 0.05, fwd, df, acc, pay_fixed=False)
    assert abs(res["value"] + rec["value"]) < 1e-3


def test_irs_invalid():
    with pytest.raises(ValueError):
        interest_rate_swap_irs_pricer(
            1e6, 0.05, np.array([0.03]), np.array([0.97, 0.94]), np.array([1.0])
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. deriv_rates
# ═══════════════════════════════════════════════════════════════════════════


def test_xccy_swap_hand_calc():
    # independent leg-PV computation
    dd = np.array([0.98, 0.95, 0.91])
    fd = np.array([0.99, 0.97, 0.94])
    acc = np.array([1.0, 1.0, 1.0])
    res = cross_currency_swap_pricer(1_000_000, 900_000, 0.03, 0.02, dd, fd, acc, 1.1, True)
    pv_dom = 1_000_000 * (0.03 * float(np.sum(acc * dd)) + dd[-1])
    pv_for = 900_000 * (0.02 * float(np.sum(acc * fd)) + fd[-1]) * 1.1
    assert abs(res["pv_domestic_leg"] - pv_dom) < 1e-3
    assert abs(res["pv_foreign_leg"] - pv_for) < 1e-3
    assert abs(res["value"] - (pv_for - pv_dom)) < 1e-3


def test_xccy_invalid():
    with pytest.raises(ValueError):
        cross_currency_swap_pricer(
            1e6, 9e5, 0.03, 0.02, np.array([0.98]), np.array([0.99, 0.97]), np.array([1.0]), 1.1
        )


def test_ois_single_period_hand_calc():
    ref = 1_000_000 * (0.031 - 0.03) * 0.25 * 0.99
    res = overnight_index_swap_ois(1_000_000, 0.03, 0.031, 0.25, 0.99, True)
    assert abs(res["value"] - ref) < 1e-6
    # zero when compounded==fixed
    assert abs(overnight_index_swap_ois(1e6, 0.03, 0.03, 0.25, 0.99)["value"]) < 1e-9


def test_ois_swap_invalid():
    with pytest.raises(ValueError):
        overnight_index_swap_ois(1e6, 0.03, 0.031, 0.0, 0.99)


def test_trs_hand_calc():
    ref = 1_000_000 * (0.05 - 0.02 * 0.5) * 0.98
    res = total_return_swap_trs(1_000_000, 0.05, 0.02, 0.5, 0.98, True)
    assert abs(res["value"] - ref) < 1e-6
    # direction flips sign
    rev = total_return_swap_trs(1_000_000, 0.05, 0.02, 0.5, 0.98, False)
    assert abs(res["value"] + rev["value"]) < 1e-9


def test_trs_invalid():
    with pytest.raises(ValueError):
        total_return_swap_trs(1e6, 0.05, 0.02, 0.0, 0.98)


def test_cds_par_spread_zeroes_value():
    # independent property: at par spread the CDS value == 0
    res = credit_default_swap_cds_pricer(1e7, 0.01, 0.02, 0.4, 5, 0.03, 4)
    par = res["par_spread"]
    res_par = credit_default_swap_cds_pricer(1e7, par, 0.02, 0.4, 5, 0.03, 4)
    assert abs(res_par["value"]) < 1.0
    assert res["premium_leg"] > 0 and res["protection_leg"] > 0


def test_cds_invalid():
    with pytest.raises(ValueError):
        credit_default_swap_cds_pricer(1e7, 0.01, 0.02, 1.5, 5, 0.03, 4)  # recovery>=1
    with pytest.raises(ValueError):
        credit_default_swap_cds_pricer(1e7, 0.01, 0.02, 0.4, 0, 0.03, 4)


def test_equity_swap_hand_calc():
    ref = 1_000_000 * (0.08 - 0.03 * 1.0) * 0.97
    res = equity_swap_pricer(1_000_000, 0.08, 0.03, 1.0, 0.97, True)
    assert abs(res["value"] - ref) < 1e-6


def test_equity_swap_invalid():
    with pytest.raises(ValueError):
        equity_swap_pricer(1e6, 0.08, 0.03, 0.0, 0.97)


def test_caplet_black76_hand_calc():
    # independent Black-76 caplet
    fwd, strike, vol, exp, acc, df = 0.03, 0.03, 0.2, 1.0, 0.25, 0.97
    d1 = (math.log(fwd / strike) + 0.5 * vol**2 * exp) / (vol * math.sqrt(exp))
    d2 = d1 - vol * math.sqrt(exp)
    caplet_val = df * (fwd * stats.norm.cdf(d1) - strike * stats.norm.cdf(d2))
    ref = 1_000_000 * acc * caplet_val
    res = caplet_floorlet_pricer_black(1_000_000, fwd, strike, vol, exp, acc, df, "caplet")
    assert abs(res["price"] - ref) < 1e-4
    # caplet - floorlet = payer FRA (put-call parity on the rate)
    flr = caplet_floorlet_pricer_black(1_000_000, fwd, strike, vol, exp, acc, df, "floorlet")
    fra = 1_000_000 * acc * df * (fwd - strike)
    assert abs((res["price"] - flr["price"]) - fra) < 1e-3


def test_caplet_invalid():
    with pytest.raises(ValueError):
        caplet_floorlet_pricer_black(1e6, 0.03, 0.03, 0.2, 1.0, 0.25, 0.97, "bad")
    with pytest.raises(ValueError):
        caplet_floorlet_pricer_black(1e6, -0.03, 0.03, 0.2, 1.0, 0.25, 0.97, "caplet")


def test_cap_is_sum_of_caplets():
    fwd = np.array([0.03, 0.032, 0.034])
    vols = np.array([0.2, 0.2, 0.2])
    exps = np.array([0.5, 1.0, 1.5])
    accs = np.array([0.5, 0.5, 0.5])
    dfs = np.array([0.985, 0.97, 0.955])
    res = cap_floor_pricer(1e6, fwd, 0.03, vols, exps, accs, dfs, "cap")
    ref = sum(
        caplet_floorlet_pricer_black(
            1e6,
            float(fwd[i]),
            0.03,
            float(vols[i]),
            float(exps[i]),
            float(accs[i]),
            float(dfs[i]),
            "caplet",
        )["price"]
        for i in range(3)
    )
    assert abs(res["price"] - ref) < 1e-4


def test_cap_floor_invalid():
    with pytest.raises(ValueError):
        cap_floor_pricer(
            1e6,
            np.array([0.03]),
            0.03,
            np.array([0.2]),
            np.array([1.0]),
            np.array([0.5]),
            np.array([0.97]),
            "bad",
        )
    with pytest.raises(ValueError):
        cap_floor_pricer(
            1e6,
            np.array([0.03, 0.03]),
            0.03,
            np.array([0.2]),
            np.array([1.0]),
            np.array([0.5]),
            np.array([0.97]),
            "cap",
        )


def test_swaption_black_hand_calc():
    # independent Black-76 swaption
    fwd, strike, vol, exp, ann = 0.03, 0.03, 0.25, 2.0, 4.0
    d1 = (math.log(fwd / strike) + 0.5 * vol**2 * exp) / (vol * math.sqrt(exp))
    d2 = d1 - vol * math.sqrt(exp)
    payer = ann * (fwd * stats.norm.cdf(d1) - strike * stats.norm.cdf(d2))
    ref = 1e6 * payer
    res = swaption_pricer_black(1e6, fwd, strike, vol, exp, ann, "payer")
    assert abs(res["price"] - ref) < 1e-3
    # payer - receiver = annuity*(fwd-strike) (parity); ATM => ~0
    rec = swaption_pricer_black(1e6, fwd, strike, vol, exp, ann, "receiver")
    assert abs(res["price"] - rec["price"]) < 1.0


def test_swaption_black_invalid():
    with pytest.raises(ValueError):
        swaption_pricer_black(1e6, 0.03, 0.03, 0.25, 2.0, 4.0, "bad")
    with pytest.raises(ValueError):
        swaption_pricer_black(1e6, -0.03, 0.03, 0.25, 2.0, 4.0, "payer")


def test_swaption_sabr_matches_black_with_sabr_vol():
    # independent: SABR swaption == Black swaption fed the SABR vol
    f, k, exp = 0.03, 0.03, 2.0
    alpha, beta, rho, nu = 0.02, 0.5, -0.3, 0.4
    sabr_vol = sabr_volatility_model(f, k, exp, alpha, beta, rho, nu)["implied_vol"]
    ref = swaption_pricer_black(1e6, f, k, sabr_vol, exp, 4.0, "payer")["price"]
    res = swaption_pricer_sabr(1e6, f, k, exp, 4.0, alpha, beta, rho, nu, "payer")
    assert abs(res["price"] - ref) < 1e-6
    assert abs(res["sabr_vol"] - sabr_vol) < 1e-8


# ═══════════════════════════════════════════════════════════════════════════
# 8. deriv_short_rate
# ═══════════════════════════════════════════════════════════════════════════


def test_vasicek_affine_bond_price():
    # independent Vasicek affine closed form P = A e^{-B r0}
    r0, kappa, theta, sigma, mat = 0.03, 0.5, 0.04, 0.01, 5.0
    b = (1 - math.exp(-kappa * mat)) / kappa
    a = math.exp((theta - sigma**2 / (2 * kappa**2)) * (b - mat) - (sigma**2 * b**2) / (4 * kappa))
    ref = a * math.exp(-b * r0)
    res = vasicek_interest_rate_model(r0, kappa, theta, sigma, mat, 50, 20_000)
    assert abs(res["bond_price"] - ref) < 1e-8
    # MC terminal mean ~ theta + (r0-theta)e^{-kappa T} (Vasicek mean)
    mean_ref = theta + (r0 - theta) * math.exp(-kappa * mat)
    assert abs(res["mc_mean_rate"] - mean_ref) < 0.01


def test_vasicek_cross_validated_against_quantlib():
    # INDEPENDENT-IMPLEMENTATION CROSS-VALIDATION (serves task #16): the
    # closed-form check above re-derives the engine's own affine formula.
    # ql.Vasicek is QuantLib's independent short-rate model implementation.
    # Verified ~5e-11 relative agreement during the audit.
    r0, kappa, theta, sigma, mat = 0.03, 0.5, 0.04, 0.01, 5.0
    ql_price = ql.Vasicek(r0, kappa, theta, sigma, 0.0).discountBond(0, mat, r0)
    eng_price = vasicek_interest_rate_model(r0, kappa, theta, sigma, mat, 50, 20_000)["bond_price"]
    assert abs(eng_price - ql_price) / ql_price < 1e-6


def test_vasicek_invalid():
    with pytest.raises(ValueError):
        vasicek_interest_rate_model(0.03, 0.0, 0.04, 0.01, 5)


def test_cir_affine_bond_price():
    # independent CIR affine closed form
    r0, kappa, theta, sigma, mat = 0.03, 0.5, 0.04, 0.05, 5.0
    gamma = math.sqrt(kappa**2 + 2 * sigma**2)
    denom = (gamma + kappa) * (math.exp(gamma * mat) - 1) + 2 * gamma
    b = 2 * (math.exp(gamma * mat) - 1) / denom
    a = (2 * gamma * math.exp((kappa + gamma) * mat / 2) / denom) ** (2 * kappa * theta / sigma**2)
    ref = a * math.exp(-b * r0)
    res = cox_ingersoll_ross_model(r0, kappa, theta, sigma, mat, 50, 20_000)
    assert abs(res["bond_price"] - ref) < 1e-8
    assert res["feller_satisfied"] == bool(2 * kappa * theta >= sigma**2)


def test_cir_cross_validated_against_quantlib():
    # INDEPENDENT-IMPLEMENTATION CROSS-VALIDATION (serves task #16): the
    # closed-form check above re-derives the engine's own affine formula.
    # ql.CoxIngersollRoss is QuantLib's independent short-rate model
    # implementation. Note QuantLib's constructor arg order is
    # (r0, theta, k, sigma) -- theta BEFORE kappa, the reverse of this
    # engine's (r0, kappa, theta, sigma) signature. Verified ~1e-9 relative
    # agreement during the audit.
    r0, kappa, theta, sigma, mat = 0.03, 0.5, 0.04, 0.05, 5.0
    ql_price = ql.CoxIngersollRoss(r0, theta, kappa, sigma).discountBond(0, mat, r0)
    eng_price = cox_ingersoll_ross_model(r0, kappa, theta, sigma, mat, 50, 20_000)["bond_price"]
    assert abs(eng_price - ql_price) / ql_price < 1e-6


def test_cir_invalid():
    with pytest.raises(ValueError):
        cox_ingersoll_ross_model(0.03, 0.0, 0.04, 0.05, 5)


def test_hull_white_equals_vasicek():
    # independent: HW with constant theta == Vasicek closed form
    r0, kappa, sigma, mat, theta = 0.03, 0.5, 0.01, 5.0, 0.03
    vas = vasicek_interest_rate_model(r0, kappa, theta, sigma, mat, 50, 20_000, seed=103)
    hw = hull_white_short_rate_model(r0, kappa, sigma, mat, theta, 50, 20_000, seed=103)
    assert abs(hw["bond_price"] - vas["bond_price"]) < 1e-10


def test_hull_white_invalid():
    with pytest.raises(ValueError):
        hull_white_short_rate_model(0.03, 0.0, 0.01, 5)


def test_lmm_bgm_sanity():
    # LIMITING CASE / independent hand-calc: zero vol => forwards stay at f0
    f0 = np.array([0.03, 0.032, 0.034])
    res0 = lmm_bgm_rate_model(f0, np.zeros(3), 0.5, 1.0, 10, 5_000, seed=104)
    assert res0["mean_terminal_rates"] == pytest.approx(list(f0), abs=1e-8)
    # with vol, rates stay positive (lognormal) and deterministic under seed
    r1 = lmm_bgm_rate_model(f0, np.full(3, 0.2), 0.5, 1.0, 10, 5_000, seed=104)
    r2 = lmm_bgm_rate_model(f0, np.full(3, 0.2), 0.5, 1.0, 10, 5_000, seed=104)
    assert r1["all_positive"] is True
    assert r1["mean_terminal_rates"] == r2["mean_terminal_rates"]


def test_lmm_bgm_invalid():
    with pytest.raises(ValueError):
        lmm_bgm_rate_model(np.array([0.03]), np.array([0.2, 0.2]), 0.5, 1.0)
    with pytest.raises(ValueError):
        lmm_bgm_rate_model(np.array([0.03]), np.array([0.2]), 0.5, 0.0)
    with pytest.raises(ValueError):
        lmm_bgm_rate_model(np.array([-0.03]), np.array([0.2]), 0.5, 1.0)


# ═══════════════════════════════════════════════════════════════════════════
# 9. deriv_fx
# ═══════════════════════════════════════════════════════════════════════════


def test_fx_forward_covered_parity():
    # independent: F = S e^{(rd-rf)T}
    spot, rd, rf, tau = 1.25, 0.04, 0.01, 1.0
    ref = spot * math.exp((rd - rf) * tau)
    res = fx_forward_pricer(spot, rd, rf, tau)
    assert abs(res["forward_rate"] - ref) < 1e-8
    # MtM value with contracted forward
    res2 = fx_forward_pricer(spot, rd, rf, tau, notional=1_000_000, contracted_forward=1.20)
    val_ref = 1_000_000 * (ref - 1.20) * math.exp(-rd * tau)
    assert abs(res2["value"] - val_ref) < 1e-3


def test_fx_forward_invalid():
    with pytest.raises(ValueError):
        fx_forward_pricer(-1, 0.04, 0.01, 1.0)
    with pytest.raises(ValueError):
        fx_forward_pricer(1.25, 0.04, 0.01, 0.0)


def test_garman_kohlhagen_equals_bs_with_two_rates():
    # independent: GK == BS with q = r_foreign
    spot, strike, rd, rf, sigma, tau = 1.25, 1.20, 0.04, 0.01, 0.15, 1.0
    ref_call = bs_ref(spot, strike, rd, sigma, tau, True, q=rf)
    res = fx_option_pricer_garman_kohlhagen(spot, strike, rd, rf, sigma, tau, "call")
    assert abs(res["price"] - ref_call) < 1e-8
    # FX put-call parity: C - P = S e^{-rf T} - K e^{-rd T}
    put = fx_option_pricer_garman_kohlhagen(spot, strike, rd, rf, sigma, tau, "put")["price"]
    parity = spot * math.exp(-rf * tau) - strike * math.exp(-rd * tau)
    assert abs((res["price"] - put) - parity) < 1e-6


def test_gk_notional_scaling():
    # independent: absolute price scales linearly with notional
    base = fx_option_pricer_garman_kohlhagen(
        1.25, 1.20, 0.04, 0.01, 0.15, 1.0, "call", notional=1.0
    )["price"]
    scaled = fx_option_pricer_garman_kohlhagen(
        1.25, 1.20, 0.04, 0.01, 0.15, 1.0, "call", notional=1_000_000
    )["price"]
    assert abs(scaled - base * 1_000_000) < 1e-2


def test_gk_invalid():
    with pytest.raises(ValueError):
        fx_option_pricer_garman_kohlhagen(1.25, 1.20, 0.04, 0.01, 0.15, 1.0, "bad")
    with pytest.raises(ValueError):
        fx_option_pricer_garman_kohlhagen(-1, 1.20, 0.04, 0.01, 0.15, 1.0, "call")

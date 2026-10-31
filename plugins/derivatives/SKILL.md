---
name: pyvar-derivatives
description: >
  Run pyvar's 62 derivatives-pricing functions on the live pyvar.com API: Black-Scholes and
  tree options, Heston/SABR/Dupire/rough-vol models, exotic Monte Carlo options, bonds and
  duration, yield curves, swaps, swaptions, CDS and FX derivatives. Use when the user wants an
  instrument priced or its Greeks computed with real numbers. Needs a free pyvar API key; the
  skill explains how to get one.
version: "1.2.0"
author: "Fibtec Limited — pyvar.com"
tags: [derivatives, options, Black-Scholes, Heston, SABR, Dupire, LSM, bonds, yield-curve, IRS, CDS, swaption, FX, monte-carlo]
---

# pyvar — Derivatives Pricing  (62 functions)

Pricing calculations: vanilla and exotic options, stochastic-volatility models, bonds and yield curves, interest-rate and FX derivatives. Pick the function in **Functions** below; the **Worked examples** show the request shape.

## Before you call anything

This skill is a guide to the **live pyvar.com API**. It computes nothing by itself, and every
function needs the user's pyvar API key. Don't substitute your own numpy/scipy code and present
the result as pyvar output: these are regulatory-grade functions and the user wants pyvar's own
numbers.

The key is the user's to hold. Never look for it on their machine (environment variables, files,
shell history, other tools' settings), and don't ask them to paste it into the chat.

1. **Call through the pyvar MCP server.** The `pyvar-mcp` plugin asks the user for the key once,
   when they enable it, and keeps it in the system's secure credential store; its tools attach it
   to every call, so you never handle it. Use
   `call_pyvar_function(domain="derivatives", function_name="<function>", params=body)` with the
   request body below (every example in this skill is a real, tested request), and
   `list_pyvar_functions` to browse.
2. **No pyvar tools available? Say so, and walk the user through setting them up** (free, about
   a minute). First, get a key: open https://www.pyvar.com#get-api-key, then either click "Sign in with Google" (when
   it is shown) or enter an email and click the link we send (single use; the same form signs
   returning users in). The dashboard opens with a first API key already created: a string
   starting `pyvar_`, shown once. A key lasts a year and can be revoked or replaced on the
   dashboard at any time. Then install the `pyvar-mcp` plugin (the `/plugin` Discover tab, or
   `/plugin install pyvar-mcp@pyvar-marketplace`); Claude Code asks for the key when it is
   enabled. On a `401 Invalid, revoked or expired API key`, send the user back to the dashboard to
   create a new one.
3. **Cannot use MCP, or cannot run code or reach the network** (for example a sandbox with no
   internet)? Give the user the exact request to run themselves, with their own key where the
   placeholder is, instead of guessing a result:
   - Python: `pip install pyvar-client`, then
     `Client(api_key="<your pyvar key>").derivatives.<function>(**body)`.
   - REST: `POST https://www.pyvar.com/api/v1/derivatives/<function>` with header
     `Authorization: Bearer <your pyvar key>` and the body as JSON.
4. **Read the response.** Every function returns one JSON object. Quote the key numbers together
   with the inputs you used (and units: rates and returns are decimals, so 0.02 means 2%).

Errors: `401` bad or expired key; `422` a parameter is wrong (the `detail` field names it: fix it
and retry, never resend the same body); `429` the daily quota is used up (free tier: 10 calls per
day across all pyvar functions; the `Retry-After` header is in seconds): tell the user instead of
retrying in a loop.

## Worked examples

Each request body below is the same set of keyword arguments for the Python client, the REST body and the MCP `params`. They were run against the real API.

### 1. Black-Scholes call price and Greeks

A six-month at-the-forward call. `tau` is in years, `rate` and `sigma` are decimals. Vega is per 1.00 of volatility (divide by 100 for per volatility point).

`POST /api/v1/derivatives/black_scholes_european_option`

```json
{
  "spot": 100,
  "strike": 105,
  "rate": 0.03,
  "sigma": 0.2,
  "tau": 0.5,
  "option_type": "call"
}
```

Returns: `price`, `d1`, `d2`.

`POST /api/v1/derivatives/black_scholes_greeks`

```json
{
  "spot": 100,
  "strike": 105,
  "rate": 0.03,
  "sigma": 0.2,
  "tau": 0.5,
  "option_type": "call"
}
```

Returns: `delta`, `gamma`, `vega`, `theta`, `rho`.

### 2. Fixed-coupon bond price and modified duration

A 10-year 5% semi-annual bond priced at a 4% yield, then its modified duration from the same cash flows (times in years).

`POST /api/v1/derivatives/bond_pricer_fixed_coupon`

```json
{
  "face_value": 100,
  "coupon_rate": 0.05,
  "yield_rate": 0.04,
  "maturity": 10,
  "frequency": 2
}
```

Returns: `price`, `clean_price`, `cashflows`.

`POST /api/v1/derivatives/modified_duration`

```json
{
  "cashflows": [2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 102.5],
  "times": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0],
  "yield_rate": 0.04,
  "frequency": 2
}
```

Returns: `modified_duration`, `macaulay_duration`, `price`.

## Functions (62)

Every function is `POST /api/v1/derivatives/<name>`. Required parameters are listed bare, optional ones with their defaults (`name=default`). Types, bounds and formulas are in `references/functions.md`, in this plugin's folder: read the entry before calling a function you have not used yet.

### Vanilla Options (BS & Trees)

- `black_scholes_european_option(spot, strike, rate, sigma, tau, option_type='call', div_yield=0.0)`: Black-Scholes-Merton price of a European option.
- `black_scholes_greeks(spot, strike, rate, sigma, tau, option_type='call', div_yield=0.0)`: Closed-form Black-Scholes first-order Greeks.
- `binomial_tree_option_pricer(spot, strike, rate, sigma, tau, n_steps=500, option_type='call', style='european', div_yield=0.0)`: Cox-Ross-Rubinstein binomial tree option price.
- `trinomial_tree_option_pricer(spot, strike, rate, sigma, tau, n_steps=300, option_type='call', style='european', div_yield=0.0)`: Boyle trinomial tree option price.
- `monte_carlo_option_pricer(spot, strike, rate, sigma, tau, n_simulations=100000, option_type='call', div_yield=0.0, seed=12345)`: Monte Carlo price of a European option (terminal GBM payoff).

### Stochastic Volatility Models

- `heston_stochastic_volatility_model(spot, strike, rate, tau, v0, kappa, theta, sigma, rho, option_type='call')`: Heston stochastic-volatility European option price (semi-analytic).
- `sabr_volatility_model(forward, strike, tau, alpha, beta, rho, nu)`: SABR implied (lognormal/Black) volatility via Hagan's expansion.
- `local_volatility_dupire_model(strikes, maturities, call_surface, rate, spot)`: Dupire local volatility surface from a call-price surface.
- `rough_volatility_rbergomi_model(spot, strike, rate, tau, xi=0.04, eta=1.5, hurst=0.1, rho=-0.7, n_steps=50, n_simulations=50000, option_type='call', seed=2024, control_variate=False, greeks=False)`: Rough Bergomi (rBergomi) European option price via Monte Carlo.
- `variance_gamma_model(spot, strike, rate, tau, sigma=0.2, theta=-0.1, nu=0.2, n_simulations=100000, option_type='call', seed=7, greeks=False)`: Variance Gamma European option price via Monte Carlo.
- `normal_inverse_gaussian_model(spot, strike, rate, tau, alpha=15.0, beta=-5.0, delta=0.5, n_simulations=100000, option_type='call', seed=11, greeks=False)`: Normal Inverse Gaussian European option price via Monte Carlo.
- `displaced_diffusion_model(spot, strike, rate, sigma, tau, displacement, option_type='call', div_yield=0.0)`: Displaced-diffusion (shifted lognormal) European option price.

### Exotic Options

- `digital_option_pricer(spot, strike, rate, sigma, tau, option_type='call', payout=1.0, div_yield=0.0)`: Cash-or-nothing digital (binary) option price.
- `barrier_option_pricer(spot, strike, barrier, rate, sigma, tau, option_type='call', barrier_type='down-and-out', div_yield=0.0, rebate=0.0)`: Single-barrier option price (Reiner-Rubinstein closed form), with a.
- `asian_option_pricer(spot, strike, rate, sigma, tau, n_steps=100, n_simulations=100000, option_type='call', average_type='arithmetic', div_yield=0.0, seed=21, qmc=False, greeks=False)`: Arithmetic-average Asian option price via Monte Carlo.
- `lookback_option_pricer(spot, strike, rate, sigma, tau, n_steps=100, n_simulations=100000, option_type='call', strike_type='floating', div_yield=0.0, seed=31, qmc=False, greeks=False)`: Lookback option price via Monte Carlo.
- `american_option_lsm(spot, strike, rate, sigma, tau, n_steps=50, n_simulations=100000, option_type='put', div_yield=0.0, seed=41, greeks=False)`: American option price via Longstaff-Schwartz Monte Carlo (LSM).
- `bermudan_option_pricer(spot, strike, rate, sigma, tau, exercise_dates=4, n_steps=48, n_simulations=100000, option_type='put', div_yield=0.0, seed=51, greeks=False)`: Bermudan option price via LSM with discrete exercise dates.
- `rainbow_option_pricer(spots, strike, rate, sigmas, tau, correlation, n_simulations=100000, option_type='call', rainbow_type='best-of', seed=61, greeks=False)`: Rainbow (best-of / worst-of) option price via Monte Carlo.
- `basket_option_pricer(spots, weights, strike, rate, sigmas, tau, correlation, n_simulations=100000, option_type='call', seed=71, greeks=False)`: Basket option price via Monte Carlo on a weighted sum of assets.
- `spread_option_kirk_approximation(spot1, spot2, strike, rate, sigma1, sigma2, rho, tau, option_type='call')`: Spread option price via Kirk's approximation.
- `compound_option_pricer(spot, strike_underlying, strike_compound, rate, sigma, tau_compound, tau_underlying, n_simulations=200000, compound_type='call-on-call', div_yield=0.0, seed=81, greeks=False)`: Compound option (option-on-option) price via the Geske (1979) closed form.
- `chooser_option_pricer(spot, strike, rate, sigma, tau_choose, tau_expiry, div_yield=0.0)`: Simple chooser option price (closed form).

### Fixed Income Instruments

- `bond_pricer_fixed_coupon(face_value, coupon_rate, yield_rate, maturity, frequency=2)`: Price a fixed-coupon bond by discounting its cashflows at a flat yield.
- `bond_pricer_floating_rate(face_value, reference_rates, spread, discount_rates, maturity, frequency=4)`: Price a floating-rate note (FRN) from projected forward rates.
- `zero_coupon_bond_pricer(face_value, yield_rate, maturity, frequency=2)`: Price a zero-coupon bond: ``face / (1 + y/m)^{m·T}``.
- `inflation_linked_bond_pricer(face_value, real_coupon_rate, real_yield, maturity, inflation_rate, frequency=2)`: Price an inflation-linked (real) bond with index-uplifted principal.
- `callable_bond_pricer(face_value, coupon_rate, short_rate, rate_vol, maturity, call_price, frequency=1)`: Price a callable bond (issuer's option) on a short-rate binomial tree.
- `puttable_bond_pricer(face_value, coupon_rate, short_rate, rate_vol, maturity, put_price, frequency=1)`: Price a puttable bond (holder's option) on a short-rate binomial tree.
- `convertible_bond_pricer(face_value, coupon_rate, yield_rate, maturity, conversion_ratio, stock_price, frequency=2)`: Price a convertible bond via the bond-floor + conversion-value maximum.

### Bond Analytics

- `modified_duration(cashflows, times, yield_rate, frequency=2)`: Modified duration = Macaulay duration / (1 + y/m).
- `effective_duration(price_base, price_up, price_down, yield_shock)`: Effective duration from re-priced bond values under a parallel shock.
- `convexity(cashflows, times, yield_rate, frequency=2)`: Bond convexity — the second-order yield sensitivity (always >= 0 for.
- `dv01_pvbp(cashflows, times, yield_rate, frequency=2)`: DV01 / PVBP — price change for a 1 basis-point yield move.
- `yield_to_maturity(price, cashflows, times, frequency=2)`: Yield to maturity — the flat rate that discounts cashflows to ``price``.
- `yield_to_call(price, face_value, coupon_rate, call_price, call_date, frequency=2)`: Yield to call — yield assuming redemption at the first call date.
- `asset_swap_spread(bond_price, cashflows, times, swap_rates, face_value=100.0, frequency=2, use_market_price=False)`: Par-par asset-swap spread.
- `z_spread_calculator(price, cashflows, times, zero_rates, frequency=2)`: Z-spread — constant spread over the zero curve that reprices the bond.
- `oas_option_adjusted_spread(market_price, face_value, coupon_rate, short_rate, rate_vol, maturity, call_price, frequency=1)`: Option-adjusted spread of a callable bond.
- `duration_macaulay(cashflows, times, yield_rate, frequency=2)`: Macaulay duration — PV-weighted average time to cashflows (in years).

### Yield Curve Construction

- `nelson_siegel_curve_fit(maturities, yields, tau_init=1.5)`: Fit a Nelson-Siegel curve to observed yields.
- `nelson_siegel_svensson_curve(maturities, yields, tau1_init=1.5, tau2_init=8.0)`: Fit the Nelson-Siegel-Svensson (six-parameter) curve.
- `bootstrap_yield_curve(par_rates, maturities, frequency=1, face_value=1.0)`: Bootstrap zero (spot) rates from par-coupon bond rates.
- `swap_rate_curve(discount_factors, maturities, frequency=1)`: Par swap rates implied by a discount-factor curve.
- `ois_curve_sonia_sofr(ois_rates, maturities, frequency=1)`: Build an OIS (SONIA/SOFR) discount curve from quoted OIS swap rates.

### Swaps, Caps, Swaptions & Rate Models

- `cross_currency_swap_pricer(notional_dom, notional_for, fixed_rate_dom, fixed_rate_for, df_dom, df_for, accruals, fx_spot, pay_domestic=True)`: Price a fixed-fixed cross-currency swap (with notional exchange).
- `overnight_index_swap_ois(notional, fixed_rate, compounded_rate, accrual, discount_factor, pay_fixed=True)`: Value a single-period overnight index swap.
- `total_return_swap_trs(notional, asset_return, financing_rate, accrual, discount_factor, receive_total_return=True)`: Value a total-return swap leg.
- `credit_default_swap_cds_pricer(notional, spread, hazard_rate, recovery_rate, maturity, discount_rate, frequency=4)`: Price a CDS via a flat-hazard-rate reduced-form model with.
- `equity_swap_pricer(notional, equity_return, funding_rate, accrual, discount_factor, receive_equity=True)`: Value an equity swap leg (equity return vs funding).
- `caplet_floorlet_pricer_black(notional, forward_rate, strike, vol, expiry, accrual, discount_factor, option_type='caplet')`: Price a single caplet/floorlet under the Black (lognormal) model.
- `cap_floor_pricer(notional, forward_rates, strike, vols, expiries, accruals, discount_factors, option_type='cap')`: Price an interest-rate cap/floor as a strip of caplets/floorlets.
- `swaption_pricer_black(notional, forward_swap_rate, strike, vol, expiry, annuity, option_type='payer')`: Price a European swaption under the Black model.
- `swaption_pricer_sabr(notional, forward_swap_rate, strike, expiry, annuity, alpha, beta, rho, nu, option_type='payer')`: Price a swaption using a SABR-implied Black volatility.
- `lmm_bgm_rate_model(forward_rates, vols, tenor, horizon, n_steps=20, n_simulations=20000, seed=104)`: LIBOR Market Model (BGM) forward-rate Monte Carlo simulation.
- `forward_rate_agreement_fra(notional, fra_rate, forward_rate, start, end, discount_factor)`: Mark-to-market value of a forward rate agreement (long = pay fixed).
- `interest_rate_swap_irs_pricer(notional, fixed_rate, forward_rates, discount_factors, accruals, pay_fixed=True)`: Price a vanilla fixed-vs-float interest-rate swap.

### Short-Rate Models

Live in `engine/deriv_short_rate.py` (not FX — see naming note below).

- `hull_white_short_rate_model(r0, kappa, sigma, maturity, theta_const=0.03, n_steps=100, n_simulations=50000, seed=103)`: Hull-White one-factor model with a constant mean-reversion level.
- `cox_ingersoll_ross_model(r0, kappa, theta, sigma, maturity, n_steps=100, n_simulations=50000, seed=102)`: CIR model: closed-form ZCB price + simulated (non-negative) short rate.
- `vasicek_interest_rate_model(r0, kappa, theta, sigma, maturity, n_steps=100, n_simulations=50000, seed=101)`: Vasicek model: closed-form zero-coupon bond price + simulated short rate.

### FX Derivatives

- `fx_forward_pricer(spot, rate_domestic, rate_foreign, tau, notional=1.0, contracted_forward=None)`: FX forward rate and mark-to-market via covered interest-rate parity.
- `fx_option_pricer_garman_kohlhagen(spot, strike, rate_domestic, rate_foreign, sigma, tau, option_type='call', notional=1.0)`: Garman-Kohlhagen FX option price.

## Naming convention
- Prices in clean price (bonds, `bond_pricer_fixed_coupon` also returns a separate
  `clean_price` key) or premium (options)
- option_type: "call" | "put"
- style: "european" | "american" — only on `binomial_tree_option_pricer` /
  `trinomial_tree_option_pricer`. Bermudan exercise is **not** a `style` value; it's the
  separate `bermudan_option_pricer` function.
- There is no `day_count` parameter anywhere in this domain (no "Act/365" / "Act/360" /
  "30/360" convention selector exists in `engine/deriv_*.py` or `schemas/derivatives.py`
  today — don't invent one when writing example calls).
- Return dicts are model-specific, not a fixed `{"price", "greeks", "model_params"}`
  shape. Common patterns actually in the code: closed-form pricers return `{"price", ...}`
  plus 1-2 diagnostic fields (e.g. `digital_option_pricer` → `{"price", "d2"}`); MC
  pricers return `{"price", "std_error"}`; `greeks=True` adds `delta`, `gamma`, `vega`,
  `theta`, `rho` as top-level sibling keys (not nested under a `"greeks"` key) — see
  below. A few models don't return "price" at all: `sabr_volatility_model` →
  `{"implied_vol"}`, `local_volatility_dupire_model` → `{"local_vol", "strikes_inner",
  "maturities_inner"}`, `heston_stochastic_volatility_model` → `{"price", "P1", "P2"}`.
## Greeks (opt-in, bump-and-reprice)

`greeks: bool = False` on the pricer's own signature — not a separate function, not a
`black_scholes_greeks`-style dedicated endpoint. Central-difference bump-and-reprice
against the base run's own pre-drawn random numbers (common random numbers, so MC noise
cancels in the difference instead of adding to it). Verified support, exhaustively:

- **Supports `greeks=True`**: `asian_option_pricer`, `lookback_option_pricer`,
  `american_option_lsm`, `bermudan_option_pricer`, `rainbow_option_pricer` (per-asset
  delta/gamma/vega, diagonal only — no cross-gammas), `basket_option_pricer` (same),
  `compound_option_pricer` — all in `engine/deriv_options_exotic.py` — plus
  `rough_volatility_rbergomi_model`, `variance_gamma_model`,
  `normal_inverse_gaussian_model` in `engine/deriv_stoch_vol.py`.
- **Does not support it**: `digital_option_pricer`, `barrier_option_pricer`,
  `spread_option_kirk_approximation`, `chooser_option_pricer` (all closed-form — use
  `black_scholes_greeks`-style analytic differentiation instead if needed), and
  `heston_stochastic_volatility_model`, `sabr_volatility_model`,
  `local_volatility_dupire_model`, `displaced_diffusion_model` (closed-form /
  semi-analytic, no MC noise to reuse via common random numbers).
- LSM products (`american_option_lsm`, `bermudan_option_pricer`) use a **30x larger**
  spot bump than the rest (3% of spot vs. 0.1%): the early-exercise regression's
  ITM/continue decision is discontinuous in spot, and at the standard 0.1% bump the
  reported gamma came out negative with a std ~4x its own (already wrong) mean; at 3% it
  converges to a small positive value consistent with the closed-form European gamma.
- `greeks=True` is mutually exclusive with `qmc=True` and with `control_variate=True`
  (raises `ValueError`) — deferred, not silently ignored.
## Variance reduction — verified per-function, not domain-wide

Three distinct techniques were added to this codebase; none of them cover every pricer,
and antithetic variates in particular are **not** part of this domain at all:

- **Randomized-QMC (scrambled Sobol, `qmc: bool = False`)**: only
  `asian_option_pricer` and `lookback_option_pricer`. Deliberately **rejected** for
  `american_option_lsm`: scrambled-Sobol points are correlated by design (that's what
  gives QMC its edge), which biases the LSM continuation-value regression and, through
  it, the exercise decision — measured at S=K=100, r=5%, σ=20%, τ=1 against a 200k-path
  plain-MC reference (~6.024), plain MC at n=6k–20k was biased +0.03 to +0.04, QMC
  replicates at the same budget were biased +0.08 to +0.31 and didn't vanish by n=20k.
  Revisit only with a regression-bias fix, not by retuning replicate count.
- **Heston-companion control variate (`control_variate: bool = False`)**: only
  `rough_volatility_rbergomi_model`. A Heston path is simulated on rBergomi's own shared
  `z_v`/`z_s` draws (shared randomness is what makes it a valid control); the exact
  reference price comes from `heston_stochastic_volatility_model`. Verified ~2x–6x
  variance reduction with no measurable bias, weaker than QMC's ~20x/~7x above because
  rBergomi's actual rough-vol dynamics differ structurally from Heston's Markovian CIR
  process.
- **Antithetic variates (`antithetic: bool = False`)**: added to `run_monte_carlo_var`
  in `engine/montecarlo.py` — the **market-risk VaR/ES engine**, a different domain
  entirely. There is no antithetic option anywhere in `engine/deriv_*.py`. Don't
  document or assume it for any derivatives pricer.
## rBergomi kernel fix — what "the missing fractional-Brownian structure" means

`rough_volatility_rbergomi_model` had three independent numerical-correctness bugs,
fixed together (see `_rbergomi_volterra_driver`, `_rbergomi_discrete_variance`,
`_rbergomi_paths` in `engine/deriv_stoch_vol.py` for the current, corrected code):

1. **Wrong autocovariance structure.** The fractional Volterra driver
   `∫(t-s)^(H-0.5) dW_s` must weight each Brownian increment by its **gap to the
   current evaluation time**, recomputed at every later step. The buggy version froze
   each increment's weight at `(t_j)^(H-0.5)` — the value at the moment it was drawn —
   and never revisited it. Both formulations Riemann-sum to the same marginal variance
   at any single time point, so a price-band test against flat Black-Scholes couldn't
   see the defect at all; only a two-time-point check (a hand-computed impulse-response
   test) can, because the bug is specifically in how the process correlates across
   time — which is the entire point of "rough" volatility.
2. **Martingale correction used the continuum limit.** The variance process's drift
   correction used `t^(2H)`, but the naive discrete Riemann sum underestimates that
   substantially at this model's default `n_steps=50` (~59% of the continuum value at
   H=0.1), pulling `E[var_t]` to ~0.60× `xi` instead of `xi`. Fixed with the exact
   discrete sum in closed form.
3. **Non-predictable variance.** The variance applied to a step's price shock was
   computed from that *same* step's own Brownian draw, correlating "random" volatility
   with the shock it should be independent of and breaking the risk-neutral drift.
   Surfaced via put-call parity (`C - P` must equal `S - K·e^{-rT}` for any risk-neutral
   Itô process): it was off by more than 15 against a correct value of ~1.98 — not a
   rounding-level miss.

Lesson for anyone touching MC kernels here: a single-band price-level sanity test (e.g.
"price is between 0.3x and 2x flat-vol Black-Scholes") cannot detect a bug that only
affects how a process behaves across multiple time points. Rough-vol / path-dependent
kernels need at least one test that checks two or more time points against each other
(autocovariance, put-call parity at the model's own default parameters, or a known
reduction limit), not just a terminal-price band.
## QuantLib cross-validation — real, but scoped

QuantLib is a **test-only** dependency (see Architecture context above). Real,
independently-implemented cross-checks exist in `tests/validation/test_derivatives_ref.py`
for: Black-Scholes, `sabr_volatility_model` (`ql.sabrVolatility`, ATM + 4 off-ATM
strikes), `heston_stochastic_volatility_model` (`AnalyticHestonEngine`, realistic
vol-of-vol), `spread_option_kirk_approximation` (`KirkEngine` +
`SpreadBasketPayoff`, multiple nonzero strikes), `variance_gamma_model`
(`VarianceGammaEngine`, MC-vs-semi-analytic within 5x the reported `std_error`),
`local_volatility_dupire_model` (convergence check, not exact match), bond pricing +
duration/convexity, `vasicek_interest_rate_model`, `cox_ingersoll_ross_model`, and
`credit_default_swap_cds_pricer`. The CDS check is deliberately **not** an exact-match
assertion: `ql.MidPointCdsEngine` settles default losses at each accrual period's
midpoint while this engine's own formula settles at the period end — two legitimate but
different discretizations of the same continuous-time integral. Confirmed (not assumed)
by running `ql.IntegralCdsEngine` at shrinking step sizes and observing convergence
toward the engine's own price. Not every pricer in this domain has a QuantLib check —
check `tests/validation/test_derivatives_ref.py` directly before assuming coverage for
a function not listed above.
## For contributors: dependencies
numpy >= 1.26 · scipy >= 1.13 · pandas >= 2.2 · QuantLib >= 1.33 (test-only, via
`requirements-heavy.txt` — the `QuantLib` PyPI package name, not the legacy
`quantlib-python` alias) · numba >= 0.59

## For contributors: architecture context
- **Compute**: NumPy/Numba (MC pricing), SciPy (calibration, integration). QuantLib is a
  *test-only* dependency here (`requirements-heavy.txt`) — it backs `tests/validation/`
  cross-validation (see below) but is never imported by `engine/` or `api/`.
- **Queue**: none. `api/routes/derivatives.py` is auto-generated (`scripts/gen_p3.py`) and
  calls each engine wrapper **synchronously, in-process** — no Celery task, no job ID, no
  polling. This is unlike `/var/compute`, which is async via Celery/SQS with a `VaRJob`
  audit row. Don't assume derivatives pricing follows the VaR job-submission pattern.
- **Storage**: none. No Redis cache, no PostgreSQL persistence, no S3 offload for
  derivatives results — every request is computed fresh and returned in the response body.
- **API**: `POST /api/v1/derivatives/{function_name}` — one route per engine function, path
  name matches the Python function name exactly (e.g. `POST
  /api/v1/derivatives/rough_volatility_rbergomi_model`).

---

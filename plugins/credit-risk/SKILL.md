---
name: pyvar-credit-risk
description: >
  Run pyvar's 55 credit-risk functions on the live pyvar.com API: expected loss, PD/LGD/EAD,
  Vasicek and Monte Carlo credit VaR, IRB and standardised capital, SA-CCR and XVA
  (CVA/DVA/FVA), CDS pricing, IFRS 9 ECL, Altman Z and other scoring models. Use when the user
  wants credit-risk numbers computed rather than only explained. Needs a free pyvar API key;
  the skill explains how to get one.
version: "1.1.0"
author: "Fibtec Limited — pyvar.com"
tags: [credit-risk, PD, LGD, EAD, IRB, XVA, CVA, IFRS9, ECL, CDS, CCR, SA-CCR, KMV, Merton, scoring]
---

# pyvar — Credit Risk  (55 functions)

Credit-risk calculations: expected and unexpected loss, regulatory capital, portfolio credit models, counterparty risk and XVA, CDS, IFRS 9 ECL and scoring. Pick the function in **Functions** below; the **Worked examples** show the request shape.

## Before you call anything

This skill is a guide to the **live pyvar.com API**. It computes nothing by itself, and every
function needs a pyvar API key. Don't substitute your own numpy/scipy code and present the result
as pyvar output: these are regulatory-grade functions and the user wants pyvar's own numbers.

1. **Find the key.** Look for `PYVAR_API_KEY` in the environment. If the pyvar MCP server is
   connected, its tools (`call_pyvar_function`, `list_pyvar_functions`) already carry the key.
2. **No key? Say so, and walk the user through getting one** (free, about a minute): open
   https://www.pyvar.com#get-api-key, then either click "Sign in with Google" (when it is shown) or enter an email and
   click the verification link (valid 24 hours, single use). The page shows the key once. Ask the
   user to copy it and set `PYVAR_API_KEY`. Keys are short-lived (60 minutes by default). On a
   `401 Invalid or expired token`, ask for a fresh one: Google sign-in issues a new key every time,
   whereas the emailed link cannot be reused, so an address that cannot sign in with Google has to
   register a different email.
3. **Call the function** with the request body below (every example in this skill is a real,
   tested request). Use whichever of these is available:
   - Python: `pip install pyvar-client`, then
     `Client(api_key=os.environ["PYVAR_API_KEY"]).credit_risk.<function>(**body)`.
   - REST: `POST https://www.pyvar.com/api/v1/credit-risk/<function>` with header
     `Authorization: Bearer $PYVAR_API_KEY` and the body as JSON.
   - MCP: `call_pyvar_function(domain="credit-risk", function_name="<function>", params=body)`.
   If you cannot run code or reach the network (for example a sandbox with no internet), give the
   user the exact `curl` command or Python snippet to run themselves instead of guessing a result.
4. **Read the response.** Every function returns one JSON object. Quote the key numbers together
   with the inputs you used (and units: rates and returns are decimals, so 0.02 means 2%).

Errors: `401` bad or expired key; `422` a parameter is wrong (the `detail` field names it: fix it
and retry, never resend the same body); `429` the daily quota is used up (free tier: 10 calls per
day across all pyvar functions; the `Retry-After` header is in seconds): tell the user instead of
retrying in a loop.

## Worked examples

Each request body below is the same set of keyword arguments for the Python client, the REST body and the MCP `params`. They were run against the real API.

### 1. Expected loss and Vasicek credit VaR on a 50m exposure

Expected loss is PD x LGD x EAD. The Vasicek single-factor model then gives the 99.9% loss quantile (the Basel IRB confidence level) for a granular portfolio.

`POST /api/v1/credit-risk/expected_loss_el_computation`

```json
{
  "pd": 0.02,
  "lgd": 0.45,
  "ead": 50000000
}
```

Returns: `el`, `el_rate`, `pd`, `lgd`, `ead`.

`POST /api/v1/credit-risk/credit_var_analytical_vasicek`

```json
{
  "pd": 0.02,
  "lgd": 0.45,
  "ead_total": 50000000,
  "asset_correlation": 0.15,
  "confidence_level": 0.999
}
```

Returns: `var`, `el`, `ul`, `loss_rate_q`, `confidence_level`.

### 2. Altman Z-score for one borrower

Balance-sheet and income inputs in any one currency unit. The result carries the score and its zone (safe above 2.99, distress below 1.81).

`POST /api/v1/credit-risk/altman_z_score_credit_scoring`

```json
{
  "working_capital": 120,
  "retained_earnings": 300,
  "ebit": 90,
  "market_value_equity": 800,
  "sales": 1200,
  "total_assets": 1000,
  "total_liabilities": 400
}
```

Returns: `z_score`, `zone`, `x1`, `x2`, `x3`, `x4`, `x5`.

## Functions (55)

Every function is `POST /api/v1/credit-risk/<name>`. Required parameters are listed bare, optional ones with their defaults (`name=default`). Types, bounds and formulas are in [references/functions.md](references/functions.md): read the entry before calling a function you have not used yet.

### Core Credit Metrics (EL/UL/PD/LGD/EAD)

- `probability_of_default_pd_estimation(n_defaults, n_obligors, floor=0.0003)`: Estimate PD from observed default cohorts (cohort / frequency method).
- `loss_given_default_lgd_model(recovery_amounts, exposure_amounts, workout_cost_rate=0.0)`: Workout LGD as one minus the recovery rate, net of workout costs.
- `exposure_at_default_ead_calculator(drawn, undrawn, credit_conversion_factor=0.75)`: EAD for a revolving / committed facility via the CCF method.
- `expected_loss_el_computation(pd, lgd, ead)`: Expected Loss ``EL = PD * LGD * EAD``.
- `unexpected_loss_ul_computation(pd, lgd, ead)`: Stand-alone Unexpected Loss per exposure and the un-diversified sum.
- `recovery_rate_estimation(recovery_amounts, exposure_amounts, discount_factors=None)`: Estimate the recovery rate (1 - LGD) from a defaulted-facility sample.
- `downturn_lgd_adjustment(lgd_long_run, downturn_multiplier=1.0, floor=0.0, method='multiplicative')`: Basel downturn-LGD adjustment of a long-run average LGD.

### Regulatory Capital (IRB/SA)

- `irb_foundation_approach_capital(pd, ead, maturity=2.5, lgd=0.45, seniority='senior_unsecured')`: Basel IRB Foundation-Approach capital (CRE31).
- `irb_advanced_approach_capital(pd, lgd, ead, maturity=2.5, correlation=None)`: Basel IRB Advanced-Approach capital (CRE31).
- `basel_standardised_approach_rwa(ead, risk_weight, credit_risk_mitigation=0.0)`: Basel Standardised-Approach RWA (CRE20).
- `maturity_adjustment_basel_irb(pd, maturity)`: Basel IRB maturity adjustment (CRE31.6).
- `sme_correlation_factor_basel(pd, annual_sales_millions)`: Basel SME firm-size correlation adjustment (CRE31.10).

### Portfolio Credit Models

- `credit_var_monte_carlo(pd, lgd, ead, asset_correlation=0.15, confidence_level=0.999, n_simulations=50000, seed=12345)`: Monte-Carlo Credit VaR under a one-factor Gaussian copula.
- `credit_var_analytical_vasicek(pd, lgd, ead_total, asset_correlation=0.15, confidence_level=0.999)`: Analytical Vasicek large-homogeneous-portfolio Credit VaR.
- `creditmetrics_portfolio_model(exposures, pd, lgd, asset_correlation=0.2, confidence_level=0.99, n_simulations=20000, seed=2024, transition_matrix=None, current_rating=None, state_loss_pct=None)`: CreditMetrics portfolio loss distribution — two-state or genuine multi-state.
- `kmv_merton_distance_to_default(asset_value, debt_face_value, asset_volatility, risk_free_rate=0.0, asset_drift=None, horizon=1.0)`: Merton / KMV distance-to-default and implied PD.

### Credit Scoring & PD Models

- `altman_z_score_credit_scoring(working_capital, retained_earnings, ebit, market_value_equity, sales, total_assets, total_liabilities)`: Altman (1968) Z-score for public manufacturers.
- `logistic_regression_pd_model(features, defaults, max_iter=100, tol=1e-08, ridge=1e-06)`: Fit a logistic-regression PD model by Newton-Raphson (IRLS) MLE.
- `machine_learning_pd_calibration(raw_scores, defaults, max_iter=100, tol=1e-08)`: Platt-scaling calibration of raw ML scores into well-calibrated PDs.
- `through_the_cycle_pd_adjustment(pit_pd, long_run_average_pd, cyclicality=0.5)`: Convert a point-in-time PD to a through-the-cycle PD.
- `point_in_time_pd_estimation(ttc_pd, macro_index, sensitivity=1.0)`: Derive a point-in-time PD from a TTC PD and a macro factor.
- `retail_scorecard_pd_model(feature_values, points_per_feature, base_points, pdo=50.0, base_score=600.0, base_odds=50.0)`: Retail scorecard: additive points to a PD via the points-to-double-odds map.

### Migration & Correlation

- `default_correlation_matrix(pd, asset_correlation)`: Pairwise default correlation from asset correlations (Gaussian copula).
- `ratings_migration_matrix(from_rating, to_rating, n_states)`: Estimate a row-stochastic ratings-migration matrix (cohort method).

### Concentration Risk

- `credit_concentration_risk_hhi(exposures)`: Herfindahl-Hirschman concentration index of a credit portfolio.

### Counterparty Credit Risk (CCR/XVA)

- `current_exposure_method_cem(mark_to_market, notional, add_on_factor)`: Basel I/II Current Exposure Method (CEM) EAD.
- `standardised_approach_ccr_sa_ccr(mark_to_market, collateral, add_on_aggregate, alpha=1.4)`: Basel SA-CCR EAD (CRE52).
- `potential_future_exposure_pfe(initial_value, volatility, time_steps, quantile=0.95, drift=0.0, n_paths=20000, seed=909)`: Potential Future Exposure profile via Monte-Carlo (arithmetic BM proxy).
- `expected_positive_exposure_epe(expected_exposure, time_steps)`: Expected Positive Exposure — time-weighted average expected exposure.
- `effective_epe_regulatory(expected_exposure, time_steps)`: Basel Effective EPE (EEPE) with the non-decreasing Effective EE profile.
- `credit_valuation_adjustment_cva(expected_exposure, time_steps, discount_factors, credit_spread, recovery_rate=0.4)`: Unilateral Credit Valuation Adjustment.
- `debt_valuation_adjustment_dva(expected_negative_exposure, time_steps, discount_factors, own_credit_spread, own_recovery_rate=0.4)`: Debit Valuation Adjustment — the symmetric own-default benefit.
- `funding_valuation_adjustment_fva(expected_exposure, time_steps, discount_factors, funding_spread, survival_probability=None)`: Funding Valuation Adjustment — cost of funding uncollateralised exposure.
- `capital_valuation_adjustment_kva(capital_profile, time_steps, discount_factors, cost_of_capital=0.1)`: Capital Valuation Adjustment — lifetime cost of regulatory capital.
- `margin_valuation_adjustment_mva(initial_margin_profile, time_steps, discount_factors, margin_funding_spread)`: Margin Valuation Adjustment — funding cost of posted initial margin.
- `xva_aggregation(cva, dva=0.0, fva=0.0, kva=0.0, mva=0.0)`: Aggregate the XVA components into a total valuation adjustment.
- `cva_sensitivity_cva_greeks(expected_exposure, time_steps, discount_factors, credit_spread, recovery_rate=0.4, spread_bump=0.0001)`: CVA sensitivities — CS01 (credit delta) and exposure delta.
- `wrong_way_risk_adjustment(base_cva, correlation, exposure_volatility=0.3)`: Wrong-way-risk (WWR) multiplicative adjustment to CVA.
- `counterparty_credit_risk_ccr_exposure(mark_to_market, add_on, collateral=0.0)`: Generic CCR exposure = current exposure + add-on, net of collateral.
- `collateral_haircut_calculation(collateral_value, haircut_collateral, haircut_fx=0.0)`: Supervisory collateral haircut under the comprehensive approach (CRE22).

### CDS & Credit Derivatives

- `credit_spread_curve_bootstrap(tenors, par_spreads, recovery_rate=0.4)`: Bootstrap a piecewise-constant hazard / survival curve from CDS spreads.
- `cds_pricing_isda_standard(payment_times, accrual_factors, discount_factors, hazard_rate, contract_spread, notional=1.0, recovery_rate=0.4)`: ISDA-standard CDS present value (protection-buyer perspective).
- `cds_spread_to_pd_conversion(cds_spread, maturity, recovery_rate=0.4)`: Credit-triangle conversion of a CDS spread to PD.
- `credit_default_swap_var(notional, risky_annuity, spread_volatility, confidence_level=0.99, horizon_days=1, position='long_protection')`: Parametric VaR of a single-name CDS position from spread risk.

### IFRS 9 & ECL

- `ifrs_9_stage_classification_pd_threshold(pd_current, pd_origination, days_past_due=0, sicr_relative_threshold=2.0, sicr_absolute_threshold=0.02)`: IFRS 9 stage classification by the PD-threshold SICR rule.
- `ifrs_9_lifetime_ecl_stage_2_3(marginal_pd, lgd, ead, discount_factors, stage=2)`: IFRS 9 Stage 2/3 lifetime Expected Credit Loss.
- `ifrs_9_12_month_ecl_stage_1(pd_12m, lgd, ead, discount_factor=1.0)`: IFRS 9 Stage 1 (12-month) Expected Credit Loss.
- `ifrs_9_scenario_weighted_ecl(scenario_ecls, scenario_weights)`: Probability-weighted ECL across forward-looking macro scenarios.
- `macroeconomic_overlays_ecl(base_ecl, macro_factors, sensitivities, management_overlay=0.0)`: Apply forward-looking macroeconomic overlays to a base ECL.
- `ifrs_9_staging_criteria_assessment(pd_current, pd_origination, days_past_due=0, forbearance=False, watchlist=False, sicr_relative_threshold=2.0)`: Full IFRS 9 staging assessment combining quantitative and qualitative SICR.

### Specialised Credit Models

- `corporate_credit_scoring_model(factor_scores, factor_weights, pd_floor=0.0003, pd_anchor=0.5)`: Weighted-factor corporate credit score mapped to a PD.
- `sovereign_credit_risk_assessment(debt_to_gdp, fiscal_balance_pct, current_account_pct, fx_reserves_months, governance_score)`: Composite sovereign credit-risk score from macro-fiscal indicators.
- `sector_default_rate_analysis(sector_defaults, sector_obligors, sector_names=None)`: Per-sector default-rate analysis with a concentration of distress.
- `credit_portfolio_optimisation(expected_returns, expected_losses, max_weight=1.0, risk_aversion=1.0)`: Single-period credit-portfolio weight optimisation (return vs expected loss).
- `credit_stress_testing(pd, lgd, ead, pd_shock_multiplier=1.5, lgd_shock_multiplier=1.2)`: Credit stress test: multiplicative PD/LGD shocks on the loss profile.

## Known limitations (Tier 3 #2 reference-validation audit)

`tests/validation/test_credit_ref.py` cross-checks all 55 functions against an
independent reference per test (closed-form recomputation, a cited BIS/IASB
formula, or a scipy fit — never engine-against-itself). That audit found two
categories worth knowing before relying on this domain's outputs:

- **Functions with a genuinely bespoke formula and no published source**,
  checked against BIS/EBA documents and the WWR literature (Hull & White 2012;
  Gregory, *The xVA Challenge*) and confirmed not to match, rather than
  assumed to: `corporate_credit_scoring_model`, `sovereign_credit_risk_assessment`,
  `macroeconomic_overlays_ecl`, the PD/LGD shock-multiplier legs of
  `credit_stress_testing` (its baseline EL leg is definitional and is fine),
  and `wrong_way_risk_adjustment`. Their docstrings previously implied
  regulatory grounding (e.g. "EBA-style", CRR Art. 181) for the *exact
  formula*, when only the general concept — downturn LGD, forward-looking
  overlays, stress testing, WWR — is regulator-mandated, not this
  implementation's specific numbers. Treat these as reasonable internal
  models, not as reproductions of a specific regulatory or academic formula.
- **`downturn_lgd_adjustment`'s multiplier specifically**: EBA/GL/2019/03
  specifies an *additive* downturn fallback (+15pp to the long-run LGD), not
  a multiplicative one. The engine docstring is explicit that it deliberately
  does not implement that additive formula and instead applies a transparent
  `lgd_long_run * downturn_multiplier` scaling, clipped to `[floor, 1]` — pass
  a `downturn_multiplier` calibrated to your own downturn analysis, not `1.15`
  expecting it to reproduce the EBA fallback.

Two functions picked up a real, verified citation during the same audit and
can be trusted against a named source: `unexpected_loss_ul_computation`
matches Bluhm/Overbeck/Wagner, *An Introduction to Credit Risk Modeling*,
Ch. 1 exactly (deterministic-LGD Bernoulli UL = `EAD * LGD * sqrt(PD(1-PD))`),
and `retail_scorecard_pd_model`'s points-to-double-odds scaling matches
Siddiqi (2006), *Credit Risk Scorecards*.

Note also: this codebase has a *different* `solvency_ii_scr_credit_risk`
function (`engine/reg_solvency.py`) that is not part of this skill — it's
Solvency II Pillar 1 counterparty-default SCR, a `regulatory`-skill function
(DR (EU) 2015/35 Art. 200-201), not a banking IRB/IFRS 9/XVA credit-risk
function. Don't confuse the two by name.
## Naming convention
- PD: probability [0,1]; LGD: loss fraction [0,1]; EAD: currency amount
- XVA functions each return their named adjustment as the primary key
  (`cva`, `dva`, `fva`, `kva`, `mva`) plus supporting fields — not a uniform
  `NPV`/`delta`/`sensitivities` shape. Only `cva_sensitivity_cva_greeks`
  returns a sensitivity, and its keys are `cs01` and `exposure_delta`
  (bump-and-reprice), not a generic `delta`. `xva_aggregation` is the
  exception with a shared shape: `total_xva` + a `components` dict.
- IFRS 9 functions return ECL amount and staging classification
## For contributors: dependencies
numpy >= 1.24 · scipy >= 1.10 · numba >= 0.57

No credit-risk engine module (`engine/credit_*.py`) imports pandas,
scikit-learn, statsmodels, or QuantLib — "Machine Learning PD Calibration"
(`machine_learning_pd_calibration`) is a hand-rolled Platt-scaling fit on top
of the module's own Newton-Raphson logistic solver, not a scikit-learn model.
QuantLib cross-validation exists in this codebase (`tests/validation/
test_derivatives_ref.py`, extended in PR #192/task #16 to bonds and a CDS
pricer) but that CDS pricer is `credit_default_swap_cds_pricer` in
`engine/deriv_rates.py` — a different function in the **derivatives** skill,
not `credit_cds.py`'s `cds_pricing_isda_standard` here. No credit-risk
function in this skill has QuantLib cross-validation today.

## For contributors: architecture context
- **Compute**: NumPy/Numba (`@njit` kernels in every `engine/credit_*.py` module,
  incl. the parallel MC credit VaR loop), SciPy (Newton-Raphson logistic fit,
  `linprog` cross-validation)
- **API**: FastAPI endpoint `/api/v1/credit-risk/{function}` — one `POST` route
  per engine function (`api/routes/credit_risk.py`, auto-generated by
  `scripts/gen_p3.py`). Unlike `POST /var/compute`, these routes call the
  engine function directly in-request and return the result — there is no
  Celery dispatch, no job ID, and no result polling for this domain today.
  `tasks/` currently holds only `var_task.py`, and `storage/models.py` has no
  ECL/staging table (only `VaRJob`, `User`, `ApiUsage`) — results are not
  persisted server-side.

---

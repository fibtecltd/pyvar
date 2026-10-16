## Naming convention
- Return dict for multi-output metrics (the large majority — decompositions,
  fan charts, backtest reports); a handful of the pure P&L-attribution helpers
  return a single-key dict too (`engine/pnl_attribution.py` never returns a bare
  float). Do not assume every function accepts `returns` + `confidence` — Greeks
  (`engine/greeks.py`), stress scenarios (`engine/stress.py`) and most of
  Volatility & Correlation (`engine/volatility.py`) take instrument- or
  exposure-shaped inputs (spot/strike/vol/tau, exposure vectors, weights +
  covariance) instead, so check each function's own parameter list above — verified
  per-function against `engine/var_models.py`, `engine/expected_shortfall.py`,
  `engine/backtesting.py`, `engine/pnl_attribution.py`, `engine/greeks.py`,
  `engine/stress.py`, `engine/volatility.py` and `engine/frtb.py`.
- Confidence level: enforced range is **[0.90, 0.9999]** — `schemas/var.py`'s
  `confidence_must_be_standard` validator rejects anything outside it. Standard
  values (CLAUDE.md §4.1): **0.99** for 1-day VaR (Basel III) — the default on
  every VaR-family function in `engine/var_models.py`; **0.975** for 10-day ES
  (FRTB IMA) — the default on every function in `engine/expected_shortfall.py`;
  **0.95** acceptable for internal limit monitoring only. (0.999 is used
  elsewhere in pyvar — Credit VaR, AMA OpRisk capital — but is not a
  market-risk convention; don't carry it over here.)
- Horizon in trading days. `run_monte_carlo_var` and the VaR-family functions
  default to 1 day; `var_fan_chart` defaults to a 10-day projection horizon
  (it's built to show how the band widens with holding period, not a 1-day
  point estimate) — check the individual default before assuming 1.
- Monte Carlo simulation count is config-driven, not a fixed literal, and
  differs by call site: the `/var/compute` API request defaults to
  `cfg.default_n_simulations = 10_000` (capped per account tier up to
  `cfg.max_n_simulations = 500_000`, `config.py`), while calling
  `run_monte_carlo_var` / `monte_carlo_expected_shortfall` directly in Python
  defaults to **100,000** paths if `n_simulations` is omitted.
## Regulatory constants — verbatim from CLAUDE.md §4, do not paraphrase
These are Basel-Committee-set thresholds; the engine treats them as constants,
never as configurable parameters (`engine/backtesting.py`, `engine/pnl_attribution.py`).
- **Expected Shortfall** is the arithmetic **mean** of losses at/beyond the VaR
  index — never the median or the max (`engine/expected_shortfall.py::_tail_mean`,
  `engine/metrics.py::compute_cvar`). `cvar_decomposition_euler` /
  `expected_shortfall_contribution` are Euler-additive: components sum exactly
  to total ES.
- **Basel traffic-light backtest**: window is **exactly 250** trading days
  (`BASEL_BACKTEST_WINDOW = 250` in `engine/backtesting.py`). Breach zones:
  green `< 5`, yellow `5-9`, red `>= 10`. Capital add-on multiplier: `3.0`
  green, BCBS graduated schedule `3.40/3.50/3.65/3.75/3.85` for 5-9 breaches
  respectively, `4.0` red.
- **Kupiec / Christoffersen**: both are chi-squared likelihood-ratio tests
  rejected at the **95%** critical value (`stats.chi2.ppf(0.95, df=1)`, `df=2`
  for the combined conditional-coverage test) — this significance level is not
  a function parameter.
- **FRTB P&L Attribution Test** (`pnl_attribution_test_frtb_pat`): jointly
  evaluates Spearman rank correlation between RTPL and HPL and the ratio
  `std(RTPL)/std(HPL)`. Green requires `|corr| >= 0.80` **and**
  `0.8 <= ratio <= 1.2`; amber requires `|corr| >= 0.70` **and**
  `0.6 <= ratio <= 1.5`; anything below amber is red (IMA disqualification).
  These thresholds are hard-coded, not kwargs.
## Variance reduction — verified project history (task #15)
- **Antithetic variates (Phase 1)** were added to the core Monte Carlo VaR/ES
  kernel only: `engine/montecarlo.py::run_monte_carlo_var` takes an
  `antithetic: bool = False` flag. When `True`, `_draw_random_shocks` draws
  `n_simulations // 2` independent `N(0,1)` shocks and mirrors each as `(z, -z)`
  (with one extra unmirrored draw if `n_simulations` is odd, so the output
  shape is unchanged). Opt-in and off by default so existing callers/results
  are unaffected. As noted above, this flag is Python-engine-only — neither
  `/var/compute` nor `/api/v1/market-risk/*` exposes it today.
- **Sobol quasi-Monte Carlo (Phase 2) was NOT added to any market-risk VaR/ES
  kernel.** It exists in `engine/deriv_options_exotic.py` (randomized scrambled-Sobol
  replicates, `qmc: bool` opt-in on the exotic-option MC pricers) — a
  **derivatives-pricing** kernel, a different skill/domain entirely. Don't
  assume `monte_carlo_var_parametric_normal` or `monte_carlo_expected_shortfall`
  support a `qmc` argument; they don't (`engine/var_models.py` and
  `engine/expected_shortfall.py` have no Sobol/QMC code path — verified by grep).
## Citations & numerical validation
- Market-risk engine functions are cross-checked in
  `tests/validation/test_market_ref.py` against an *external* reference computed
  independently inside the test (closed-form formulas, scipy cross-validation,
  hard-coded Basel/FRTB thresholds, or an independent hand-calculation) —
  **never against the function's own output.** Tolerance is 0.1% relative for
  VaR/ES/simulation-class figures and **zero** tolerance for regulatory zone
  boundaries and the 250-day rule.
- A citation-cleanup pass (CHANGELOG "Changed") removed misleading or
  self-authored regulatory citations from engine docstrings project-wide and
  documented genuine no-published-source gaps instead of citing sources that
  don't actually support the implementation. `test_market_ref.py` itself
  records the remaining honest limitation: Cornish-Fisher, Kupiec, EGARCH,
  GJR-GARCH, GARCH(1,1) mean-reversion, spectral risk measure, Greeks-based
  Taylor P&L, and the FRTB SBM/DRC/RRAO/liquidity-adjusted-ES/SES formulas are
  citable for *formula* provenance but BCBS publishes no end-to-end numeric
  worked example for them at these specific test inputs — don't add a fake
  "matches BCBS worked example" claim for those.
## Coverage note
`pyvar_functions.csv` (the source for the "68 functions" figure above) is a
stale P2-era snapshot. The live, generated catalogue (`portal/functions.json`,
built from the running OpenAPI schema) lists **71** market-risk routes — the
gap is largely 4 legacy `engine/metrics.py` routes (`compute_cvar`,
`compute_rolling_var`, `compute_loss_percentiles`, `compute_breaches`) that
duplicate newer, already-listed entries (`conditional_var_es`,
`rolling_var_backtest`, `expected_shortfall`/fan-chart internals,
`traffic_light_backtesting`) but are wired as separate live routes. See
`docs/p9-function-catalogue-reconciliation.md` for the full reconciliation —
treat `portal/functions.json` as canonical if the two ever disagree.
## For contributors: dependencies
numpy >= 1.24 · scipy >= 1.10 · pandas >= 2.0 · statsmodels >= 0.14
numba >= 0.57 · arch >= 6.0

## For contributors: architecture context
- **Compute**: NumPy/Numba (MC loops, JIT), SciPy/statsmodels (GARCH, PCA)
- **Queue**: Celery + Redis (async VaR jobs)
- **Storage**: Redis cache (intraday VaR), PostgreSQL (backtest results)
- **API**: FastAPI endpoint `/api/v1/market-risk/{function}`

---

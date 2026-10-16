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

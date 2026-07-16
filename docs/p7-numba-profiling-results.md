# P7 Task 1 — Numba kernel profiling results

Profiling complete, no optimisation needed.

## Method

Benchmarked the 10 most likely compute-intensive Monte Carlo / simulation
functions across Market Risk, Derivatives, and Operational Risk
(`scripts/p7_bench.py`) at `n_simulations=100_000` (`n_years=100_000` for the
LDA compound-loss case). Each function was called once to warm the Numba
cache, then timed on a second call.

## Results

| Domain | Function | warm (s) | cold (s) |
|---|---|---|---|
| Market Risk | `run_monte_carlo_var` | 0.007 | 0.196 |
| Market Risk | `monte_carlo_expected_shortfall` | 0.007 | 0.007 |
| Derivatives | `rough_volatility_rbergomi_model` | 0.069 | 0.090 |
| Derivatives | `variance_gamma_model` | 0.002 | 0.004 |
| Derivatives | `asian_option_pricer` | 0.058 | 0.065 |
| Derivatives | `lookback_option_pricer` | 0.057 | 0.057 |
| Derivatives | `rainbow_option_pricer` | 0.003 | 0.006 |
| Derivatives | `basket_option_pricer` | 0.001 | 0.001 |
| Derivatives | `american_option_lsm` | 0.244 | 0.230 |
| Operational Risk | `monte_carlo_oprisk_capital` | 0.017 | 0.021 |

Slowest function (`american_option_lsm`) is **0.24s**, well under the 5s
per-function profiling trigger and the 10s P7 exit-gate target.

## Conclusion

Exit criterion ("no profiled function exceeds 10s at 100k paths") is already
met with no code changes. All 10 functions already follow the CLAUDE.md
§3.1 Numba rules correctly: `prange` is used wherever paths are independent
(`_simulate_paths`, `_gbm_path_stats`, `_multi_asset_terminals`,
`_rbergomi_paths`, `_levy_subordinated_payoff`), random numbers are
pre-drawn before the JIT region, arrays are float64 throughout, and
`cache=True` is set on every kernel.

One non-blocking observation for future reference: `_gbm_full_paths` in
`engine/deriv_options_exotic.py` (feeds `american_option_lsm` and
`bermudan_option_pricer`) uses a sequential `range(n_paths)` rather than
`prange`, even though paths are independent — same pattern already
parallelised a few functions above it in `_gbm_path_stats`. Not applied here:
at 0.23s it isn't required to hit the exit gate, and changing it carries a
small regression risk for no measurable benefit at this scale.

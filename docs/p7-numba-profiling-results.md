# P7 Task 1 — Numba kernel profiling results

Profiling complete, no optimisation needed.

**Correction (post-review):** the original version of this document reported
a "cold" column that was not actually a first-ever-compile measurement — see
*Methodology correction* below. The corrected numbers still support the same
conclusion (no code changes needed), but the true cold-start cost is
materially higher for at least one function than first reported.

## Method

Benchmarked the 10 most likely compute-intensive Monte Carlo / simulation
functions across Market Risk, Derivatives, and Operational Risk
(`scripts/p7_bench.py`) at `n_simulations=100_000` (`n_years=100_000` for the
LDA compound-loss case). Each function is called twice: the first call is a
genuine first-ever JIT compile (`true_cold`), the second is steady-state
(`warm`). Every result is sanity-checked (finite, non-degenerate) before its
timing is recorded.

### Methodology correction

The first draft of this benchmark called each function twice in-process and
labelled the first call "cold". That is only a true cold-compile measurement
if Numba's on-disk cache (`NUMBA_CACHE_DIR`, `~/.cache/numba/` by default) is
empty. It was not: this machine already held compiled `.nbc`/`.nbi` artifacts
for these exact kernels from earlier sessions (confirmed via
`ls -la ~/.cache/numba/engine_*`, timestamped days before this benchmark ran).
So the original "cold" column measured disk-cache-warm, process-cold
overhead — it silently skipped the real LLVM compilation step.

The corrected script points `NUMBA_CACHE_DIR` at a fresh empty temp directory
*before* importing anything that touches Numba (Numba reads this env var
once, at import time — setting it later has no effect). This forces genuine
first-ever compilation on the first call in each run.

## Results (corrected)

| Domain | Function | true_cold (s) | warm (s) |
|---|---|---|---|
| Market Risk | `run_monte_carlo_var` | **1.083** | 0.007 |
| Market Risk | `monte_carlo_expected_shortfall` | 0.007 | 0.007 |
| Derivatives | `rough_volatility_rbergomi_model` | 0.328 | 0.068 |
| Derivatives | `variance_gamma_model` | 0.152 | 0.002 |
| Derivatives | `asian_option_pricer` | 0.209 | 0.058 |
| Derivatives | `lookback_option_pricer` | 0.057 | 0.058 |
| Derivatives | `rainbow_option_pricer` | 0.185 | 0.003 |
| Derivatives | `basket_option_pricer` | 0.001 | 0.001 |
| Derivatives | `american_option_lsm` | 0.331 | 0.244 |
| Operational Risk | `monte_carlo_oprisk_capital` | 0.118 | 0.011 |
| **TOTAL (all 10, one process)** | | **2.472** | 0.460 |

`run_monte_carlo_var`'s true cold cost (1.08s) is ~150x its originally
reported "cold" figure (0.196s) — it compiles `_simulate_paths`, a
`parallel=True` kernel, which costs materially more to JIT than the
sequential kernels in this batch. The aggregate true-cold total across all
10 functions (**2.47s**) lines up well with CLAUDE.md §11's documented
"Numba first-call compilation takes ~2s on fresh worker" — a useful
cross-validation of that known-issue note.

## Numeric sanity check

`american_option_lsm(spot=100, strike=100, rate=0.02, sigma=0.2, tau=1.0)` →
price = **7.0948**. Cross-checked against the closed-form Black-Scholes
European put for the same parameters = **6.9359** (computed independently via
`scipy.stats.norm.cdf`). The American price is correctly higher by a
plausible early-exercise premium (0.159) — American ≥ European always holds;
a lower American price would have indicated a broken LSM implementation.
`run_monte_carlo_var` output was checked for `cvar_pct >= var_pct` and a
full-length (100,000-entry) `loss_dist` — both hold.

Provenance was also checked directly: `american_option_lsm.__module__ ==
"engine.deriv_options_exotic"`, resolves to the real source file, is a plain
`function` object with no `__wrapped__` decorator chain, and `engine/*.py`
has no `lru_cache`/`memoize`/`functools.cache` usage anywhere — the benchmark
calls the real production function, not a stub or memoised wrapper.

## Conclusion

Even with the corrected true-cold numbers, the exit criterion ("no profiled
function exceeds 10s at 100k paths") is met with no code changes: the
slowest single true-cold compile is 1.08s and the slowest warm call is
0.244s, both far under the 5s profiling trigger and the 10s exit gate. All
10 functions already follow the CLAUDE.md §3.1 Numba rules correctly:
`prange` is used wherever paths are independent (`_simulate_paths`,
`_gbm_path_stats`, `_multi_asset_terminals`, `_rbergomi_paths`,
`_levy_subordinated_payoff`), random numbers are pre-drawn before the JIT
region, arrays are float64 throughout, and `cache=True` is set on every
kernel — meaning in production (where the Numba cache directory is
preserved on the EBS volume, per CLAUDE.md §11) only the *first* boot after
an engine code change pays the true-cold cost; subsequent boots are
disk-cache-warm, close to the `warm` column above.

One non-blocking observation for future reference: `_gbm_full_paths` in
`engine/deriv_options_exotic.py` (feeds `american_option_lsm` and
`bermudan_option_pricer`) uses a sequential `range(n_paths)` rather than
`prange`, even though paths are independent — same pattern already
parallelised a few functions above it in `_gbm_path_stats`. Not applied here:
at 0.33s true-cold / 0.24s warm it isn't required to hit the exit gate, and
changing it carries a small regression risk for no measurable benefit at
this scale.

"""P7 Task 1 — benchmark of the 10 hottest Monte Carlo kernels at n=100k.

Not part of the committed test suite — a throwaway profiling harness for the
perf/p7-numba-profiling branch.

CORRECTNESS NOTE (found during review — see docs/p7-numba-profiling-results.md):
a first-in-this-process call is only a genuine "true cold" (first-ever JIT
compile) measurement if Numba's on-disk cache is empty. This machine's
~/.cache/numba/ already held compiled artifacts for these exact kernels from
earlier sessions, so a naive "first call in this script" is disk-cache-warm,
not truly cold — it silently skips the ~1-2s LLVM compile step entirely.

To measure genuine cold-start cost, this script points NUMBA_CACHE_DIR at a
fresh empty temp directory *before* importing anything that touches Numba
(engine.* imports transitively import numba). That must happen before those
imports — Numba reads the cache directory from the environment once, at
import time, so setting os.environ later in the process has no effect.

Each function is then called twice in that fresh-cache process:
  true_cold — first call ever, forces real JIT compilation
  warm      — second call, same process, already compiled in memory
"true_cold" is what a freshly-launched worker pays before main.py's lifespan
warmup call runs (CLAUDE.md §11). "warm" is steady-state per-request cost
once that warmup has happened (or once the disk cache, preserved on the EBS
volume in production, is already populated from a prior boot).
"""

from __future__ import annotations

import os
import tempfile

_FRESH_CACHE_DIR = tempfile.mkdtemp(prefix="p7_bench_numba_cache_")
os.environ["NUMBA_CACHE_DIR"] = (
    _FRESH_CACHE_DIR  # must precede any numba-touching import
)

import time  # noqa: E402

import numpy as np  # noqa: E402

from engine.deriv_options_exotic import (  # noqa: E402
    american_option_lsm,
    asian_option_pricer,
    basket_option_pricer,
    lookback_option_pricer,
    rainbow_option_pricer,
)
from engine.deriv_stoch_vol import (  # noqa: E402
    rough_volatility_rbergomi_model,
    variance_gamma_model,
)
from engine.expected_shortfall import monte_carlo_expected_shortfall  # noqa: E402
from engine.montecarlo import run_monte_carlo_var  # noqa: E402
from engine.oprisk_lda import monte_carlo_oprisk_capital  # noqa: E402

RETURNS = np.random.default_rng(0).normal(0.0003, 0.012, 252)
CORR2 = np.array([[1.0, 0.3], [0.3, 1.0]])

CASES = [
    (
        "Market Risk",
        "run_monte_carlo_var",
        lambda: run_monte_carlo_var(
            RETURNS, portfolio_value=1_000_000.0, n_simulations=100_000
        ),
    ),
    (
        "Market Risk",
        "monte_carlo_expected_shortfall",
        lambda: monte_carlo_expected_shortfall(
            RETURNS, portfolio_value=1_000_000.0, n_simulations=100_000
        ),
    ),
    (
        "Derivatives",
        "rough_volatility_rbergomi_model",
        lambda: rough_volatility_rbergomi_model(
            100.0, 100.0, 0.02, 1.0, n_simulations=100_000
        ),
    ),
    (
        "Derivatives",
        "variance_gamma_model",
        lambda: variance_gamma_model(100.0, 100.0, 0.02, 1.0, n_simulations=100_000),
    ),
    (
        "Derivatives",
        "asian_option_pricer",
        lambda: asian_option_pricer(
            100.0, 100.0, 0.02, 0.2, 1.0, n_simulations=100_000
        ),
    ),
    (
        "Derivatives",
        "lookback_option_pricer",
        lambda: lookback_option_pricer(
            100.0, 100.0, 0.02, 0.2, 1.0, n_simulations=100_000
        ),
    ),
    (
        "Derivatives",
        "rainbow_option_pricer",
        lambda: rainbow_option_pricer(
            np.array([100.0, 100.0]),
            100.0,
            0.02,
            np.array([0.2, 0.2]),
            1.0,
            CORR2,
            n_simulations=100_000,
        ),
    ),
    (
        "Derivatives",
        "basket_option_pricer",
        lambda: basket_option_pricer(
            np.array([100.0, 100.0]),
            np.array([0.5, 0.5]),
            100.0,
            0.02,
            np.array([0.2, 0.2]),
            1.0,
            CORR2,
            n_simulations=100_000,
        ),
    ),
    (
        "Derivatives",
        "american_option_lsm",
        lambda: american_option_lsm(
            100.0, 100.0, 0.02, 0.2, 1.0, n_simulations=100_000
        ),
    ),
    (
        "Operational Risk",
        "monte_carlo_oprisk_capital",
        lambda: monte_carlo_oprisk_capital(10.0, 8.0, 1.5, n_years=100_000),
    ),
]


def _sanity_check(name: str, result: dict) -> None:  # type: ignore[type-arg]
    """Reject degenerate results (all-zero, NaN, empty) so a benchmark never
    silently times a broken call."""
    numeric_values = [v for v in result.values() if isinstance(v, (int, float))]
    if not numeric_values:
        raise AssertionError(f"{name}: no numeric fields in result {result!r}")
    if not all(np.isfinite(v) for v in numeric_values):
        raise AssertionError(f"{name}: non-finite value in result {result!r}")
    if all(v == 0 for v in numeric_values):
        raise AssertionError(f"{name}: every numeric field is zero — degenerate result")


def main() -> None:
    print(f"NUMBA_CACHE_DIR (fresh, empty) = {_FRESH_CACHE_DIR}")
    print(f"{'domain':<18} {'function':<32} {'true_cold(s)':>13} {'warm(s)':>10}")
    total_cold = 0.0
    total_warm = 0.0
    for domain, name, fn in CASES:
        t0 = time.perf_counter()
        result = fn()
        true_cold = time.perf_counter() - t0
        _sanity_check(name, result)

        t0 = time.perf_counter()
        fn()
        warm = time.perf_counter() - t0

        total_cold += true_cold
        total_warm += warm
        flag = "  <-- >5s" if warm > 5.0 else ""
        print(f"{domain:<18} {name:<32} {true_cold:>13.3f} {warm:>10.3f}{flag}")

    print(
        f"{'':<18} {'TOTAL (sum of all 10)':<32} {total_cold:>13.3f} {total_warm:>10.3f}"
    )


if __name__ == "__main__":
    main()

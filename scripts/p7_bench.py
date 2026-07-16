"""P7 Task 1 — ad hoc benchmark of the 10 hottest Monte Carlo kernels at n=100k.

Not part of the committed test suite — a throwaway profiling harness for the
perf/p7-numba-profiling branch. Times each public wrapper (JIT warmup excluded
via one untimed warm-up call) and reports wall-clock seconds.
"""

from __future__ import annotations

import time

import numpy as np

from engine.deriv_options_exotic import (
    american_option_lsm,
    asian_option_pricer,
    basket_option_pricer,
    lookback_option_pricer,
    rainbow_option_pricer,
)
from engine.deriv_stoch_vol import rough_volatility_rbergomi_model, variance_gamma_model
from engine.expected_shortfall import monte_carlo_expected_shortfall
from engine.montecarlo import run_monte_carlo_var
from engine.oprisk_lda import monte_carlo_oprisk_capital

RETURNS = np.random.default_rng(0).normal(0.0003, 0.012, 252)
CORR2 = np.array([[1.0, 0.3], [0.3, 1.0]])

CASES = [
    ("Market Risk", "run_monte_carlo_var", lambda: run_monte_carlo_var(
        RETURNS, portfolio_value=1_000_000.0, n_simulations=100_000)),
    ("Market Risk", "monte_carlo_expected_shortfall", lambda: monte_carlo_expected_shortfall(
        RETURNS, portfolio_value=1_000_000.0, n_simulations=100_000)),
    ("Derivatives", "rough_volatility_rbergomi_model", lambda: rough_volatility_rbergomi_model(
        100.0, 100.0, 0.02, 1.0, n_simulations=100_000)),
    ("Derivatives", "variance_gamma_model", lambda: variance_gamma_model(
        100.0, 100.0, 0.02, 1.0, n_simulations=100_000)),
    ("Derivatives", "asian_option_pricer", lambda: asian_option_pricer(
        100.0, 100.0, 0.02, 0.2, 1.0, n_simulations=100_000)),
    ("Derivatives", "lookback_option_pricer", lambda: lookback_option_pricer(
        100.0, 100.0, 0.02, 0.2, 1.0, n_simulations=100_000)),
    ("Derivatives", "rainbow_option_pricer", lambda: rainbow_option_pricer(
        np.array([100.0, 100.0]), 100.0, 0.02, np.array([0.2, 0.2]), 1.0, CORR2,
        n_simulations=100_000)),
    ("Derivatives", "basket_option_pricer", lambda: basket_option_pricer(
        np.array([100.0, 100.0]), np.array([0.5, 0.5]), 100.0, 0.02,
        np.array([0.2, 0.2]), 1.0, CORR2, n_simulations=100_000)),
    ("Derivatives", "american_option_lsm", lambda: american_option_lsm(
        100.0, 100.0, 0.02, 0.2, 1.0, n_simulations=100_000)),
    ("Operational Risk", "monte_carlo_oprisk_capital", lambda: monte_carlo_oprisk_capital(
        10.0, 8.0, 1.5, n_years=100_000)),
]


def main() -> None:
    print(f"{'domain':<18} {'function':<32} {'warm(s)':>10} {'cold(s)':>10}")
    for domain, name, fn in CASES:
        t0 = time.perf_counter()
        fn()
        cold = time.perf_counter() - t0
        t0 = time.perf_counter()
        fn()
        warm = time.perf_counter() - t0
        flag = "  <-- >5s" if warm > 5.0 else ""
        print(f"{domain:<18} {name:<32} {warm:>10.3f} {cold:>10.3f}{flag}")


if __name__ == "__main__":
    main()

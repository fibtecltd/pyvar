"""
api/trial_whitelist.py — the functions the no-sign-up trial lane may run, each with one example request body

Reasoning:
- The lane (api/routes/trial.py) runs a function inline in a worker thread for a caller nobody has
  authenticated, so it runs only functions chosen one by one. A function qualifies when, in the benchmark of
  docs/trial-lane-whitelist-benchmark-2026-11-17.md, it answered 200, its p95 was far below the lane's 1 s
  deadline and, in a fresh process warmed the way main.py's lifespan warms it, it compiled no Numba kernel on
  its first call (a compile would cost seconds on a worker thread and a charge of many units to one caller).
  70 of the 385 functions compile on first call (the historical VaR and expected-shortfall functions among
  them); they stay out until their kernels are baked into the image, which is a separate decision.
- Of the qualifying 315 the lane takes 30, three or four of each domain, because every function on this list
  is something an unauthenticated caller can aim inputs at. The choice favours the functions a first-time user
  asks for (parametric and Cornish-Fisher VaR, Kupiec and traffic-light backtests, Black-Scholes, bond and swap
  pricing, Basel ratios, the LCR family, OpVaR inputs) and leaves out anything with a simulation count, a path
  count or a solver whose cost grows with a parameter. Adding a function is one line in trial_examples.json plus
  the test that proves it meets the rules above (tests/test_trial_routes.py); widening the list is the owner's call.
- The examples are the benchmark's own bodies (scripts/trial_weight_bench.py). They warm the functions at
  start-up (api/routes/trial.py::warm_whitelist) and are the lane's tests' inputs, so an example that stops
  validating fails the suite instead of the first caller.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXAMPLES: dict[str, dict[str, Any]] = json.loads(
    Path(__file__).with_name("trial_examples.json").read_text(encoding="utf-8")
)

# Function name (the last segment of its /api/v1/<domain>/<name> route; unique across all domains) to run.
WHITELIST: frozenset[str] = frozenset(EXAMPLES)

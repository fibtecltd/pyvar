"""tests/test_trial_whitelist.py — what a function must be to be on the no-sign-up trial lane's list.

Reasoning:
- api/trial_whitelist.py documents three rules: the function answers 200 on its example; it compiles no Numba
  kernel on its first call in a process warmed the way main.py's lifespan warms it (a compile is seconds on a
  worker thread and a charge of many units to one caller); and its cost does not grow with a parameter the caller
  chooses (a simulation or path count, a step count), because a call cannot be cancelled once it is running and
  the lane has one slot per API task. This file turns the second and third into tests, so a function cannot be
  added to the list, or a dependency change cannot start compiling one already on it, without a failure here.
- The compile check runs in a SUBPROCESS with an empty Numba cache directory: in this process another test may have
  compiled the kernel already, which would hide exactly what the rule is about.
"""

from __future__ import annotations

import json
import os
import re
import subprocess  # noqa: S404 - a fixed argument list, no shell, our own script
import sys
import tempfile
from pathlib import Path

import pytest

from api.routes import trial as trial_routes
from api.trial_whitelist import EXAMPLES, WHITELIST

ROOT = Path(__file__).resolve().parents[1]

# Parameter names whose value sets how much work a call does. None of the listed functions may take one.
_COSTLY_PARAMETER = re.compile(
    r"(^|_)(n_)?(simulations?|sims?|paths?|scenarios?|steps?|iterations?|bootstrap|samples?|draws?)($|_)"
)

_CHILD = r"""
import gc, json, sys
import numpy as np
from numba.core.dispatcher import Dispatcher

from api.routes import trial
from api.trial_whitelist import EXAMPLES
from engine.montecarlo import run_monte_carlo_var


def compiles():
    return sum(
        sum(obj.stats.cache_misses.values())
        for obj in gc.get_objects()
        if isinstance(obj, Dispatcher)
    )


# What main.py's lifespan runs before serving (the only kernel the image pre-bakes).
run_monte_carlo_var(np.random.randn(30) * 0.01, portfolio_value=1.0, n_simulations=1_000, seed=0)
registry = trial.registry()
report = {}
for name in sorted(registry):
    before = compiles()
    status, _ = trial._run_endpoint(registry[name], registry[name].model.model_validate(EXAMPLES[name]))
    report[name] = {"status": status, "compiled": compiles() - before}
# A positive control: a function known to compile, so a counter that always reads zero fails the parent.
from engine.var_models import historical_simulation_var

before = compiles()
historical_simulation_var(np.random.randn(100) * 0.01, 1_000_000.0, 0.99)
report["__control__"] = {"status": 200, "compiled": compiles() - before}
print("REPORT " + json.dumps(report))
"""


def test_no_whitelisted_function_compiles_a_kernel_on_its_first_call() -> None:
    with tempfile.TemporaryDirectory(prefix="trial-numba-") as cache_dir:
        env = {**os.environ, "NUMBA_CACHE_DIR": cache_dir, "PYTHONPATH": str(ROOT)}
        proc = subprocess.run(  # noqa: S603 # nosec B603
            [sys.executable, "-c", _CHILD],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=300,
            check=False,
        )
    lines = [line for line in proc.stdout.splitlines() if line.startswith("REPORT ")]
    assert lines, f"the child printed no report:\n{proc.stderr[-1500:]}"
    report = json.loads(lines[-1][len("REPORT ") :])
    control = report.pop("__control__")
    assert control["compiled"] > 0, "the compile counter reads zero for a function that compiles"
    assert set(report) == set(WHITELIST)
    assert {name: row["status"] for name, row in report.items() if row["status"] != 200} == {}
    compiled = {name: row["compiled"] for name, row in report.items() if row["compiled"]}
    assert not compiled, (
        "these functions compile a Numba kernel on their first call, so they cannot be on the trial "
        f"list until their kernels are baked into the image: {compiled}"
    )


@pytest.mark.parametrize("function", sorted(WHITELIST))
def test_no_whitelisted_function_takes_a_parameter_that_sets_how_much_work_it_does(
    function: str,
) -> None:
    model = trial_routes.registry()[function].model
    costly = [name for name in model.model_fields if _COSTLY_PARAMETER.search(name)]
    assert (
        not costly
    ), f"{function} has parameter(s) {costly}: its cost grows with the caller's input"


def test_every_example_is_inside_the_lanes_own_input_caps() -> None:
    from config import get_settings

    cfg = get_settings()
    for name, body in EXAMPLES.items():
        assert (
            len(json.dumps(body)) < cfg.trial_max_body_bytes // 2
        ), name  # room for a real caller's data
        leaves, stack = 0, [body]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
            else:
                leaves += 1
        assert leaves <= cfg.trial_max_array_elements // 2, name


def test_the_list_is_thirty_functions_across_all_eight_domains() -> None:
    domains = {entry.path.split("/")[1] for entry in trial_routes.registry().values()}
    assert len(WHITELIST) == 30
    assert domains == {
        "market-risk",
        "credit-risk",
        "liquidity",
        "operational",
        "portfolio",
        "regulatory",
        "derivatives",
        "alm",
    }


def test_the_functions_that_compile_on_first_call_are_not_on_the_list() -> None:
    """Named from the benchmark (docs/trial-lane-whitelist-benchmark-2026-11-17.md): the flagship ones among them."""
    compiling = {
        "historical_simulation_var",
        "historical_expected_shortfall",
        "conditional_var_es",
        "garch_11_volatility_forecast",
        "sharpe_ratio",
        "maximum_drawdown",
        "monte_carlo_option_pricer",
        "binomial_tree_option_pricer",
        "credit_var_monte_carlo",
        "loss_distribution_approach_lda",
    }
    assert not compiling & WHITELIST

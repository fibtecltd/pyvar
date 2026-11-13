"""P7 follow-up: the Numba kernels against fair, vectorised NumPy baselines.

Why this exists: docs/p7-numba-profiling-results.md reports how long the Numba kernels take, but not what
they take compared with plain NumPy, so it shows what pyvar does and not what the JIT buys. This script
adds that comparator for four of the hottest kernels (docs/plan-swot-engineering-integration.md, W1). Fully
local and offline: no AWS, no network.

## Running it

    python scripts/p7_vs_numpy.py                      # everything, three subprocesses
    python scripts/p7_vs_numpy.py --repeats 25 --json out.json

## Fairness rules (each one is checked by the code, not just stated)

1. Same algorithm and the same random draws. Every baseline receives the identical pre-drawn normals as the
   Numba kernel, and the script refuses to time anything until the two outputs agree (kernels: relative
   1e-9; end to end: the tolerances in `CASES`). A baseline that computes something different is not a
   baseline.
2. The baselines are what a competent NumPy author would write: vectorised over paths, float64, no Python
   loops over paths. They are not tuned further (no Cython, no multithreading beyond what NumPy and its BLAS
   do by themselves).
3. Warm calls only for the speed columns (two untimed warm-up calls, then `--repeats` timed ones); the
   median and the interquartile range are reported, never one shot. Garbage collection is paused while
   timing.
4. Numba is measured twice, on one thread and on all cores, so that what comes from compilation can be told
   apart from what comes from parallelism. The NumPy baselines are single-threaded except where NumPy's own
   BLAS threads a matrix product.
5. The first-call (compile) cost of each kernel is measured separately, in a process whose Numba cache
   directory is fresh and empty, as in scripts/p7_bench.py.
6. The hardware and library versions are recorded with the numbers. Absolute times belong to the machine
   they were measured on; the ratios are the finding.

A pure-Python loop baseline (NUMBA_DISABLE_JIT=1) is deliberately not run: it would be a strawman.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import platform
import subprocess  # nosec B404
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
N_SIMS = 100_000  # the same size as scripts/p7_bench.py


# ── timing and checking helpers ──────────────────────────────────────────────────────────────────────
def _stats(samples_ms: list[float]) -> dict[str, float]:
    ordered = sorted(samples_ms)
    n = len(ordered)
    return {
        "median_ms": ordered[n // 2] if n % 2 else 0.5 * (ordered[n // 2 - 1] + ordered[n // 2]),
        "p25_ms": ordered[max(0, int(0.25 * (n - 1)))],
        "p75_ms": ordered[min(n - 1, int(round(0.75 * (n - 1))))],
        "min_ms": ordered[0],
    }


def _bench(fn: Callable[[], Any], repeats: int, warmup: int = 2) -> dict[str, float]:
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    gc.collect()
    gc.disable()
    try:
        for _ in range(repeats):
            t0 = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - t0) * 1e3)
    finally:
        gc.enable()
    return _stats(samples)


def _first_call_ms(fn: Callable[[], Any]) -> float:
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1e3


def _max_rel_diff(a: Any, b: Any) -> float:
    import numpy as np

    a_arr, b_arr = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    scale = np.maximum(np.abs(a_arr), np.abs(b_arr)).max()
    return float(np.abs(a_arr - b_arr).max() / scale) if scale > 0 else 0.0


# ── the cases: a Numba kernel, its NumPy twin, and the public function around each ───────────────────
def _build_cases(np: Any) -> list[dict[str, Any]]:
    """Import the engine (after NUMBA_* variables are set) and build every case."""
    sys.path.insert(0, str(ROOT))
    from engine.deriv_options_exotic import (
        _gbm_full_paths,
        _gbm_path_stats,
        _lsm_price,
        american_option_lsm,
        asian_option_pricer,
    )
    from engine.deriv_stoch_vol import _rbergomi_paths, rough_volatility_rbergomi_model
    from engine.montecarlo import (
        _draw_random_shocks,
        _simulate_paths,
        _sorted_losses,
        run_monte_carlo_var,
    )

    cases: list[dict[str, Any]] = []

    # 1. Monte Carlo VaR: horizon 1 (the API default) and 10 (where the kernel does more work) ----------
    returns = np.random.default_rng(0).normal(0.0003, 0.012, 252)

    def np_simulate_paths(rets: Any, shocks: Any, horizon: int) -> Any:
        return (float(np.mean(rets)) + float(np.std(rets)) * shocks[:, :horizon]).sum(axis=1)

    def np_run_monte_carlo_var(horizon: int) -> dict[str, Any]:
        np.random.seed(42)
        shocks = _draw_random_shocks(N_SIMS, horizon, False)
        losses = np.sort(-np_simulate_paths(returns, shocks, horizon))
        idx = min(int(np.floor(0.99 * N_SIMS)), N_SIMS - 1)
        return {
            "var_pct": round(float(losses[idx]), 6),
            "cvar_pct": round(float(np.mean(losses[idx:])), 6),
            "loss_dist": losses.tolist(),
        }

    for horizon in (1, 10):
        np.random.seed(42)
        shocks = _draw_random_shocks(N_SIMS, horizon, False)
        pnl = np_simulate_paths(returns, shocks, horizon)
        sorted_losses = np.sort(-pnl)
        cases.append(
            {
                "name": f"run_monte_carlo_var (horizon {horizon})",
                "kernel": "_simulate_paths",
                "numba_kernel": lambda s=shocks, h=horizon: _simulate_paths(returns, s, h),
                "numpy_kernel": lambda s=shocks, h=horizon: np_simulate_paths(returns, s, h),
                "numba_e2e": lambda h=horizon: run_monte_carlo_var(
                    returns, 1_000_000.0, horizon_days=h, n_simulations=N_SIMS
                ),
                "numpy_e2e": lambda h=horizon: np_run_monte_carlo_var(h),
                "rng": lambda h=horizon: _draw_random_shocks(N_SIMS, h, False),
                "e2e_keys": ("var_pct", "cvar_pct", "loss_dist"),
                "e2e_tol": 1e-9,
                "extras": {
                    "random draw (np.random.randn)": lambda h=horizon: _draw_random_shocks(
                        N_SIMS, h, False
                    ),
                    "sort, Numba (_sorted_losses)": lambda p=pnl: _sorted_losses(p),
                    "sort, np.sort(-pnl)": lambda p=pnl: np.sort(-p),
                    "loss_dist list conversion (.tolist())": lambda sl=sorted_losses: sl.tolist(),
                },
            }
        )

    # 2. Asian option: path statistics ----------------------------------------------------------------
    spot, strike, rate, sigma, tau, steps = 100.0, 100.0, 0.02, 0.2, 1.0, 100
    normals_a = np.random.default_rng(21).standard_normal((N_SIMS, steps)).astype(np.float64)

    def np_gbm_path_stats(
        s0: float, r: float, q: float, vol_: float, t: float, z: Any, all_stats: bool = True
    ) -> Any:
        n_paths, n_steps = z.shape
        dt = t / n_steps
        s = s0 * np.exp(np.cumsum((r - q - 0.5 * vol_ * vol_) * dt + vol_ * math.sqrt(dt) * z, 1))
        out = np.empty((n_paths, 4 if all_stats else 2), dtype=np.float64)
        out[:, 0] = s[:, -1]
        out[:, 1] = s.mean(axis=1)
        if all_stats:
            out[:, 2] = np.minimum(s0, s.min(axis=1))
            out[:, 3] = np.maximum(s0, s.max(axis=1))
        return out

    def np_asian_e2e() -> dict[str, float]:
        z = np.random.default_rng(21).standard_normal((N_SIMS, steps)).astype(np.float64)
        avg = np_gbm_path_stats(spot, rate, 0.0, sigma, tau, z)[:, 1]
        disc_payoff = math.exp(-rate * tau) * np.maximum(avg - strike, 0.0)
        return {"price": round(float(np.mean(disc_payoff)), 8)}

    cases.append(
        {
            "name": "asian_option_pricer",
            "kernel": "_gbm_path_stats",
            "numba_kernel": lambda: _gbm_path_stats(spot, rate, 0.0, sigma, tau, normals_a),
            "numpy_kernel": lambda: np_gbm_path_stats(spot, rate, 0.0, sigma, tau, normals_a),
            "numpy_kernel_lean": lambda: np_gbm_path_stats(
                spot, rate, 0.0, sigma, tau, normals_a, all_stats=False
            ),
            "numba_e2e": lambda: asian_option_pricer(
                spot, strike, rate, sigma, tau, n_simulations=N_SIMS
            ),
            "numpy_e2e": np_asian_e2e,
            "rng": lambda: np.random.default_rng(21)
            .standard_normal((N_SIMS, steps))
            .astype(np.float64),
            "e2e_keys": ("price",),
            "e2e_tol": 1e-9,
        }
    )

    # 3. American option (Longstaff-Schwartz): only the path generator is Numba ---------------------------
    steps_l = 50
    normals_l = np.random.default_rng(41).standard_normal((N_SIMS, steps_l)).astype(np.float64)
    mask = np.ones(steps_l + 1, dtype=np.bool_)

    def np_gbm_full_paths(s0: float, r: float, q: float, vol_: float, t: float, z: Any) -> Any:
        n_paths, n_steps = z.shape
        dt = t / n_steps
        paths = np.empty((n_paths, n_steps + 1), dtype=np.float64)
        paths[:, 0] = s0
        steps_ = (r - q - 0.5 * vol_ * vol_) * dt + vol_ * math.sqrt(dt) * z
        paths[:, 1:] = s0 * np.exp(np.cumsum(steps_, axis=1))
        return paths

    def np_american_e2e() -> dict[str, float]:
        z = np.random.default_rng(41).standard_normal((N_SIMS, steps_l)).astype(np.float64)
        paths = np_gbm_full_paths(100.0, 0.02, 0.0, 0.2, 1.0, z)
        price = _lsm_price(paths, 100.0, 0.02, 1.0 / steps_l, False, mask)
        return {"price": round(float(price), 8)}

    cases.append(
        {
            "name": "american_option_lsm",
            "kernel": "_gbm_full_paths (the only Numba stage; the regression is NumPy)",
            "numba_kernel": lambda: _gbm_full_paths(100.0, 0.02, 0.0, 0.2, 1.0, normals_l),
            "numpy_kernel": lambda: np_gbm_full_paths(100.0, 0.02, 0.0, 0.2, 1.0, normals_l),
            "numba_e2e": lambda: american_option_lsm(
                100.0, 100.0, 0.02, 0.2, 1.0, n_simulations=N_SIMS
            ),
            "numpy_e2e": np_american_e2e,
            "rng": lambda: np.random.default_rng(41)
            .standard_normal((N_SIMS, steps_l))
            .astype(np.float64),
            "e2e_keys": ("price",),
            "e2e_tol": 1e-6,  # exercise decisions can flip on last-digit differences in the paths
        }
    )

    # 4. rough Bergomi: the Volterra driver is a lower-triangular convolution, one matrix product ------
    xi, eta, hurst, rho, steps_r = 0.04, 1.5, 0.1, -0.7, 50
    rng_r = np.random.default_rng(2024)
    z_v = rng_r.standard_normal((N_SIMS, steps_r)).astype(np.float64)
    z_s = rng_r.standard_normal((N_SIMS, steps_r)).astype(np.float64)

    def np_rbergomi_paths(z_v_: Any, z_s_: Any, s0: float, k: float, r: float, t: float) -> Any:
        n = z_v_.shape[1]
        dt = t / n
        sqrt_dt = math.sqrt(dt)
        weights = np.zeros(
            (n, n)
        )  # weights[step, j] = ((step + 1 - j) * dt) ** (H - 0.5) * sqrt(dt)
        for step in range(n):
            weights[step, : step + 1] = ((step + 1 - np.arange(step + 1)) * dt) ** (hurst - 0.5)
        wv = (z_v_ @ weights.T) * sqrt_dt
        two_h = 2.0 * hurst
        discrete_var = (
            two_h * dt**two_h * np.cumsum(np.arange(1, n + 1, dtype=np.float64) ** (two_h - 1.0))
        )
        var = np.empty_like(z_v_)
        var[:, 0] = xi
        var[:, 1:] = xi * np.exp(
            eta * math.sqrt(two_h) * wv[:, :-1] - 0.5 * eta * eta * discrete_var[:-1]
        )
        vol = np.sqrt(np.where(var > 0.0, var, 1e-12))
        dw = rho * z_v_ + math.sqrt(1.0 - rho * rho) * z_s_
        log_s = math.log(s0) + ((r - 0.5 * var) * dt + vol * sqrt_dt * dw).sum(axis=1)
        return math.exp(-r * t) * np.maximum(np.exp(log_s) - k, 0.0)

    def np_rbergomi_e2e() -> dict[str, float]:
        rng = np.random.default_rng(2024)
        zv = rng.standard_normal((N_SIMS, steps_r)).astype(np.float64)
        zs = rng.standard_normal((N_SIMS, steps_r)).astype(np.float64)
        return {
            "price": round(float(np.mean(np_rbergomi_paths(zv, zs, 100.0, 100.0, 0.02, 1.0))), 8)
        }

    def draw_r() -> Any:
        rng = np.random.default_rng(2024)
        return (
            rng.standard_normal((N_SIMS, steps_r)).astype(np.float64),
            rng.standard_normal((N_SIMS, steps_r)).astype(np.float64),
        )

    cases.append(
        {
            "name": "rough_volatility_rbergomi_model",
            "kernel": "_rbergomi_paths",
            "numba_kernel": lambda: _rbergomi_paths(
                100.0, 100.0, 0.02, 1.0, xi, eta, hurst, rho, z_v, z_s, steps_r, True
            ),
            "numpy_kernel": lambda: np_rbergomi_paths(z_v, z_s, 100.0, 100.0, 0.02, 1.0),
            "numba_e2e": lambda: rough_volatility_rbergomi_model(
                100.0, 100.0, 0.02, 1.0, n_simulations=N_SIMS
            ),
            "numpy_e2e": np_rbergomi_e2e,
            "rng": draw_r,
            "e2e_keys": ("price",),
            "e2e_tol": 1e-9,
        }
    )
    return cases


# ── workers (one process each, so NUMBA_* variables are set before Numba is imported) ───────────────
def _worker(mode: str, repeats: int) -> dict[str, Any]:
    import numpy as np

    cases = _build_cases(np)
    rows: list[dict[str, Any]] = []
    seen_kernels: set[str] = set()
    for case in cases:
        row: dict[str, Any] = {"name": case["name"], "kernel": case["kernel"]}
        if mode == "cold":
            if (
                case["kernel"] in seen_kernels
            ):  # already compiled by an earlier row: not a first call
                continue
            seen_kernels.add(case["kernel"])
            # the very first call in this process, so compilation is included for Numba
            row["numba_first_call_ms"] = _first_call_ms(case["numba_kernel"])
            row["numpy_first_call_ms"] = _first_call_ms(case["numpy_kernel"])
            rows.append(row)
            continue

        # equivalence first: nothing is timed until the baseline reproduces the Numba output
        a, b = case["numba_kernel"](), case["numpy_kernel"]()
        row["kernel_max_rel_diff"] = _max_rel_diff(a, b)
        if row["kernel_max_rel_diff"] > 1e-9:
            raise AssertionError(
                f"{case['name']}: kernel outputs differ by {row['kernel_max_rel_diff']}"
            )
        ra, rb = case["numba_e2e"](), case["numpy_e2e"]()
        diffs = [_max_rel_diff(ra[key], rb[key]) for key in case["e2e_keys"]]
        row["e2e_max_rel_diff"] = max(diffs)
        if row["e2e_max_rel_diff"] > case["e2e_tol"]:
            raise AssertionError(
                f"{case['name']}: end-to-end outputs differ by {row['e2e_max_rel_diff']}"
            )

        row["numba_kernel"] = _bench(case["numba_kernel"], repeats)
        row["numpy_kernel"] = _bench(case["numpy_kernel"], repeats)
        if "numpy_kernel_lean" in case:
            row["numpy_kernel_lean"] = _bench(case["numpy_kernel_lean"], repeats)
        row["numba_e2e"] = _bench(case["numba_e2e"], repeats)
        row["numpy_e2e"] = _bench(case["numpy_e2e"], repeats)
        row["rng"] = _bench(case["rng"], repeats)
        if "extras" in case:
            row["extras"] = {k: _bench(f, repeats) for k, f in case["extras"].items()}
        rows.append(row)

    import numba

    return {
        "mode": mode,
        "numba_threads": numba.config.NUMBA_NUM_THREADS,
        "numba_threading_layer": numba.config.THREADING_LAYER,
        "rows": rows,
    }


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _run_worker(mode: str, threads: int, repeats: int) -> dict[str, Any]:
    env = dict(os.environ, NUMBA_NUM_THREADS=str(threads))
    if mode == "cold":
        env["NUMBA_CACHE_DIR"] = tempfile.mkdtemp(prefix="p7_vs_numpy_cache_")
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        mode,
        "--repeats",
        str(repeats),
    ]
    # the command is this same script with fixed arguments, and no shell is involved
    done = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)  # nosec B603
    if done.returncode != 0:
        raise RuntimeError(f"worker {mode} failed:\n{done.stderr[-2000:]}")
    return json.loads(done.stdout.splitlines()[-1])


def _fmt(stat: dict[str, float]) -> str:
    return f"{stat['median_ms']:.2f} ({stat['p25_ms']:.2f}-{stat['p75_ms']:.2f})"


def _report(
    one: dict[str, Any], many: dict[str, Any], cold: dict[str, Any], meta: dict[str, Any]
) -> str:
    out = [
        f"Machine: {meta['cpu']}, {meta['cores']} cores | Python {meta['python']} | NumPy {meta['numpy']}"
        f" | Numba {meta['numba']} | repeats {meta['repeats']} | n_simulations {N_SIMS}",
        "",
        f"Kernel only, warm, ms: median (p25-p75). Numba all cores = {many['numba_threads']} threads.",
        "| Case | NumPy | Numba 1 thread | Numba all cores | NumPy / Numba 1 | NumPy / Numba all |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r1, rn in zip(one["rows"], many["rows"], strict=True):
        np_ms, n1, nn = (
            r1["numpy_kernel"]["median_ms"],
            r1["numba_kernel"]["median_ms"],
            rn["numba_kernel"]["median_ms"],
        )
        out.append(
            f"| {r1['name']} | {_fmt(r1['numpy_kernel'])} | {_fmt(r1['numba_kernel'])} | {_fmt(rn['numba_kernel'])}"
            f" | {np_ms / n1:.2f}x | {np_ms / nn:.2f}x |"
        )
    out += [
        "",
        "End to end (the public function, RNG included), warm, ms: median (p25-p75).",
        "| Case | NumPy | Numba all cores | NumPy / Numba | RNG share of Numba call | kernel share of Numba call |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rn in many["rows"]:
        e_n, e_b = rn["numpy_e2e"]["median_ms"], rn["numba_e2e"]["median_ms"]
        out.append(
            f"| {rn['name']} | {_fmt(rn['numpy_e2e'])} | {_fmt(rn['numba_e2e'])} | {e_n / e_b:.2f}x"
            f" | {100 * rn['rng']['median_ms'] / e_b:.0f}% | {100 * rn['numba_kernel']['median_ms'] / e_b:.0f}% |"
        )
    out += [
        "",
        "First call (Numba includes JIT compilation; fresh cache), ms.",
        "| Case | Numba first call | NumPy first call |",
        "| --- | ---: | ---: |",
    ]
    for rc in cold["rows"]:
        out.append(
            f"| {rc['name']} | {rc['numba_first_call_ms']:.0f} | {rc['numpy_first_call_ms']:.1f} |"
        )
    for rn in many["rows"]:
        if "extras" in rn:
            out += ["", f"Where the time goes in {rn['name']}, warm, ms: median (p25-p75)."]
            out += [f"- {label}: {_fmt(stat)}" for label, stat in rn["extras"].items()]
    out += ["", "Equivalence (max relative difference, baseline against Numba):"]
    for rn in many["rows"]:
        out.append(
            f"- {rn['name']}: kernel {rn['kernel_max_rel_diff']:.1e}, end to end {rn['e2e_max_rel_diff']:.1e}"
        )
    for rn in many["rows"]:
        if "numpy_kernel_lean" in rn:
            out.append(
                f"\nAsian, NumPy computing only the two columns the pricer uses: {_fmt(rn['numpy_kernel_lean'])} ms"
            )
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--json", type=Path, default=None, help="also write the raw results here")
    parser.add_argument("--worker", choices=("bench", "cold"), default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker:  # a child process: print one JSON line and stop
        print(json.dumps(_worker(args.worker, args.repeats)))
        return

    cores = (
        len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    )
    one = _run_worker("bench", 1, args.repeats)
    many = _run_worker("bench", cores, args.repeats)
    cold = _run_worker("cold", cores, 1)
    import numba
    import numpy

    meta = {
        "cpu": _cpu_model(),
        "cores": cores,
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "numba": numba.__version__,
        "repeats": args.repeats,
    }
    print(_report(one, many, cold, meta))
    if args.json:
        args.json.write_text(
            json.dumps({"meta": meta, "one_thread": one, "all_cores": many, "cold": cold}, indent=2)
        )


if __name__ == "__main__":
    main()

# P7 follow-up: the Numba kernels against fair NumPy baselines

**Measured 2026-11-13** with `scripts/p7_vs_numpy.py` (21 repeats; raw numbers in `docs/p7-numba-vs-numpy-results.json`). This is item W1 of
`docs/plan-swot-engineering-integration.md`. It adds the comparator that `docs/p7-numba-profiling-results.md` lacks: that document says how long
the kernels take, this one says what the JIT buys compared with plain, vectorised NumPy.

**One-paragraph result.** Where per-path computation dominates, the compiled kernels are clearly faster than vectorised NumPy: 2.1 times on one
thread and 7.1 times on four cores for the Asian option's path loop, and 3.9 to 13.5 times for the Monte Carlo VaR kernel. **End to end, the picture
is different.** Measured as the public functions, Numba is faster than a plain-NumPy version of the same function in **one of five cases** (the Asian
pricer, 1.7 times), at parity in one (the American option), and **slower in three**: the 1-day Monte Carlo VaR (NumPy is 3.4 times faster), the
10-day Monte Carlo VaR (1.3 times) and the rough Bergomi pricer (2.4 times). Random-number generation, sorting and other NumPy stages dominate the
time, and in two functions a slow Numba stage costs more than the JIT saves. The speed of these functions is not, on this evidence, a result of the
JIT.

**Follow-up, same day: the two slow stages were fixed in the same pull request, and the result is in the last section.** The sort in the Monte Carlo VaR
function now uses `np.sort`, and the rough Bergomi pricer computes its lag weights once. Measured again, end to end, Numba is faster than the plain-NumPy
version in **three of five cases** (Asian 1.55x, rough Bergomi 1.69x, 10-day VaR 1.24x), at parity in two (1-day VaR 0.97x, American 0.97x) and slower in none.
The sections below describe the code as it was measured first.

## Method

**Equivalence before timing.** Every baseline receives the identical pre-drawn random numbers as the Numba code, and the script refuses to time anything
until the outputs agree. Kernel outputs agree to a relative difference of at most 1.4e-14, and the public functions' outputs to 3.3e-16 or exactly
(prices are rounded to 8 decimals). A baseline that computed something different would not be a baseline.

**The baselines** are what a competent NumPy author writes: vectorised over paths, float64, no loops over paths, no further tuning. For the rough
Bergomi model the Volterra driver, which the Numba kernel recomputes path by path, is one matrix product against a weight matrix built once.

**Numba is measured twice**, on one thread and on all four cores, so that what comes from compilation can be told apart from what comes from
parallelism. The NumPy baselines are single-threaded except where NumPy's own BLAS threads a matrix product (the rough Bergomi baseline).

**Timing.** Two untimed warm-up calls, then 21 timed calls, with garbage collection paused; the median and the interquartile range are reported. First-call
(compile) cost is measured separately in a process with a fresh, empty Numba cache. `n_simulations` is 100,000 and the other arguments are the functions'
defaults, as in `scripts/p7_bench.py`.

**Machine:** an Intel Xeon 2.1 GHz virtual machine with 4 cores, Python 3.11.17, NumPy 2.4.6, Numba 0.68.1. This is not production hardware.

## Results

**Kernel only**, warm, milliseconds, median (interquartile range). "x" is NumPy time divided by Numba time, so above 1 means Numba is faster.

- `run_monte_carlo_var`, 1-day horizon (`_simulate_paths`): NumPy 0.30 (0.24 to 0.33); Numba 1 thread 0.08, 3.9x; Numba 4 cores 0.05, 6.3x.
- `run_monte_carlo_var`, 10-day horizon: NumPy 2.91 (2.87 to 3.05); Numba 1 thread 0.50, 5.8x; 4 cores 0.22, 13.5x.
- `asian_option_pricer` (`_gbm_path_stats`): NumPy 145.7 (138.4 to 159.8); Numba 1 thread 68.0, 2.1x; 4 cores 20.7, 7.1x. A NumPy version computing only the
  two columns the pricer uses takes 112.1, which gives 1.6x and 5.4x.
- `american_option_lsm` (`_gbm_full_paths`, the only Numba stage; the regression is NumPy): NumPy 62.2 (61.1 to 63.9); Numba 1 thread 45.9, 1.35x; 4 cores 53.1,
  1.17x (the kernel is serial, so the extra cores do nothing).
- `rough_volatility_rbergomi_model` (`_rbergomi_paths`): NumPy 156.3 (147.9 to 164.8); Numba 1 thread **2,056**, **0.08x**; 4 cores 625, **0.25x**.

**End to end**, the public function with its random numbers, warm, milliseconds, median (interquartile range):

- `run_monte_carlo_var`, 1 day: NumPy **3.85** (3.50 to 4.38); Numba **13.28** (12.74 to 14.37); ratio 0.29x.
- `run_monte_carlo_var`, 10 days: NumPy 23.99 (23.06 to 29.50); Numba 30.86 (29.43 to 37.91); ratio 0.78x.
- `asian_option_pricer`: NumPy 298.4 (286.9 to 309.8); Numba 175.8 (169.3 to 189.8); ratio 1.70x.
- `american_option_lsm`: NumPy 402.8 (390.1 to 427.6); Numba 421.7 (392.8 to 444.3); ratio 0.96x.
- `rough_volatility_rbergomi_model`: NumPy 320.7 (309.9 to 352.1); Numba 781.0 (743.1 to 823.7); ratio 0.41x.

**Where the time goes in the Numba functions.** The stages were timed in isolation, so shares can add to more than 100% and are approximate.
The 1-day VaR call is 13.3 ms: the random draw about 1.6 ms (12%), the compiled simulation kernel 0.05 ms (under 1%), and the rest is mostly the sort and the
conversion of the 100,000-value loss distribution to a Python list. In isolation the Numba sort inside the function (`_sorted_losses`) takes **8.81 ms**
against **0.77 ms** for `np.sort` on the same data, 11.5 times slower; the list conversion takes 1.58 ms. For the 10-day VaR the random draw is half the call
(15.6 ms of 30.9). In the Asian pricer, generating 10 million normal draws is most of the call (about 165 ms of 176) and the compiled kernel about 12%. In the
American option the kernel is about 13% and the NumPy regression most of the rest. In the rough Bergomi pricer the kernel is 80% of the call and it is the
slow part.

**First call**, fresh Numba cache, milliseconds, Numba against NumPy: Monte Carlo VaR kernel 2,201 against 0.7; Asian 704 against 205; American 272 against 68;
rough Bergomi 1,776 against 260. The first row includes the one-time start-up of Numba's threading layer in a fresh process, so it is higher than the 1.08 s
that `p7-numba-profiling-results.md` reports for the whole `run_monte_carlo_var` call.

## What this shows

1. **The compiled kernels earn their keep where the per-path work is real.** The Asian path loop is 2.1 times faster than NumPy on one thread and 7.1 times
   on four cores, and the VaR kernel is 3.9 to 13.5 times faster. Both numbers are measured against equivalent, vectorised code, not a Python loop.
2. **That advantage mostly does not reach the function.** The kernels are small next to random-number generation and sorting, which NumPy already does in
   compiled code. End to end, Numba wins in one of five cases.
3. **Two stages cost more than the JIT saves.** (a) The sort inside the Monte Carlo VaR function is 11.5 times slower in Numba than `np.sort` on this machine, which makes the 1-day call 3.4 times
   slower than a plain-NumPy version. The likely reason is that NumPy 2.x sorts floats with vector instructions on CPUs that have them, and this CPU
   advertises AVX-512; that explanation was not isolated. (b) The rough
   Bergomi kernel recomputes the same lag weights, `(lag * dt) ** (H - 0.5)`, for every path inside its inner loop, although they depend only on the lag; the
   NumPy baseline computes them once and is 13 times faster than the kernel on one thread and 4 times faster on four cores.
4. **None of this says the engine is wrong.** The outputs agree to 1e-14. It says that the speed of these functions comes from compiled NumPy and SciPy and from the kernels where they matter, and that "JIT-accelerated"
   describes the kernels, not the functions.

## What this does not show

- **One machine, one size.** A 4-core virtual machine, `n_simulations` of 100,000, the functions' default arguments. Production workers are EC2 Spot
  instances of other types. More cores shrink the parallel kernels further, but the random draws and the sort stay single-threaded in both versions.
- **Other kernels.** Four functions were compared, not the 58 `@njit` kernels. They were chosen as the hottest in the p7 benchmark.
- **The NumPy sort advantage depends on the CPU** (vector instructions and the NumPy version). On a CPU without them the gap narrows.
- **The rough Bergomi baseline benefits from threaded BLAS** for its matrix product; the Numba kernel does not use it. A Numba kernel with the weights
  precomputed would also be faster than the current one, and was not measured.
- **Not a comparison with other architectures or vendors.** It compares two implementations of the same algorithm on one machine. It says nothing about cost per job
  or about anything outside the compute kernels (W2 to W5 of the plan).
- **No pure-Python baseline.** `NUMBA_DISABLE_JIT=1` would be a strawman and was not run.

## Opportunities this exposed (both made in the same pull request; see the last section)

Each is a change to `engine/` with its own tests, and so starts a CodePipeline run when merged. Neither touches regulatory logic.

1. `run_monte_carlo_var`: replace the Numba sort with `np.sort` (the loss distribution is identical). Estimated from the stage timings, not measured: the 1-day
   call would fall from about 13.3 ms to about 5.2 ms.
2. `rough_volatility_rbergomi_model`: compute the lag weights once, outside the path loop (or use the matrix form). The NumPy baseline, which does exactly that,
   reproduces the kernel's output to 1.4e-14 in about 156 ms against the kernel's 2,056 ms on one thread. A Numba kernel with the same change was not written or
   measured, so its speed is unknown.

## What follows for the SWOT and for wording

`docs/plan-swot-engineering-integration.md` is updated with these results. In short: do not present speed over vectorised NumPy as the innovation, because the
evidence does not support it end to end. The GitHub description ("385+ JIT-accelerated functions for fast VaR and Monte Carlo simulations") and the README's
"JIT-compiled" wording, and the published technical deep dive's cold and warm timings (1.083 s and 0.007 s for `run_monte_carlo_var`), are accurate as statements about the kernels and as raw timings, but
a reader can take them to mean the JIT is why the functions are fast; they deserve a wording review, which Filippo deferred on 2026-11-13 (left unchanged for now). The README's count of JIT functions is a separate open item.

## Reproducing it

```
python scripts/p7_vs_numpy.py --repeats 21 --json docs/p7-numba-vs-numpy-results.json
```

It needs the repository's requirements and four to eight minutes on a 4-core machine. Absolute times depend on the machine; the ratios and the equivalence
checks are the result.

## After the two changes (measured 2026-11-13, raw numbers in `docs/p7-numba-vs-numpy-results-after.json`)

**What changed in `engine/`.** (1) `run_monte_carlo_var` sorts the losses in place with NumPy; the Numba helper `_sorted_losses`, whose only caller it was, is removed.
(2) `_rbergomi_paths` computes the lag weights once per call (`_rbergomi_volterra_weights`) and every path uses them (`_rbergomi_volterra_driver_weighted`);
`_rbergomi_volterra_driver` keeps its signature as a thin wrapper, so the existing hand-calculation test of the gap-based weights applies unchanged.

**Outputs.** The VaR loss distribution is bit for bit identical on 12 reference arrays (1, 5 and 10 days, antithetic on and off, 50,000 values each). The rough Bergomi
per-path payoffs differ by at most 3.7e-15 relative over six reference cases (three Hurst exponents, call and put), which is rounding in the weights; the public function's
outputs, Greeks included, were identical at 8 decimals in the cases compared. Because the differences are about 1e-15, a rounded 8-decimal price could in principle change in its last
digit in a rare case; none did here.

**End to end**, the public Numba function, warm, milliseconds, median (interquartile range), against the first measurement:

- `run_monte_carlo_var`, 1 day: 13.28 before, **5.66** (5.32 to 5.98) after, 2.3 times faster. Against the plain-NumPy version, 0.29x before and 0.97x after: parity.
  The stage timings predicted about 5.2 ms.
- `run_monte_carlo_var`, 10 days: 30.86 before, **19.81** (19.57 to 20.04) after, 1.6 times faster; against NumPy 0.78x before, 1.24x after.
- `rough_volatility_rbergomi_model`: 781.0 before, **210.4** (198.4 to 222.1) after, 3.7 times faster; against NumPy 0.41x before, 1.69x after.
- `asian_option_pricer` and `american_option_lsm` are unchanged code.

**Kernel only**, rough Bergomi (`_rbergomi_paths`): one thread 2,056 before and **102.6** after (20 times faster); four cores 625 before and **40.3** after (15.5 times faster). It is now 1.8 times
(one thread) and 4.6 times (four cores) faster than the NumPy baseline, where it was 13 and 4 times slower.

**Run-to-run noise.** The two runs were hours apart on a shared virtual machine. The unchanged functions moved by up to 19% end to end (Asian 175.8 to 208.8 ms, American 421.7 to
434.2 ms), and the NumPy baselines moved too (the 1-day VaR baseline from 3.85 to 5.50 ms). Only differences far larger than that are findings: the VaR and rough Bergomi
improvements are 1.6 to 3.7 times, and the Asian and American results are the control.

**What is still true.** Numba is not faster than vectorised NumPy end to end in every case: the American option is at parity (the NumPy regression dominates it), and in every function the
random draws are a large share of the time. The first-call (compile) costs are unchanged in kind: 2,138 ms for the VaR kernel's first call in a fresh process (threading-layer start-up included),
1,437 ms for rough Bergomi.

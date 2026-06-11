# P5 Agent Teams — Parallel Validation
# Used by: pyvar-run.sh p5 --mode agent
# Machine: M4 only

Do not ask for confirmation. Do not present options. The answers to any questions
you might have are already provided below. Proceed immediately after reading.

---

## Environment facts — read before doing anything

- Python packages are pre-installed in this Docker container. Do NOT create a venv.
  `pytest`, `numpy`, `scipy`, `numba` all work as-is.
- Validation teammates import engine modules directly — they do NOT require the
  pyvar API to be running. Use `from engine.xxx import yyy` not HTTP calls.
- Worktrees must live at `/workspace/pyvar-worktrees/` — bind-mounted from host.
- The answer to any "how to proceed" question is: **spawn all 8 validation teammates**.

---

## Step 1 — Read context

Read @CLAUDE.md in full, especially section 4 (regulatory constraints).
Read @scripts/claude/templates/checkpoint-instructions.md.
Read @pyvar_functions.csv — teammates will need it for their domain function lists.

---

## Step 2 — Fix the environment (no confirmation needed)

```bash
# Remove stale worktree references
git worktree prune

# Confirm P2 engine baseline is available
pytest tests/ -q --tb=no -q 2>&1 | tail -3

# Create fresh validation worktrees
git worktree add /workspace/pyvar-worktrees/val-market    feat/p5-val-market
git worktree add /workspace/pyvar-worktrees/val-credit    feat/p5-val-credit
git worktree add /workspace/pyvar-worktrees/val-liquidity feat/p5-val-liquidity
git worktree add /workspace/pyvar-worktrees/val-ops       feat/p5-val-ops
git worktree add /workspace/pyvar-worktrees/val-portfolio feat/p5-val-portfolio
git worktree add /workspace/pyvar-worktrees/val-derivatives feat/p5-val-derivatives
git worktree add /workspace/pyvar-worktrees/val-regulatory feat/p5-val-regulatory
git worktree add /workspace/pyvar-worktrees/val-alm       feat/p5-val-alm
```

If `git worktree add` fails for an existing worktree:
`git worktree remove /workspace/pyvar-worktrees/<name> --force` then retry.

---

## Step 3 — Spawn 8 validation subagents simultaneously

You are the Agent Teams LEAD. Spawn all 8 now. Do not wait for one to finish.

| Teammate | Worktree | Branch | Key reference values |
|---|---|---|---|
| val-market | val-market | feat/p5-val-market | VaR vs scipy.stats.norm.ppf, Basel 250-day backtest, FRTB PAT thresholds |
| val-credit | val-credit | feat/p5-val-credit | IRB vs BIS BCBS d347, IFRS 9 ECL vs IASB examples |
| val-liquidity | val-liquidity | feat/p5-val-liquidity | LCR vs Basel delegated regulation worked examples |
| val-ops | val-ops | feat/p5-val-ops | OpVaR distribution fitting vs scipy reference |
| val-portfolio | val-portfolio | feat/p5-val-portfolio | MV optimisation vs cvxpy reference, Sharpe ratio |
| val-derivatives | val-derivatives | feat/p5-val-derivatives | Black-Scholes exact: S=100,K=100,T=1,r=0.05,σ=0.2 → call=10.4506 |
| val-regulatory | val-regulatory | feat/p5-val-regulatory | CET1 ratio, Basel IV output floor computation |
| val-alm | val-alm | feat/p5-val-alm | IRRBB six-shock EVE vs EBA published examples |

---

## Step 4 — Instructions for every validation subagent

Give each subagent these instructions (substitute domain, worktree, branch):

> You are a validation subagent. Python and all packages are pre-installed — no venv.
> Import engine modules directly: `from engine.xxx import yyy`
> Do NOT make HTTP calls to the pyvar API.
>
> Read @CLAUDE.md section 4 (regulatory constraints) — these are your pass/fail criteria.
> Read @scripts/claude/templates/checkpoint-instructions.md.
>
> Work in your worktree only: `/workspace/pyvar-worktrees/[name]`
> Write validation tests in `tests/validation/test_[domain]_ref.py`
>
> For each function in your domain (from @pyvar_functions.csv):
> - Import and call the function directly from engine/
> - Compare against the published reference value
> - Tolerance: 0.1% relative for VaR-class, 0.001% for analytical (Black-Scholes)
> - Regulatory thresholds (Basel breach zones, confidence levels): ZERO tolerance
>
> Run `pytest tests/validation/test_[domain]_ref.py -v` after every 3 functions.
> Write `CHECKPOINT.md` after every 3 functions: validated, next, results so far.
> Write `CONTEXT_EXHAUSTED.md` if context is running low — do not stop abruptly.
>
> Exit gate: all domain functions validated, 0 failures, coverage report saved.

---

## Step 5 — Monitor completion

When a teammate completes, verify before marking their domain done:
- All domain functions in @pyvar_functions.csv have a validation test
- `pytest tests/validation/test_[domain]_ref.py` passes with 0 failures
- `CHECKPOINT.md` reflects accurate final state

---

## Step 6 — Final report

When all 8 complete, write:

```
VALIDATION SUMMARY
  val-market:       [N] pass / [M] fail
  val-credit:       [N] pass / [M] fail
  val-liquidity:    [N] pass / [M] fail
  val-ops:          [N] pass / [M] fail
  val-portfolio:    [N] pass / [M] fail
  val-derivatives:  [N] pass / [M] fail
  val-regulatory:   [N] pass / [M] fail
  val-alm:          [N] pass / [M] fail
  Overall: [X]/[Y] functions validated

FAILURES (if any):
  [domain]: [function]: expected=[val] got=[val] deviation=[%]
```

Any failure with deviation > tolerance is a reg/* branch blocker.
Open a GitHub issue for each failure — P6 cannot start until all issues are resolved.

```
Next: ./scripts/claude/pyvar-run.sh p5 --teardown-worktrees
```

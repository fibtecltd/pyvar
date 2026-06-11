# P2 Agent Teams — Engine Implementation
# Used by: pyvar-run.sh p2 --mode agent
# Machine: M4 only

Do not ask for confirmation. Do not present options. The answers to any questions
you might have are already provided below. Proceed immediately after reading.

---

## Environment facts — read before doing anything

- Python packages are pre-installed in this Docker container image. Do NOT create a
  venv. Do NOT run pip install. `pytest`, `numpy`, `numba`, `scipy` all work as-is.
- Working directory is `/workspace/pyvar` — the full pyvar repo is here.
- Worktrees must live at `/workspace/pyvar-worktrees/` — that path is bind-mounted
  from the host. Do not use relative `../` paths.
- The answer to "sequential vs teams vs single domain" is: **teams**. Proceed.

---

## Step 1 — Read context

Read @CLAUDE.md in full.
Read @scripts/claude/templates/checkpoint-instructions.md.
Read @pyvar_functions.csv — you will need it for domain function lists.

---

## Step 2 — Fix the environment (do this first, no confirmation needed)

```bash
# Remove stale Mac worktree references
git worktree prune

# Confirm Market Risk baseline passes in this container
pytest tests/test_var_models.py tests/test_expected_shortfall.py \
       tests/test_backtesting.py tests/test_greeks.py \
       tests/test_pnl_attribution.py tests/test_stress.py \
       tests/test_volatility.py tests/test_frtb.py -q

# Create fresh worktrees at container-accessible paths
git worktree add /workspace/pyvar-worktrees/credit-risk feat/p2-credit-risk
git worktree add /workspace/pyvar-worktrees/liquidity-ops feat/p2-liquidity-ops
git worktree add /workspace/pyvar-worktrees/portfolio-reg feat/p2-portfolio-reg
git worktree add /workspace/pyvar-worktrees/drv-alm feat/p2-drv-alm
```

If pytest fails, fix the failures before spawning teammates.
If `git worktree add` fails because the branch already has a worktree,
run `git worktree remove /workspace/pyvar-worktrees/<name> --force` first.

---

## Step 3 — Spawn 4 subagents simultaneously

You are the Agent Teams LEAD. Spawn all 4 now. Do not wait for one to finish
before starting the next.

**credit-risk**
- Worktree: `/workspace/pyvar-worktrees/credit-risk`
- Branch: `feat/p2-credit-risk`
- Scope: Credit Risk — 55 functions from @pyvar_functions.csv (DOMAIN = "Credit Risk")

**liquidity-ops**
- Worktree: `/workspace/pyvar-worktrees/liquidity-ops`
- Branch: `feat/p2-liquidity-ops`
- Scope: Liquidity Risk (40) + Operational Risk (44) = 84 functions

**portfolio-reg**
- Worktree: `/workspace/pyvar-worktrees/portfolio-reg`
- Branch: `feat/p2-portfolio-reg`
- Scope: Portfolio Analytics (50) + Regulatory & Compliance (30) = 80 functions

**drv-alm**
- Worktree: `/workspace/pyvar-worktrees/drv-alm`
- Branch: `feat/p2-drv-alm`
- Scope: Derivatives & Pricing (62) + ALM & Balance Sheet (33) = 95 functions

---

## Step 4 — Instructions for every subagent

Give each subagent these instructions (substitute domain, worktree, branch):

> You are a domain implementation subagent. Python is pre-installed — no venv needed.
>
> Read @CLAUDE.md sections 3.1 (Numba rules), 4 (regulatory), 5 (testing).
> Read @scripts/claude/templates/checkpoint-instructions.md.
>
> Work in your worktree only: `/workspace/pyvar-worktrees/[name]`
> Read @pyvar_functions.csv — implement every function in your assigned domains.
>
> For each function:
> - Implement in `engine/` following Numba rules (stateless @njit, float64, cache=True)
> - Write a numerical correctness test — no mocking of engine code
> - Run `pytest tests/test_[module].py -x -q` before committing
>
> After every 5 functions:
>   `git add -A && git commit -m "feat(p2-[domain]): implement [function]"`
>   Write `CHECKPOINT.md` with: done, next, git state.
>
> If context is running low: write `CONTEXT_EXHAUSTED.md` — do not stop abruptly.
> Exit only when: all domain functions implemented, pytest passes, no Numba violations.

---

## Step 5 — Monitor completion

When a teammate completes, verify:
- Function count matches @pyvar_functions.csv for their domain
- `pytest` passes in their worktree
- Zero Numba violations, zero regulatory violations

---

## Step 6 — Final report

When all 4 complete, write:

```
ALL DOMAINS COMPLETE
  credit-risk:   [N] functions, [M] tests
  liquidity-ops: [N] functions, [M] tests
  portfolio-reg: [N] functions, [M] tests
  drv-alm:       [N] functions, [M] tests
Total: 314 functions

Next: ./scripts/claude/pyvar-run.sh p2 --teardown-worktrees
```

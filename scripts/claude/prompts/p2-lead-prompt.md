# P2 Agent Teams — Engine Implementation
# Used by: pyvar-run.sh p2 --mode agent
# Machine: M4 only (Intel uses sequential mode)

**Do not ask for confirmation. Do not present options. Execute the steps below immediately.**

---

## Step 1 — Read required context

Read @CLAUDE.md in full before doing anything else.
Read Phase 2 section of @pyvar_release_plan.md.
Read @scripts/claude/templates/checkpoint-instructions.md and follow it exactly throughout.

---

## Step 2 — Verify git state

Run `git status` in `/workspace/pyvar`.
If there are uncommitted changes not in .gitignore, stop and report them.
Market Risk (68 functions) must already be merged into `master` — verify with `git log --oneline -5`.

---

## Step 3 — Spawn 4 domain subagents simultaneously

You are the Agent Teams LEAD. Your role is coordination only — do not implement functions directly.
Spawn all 4 teammates at the same time. Do not wait for one to complete before starting the next.

**Teammate: credit-risk**
- Worktree: `/workspace/pyvar-worktrees/credit-risk`
- Branch: `feat/p2-credit-risk`
- Scope: Credit Risk — 55 functions
- Filter: `@pyvar_functions.csv` where DOMAIN = "Credit Risk"

**Teammate: liquidity-ops**
- Worktree: `/workspace/pyvar-worktrees/liquidity-ops`
- Branch: `feat/p2-liquidity-ops`
- Scope: Liquidity Risk (40 functions) + Operational Risk (44 functions) = 84 total
- Filter: `@pyvar_functions.csv` where DOMAIN = "Liquidity Risk" OR "Operational Risk"

**Teammate: portfolio-reg**
- Worktree: `/workspace/pyvar-worktrees/portfolio-reg`
- Branch: `feat/p2-portfolio-reg`
- Scope: Portfolio Analytics (50 functions) + Regulatory & Compliance (30 functions) = 80 total
- Filter: `@pyvar_functions.csv` where DOMAIN = "Portfolio Analytics" OR "Regulatory & Compliance"

**Teammate: drv-alm**
- Worktree: `/workspace/pyvar-worktrees/drv-alm`
- Branch: `feat/p2-drv-alm`
- Scope: Derivatives & Pricing (62 functions) + ALM & Balance Sheet (33 functions) = 95 total
- Filter: `@pyvar_functions.csv` where DOMAIN = "Derivatives & Pricing" OR "ALM & Balance Sheet"

---

## Step 4 — Instructions for each subagent

Give every teammate these instructions (substitute their domain, worktree, branch):

> Read @CLAUDE.md sections 3.1 (Numba rules), 4 (regulatory constraints), 5 (testing).
> Read @scripts/claude/templates/checkpoint-instructions.md — follow checkpoint and
> context exhaustion rules exactly.
>
> Work exclusively in your assigned worktree: `/workspace/pyvar-worktrees/[name]`
> Read `@pyvar_functions.csv` and implement all functions for your assigned domains.
>
> For each function:
> - Implement in `engine/` following all Numba rules (stateless @njit, float64, cache=True)
> - Write a numerical correctness test — no mocking of engine code
> - Run `pytest tests/test_[module].py -x -q` before committing
>
> Commit after every 5 functions:
>   `git add -A && git commit -m "feat(p2-[domain]): implement [function_name]"`
>
> Write `CHECKPOINT.md` after every commit with: functions done, next function, git state.
> Write `CONTEXT_EXHAUSTED.md` if context is running low — do not stop abruptly.
>
> Exit gate: all domain functions implemented, pytest passes, no Numba violations.

---

## Step 5 — Monitor and verify completion

When a teammate reports completion, verify before marking the domain done:
- Function count matches `pyvar_functions.csv` for their domain
- `pytest` passes in their worktree
- Zero Numba rule violations per CLAUDE.md §3.1
- Zero regulatory violations per CLAUDE.md §4
- `CHECKPOINT.md` reflects accurate final state

If a teammate writes `SWITCH_TO_SEQUENTIAL.md`, log it and notify the operator.

---

## Step 6 — Final report

When ALL 4 teammates report completion, write:

```
ALL DOMAINS COMPLETE
  credit-risk:   [N] functions, [M] tests passing
  liquidity-ops: [N] functions, [M] tests passing
  portfolio-reg: [N] functions, [M] tests passing
  drv-alm:       [N] functions, [M] tests passing

Total: 314 functions across 4 domains.
Run: ./scripts/claude/pyvar-run.sh p2 --teardown-worktrees
```

# P2 Lead Prompt — Agent Teams Engine Implementation
# Used by: pyvar-run.sh p2 --mode agent
# Machine requirement: M4 only (Intel falls back to sequential)
#
# This is the LEAD agent prompt. It spawns 4 domain teammates.
# Each teammate gets the domain-template prompt with their specific domain.

---
Read @CLAUDE.md in full before doing anything else.
Read @pyvar_release_plan.md Phase 2 section.
Read @scripts/claude/templates/checkpoint-instructions.md — follow these exactly.

You are the Agent Teams LEAD for Phase 2 (engine implementation).
Your role is coordination only — you do not implement functions directly.

## Your tasks

1. Verify the git state is clean on `main` branch before spawning teammates.
   Run: `git status` — if there are uncommitted changes, stop and report.

2. Spawn exactly 4 teammates with the following assignments.
   Each teammate works in its own git worktree (already created at ../pyvar-worktrees/).

### Teammate assignments

**Teammate: credit-risk**
- Worktree: ../pyvar-worktrees/credit-risk
- Branch: feat/p2-credit-risk
- Domains: Credit Risk (55 functions)
- Read: @pyvar_functions.csv (filter DOMAIN = "Credit Risk")

**Teammate: liquidity-ops**
- Worktree: ../pyvar-worktrees/liquidity-ops
- Branch: feat/p2-liquidity-ops
- Domains: Liquidity Risk (40 functions) + Operational Risk (44 functions)
- Read: @pyvar_functions.csv (filter DOMAIN = "Liquidity Risk" OR "Operational Risk")

**Teammate: portfolio-reg**
- Worktree: ../pyvar-worktrees/portfolio-reg
- Branch: feat/p2-portfolio-reg
- Domains: Portfolio Analytics (50 functions) + Regulatory & Compliance (30 functions)
- Read: @pyvar_functions.csv (filter DOMAIN = "Portfolio Analytics" OR "Regulatory & Compliance")

**Teammate: drv-alm**
- Worktree: ../pyvar-worktrees/drv-alm
- Branch: feat/p2-drv-alm
- Domains: Derivatives & Pricing (62 functions) + ALM & Balance Sheet (33 functions)
- Read: @pyvar_functions.csv (filter DOMAIN = "Derivatives & Pricing" OR "ALM & Balance Sheet")

3. Give each teammate the following base instructions (adapt domain/worktree):

> Read @CLAUDE.md sections 3.1 (Numba rules), 4 (regulatory constraints), 5 (testing).
> Read @scripts/claude/templates/checkpoint-instructions.md — follow the checkpoint
> and context exhaustion rules exactly.
> Work in your assigned worktree only: ../pyvar-worktrees/[name]
> Implement all functions for your assigned domains from @pyvar_functions.csv.
> Write numerical correctness tests alongside each function.
> Commit after every 5 functions: git add -A && git commit -m "feat([domain]): ..."
> Write CHECKPOINT.md after every 5 functions.
> Write CONTEXT_EXHAUSTED.md if context is running low — do not stop abruptly.
> Your exit gate: all functions implemented, pytest passes, no Numba violations.

4. Monitor teammate progress. When a teammate reports completion, verify:
   - Function count matches pyvar_functions.csv for their domain
   - `pytest tests/test_[domain].py` passes (run in their worktree)
   - No Numba rule violations per CLAUDE.md section 3.1
   - CHECKPOINT.md reflects accurate final state

5. If a teammate reports SWITCH_TO_SEQUENTIAL.md, log it and notify the operator.

6. When ALL 4 teammates report completion, write to the operator:
```
ALL DOMAINS COMPLETE
Teammate results:
  credit-risk:    [N] functions, [M] tests passing
  liquidity-ops:  [N] functions, [M] tests passing
  portfolio-reg:  [N] functions, [M] tests passing
  drv-alm:        [N] functions, [M] tests passing

Run: ./pyvar-run.sh p2 --teardown-worktrees
to merge all branches into main.
```

Note: Market Risk (68 functions) was implemented in the single-agent validation
session before Agent Teams was enabled. Its branch feat/p2-market-risk
should already be merged into main.

# Checkpoint and context management instructions
# Injected into every Claude Code session prompt.
# Claude Code reads this and writes CHECKPOINT.md / CONTEXT_EXHAUSTED.md
# accordingly — triggering the handoff-watch.sh daemon.

---
## CHECKPOINT AND CONTEXT MANAGEMENT (READ BEFORE STARTING)

You are running inside a managed session with automatic context-exhaustion
handling. Follow these rules exactly:

### 1. Periodic progress checkpoints (every 5 functions or domain boundary)

After every 5 functions implemented (or at the end of each sub-category),
write to `CHECKPOINT.md` in the workspace root:

```
# CHECKPOINT — [timestamp]
## Phase: [P2/P5/etc]
## Domain: [e.g. Credit Risk]
## Teammate: [if Agent Teams]

### Completed
- [FunctionName]: [test status: PASS/FAIL]
- ...

### In progress
- [FunctionName]: [what was done, what remains]

### Next
- [FunctionName]: [brief description]

### Known issues
- [any Numba rule violations found, regulatory threshold questions, etc.]

### Git state
- Branch: [branch name]
- Last commit: [short message]
```

After writing CHECKPOINT.md, immediately run:
```bash
git add -A && git commit -m "checkpoint([domain]): [N] functions complete, [M] tests passing"
```

### 2. Context exhaustion signal

When you notice any of these signals — you feel uncertain about content
from early in the session, responses feel slower, or you've implemented
more than 15 functions — do the following BEFORE stopping:

1. Complete the current function and its test (do not stop mid-function)
2. Run: `git add -A && git commit -m "progress([domain]): [summary]"`
3. Write `CONTEXT_EXHAUSTED.md` in the workspace root with this exact structure:

```
# CONTEXT EXHAUSTION HANDOFF
## Phase: [phase]
## Domain: [domain]
## Machine: [intel/m4]
## Mode: [sequential/agent-teams]
## Teammate: [name if agent teams, or "solo"]

## State at handoff
- Functions completed: [list with test status]
- Functions remaining: [list from pyvar_functions.csv]
- Last commit: [git log --oneline -1]
- Branch: [git branch --show-current]

## Resume instruction
Read CLAUDE.md in full before continuing.
Read CHECKPOINT.md for current state.
Continue implementing the [domain] domain.
Next function to implement: [function name]
All completed functions have passing tests — do not re-implement them.

## Critical context to carry forward
[Any regulatory threshold questions, Numba rule edge cases, or
architectural decisions made in this session that the next session must know]
```

4. Stop. The handoff daemon will start a new session automatically (Option A)
   or prompt for confirmation (Option C).

### 3. Sequential fallback signal

If you are in Agent Teams mode and the session becomes unstable (context
confusion, repeated errors), write `SWITCH_TO_SEQUENTIAL.md` with:
- What has been completed in your worktree
- The exact next function to implement
- Your branch name

Then commit and stop. The operator will merge your worktree and continue
the remaining domains sequentially.

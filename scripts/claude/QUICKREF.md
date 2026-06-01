# pyvar-run.sh — Quick Reference

## Setup (once)

```bash
# 1. Install fswatch (auto-handoff dependency)
brew install fswatch

# 2. Make scripts executable
chmod +x ~/claude-docker/scripts/pyvar-run.sh
chmod +x ~/claude-docker/scripts/lib/*.sh

# 3. Create shared Docker network
docker network create pyvar_net
```

## Phase reference

| Phase | Mode on M4 | Mode on Intel | Agent Teams |
|---|---|---|---|
| P1 | sequential | sequential | off |
| **P2** | **agent (4 teammates)** | sequential | **PRIMARY** |
| P3 | sequential | sequential | off |
| P4 | sequential | sequential | off |
| **P5** | **agent (8 teammates)** | sequential | conditional |
| P6–P9 | sequential | sequential | off |

---

## Daily workflow — most common commands

```bash
cd ~/claude-docker/scripts

# Start phase with auto-detected mode and hybrid handoff
./pyvar-run.sh p2

# Resume last session for a phase
./pyvar-run.sh p2 --resume

# Resume specific session
./pyvar-run.sh p2 --resume <session-id>

# Preview what would run (no execution)
./pyvar-run.sh p2 --dry-run

# List all saved sessions
./pyvar-run.sh sessions
```

---

## Machine-specific resource overrides

```bash
# Force Intel profile (e.g. when on M4 but memory-constrained)
./pyvar-run.sh p2 --machine intel

# Force M4 profile
./pyvar-run.sh p2 --machine m4

# Resources auto-detected if --machine not set:
#   Intel i5 2.5GHz:  claude 1 CPU / 2 GB  |  worker 1.5 CPU / 4 GB
#   M4 4.4GHz:        claude 4 CPU / 5 GB  |  worker 4 CPU  / 4 GB
```

---

## Mode switching

```bash
# Force Agent Teams (M4 only — ignored on Intel)
./pyvar-run.sh p2 --mode agent

# Force sequential (any machine)
./pyvar-run.sh p2 --mode seq

# Switch mid-flight: commit all worktrees and switch to sequential
# (run from inside container or separate terminal)
./pyvar-run.sh p2 --mode seq --worktree credit-risk
```

---

## Git worktrees (P2 Agent Teams)

```bash
# Step 1: create worktrees before starting Agent Teams session
./pyvar-run.sh p2 --setup-worktrees

# Step 2: run Agent Teams session (worktrees are auto-mounted)
./pyvar-run.sh p2 --mode agent

# Step 3: merge completed worktrees into main
./pyvar-run.sh p2 --teardown-worktrees

# Step 3 (dry-run): preview merge commands
./pyvar-run.sh p2 --teardown-worktrees --dry-run

# Run in a specific worktree (sequential fallback for one domain)
./pyvar-run.sh p2 --mode seq --worktree credit-risk --resume
```

---

## Context exhaustion / auto-handoff

```bash
# Option A — fully automatic (new session starts immediately)
./pyvar-run.sh p2 --handoff auto

# Option C — hybrid (pauses, asks you to confirm)
./pyvar-run.sh p2 --handoff hybrid    # default

# Resume from a saved handoff file manually
./pyvar-run.sh p2 --handoff-file ~/.pyvar-sessions/handoff-p2-20260425T143000Z.md
```

The handoff watcher runs in the background whenever pyvar-run.sh starts.
It watches for `CONTEXT_EXHAUSTED.md` in `/workspace/pyvar`.
Claude Code writes this file automatically per the checkpoint instructions.

If fswatch is not installed, auto-handoff is disabled with a warning:
```bash
brew install fswatch
```

---

## Full Option C stack (both containers)

```bash
# Start pyvar stack first
cd ~/projects/pyvar && docker compose up -d

# Then start Claude Code session
./pyvar-run.sh p3
# Claude can reach http://pyvar-api:8000 over pyvar_net
```

---

## Backup and restore sessions

```bash
# Backup claude_home volume (preserves all sessions + plugins)
docker run --rm \
  -v claude-docker_claude_home:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/claude_home_$(date +%Y%m%d).tar.gz -C /data .

# Restore
docker run --rm \
  -v claude-docker_claude_home:/data \
  -v $(pwd):/backup \
  alpine sh -c "cd /data && tar xzf /backup/claude_home_YYYYMMDD.tar.gz"
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `fswatch not found` | not installed | `brew install fswatch` |
| Agent Teams not starting on M4 | AT setting not applied | `./pyvar-run.sh p2 --at-only` |
| Worktree already exists | previous run not cleaned | `git worktree list`, then `git worktree remove ../pyvar-worktrees/credit-risk` |
| Context exhaustion not detected | Claude did not write CONTEXT_EXHAUSTED.md | Check session prompt includes checkpoint-instructions.md |
| Merge conflict on teardown | teammate modified same file | `git mergetool` in pyvar root |
| Plugin not found on Intel | marketplace not registered | `./pyvar-run.sh p1` applies plugin config fresh |

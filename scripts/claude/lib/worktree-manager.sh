#!/bin/sh
# lib/worktree-manager.sh
# Git worktree management for Agent Teams parallel sessions.
# Source this file; do not execute it directly.
#
# P2 domains → 4 worktrees (2 domains per teammate)
# P5 domains → 8 worktrees (1 domain per validation teammate)

PYVAR_ROOT="${PYVAR_WORKSPACE:-$HOME/projects/pyvar}"
WORKTREE_BASE="${PYVAR_ROOT}/../pyvar-worktrees"

# ── P2 worktree map ────────────────────────────────────────────────
# teammate : branch : domains
P2_WORKTREES="
credit-risk:feat/p2-credit-risk:Credit Risk (55 functions)
liquidity-ops:feat/p2-liquidity-ops:Liquidity Risk + Operational Risk (84 functions)
portfolio-reg:feat/p2-portfolio-reg:Portfolio Analytics + Regulatory (80 functions)
drv-alm:feat/p2-drv-alm:Derivatives + ALM (95 functions)
"

# ── P5 worktree map ────────────────────────────────────────────────
P5_WORKTREES="
val-market:feat/p5-val-market:Market Risk validation
val-credit:feat/p5-val-credit:Credit Risk validation
val-liquidity:feat/p5-val-liquidity:Liquidity Risk validation
val-ops:feat/p5-val-ops:Operational Risk validation
val-portfolio:feat/p5-val-portfolio:Portfolio Analytics validation
val-regulatory:feat/p5-val-regulatory:Regulatory validation
val-derivatives:feat/p5-val-derivatives:Derivatives validation
val-alm:feat/p5-val-alm:ALM validation
"

# ── setup_worktrees ────────────────────────────────────────────────
# Creates git worktrees for the given phase.
# Usage: setup_worktrees p2 | setup_worktrees p5
setup_worktrees() {
    local phase="$1"
    local map=""

    case "$phase" in
        p2) map="$P2_WORKTREES" ;;
        p5) map="$P5_WORKTREES" ;;
        *)
            echo "[worktree] ERROR: phase '$phase' has no worktree map."
            return 1
            ;;
    esac

    mkdir -p "$WORKTREE_BASE"

    echo "[worktree] Setting up $phase worktrees in $WORKTREE_BASE ..."
    echo "$map" | while IFS=: read -r name branch desc; do
        [ -z "$name" ] && continue
        local path="$WORKTREE_BASE/$name"

        if [ -d "$path" ]; then
            echo "[worktree]   (exists) $name — $desc"
            continue
        fi

        # Create branch from main if it doesn't exist
        if ! git -C "$PYVAR_ROOT" show-ref --verify --quiet "refs/heads/$branch"; then
            git -C "$PYVAR_ROOT" branch "$branch" master
        fi

        git -C "$PYVAR_ROOT" worktree add "$path" "$branch"
        echo "[worktree]   ✓ $name ($branch) — $desc"
        echo "[worktree]     path: $path"
    done

    echo "[worktree] Setup complete."
    list_worktrees "$phase"
}

# ── list_worktrees ─────────────────────────────────────────────────
list_worktrees() {
    echo ""
    echo "Active worktrees:"
    git -C "$PYVAR_ROOT" worktree list
}

# ── teardown_worktrees ─────────────────────────────────────────────
# Merges completed worktrees back to main and removes them.
# Usage: teardown_worktrees p2 [--dry-run]
teardown_worktrees() {
    local phase="$1"
    local dry_run="$2"
    local map=""

    case "$phase" in
        p2) map="$P2_WORKTREES" ;;
        p5) map="$P5_WORKTREES" ;;
        *) echo "[worktree] ERROR: unknown phase '$phase'"; return 1 ;;
    esac

    echo "[worktree] Merging $phase worktrees into master ..."

    echo "$map" | while IFS=: read -r name branch desc; do
        [ -z "$name" ] && continue
        local path="$WORKTREE_BASE/$name"

        if [ ! -d "$path" ]; then
            echo "[worktree]   (skip) $name — worktree not found"
            continue
        fi

        # Check for uncommitted changes
        if ! git -C "$path" diff --quiet HEAD 2>/dev/null; then
            echo "[worktree]   ⚠ $name has uncommitted changes — committing first."
            git -C "$path" add -A
            git -C "$path" commit -m "wip($name): auto-commit before merge"
        fi

        if [ "$dry_run" = "--dry-run" ]; then
            echo "[worktree]   [dry-run] would merge $branch into master"
            continue
        fi

        # Merge into master
        git -C "$PYVAR_ROOT" checkout master
        if git -C "$PYVAR_ROOT" merge --no-ff "$branch" \
                -m "merge($phase): $desc"; then
            echo "[worktree]   ✓ merged $branch"
            # Remove worktree and branch
            git -C "$PYVAR_ROOT" worktree remove "$path" --force
            git -C "$PYVAR_ROOT" branch -d "$branch"
            echo "[worktree]   ✓ removed worktree $name"
        else
            echo "[worktree]   ✗ CONFLICT in $branch — resolve manually, then:"
            echo "             git -C $PYVAR_ROOT merge --continue"
        fi
    done

    echo "[worktree] Teardown complete."
}

# ── switch_to_sequential ───────────────────────────────────────────
# Emergency: commit all worktrees' progress, leave branches open,
# switch to sequential mode without merging.
# Called when Agent Teams session needs to be abandoned mid-flight.
switch_to_sequential() {
    local phase="$1"
    local map=""

    case "$phase" in
        p2) map="$P2_WORKTREES" ;;
        p5) map="$P5_WORKTREES" ;;
        *) echo "[worktree] ERROR: unknown phase '$phase'"; return 1 ;;
    esac

    echo "[worktree] Committing all worktrees for manual sequential resume ..."

    echo "$map" | while IFS=: read -r name branch desc; do
        [ -z "$name" ] && continue
        local path="$WORKTREE_BASE/$name"
        [ -d "$path" ] || continue

        local changed
        changed=$(git -C "$path" status --porcelain)
        if [ -n "$changed" ]; then
            git -C "$path" add -A
            git -C "$path" commit -m "wip($name): switch to sequential" || true
            echo "[worktree]   ✓ committed $name"
        else
            echo "[worktree]   (clean) $name — nothing to commit"
        fi
    done

    echo ""
    echo "[worktree] All worktrees committed. Branches preserved."
    echo "           Resume each domain as a single-agent session using:"
    echo "           ./pyvar-run.sh $phase --mode seq --worktree <name>"
}

export PYVAR_ROOT WORKTREE_BASE

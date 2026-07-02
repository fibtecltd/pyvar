#!/bin/bash
# ================================================================
# run.sh — Generic phase launcher
# Location: ~/projects/pyvar/scripts/claude/run.sh
#
# Bundles all 4 phase steps into a single command:
#   1. Generate settings.local.json for the given phase + mode
#   2. Set up worktrees (only for phases with a worktree map: p2, p5, p5b)
#   3. Launch Claude Code session (prompt injected from <phase>-lead-prompt.md)
#   4. Tear down worktrees after session completes (worktree phases only)
#
# Usage:
#   ./scripts/claude/run.sh <phase>                    full run, auto mode
#   ./scripts/claude/run.sh <phase> --mode agent       force Agent Teams
#   ./scripts/claude/run.sh <phase> --mode seq         force sequential
#   ./scripts/claude/run.sh <phase> --dry-run          preview only
#   ./scripts/claude/run.sh <phase> --skip-setup       skip steps 1+2
#   ./scripts/claude/run.sh <phase> --teardown-only    run step 4 only
#   ./scripts/claude/run.sh <phase> --resume           resume last session
#   ./scripts/claude/run.sh <phase> --handoff auto     Option A handoff
#   ./scripts/claude/run.sh <phase> --handoff hybrid   Option C handoff (default)
#
# Phases with worktree support (steps 2+4 active):
#   p2   — engine implementation (4 worktrees)
#   p5   — validation + coverage (8 worktrees)
#   p5b  — remainder testing (3 worktrees)
#
# Phases without worktrees (steps 2+4 skipped):
#   p1, p3, p4, p6, p7, p8, p9
# ================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYVAR_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Phases that have worktree maps in worktree-manager.sh
WORKTREE_PHASES="p2 p5 p5b"

# ── Parse arguments ───────────────────────────────────────────────
PHASE=""
MODE="auto"
HANDOFF="hybrid"
DRY_RUN=0
SKIP_SETUP=0
TEARDOWN_ONLY=0
RESUME_FLAG=""

while [ $# -gt 0 ]; do
    case "$1" in
        p[1-9]|p5b)
            PHASE="$1"; shift ;;
        --mode)
            MODE="$2"; shift 2 ;;
        --handoff)
            HANDOFF="$2"; shift 2 ;;
        --dry-run)
            DRY_RUN=1; shift ;;
        --skip-setup)
            SKIP_SETUP=1; shift ;;
        --teardown-only)
            TEARDOWN_ONLY=1; shift ;;
        --resume)
            RESUME_FLAG="--resume"; shift ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: $0 <phase> [--mode agent|seq] [--handoff auto|hybrid]"
            echo "           [--dry-run] [--skip-setup] [--teardown-only] [--resume]"
            exit 1 ;;
    esac
done

if [ -z "$PHASE" ]; then
    echo "Usage: $0 <phase> [options]"
    echo "Phases: p1 p2 p3 p4 p5 p5b p6 p7 p8 p9"
    exit 1
fi

# ── Helpers ───────────────────────────────────────────────────────
run() {
    if [ $DRY_RUN -eq 1 ]; then
        echo "[dry-run] $*"
    else
        eval "$*"
    fi
}

has_worktrees() {
    echo "$WORKTREE_PHASES" | grep -qw "$PHASE"
}

header() {
    echo ""
    echo "╔════════════════════════════════════════════════════════╗"
    printf "║  %-54s ║\n" "$1"
    printf "║  %-54s ║\n" "$2"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
}

PHASE_UPPER="$(echo "$PHASE" | tr '[:lower:]' '[:upper:]')"
header "run.sh · Phase $PHASE_UPPER" "mode=$MODE  handoff=$HANDOFF  worktrees=$(has_worktrees && echo yes || echo no)"

# ── Teardown only ─────────────────────────────────────────────────
if [ $TEARDOWN_ONLY -eq 1 ]; then
    if has_worktrees; then
        echo "[$PHASE] Teardown only — tearing down worktrees ..."
        run "$SCRIPT_DIR/pyvar-run.sh" "$PHASE" --teardown-worktrees ${DRY_RUN:+--dry-run}
    else
        echo "[$PHASE] Phase $PHASE has no worktrees — teardown not applicable."
    fi
    exit 0
fi

# ── Step 1 — Generate settings.local.json ─────────────────────────
if [ $SKIP_SETUP -eq 0 ]; then
    echo "[$PHASE] Step 1 — Generating settings.local.json (phase=$PHASE mode=$MODE) ..."
    # Resolve auto → agent before passing to write-settings-local.py
    # (write-settings-local.py only understands "agent" or "seq", not "auto")
    RESOLVED_MODE="$MODE"
    [ "$MODE" = "auto" ] && RESOLVED_MODE="agent"
    run python3 "$SCRIPT_DIR/write-settings-local.py" "$PHASE" --mode "$RESOLVED_MODE"
    echo ""

    # ── Step 2 — Set up worktrees (only for worktree phases) ──────
    if has_worktrees; then
        echo "[$PHASE] Step 2 — Setting up worktrees ..."
        run "$SCRIPT_DIR/pyvar-run.sh" "$PHASE" --setup-worktrees ${DRY_RUN:+--dry-run}
        echo ""
    else
        echo "[$PHASE] Step 2 — Skipped (phase $PHASE has no worktree map)."
        echo ""
    fi
else
    echo "[$PHASE] Steps 1+2 skipped (--skip-setup)."
    echo ""
fi

# ── Step 3 — Launch Claude Code session ───────────────────────────
echo "[$PHASE] Step 3 — Launching Claude Code session ..."
if [ -f "$SCRIPT_DIR/prompts/${PHASE}-lead-prompt.md" ]; then
    echo "         Prompt: prompts/${PHASE}-lead-prompt.md"
else
    echo "         WARNING: prompts/${PHASE}-lead-prompt.md not found — interactive session."
fi
echo ""

PYVAR_RUN_ARGS="$PHASE --mode $MODE --handoff $HANDOFF"
[ -n "$RESUME_FLAG" ] && PYVAR_RUN_ARGS="$PYVAR_RUN_ARGS $RESUME_FLAG"
[ $DRY_RUN -eq 1 ]   && PYVAR_RUN_ARGS="$PYVAR_RUN_ARGS --dry-run"

run "$SCRIPT_DIR/pyvar-run.sh" $PYVAR_RUN_ARGS

SESSION_EXIT=$?
echo ""
echo "[$PHASE] Session ended (exit code $SESSION_EXIT)."

# ── Step 4 — Tear down worktrees (only for worktree phases) ───────
if has_worktrees; then
    echo ""
    echo "[$PHASE] Step 4 — Worktree teardown."
    echo "         Review and merge feat/${PHASE}-* PRs on GitHub before confirming."
    echo ""
    read -r -p "         Proceed with teardown? [y/N] " confirm
    if [ "${confirm:-N}" = "y" ] || [ "${confirm:-N}" = "Y" ]; then
        run "$SCRIPT_DIR/pyvar-run.sh" "$PHASE" --teardown-worktrees ${DRY_RUN:+--dry-run}
        echo "[$PHASE] Teardown complete."
    else
        echo "[$PHASE] Teardown skipped. Run when ready:"
        echo "         $SCRIPT_DIR/run.sh $PHASE --teardown-only"
    fi
else
    echo "[$PHASE] Step 4 — Skipped (phase $PHASE has no worktrees)."
fi

echo ""
echo "[$PHASE] Done."

#!/bin/bash
# ================================================================
# pyvar-resume.sh — Express session resume utility
# Location: ~/claude-docker/scripts/pyvar-resume.sh
#
# The fastest way to resume a Claude Code session for any pyvar phase.
# Handles session ID storage, listing, and launching in one command.
#
# Usage:
#   ./pyvar-resume.sh <phase>                   resume last saved session
#   ./pyvar-resume.sh <phase> <session-id>      resume explicit session ID
#   ./pyvar-resume.sh <phase> --worktree <name> resume worktree session
#   ./pyvar-resume.sh --save <phase> <id>       save a session ID manually
#   ./pyvar-resume.sh --save <phase> <id> <wt>  save with worktree tag
#   ./pyvar-resume.sh --list                    list all saved sessions
#   ./pyvar-resume.sh --capture <phase>         auto-save from container
#   ./pyvar-resume.sh --from-handoff <phase> <timestamp>  resume handoff
#   ./pyvar-resume.sh --native                  list Claude Code's own sessions
#   ./pyvar-resume.sh --where                   show where session files live
#   ./pyvar-resume.sh --dry-run <phase>         show command without running
#
# Examples:
#   ./pyvar-resume.sh p2
#   ./pyvar-resume.sh p2 3a8f1c2d-4b9e-4f7a-8c6d-1e2f3a4b5c6d
#   ./pyvar-resume.sh p2 --worktree credit-risk
#   ./pyvar-resume.sh --save p2 3a8f1c2d-4b9e-4f7a-8c6d-1e2f3a4b5c6d
#   ./pyvar-resume.sh --capture p2
#   ./pyvar-resume.sh --list
#   ./pyvar-resume.sh --native
# ================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib/detect-machine.sh"
. "$SCRIPT_DIR/lib/session-manager.sh"

CLAUDE_DOCKER_DIR="${CLAUDE_DOCKER_DIR:-$HOME/claude-docker}"
COMPOSE_FILE="$CLAUDE_DOCKER_DIR/docker-compose.yml"
PYVAR_WORKSPACE="${PYVAR_WORKSPACE:-$HOME/projects/pyvar}"

# ── Parse arguments ───────────────────────────────────────────────
ACTION="resume"
PHASE=""
SESSION_ID=""
WORKTREE=""
HANDOFF_TS=""
DRY_RUN=0

case "${1:-}" in
    --list)    ACTION="list";    shift ;;
    --save)    ACTION="save";    shift ;;
    --capture) ACTION="capture"; shift ;;
    --native)  ACTION="native";  shift ;;
    --where)   ACTION="where";   shift ;;
    --from-handoff) ACTION="from-handoff"; shift ;;
    --dry-run) DRY_RUN=1; ACTION="resume"; shift ;;
    p[1-9])    PHASE="$1"; shift ;;
    "")        ACTION="list" ;;
esac

# Remaining args
while [ $# -gt 0 ]; do
    case "$1" in
        --worktree) WORKTREE="$2"; shift 2 ;;
        --dry-run)  DRY_RUN=1; shift ;;
        p[1-9])     PHASE="$1"; shift ;;
        ????????-????-????-????-????????????) SESSION_ID="$1"; shift ;;
        2[0-9][0-9][0-9][0-9][0-9][0-9][0-9]T*) HANDOFF_TS="$1"; shift ;;
        *)  echo "Unrecognised argument: $1"; exit 1 ;;
    esac
done

# ── Helper: build and run docker compose run ──────────────────────
run_session() {
    local phase="$1"
    local resume_id="$2"
    local workdir="${3:-/workspace/pyvar}"

    # M4 uses Opus for Agent Teams phases; other phases use default
    local model=""
    case "$phase" in p2|p5) [ "$AGENT_TEAMS_OK" -eq 1 ] && model="--model claude-opus-4-8" ;; esac

    local cmd
    cmd="docker compose -f \"$COMPOSE_FILE\" run --rm \
  --cpus $CLAUDE_CPUS \
  --memory $CLAUDE_MEM \
  -w $workdir \
  claude $model --resume $resume_id"

    echo ""
    echo "  Phase   : $phase"
    echo "  Session : $resume_id"
    echo "  Workdir : $workdir"
    echo "  Machine : $MACHINE  ($CLAUDE_CPUS CPU / $CLAUDE_MEM)"
    echo "  Command : $cmd"
    echo ""

    if [ "$DRY_RUN" -eq 1 ]; then
        echo "  [dry-run] — not executed."
    else
        eval "$cmd"
        # After session ends, auto-capture the (possibly updated) session ID
        auto_save_from_container "$phase" "$WORKTREE"
    fi
}

# ── Actions ───────────────────────────────────────────────────────
case "$ACTION" in

    # ── LIST ───────────────────────────────────────────────────────
    list)
        list_sessions
        ;;

    # ── SAVE ───────────────────────────────────────────────────────
    save)
        if [ -z "$PHASE" ] || [ -z "$SESSION_ID" ]; then
            echo "Usage: ./pyvar-resume.sh --save <phase> <session-id> [worktree]"
            echo "Example:"
            echo "  ./pyvar-resume.sh --save p2 3a8f1c2d-4b9e-4f7a-8c6d-1e2f3a4b5c6d"
            exit 1
        fi
        save_session "$PHASE" "$SESSION_ID" "$WORKTREE"
        ;;

    # ── CAPTURE ────────────────────────────────────────────────────
    # Auto-reads the latest session ID from inside the container.
    # Run this right after a session ends.
    capture)
        if [ -z "$PHASE" ]; then
            echo "Usage: ./pyvar-resume.sh --capture <phase> [worktree]"
            exit 1
        fi
        echo "Reading latest session from container ..."
        auto_save_from_container "$PHASE" "$WORKTREE"
        ;;

    # ── NATIVE ─────────────────────────────────────────────────────
    # Lists Claude Code's own session files inside the container.
    # Shows UUIDs without our abstraction layer — useful for digging
    # out a session ID that was never saved to ~/.pyvar-sessions/.
    native)
        echo ""
        echo "Claude Code native session files (inside container)"
        echo "Path: /home/claude/.claude/projects/"
        echo "────────────────────────────────────────────────────"
        docker compose -f "$COMPOSE_FILE" exec -u claude claude \
            sh -c 'find /home/claude/.claude/projects -name "*.jsonl" \
                        2>/dev/null | xargs ls -lt 2>/dev/null \
                   | awk "{print NR\". \"$9, $5, $6, $7, $8}" \
                   | sed "s|.*/projects/[^/]*/||"' \
            2>/dev/null \
            || echo "  (container not running — start with: docker compose up -d claude)"
        echo ""
        echo "To resume any listed session:"
        echo "  ./pyvar-resume.sh <phase> <uuid-from-list>"
        echo ""
        ;;

    # ── WHERE ──────────────────────────────────────────────────────
    # Explains exactly where session files live on every layer.
    where)
        echo ""
        echo "Session file locations"
        echo "══════════════════════════════════════════════════════"
        echo ""
        echo "1. pyvar-resume.sh session registry (host)"
        echo "   $SESSION_DIR/"
        ls -1 "$SESSION_DIR"/last-session-* 2>/dev/null | sed 's/^/   /' || echo "   (empty)"
        echo ""
        echo "2. Claude Code native storage (inside Docker volume)"
        echo "   Volume : claude-docker_claude_home"
        echo "   Path   : /home/claude/.claude/projects/<hash>/<uuid>.jsonl"
        echo "   View   : ./pyvar-resume.sh --native"
        echo ""
        echo "3. Docker volume on host (macOS Docker Desktop)"
        echo "   ~/Library/Containers/com.docker.docker/Data/vms/0/data/docker.raw"
        echo "   (not directly accessible — use docker exec or volume backup)"
        echo ""
        echo "4. Backup (if you ran the volume backup command)"
        echo "   ~/claude_home_YYYYMMDD.tar.gz"
        echo "   Contains: .claude/projects/ with all session JSONL files"
        echo ""
        echo "5. Handoff prompts (context-exhaustion records)"
        echo "   $SESSION_DIR/handoff-<phase>-<timestamp>.md"
        ls -1 "$SESSION_DIR"/handoff-*.md 2>/dev/null | sed 's/^/   /' || echo "   (none)"
        echo ""
        echo "6. Session log (all saves)"
        echo "   $SESSION_LOG"
        [ -f "$SESSION_LOG" ] && tail -5 "$SESSION_LOG" | sed 's/^/   /' || echo "   (empty)"
        echo ""
        ;;

    # ── FROM-HANDOFF ───────────────────────────────────────────────
    # Resumes from a saved handoff prompt file (after context exhaustion
    # was saved-and-stopped rather than auto-continued).
    from-handoff)
        if [ -z "$PHASE" ] || [ -z "$HANDOFF_TS" ]; then
            echo "Usage: ./pyvar-resume.sh --from-handoff <phase> <timestamp>"
            echo "       Timestamp format: 20260501T120000Z"
            echo "       (see ./pyvar-resume.sh --where for saved handoffs)"
            exit 1
        fi
        HANDOFF_FILE="$SESSION_DIR/handoff-$PHASE-$HANDOFF_TS.md"
        if [ ! -f "$HANDOFF_FILE" ]; then
            echo "Handoff file not found: $HANDOFF_FILE"
            echo "Available handoffs:"
            ls "$SESSION_DIR"/handoff-"$PHASE"-*.md 2>/dev/null | sed 's/^/  /' \
                || echo "  (none for phase $PHASE)"
            exit 1
        fi

        echo "Resuming from handoff: $HANDOFF_FILE"
        echo ""
        head -10 "$HANDOFF_FILE"
        echo "..."
        echo ""

        # Build the continuation prompt
        PROMPT_TMP=$(mktemp /tmp/pyvar-handoff-XXXXXX.md)
        cat "$HANDOFF_FILE" > "$PROMPT_TMP"

        WORKDIR="/workspace/pyvar"
        [ -n "$WORKTREE" ] && WORKDIR="/workspace/../pyvar-worktrees/$WORKTREE"

        local model=""
        case "$PHASE" in p2|p5) [ "$AGENT_TEAMS_OK" -eq 1 ] && model="--model claude-opus-4-8" ;; esac

        CMD="docker compose -f \"$COMPOSE_FILE\" run --rm \
  --cpus $CLAUDE_CPUS \
  --memory $CLAUDE_MEM \
  -w $WORKDIR \
  claude $model"

        if [ "$DRY_RUN" -eq 1 ]; then
            echo "[dry-run] Would run: $CMD --print '$(head -3 "$PROMPT_TMP")...'"
        else
            eval "$CMD" -- --print "$(cat "$PROMPT_TMP")"
            auto_save_from_container "$PHASE" "$WORKTREE"
        fi
        rm -f "$PROMPT_TMP"
        ;;

    # ── RESUME (default) ───────────────────────────────────────────
    resume)
        if [ -z "$PHASE" ]; then
            echo "Usage: ./pyvar-resume.sh <phase> [session-id] [--worktree <name>]"
            echo "Run ./pyvar-resume.sh --list to see saved sessions."
            exit 1
        fi

        # Determine session ID to resume
        if [ -n "$SESSION_ID" ]; then
            # Explicit ID provided on command line
            echo "Using explicit session ID: $SESSION_ID"
            # Save it so future --resume without ID finds it
            save_session "$PHASE" "$SESSION_ID" "$WORKTREE"
        else
            # Look up from our registry
            SESSION_ID=$(get_session "$PHASE" "$WORKTREE")
            if [ -z "$SESSION_ID" ]; then
                echo "No saved session found for phase $PHASE${WORKTREE:+ worktree=$WORKTREE}."
                echo ""
                echo "Options:"
                echo "  1. Run ./pyvar-resume.sh --native to list Claude's own sessions"
                echo "     then: ./pyvar-resume.sh $PHASE <uuid>"
                echo "  2. Run ./pyvar-resume.sh --capture $PHASE after a session ends"
                echo "  3. Start fresh: ./pyvar-run.sh $PHASE"
                exit 1
            fi
            echo "Found saved session for $PHASE: $SESSION_ID"
        fi

        # Determine working directory
        WORKDIR="/workspace/pyvar"
        [ -n "$WORKTREE" ] && WORKDIR="/workspace/../pyvar-worktrees/$WORKTREE"

        run_session "$PHASE" "$SESSION_ID" "$WORKDIR"
        ;;

esac

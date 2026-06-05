#!/bin/bash
# lib/handoff-watch.sh  (v2 — cross-platform)
# Watches for CONTEXT_EXHAUSTED.md using the platform-appropriate watcher.
#
# Replaces the fswatch-only v1 with a backend that works on:
#   macOS       → fswatch
#   Linux       → inotifywait
#   WSL         → inotifywait (on Linux filesystem)
#   Any         → poll fallback (5s latency, no deps)
#
# Usage (called by pyvar-run.sh):
#   bash ./lib/handoff-watch.sh <phase> <mode:auto|hybrid> <session_cmd> &
#   WATCH_PID=$!

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/file-watcher.sh"
. "$SCRIPT_DIR/session-manager.sh"

PHASE="${1:-p2}"
HANDOFF_MODE="${2:-hybrid}"
SESSION_CMD="${3:-}"

WORKSPACE="${PYVAR_WORKSPACE:-$HOME/projects/pyvar}"
EXHAUSTED_FILE="$WORKSPACE/CONTEXT_EXHAUSTED.md"
SESSION_STATE_DIR="${HOME}/.pyvar-sessions"
LOG_FILE="$SESSION_STATE_DIR/handoff.log"

mkdir -p "$SESSION_STATE_DIR"

log() { echo "[handoff-watch $(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }

log "Starting — phase=$PHASE  mode=$HANDOFF_MODE  backend=$(detect_watcher_backend 2>/dev/null; echo $WATCHER_BACKEND)"

# ── Main loop ─────────────────────────────────────────────────────
# watch_for_file blocks until CONTEXT_EXHAUSTED.md appears, then
# we process it. Loop restarts after each handled event.
while true; do

    # Block until trigger file appears
    watch_for_file "$WORKSPACE" "CONTEXT_EXHAUSTED.md"

    # Brief pause to ensure Claude Code has finished writing the file
    sleep 2
    [ -f "$EXHAUSTED_FILE" ] || { log "File vanished — continuing watch."; continue; }

    HANDOFF_PROMPT=$(cat "$EXHAUSTED_FILE")
    TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
    HANDOFF_SAVED="$SESSION_STATE_DIR/handoff-$PHASE-$TIMESTAMP.md"

    echo "$HANDOFF_PROMPT" > "$HANDOFF_SAVED"
    log "Context exhaustion detected. Handoff saved: $(basename "$HANDOFF_SAVED")"

    echo ""
    echo "┌────────────────────────────────────────────────────────┐"
    echo "│  CONTEXT EXHAUSTED  ·  Phase $PHASE  ·  Mode: $HANDOFF_MODE"
    echo "├────────────────────────────────────────────────────────┤"
    echo "$HANDOFF_PROMPT" | head -20
    echo "└────────────────────────────────────────────────────────┘"
    echo ""

    case "$HANDOFF_MODE" in

        auto)
            log "Option A — launching new session in 5s (Ctrl+C to cancel)."
            echo "  [Option A] New session starts in 5 seconds ..."
            sleep 5
            rm -f "$EXHAUSTED_FILE"
            _launch_continuation "$PHASE" "$SESSION_CMD" "$HANDOFF_SAVED"
            ;;

        hybrid)
            echo "  [Option C] Continue?  y=yes  n=stop  s=save-and-stop"
            printf "  > "; read -r answer </dev/tty
            case "$answer" in
                y|Y)
                    rm -f "$EXHAUSTED_FILE"
                    _launch_continuation "$PHASE" "$SESSION_CMD" "$HANDOFF_SAVED"
                    ;;
                s|S)
                    log "Saved and stopped."
                    echo "  Resume later: ./pyvar-resume.sh --from-handoff $PHASE $TIMESTAMP"
                    exit 0
                    ;;
                *)
                    rm -f "$EXHAUSTED_FILE"
                    log "User declined continuation."
                    exit 0
                    ;;
            esac
            ;;
    esac
done

# ── Helper: launch continuation session ──────────────────────────
_launch_continuation() {
    local phase="$1"
    local cmd="$2"
    local handoff_file="$3"

    PROMPT_TMP=$(mktemp /tmp/pyvar-handoff-XXXXXX.md)
    cat "$handoff_file" > "$PROMPT_TMP"

    log "Launching continuation session for $phase ..."

    if [ -n "$cmd" ]; then
        eval "$cmd" -- --print "$(cat "$PROMPT_TMP")"
    else
        log "No SESSION_CMD — start manually: ./pyvar-resume.sh $phase"
    fi

    rm -f "$PROMPT_TMP"
    log "Continuation session ended. Restarting watcher."
}

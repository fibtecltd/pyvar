#!/bin/sh
# lib/session-manager.sh  (v2)
#
# WHERE CLAUDE CODE STORES SESSION IDs
# ─────────────────────────────────────────────────────────────────
#
# Claude Code stores conversation history inside the container at:
#
#   /home/claude/.claude/projects/
#
# This directory is persisted via the claude_home named Docker volume,
# so it survives container restarts.
#
# Directory structure:
#
#   /home/claude/.claude/
#   └── projects/
#       └── <path-hash>/           ← SHA derived from the working dir
#           └── <session-id>.jsonl ← one file per session (JSONL)
#
# The <path-hash> is computed from the absolute path Claude Code was
# started in, e.g. /workspace/pyvar → a hex string like "a3f2c8d1..."
#
# The <session-id> is a UUID v4, e.g.:
#   3a8f1c2d-4b9e-4f7a-8c6d-1e2f3a4b5c6d
#
# Claude Code shows the session ID:
#   - In the terminal header when a session starts
#   - Via: claude --resume          (interactive picker)
#   - Via: claude --resume <id>     (direct jump)
#
# THIS SCRIPT saves those IDs to the HOST at:
#   ~/.pyvar-sessions/
#   ├── last-session-p1              ← last ID for phase p1
#   ├── last-session-p2              ← last ID for phase p2
#   ├── last-session-p2-credit-risk  ← worktree-scoped ID
#   ├── sessions.log                 ← append-only audit log
#   └── handoff-p2-<timestamp>.md    ← handoff prompts
# ─────────────────────────────────────────────────────────────────

SESSION_DIR="${HOME}/.pyvar-sessions"
SESSION_LOG="$SESSION_DIR/sessions.log"
mkdir -p "$SESSION_DIR"

save_session() {
    local phase="$1" sid="$2" worktree="${3:-}"
    # Warn if not UUID format
    case "$sid" in
        ????????-????-????-????-????????????) ;;
        *) echo "[session] WARNING: '$sid' does not look like a UUID." ;;
    esac
    local key="last-session-$phase"
    [ -n "$worktree" ] && key="last-session-$phase-$worktree"
    echo "$sid" > "$SESSION_DIR/$key"
    printf "%s  %-12s  %-20s  %s\n" \
        "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$phase" "${worktree:-(main)}" "$sid" \
        >> "$SESSION_LOG"
    echo "[session] Saved: $key = $sid"
}

get_session() {
    local phase="$1" worktree="${2:-}"
    local key="last-session-$phase"
    [ -n "$worktree" ] && key="last-session-$phase-$worktree"
    [ -f "$SESSION_DIR/$key" ] && cat "$SESSION_DIR/$key" || echo ""
}

list_sessions() {
    echo ""
    echo "Saved pyvar session IDs  (host: $SESSION_DIR)"
    echo "────────────────────────────────────────────────────────────────"
    printf "  %-28s  %s\n" "Key" "Session ID"
    echo "────────────────────────────────────────────────────────────────"
    local found=0
    for f in "$SESSION_DIR"/last-session-*; do
        [ -f "$f" ] || continue
        local key; key=$(basename "$f" | sed 's/last-session-//')
        local sid; sid=$(cat "$f")
        printf "  %-28s  %s\n" "$key" "$sid"
        found=1
    done
    [ "$found" -eq 0 ] && echo "  (no saved sessions)"
    echo "────────────────────────────────────────────────────────────────"
    echo "Full log: $SESSION_LOG"
    echo ""
}

# Auto-capture session ID from inside the running container
# by finding the most recently modified .jsonl file.
auto_save_from_container() {
    local phase="$1" worktree="${2:-}"
    local compose_file="${CLAUDE_DOCKER_DIR:-$HOME/claude-docker}/docker-compose.yml"
    local sid
    sid=$(docker compose -f "$compose_file" exec -u claude claude \
        sh -c 'find /home/claude/.claude/projects -name "*.jsonl" \
               2>/dev/null | xargs ls -t 2>/dev/null | head -1 \
               | xargs basename 2>/dev/null | sed "s/\.jsonl//"' 2>/dev/null || echo "")
    if [ -n "$sid" ]; then
        save_session "$phase" "$sid" "$worktree"
    else
        echo "[session] Could not auto-capture. Save manually:"
        echo "          ./pyvar-resume.sh --save $phase <uuid>"
    fi
}

build_handoff_context() {
    # Returns content of CONTEXT_EXHAUSTED.md if it exists, else empty string.
    # Called by pyvar-run.sh to inject handoff context into the next session.
    local exhausted_file="${PYVAR_WORKSPACE:-$HOME/projects/pyvar}/CONTEXT_EXHAUSTED.md"
    if [ -f "$exhausted_file" ]; then
        cat "$exhausted_file"
    else
        echo ""
    fi
}

clear_exhausted_flag() {
    # Removes CONTEXT_EXHAUSTED.md after its content has been injected.
    local exhausted_file="${PYVAR_WORKSPACE:-$HOME/projects/pyvar}/CONTEXT_EXHAUSTED.md"
    rm -f "$exhausted_file"
    echo "[session] CONTEXT_EXHAUSTED.md cleared."
}

# Append all three to the end of session-manager.sh, before the export line:

build_handoff_context() {
    local exhausted="${PYVAR_WORKSPACE:-$HOME/projects/pyvar}/CONTEXT_EXHAUSTED.md"
    [ -f "$exhausted" ] && cat "$exhausted" || echo ""
}

clear_exhausted_flag() {
    rm -f "${PYVAR_WORKSPACE:-$HOME/projects/pyvar}/CONTEXT_EXHAUSTED.md"
    echo "[session] CONTEXT_EXHAUSTED.md cleared."
}

build_checkpoint_context() {
    local checkpoint="${PYVAR_WORKSPACE:-$HOME/projects/pyvar}/CHECKPOINT.md"
    [ -f "$checkpoint" ] && cat "$checkpoint" || echo ""
}

get_session_id() {
    get_session "$@"
}

export SESSION_DIR SESSION_LOG

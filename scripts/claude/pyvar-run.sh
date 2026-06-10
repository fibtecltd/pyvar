#!/bin/bash
# ================================================================
# pyvar-run.sh — Master Claude Code session launcher
# Location: ~/claude-docker/scripts/pyvar-run.sh
#
# Handles all four session concerns:
#   1. Resume        — --resume / session-id tracking
#   2. Resources     — auto-detected per machine (Intel vs M4)
#   3. Worktrees     — git worktree setup/teardown for P2/P5
#   4. Context       — fswatch daemon, auto-handoff (Option A/C)
#
# Usage:
#   ./pyvar-run.sh <phase>                    default run
#   ./pyvar-run.sh <phase> --resume           resume last session
#   ./pyvar-run.sh <phase> --resume <id>      resume specific session
#   ./pyvar-run.sh <phase> --mode agent       force Agent Teams (M4 only)
#   ./pyvar-run.sh <phase> --mode seq         force sequential
#   ./pyvar-run.sh <phase> --handoff auto     Option A — auto restart
#   ./pyvar-run.sh <phase> --handoff hybrid   Option C — confirm restart
#   ./pyvar-run.sh <phase> --worktree <name>  run in specific worktree
#   ./pyvar-run.sh <phase> --setup-worktrees  create worktrees then exit
#   ./pyvar-run.sh <phase> --teardown-worktrees  merge worktrees then exit
#   ./pyvar-run.sh <phase> --dry-run          show commands, no execution
#   ./pyvar-run.sh sessions                   list saved sessions
#   ./pyvar-run.sh <phase> --machine intel    override machine detection
#   ./pyvar-run.sh <phase> --machine m4
# ================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"
PROMPTS_DIR="$SCRIPT_DIR/prompts"
TEMPLATES_DIR="$SCRIPT_DIR/templates"

CLAUDE_DOCKER_DIR="${CLAUDE_DOCKER_DIR:-$HOME/claude-docker}"
PYVAR_WORKSPACE="${PYVAR_WORKSPACE:-$HOME/projects/pyvar}"
COMPOSE_FILE="$CLAUDE_DOCKER_DIR/docker-compose.yml"

# ── Source libraries ──────────────────────────────────────────────
. "$LIB_DIR/detect-machine.sh"
. "$LIB_DIR/session-manager.sh"
. "$LIB_DIR/worktree-manager.sh"

# ── Defaults ──────────────────────────────────────────────────────
PHASE=""
RESUME_FLAG=""
RESUME_ID=""
MODE="auto"           # auto | agent | seq
HANDOFF_MODE="hybrid" # auto | hybrid
WORKTREE_NAME=""
SETUP_WT=0
TEARDOWN_WT=0
DRY_RUN=0
EXTRA_ARGS=""
SKIP_PERMS=""

# ── Parse arguments ───────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        p[1-9]|sessions) PHASE="$1"; shift ;;
        --resume)
            RESUME_FLAG="--resume"
            if [ -n "${2:-}" ] && [[ "${2:-}" != --* ]]; then
                RESUME_ID="$2"; shift
            fi
            shift ;;
        --mode)        MODE="$2";         shift 2 ;;
        --handoff)     HANDOFF_MODE="$2"; shift 2 ;;
        --worktree)    WORKTREE_NAME="$2"; shift 2 ;;
        --machine)     PYVAR_MACHINE="$2"; . "$LIB_DIR/detect-machine.sh"; shift 2 ;;
        --setup-worktrees)    SETUP_WT=1;    shift ;;
        --teardown-worktrees) TEARDOWN_WT=1; shift ;;
        --dry-run)     DRY_RUN=1;         shift ;;
        --dangerously-skip-permissions) SKIP_PERMS="--dangerously-skip-permissions"; shift ;;
        --) shift; EXTRA_ARGS="$*"; break ;;
        *)  echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Helpers ───────────────────────────────────────────────────────
run() {
    if [ $DRY_RUN -eq 1 ]; then
        echo "[dry-run] $*"
    else
        eval "$*"
    fi
}

header() {
    echo ""
    echo "╔════════════════════════════════════════════════════════╗"
    printf "║  %-54s ║\n" "$1"
    printf "║  %-54s ║\n" "$2"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
}

# ── Special commands ──────────────────────────────────────────────
if [ "$PHASE" = "sessions" ]; then
    list_sessions
    exit 0
fi

if [ -z "$PHASE" ]; then
    echo "Usage: ./pyvar-run.sh <p1..p9> [options]"
    echo "       ./pyvar-run.sh sessions"
    exit 1
fi

header "pyvar-run.sh · Phase $(echo "$PHASE" | tr '[:lower:]' '[:upper:]')" "machine=$MACHINE  mode=$MODE  handoff=$HANDOFF_MODE"

# ── Step 1: Machine resource profile ─────────────────────────────
echo "[1/6] Machine: $MACHINE"
echo "      claude: --cpus $CLAUDE_CPUS --memory $CLAUDE_MEM"
echo "      worker: --cpus $WORKER_CPUS --memory $WORKER_MEM"
echo "      Agent Teams viable: $AGENT_TEAMS_OK"

# ── Step 2: Resolve mode ──────────────────────────────────────────
if [ "$MODE" = "auto" ]; then
    case "$PHASE" in
        p2|p5)
            if [ "$AGENT_TEAMS_OK" -eq 1 ]; then
                MODE="agent"
            else
                echo "[2/6] Mode auto → sequential (Intel hardware; Agent Teams not viable)"
                MODE="seq"
            fi
            ;;
        *) MODE="seq" ;;
    esac
fi

if [ "$MODE" = "agent" ] && [ "$AGENT_TEAMS_OK" -eq 0 ]; then
    echo "[2/6] WARNING: Agent Teams requested on Intel. Overriding to sequential."
    MODE="seq"
fi
echo "[2/6] Mode: $MODE"

# ── Step 3: Worktree operations ───────────────────────────────────
if [ $SETUP_WT -eq 1 ]; then
    echo "[3/6] Setting up worktrees for $PHASE ..."
    run setup_worktrees "$PHASE"
    echo "      Worktrees ready. Run without --setup-worktrees to start session."
    exit 0
fi

if [ $TEARDOWN_WT -eq 1 ]; then
    echo "[3/6] Tearing down worktrees for $PHASE ..."
    run teardown_worktrees "$PHASE" "${DRY_RUN:+--dry-run}"
    exit 0
fi

# Determine working directory inside container
if [ -n "$WORKTREE_NAME" ]; then
    WORKDIR="/workspace/../pyvar-worktrees/$WORKTREE_NAME"
    echo "[3/6] Worktree: $WORKTREE_NAME (branch: feat/$PHASE-$WORKTREE_NAME)"
else
    WORKDIR="/workspace/pyvar"
    echo "[3/6] Workspace: $WORKDIR"
fi

# ── Step 4: Phase plugin configuration ───────────────────────────
PHASE_SCRIPT="$PYVAR_WORKSPACE/scripts/claude/pyvar-phase.sh"
if [ -f "$PHASE_SCRIPT" ]; then
    echo "[4/6] Applying phase plugin config ..."
    run bash "$PHASE_SCRIPT" "$PHASE" ${DRY_RUN:+--dry-run}

    # Toggle Agent Teams in settings.json
    if [ "$MODE" = "agent" ]; then
        run bash "$PHASE_SCRIPT" "$PHASE" --at-only
    fi
else
    echo "[4/6] WARNING: pyvar-phase.sh not found at $PHASE_SCRIPT — skipping plugin config."
fi

# ── Step 5: Build resume flag ─────────────────────────────────────
RESUME=""
if [ -n "$RESUME_FLAG" ]; then
    if [ -n "$RESUME_ID" ]; then
        RESUME="--resume $RESUME_ID"
    else
        SAVED_ID=$(get_session_id "$PHASE")
        if [ -n "$SAVED_ID" ]; then
            RESUME="--resume $SAVED_ID"
            echo "[5/6] Resuming session: $SAVED_ID"
        else
            echo "[5/6] No saved session for $PHASE — starting fresh."
        fi
    fi
else
    # Check for checkpoint from previous exhausted session
    HANDOFF=$(build_handoff_context)
    if [ -n "$HANDOFF" ]; then
        echo "[5/6] Found CONTEXT_EXHAUSTED.md — will inject handoff prompt."
        clear_exhausted_flag
    fi
fi

# Build checkpoint injection
CHECKPOINT_CTX=$(build_checkpoint_context)
if [ -n "$CHECKPOINT_CTX" ]; then
    echo "[5/6] CHECKPOINT.md found — will inject as context."
fi

# ── Step 6: Build and execute docker compose run ─────────────────
echo "[6/6] Launching Claude Code session ..."
echo ""

# Select prompt file for this phase+mode
if [ "$MODE" = "agent" ]; then
    case "$PHASE" in
        p2) PROMPT_FILE="$PROMPTS_DIR/p2-lead-prompt.md" ;;
        p5) PROMPT_FILE="$PROMPTS_DIR/p5-lead-prompt.md" ;;
        *)  PROMPT_FILE="" ;;
    esac
else
    PROMPT_FILE=""
fi

# Choose Claude model
if [ "$MODE" = "agent" ]; then
    CLAUDE_MODEL="--model claude-opus-4-8"
else
    CLAUDE_MODEL=""
fi

# Build the base docker compose run command
SESSION_CMD="docker compose -f \"$COMPOSE_FILE\" run --rm -T \
  --cpus $CLAUDE_CPUS \
  --memory $CLAUDE_MEM \
  --memory-reservation ${CLAUDE_MEM%g}00m \
  -w $WORKDIR \
  claude $SKIP_PERMS --print $CLAUDE_MODEL $RESUME"

# Append --print with handoff prompt if resuming from context exhaustion
PRINT_FLAG=""
if [ -n "${HANDOFF:-}" ]; then
    PRINT_TMP=$(mktemp /tmp/pyvar-prompt-XXXXXX.md)
    {
        cat "$TEMPLATES_DIR/checkpoint-instructions.md"
        echo ""
        echo "---"
        echo "## HANDOFF CONTEXT (from previous exhausted session)"
        echo ""
        echo "$HANDOFF"
        echo ""
        echo "---"
        echo "Continue from where the previous session left off."
    } > "$PRINT_TMP"
    PRINT_FLAG="--print \"$(cat "$PRINT_TMP" | head -50)...\""
    FULL_PROMPT_FILE="$PRINT_TMP"
elif [ -n "$PROMPT_FILE" ] && [ -f "$PROMPT_FILE" ]; then
    PRINT_TMP=$(mktemp /tmp/pyvar-prompt-XXXXXX.md)
    {
        cat "$TEMPLATES_DIR/checkpoint-instructions.md"
        echo ""
        echo "---"
        if [ -n "$CHECKPOINT_CTX" ]; then
            echo "## CHECKPOINT (from previous session)"
            echo ""
            echo "$CHECKPOINT_CTX"
            echo ""
            echo "---"
        fi
        cat "$PROMPT_FILE"
    } > "$PRINT_TMP"
    FULL_PROMPT_FILE="$PRINT_TMP"
else
    FULL_PROMPT_FILE=""
fi

# Start fswatch handoff daemon (background)
WATCH_PID=""
if [ -n "$PYVAR_WORKSPACE" ] && command -v fswatch >/dev/null 2>&1; then
    echo "      Starting handoff watcher (mode=$HANDOFF_MODE) ..."
    bash "$LIB_DIR/handoff-watch.sh" "$PHASE" "$HANDOFF_MODE" "$SESSION_CMD" &
    WATCH_PID=$!
    echo "      Watcher PID: $WATCH_PID"
else
    echo "      WARNING: fswatch not found — auto-handoff disabled."
    echo "               Install: brew install fswatch"
fi

# Execute (or dry-run) the session
if [ $DRY_RUN -eq 1 ]; then
    echo ""
    echo "[dry-run] Would execute:"
    echo "  $SESSION_CMD"
    if [ -n "$FULL_PROMPT_FILE" ]; then
        echo "  with prompt file: $FULL_PROMPT_FILE"
        echo ""
        echo "  Prompt preview (first 20 lines):"
        head -20 "$FULL_PROMPT_FILE" | sed 's/^/    /'
    fi
    echo ""
    echo "  Handoff watcher: $HANDOFF_MODE"
    echo "  Worktrees setup: $([ $SETUP_WT -eq 1 ] && echo yes || echo no)"
else
    # Save session state before starting (session ID captured after start)
    if [ -n "$FULL_PROMPT_FILE" ]; then
        # Inject prompt via --print for the first message
        #CLAUDE_PROMPT=$(cat "$FULL_PROMPT_FILE")
        eval "$SESSION_CMD" < "$FULL_PROMPT_FILE"
        rm -f "$FULL_PROMPT_FILE" "${PRINT_TMP:-}"
    else
        eval "$SESSION_CMD"
    fi

    EXIT_CODE=$?
    echo ""
    echo "[pyvar-run] Session ended (exit code $EXIT_CODE)"
fi

# Stop the handoff watcher
if [ -n "$WATCH_PID" ]; then
    kill "$WATCH_PID" 2>/dev/null || true
    echo "[pyvar-run] Handoff watcher stopped (PID $WATCH_PID)"
fi

# Offer worktree merge after P2/P5 completes
if [ "$MODE" = "agent" ] && [ $DRY_RUN -eq 0 ]; then
    echo "[pyvar-run] Agent Teams complete."
    echo "            When all domain PRs are merged run:"
    echo "            ./scripts/claude/pyvar-run.sh $PHASE --teardown-worktrees"
fi

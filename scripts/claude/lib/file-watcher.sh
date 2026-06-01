#!/bin/sh
# lib/file-watcher.sh  (v2 — with watchdog integration)
# Cross-platform file watcher.
# Source this file; do not execute it directly.
#
# Backend priority (auto-selected):
#   1. pyvar_watcher.py + watchdog  — pip install watchdog  (recommended)
#   2. pyvar_watcher.py (poll mode) — no deps, pure Python
#   3. inotifywait                  — Linux / WSL Linux fs
#   4. fswatch                      — macOS
#   5. pure shell poll              — universal fallback
#
# WSL + /mnt/c/ warning: backends 1-3 all use inotify internally on Linux.
# None of them can watch Windows NTFS paths from WSL. Keep pyvar on
# the WSL Linux filesystem (~/projects/pyvar), not /mnt/c/.
#
# Install watchdog on the host (recommended):
#   pip3 install watchdog
#   python3 lib/pyvar_watcher.py --status   # verify backend

SCRIPT_DIR="${SCRIPT_DIR:-$(dirname "$0")}"
WATCHER_PY="$SCRIPT_DIR/pyvar_watcher.py"

detect_watcher_backend() {
    OS=$(uname -s)
    WSL=0
    if [ "$OS" = "Linux" ] && grep -qi microsoft /proc/version 2>/dev/null; then
        WSL=1
    fi

    # 1. Python + watchdog (best cross-platform option)
    if [ -f "$WATCHER_PY" ] && command -v python3 >/dev/null 2>&1; then
        if python3 -c "import watchdog" 2>/dev/null; then
            WATCHER_BACKEND="watchdog-py"
            WATCHER_INSTALL="already installed (pip install watchdog)"
            return
        fi
        # Python available but no watchdog — will use poll mode in the script
        WATCHER_BACKEND="poll-py"
        WATCHER_INSTALL="pip3 install watchdog  (for event-driven mode)"
        return
    fi

    # 2. inotifywait (Linux / WSL)
    if command -v inotifywait >/dev/null 2>&1; then
        WATCHER_BACKEND="inotifywait"
        WATCHER_INSTALL="already installed"
        if [ "$WSL" -eq 1 ]; then
            echo "[file-watcher] WSL: inotifywait works only on Linux filesystem." >&2
        fi
        return
    fi

    # 3. fswatch (macOS)
    if [ "$OS" = "Darwin" ] && command -v fswatch >/dev/null 2>&1; then
        WATCHER_BACKEND="fswatch"
        WATCHER_INSTALL="already installed"
        return
    fi

    # 4. Pure shell poll (no deps)
    WATCHER_BACKEND="poll-sh"
    case "$OS" in
        Darwin) WATCHER_INSTALL="brew install fswatch  OR  pip3 install watchdog" ;;
        Linux)  WATCHER_INSTALL="sudo apt-get install inotify-tools  OR  pip3 install watchdog" ;;
        *)      WATCHER_INSTALL="pip3 install watchdog" ;;
    esac
    echo "[file-watcher] No native watcher — using shell poll (5s latency)." >&2
    echo "               Faster option: $WATCHER_INSTALL" >&2

    export WATCHER_BACKEND WATCHER_INSTALL WSL
}

# watch_for_file <directory> <filename>
# Blocks until <filename> appears in <directory>.
watch_for_file() {
    local watch_dir="$1"
    local target_file="$2"

    detect_watcher_backend

    echo "[file-watcher] backend=$WATCHER_BACKEND  dir=$watch_dir  target=$target_file" >&2

    case "$WATCHER_BACKEND" in

        watchdog-py|poll-py)
            # Delegate entirely to the Python script — it auto-selects watchdog or poll
            python3 "$WATCHER_PY" "$watch_dir" "$target_file"
            ;;

        inotifywait)
            while true; do
                inotifywait --quiet -e close_write -e moved_to \
                    --include "${target_file}\$" "$watch_dir" 2>/dev/null
                [ -f "$watch_dir/$target_file" ] && break
            done
            ;;

        fswatch)
            fswatch -1 -e ".*" -i "${target_file}\$" "$watch_dir"
            ;;

        poll-sh)
            local target_path="$watch_dir/$target_file"
            local prev=""
            while true; do
                if [ -f "$target_path" ]; then
                    local cur
                    cur=$(stat -c %Y "$target_path" 2>/dev/null || stat -f %m "$target_path" 2>/dev/null || echo "1")
                    [ "$cur" != "$prev" ] && { prev="$cur"; break; }
                fi
                sleep 5
            done
            ;;
    esac

    echo "[file-watcher] detected: $target_file" >&2
}

print_watcher_status() {
    detect_watcher_backend
    if [ -f "$WATCHER_PY" ] && command -v python3 >/dev/null 2>&1; then
        python3 "$WATCHER_PY" --status
    else
        echo "Backend: $WATCHER_BACKEND"
        echo "Install: $WATCHER_INSTALL"
        echo "Platform: $(uname -s)$([ "${WSL:-0}" -eq 1 ] && echo ' (WSL)')"
    fi
}

export WATCHER_BACKEND WATCHER_INSTALL

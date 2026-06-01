#!/usr/bin/env python3
"""
pyvar_watcher.py
================
Cross-platform file watcher for the pyvar handoff daemon.
Replaces the shell file-watcher.sh when called directly.

Backend priority (auto-selected at startup):
  1. watchdog   — pip install watchdog  (macOS: FSEvents, Linux: inotify, Windows: ReadDirectoryChangesW)
  2. inotifywait — system package       (Linux / WSL on Linux filesystem only)
  3. fswatch     — brew install fswatch (macOS only)
  4. poll        — pure Python, no deps (5s latency, works everywhere)

WSL note: backends 1 and 2 both use inotify internally. Neither can watch
files on Windows NTFS paths (/mnt/c/...). Keep the pyvar workspace on the
WSL Linux filesystem (~/projects/pyvar) — not under /mnt/c/.

Usage (standalone):
    python3 pyvar_watcher.py <watch_dir> <target_filename>
    python3 pyvar_watcher.py ~/projects/pyvar CONTEXT_EXHAUSTED.md
    Exits with code 0 when the file is detected.
    Exits with code 1 on error.

Usage (from shell script):
    python3 lib/pyvar_watcher.py "$WORKSPACE" "CONTEXT_EXHAUSTED.md"
    if [ $? -eq 0 ]; then ... fi

Usage (import):
    from pyvar_watcher import wait_for_file, detect_backend
    backend = detect_backend()
    wait_for_file("~/projects/pyvar", "CONTEXT_EXHAUSTED.md")
"""

import os
import sys
import time
import shutil
import platform
import subprocess
from pathlib import Path


# ── Backend detection ─────────────────────────────────────────────

def detect_backend() -> str:
    """
    Returns the best available backend for this platform.
    Priority: watchdog > inotifywait > fswatch > poll
    """
    # 1. watchdog (Python, cross-platform)
    try:
        import watchdog  # noqa: F401
        return "watchdog"
    except ImportError:
        pass

    os_name = platform.system()

    # 2. inotifywait (Linux / WSL)
    if os_name == "Linux" and shutil.which("inotifywait"):
        return "inotifywait"

    # 3. fswatch (macOS)
    if os_name == "Darwin" and shutil.which("fswatch"):
        return "fswatch"

    # 4. Poll fallback — no dependencies
    return "poll"


def _is_wsl() -> bool:
    """True when running inside WSL (Windows Subsystem for Linux)."""
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except (FileNotFoundError, PermissionError):
        return False


def _warn_wsl_ntfs(watch_dir: str) -> None:
    """Warn if watching a Windows NTFS path from WSL."""
    if _is_wsl() and watch_dir.startswith("/mnt/"):
        print(
            f"[pyvar_watcher] WARNING: WSL + NTFS path detected ({watch_dir}).\n"
            "  inotify (used by watchdog and inotifywait) cannot reliably detect\n"
            "  changes to files on Windows drives from WSL.\n"
            "  Fix: move ~/projects/pyvar to the WSL Linux filesystem, not /mnt/c/.",
            file=sys.stderr,
        )


# ── Backend implementations ───────────────────────────────────────

def _wait_watchdog(watch_dir: str, target_file: str) -> None:
    """
    Event-driven watch using the watchdog library.
    Latency: ~50ms (FSEvents/macOS), ~10ms (inotify/Linux).
    Install: pip install watchdog
    """
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

    target_path = os.path.join(os.path.abspath(watch_dir), target_file)
    found = threading_Event()

    class Handler(FileSystemEventHandler):
        def on_created(self, event: FileCreatedEvent) -> None:
            if not event.is_directory and event.src_path == target_path:
                print(f"[pyvar_watcher] watchdog detected: {target_file}", file=sys.stderr)
                found.set()

        def on_modified(self, event: FileModifiedEvent) -> None:
            if not event.is_directory and event.src_path == target_path:
                print(f"[pyvar_watcher] watchdog modified: {target_file}", file=sys.stderr)
                found.set()

    # Import threading Event here to avoid shadowing builtins at module level
    import threading
    found = threading.Event()
    Handler_ = Handler  # rebind after threading import

    observer = Observer()
    observer.schedule(Handler_(), watch_dir, recursive=False)
    observer.start()
    try:
        # Also check if the file already exists (race condition guard)
        if os.path.exists(target_path):
            print(f"[pyvar_watcher] found existing: {target_file}", file=sys.stderr)
            return
        found.wait()  # blocks until file is detected
    finally:
        observer.stop()
        observer.join()


def _wait_inotifywait(watch_dir: str, target_file: str) -> None:
    """
    Event-driven watch using inotifywait (Linux / WSL on Linux fs).
    Latency: ~10ms.
    Install: sudo apt-get install inotify-tools
    """
    cmd = [
        "inotifywait",
        "--quiet",
        "-e", "close_write",
        "-e", "moved_to",
        "--include", f"^{target_file}$",
        watch_dir,
    ]
    while True:
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0:
            # Verify it is the exact file we want
            if os.path.exists(os.path.join(watch_dir, target_file)):
                return


def _wait_fswatch(watch_dir: str, target_file: str) -> None:
    """
    Event-driven watch using fswatch (macOS).
    Latency: ~50ms.
    Install: brew install fswatch
    """
    cmd = [
        "fswatch",
        "-1",                       # exit after first match
        "-e", ".*",                 # exclude everything
        "-i", f"{target_file}$",    # re-include target
        watch_dir,
    ]
    subprocess.run(cmd, check=True)


def _wait_poll(watch_dir: str, target_file: str, interval: float = 5.0) -> None:
    """
    Polling fallback — no dependencies.
    Latency: 0 to `interval` seconds (default 5s).
    Works on macOS, Linux, WSL, Windows (native Python), Docker.
    """
    target_path = os.path.join(watch_dir, target_file)
    last_mtime: float = 0.0

    print(
        f"[pyvar_watcher] poll fallback — checking every {interval}s\n"
        "  For lower latency: pip install watchdog",
        file=sys.stderr,
    )

    while True:
        if os.path.exists(target_path):
            mtime = os.path.getmtime(target_path)
            if mtime != last_mtime:
                last_mtime = mtime
                return
        time.sleep(interval)


# ── Public API ────────────────────────────────────────────────────

def wait_for_file(watch_dir: str, target_file: str) -> None:
    """
    Blocks until <target_file> appears in <watch_dir>.
    Selects the best available backend automatically.
    """
    watch_dir = os.path.expanduser(watch_dir)
    _warn_wsl_ntfs(watch_dir)

    backend = detect_backend()
    print(
        f"[pyvar_watcher] backend={backend}  watching={watch_dir}  target={target_file}",
        file=sys.stderr,
    )

    # 2-second debounce after detection — let Claude Code finish writing the file
    if backend == "watchdog":
        _wait_watchdog(watch_dir, target_file)
    elif backend == "inotifywait":
        _wait_inotifywait(watch_dir, target_file)
    elif backend == "fswatch":
        _wait_fswatch(watch_dir, target_file)
    else:
        _wait_poll(watch_dir, target_file)

    time.sleep(2)


def install_watchdog() -> bool:
    """
    Attempts to pip-install watchdog into the current Python environment.
    Returns True on success.
    """
    print("[pyvar_watcher] Installing watchdog ...", file=sys.stderr)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "watchdog>=6.0.0"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("[pyvar_watcher] watchdog installed successfully.", file=sys.stderr)
        return True
    print(f"[pyvar_watcher] watchdog install failed:\n{result.stderr}", file=sys.stderr)
    return False


def print_status() -> None:
    """Prints backend availability for all platforms."""
    backend = detect_backend()
    wsl = _is_wsl()

    print(f"\nPlatform    : {platform.system()}{' (WSL)' if wsl else ''}")
    print(f"Selected    : {backend}")
    print("")
    print("Backend availability:")
    try:
        import watchdog  # noqa: F401
        print(f"  watchdog     ✓  ({watchdog.__version__})")
    except ImportError:
        print(f"  watchdog     ✗  → pip install watchdog")
    print(f"  inotifywait  {'✓' if shutil.which('inotifywait') else '✗  → sudo apt-get install inotify-tools'}")
    print(f"  fswatch      {'✓' if shutil.which('fswatch') else '✗  → brew install fswatch'}")
    print(f"  poll         ✓  (always available — 5s latency)")

    if wsl:
        print("\nWSL note: inotify (watchdog + inotifywait) only works on the")
        print("  Linux filesystem. Move pyvar to ~/projects/pyvar, not /mnt/c/.")
    print("")


# ── CLI entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in ("--status", "--backends"):
        print_status()
        sys.exit(0)

    if len(sys.argv) == 2 and sys.argv[1] == "--install":
        sys.exit(0 if install_watchdog() else 1)

    if len(sys.argv) != 3:
        print(
            "Usage:\n"
            "  python3 pyvar_watcher.py <watch_dir> <target_file>\n"
            "  python3 pyvar_watcher.py --status\n"
            "  python3 pyvar_watcher.py --install   (pip install watchdog)",
            file=sys.stderr,
        )
        sys.exit(1)

    watch_dir = sys.argv[1]
    target_file = sys.argv[2]

    if not os.path.isdir(os.path.expanduser(watch_dir)):
        print(f"Error: watch_dir does not exist: {watch_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        wait_for_file(watch_dir, target_file)
        print(f"[pyvar_watcher] detected: {target_file}")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n[pyvar_watcher] interrupted.", file=sys.stderr)
        sys.exit(130)

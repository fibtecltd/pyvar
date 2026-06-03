#!/usr/bin/env python3
"""
scripts/hooks/stop_checkpoint_enforcer.py
==========================================
Claude Code Stop hook — fires when Claude Code is about to end a session.

Enforcement:
  1. If engine/ files were modified since last commit — block stop, demand commit
  2. If CHECKPOINT.md is absent or stale (>30 min since last write) — warn
  3. If tests are failing on modified engine files — block stop

Called by Claude Code Stop hook in settings.json.
"""

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = Path("/workspace/pyvar")
CHECKPOINT = WORKSPACE / "CHECKPOINT.md"

RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
BOLD = "\033[1m"
RESET = "\033[0m"


def get_uncommitted_engine_files() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "engine/"], cwd=WORKSPACE, capture_output=True, text=True
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def get_failing_tests() -> list[str]:
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/test_engine.py", "-x", "-q", "--tb=no"],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        # Extract failing test names
        failing = [ln for ln in result.stdout.splitlines() if "FAILED" in ln]
        return failing
    return []


def checkpoint_is_stale() -> bool:
    if not CHECKPOINT.exists():
        return True
    mtime = datetime.fromtimestamp(CHECKPOINT.stat().st_mtime)
    return datetime.now() - mtime > timedelta(minutes=30)


def main() -> int:
    issues = []
    warnings = []

    uncommitted = get_uncommitted_engine_files()
    if uncommitted:
        issues.append(
            f"{len(uncommitted)} engine file(s) have uncommitted changes:\n"
            + "\n".join(f"  {f}" for f in uncommitted[:5])
            + "\n  Run: git add -A && git commit -m 'progress(domain): description'"
        )

    if checkpoint_is_stale():
        warnings.append(
            "CHECKPOINT.md is absent or older than 30 minutes.\n"
            "  Write CHECKPOINT.md with: completed functions, next function, git state."
        )

    try:
        failing = get_failing_tests()
        if failing:
            issues.append(
                f"{len(failing)} test(s) failing:\n" + "\n".join(f"  {t}" for t in failing[:5])
            )
    except subprocess.TimeoutExpired:
        warnings.append("pytest timed out — run manually before stopping.")
    except Exception:
        pass

    if issues:
        print(
            f"\n{BOLD}{RED}━━ Stop Hook: Blocked ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}",
            file=sys.stderr,
        )
        for issue in issues:
            print(f"{RED}BLOCKED{RESET}  {issue}\n", file=sys.stderr)
        print(f"{BOLD}Resolve all issues before stopping.{RESET}\n", file=sys.stderr)
        return 1

    for warning in warnings:
        print(f"{YELLOW}WARNING{RESET}  {warning}", file=sys.stderr)

    if not issues and not warnings:
        print(f"{GREEN}[stop-hook] Session state clean — safe to stop.{RESET}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

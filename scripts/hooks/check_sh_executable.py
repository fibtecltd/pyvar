#!/usr/bin/env python3
"""
scripts/hooks/check_sh_executable.py
====================================
Pre-commit hook: every committed *.sh script must carry the executable bit.

Called by pre-commit with the list of staged *.sh files (see the
`ensure-sh-executable` hook in .pre-commit-config.yaml). For each file staged
with mode 100644, this forces the git index entry to 100755 via
`git add --chmod=+x`, then exits non-zero — the same "fix and force a
re-commit" pattern Black and isort already use in this repo's pre-commit
config.

Deliberately checks/fixes the git INDEX mode (`git ls-files -s`), not the
OS filesystem permission bits (`os.stat`/`Path.chmod`): Windows has no real
POSIX execute bit, so `Path.stat().st_mode` never reports `.sh` files as
executable there regardless of what git has tracked, and `Path.chmod()` is a
no-op for the execute bits on that platform. Operating on the index directly
via `git add --chmod=+x` works identically on Windows, macOS, and Linux, and
is exactly what actually determines the mode of the committed blob.
"""

from __future__ import annotations

import subprocess
import sys

EXECUTABLE_MODE = "100755"


def staged_mode(filepath: str) -> str | None:
    """Return the git index mode (e.g. "100644") for a staged path, or None."""
    result = subprocess.run(
        ["git", "ls-files", "-s", "--", filepath],
        capture_output=True,
        text=True,
        check=True,
    )
    line = result.stdout.strip()
    if not line:
        return None
    return line.split()[0]


def main(files: list[str]) -> int:
    fixed: list[str] = []

    for filepath in files:
        mode = staged_mode(filepath)
        if mode is None or mode == EXECUTABLE_MODE:
            continue

        subprocess.run(["git", "add", "--chmod=+x", "--", filepath], check=True)
        fixed.append(filepath)

    if fixed:
        print("Set +x on the following .sh scripts (re-staged, please commit again):")
        for f in fixed:
            print(f"  {f}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

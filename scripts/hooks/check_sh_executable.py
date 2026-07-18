#!/usr/bin/env python3
"""
scripts/hooks/check_sh_executable.py
====================================
Pre-commit hook: every committed *.sh script must carry the executable bit.

Called by pre-commit with the list of staged *.sh files (see the
`ensure-sh-executable` hook in .pre-commit-config.yaml). For each file missing
+x, this chmods the working-tree file to 0o755 and re-stages it via
`git add`, then exits non-zero — the same "fix and force a re-commit" pattern
Black and isort already use in this repo's pre-commit config.

Why re-stage instead of just chmodding: pre-commit checks out staged content
into a snapshot before running hooks, so committing would otherwise still
happen with the original (non-executable) file mode.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXEC_BITS = 0o111  # owner+group+other execute


def main(files: list[str]) -> int:
    fixed: list[str] = []

    for filepath in files:
        path = Path(filepath)
        if not path.exists():
            continue

        mode = path.stat().st_mode
        if mode & EXEC_BITS == EXEC_BITS:
            continue

        path.chmod(mode | EXEC_BITS)
        subprocess.run(["git", "add", filepath], check=True)
        fixed.append(filepath)

    if fixed:
        print("Set +x on the following .sh scripts (re-staged, please commit again):")
        for f in fixed:
            print(f"  {f}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

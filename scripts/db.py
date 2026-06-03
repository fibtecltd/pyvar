"""
scripts/db.py — Database management CLI for pyvar

Usage:
  python scripts/db.py upgrade          # apply all pending migrations
  python scripts/db.py downgrade -1     # roll back one migration
  python scripts/db.py revision "msg"   # autogenerate new migration
  python scripts/db.py current          # show current revision
  python scripts/db.py history          # show migration history
  python scripts/db.py check            # verify DB matches models
  python scripts/db.py sql              # print upgrade SQL without applying

Reasoning:
- Thin wrapper around Alembic CLI with sensible defaults.
- 'check' command compares the live DB schema to ORM models and
  errors if they diverge — useful in the CDK pipeline health check
  step to catch drift before it causes runtime failures.
- 'sql' mode generates offline SQL for DBA review in regulated environments.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def run_alembic(*args: str) -> int:
    cmd = ["alembic", "-c", str(ROOT / "alembic.ini"), *args]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)  # nosec B603
    return result.returncode


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    extra = sys.argv[2:]

    match command:
        case "upgrade":
            target = extra[0] if extra else "head"
            sys.exit(run_alembic("upgrade", target))

        case "downgrade":
            target = extra[0] if extra else "-1"
            sys.exit(run_alembic("downgrade", target))

        case "revision":
            message = extra[0] if extra else "auto"
            sys.exit(run_alembic("revision", "--autogenerate", "-m", message))

        case "current":
            sys.exit(run_alembic("current"))

        case "history":
            sys.exit(run_alembic("history", "--verbose"))

        case "check":
            # Check that current DB matches head revision
            # Exits non-zero if migrations are pending — used in CI
            sys.exit(run_alembic("check"))

        case "sql":
            # Print SQL without applying — for DBA review
            target = extra[0] if extra else "head"
            sys.exit(run_alembic("upgrade", target, "--sql"))

        case "stamp":
            # Mark current DB as being at a specific revision (no migration run)
            # Useful when manually applying SQL in an emergency
            target = extra[0] if extra else "head"
            sys.exit(run_alembic("stamp", target))

        case _:
            print(f"Unknown command: {command}")
            print(__doc__)
            sys.exit(1)


if __name__ == "__main__":
    main()

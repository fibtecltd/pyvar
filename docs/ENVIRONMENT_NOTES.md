# ENVIRONMENT NOTES — read before running anything

**Status: the container's Python was broken on arrival; fixed durably on 2026-06-11.**

## What was wrong
- The prompt claimed "pytest, numpy, numba, scipy all work as-is." They did NOT.
- The interpreter that owned the installed packages (`/usr/local/bin/python3.11`) was
  missing. Packages live in `/usr/local/lib/python3.11/site-packages`.
- The surviving interpreter `/usr/bin/python3.11` searches `dist-packages`, not
  `site-packages`, so `import numpy/numba/scipy/pytest` failed with `ModuleNotFoundError`.
- The `pytest` console script (`/usr/local/bin/pytest`) has a dead shebang
  (`#!/usr/local/bin/python3.11`) and cannot execute. It cannot be repaired without root.

## The fix (persists across sessions — lives on disk under /home/claude)
1. User-site `.pth` bridge — auto-loaded by every `python3.11` invocation
   (`ENABLE_USER_SITE=True`):
   `/home/claude/.local/lib/python3.11/site-packages/_pyvar_bridge.pth`
   → contains the single line `/usr/local/lib/python3.11/site-packages`
2. `~/.local/bin/pytest` shim execs `/usr/bin/python3.11 -m pytest "$@"`
3. `~/.bashrc` exports `PATH` and `PYTHONPATH` (belt-and-suspenders for login shells)

## How to run tests — IMPORTANT
- The Claude Code Bash tool uses a NON-login, NON-interactive shell that does NOT
  source `~/.bashrc`. So bare `pytest` resolves to the broken root launcher.
- **ALWAYS invoke tests as `python -m pytest ...` (or `python3.11 -m pytest ...`).**
  This works with zero manual env because the `.pth` bridge is loaded automatically.

## Verified baseline
Market Risk suite (P1) is green: 117 tests pass via `python -m pytest`.

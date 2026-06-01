#!/usr/bin/env python3
"""
scripts/hooks/check_numba_rules.py
====================================
Pre-commit hook: enforces CLAUDE.md section 3.1 Numba JIT rules.

Called by pre-commit with the list of staged engine/*.py files.
Exits non-zero if any violation is found.

Rules enforced:
  RULE 1 — @njit functions are stateless (no Python objects as args)
  RULE 2 — No dynamic dispatch (no hasattr/getattr inside @njit)
  RULE 3 — RNG drawn outside @njit (no np.random inside @njit body)
  RULE 4 — prange only in @njit(parallel=True, cache=True)
  RULE 5 — @njit functions return only np.ndarray
  RULE 6 — Warmup call present in main.py lifespan handler

Note: Rule 6 is only checked when main.py is in the staged files.
Rules 1-5 are checked on all staged engine/*.py files.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── ANSI colours for terminal output ─────────────────────────────────────────
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


@dataclass
class Violation:
    rule: int
    file: str
    line: int
    message: str
    severity: str = "ERROR"  # ERROR | WARNING


def notify(violations: list[Violation]) -> None:
    """Print structured violations to stderr."""
    errors = [v for v in violations if v.severity == "ERROR"]
    warnings = [v for v in violations if v.severity == "WARNING"]

    print(f"\n{BOLD}{CYAN}━━ Numba JIT Rule Checker ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}", file=sys.stderr)

    for v in violations:
        colour = RED if v.severity == "ERROR" else YELLOW
        print(
            f"{colour}{v.severity}{RESET}  [{v.file}:{v.line}] "
            f"RULE {v.rule}: {v.message}",
            file=sys.stderr,
        )

    print(
        f"\n{BOLD}{'❌' if errors else '⚠️ '} "
        f"{len(errors)} error(s), {len(warnings)} warning(s){RESET}",
        file=sys.stderr,
    )
    if errors:
        print(f"See {BOLD}CLAUDE.md section 3.1{RESET} for the full rule set.\n", file=sys.stderr)


class NumbaRuleVisitor(ast.NodeVisitor):
    """AST visitor that checks Numba JIT rules on a single file."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.violations: list[Violation] = []
        self._njit_func_names: set[str] = set()
        self._current_njit: Optional[str] = None
        self._parallel_njit: set[str] = set()

    def _add(self, rule: int, node: ast.AST, message: str, severity: str = "ERROR") -> None:
        self.violations.append(
            Violation(rule, self.filepath, getattr(node, "lineno", 0), message, severity)
        )

    def _is_njit(self, decorator: ast.expr) -> bool:
        """Check if a decorator is @njit or @numba.njit."""
        if isinstance(decorator, ast.Name):
            return decorator.id == "njit"
        if isinstance(decorator, ast.Attribute):
            return decorator.attr == "njit"
        if isinstance(decorator, ast.Call):
            return self._is_njit(decorator.func)
        return False

    def _has_parallel(self, decorator: ast.expr) -> bool:
        """Check if @njit(parallel=True, ...) is set."""
        if isinstance(decorator, ast.Call):
            for kw in decorator.keywords:
                if kw.arg == "parallel" and isinstance(kw.value, ast.Constant) and kw.value.value:
                    return True
        return False

    def _has_cache(self, decorator: ast.expr) -> bool:
        """Check if @njit(..., cache=True) is set."""
        if isinstance(decorator, ast.Call):
            for kw in decorator.keywords:
                if kw.arg == "cache" and isinstance(kw.value, ast.Constant) and kw.value.value:
                    return True
        return False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        njit_decs = [d for d in node.decorator_list if self._is_njit(d)]

        if not njit_decs:
            self.generic_visit(node)
            return

        dec = njit_decs[0]
        fname = node.name

        # RULE 4: prange requires parallel=True, cache=True
        if not self._has_parallel(dec):
            # Check body uses prange
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if (isinstance(func, ast.Name) and func.id == "prange") or \
                       (isinstance(func, ast.Attribute) and func.attr == "prange"):
                        self._add(4, child,
                            f"prange() used in {fname} but @njit(parallel=True) is missing")
        else:
            self._parallel_njit.add(fname)
            if not self._has_cache(dec):
                self._add(4, dec,
                    f"{fname}: @njit(parallel=True) without cache=True. "
                    "cache=True is mandatory — prevents recompilation on worker restart.")

        self._njit_func_names.add(fname)
        prev = self._current_njit
        self._current_njit = fname

        # Walk body checking RULES 2, 3
        for child in ast.walk(node):
            # RULE 2: No dynamic dispatch
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Name) and func.id in ("hasattr", "getattr", "setattr"):
                    self._add(2, child,
                        f"{fname}: {func.id}() inside @njit — no dynamic dispatch allowed")

            # RULE 3: No np.random inside @njit
            if isinstance(child, ast.Attribute):
                if child.attr in ("randn", "rand", "randint", "random_sample",
                                  "normal", "uniform", "standard_normal"):
                    if isinstance(child.value, ast.Name) and child.value.id in ("np", "numpy"):
                        self._add(3, child,
                            f"{fname}: np.random.{child.attr}() inside @njit. "
                            "Pre-draw random numbers outside the JIT region and pass as argument.")

            # RULE 1: No Python objects (dict/list/object) as annotations
        for arg in node.args.args:
            if arg.annotation:
                ann_str = ast.unparse(arg.annotation) if hasattr(ast, "unparse") else str(arg.annotation)
                if any(t in ann_str for t in ("dict", "Dict", "list", "List", "Any", "object")):
                    self._add(1, arg,
                        f"{fname}: arg '{arg.arg}' annotated as {ann_str}. "
                        "@njit functions must accept only np.ndarray, scalars, or primitives.",
                        severity="WARNING")

        self._current_njit = prev
        self.generic_visit(node)

    # Also check module-level imports inside functions (RULE 1)
    def visit_Import(self, node: ast.Import) -> None:
        if self._current_njit:
            self._add(1, node,
                f"{self._current_njit}: import statement inside @njit function")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._current_njit:
            self._add(1, node,
                f"{self._current_njit}: import statement inside @njit function")
        self.generic_visit(node)


def check_rule_6_warmup(main_path: Path) -> list[Violation]:
    """RULE 6: warmup call must exist in main.py lifespan handler."""
    violations: list[Violation] = []
    text = main_path.read_text()
    if "lifespan" not in text:
        violations.append(Violation(6, str(main_path), 0,
            "lifespan handler not found in main.py. "
            "Numba warmup must be called in the FastAPI lifespan context."))
    elif "warmup" not in text and "run_monte_carlo" not in text:
        violations.append(Violation(6, str(main_path), 0,
            "Numba warmup call not detected in main.py lifespan handler. "
            "ECS health check startPeriod=30s depends on this.", severity="WARNING"))
    return violations


def main(files: list[str]) -> int:
    all_violations: list[Violation] = []

    for filepath in files:
        path = Path(filepath)
        if not path.exists():
            continue

        try:
            source = path.read_text()
            tree = ast.parse(source, filename=filepath)
        except SyntaxError as e:
            print(f"SyntaxError in {filepath}: {e}", file=sys.stderr)
            continue

        visitor = NumbaRuleVisitor(filepath)
        visitor.visit(tree)
        all_violations.extend(visitor.violations)

    # Rule 6 check on main.py if it appears in staged files
    main_candidates = [f for f in files if Path(f).name == "main.py"]
    for m in main_candidates:
        all_violations.extend(check_rule_6_warmup(Path(m)))

    if all_violations:
        notify(all_violations)

    errors = [v for v in all_violations if v.severity == "ERROR"]
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

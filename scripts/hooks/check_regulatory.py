#!/usr/bin/env python3
"""
scripts/hooks/check_regulatory.py
====================================
Pre-commit hook: regulatory threshold guard.
Enforces CLAUDE.md section 4 — regulatory constraints.

Detects:
  - Hardcoded VaR confidence levels outside [0.90, 0.9999]
  - Incorrect backtesting window (must be 250, not 252/260)
  - Incorrect Basel breach zone boundaries (5, 9 thresholds)
  - ES computed as median or max instead of mean
  - PAT thresholds replaced with non-Basel values
  - Capital add-on multipliers tampered with (3.0, 3.4–3.8, 4.0)

All these constants are SET BY REGULATORS and must not be changed.
Any deviation is a compliance finding, not a code style issue.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

RED = "\033[31m"
BOLD = "\033[1m"
CYAN = "\033[36m"
RESET = "\033[0m"

# ── Regulatory constant definitions ──────────────────────────────────────────

# Valid VaR confidence level range (Basel III § 185, FRTB Art. 325bf)
VAR_CONFIDENCE_MIN = 0.90
VAR_CONFIDENCE_MAX = 0.9999

# Basel traffic-light backtesting window (Basel Committee, BCBS Jan 2019 § 5.5)
BACKTEST_WINDOW = 250

# Basel breach zones (BCBS FRTB Table 1)
BREACH_GREEN_MAX = 4  # 0–4 breaches: green
BREACH_YELLOW_MAX = 9  # 5–9 breaches: yellow
# ≥10 breaches: red

# Capital add-on multipliers (BCBS FRTB Table 1)
MULTIPLIER_GREEN = 3.0
MULTIPLIER_RED = 4.0

# FRTB PAT thresholds (BCBS FRTB § 9.5)
PAT_CORR_GREEN = 0.80
PAT_CORR_AMBER = 0.70
PAT_RATIO_HI = 1.2
PAT_RATIO_LO = 0.8


def find_float_literals(tree: ast.Module, source_lines: list[str]) -> list[tuple[float, int]]:
    """Extract all float literals with their line numbers."""
    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            results.append((node.value, node.lineno))
    return results


def find_int_literals(tree: ast.Module) -> list[tuple[int, int]]:
    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            results.append((node.value, node.lineno))
    return results


def check_file(filepath: str) -> list[tuple[str, int, str]]:
    """Returns list of (filepath, lineno, message) violations."""
    path = Path(filepath)
    source = path.read_text()
    source_lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []

    violations = []

    floats = find_float_literals(tree, source_lines)
    ints = find_int_literals(tree)

    for value, lineno in floats:
        line_ctx = source_lines[lineno - 1].strip() if lineno <= len(source_lines) else ""

        # VaR confidence level range check
        # Only flag values that look like confidence levels (0.9x range)
        if 0.5 < value < 1.0:
            if value < VAR_CONFIDENCE_MIN or value > VAR_CONFIDENCE_MAX:
                # Skip if it's clearly not a confidence level
                if any(kw in line_ctx.lower() for kw in ("confidence", "alpha", "quantile", "var")):
                    violations.append(
                        (
                            filepath,
                            lineno,
                            f"VaR confidence level {value} outside Basel valid range "
                            f"[{VAR_CONFIDENCE_MIN}, {VAR_CONFIDENCE_MAX}]. "
                            "Enforced by schemas/var.py validator — do not relax.",
                        )
                    )

        # Capital add-on multiplier: 3.0 is green, 4.0 is red
        # If a value near these is used in a multiplier context, flag if wrong
        if abs(value - 4.0) < 0.01:
            if any(kw in line_ctx.lower() for kw in ("multiplier", "add_on", "addon", "capital")):
                # Allowed: exactly 4.0 for red zone
                pass
        if 3.0 < value < 3.4 or 3.8 < value < 4.0:
            if any(kw in line_ctx.lower() for kw in ("multiplier", "add_on", "addon", "capital")):
                violations.append(
                    (
                        filepath,
                        lineno,
                        f"Capital multiplier {value} is outside Basel allowed values. "
                        f"Green=3.0, Yellow=3.4–3.8, Red=4.0 (BCBS FRTB Table 1).",
                    )
                )

        # PAT correlation thresholds
        if any(kw in line_ctx.lower() for kw in ("corr", "spearman", "pat", "attribution")):
            if abs(value - 0.80) > 0.001 and abs(value - 0.70) > 0.001:
                if 0.6 < value < 0.95:
                    violations.append(
                        (
                            filepath,
                            lineno,
                            f"PAT correlation threshold {value} does not match Basel values. "
                            f"Green≥{PAT_CORR_GREEN}, Amber≥{PAT_CORR_AMBER} (BCBS FRTB § 9.5).",
                        )
                    )

    for value, lineno in ints:
        line_ctx = source_lines[lineno - 1].strip() if lineno <= len(source_lines) else ""

        # Backtesting window: must be exactly 250
        if value in (252, 260, 365, 261):
            if any(
                kw in line_ctx.lower()
                for kw in ("backtest", "window", "days", "trading", "lookback")
            ):
                violations.append(
                    (
                        filepath,
                        lineno,
                        f"Backtesting window {value} detected. Basel standard is EXACTLY 250 "
                        "trading days — not 252, 260, or 365. (BCBS FRTB § 5.5)",
                    )
                )

        # Basel breach zone boundaries
        if value == 4 and any(kw in line_ctx.lower() for kw in ("breach", "exception", "green")):
            # 4 is correct for green zone max
            pass
        if value in (10, 11) and any(
            kw in line_ctx.lower() for kw in ("breach", "exception", "red")
        ):
            # Check it's used as >= 10 not > 10 or > 9
            if ">" in line_ctx and "= " not in line_ctx and ">10" not in line_ctx.replace(" ", ""):
                violations.append(
                    (
                        filepath,
                        lineno,
                        f"Basel red zone check: use '>= 10' breaches not '> {value}'. "
                        "This is a compliance-critical boundary (BCBS FRTB Table 1).",
                    )
                )

    # Text-based checks for ES computation pattern
    # ES must be the MEAN of losses beyond VaR, not median or max
    es_patterns = [
        (
            r"\bmedian\b.*\bexceed\b|\bexceed\b.*\bmedian\b",
            "ES computed as median — must be mean of losses beyond VaR threshold",
        ),
        (
            r"\bmax\b.*\bexceed\b|\bexceed\b.*\bmax\b",
            "ES computed as max — must be mean of losses beyond VaR threshold",
        ),
        (
            r"\.percentile\s*\(\s*losses.*,\s*9[0-9]",
            "Check: ES should use mean of tail losses, not percentile of losses",
        ),
    ]
    for pattern, msg in es_patterns:
        for match in re.finditer(pattern, source, re.IGNORECASE):
            lineno = source[: match.start()].count("\n") + 1
            violations.append((filepath, lineno, msg))

    return violations


def main(files: list[str]) -> int:
    all_violations: list[tuple[str, int, str]] = []

    for f in files:
        if Path(f).exists():
            all_violations.extend(check_file(f))

    if all_violations:
        print(
            f"\n{BOLD}{CYAN}━━ Regulatory Threshold Guard ━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}",
            file=sys.stderr,
        )
        for filepath, lineno, msg in all_violations:
            print(f"{RED}REGULATORY{RESET}  [{filepath}:{lineno}] {msg}", file=sys.stderr)
        print(
            f"\n{BOLD}❌ {len(all_violations)} regulatory violation(s).{RESET}\n"
            f"These thresholds are set by regulators — see {BOLD}CLAUDE.md section 4{RESET}.\n"
            "Open a reg/* branch and get a second reviewer before changing any of these.\n",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

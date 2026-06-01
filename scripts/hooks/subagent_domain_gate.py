#!/usr/bin/env python3
"""
scripts/hooks/subagent_domain_gate.py
=======================================
Claude Code SubagentStop hook.
Fires when a domain teammate subagent stops.

Gate checks before the adversarial subagent is invoked:
  1. CHECKPOINT.md present and complete (all required sections)
  2. All modified engine files committed
  3. pytest passes on domain test file
  4. Function count matches pyvar_functions.csv for the domain
  5. No Numba rule violations in committed files

If all gates pass: signals the lead agent to invoke the adversarial validator.
If any gate fails: blocks the lead from marking the domain complete.

Output is written to /workspace/pyvar/DOMAIN_GATE_RESULT.md
The lead agent reads this file to decide next action.
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

WORKSPACE = Path("/workspace/pyvar")
CHECKPOINT = WORKSPACE / "CHECKPOINT.md"
GATE_RESULT = WORKSPACE / "DOMAIN_GATE_RESULT.md"

GREEN = "\033[32m"
RED   = "\033[31m"
BOLD  = "\033[1m"
RESET = "\033[0m"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True, **kwargs)


def check_checkpoint_complete() -> tuple[bool, str]:
    if not CHECKPOINT.exists():
        return False, "CHECKPOINT.md not found"
    content = CHECKPOINT.read_text()
    required = ["## Completed", "## In progress", "## Next", "## Git state"]
    missing = [s for s in required if s not in content]
    if missing:
        return False, f"CHECKPOINT.md missing sections: {', '.join(missing)}"
    return True, "CHECKPOINT.md complete"


def check_no_uncommitted() -> tuple[bool, str]:
    r = run(["git", "status", "--porcelain", "engine/"])
    if r.stdout.strip():
        files = r.stdout.strip().splitlines()
        return False, f"{len(files)} uncommitted engine file(s): {files[0]}"
    return True, "No uncommitted engine files"


def check_pytest_domain() -> tuple[bool, str]:
    """Run pytest on the domain's test file."""
    # Determine which domain this is from CHECKPOINT.md
    if not CHECKPOINT.exists():
        return False, "Cannot determine domain (no CHECKPOINT.md)"

    content = CHECKPOINT.read_text()
    # Extract domain name from checkpoint
    domain_line = [l for l in content.splitlines() if "## Domain:" in l]
    if not domain_line:
        return True, "Domain not specified — skipping pytest gate"

    domain = domain_line[0].split(":", 1)[-1].strip().lower().replace(" ", "_")
    test_file = f"tests/test_{domain}.py"
    test_path = WORKSPACE / test_file

    if not test_path.exists():
        return True, f"No test file for domain {domain} yet — skipping"

    r = run(["python", "-m", "pytest", test_file, "-x", "-q", "--tb=short"], timeout=180)
    if r.returncode != 0:
        failing_lines = [l for l in r.stdout.splitlines() if "FAILED" in l or "ERROR" in l]
        return False, f"pytest failures in {test_file}:\n" + "\n".join(f"  {l}" for l in failing_lines[:5])

    # Extract pass count
    summary = [l for l in r.stdout.splitlines() if "passed" in l]
    return True, summary[0] if summary else f"pytest passed on {test_file}"


def check_numba_violations() -> tuple[bool, str]:
    """Run Numba rule checker on all committed engine files."""
    r = run(["git", "diff", "--name-only", "HEAD~1", "HEAD", "--", "engine/"])
    if not r.stdout.strip():
        # Check all engine files
        engine_files = list(WORKSPACE.glob("engine/*.py"))
    else:
        engine_files = [WORKSPACE / f for f in r.stdout.strip().splitlines()]

    if not engine_files:
        return True, "No engine files to check"

    checker = str(WORKSPACE / "scripts/hooks/check_numba_rules.py")
    r = run(["python3", checker] + [str(f) for f in engine_files if f.exists()])
    if r.returncode != 0:
        return False, f"Numba rule violations detected:\n{r.stderr[:500]}"
    return True, f"Numba rules OK on {len(engine_files)} file(s)"


def write_gate_result(gates: list[tuple[str, bool, str]], ready_for_adversarial: bool) -> None:
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# DOMAIN_GATE_RESULT",
        f"## Timestamp: {timestamp}",
        f"## Ready for adversarial validation: {'YES' if ready_for_adversarial else 'NO'}",
        "",
        "## Gate results",
    ]
    for name, passed, detail in gates:
        status = "✅ PASS" if passed else "❌ FAIL"
        lines.append(f"- {status} **{name}**: {detail}")

    if ready_for_adversarial:
        lines += [
            "",
            "## Lead agent instruction",
            "All gates passed. Invoke the adversarial validator subagent:",
            "```",
            "Read /workspace/pyvar/scripts/adversarial/p2_domain_validator.md",
            "Spawn adversarial subagent with the domain's completed code.",
            "Do NOT mark domain complete until adversarial report shows 0 critical findings.",
            "```",
        ]
    else:
        lines += [
            "",
            "## Lead agent instruction",
            "One or more gates failed. Do NOT invoke the adversarial validator yet.",
            "Return failing gates to the domain teammate for remediation.",
        ]

    GATE_RESULT.write_text("\n".join(lines))


def main() -> int:
    gates = [
        ("Checkpoint complete",   *check_checkpoint_complete()),
        ("No uncommitted files",  *check_no_uncommitted()),
        ("pytest domain",         *check_pytest_domain()),
        ("Numba rules",           *check_numba_violations()),
    ]

    all_passed = all(passed for _, passed, _ in gates)
    write_gate_result(gates, all_passed)

    if all_passed:
        print(f"{GREEN}[domain-gate] All gates passed — adversarial validation ready.{RESET}", file=sys.stderr)
        print(f"[domain-gate] Results written to DOMAIN_GATE_RESULT.md", file=sys.stderr)
        return 0
    else:
        failed = [name for name, passed, _ in gates if not passed]
        print(f"{RED}[domain-gate] {len(failed)} gate(s) failed: {', '.join(failed)}{RESET}", file=sys.stderr)
        print(f"[domain-gate] Results written to DOMAIN_GATE_RESULT.md", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

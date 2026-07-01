#!/usr/bin/env python3
"""
scripts/claude/write-settings-local.py
========================================
Generates /workspace/pyvar/.claude/settings.local.json per phase.

Called by pyvar-phase.sh before starting a Claude Code session.
This is how pyvar hooks are activated without touching settings.json
(which lives in the claude-docker repo and must stay clean).

Claude Code loads settings in order:
  ~/.claude/settings.json       (claude-docker, infrastructure)
  <project>/.claude/settings.local.json  (pyvar, this file — overrides/extends)

Usage:
  python3 scripts/claude/write-settings-local.py <phase>
  python3 scripts/claude/write-settings-local.py p2
  python3 scripts/claude/write-settings-local.py p2 --mode agent
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent
OUTPUT = WORKSPACE / ".claude" / "settings.local.json"
HOOKS_DIR = str(WORKSPACE / "scripts" / "hooks")


def phase_hooks(phase: str, mode: str = "seq") -> dict:
    """
    Returns the hooks block appropriate for the given phase.
    Only phases that need hooks get them — simpler phases stay clean.
    """

    # ── Hooks shared across all pyvar phases ─────────────────────────────────
    pre_tool_use_shared = [
        {
            "matcher": "Write|Edit",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "bash -c 'BRANCH=$(git -C /workspace/pyvar branch --show-current 2>/dev/null); "
                        'if [ "$BRANCH" = "main" ]; then '
                        'echo "[pyvar-hook] ERROR: Direct write to main blocked. Use feat/* or fix/*."; '
                        "exit 1; fi'"
                    ),
                }
            ],
        }
    ]

    post_tool_use_shared = []
    stop_hooks = []
    subagent_stop_hooks = []

    # ── P2 / P5: engine write hooks ───────────────────────────────────────────
    if phase in ("p2", "p5"):
        post_tool_use_shared += [
            {
                "matcher": "Write|Edit",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            f'bash -c \'FILE="${{CLAUDE_TOOL_INPUT_FILE_PATH:-}}"; '
                            f'if [[ "$FILE" == */engine/*.py ]] && [ -f "$FILE" ]; then '
                            f'python3 {HOOKS_DIR}/check_numba_rules.py "$FILE"; fi\''
                        ),
                    }
                ],
            },
            {
                "matcher": "Write|Edit",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            f'bash -c \'FILE="${{CLAUDE_TOOL_INPUT_FILE_PATH:-}}"; '
                            f'if [[ "$FILE" =~ /engine/|/api/|/tasks/|/schemas/ ]] && [ -f "$FILE" ]; then '
                            f'python3 {HOOKS_DIR}/check_regulatory.py "$FILE"; fi\''
                        ),
                    }
                ],
            },
            {
                "matcher": "Write|Edit",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            'bash -c \'FILE="${CLAUDE_TOOL_INPUT_FILE_PATH:-}"; '
                            'if [[ "$FILE" == */engine/*.py ]] && [ -f "$FILE" ]; then '
                            'MODULE=$(basename "$FILE" .py); TEST="/workspace/pyvar/tests/test_${MODULE}.py"; '
                            'if [ -f "$TEST" ]; then '
                            'echo "[pyvar-hook] pytest $TEST"; '
                            'cd /workspace/pyvar && python -m pytest "$TEST" -x -q 2>&1 | tail -4; fi; fi\''
                        ),
                    }
                ],
            },
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            f'bash -c \'if echo "${{CLAUDE_TOOL_INPUT_COMMAND:-}}" | grep -q "git commit"; then '
                            f"python3 {HOOKS_DIR}/post_commit_checkpoint.py; fi'"
                        ),
                    }
                ],
            },
        ]

        stop_hooks = [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"python3 {HOOKS_DIR}/stop_checkpoint_enforcer.py",
                    }
                ]
            }
        ]

        # Agent Teams mode: add SubagentStop domain gate
        if mode == "agent":
            subagent_stop_hooks = [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {HOOKS_DIR}/subagent_domain_gate.py",
                        }
                    ]
                }
            ]

    # ── P3: API route validation ───────────────────────────────────────────────
    elif phase == "p3":
        post_tool_use_shared += [
            {
                "matcher": "Write|Edit",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            f'bash -c \'FILE="${{CLAUDE_TOOL_INPUT_FILE_PATH:-}}"; '
                            f'if [[ "$FILE" =~ /api/|/schemas/ ]] && [ -f "$FILE" ]; then '
                            f'python3 {HOOKS_DIR}/check_regulatory.py "$FILE"; fi\''
                        ),
                    }
                ],
            },
            {
                "matcher": "Write|Edit",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            'bash -c \'FILE="${CLAUDE_TOOL_INPUT_FILE_PATH:-}"; '
                            'if [[ "$FILE" == */api/routes/*.py ]] && [ -f "$FILE" ]; then '
                            "cd /workspace/pyvar && python -c "
                            '"from main import create_app; app=create_app(); '
                            'print(f\\"[pyvar-hook] API OK: {len(app.routes)} routes\\")" 2>&1 | tail -2; fi\''
                        ),
                    }
                ],
            },
        ]

    # ── P4: CDK stack validation ───────────────────────────────────────────────
    elif phase == "p4":
        post_tool_use_shared += [
            {
                "matcher": "Write|Edit",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            'bash -c \'FILE="${CLAUDE_TOOL_INPUT_FILE_PATH:-}"; '
                            'if [[ "$FILE" == */pyvar-cdk/stacks/*.py ]]; then '
                            'echo "[pyvar-hook] CDK stack changed — run: '
                            "cd /workspace/pyvar/pyvar-cdk && cdk synth --quiet\"; fi'"
                        ),
                    }
                ],
            }
        ]

    # ── Assemble hooks block ──────────────────────────────────────────────────
    hooks: dict = {}
    if pre_tool_use_shared:
        hooks["PreToolUse"] = pre_tool_use_shared
    if post_tool_use_shared:
        hooks["PostToolUse"] = post_tool_use_shared
    if stop_hooks:
        hooks["Stop"] = stop_hooks
    if subagent_stop_hooks:
        hooks["SubagentStop"] = subagent_stop_hooks

    return hooks


def phase_env(phase: str, mode: str = "seq") -> dict:
    """
    Environment overrides for specific phases.
    These extend/override the env block in ~/.claude/settings.json.
    """
    env: dict = {}

    # Agent Teams env var — add for P2/P5 on M4 in agent mode
    if phase in ("p2", "p5") and mode == "agent":
        env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
    if phase == "p5":
        env["NUMBA_DISABLE_JIT"] = "1"

    return env


def write_settings_local(phase: str, mode: str = "seq") -> None:
    """Write .claude/settings.local.json for the given phase."""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}

    hooks = phase_hooks(phase, mode)
    if hooks:
        data["hooks"] = hooks

    env = phase_env(phase, mode)
    if env:
        data["env"] = env

    OUTPUT.write_text(json.dumps(data, indent=2))

    hook_count = sum(len(v) for v in hooks.values())
    print(f"[write-settings-local] phase={phase} mode={mode} → {hook_count} hook(s) written")
    print(f"[write-settings-local] output: {OUTPUT}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 write-settings-local.py <phase> [--mode agent|seq]")
        sys.exit(1)

    phase = sys.argv[1].lower()
    mode = "agent" if "--mode agent" in " ".join(sys.argv) else "seq"
    write_settings_local(phase, mode)

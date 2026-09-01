"""scripts/generate_plugins.py — Claude Code plugin generator for .claude/skills/*

Reasoning:
- .claude-plugin/marketplace.json already declares 13 individual single-skill
  plugins (one per .claude/skills/* entry, matching each skill's own
  frontmatter `name`) at plugins/<path>/ -- this script is what actually
  builds those directories from the skills that are the real source of
  truth, rather than hand-maintaining a second copy that can drift.
- Same "generate, commit, CI diffs against a fresh regenerate" pattern as
  pyvar-client/codegen/generate.py (see .github/workflows/plugins-ci.yml's
  drift-check job) -- not a deploy-time build step. A git-based Claude Code
  plugin install reads directly from the committed repo tree, so the
  generated files have to actually be committed, not produced on the fly
  at deploy time the way portal/'s demo-result.json is.
- Single-skill shorthand (Claude Code plugin spec): SKILL.md sits at the
  plugin root, no nested skills/ subdirectory -- each of these 13 plugins
  wraps exactly one skill.

Usage:
  python3 scripts/generate_plugins.py
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
PLUGINS_DIR = REPO_ROOT / "plugins"
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"

# skill directory name -> plugin path (relative to plugins/), matching
# .claude-plugin/marketplace.json's already-committed "path" values exactly.
SKILL_TO_PLUGIN_PATH = {
    "alm": "alm",
    "credit-risk": "credit-risk",
    "derivatives": "derivatives",
    "liquidity-risk": "liquidity-risk",
    "market-risk": "market-risk",
    "operational-risk": "operational-risk",
    "portfolio-analytics": "portfolio-analytics",
    "regulatory": "regulatory",
    "arch-api-gateway": "arch/api-gateway",
    "arch-data-ingestion": "arch/data-ingestion",
    "arch-compute": "arch/compute",
    "arch-storage": "arch/storage",
    "arch-observability": "arch/observability",
}

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)
VERSION_RE = re.compile(r'^version:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)


def parse_frontmatter(skill_md_text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(skill_md_text)
    if not match:
        raise ValueError("SKILL.md missing YAML frontmatter block")
    fm_text = match.group(1)
    name_match = NAME_RE.search(fm_text)
    version_match = VERSION_RE.search(fm_text)
    if not name_match or not version_match:
        raise ValueError("SKILL.md frontmatter missing name/version")
    return {"name": name_match.group(1), "version": version_match.group(1)}


def main() -> None:
    marketplace = json.loads(MARKETPLACE_PATH.read_text())
    descriptions_by_plugin_name = {p["name"]: p["description"] for p in marketplace["plugins"]}

    for skill_dir_name, plugin_path in SKILL_TO_PLUGIN_PATH.items():
        skill_md_path = SKILLS_DIR / skill_dir_name / "SKILL.md"
        skill_md_text = skill_md_path.read_text()
        fm = parse_frontmatter(skill_md_text)

        plugin_name = fm["name"]  # e.g. "pyvar-market-risk" -- must match marketplace.json's "name"
        description = descriptions_by_plugin_name.get(plugin_name)
        if description is None:
            raise SystemExit(
                f"plugin name {plugin_name!r} (from {skill_md_path}) has no matching "
                f"entry in .claude-plugin/marketplace.json -- add it there first"
            )

        plugin_dir = PLUGINS_DIR / plugin_path
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / ".claude-plugin").mkdir(parents=True, exist_ok=True)

        shutil.copyfile(skill_md_path, plugin_dir / "SKILL.md")

        plugin_json = {
            "name": plugin_name,
            "version": fm["version"],
            "description": description,
            "author": {"name": "Fibtec Limited", "url": "https://pyvar.com"},
            "homepage": "https://pyvar.com",
            "repository": "https://github.com/fibtecltd/pyvar",
            "license": "Apache-2.0",
        }
        (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps(plugin_json, indent=2) + "\n"
        )
        print(f"wrote plugins/{plugin_path}/  (plugin: {plugin_name}, version {fm['version']})")


if __name__ == "__main__":
    main()

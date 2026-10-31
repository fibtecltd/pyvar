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
- Anthropic's directory reads an icon and four https links from plugin.json
  for each listing (the plugin manifest reference, "Directory listing
  fields"), and refuses a listing without a square PNG or JPEG of 512 to
  2048 px under 2 MB. Every plugin gets the same pyvar mark, copied from
  docs/brand/ as icon.png, and the same four links, so a plugin cannot be
  added without them. tests/test_plugin_directory_policy.py checks the result.
- Each plugin also gets its own README.md. The directory reads a plugin's
  README for the listing and, when the plugin folder has none, takes the
  repository's root README instead -- a developer README whose
  "http://localhost:8000/docs" comment was read as the plugin's documentation
  link and refused (LISTING_URL_SCHEME). A README of its own, with https links
  only, keeps the listing independent of the root README.

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
ICON_SOURCE = REPO_ROOT / "docs" / "brand" / "favicon-light-512.png"  # 1024 x 1024 PNG

# The directory-listing fields (plugin.json), the same for every plugin. Claude Code ignores them
# at load time; Anthropic's directory shows them. Each link must be an https:// URL.
LISTING_FIELDS = {
    "icon": "./icon.png",
    "documentationUrl": "https://www.pyvar.com/plugins.html",
    "supportUrl": "https://github.com/fibtecltd/pyvar/issues",
    "privacyPolicyUrl": "https://www.pyvar.com/privacy.html",
    "termsOfServiceUrl": "https://www.pyvar.com/terms.html",
}

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


README_TEMPLATE = """\
# {name}

{description}.

{what_it_is}

## Install

```
/plugin marketplace add fibtecltd/pyvar
/plugin install {name}@pyvar-marketplace
```
{key_section}
## Links

- Documentation: {documentation}
- Source: {repository}
- Support: {support}
- Privacy policy: {privacy}
- Terms of service: {terms}

Licence: Apache-2.0. pyvar is not independently validated for regulatory use; its output is
not a substitute for your institution's own model validation.
"""

DOMAIN_WHAT = (
    "A Claude skill: it teaches Claude which of pyvar's functions fits a question, what to send, "
    "and how to read the answer. Every number comes from the live API at https://www.pyvar.com; "
    "the skill computes nothing itself."
)
ARCH_WHAT = (
    "A Claude skill with architecture notes for contributors to the pyvar codebase "
    "(https://github.com/fibtecltd/pyvar). It is not needed to call the pyvar API."
)
KEY_SECTION = """
## The API key

The skill needs your own pyvar API key to call the API, and never reads one from your
machine. Get a free key at https://www.pyvar.com#get-api-key (sign in with Google or an emailed
link; no password, no card), then install the `pyvar-mcp` plugin: Claude Code asks for the key
when it is enabled and keeps it in the system's secure credential store.

```
/plugin install pyvar-mcp@pyvar-marketplace
```
"""


def readme_for(plugin_name: str, description: str, is_arch: bool) -> str:
    return README_TEMPLATE.format(
        name=plugin_name,
        description=description.rstrip("."),
        what_it_is=ARCH_WHAT if is_arch else DOMAIN_WHAT,
        key_section="" if is_arch else KEY_SECTION,
        documentation=LISTING_FIELDS["documentationUrl"],
        repository="https://github.com/fibtecltd/pyvar",
        support=LISTING_FIELDS["supportUrl"],
        privacy=LISTING_FIELDS["privacyPolicyUrl"],
        terms=LISTING_FIELDS["termsOfServiceUrl"],
    )


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
        shutil.copyfile(ICON_SOURCE, plugin_dir / "icon.png")
        (plugin_dir / "README.md").write_text(
            readme_for(plugin_name, description, skill_dir_name.startswith("arch-"))
        )

        # references/ (per-function parameter tables for the domain skills) ships with the
        # plugin; copy it fresh so a file removed from the source can't linger in plugins/.
        references_src = skill_md_path.parent / "references"
        references_dst = plugin_dir / "references"
        if references_dst.exists():
            shutil.rmtree(references_dst)
        if references_src.is_dir():
            shutil.copytree(references_src, references_dst)

        plugin_json = {
            "name": plugin_name,
            "version": fm["version"],
            "description": description,
            "author": {"name": "Fibtec Limited", "url": "https://pyvar.com"},
            "homepage": "https://pyvar.com",
            "repository": "https://github.com/fibtecltd/pyvar",
            "license": "Apache-2.0",
            **LISTING_FIELDS,
        }
        (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps(plugin_json, indent=2) + "\n"
        )
        print(f"wrote plugins/{plugin_path}/  (plugin: {plugin_name}, version {fm['version']})")


if __name__ == "__main__":
    main()

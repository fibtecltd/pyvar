"""The published Claude skills must stay true to the API they describe.

Reasoning:
- The eight domain skills are rendered by scripts/sync_skills.py from the function
  catalog (portal/functions.json) and the live OpenAPI schema. If a function is
  added, renamed or re-parameterised, the skill is stale and Claude would call an
  endpoint that no longer exists (26 of market-risk's 68 names had already drifted
  that way). These tests fail until `python3 scripts/sync_skills.py` is re-run.
- plugins/* is a generated copy of .claude/skills/*; the plugins CI job checks the
  same thing, but a plain pytest run should catch it too.
- Every worked example in a skill is executed in tests/test_skill_examples.py.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

sync_skills = importlib.import_module("sync_skills")

DOMAIN_SKILLS = sync_skills.DOMAIN_SKILLS
ARCH_SKILLS = (
    "arch-api-gateway",
    "arch-compute",
    "arch-data-ingestion",
    "arch-observability",
    "arch-storage",
)
PLUGIN_PATH = {s: s for s in DOMAIN_SKILLS} | {s: "arch/" + s[len("arch-") :] for s in ARCH_SKILLS}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
MAX_DESCRIPTION_CHARS = 1024  # the Agent Skills limit on the frontmatter description


def _frontmatter(skill: str) -> dict[str, str]:
    text = (REPO / ".claude" / "skills" / skill / "SKILL.md").read_text()
    block = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert block, f"{skill}: missing frontmatter"
    name = re.search(r"^name:\s*(\S+)", block.group(1), re.MULTILINE)
    version = re.search(r'^version:\s*"?([^"\n]+)"?', block.group(1), re.MULTILINE)
    desc = re.search(r"^description: >\n((?:  .*\n?)+)", block.group(1) + "\n", re.MULTILINE)
    assert name and version and desc, f"{skill}: frontmatter missing name/version/description"
    return {
        "name": name.group(1),
        "version": version.group(1),
        "description": " ".join(desc.group(1).split()),
    }


@pytest.fixture(scope="module")
def rendered() -> dict[str, str]:
    """What sync_skills.py would write right now, keyed by repo-relative path."""
    return {str(p.relative_to(REPO)): content for p, content in sync_skills._targets()}


def test_domain_skills_are_in_sync_with_the_catalog(rendered: dict[str, str]) -> None:
    stale = [path for path, content in rendered.items() if (REPO / path).read_text() != content]
    assert (
        not stale
    ), "stale skill files, run `python3 scripts/sync_skills.py` and commit: " + ", ".join(stale)


def test_every_catalogued_function_is_in_exactly_one_skill() -> None:
    catalog = json.loads((REPO / "portal" / "functions.json").read_text())
    expected: dict[str, int] = {}
    for entry in catalog:
        expected[entry["domain"]] = expected.get(entry["domain"], 0) + 1
    assert sum(expected.values()) == 385
    seen: set[tuple[str, str]] = set()
    for skill in DOMAIN_SKILLS:
        spec = json.loads((REPO / "scripts" / "skill_specs" / f"{skill}.json").read_text())
        names = [fn for g in spec["groups"] for fn in g["functions"]]
        assert len(names) == len(set(names)), f"{skill}: duplicate function"
        assert len(names) == expected[spec["domain"]], f"{skill}: function count != catalog"
        seen |= {(spec["domain"], n) for n in names}
    assert seen == {(e["domain"], e["name"]) for e in catalog}


@pytest.mark.parametrize("skill", DOMAIN_SKILLS + ARCH_SKILLS)
def test_frontmatter_is_valid_and_matches_the_plugin(skill: str) -> None:
    fm = _frontmatter(skill)
    assert fm["name"] == f"pyvar-{skill}"
    assert SEMVER.match(fm["version"])
    assert len(fm["description"]) <= MAX_DESCRIPTION_CHARS
    plugin = json.loads(
        (REPO / "plugins" / PLUGIN_PATH[skill] / ".claude-plugin" / "plugin.json").read_text()
    )
    assert plugin["name"] == fm["name"]
    assert plugin["version"] == fm["version"]


@pytest.mark.parametrize("skill", DOMAIN_SKILLS)
def test_domain_skill_tells_claude_how_to_run_a_function(skill: str) -> None:
    text = (REPO / ".claude" / "skills" / skill / "SKILL.md").read_text()
    assert "API key" in _frontmatter(skill)["description"]
    for needle in ("PYVAR_API_KEY", f"{sync_skills.SIGNUP_URL}", "pyvar-client", "429"):
        assert needle in text, f"{skill}: setup section lost {needle!r}"
    # the old stub style gave no parameters and a Python namespace that does not exist
    assert "**params" not in text
    assert not re.search(
        r"\bpyvar\.(market_risk|credit_risk|liquidity|operational|portfolio)\.", text
    )
    assert "references/functions.md" in text


@pytest.mark.parametrize("skill", ARCH_SKILLS)
def test_arch_skills_say_they_are_for_contributors(skill: str) -> None:
    text = (REPO / ".claude" / "skills" / skill / "SKILL.md").read_text()
    assert _frontmatter(skill)["description"].startswith("Architecture notes for contributors")
    assert "Who this is for" in text


@pytest.mark.parametrize("skill", DOMAIN_SKILLS + ARCH_SKILLS)
def test_plugin_copy_matches_the_skill_source(skill: str) -> None:
    src = REPO / ".claude" / "skills" / skill
    dst = REPO / "plugins" / PLUGIN_PATH[skill]
    assert (dst / "SKILL.md").read_text() == (src / "SKILL.md").read_text()
    src_refs = (
        sorted(p.name for p in (src / "references").glob("*"))
        if (src / "references").is_dir()
        else []
    )
    dst_refs = (
        sorted(p.name for p in (dst / "references").glob("*"))
        if (dst / "references").is_dir()
        else []
    )
    assert src_refs == dst_refs
    for name in src_refs:
        assert (dst / "references" / name).read_text() == (src / "references" / name).read_text()

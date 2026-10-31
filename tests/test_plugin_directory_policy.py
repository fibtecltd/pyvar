"""The checks Anthropic's plugin directory runs on every submission, run on every plugin here.

Each rule below was a finding on a real review of pyvar-portfolio-analytics v1.1.0 (the review
repeated daily on the same commit until the plugin changed):

- No icon: a square PNG or JPEG of 512 to 2048 px a side, under 2 MB, named by `icon` in plugin.json.
- Listing link not accepted: the listing's README and the four listing links must be https://. A
  plugin folder with no README of its own is shown the repository's root README, whose
  "http://localhost:8000/docs" comment was read as the plugin's documentation link.
- Uses a credential from the user's machine: a skill that tells Claude to look for the API key in
  the environment, or to run code that reads it there, is held ("Update adds credential forward").
  The key has to come from a `userConfig` option with `sensitive: true`, which only an MCP server
  can receive (a sensitive value is not substituted into skill text), so the skills point to the
  pyvar-mcp plugin and carry no credential handling of their own.

`claude plugin validate ./plugins/<name> --strict` runs the first two against a real plugin
folder; run it too before submitting.
"""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGINS = REPO / "plugins"
LISTING_URLS = ("documentationUrl", "supportUrl", "privacyPolicyUrl", "termsOfServiceUrl")
SKILL_PLUGINS = sorted(
    p.parent.parent
    for p in PLUGINS.glob("**/.claude-plugin/plugin.json")
    if p.parent.parent.name != "mcp"
)
ALL_PLUGINS = SKILL_PLUGINS + [PLUGINS / "mcp"]
IDS = [str(p.relative_to(PLUGINS)) for p in ALL_PLUGINS]
SKILL_IDS = [str(p.relative_to(PLUGINS)) for p in SKILL_PLUGINS]
_MD_LINK = re.compile(r"\]\(([^)\s]+)")
_ABSOLUTE = re.compile(r"^https://")


def _manifest(plugin: Path) -> dict[str, object]:
    return json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_there_are_fourteen_plugins() -> None:
    assert len(SKILL_PLUGINS) == 13 and len(ALL_PLUGINS) == 14


@pytest.mark.parametrize("plugin", ALL_PLUGINS, ids=IDS)
def test_plugin_has_a_listing_icon(plugin: Path) -> None:
    icon = _manifest(plugin).get("icon")
    assert isinstance(icon, str) and icon.startswith("./"), f"{plugin.name}: no icon in plugin.json"
    path = plugin / icon
    assert path.suffix.lower() == ".png" and path.is_file(), f"{plugin.name}: {icon} is missing"
    width, height = _png_size(path)
    assert width == height, f"{plugin.name}: icon is {width}x{height}, not square"
    assert 512 <= width <= 2048, f"{plugin.name}: icon is {width}px, needs 512 to 2048"
    assert path.stat().st_size < 2 * 1024 * 1024, f"{plugin.name}: icon is 2 MB or more"


@pytest.mark.parametrize("plugin", ALL_PLUGINS, ids=IDS)
def test_plugin_listing_links_are_https(plugin: Path) -> None:
    manifest = _manifest(plugin)
    for field in LISTING_URLS:
        value = manifest.get(field)
        assert isinstance(value, str) and _ABSOLUTE.match(
            value
        ), f"{plugin.name}: {field}={value!r}"
    for field in ("homepage", "repository"):
        assert _ABSOLUTE.match(str(manifest[field])), f"{plugin.name}: {field} is not https"


@pytest.mark.parametrize("plugin", ALL_PLUGINS, ids=IDS)
def test_plugin_has_its_own_readme_with_only_https_links(plugin: Path) -> None:
    readme = plugin / "README.md"
    assert readme.is_file(), f"{plugin.name}: no README.md, so the repository's would be used"
    text = readme.read_text(encoding="utf-8")
    for target in _MD_LINK.findall(text):
        assert _ABSOLUTE.match(target), f"{plugin.name}: README links to {target!r}"
    for line in text.splitlines():
        assert not re.search(
            r"https?://(localhost|127\.|0\.0\.0\.0)", line
        ), f"{plugin.name}: {line}"


def _skill_files(plugin: Path) -> list[Path]:
    return [plugin / "SKILL.md", *sorted((plugin / "references").glob("*.md"))]


@pytest.mark.parametrize("plugin", SKILL_PLUGINS, ids=SKILL_IDS)
def test_skill_files_have_no_relative_links(plugin: Path) -> None:
    for path in _skill_files(plugin):
        for target in _MD_LINK.findall(path.read_text(encoding="utf-8")):
            assert _ABSOLUTE.match(target), f"{path.relative_to(REPO)} links to {target!r}"


# The eight domain skills call the pyvar API for the user; the five architecture skills only
# describe the codebase (one snippet shows the server's own Celery settings), so only the former
# are held to "never read a credential".
DOMAIN_PLUGINS = [p for p in SKILL_PLUGINS if p.parent.name != "arch"]


@pytest.mark.parametrize("plugin", DOMAIN_PLUGINS, ids=[p.name for p in DOMAIN_PLUGINS])
def test_domain_skill_reads_no_credential_from_the_machine(plugin: Path) -> None:
    assert len(DOMAIN_PLUGINS) == 8
    for path in _skill_files(plugin):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("PYVAR_API_KEY", "os.environ", "getenv(", "$PYVAR", "in the environment"):
            assert forbidden not in text, f"{path.relative_to(REPO)} mentions {forbidden!r}"


def test_the_repository_readme_has_no_localhost_documentation_link() -> None:
    # still the README of last resort for any plugin folder that has none
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert not re.search(r"(?i)docs?:\s*https?://(localhost|127\.)", text)


def test_pyvar_mcp_takes_its_key_from_a_sensitive_user_config_option() -> None:
    manifest = _manifest(PLUGINS / "mcp")
    option = manifest["userConfig"]["pyvar_api_key"]  # type: ignore[index]
    assert option["sensitive"] is True and option["required"] is True
    env = manifest["mcpServers"]["pyvar"]["env"]  # type: ignore[index]
    assert env == {"PYVAR_API_KEY": "${user_config.pyvar_api_key}"}

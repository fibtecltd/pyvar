#!/usr/bin/env python3
"""scripts/generate_article_headers.py — header images for the Medium articles.

Reasoning:
- A header image that states numbers should state numbers that are true. Every figure here is
  read from the repository when the image is drawn (the plugin manifest, the function
  catalogue, the skill specs, config.py, the client and notebook packages, the pyvar-full
  compose file), so a header cannot drift from the code behind its article.
- Same house style and tile grid as the plugins-end-to-end article
  (scripts/generate_plugin_flow_figures.py::tiles_figure).
- Medium does not accept SVG, so the output is PNG. The script fails if any label overflows its
  tile.

Usage (repo root; matplotlib and pyyaml are tooling dependencies only:
pip install matplotlib pyyaml):
    python scripts/generate_article_headers.py
    python scripts/generate_article_headers.py --only client-guide,rest-api-guide --out /tmp/h
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import generate_plugin_figures as g  # noqa: E402
import generate_plugin_flow_figures as ff  # noqa: E402  (tiles grid, config readers)

DEFAULT_OUT = ROOT / "docs" / "publications" / "assets" / "headers"
Tile = tuple[str, str, str, bool]


def plugin_counts() -> tuple[int, int, int, int]:
    """(plugins, domain skills, architecture skills, MCP servers) from the plugin manifest."""
    manifest = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text("utf-8"))
    names = [p["name"] for p in manifest["plugins"]]
    arch = sum(n.startswith("pyvar-arch-") for n in names)
    mcp = sum(n == "pyvar-mcp" for n in names)
    return len(names), len(names) - arch - mcp, arch, mcp


def mcp_launch() -> tuple[str, str]:
    """(command, args) the pyvar-mcp plugin starts the server with."""
    plugin = json.loads(
        (ROOT / "plugins" / "mcp" / ".claude-plugin" / "plugin.json").read_text("utf-8")
    )
    server = plugin["mcpServers"]["pyvar"]
    return str(server["command"]), " ".join(server["args"])


def project(path: str) -> dict[str, object]:
    """The [project] table of a pyproject.toml."""
    data = tomllib.loads((ROOT / path / "pyproject.toml").read_text("utf-8"))
    return dict(data["project"])


def source_constant(path: str, name: str) -> float:
    text = (ROOT / path).read_text("utf-8")
    match = re.search(rf"^{name}\s*=\s*([\d.]+)", text, re.MULTILINE)
    g.need(match is not None, f"{name} not found in {path}")
    assert match is not None
    return float(match.group(1))


def magic_names() -> list[str]:
    """Methods of pyvar-jupyter's PyvarMagics decorated as IPython magics."""
    tree = ast.parse((ROOT / "pyvar-jupyter" / "pyvar_jupyter" / "_magics.py").read_text("utf-8"))
    kinds = {"line_magic", "cell_magic", "line_cell_magic"}
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            decorators = {d.id for d in node.decorator_list if isinstance(d, ast.Name)}
            if decorators & kinds:
                names.append(node.name)
    return sorted(names)


def notebooks() -> int:
    return len(list((ROOT / "pyvar-jupyter" / "examples").glob("*.ipynb")))


def compose_services() -> list[str]:
    data = yaml.safe_load((ROOT / "pyvar-full" / "docker-compose.yml").read_text("utf-8"))
    return list(data["services"])


def simulation_caps() -> tuple[int, int, int]:
    from api.middleware.auth import TokenPayload

    caps = [TokenPayload("caps", tier).max_simulations for tier in ("free", "pro", "enterprise")]
    return caps[0], caps[1], caps[2]


def head_plugins() -> tuple[str, str, list[Tile]]:
    total, domain, arch, mcp = plugin_counts()
    functions, domains = ff.catalogue_counts()
    _, examples, calls = ff.example_counts()
    command, args = mcp_launch()
    return (
        f"{total} plugins at a glance",
        "Read from the plugin manifest, the skill specs and the function catalogue when this image is drawn.",
        [
            (
                f"{total}",
                "plugins in one marketplace",
                f"{domain} domain skills, {arch} architecture skills, {mcp} MCP server",
                False,
            ),
            (f"{functions}", "functions behind them", f"{domains} domains, one REST API", True),
            (
                f"{examples}",
                "worked examples in the domain skills",
                f"{calls} requests run against the real application on every test run",
                True,
            ),
            (
                command,
                "starts the MCP server",
                f"{command} {args}: the plugin runs the server from PyPI",
                False,
            ),
        ],
    )


def head_live_updates() -> tuple[str, str, list[Tile]]:
    total, domain, arch, mcp = plugin_counts()
    services = compose_services()
    return (
        "pyvar today at a glance",
        "Read from the plugin manifest, config.py and pyvar-full/docker-compose.yml when this image is drawn.",
        [
            (
                f"{total}",
                "plugins",
                f"{domain} domain skills, {arch} architecture skills, {mcp} MCP server",
                False,
            ),
            (
                f"{int(ff.default('var_stream_max_wait_seconds'))} s",
                "longest a result stream waits",
                "the stream pushes the result the instant the job completes",
                True,
            ),
            (f"{len(services)}", "services in one docker compose up", ", ".join(services), True),
            (
                f"{ff.default('api_key_default_expiry_days')} days",
                "API key lifetime",
                "created on the dashboard after signing in",
                False,
            ),
        ],
    )


def head_client_guide() -> tuple[str, str, list[Tile]]:
    functions, domains = ff.catalogue_counts()
    meta = project("pyvar-client")
    deps = list(meta["dependencies"])  # type: ignore[call-overload]
    retries = int(source_constant("pyvar-client/pyvar_client/_transport.py", "_MAX_RETRIES"))
    backoff = source_constant("pyvar-client/pyvar_client/_transport.py", "_BACKOFF_BASE_SECONDS")
    return (
        "pyvar-client at a glance",
        "Read from the function catalogue, pyvar-client's pyproject.toml and its transport module when this image is drawn.",
        [
            (
                f"{functions}",
                "functions, one method each",
                f"{domains} domain namespaces plus var for the async Monte Carlo job",
                False,
            ),
            (
                f"{retries}",
                "automatic retries",
                f"exponential backoff from {backoff} s, idempotent calls only",
                True,
            ),
            (
                f"{len(deps)}",
                "runtime dependency" if len(deps) == 1 else "runtime dependencies",
                ", ".join(deps),
                True,
            ),
            (
                f"{meta['version']}",
                "current version",
                "Client() reads PYVAR_API_KEY from the environment",
                False,
            ),
        ],
    )


def head_jupyter_guide() -> tuple[str, str, list[Tile]]:
    functions, _ = ff.catalogue_counts()
    meta = project("pyvar-jupyter")
    magics = magic_names()
    return (
        "pyvar-jupyter at a glance",
        "Read from the function catalogue, pyproject.toml, the magics and the examples folder when this image is drawn.",
        [
            (f"{len(magics)}", "magics", ", ".join("%" + m for m in magics), False),
            (
                f"{notebooks()}",
                "worked example notebooks",
                "in pyvar-jupyter/examples, ready to run",
                True,
            ),
            (
                f"{functions}",
                "functions from one magic",
                "any <domain>.<function>, parameters as key=value or JSON",
                True,
            ),
            (
                f"{meta['version']}",
                "current version",
                "pip install pyvar-jupyter, then %load_ext pyvar_jupyter",
                False,
            ),
        ],
    )


def head_domain_examples() -> tuple[str, str, list[Tile]]:
    functions, domains = ff.catalogue_counts()
    meta = project("pyvar-jupyter")
    return (
        "Nine notebooks at a glance",
        "Read from pyvar-jupyter's examples folder, the function catalogue and its pyproject.toml when this image is drawn.",
        [
            (
                f"{notebooks()}",
                "worked example notebooks",
                "01 to 09 in pyvar-jupyter/examples",
                False,
            ),
            (
                f"{domains}",
                "risk domains in the catalogue",
                "each reachable from a notebook with one magic",
                True,
            ),
            (
                f"{functions}",
                "functions available",
                "the same catalogue the REST API and the plugins use",
                True,
            ),
            (
                f"{meta['version']}",
                "pyvar-jupyter version",
                "pip install pyvar-jupyter, then %load_ext pyvar_jupyter",
                False,
            ),
        ],
    )


def head_rest_guide() -> tuple[str, str, list[Tile]]:
    functions, domains = ff.catalogue_counts()
    free_cap, pro_cap, ent_cap = simulation_caps()
    return (
        "The REST API at a glance",
        "Read from the function catalogue, config.py and the tier definitions when this image is drawn.",
        [
            (
                f"{functions}",
                "POST endpoints",
                "/api/v1/<domain>/<function>, JSON in and JSON out",
                False,
            ),
            (
                f"{domains}",
                "domain prefixes",
                "market-risk, credit-risk, derivatives and five more",
                True,
            ),
            (
                f"{ff.default('rate_limit_free_daily')} a day",
                "free-tier calls",
                f"{ff.default('rate_limit_pro_daily')} a day on Pro, one shared bucket across every endpoint",
                True,
            ),
            (
                f"{free_cap:,}",
                "simulations per Monte Carlo call, free",
                f"{pro_cap:,} on Pro, {ent_cap:,} on Enterprise",
                False,
            ),
        ],
    )


HEADERS: dict[str, Callable[[], tuple[str, str, list[Tile]]]] = {
    "pyvar-plugins": head_plugins,
    "pyvar-plugins-live-recent-updates": head_live_updates,
    "pyvar-client-guide": head_client_guide,
    "pyvar-jupyter-guide": head_jupyter_guide,
    "pyvar-domain-examples": head_domain_examples,
    "pyvar-rest-api-guide": head_rest_guide,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--only", default="", help="comma-separated: " + ", ".join(HEADERS))
    args = parser.parse_args()
    only = [n for n in args.only.split(",") if n]
    keys = [k for k in HEADERS if not only or k in only or k.removeprefix("pyvar-") in only]
    if only and not keys:
        raise SystemExit(f"unknown header(s): {', '.join(only)}")
    for key in keys:
        title, subtitle, tiles = HEADERS[key]()
        print("wrote", ff.tiles_figure(title, subtitle, tiles, Path(args.out), f"header-{key}"))


if __name__ == "__main__":
    main()

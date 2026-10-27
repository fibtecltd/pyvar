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
- A header can also be a picture instead of a grid of facts: ART_HEADERS maps an article to the
  artwork kept under docs/publications/assets/headers/source/, saved as PNG at its own size
  (the overview article's dot-matrix bell curve). The script fails if the picture is not
  roughly 2:1, the shape Medium and social previews crop to.

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
ART_SOURCES = DEFAULT_OUT / "source"
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


def setting(name: str) -> float:
    """A setting's built-in default as a number (config.Settings; ints and floats alike)."""
    value = ff.Settings.model_fields[name].default
    g.need(isinstance(value, (int, float)), f"{name} default is not a number: {value!r}")
    return float(value)


def head_streaming_results() -> tuple[str, str, list[Tile]]:
    wait = int(setting("var_stream_max_wait_seconds"))
    per_process = int(setting("var_stream_max_connections"))
    per_account = int(setting("var_stream_max_connections_per_user"))
    safety = setting("var_stream_safety_poll_seconds")
    return (
        "The result stream at a glance",
        "Read from the route, the schemas and config.py when this image is drawn.",
        [
            (
                "1 frame",
                "the result, then the server closes",
                "same JSON as GET /var/result/{task_id}",
                False,
            ),
            (
                f"{wait} s",
                "the longest a stream waits",
                "then a pending frame and a close; polling still works",
                True,
            ),
            (
                f"{per_process}",
                "open streams per server process",
                f"{per_account} per account; over the cap the close code is 1013",
                True,
            ),
            (
                f"{safety:g} s",
                "the longest a lost push can delay a result",
                "a timer re-reads the stored result if a message is missed",
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
    "pyvar-streaming-results": head_streaming_results,
}


# article -> artwork file under ART_SOURCES
ART_HEADERS: dict[str, str] = {"pyvar-overview": "bell-dot-matrix.jpg"}


def art_header(key: str, out: Path) -> Path:
    """The article's artwork, saved as header-<key>.png at its own size."""
    from PIL import Image

    source = ART_SOURCES / ART_HEADERS[key]
    g.need(source.is_file(), f"artwork for {key} not found: {source}")
    with Image.open(source) as picture:
        rgb = picture.convert("RGB")
    width, height = rgb.size
    g.need(1.8 <= width / height <= 2.0, f"{source.name} is {width}x{height}, not roughly 2:1")
    g.need(width >= 1200, f"{source.name} is only {width}px wide; Medium wants 1200 or more")
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"header-{key}.png"
    rgb.save(path, optimize=True)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    names = [*HEADERS, *ART_HEADERS]
    parser.add_argument("--only", default="", help="comma-separated: " + ", ".join(names))
    args = parser.parse_args()
    only = [n for n in args.only.split(",") if n]
    keys = [k for k in names if not only or k in only or k.removeprefix("pyvar-") in only]
    if only and not keys:
        raise SystemExit(f"unknown header(s): {', '.join(only)}")
    for key in keys:
        if key in ART_HEADERS:
            print("wrote", art_header(key, Path(args.out)))
            continue
        title, subtitle, tiles = HEADERS[key]()
        print("wrote", ff.tiles_figure(title, subtitle, tiles, Path(args.out), f"header-{key}"))


if __name__ == "__main__":
    main()

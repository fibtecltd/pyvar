#!/usr/bin/env python3
"""scripts/check_home_snippet.py: run the code shown in the home page's terminal panel, as written, and compare.

Reasoning:
- The panel on portal/index.html shows how to call the API with pyvar-client. It was wrong once (an import of a package
  that does not exist, a keyword the client does not take, fields read as attributes of a dict) and nobody noticed, because
  nothing ran it. This reads the code out of the page, runs it unchanged through the real pyvar-client, and checks that
  what it prints is what the panel says it prints. tests/test_portal_home_snippet.py does the same offline against the
  real server-side request and result models and engine; this is the same check against a live deployment.
- "As written" means the page's own lines: the snippet's `Client(api_key="pyvar_...")` is the real class, with the key
  and the base URL put in by a thin subclass (the page's text is not edited), and `returns` is the 60-day demo series
  the publisher uses (pyvar-cdk/lambda/public_data_publisher/handler.py), which is also what the panel's numbers come from.
- The key is read from PYVAR_API_KEY and is never printed. Use a dev key against dev: a run is one VaR job (1,000 paths).
- It imports the repository's own pyvar-client, so `httpx` (the client's one runtime dependency, in requirements.txt)
  must be installed where it runs: on a machine without the project's environment, `pip install httpx` first. Without
  it the run prints "the snippet failed: ModuleNotFoundError" and exits 1, before any request is made. `--show` needs
  nothing installed.

Usage (repo root):
    PYVAR_API_KEY=pyvar_... python scripts/check_home_snippet.py --base-url https://dev.pyvar.com
    python scripts/check_home_snippet.py --show        # just print the code and the outputs the page shows

Exit codes: 0 the snippet ran and printed what the page shows; 1 it ran and printed something else (or failed);
2 a usage error (no key, no snippet found).
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import os
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "portal" / "index.html"
PUBLISHER = ROOT / "pyvar-cdk" / "lambda" / "public_data_publisher" / "handler.py"


class _TerminalLines(HTMLParser):
    """The text of each line (each direct child <div>) of the page's `.terminal-body`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.body_depth: int | None = None
        self.current: list[str] | None = None
        self.lines: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        self.depth += 1
        classes = (dict(attrs).get("class") or "").split()
        if "terminal-body" in classes and self.body_depth is None:
            self.body_depth = self.depth
        elif self.body_depth is not None and self.depth == self.body_depth + 1:
            self.current = []

    def handle_endtag(self, tag: str) -> None:
        if tag != "div":
            return
        if (
            self.body_depth is not None
            and self.depth == self.body_depth + 1
            and self.current is not None
        ):
            self.lines.append("".join(self.current).replace("\xa0", " ").rstrip())
            self.current = None
        if self.depth == self.body_depth:
            self.body_depth = -1  # closed: ignore anything after the panel
        self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.current.append(data)


def panel_lines(html: str | None = None) -> list[str]:
    parser = _TerminalLines()
    parser.feed(html if html is not None else INDEX.read_text(encoding="utf-8"))
    return parser.lines


def split_panel(lines: list[str]) -> tuple[str, list[str]]:
    """(the code the panel shows, the output lines it shows). The code is every `>>>` line plus its indented
    continuation lines and the closing parenthesis; an output line is a value, then `  # a note`."""
    code: list[str] = []
    outputs: list[str] = []
    for line in lines:
        if line.startswith(">>> "):
            code.append(line[4:])
        elif line.startswith("    ") or line == ")":
            code.append(line)
        elif line.startswith(("$", "#")) or not line:
            continue
        else:
            outputs.append(line)
    return "\n".join(code) + "\n", outputs


def snippet_code() -> str:
    code, _ = split_panel(panel_lines())
    return code


def shown_outputs() -> list[str]:
    """The value of each output line the panel shows, without its trailing `  # note`."""
    _, outputs = split_panel(panel_lines())
    return [line.partition("  #")[0].strip() for line in outputs]


def demo_returns() -> list[float]:
    """The publisher's fixed 60-day series, read from its source without importing it (it needs AWS settings)."""
    tree = ast.parse(PUBLISHER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "DEMO_RETURNS":
            assert node.value is not None
            return [float(v) for v in ast.literal_eval(node.value)]
    raise LookupError("DEMO_RETURNS not found in the publisher")


def import_client() -> Any:
    """The repository's pyvar_client package (not an installed one, which may be older)."""
    path = str(ROOT / "pyvar-client")
    if path not in sys.path:
        sys.path.insert(0, path)
    import pyvar_client

    return pyvar_client


def run_snippet(
    code: str, *, api_key: str | None = None, base_url: str | None = None, transport: Any = None
) -> list[str]:
    """Run `code` unchanged through the real client and return what it printed, line by line.

    `Client` inside the page's own `from pyvar_client import Client` is a subclass that supplies the key, the base
    URL and (for the offline test) a transport; nothing about the page's text is edited.
    """
    module = import_client()
    real = module.Client

    class PageClient(real):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if api_key:
                kwargs["api_key"] = api_key
                args = ()
            if base_url:
                kwargs["base_url"] = base_url
            if transport is not None:
                kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    module.Client = PageClient
    try:
        out = io.StringIO()
        compiled = compile(code, str(INDEX), "exec")
        namespace = {"returns": demo_returns()}
        with contextlib.redirect_stdout(out):
            # nosec B102: the code is the snippet in this repository's own home page, run by an operator or a test.
            exec(compiled, namespace)  # nosec B102  # noqa: S102
    finally:
        module.Client = real
    return out.getvalue().splitlines()


def compare(printed: list[str], shown: list[str]) -> list[str]:
    """Differences between what the code printed and what the panel shows. The engine's time varies from run to run,
    so the last value need only be a whole number of milliseconds; the others must be equal."""
    problems: list[str] = []
    if len(printed) != len(shown):
        return [f"the code printed {len(printed)} lines, the panel shows {len(shown)}"]
    for index, (got, want) in enumerate(zip(printed, shown, strict=True)):
        if index == len(shown) - 1:
            if not got.isdigit():
                problems.append(
                    f"line {index + 1}: duration_ms printed {got!r}, not a whole number"
                )
        elif got != want:
            problems.append(f"line {index + 1}: printed {got!r}, the panel shows {want!r}")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--base-url", default="https://dev.pyvar.com", help="API base URL (default: dev)"
    )
    parser.add_argument(
        "--show", action="store_true", help="print the code and the shown outputs; run nothing"
    )
    args = parser.parse_args(argv)

    code = snippet_code()
    shown = shown_outputs()
    if not code.strip() or not shown:
        print("no snippet found in portal/index.html", file=sys.stderr)
        return 2
    if args.show:
        print(code)
        print("the panel shows:", *shown, sep="\n  ")
        return 0
    key = os.environ.get("PYVAR_API_KEY")
    if not key:
        print("set PYVAR_API_KEY (a key for the environment named by --base-url)", file=sys.stderr)
        return 2
    try:
        printed = run_snippet(code, api_key=key, base_url=args.base_url)
    except (
        Exception
    ) as exc:  # noqa: BLE001 - report the class, never the message (it could carry a response body)
        print(f"the snippet failed: {type(exc).__name__}")
        return 1
    problems = compare(printed, shown)
    print("printed:", *printed, sep="\n  ")
    print("the panel shows:", *shown, sep="\n  ")
    if problems:
        print("DIFFERENT:", *problems, sep="\n  ")
        return 1
    print(f"OK: the page's snippet ran against {args.base_url} and printed what the panel shows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

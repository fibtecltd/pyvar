"""pyvar_local/cli.py — minimal local CLI over the pyvar compute engine.

Reasoning:
- docs/proposals/pyvar-local-package-proposal.docx's own "what ships in the
  package" scope is engine/ plus a lightweight local entry point, not a
  full parallel FastAPI server matching the hosted API's route surface --
  that fuller server is tracked as a deliberate fast-follow (see this
  package's README), not built here.
- This CLI is a real, functional interface, not a stub: every public
  engine function is reachable by design, discovered by reflecting over
  the actual engine/ modules at runtime -- so it can never drift out of
  sync with what engine/ actually contains the way a hand-maintained
  dispatch table could.
- No API key, no network call: engine/ functions are called directly,
  in-process.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import pkgutil
import sys
from collections.abc import Iterator
from typing import Any

import engine


def _iter_engine_functions() -> Iterator[tuple[str, str, Any]]:
    """Yield (module_name, function_name, callable) for every public,
    top-level function actually defined in each engine/*.py module."""
    for _finder, mod_name, _is_pkg in pkgutil.iter_modules(engine.__path__):
        module = importlib.import_module(f"engine.{mod_name}")
        for func_name, func in inspect.getmembers(module, inspect.isfunction):
            if func_name.startswith("_"):
                continue
            if func.__module__ != module.__name__:
                continue  # imported into this module, not defined here -- skip duplicates
            yield mod_name, func_name, func


def cmd_list(_args: argparse.Namespace) -> None:
    for mod_name, func_name, func in sorted(_iter_engine_functions()):
        print(f"{mod_name}.{func_name}{inspect.signature(func)}")


def cmd_call(args: argparse.Namespace) -> None:
    params: dict[str, Any] = json.loads(args.params) if args.params else {}

    try:
        module = importlib.import_module(f"engine.{args.module}")
    except ModuleNotFoundError:
        print(f"error: no such engine module 'engine.{args.module}'", file=sys.stderr)
        sys.exit(1)

    func = getattr(module, args.function, None)
    if args.function.startswith("_") or not inspect.isfunction(func):
        print(
            f"error: no such public function '{args.function}' in engine.{args.module}",
            file=sys.stderr,
        )
        sys.exit(1)

    result = func(**params)
    print(json.dumps(result, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pyvar-local",
        description="Call pyvar's compute engine directly, offline -- no API key, no network.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List every callable engine function").set_defaults(func=cmd_list)

    call_parser = sub.add_parser("call", help="Call one engine function")
    call_parser.add_argument("module", help="engine submodule, e.g. montecarlo")
    call_parser.add_argument("function", help="function name, e.g. run_monte_carlo_var")
    call_parser.add_argument(
        "--params",
        default=None,
        help="JSON object of keyword arguments, e.g. '{\"portfolio_value\": 1000000}'",
    )
    call_parser.set_defaults(func=cmd_call)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

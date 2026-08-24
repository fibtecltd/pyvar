"""pyvar_client.cli -- the `pyvar` command-line entry point.

Reasoning:
- Generic JSON-params dispatch, not 385 hand-generated per-function flag
  sets: `pyvar <domain> <function> --params file.json` resolves via
  getattr(client, domain) then getattr(namespace, function) and calls it
  with the params dict unpacked as keyword arguments -- every generated
  method takes keyword-only args (see pyvar_client._generated's own module
  docstring), so this works uniformly across all 385 methods and any
  future ones with zero new codegen. The alternative -- a second codegen
  step producing 385 argparse subcommands -- is exactly the kind of second
  place the SDK's own methods could drift from the API (see
  docs/p9-function-catalogue-reconciliation.md in the main repo for a real
  instance of that drift already happening once).
- argparse, stdlib only -- pyproject.toml's own comment on the httpx
  dependency ("Dependency-light by design") extends to the CLI: no new
  runtime dependency, so `pip install pyvar-client` alone gets you the
  `pyvar` command, no extras group required.
- Domain subcommands are named after the SDK's own snake_case Client
  attributes (market_risk, credit_risk, ...), not the API's kebab-case
  path segments -- a kebab->snake translation table would reintroduce the
  same hardcoded-mapping drift risk the generic-dispatch design above is
  meant to avoid.
- `var` is not a generic domain: client.var wraps the one async function
  (submit/poll/compute, see pyvar_client._var's own module docstring) with
  a genuinely different call shape, so it gets its own submit/poll/compute
  sub-subcommands instead of a bare `function` positional.
- Calling a function with neither --params nor --params-json prints its
  docstring and signature instead of attempting a call that's certain to
  fail validation with zero fields -- cheap discoverability without
  fighting argparse's own per-subcommand -h/--help, which can't know about
  a specific function's parameters ahead of time.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from collections.abc import Callable
from typing import Any

from pyvar_client import __version__
from pyvar_client._client import DEFAULT_BASE_URL, DEFAULT_TIMEOUT_SECONDS, Client
from pyvar_client._generated.alm import AlmNamespace
from pyvar_client._generated.credit_risk import CreditRiskNamespace
from pyvar_client._generated.derivatives import DerivativesNamespace
from pyvar_client._generated.liquidity import LiquidityNamespace
from pyvar_client._generated.market_risk import MarketRiskNamespace
from pyvar_client._generated.operational import OperationalNamespace
from pyvar_client._generated.portfolio import PortfolioNamespace
from pyvar_client._generated.regulatory import RegulatoryNamespace
from pyvar_client._var import VarNamespace
from pyvar_client.exceptions import (
    PyvarAuthError,
    PyvarComputeError,
    PyvarError,
    PyvarRateLimitError,
    PyvarTimeoutError,
    PyvarValidationError,
)

# Client attribute name -> generated namespace class. Mirrors _client.py's
# own __init__ exactly -- that's the one place these are defined, so this
# table is hand-written from it rather than introspected (there's no live
# Client to introspect without an API key already in hand, and list-domains/
# list-functions deliberately need none).
_NAMESPACE_CLASSES: dict[str, type] = {
    "market_risk": MarketRiskNamespace,
    "derivatives": DerivativesNamespace,
    "credit_risk": CreditRiskNamespace,
    "portfolio": PortfolioNamespace,
    "operational_risk": OperationalNamespace,
    "liquidity_risk": LiquidityNamespace,
    "alm": AlmNamespace,
    "regulatory": RegulatoryNamespace,
    "var": VarNamespace,
}

_GENERIC_DOMAINS = tuple(name for name in _NAMESPACE_CLASSES if name != "var")

_EXIT_OK = 0
_EXIT_ERROR = 1
_EXIT_AUTH_ERROR = 2
_EXIT_VALIDATION_ERROR = 3
_EXIT_RATE_LIMIT = 4
_EXIT_COMPUTE_ERROR = 5
_EXIT_INTERRUPTED = 130


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--api-key",
        default=None,
        help="Bearer JWT. Falls back to the PYVAR_API_KEY environment variable.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=f"API base URL. Falls back to PYVAR_BASE_URL, then {DEFAULT_BASE_URL!r}.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print single-line JSON instead of indented.",
    )


def _add_params_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--params",
        metavar="FILE",
        help="Path to a JSON file of keyword arguments, or - to read JSON from stdin.",
    )
    group.add_argument(
        "--params-json",
        metavar="JSON",
        help="Inline JSON object of keyword arguments.",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """Builds the full `pyvar` argparse tree. See module docstring for the shape."""
    parser = argparse.ArgumentParser(
        prog="pyvar",
        description="Command-line client for pyvar.com's risk computation API.",
    )
    parser.add_argument("--version", action="version", version=f"pyvar-client {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_domains = subparsers.add_parser(
        "list-domains", help="List the available domain subcommands."
    )
    _add_common_args(list_domains)

    list_functions = subparsers.add_parser(
        "list-functions", help="List the functions available in one domain."
    )
    _add_common_args(list_functions)
    list_functions.add_argument(
        "--domain", required=True, choices=sorted(_NAMESPACE_CLASSES), help="Domain to list."
    )

    for domain in _GENERIC_DOMAINS:
        sub = subparsers.add_parser(domain, help=f"Call a {domain} function.")
        _add_common_args(sub)
        sub.add_argument("function", help="Method name, e.g. historical_simulation_var.")
        _add_params_args(sub)

    var_parser = subparsers.add_parser("var", help="The one async function: submit/poll/compute.")
    var_sub = var_parser.add_subparsers(dest="var_command", required=True)

    var_submit = var_sub.add_parser("submit", help="Submit a VaR job, print its task_id.")
    _add_common_args(var_submit)
    _add_params_args(var_submit)

    var_poll = var_sub.add_parser("poll", help="Check a VaR job once, without blocking.")
    _add_common_args(var_poll)
    var_poll.add_argument("task_id")

    var_compute = var_sub.add_parser("compute", help="Submit and block until the job finishes.")
    _add_common_args(var_compute)
    _add_params_args(var_compute)
    var_compute.add_argument("--poll-interval", type=float, default=None, dest="poll_interval")
    var_compute.add_argument("--poll-timeout", type=float, default=None, dest="poll_timeout")

    return parser


def build_client(
    args: argparse.Namespace,
    *,
    client_factory: Callable[..., Client] = Client,
) -> Client:
    """Resolves credentials/base URL from flags or env vars and constructs a Client.

    Raises:
        ValueError: no API key was given by either --api-key or PYVAR_API_KEY --
            this is the one required credential, matching Client.__init__'s own
            check. Raised (not sys.exit) so main()'s single except block maps it
            to exit code 1 uniformly, same as any other bad-input case.
    """
    api_key = args.api_key or os.environ.get("PYVAR_API_KEY")
    if not api_key:
        raise ValueError("no API key -- pass --api-key or set PYVAR_API_KEY.")
    base_url = args.base_url or os.environ.get("PYVAR_BASE_URL") or DEFAULT_BASE_URL
    return client_factory(api_key=api_key, base_url=base_url, timeout=args.timeout)


def _load_params(args: argparse.Namespace) -> dict[str, Any] | None:
    """Loads --params/--params-json into a dict.

    Returns:
        None when neither flag was given -- the caller should print help for
        the target function instead of attempting a call that's certain to
        fail validation with zero fields.
    """
    if args.params_json is not None:
        parsed = json.loads(args.params_json)
    elif args.params is not None:
        if args.params == "-":
            parsed = json.loads(sys.stdin.read())
        else:
            with open(args.params, encoding="utf-8") as fh:
                parsed = json.load(fh)
    else:
        return None

    if not isinstance(parsed, dict):
        raise TypeError("--params/--params-json must be a JSON object of keyword arguments.")
    return parsed


def _print_function_help(namespace_cls: type, function_name: str) -> None:
    func = getattr(namespace_cls, function_name, None)
    if func is None or function_name.startswith("_") or not inspect.isfunction(func):
        raise ValueError(
            f"{function_name!r} is not a function on {namespace_cls.__name__}. "
            "Run list-functions to see what's available."
        )
    # eval_str=True resolves the string annotations `from __future__ import
    # annotations` leaves on every generated method back into real types
    # (int, not 'int') for display -- safe here since Any/dict/list are all
    # resolvable in the generated modules' own globals.
    signature = inspect.signature(func, eval_str=True)
    # Drop the leading `self` -- callers invoke this as
    # client.<domain>.<function>(...), not on the class directly.
    params = [p for name, p in signature.parameters.items() if name != "self"]
    print(f"{function_name}{signature.replace(parameters=params)}")
    print()
    print(inspect.getdoc(func) or "(no docstring)")


def _invoke(client: Client, domain: str, function: str, params: dict[str, Any]) -> Any:
    namespace = getattr(client, domain)
    func = getattr(namespace, function, None)
    if func is None or function.startswith("_") or not callable(func):
        valid = sorted(
            name
            for name, member in inspect.getmembers(namespace)
            if not name.startswith("_") and inspect.ismethod(member)
        )
        raise ValueError(f"{function!r} is not a function on {domain!r}. Available: {valid}")
    return func(**params)


def _run_var_command(client: Client, args: argparse.Namespace) -> Any:
    """Dispatches submit/poll/compute. Callers must check for the
    "no params given" case themselves before calling this for submit/compute
    (see main()) -- _load_params() returning None here would otherwise mean
    silently JSON-encoding a None result instead of showing help.
    """
    if args.var_command == "poll":
        return client.var.poll(args.task_id)

    params = _load_params(args)
    assert params is not None  # guaranteed by main()'s pre-check

    if args.var_command == "submit":
        return {"task_id": client.var.submit(**params)}

    if args.poll_interval is not None:
        params["poll_interval_seconds"] = args.poll_interval
    if args.poll_timeout is not None:
        params["poll_timeout_seconds"] = args.poll_timeout
    return client.var.compute(**params)


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[..., Client] = Client,
) -> int:
    """The `pyvar` entry point (see pyproject.toml's [project.scripts]).

    Never raises -- every error path is caught and mapped to an exit code
    (see module-level _EXIT_* constants), so this is safe to call as
    `sys.exit(main())` (which is exactly what the generated console-script
    wrapper does).
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "list-domains":
            for name in sorted(_NAMESPACE_CLASSES):
                print(name)
            return _EXIT_OK

        if args.command == "list-functions":
            namespace_cls = _NAMESPACE_CLASSES[args.domain]
            for name, member in inspect.getmembers(namespace_cls):
                if name.startswith("_") or not inspect.isfunction(member):
                    continue
                summary = (inspect.getdoc(member) or "").split("\n", 1)[0]
                print(f"{name} -- {summary}" if summary else name)
            return _EXIT_OK

        client = build_client(args, client_factory=client_factory)
        try:
            if args.command == "var":
                if args.var_command != "poll":
                    params_given = args.params is not None or args.params_json is not None
                    if not params_given:
                        _print_function_help(VarNamespace, args.var_command)
                        return _EXIT_OK
                result = _run_var_command(client, args)
            else:
                domain = args.command
                params = _load_params(args)
                if params is None:
                    _print_function_help(_NAMESPACE_CLASSES[domain], args.function)
                    return _EXIT_OK
                result = _invoke(client, domain, args.function, params)

            print(json.dumps(result, indent=None if args.compact else 2))
            return _EXIT_OK
        finally:
            client.close()

    except PyvarAuthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_AUTH_ERROR
    except PyvarValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        for item in exc.detail:
            print(f"  - {item}", file=sys.stderr)
        return _EXIT_VALIDATION_ERROR
    except PyvarRateLimitError as exc:
        print(f"error: {exc} (retry after {exc.retry_after}s)", file=sys.stderr)
        return _EXIT_RATE_LIMIT
    except (PyvarComputeError, PyvarTimeoutError) as exc:
        print(f"error: {exc} (task_id={exc.task_id})", file=sys.stderr)
        return _EXIT_COMPUTE_ERROR
    except PyvarError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    except (ValueError, TypeError, AttributeError, FileNotFoundError, json.JSONDecodeError) as exc:
        # TypeError covers func(**params) called with missing/unexpected
        # keyword arguments -- a client-side mistake caught before any HTTP
        # call is made, same "exit 1, clear message" treatment as the rest
        # of this group rather than an uncaught traceback.
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    except KeyboardInterrupt:
        return _EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())

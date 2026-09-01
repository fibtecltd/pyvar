"""pyvar_jupyter._dispatch -- resolves "domain.function" against a live Client.

Reasoning:
- No second copy of the domain->namespace mapping. pyvar_client/cli.py keeps
  its own _NAMESPACE_CLASSES table because the CLI needs list-domains/
  list-functions to work with zero API key (no Client instance to introspect
  yet). Magics always require a live, authenticated Client first (there's no
  offline mode here), so plain getattr(client, domain) already gives the
  right namespace -- a second hardcoded table here would just be one more
  place this could drift from _client.py's own __init__.
- Values are parsed with ast.literal_eval, falling back to the raw string on
  failure -- so `confidence_level=0.99`, `n_simulations=100000`, and
  `returns=[0.01,-0.02,0.015]` all parse as their real Python types on the
  %pyvar line-magic path, while a bare word like `method=historical` still
  works as a plain string.
- Tokenizing the line can't just be str.split()/shlex.split(): IPython's
  {expr} variable expansion (see _magics.py's own use of shell.var_expand)
  substitutes str(expr), and Python's own str() of a list puts a space
  after every comma ("[0.01, -0.02]") -- a naive whitespace split would
  chop that into two broken tokens. tokenize_key_value_line tracks
  bracket/quote depth instead, splitting only on whitespace that's outside
  every [...]/{...}/(...) and every quoted substring.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any

from pyvar_client import Client


class PyvarDispatchError(Exception):
    """Raised for a magic-invocation problem that isn't itself an API error --
    an unknown domain/function, or a bad key=value token."""


def resolve_function(client: Client, domain: str, function: str) -> Any:
    """getattr(client, domain) then getattr(namespace, function), with
    Pyvar-flavored error messages instead of a bare AttributeError."""
    namespace = getattr(client, domain, None)
    if namespace is None:
        available = ", ".join(_domain_names(client))
        raise PyvarDispatchError(f"Unknown domain {domain!r}. Available: {available}")

    func = getattr(namespace, function, None)
    if func is None or not callable(func):
        available = ", ".join(
            name for name, _ in inspect.getmembers(namespace, predicate=inspect.ismethod)
        )
        raise PyvarDispatchError(
            f"Unknown function {function!r} in domain {domain!r}. Available: {available}"
        )
    return func


def _domain_names(client: Client) -> list[str]:
    # Client.__init__ sets exactly two private attrs (_api_key, _http) and
    # one public attribute per domain namespace -- nothing else is public,
    # so this doesn't need its own hardcoded domain list either.
    return [name for name in vars(client) if not name.startswith("_")]


_OPEN_BRACKETS = "[{("
_CLOSE_BRACKETS = "]})"
_QUOTE_CHARS = "'\""


def tokenize_key_value_line(text: str) -> list[str]:
    """Split on whitespace, but only at bracket-depth 0 and outside quotes.

    "returns=[0.01, -0.02] portfolio_value=1000000" -> two tokens, not four
    -- see this module's own docstring for why a plain .split()/shlex.split()
    breaks on IPython's {expr} variable expansion.
    """
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    quote_char: str | None = None

    for char in text:
        if quote_char is not None:
            current.append(char)
            if char == quote_char:
                quote_char = None
            continue
        if char in _QUOTE_CHARS:
            quote_char = char
            current.append(char)
            continue
        if char in _OPEN_BRACKETS:
            depth += 1
            current.append(char)
            continue
        if char in _CLOSE_BRACKETS:
            depth = max(0, depth - 1)
            current.append(char)
            continue
        if char.isspace() and depth == 0:
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(char)

    if current:
        tokens.append("".join(current))
    return tokens


def parse_line_params(tokens: list[str]) -> dict[str, Any]:
    """Parse ["key=value", ...] tokens into a kwargs dict.

    Each value is run through ast.literal_eval first (so numbers, lists,
    dicts, booleans, None all parse as real Python types), falling back to
    the raw string if that fails -- the same "best-effort typed, string
    fallback" approach as pyvar_client/cli.py's own --params-json handling,
    just for the terser line-magic form.
    """
    params: dict[str, Any] = {}
    for token in tokens:
        if "=" not in token:
            raise PyvarDispatchError(f"Expected key=value, got {token!r}")
        key, _, raw_value = token.partition("=")
        key = key.strip()
        raw_value = raw_value.strip()
        try:
            params[key] = ast.literal_eval(raw_value)
        except (ValueError, SyntaxError):
            params[key] = raw_value
    return params


def format_signature(func: Any) -> str:
    """Docstring + signature for a domain function -- shown when a magic is
    called with no parameters, mirroring pyvar_client/cli.py's own
    no-params-supplied behavior (cheap discoverability, no doomed API call)."""
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        sig = None
    lines = []
    if sig is not None:
        lines.append(f"{func.__name__}{sig}")
    doc = inspect.getdoc(func)
    if doc:
        lines.append("")
        lines.append(doc)
    return "\n".join(lines) if lines else f"{func.__name__}(...)"

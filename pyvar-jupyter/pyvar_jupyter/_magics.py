"""pyvar_jupyter._magics -- %pyvar / %%pyvar / %pyvar_key / %pyvar_base_url.

Reasoning:
- One lazily-constructed Client per kernel session, not per call -- mirrors
  Client's own connection-pooling rationale (_client.py's module docstring):
  a fresh httpx.Client per magic invocation would throw that away every
  cell.
- The client is built from PYVAR_API_KEY / PYVAR_API_BASE_URL env vars if
  present (same variable names pyvar_client's own CLI and pyvar-mcp already
  use), so a key exported before `jupyter lab` just works with zero magics.
  %pyvar_key exists for the common case of pasting a key mid-session instead
  (e.g. a hosted notebook environment where env vars aren't convenient) --
  it is never written to disk or logged, only held in memory for this kernel.
- Cell body is JSON, not YAML -- matches pyvar_client/cli.py's own
  --params-json convention exactly (one params format across the CLI and
  notebook interfaces) and adds no new dependency for a "minimal" v1.
"""

from __future__ import annotations

import json
import os

from IPython.core.magic import Magics, line_cell_magic, line_magic, magics_class

from pyvar_client import Client
from pyvar_client._client import DEFAULT_BASE_URL
from pyvar_client.exceptions import PyvarError
from pyvar_jupyter._dispatch import (
    PyvarDispatchError,
    format_signature,
    parse_line_params,
    resolve_function,
    tokenize_key_value_line,
)
from pyvar_jupyter._display import PyvarResult


@magics_class
class PyvarMagics(Magics):
    def __init__(self, shell=None) -> None:
        super().__init__(shell)
        self._client: Client | None = None
        self._base_url: str = os.environ.get("PYVAR_API_BASE_URL", DEFAULT_BASE_URL)

    def _get_client(self) -> Client:
        if self._client is not None:
            return self._client
        api_key = os.environ.get("PYVAR_API_KEY")
        if not api_key:
            raise PyvarDispatchError(
                "No pyvar API key set. Run %pyvar_key <your-key>, or set the "
                "PYVAR_API_KEY environment variable before starting the kernel. "
                "Get a free-tier key at https://www.pyvar.com#get-api-key."
            )
        self._client = Client(api_key=api_key, base_url=self._base_url)
        return self._client

    @line_magic
    def pyvar_key(self, line: str) -> None:
        """%pyvar_key <token> -- set the API key for this kernel session
        (in-memory only, never written to disk)."""
        token = line.strip()
        if not token:
            print("Usage: %pyvar_key <your-api-key>")
            return
        os.environ["PYVAR_API_KEY"] = token
        self._client = None  # rebuild lazily with the new key on next call
        print("pyvar API key set for this session.")

    @line_magic
    def pyvar_base_url(self, line: str) -> None:
        """%pyvar_base_url <url> -- point at a non-production deployment
        (e.g. http://localhost:8000 or https://dev.pyvar.com) for this
        kernel session. Defaults to production."""
        url = line.strip()
        if not url:
            print(f"Current base URL: {self._base_url}")
            return
        self._base_url = url
        self._client = None  # rebuild lazily against the new base_url
        print(f"pyvar base URL set to {url!r} for this session.")

    @line_cell_magic
    def pyvar(self, line: str, cell: str | None = None) -> PyvarResult | None:
        """%pyvar <domain>.<function> [key=value ...]
        %%pyvar <domain>.<function>
        {"key": "value", ...}

        Line form: params as space-separated key=value tokens, e.g.
            %pyvar market_risk.monte_carlo_var returns=[0.01,-0.02,0.015] \\
                portfolio_value=1000000 confidence_level=0.99

        Cell form: params as a JSON object in the cell body -- use this over
        the line form when params are large or nested (arrays, nested
        objects). Called with no params (a bare line, or an empty cell),
        prints the function's docstring and signature instead of making a
        doomed API call with zero fields.
        """
        return self._invoke(line, cell_body=cell)

    def _invoke(self, line: str, *, cell_body: str | None) -> PyvarResult | None:
        # Standard IPython magic convention: {expr} in the magic line is
        # replaced with str(expr) evaluated in the caller's namespace, so
        # `%pyvar market_risk.historical_simulation_var returns={my_returns}
        # portfolio_value=1000000` works for a Python variable built earlier
        # in the notebook, not just literal values typed inline. Only the
        # line is expanded, not a cell-magic's JSON body -- str()'ing an
        # arbitrary Python value isn't guaranteed to produce valid JSON
        # (True/False/None vs true/false/null), so that combination isn't
        # promised to work and callers should build the JSON body itself
        # instead.
        if self.shell is not None:
            line = self.shell.var_expand(line, depth=1)
        target = line.strip()
        if not target:
            print("Usage: %pyvar <domain>.<function> [key=value ...]")
            return None

        parts = tokenize_key_value_line(target)
        domain_function = parts[0]
        if "." not in domain_function:
            print(f"Expected <domain>.<function>, got {domain_function!r}")
            return None
        domain, _, function = domain_function.partition(".")

        try:
            client = self._get_client()
            func = resolve_function(client, domain, function)

            if cell_body is not None:
                stripped = cell_body.strip()
                params = json.loads(stripped) if stripped else {}
                if not isinstance(params, dict):
                    print('Cell body must be a JSON object, e.g. {"portfolio_value": 1000000}')
                    return None
            else:
                params = parse_line_params(parts[1:])

            if not params:
                print(format_signature(func))
                return None

            result = func(**params)
            return PyvarResult(result)

        except json.JSONDecodeError as exc:
            print(f"Invalid JSON in cell body: {exc}")
        except PyvarDispatchError as exc:
            print(str(exc))
        except PyvarError as exc:
            status = f" (HTTP {exc.response_status})" if exc.response_status else ""
            print(f"pyvar API error{status}: {exc}")
        return None

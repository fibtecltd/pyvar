"""pyvar_jupyter._display -- wraps a pyvar API response for rich notebook output.

Reasoning:
- v1 scope is deliberately a clean HTML table, not the portal's KaTeX formula
  rendering (portal/pyvar.js's _renderFormula). That metadata lives in
  portal/functions.json server-side and isn't exposed through the REST API
  or pyvar_client today -- wiring it in here would mean either a second
  network call per result or embedding a copy of functions.json that can
  drift from the real one, the same duplication risk
  scripts/generate_mcp_tools.py's own docstring already flags for a
  different package. Left for a follow-up once that metadata has a real
  client-facing source.
- Every response value is html.escape()'d before going into the table --
  API responses can echo back parts of the request (e.g. a validation
  error's field values), so this follows the same "never trust API output
  in an HTML sink" rule portal/pyvar.js applies to its own innerHTML calls.
"""

from __future__ import annotations

import html
from typing import Any


class PyvarResult:
    """Wraps a dict result (or any value) from a pyvar_client call.

    Behaves like the underlying dict for normal Python use --
    result["var_abs"], result.get(...), iteration, etc. all work -- but
    Jupyter renders it as a formatted table instead of a raw dict repr when
    it's the last expression in a cell.
    """

    def __init__(self, data: Any) -> None:
        self.data = data

    def __repr__(self) -> str:
        return repr(self.data)

    def __getitem__(self, key: Any) -> Any:
        return self.data[key]

    def __contains__(self, key: Any) -> bool:
        return key in self.data

    def __iter__(self):
        return iter(self.data)

    def get(self, key: Any, default: Any = None) -> Any:
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        raise TypeError(f"{type(self.data).__name__} has no .get()")

    def _repr_html_(self) -> str:
        if isinstance(self.data, dict):
            return _dict_table(self.data)
        return f"<pre>{html.escape(repr(self.data))}</pre>"


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:,.6g}"
    if isinstance(value, dict):
        return _dict_table(value)
    if isinstance(value, (list, tuple)):
        if len(value) > 12:
            shown = ", ".join(_format_value(v) for v in value[:12])
            return f"[{shown}, ... +{len(value) - 12} more]"
        return "[" + ", ".join(_format_value(v) for v in value) + "]"
    return html.escape(str(value))


def _dict_table(data: dict[str, Any]) -> str:
    rows = "\n".join(
        f'<tr><td style="padding:2px 10px 2px 0;color:#666;'
        f'font-family:monospace">{html.escape(str(key))}</td>'
        f'<td style="padding:2px 0;font-family:monospace">{_format_value(value)}</td></tr>'
        for key, value in data.items()
    )
    return f'<table style="border-collapse:collapse">{rows}</table>'


def show(data: Any) -> PyvarResult:
    """Wrap any pyvar_client result for rich display -- usable standalone,
    not just via the %pyvar/%%pyvar magics (which already return a
    PyvarResult on their own)."""
    return PyvarResult(data)

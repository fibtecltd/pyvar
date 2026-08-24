"""pyvar_client — Python SDK for pyvar.com's REST API.

>>> from pyvar_client import Client
>>> client = Client(api_key="eyJ...")
>>> client.market_risk.historical_simulation_var(...)

See Client's own docstring for auth/usage, and pyvar_client._generated's
module docstring for how the 385 per-domain methods are produced.
"""

from __future__ import annotations

from pyvar_client._client import Client
from pyvar_client.exceptions import (
    PyvarAuthError,
    PyvarComputeError,
    PyvarError,
    PyvarRateLimitError,
    PyvarTimeoutError,
    PyvarValidationError,
)

__version__ = "0.1.1"

__all__ = [
    "Client",
    "PyvarAuthError",
    "PyvarComputeError",
    "PyvarError",
    "PyvarRateLimitError",
    "PyvarTimeoutError",
    "PyvarValidationError",
    "__version__",
]

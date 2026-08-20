"""pyvar_client._client — the Client entry point.

Reasoning:
- One Client, one httpx.Client (connection pooling/keep-alive reused
  across every call), one token. Per-domain namespaces
  (client.market_risk, client.credit_risk, ...) are generated from the
  live OpenAPI schema by codegen/generate.py -- see pyvar_client/
  _generated/'s own module docstring for what "generated" means here and
  why it isn't hand-maintained.
- Auth is a token the caller already has (register/verify is a one-time
  human step via the portal's email-verification flow -- POST
  /api/v1/auth/register + clicking the emailed link). This client has no
  register()/verify() methods and doesn't automate that flow.
- base_url defaults to prod. Point it at http://localhost:8000 for local
  dev against `uvicorn main:app --reload`, or https://dev.pyvar.com
  against the dev deployment.
"""

from __future__ import annotations

from types import TracebackType

import httpx

from pyvar_client._generated.alm import AlmNamespace
from pyvar_client._generated.credit_risk import CreditRiskNamespace
from pyvar_client._generated.derivatives import DerivativesNamespace
from pyvar_client._generated.liquidity import LiquidityNamespace
from pyvar_client._generated.market_risk import MarketRiskNamespace
from pyvar_client._generated.operational import OperationalNamespace
from pyvar_client._generated.portfolio import PortfolioNamespace
from pyvar_client._generated.regulatory import RegulatoryNamespace
from pyvar_client._transport import send_request
from pyvar_client._var import VarNamespace

DEFAULT_BASE_URL = "https://www.pyvar.com"
DEFAULT_TIMEOUT_SECONDS = 30.0


class Client:
    """pyvar.com API client.

    Example:
        >>> client = Client(api_key="eyJ...")
        >>> result = client.market_risk.historical_simulation_var(
        ...     returns=[...], portfolio_value=1_000_000, confidence_level=0.99,
        ... )
        >>> var_result = client.var.compute(
        ...     returns=[...], portfolio_value=1_000_000, n_simulations=100_000,
        ... )  # blocks: submits, polls, returns the finished VaRResult

    Args:
        api_key: Bearer JWT obtained via the portal's registration/
            verification flow. Required -- this client has no
            registration flow of its own.
        base_url: API base URL. Defaults to production.
        timeout: Per-request timeout in seconds, passed straight to httpx.
        transport: An httpx transport override. Not needed for real usage
            -- exists so tests can swap in an httpx.MockTransport instead
            of making real HTTP calls (see tests/conftest.py), the same
            "never hit a real service in tests" rule the main pyvar repo
            applies to AWS.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")

        self._api_key = api_key
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

        self.market_risk = MarketRiskNamespace(self)
        self.derivatives = DerivativesNamespace(self)
        self.credit_risk = CreditRiskNamespace(self)
        self.portfolio = PortfolioNamespace(self)
        self.operational_risk = OperationalNamespace(self)
        self.liquidity_risk = LiquidityNamespace(self)
        self.alm = AlmNamespace(self)
        self.regulatory = RegulatoryNamespace(self)
        self.var = VarNamespace(self)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        idempotent: bool = True,
    ) -> dict:
        return send_request(
            self._http,
            method,
            path,
            token=self._api_key,
            json_body=json_body,
            params=params,
            idempotent=idempotent,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

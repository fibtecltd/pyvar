"""tests/test_generated_methods.py — structural coverage across all 385
generated methods, not 385 hand-authored fixtures.

Reasoning:
- Hand-writing a fixture per generated method would be its own 385-entry
  maintenance burden -- exactly what codegen/generate.py exists to avoid
  for the methods themselves (see that script's module docstring). This
  test instead drives every entry in portal/functions.json generically:
  resolve the right namespace + method by name, call it with a dummy
  value for every declared parameter (structural only -- real values
  don't matter here, since the mock transport returns a canned response
  regardless of the request body; numerical correctness is the main
  repo's own engine test suite's job, not this client's), and assert the
  request hit the right path with every declared parameter present as a
  body key. Catches: a method missing entirely, a wrong HTTP path, a
  parameter silently dropped from the request body -- the class of bug
  codegen drift would actually produce.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import httpx
import pytest

from tests.conftest import make_client

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads((REPO_ROOT / "portal" / "functions.json").read_text())

_DOMAIN_TO_NAMESPACE_ATTR = {
    "alm": "alm",
    "credit-risk": "credit_risk",
    "derivatives": "derivatives",
    "liquidity": "liquidity_risk",
    "market-risk": "market_risk",
    "operational": "operational_risk",
    "portfolio": "portfolio",
    "regulatory": "regulatory",
}


@pytest.mark.parametrize("fn", CATALOG, ids=lambda fn: f"{fn['domain']}.{fn['name']}")
def test_generated_method_hits_correct_path_with_all_params(fn):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    client = make_client(handler)
    namespace = getattr(client, _DOMAIN_TO_NAMESPACE_ATTR[fn["domain"]])
    method = getattr(namespace, fn["name"])

    sig = inspect.signature(method)
    kwargs = {name: 1 for name in sig.parameters if name != "self"}
    method(**kwargs)

    assert captured["path"] == fn["path"]
    for param in fn["params"]:
        assert (
            param["name"] in captured["body"]
        ), f"{fn['domain']}.{fn['name']}: param {param['name']!r} missing from request body"


def test_every_catalog_domain_has_a_namespace_mapping():
    catalog_domains = {fn["domain"] for fn in CATALOG}
    assert catalog_domains == set(_DOMAIN_TO_NAMESPACE_ATTR)


def test_catalog_function_count_matches_generated_method_count():
    """Regression guard for the exact drift class this codegen exists to
    prevent (docs/p9-function-catalogue-reconciliation.md in the main
    repo) -- if portal/functions.json and the live OpenAPI schema ever
    disagree on count again, this fails loudly instead of silently
    shipping a stale client."""
    from pyvar_client._generated import (
        AlmNamespace,
        CreditRiskNamespace,
        DerivativesNamespace,
        LiquidityNamespace,
        MarketRiskNamespace,
        OperationalNamespace,
        PortfolioNamespace,
        RegulatoryNamespace,
    )

    def public_method_count(cls) -> int:
        return sum(
            1
            for name, member in vars(cls).items()
            if not name.startswith("_") and inspect.isfunction(member)
        )

    total_generated = sum(
        public_method_count(cls)
        for cls in (
            AlmNamespace,
            CreditRiskNamespace,
            DerivativesNamespace,
            LiquidityNamespace,
            MarketRiskNamespace,
            OperationalNamespace,
            PortfolioNamespace,
            RegulatoryNamespace,
        )
    )
    assert total_generated == len(CATALOG)

"""tests/test_client.py — Client construction and lifecycle."""

from __future__ import annotations

import pytest

from pyvar_client import Client


def test_requires_api_key():
    with pytest.raises(ValueError):
        Client(api_key="")


def test_context_manager_closes_http_client():
    with Client(api_key="test-token") as client:
        assert client._http.is_closed is False
    assert client._http.is_closed is True


def test_all_domain_namespaces_present():
    client = Client(api_key="test-token")
    for attr in (
        "market_risk",
        "derivatives",
        "credit_risk",
        "portfolio",
        "operational_risk",
        "liquidity_risk",
        "alm",
        "regulatory",
        "var",
    ):
        assert hasattr(client, attr), f"Client missing namespace: {attr}"

"""
tests/test_nonfinite_and_metrics.py — NaN/Infinity handling and /metrics labels

Reasoning:
- A NaN in a request body used to either crash the 422 renderer (500 on
  POST /var/compute) or sail through a domain route and come back as nulls with
  HTTP 200. Both must be a clean 422 that names the offending field.
- Every generated domain request model carries allow_inf_nan=False; the
  parametrised check keeps a regenerated schema from silently dropping it.
- /metrics must label requests with the route template (not "none").
"""

from __future__ import annotations

import importlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from api.errors import _json_safe
from api.middleware.auth import create_access_token
from ingestion.fixtures import generate_gbm_returns
from main import create_app

DOMAIN_SCHEMAS = [
    "alm",
    "credit_risk",
    "derivatives",
    "liquidity",
    "market_risk",
    "operational",
    "portfolio",
    "regulatory",
]
RETURNS = generate_gbm_returns(60, seed=5).tolist()


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.fixture
def headers():
    return {
        "Authorization": f"Bearer {create_access_token('tester', 'enterprise')}",
        "Content-Type": "application/json",
    }


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _body_with_nan(payload: dict) -> str:
    """JSON text whose first return is the bare token NaN (what json.loads accepts)."""
    return json.dumps(payload).replace(str(RETURNS[0]), "NaN", 1)


@pytest.mark.asyncio
async def test_var_compute_nan_is_422_not_500(app, headers):
    payload = {
        "portfolio_value": 1_000_000,
        "returns": RETURNS,
        "confidence_level": 0.99,
        "horizon_days": 1,
        "n_simulations": 5_000,
    }
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/var/compute", content=_body_with_nan(payload), headers=headers
        )
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"][:2] == ["body", "returns"]


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["NaN", "Infinity", '"nan"', '"-inf"'])
async def test_domain_route_rejects_non_finite(app, headers, token):
    # Bare NaN/Infinity tokens (json.loads accepts them) and the strings pydantic
    # would otherwise coerce to a float.
    raw = json.dumps({"returns": RETURNS, "portfolio_value": 1_000_000.0})
    raw = raw.replace(str(RETURNS[0]), token, 1)
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/market-risk/historical_simulation_var", content=raw, headers=headers
        )
    assert resp.status_code == 422, resp.text
    assert any(err["type"] == "finite_number" for err in resp.json()["detail"])


@pytest.mark.asyncio
async def test_finite_input_still_succeeds(app, headers):
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/market-risk/historical_simulation_var",
            json={"returns": RETURNS, "portfolio_value": 1_000_000.0},
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["var_abs"] > 0


def test_json_safe_renders_non_finite_floats():
    out = _json_safe({"a": float("nan"), "b": [float("inf"), -float("inf"), 1.5], "c": "x"})
    assert out == {"a": "NaN", "b": ["Infinity", "-Infinity", 1.5], "c": "x"}
    json.dumps(out, allow_nan=False)  # must not raise


def _request_models() -> list[tuple[str, type[BaseModel]]]:
    found = []
    for name in DOMAIN_SCHEMAS:
        module = importlib.import_module(f"schemas.{name}")
        for cls_name, cls in inspect.getmembers(module, inspect.isclass):
            if cls_name.endswith("Request") and issubclass(cls, BaseModel):
                if cls.__module__ == module.__name__:
                    found.append((f"{name}.{cls_name}", cls))
    return found


def test_all_385_domain_request_models_reject_non_finite():
    models = _request_models()
    assert len(models) == 385
    missing = [n for n, cls in models if cls.model_config.get("allow_inf_nan") is not False]
    assert not missing, missing[:5]


# Prometheus metrics register once per process and the instrumentation of the first
# create_app() wins, so this check runs in a fresh interpreter.
_METRICS_PROBE = """
import asyncio, logging
logging.disable(logging.CRITICAL)
from unittest.mock import patch
from httpx import ASGITransport, AsyncClient
from api.middleware.auth import create_access_token

async def main():
    with patch("sentry_sdk.init"):
        from main import create_app
        app = create_app()
    hdr = {"Authorization": "Bearer " + create_access_token("tester", "enterprise")}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/v1/credit-risk/expected_loss_el_computation",
                     json={"pd": 0.02, "lgd": 0.45, "ead": 1e6}, headers=hdr)
        text = (await c.get("/metrics")).text
    print("\\n".join(l for l in text.splitlines() if l.startswith("http_requests_total{")))

asyncio.run(main())
"""


def test_metrics_label_requests_with_the_route_template():
    path = "/api/v1/credit-risk/expected_loss_el_computation"
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-c", _METRICS_PROBE],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
        cwd=Path(__file__).resolve().parent.parent,
    ).stdout
    lines = out.splitlines()
    assert any(f'handler="{path}"' in ln for ln in lines), out
    assert not any('handler="none"' in ln for ln in lines), out

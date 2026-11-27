"""The asyncio Redis clients are given redis.asyncio.retry.Retry, the synchronous one keeps redis.retry.Retry.

Why: redis-py's asyncio client wants an asyncio Retry. Given the synchronous class it converts it and warns
("A synchronous redis.retry.Retry was passed to an asyncio client"), which the prod log showed once per process
(the trial-lane verification of 2026-11-27). The conversion keeps the backoff, the retry count and the error list, so
nothing was broken, but the older redis-py this repository still allows (requirements: redis>=5.0.3) does not convert
at all: a synchronous Retry on an asyncio client would be awaited wrongly on the first retry. The four asyncio builders
below now import the asyncio class.

The rate limiter is the other way round on purpose: slowapi hands storage_options to the `limits` library, whose Redis
storage is a SYNCHRONOUS client, so it must keep redis.retry.Retry. Changing it too would be the bug.
"""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path

import pytest
from redis.asyncio.retry import Retry as AsyncRetry
from redis.retry import Retry as SyncRetry

ROOT = Path(__file__).resolve().parent.parent

ASYNC_SITES = [
    "api/middleware/trial.py",
    "api/assistant/store.py",
    "api/routes/caching.py",
    "ingestion/market_data/cache.py",
]
SYNC_SITE = "api/middleware/rate_limit.py"


def _retry_import_modules(relative: str) -> list[str]:
    """The module each `from <module> import Retry` in the file names."""
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    return [
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and any(alias.name == "Retry" for alias in node.names)
    ]


@pytest.mark.parametrize("relative", ASYNC_SITES)
def test_an_asyncio_client_builder_imports_the_asyncio_retry(relative: str) -> None:
    assert _retry_import_modules(relative) == ["redis.asyncio.retry"]


def test_the_rate_limiter_keeps_the_synchronous_retry() -> None:
    assert _retry_import_modules(SYNC_SITE) == ["redis.retry"]


def _client_of_trial() -> object:
    return importlib.import_module("api.middleware.trial")._build_client()


def _client_of_assistant() -> object:
    return importlib.import_module("api.assistant.store")._build_client()


def _client_of_caching() -> object:
    module = importlib.import_module("api.routes.caching")
    module._redis_client = None
    return module._get_redis_client()


def _client_of_market_data() -> object:
    module = importlib.import_module("ingestion.market_data.cache")
    module._redis_client = None
    return module._get_redis_client()


BUILDERS = [
    pytest.param(_client_of_trial, id="trial"),
    pytest.param(_client_of_assistant, id="assistant-store"),
    pytest.param(_client_of_caching, id="route-cache"),
    pytest.param(_client_of_market_data, id="market-data-cache"),
]


@pytest.mark.parametrize("build", BUILDERS)
def test_building_the_client_raises_no_warning_and_keeps_an_asyncio_retry(build) -> None:
    """A warning is an error here. The caching builders swallow exceptions and answer None, so None fails too."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        client = build()
    assert client is not None
    retry = client.connection_pool.connection_kwargs["retry"]
    assert isinstance(retry, AsyncRetry)
    assert retry._retries == 2


def test_the_rate_limiters_storage_is_a_synchronous_client_that_takes_the_synchronous_retry() -> (
    None
):
    """tests/conftest.py swaps the module's limiter for an in-memory one, so build the same kind of storage here:
    slowapi -> limits -> a redis.client.Redis, with the very class rate_limit.py imports as Retry.
    """
    from redis.backoff import ExponentialBackoff
    from slowapi import Limiter

    rate_limit = importlib.import_module("api.middleware.rate_limit")
    assert rate_limit.Retry is SyncRetry
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        limiter = Limiter(
            key_func=lambda request: "k",
            storage_uri="redis://localhost:6379/0",
            storage_options={
                "retry": rate_limit.Retry(ExponentialBackoff(cap=0.2, base=0.02), retries=2)
            },
        )
    sync_client = limiter._storage.storage
    assert type(sync_client).__module__ == "redis.client"
    retry = sync_client.connection_pool.connection_kwargs["retry"]
    assert isinstance(retry, SyncRetry) and not isinstance(retry, AsyncRetry)

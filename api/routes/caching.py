"""
api/routes/caching.py — ElastiCache (Redis) result caching for async job endpoints

Reasoning:
- Identical requests (dashboards polling the same scenario, retried client
  calls) don't need a full Celery round-trip. Serving them from cache turns a
  1-10s job into a <200ms response.
- Cache key is SHA-256 of the canonical (sort_keys) JSON of the request body —
  deterministic regardless of dict insertion order.
- Reuses the same connection string as CELERY_RESULT_BACKEND
  (rediss://...&ssl_cert_reqs=CERT_NONE, injected by api_stack.py / P6 Task 4b
  pattern) rather than provisioning a second cache — same ElastiCache
  Serverless cluster, distinguished only by the "pyvar:{domain}:" key prefix.
- Reads/writes are best-effort: an ElastiCache outage must never break or slow
  a request — any Redis error (including the client being unavailable) is
  treated as a cache miss (fail open). Same philosophy as _emit_job_metric in
  tasks/var_task.py, whose CloudWatch namespace and IAM scope this module
  reuses directly rather than duplicating.
- The API task role's cloudwatch:PutMetricData grant (api_stack.py) is already
  scoped to the "pyvar" namespace with no resource restriction beyond that
  condition, so CacheHit/CacheMiss metrics need no new IAM grant.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel

from api.responses import OrjsonResponse
from config import get_settings
from schemas.var import JobResultResponse, JobStatus, VaRResult
from tasks.var_task import _emit_job_metric

cfg = get_settings()
logger = logging.getLogger(__name__)

_redis_client: Any = None  # lazily created — see _get_redis_client()

F = TypeVar("F", bound=Callable[..., Awaitable[OrjsonResponse]])


def _redis_url() -> str:
    """Same connection string Celery uses for CELERY_RESULT_BACKEND — reused, not duplicated.

    CELERY_RESULT_BACKEND's ssl_cert_reqs=CERT_NONE query param is written in
    Kombu's convention (kombu.utils.url.parse_ssl_cert_reqs accepts both
    "CERT_NONE" and "none"). redis.asyncio.from_url() does not coerce
    ssl_cert_reqs at all, and — despite kwargs normally overriding URL values —
    its own docs and code confirm querystring values win over explicit kwargs
    for from_url(), so passing the real enum as a kwarg is silently clobbered
    by this uppercase string. Rewriting the query param itself is the only
    fix: SSLConnection's CERT_REQS dict is lowercase-only ("none"/"optional"/
    "required"), so the uppercase string otherwise reaches it unchanged and
    raises RedisError("Invalid SSL Certificate Requirements Flag: CERT_NONE").
    """
    raw = os.environ.get("CELERY_RESULT_BACKEND", cfg.redis_url)
    parsed = urlsplit(raw)
    query = parse_qs(parsed.query)
    if "ssl_cert_reqs" in query:
        query["ssl_cert_reqs"] = [query["ssl_cert_reqs"][0].lower().removeprefix("cert_")]
        parsed = parsed._replace(query=urlencode(query, doseq=True))
    return urlunsplit(parsed)


def _get_redis_client() -> Any:
    """Lazily create the async Redis client. Returns None if redis is unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis

            _redis_client = aioredis.from_url(_redis_url(), decode_responses=True)
        except Exception:  # noqa: BLE001 — cache must never block a request
            logger.warning("Redis cache client unavailable — caching disabled for this call")
            return None
    return _redis_client


def _cache_key(domain: str, params: dict[str, Any]) -> str:
    """SHA-256 of the canonical (sort_keys) JSON of the request params."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"pyvar:{domain}:{digest}"


async def _cache_get(domain: str, params: dict[str, Any]) -> dict[str, Any] | None:
    client = _get_redis_client()
    if client is None:
        return None
    try:
        raw = await client.get(_cache_key(domain, params))
    except Exception:  # noqa: BLE001 — best-effort, never fail the request
        logger.exception("Cache read failed", extra={"domain": domain})
        return None
    return json.loads(raw) if raw is not None else None  # type: ignore[no-any-return]


async def _cache_set(domain: str, params: dict[str, Any], result: dict[str, Any]) -> None:
    client = _get_redis_client()
    if client is None:
        return
    try:
        await client.set(
            _cache_key(domain, params),
            json.dumps(result),
            ex=cfg.celery_result_ttl,
        )
    except Exception:  # noqa: BLE001 — best-effort, never fail the request
        logger.exception("Cache write failed", extra={"domain": domain})


def cache_check(domain: str) -> Callable[[F], F]:
    """Decorator for POST dispatch endpoints: serve a cached result if one exists.

    On cache hit, returns 200 with the cached result immediately, bypassing
    Celery entirely. On cache miss, calls the wrapped handler unchanged (the
    normal 202 + task_id dispatch). Looks up the decorated handler's `body`
    kwarg (the Pydantic request model FastAPI injects) to compute the key.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> OrjsonResponse:
            body = kwargs.get("body")
            if not isinstance(body, BaseModel):
                return await func(*args, **kwargs)

            params = body.model_dump(mode="json")
            cached = await _cache_get(domain, params)
            if cached is not None:
                _emit_job_metric("CacheHit", [{"Name": "Domain", "Value": domain}])
                return OrjsonResponse(
                    content=JobResultResponse(
                        task_id="cached",
                        status=JobStatus.SUCCESS,
                        result=VaRResult(**cached),
                    ).model_dump(),
                    status_code=200,
                )

            _emit_job_metric("CacheMiss", [{"Name": "Domain", "Value": domain}])
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


async def write_result_to_cache(
    domain: str, params: dict[str, Any], result: dict[str, Any]
) -> None:
    """Write a completed job result to cache, keyed on its original request params.

    Called from the GET .../result/{task_id} handler once a job reaches SUCCESS.
    Celery's result_extended=True keeps the original dispatch kwargs on the
    AsyncResult, so the caller can recompute the exact key used at dispatch time.
    """
    await _cache_set(domain, params, result)

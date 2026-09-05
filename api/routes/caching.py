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
  The URL-fixup logic itself lives in storage/redis_client.py — shared with
  api/middleware/rate_limit.py (#146), which hits the identical bug via the
  `limits` library's own redis.from_url() call.
- Reads/writes are best-effort: an ElastiCache outage must never break or slow
  a request — any Redis error (including the client being unavailable) is
  treated as a cache miss (fail open). Same philosophy as _emit_job_metric in
  tasks/var_task.py, whose CloudWatch namespace and IAM scope this module
  reuses directly rather than duplicating.
- The async client is a long-lived singleton (_redis_client), so pooled
  connections sit idle between requests — long enough that ElastiCache
  Serverless's proxy layer silently drops them, and the next command hits a
  bare ConnectionResetError on write (Sentry issue a5ebcb89, dev, 2026-09-03).
  health_check_interval PINGs idle connections before reuse so most of these
  are caught before they hit application code, and a short-capped retry (2
  attempts, <=0.2s backoff) absorbs the rest without violating the "never
  slow a request" rule above.
- That retry budget is intentionally tight, so it won't always win — the
  proxy's own reconnect can occasionally outlast it (Sentry issue 5d53be95,
  prod, 2026-09-04: same idle-drop as a5ebcb89, now seen in prod). That's
  still the designed fail-open path, not an outage, so _cache_get/_cache_set
  log it at warning (not exception) and emit a CacheReadError/CacheWriteError
  metric instead of letting logger.exception() page it into Sentry as an
  ERROR.
- The API task role's cloudwatch:PutMetricData grant (api_stack.py) is already
  scoped to the "pyvar" namespace with no resource restriction beyond that
  condition, so CacheHit/CacheMiss/CacheReadError/CacheWriteError metrics
  need no new IAM grant.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from api.responses import OrjsonResponse
from config import get_settings
from schemas.var import JobResultResponse, JobStatus, VaRResult
from storage.redis_client import redis_url
from storage.s3 import hydrate_presigned_url
from tasks.var_task import _emit_job_metric

cfg = get_settings()
logger = logging.getLogger(__name__)

_redis_client: Any = None  # lazily created — see _get_redis_client()

F = TypeVar("F", bound=Callable[..., Awaitable[OrjsonResponse]])


def _get_redis_client() -> Any:
    """Lazily create the async Redis client. Returns None if redis is unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            from redis.backoff import ExponentialBackoff
            from redis.exceptions import ConnectionError as RedisConnectionError
            from redis.exceptions import TimeoutError as RedisTimeoutError
            from redis.retry import Retry

            _redis_client = aioredis.from_url(
                redis_url(),
                decode_responses=True,
                socket_keepalive=True,
                health_check_interval=30,
                retry=Retry(ExponentialBackoff(cap=0.2, base=0.02), retries=2),
                retry_on_error=[RedisConnectionError, RedisTimeoutError],
            )
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
        # warning, not exception: ElastiCache Serverless idle-connection resets
        # (see module docstring) routinely outlast the 2-attempt retry budget —
        # this is the designed fail-open path, not an unhandled error, so it
        # must not page as a Sentry error. Sentry issue 5d53be95, prod,
        # 2026-09-04 was this exact handled path getting reported as ERROR.
        logger.warning("Cache read failed — treating as cache miss", extra={"domain": domain})
        _emit_job_metric("CacheReadError", [{"Name": "Domain", "Value": domain}])
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
        # warning, not exception — see matching comment in _cache_get above.
        logger.warning("Cache write failed — result not cached", extra={"domain": domain})
        _emit_job_metric("CacheWriteError", [{"Name": "Domain", "Value": domain}])


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
                # #130: cached results carry s3_key but never a baked-in
                # presigned_url (see write_result_to_cache's caller) — attach
                # a fresh one here, same as the live GET /var/result path.
                return OrjsonResponse(
                    content=JobResultResponse(
                        task_id="cached",
                        status=JobStatus.SUCCESS,
                        result=VaRResult(**hydrate_presigned_url(cached)),
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

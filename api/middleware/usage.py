"""
api/middleware/usage.py — async per-request usage telemetry

Reasoning:
- Records one api_usage row per compute request (domain, function, tier,
  duration, HTTP status) for the weekly usage analytics in
  observability/queries.sql.
- NON-BLOCKING by construction: the only work on the request hot path is two
  time.perf_counter() reads. Everything else — JWT decode for the tier, path
  parsing, and the DB INSERT — runs in a fire-and-forget asyncio task scheduled
  AFTER the response is produced, so it adds no latency the client can observe.
- A telemetry write must never affect the request: the background task swallows
  and logs any error (DB down, decode failure) rather than propagating it.
- Only /api/v1/* compute requests are tracked; /health, /metrics, /docs, etc.
  live outside that prefix and are skipped.

The tier is read from the JWT here (best-effort, in the background task) rather
than from the auth dependency: middleware runs around, not inside, the DI graph,
so the decoded TokenPayload is not available. A second HS256 decode is cheap and
happens off the hot path anyway.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from fastapi import Request, Response
from jose import jwt

from config import get_settings
from storage.models import ApiUsage
from storage.session import get_sessionmaker

cfg = get_settings()
logger = logging.getLogger(__name__)

# Keep strong references to in-flight background tasks so the event loop does not
# garbage-collect them mid-write (asyncio only holds weak refs to tasks).
_pending: set[asyncio.Task] = set()


def _should_track(path: str) -> bool:
    """Track only compute API calls (everything under the versioned prefix)."""
    prefix = cfg.api_v1_prefix
    return path.startswith(prefix) and path.rstrip("/") != prefix.rstrip("/")


def _parse_path(path: str) -> tuple[str, str]:
    """Derive (domain, function_name) from a request path.

    /api/v1/market-risk/expected-shortfall -> ("market-risk", "expected-shortfall")
    /api/v1/var/compute                     -> ("var", "compute")
    """
    rel = path[len(cfg.api_v1_prefix):].strip("/")
    parts = [p for p in rel.split("/") if p]
    if not parts:
        return "unknown", "unknown"
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], "/".join(parts[1:])


def _tier_from_auth(auth_header: str) -> str:
    """Best-effort tier extraction from the bearer JWT. 'unknown' on any failure."""
    if not auth_header.lower().startswith("bearer "):
        return "unknown"
    token = auth_header[7:].strip()
    try:
        payload = jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
        return str(payload.get("tier", "unknown"))
    except Exception:  # noqa: BLE001 — telemetry must not care why a token is unusable
        return "unknown"


async def _persist_usage(path: str, auth_header: str, status_code: int, duration_ms: int) -> None:
    """Insert one api_usage row. Best-effort: never raises into the caller."""
    try:
        domain, function_name = _parse_path(path)
        row = ApiUsage(
            domain=domain,
            function_name=function_name,
            tier=_tier_from_auth(auth_header),
            duration_ms=duration_ms,
            status=status_code,
        )
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            session.add(row)
            await session.commit()
    except Exception:  # noqa: BLE001 — a telemetry write must never affect requests
        logger.warning("api_usage write failed", extra={"path": path}, exc_info=False)


async def usage_tracking_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Measure the request, then schedule the usage insert off the hot path."""
    start = time.perf_counter()
    status_code = 500  # default if the handler raises before producing a response
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if _should_track(request.url.path):
            duration_ms = int((time.perf_counter() - start) * 1000)
            # Capture header now (request object may be consumed downstream); the
            # decode + DB write happen in the background task, not here.
            auth_header = request.headers.get("authorization", "")
            task = asyncio.create_task(
                _persist_usage(request.url.path, auth_header, status_code, duration_ms)
            )
            _pending.add(task)
            task.add_done_callback(_pending.discard)

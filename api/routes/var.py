"""
api/routes/var.py — VaR API endpoints

Reasoning:
- Two endpoints follow the async job pattern standard for long-running compute:
    POST /var/compute   → validates params, dispatches Celery task, returns task_id
    GET  /var/result/{task_id} → polls Redis result backend, returns status + result

- This pattern prevents HTTP timeouts for 100k-path simulations (1-10 seconds)
  and lets the frontend show real-time progress.

- The route enforces the user's simulation cap based on their JWT tier claim
  before dispatching — fail fast, before burning CPU.

- Monthly simulation-count cap, Pro only (item 5 §8 follow-on): a second,
  cumulative check via the SAME Redis-backed limiter api/middleware/
  rate_limit.py uses, scoped to VaR specifically since VaRJob is the only
  endpoint family with a per-user simulation-count record today — see
  config.py's rate_limit_pro_monthly_simulations comment. Breaching it hard-
  downgrades the account to Free (api/middleware/billing_lifecycle.py), the
  same reaction as rate_limit.py's monthly request-count cap, not a 429.

- Rate limiting (issue #146): POST /compute is covered by the SAME account-wide
  daily quota as every other compute endpoint, not a VaR-specific per-minute
  limit — enforced via api/middleware/rate_limit.py::enforce_compute_rate_limit,
  attached to this one route's `dependencies=` below (NOT at router-inclusion
  time in main.py, unlike the 8 domain routers) because this router also
  contains GET /result/{task_id}, a cheap result poll that must never share
  the same daily compute-dispatch quota. (This supersedes an earlier,
  never-implemented "10 requests/minute per user" claim that lived in this
  docstring — see #146's investigation for why a per-endpoint limit doesn't
  give the intended per-account quota across the 386 compute endpoints this
  app exposes.)

- The result endpoint returns the full VaRResult including the loss_dist array
  for jobs at or below cfg.s3_result_offload_threshold simulations. Above it
  (#130), tasks/var_task.py writes the full result to S3 instead, loss_dist
  here is empty, and presigned_url (storage/s3.py::hydrate_presigned_url,
  generated fresh on every poll) is populated instead.

- var_jobs audit write (issue #118): a `pending` VaRJob row is INSERTed here,
  synchronously, BEFORE the Celery task is dispatched — and if that insert
  fails, the request fails (503) without dispatching. This is deliberately
  NOT the api_usage fire-and-forget pattern: var_jobs is the regulatory audit
  log for every VaR computation (CLAUDE.md §3.3 — rows are never deleted,
  retained indefinitely for compliance), so "the compute ran but nothing was
  recorded" is the one outcome this write path exists to prevent. Once the
  row exists, the task_id is reused for apply_async so the row this endpoint
  created is the same row tasks/var_task.py updates on completion — task_id
  is the dedup key end to end, never a second INSERT.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import limits
import redis.asyncio as aioredis
from celery.result import AsyncResult
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jose import JWTError
from sqlalchemy import update
from starlette.concurrency import run_in_threadpool

from api.middleware import rate_limit as rate_limit_module
from api.middleware.auth import TokenPayload, decode_token_payload, get_current_user
from api.middleware.billing_lifecycle import (
    DOWNGRADE_MONTHLY_SIMULATION_LIMIT,
    EVENT_DOWNGRADED_MONTHLY_SIMULATION_LIMIT,
    downgrade_for_monthly_limit,
)
from api.middleware.rate_limit import enforce_compute_rate_limit
from api.responses import OrjsonResponse
from api.routes.caching import cache_check, write_result_to_cache
from config import get_settings
from schemas.var import JobResponse, JobResultResponse, JobStatus, VaRRequest, VaRResult
from storage.models import VaRJob
from storage.redis_client import redis_url
from storage.s3 import hydrate_presigned_url
from storage.session import get_sessionmaker
from tasks.var_task import celery_app, compute_var_task

cfg = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/var", tags=["VaR"])

# ── Scale-from-zero kickstart signal ────────────────────────────────────────────
# compute_stack.py's worker ASG scales from 0 -> 1 on this metric instead of raw
# SQS ApproximateNumberOfMessagesVisible. Root cause (Day -3 smoke test finding,
# task #38): SQS stops publishing ANY CloudWatch metric for a queue after 6+
# hours of zero activity, and delivery resumes with UP TO A 15-MINUTE LAG once
# activity resumes -- this is a platform-level behavior of SQS's own CloudWatch
# integration, not specific to one metric name (switching to e.g.
# NumberOfMessagesSent would hit the identical delay, since that metric is
# subject to the same "queue must be active" gating). A custom app-published
# metric has no such gating -- put_metric_data is always accepted immediately,
# regardless of how long the queue was idle -- so publishing this the instant a
# job is enqueued bypasses SQS's own metrics pipeline entirely for the 0->1
# kickstart specifically. The steady-state ScaleOnQueueDepth target-tracking
# policy is UNCHANGED and still reads the real queue depth -- that's correct
# once at least one instance is already running.
#
# Metric name has the environment baked in (job-submitted-{env}, matching
# compute_stack.py's existing worker-errors-{env} convention) rather than a
# CloudWatch dimension -- dev and prod share one AWS account/region, and the
# existing JobCount/JobErrors metrics (tasks/var_task.py) have no
# environment-distinguishing dimension at all, so they likely already conflate
# dev's and prod's counts into one time series. Not fixed here (separate,
# pre-existing gap), but deliberately not repeated for this new metric.
_SCALE_KICKSTART_METRIC_NAMESPACE = "pyvar"
_SCALE_KICKSTART_METRIC_NAME = f"job-submitted-{cfg.app_env}"
_cw_client = None  # lazily created; creation needs a region (set via env)


def _emit_scale_kickstart_metric() -> None:
    """Publish a single-count CloudWatch metric marking a job submission.

    Best-effort and fully isolated: must never fail or slow the actual
    /var/compute response, so every error — including lazy client creation —
    is swallowed with a warning. Same pattern as tasks/var_task.py's
    _emit_job_metric (worker side); duplicated rather than imported since
    that helper is worker-process-private (leading underscore) and this is a
    different process (API, not Celery worker) publishing a different signal.

    Only attempts the call when actually running in a real ECS task (same
    cfg.ecs_container_metadata_uri_v4 gate as observability/setup.py's
    _resolve_sentry_dsn(), for the identical reason: local dev and CI's test
    job must never attempt a real AWS call — CLAUDE.md/tests Rule 3).
    """
    if not cfg.ecs_container_metadata_uri_v4:
        return
    global _cw_client
    try:
        if _cw_client is None:
            import boto3

            _cw_client = boto3.client("cloudwatch")
        _cw_client.put_metric_data(
            Namespace=_SCALE_KICKSTART_METRIC_NAMESPACE,
            MetricData=[
                {
                    "MetricName": _SCALE_KICKSTART_METRIC_NAME,
                    "Value": 1.0,
                    "Unit": "Count",
                }
            ],
        )
    except Exception:  # noqa: BLE001 — metric emission must never break dispatch
        logger.warning("Failed to emit scale-from-zero kickstart metric")


# ── POST /var/compute ─────────────────────────────────────────────────────────


@router.post(
    "/compute",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a Monte Carlo VaR computation",
    description=(
        "Dispatches a VaR computation job to the Celery worker pool. "
        "Returns a task_id immediately. Poll GET /var/result/{task_id} for results. "
        "Identical requests (same params) may return 200 with a cached result instead."
    ),
    # Route-level, not router-level (main.py applies the same dependency to
    # the whole router for the 8 domain routers, which are POST-only) —
    # var_router also contains GET /result/{task_id}, a cheap result poll
    # that must never be throttled by the same daily compute-dispatch quota.
    dependencies=[Depends(enforce_compute_rate_limit)],
)
@cache_check(domain="var")
async def submit_var(
    request: Request,
    body: VaRRequest,
    user: TokenPayload = Depends(get_current_user),
) -> OrjsonResponse:

    # Enforce per-tier simulation cap (fail fast before queuing)
    if body.n_simulations > user.max_simulations:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Your {user.tier!r} tier allows a maximum of "
                f"{user.max_simulations:,} simulations. "
                f"Requested: {body.n_simulations:,}."
            ),
        )

    # Monthly simulation-count cap, Pro only (item 5 §8 follow-on). Scoped to
    # VaR specifically — see config.py's rate_limit_pro_monthly_simulations
    # comment for why this can't be enforced generically the way the
    # request-count cap is (api/middleware/rate_limit.py). Referenced via the
    # rate_limit module object, not `from ... import _limiter` directly, so
    # tests/conftest.py's autouse fixture (which patches
    # api.middleware.rate_limit._limiter) is picked up here too.
    if user.tier == "pro":
        sim_item = limits.parse(f"{cfg.rate_limit_pro_monthly_simulations}/month")
        try:
            sim_allowed = rate_limit_module._limiter.limiter.hit(
                sim_item, user.user_id, "var-simulations-monthly", cost=body.n_simulations
            )
        except Exception:  # noqa: BLE001 — fail open on a Redis outage
            logger.warning(
                "Rate limit storage unavailable for monthly simulation check — allowing request",
                exc_info=True,
            )
            sim_allowed = True

        if not sim_allowed:
            await downgrade_for_monthly_limit(
                user_id=user.user_id,
                downgrade_reason=DOWNGRADE_MONTHLY_SIMULATION_LIMIT,
                event_type=EVENT_DOWNGRADED_MONTHLY_SIMULATION_LIMIT,
                detail=(
                    f"Exceeded {cfg.rate_limit_pro_monthly_simulations:,} "
                    "simulations this billing period."
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Your Pro plan's monthly simulation limit has been "
                    "reached. Your account has moved to the Free plan for "
                    "the rest of this billing period; full Pro limits resume "
                    "automatically at your next billing date."
                ),
            )

    # Generated here (not left to Celery) so the same id ties together the audit
    # row below and the dispatched task — task_id is the var_jobs dedup key.
    task_id = str(uuid.uuid4())

    try:
        async with get_sessionmaker()() as session:
            session.add(
                VaRJob(
                    task_id=task_id,
                    user_id=user.user_id,
                    tier=user.tier,
                    status="pending",
                    portfolio_value=body.portfolio_value,
                    n_simulations=body.n_simulations,
                    confidence_level=body.confidence_level,
                    horizon_days=body.horizon_days,
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — surfaced as 503 below, not swallowed
        logger.error(
            "var_jobs audit insert failed — job NOT dispatched",
            extra={"task_id": task_id, "user_id": user.user_id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to record the audit log entry for this request. Please retry.",
        ) from exc

    # Dispatch to Celery — payload must be JSON-serialisable (list, not np.ndarray)
    try:
        task = compute_var_task.apply_async(
            kwargs={"payload": body.model_dump()},
            task_id=task_id,
        )
    except Exception as exc:  # noqa: BLE001 — the audit row already exists; compensate it
        logger.error(
            "Celery dispatch failed after var_jobs row was written",
            extra={"task_id": task_id, "user_id": user.user_id},
            exc_info=True,
        )
        try:
            async with get_sessionmaker()() as session:
                await session.execute(
                    update(VaRJob)
                    .where(VaRJob.task_id == task_id)
                    .values(
                        status="failure",
                        error_message="dispatch failed",
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
        except Exception:  # noqa: BLE001 — best-effort compensation, do not mask the 503
            logger.warning(
                "Failed to mark var_jobs row as failed after dispatch error",
                extra={"task_id": task_id},
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to queue the computation. Please retry.",
        ) from exc

    logger.info(
        "VaR job queued",
        extra={"task_id": task.id, "user_id": user.user_id, "n_sims": body.n_simulations},
    )
    _emit_scale_kickstart_metric()

    return OrjsonResponse(
        content=JobResponse(task_id=task.id).model_dump(),
        status_code=status.HTTP_202_ACCEPTED,
    )


# ── GET /var/result/{task_id} ─────────────────────────────────────────────────


def _read_celery_result(task_id: str) -> tuple[str, Any, dict[str, Any] | None]:
    """Blocking Celery/result-backend read — call via run_in_threadpool, never inline.

    AsyncResult.state/.result/.kwargs each hit the sync redis client (Celery has
    no async result backend). Sentry issue cdb4c0e5 (dev, 2026-09-03): a stalled
    write to a stale ElastiCache connection blocked this call for as long as the
    kernel's own TCP retransmission timeout, and because it ran straight in the
    event loop it froze every other in-flight request on the same worker, not
    just this one. tasks/var_task.py's celery_app socket tuning bounds how long
    that stall can now last; running the read in a thread here bounds the blast
    radius to this one request even if it still stalls the full 5s.
    """
    async_result = AsyncResult(task_id, app=celery_app)
    state = async_result.state
    raw_result = async_result.result if state in ("SUCCESS", "FAILURE") else None
    kwargs = async_result.kwargs if state == "SUCCESS" else None
    return state, raw_result, kwargs


async def _build_job_result_response(task_id: str) -> JobResultResponse:
    """Build the hydrated JobResultResponse for a task_id.

    Shared by GET /var/result/{task_id} and the WebSocket stream route below
    so both transports report from the same authoritative source (the Celery
    result backend) through identical hydration/caching logic — never
    duplicated in a way that could silently drift between the poll and push
    code paths.
    """
    state, raw_result, kwargs = await run_in_threadpool(_read_celery_result, task_id)

    # Map Celery states to our JobStatus enum
    status_map = {
        "PENDING": JobStatus.PENDING,
        "STARTED": JobStatus.STARTED,
        "SUCCESS": JobStatus.SUCCESS,
        "FAILURE": JobStatus.FAILURE,
        "RETRY": JobStatus.PENDING,
    }
    job_status = status_map.get(state, JobStatus.PENDING)

    result = None
    error = None

    if state == "SUCCESS":
        raw = raw_result
        payload = (kwargs or {}).get("payload")
        if isinstance(payload, dict):
            # Cache the canonical raw result (s3_key, no presigned_url) — the
            # cache-hit path in api/routes/caching.py generates its own fresh
            # presigned URL the same way this branch does below, rather than
            # caching one that could outlive its expiry.
            await write_result_to_cache("var", payload, raw)
        # #130: attaches a fresh presigned_url when raw carries an s3_key
        # (large-simulation offload) — a no-op otherwise.
        result = VaRResult(**hydrate_presigned_url(raw))

    elif state == "FAILURE":
        error = str(raw_result)

    return JobResultResponse(
        task_id=task_id,
        status=job_status,
        result=result if result else None,
        error=error,
    )


@router.get(
    "/result/{task_id}",
    response_model=JobResultResponse,
    summary="Poll for VaR computation result",
    description="Returns job status. When status=success, result contains the full VaR output.",
)
async def get_var_result(
    task_id: str,
    user: TokenPayload = Depends(get_current_user),
) -> OrjsonResponse:

    job_result = await _build_job_result_response(task_id)

    # CloudFront's ApiCachePolicy (edge_stack.py) clamps TTL using this header —
    # min_ttl=0/max_ttl=3600 — so PENDING/STARTED/FAILURE are never cached
    # (a still-running or failed job may change on the next poll) and only an
    # immutable SUCCESS result is eligible to be served from the edge cache.
    cache_control = "public, max-age=3600" if job_result.status == JobStatus.SUCCESS else "no-store"

    return OrjsonResponse(
        content=job_result.model_dump(),
        headers={"Cache-Control": cache_control},
    )


async def _send_if_terminal(websocket: WebSocket, task_id: str) -> bool:
    """Read the job's authoritative state; if it is terminal, push it and close the socket."""
    job_result = await _build_job_result_response(task_id)
    if job_result.status in (JobStatus.SUCCESS, JobStatus.FAILURE):
        await websocket.send_text(job_result.model_dump_json())
        await websocket.close()
        return True
    return False


# ── WS /var/stream/{task_id} ──────────────────────────────────────────────────


class _StreamSlots:
    """Open-socket budget of this process: one total cap, one cap per user.

    Counted per uvicorn worker process, not per task: the image runs two workers
    (Dockerfile), so a task holds up to twice the caps and, with N tasks, a user can hold
    2 x N times the per-user cap. Plain counters need no lock: acquire and release never await.
    """

    def __init__(self) -> None:
        self.active = 0
        self._by_user: dict[str, int] = {}

    def acquire(self, user_id: str) -> str | None:
        """Reserve a slot. Returns None on success, else the reason it was refused."""
        if self.active >= cfg.var_stream_max_connections:
            return "Too many open streams on this server"
        if self._by_user.get(user_id, 0) >= cfg.var_stream_max_connections_per_user:
            return "Too many open streams for this account"
        self.active += 1
        self._by_user[user_id] = self._by_user.get(user_id, 0) + 1
        return None

    def release(self, user_id: str) -> None:
        self.active -= 1
        remaining = self._by_user.get(user_id, 0) - 1
        if remaining > 0:
            self._by_user[user_id] = remaining
        else:
            self._by_user.pop(user_id, None)


_stream_slots = _StreamSlots()


# Every job's completion is published on its own channel (tasks/var_task.py). One
# pattern subscription per API process hears all of them and wakes the sockets that wait.
_JOB_DONE_PATTERN = "pyvar:var-job-done:*"


class _JobDoneBus:
    """One Redis Pub/Sub subscription per API process, shared by every waiting stream socket.

    Phase 0 on dev, then a local reproduction against a TLS Redis: a client and Pub/Sub
    subscription per socket cost about 1.7 MiB per socket (each Redis connection builds its own
    TLS context, 0.8 MiB) and 1.2 to 1.8 Redis connections per socket. A shared subscriber
    costs about 0.6 MiB per socket and no connection per socket.

    A message only wakes a waiter. Pub/Sub has no persistence, so the route still reads the
    authoritative state after every wake-up and on a timer, and `healthy` says whether that
    timer can be slow: while the subscriber is down the sockets poll at the old, short interval.
    """

    def __init__(self) -> None:
        self._waiters: dict[str, set[asyncio.Event]] = {}
        self._reader: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.healthy = False

    def register(self, task_id: str) -> asyncio.Event:
        """Start listening for `task_id`; call it BEFORE the first state read, so a completion
        between that read and the registration is not missed. Returns the event to wait on."""
        loop = asyncio.get_running_loop()
        if self._reader is None or self._reader.done() or self._loop is not loop:
            self.healthy = False
            self._loop = loop
            self._reader = loop.create_task(self._read_forever())
        event = asyncio.Event()
        self._waiters.setdefault(task_id, set()).add(event)
        return event

    def unregister(self, task_id: str, event: asyncio.Event) -> None:
        waiters = self._waiters.get(task_id)
        if waiters is not None:
            waiters.discard(event)
            if not waiters:
                del self._waiters[task_id]

    async def close(self) -> None:
        """Stop the subscriber (application shutdown)."""
        reader, self._reader = self._reader, None
        if reader is not None and not reader.done():
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader

    def _dispatch(self, message: dict[str, Any]) -> None:
        if message.get("type") != "pmessage":
            return
        channel = message["channel"]
        name = channel.decode() if isinstance(channel, bytes) else str(channel)
        for event in tuple(self._waiters.get(name.rsplit(":", 1)[-1], ())):
            event.set()

    async def _read_forever(self) -> None:
        backoff = 1.0
        while True:
            client: Any = None
            pubsub: Any = None
            try:
                client = aioredis.Redis.from_url(redis_url(), health_check_interval=30)
                pubsub = client.pubsub()
                await pubsub.psubscribe(_JOB_DONE_PATTERN)
                self.healthy = True
                backoff = 1.0
                async for message in pubsub.listen():
                    self._dispatch(message)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — Pub/Sub only speeds delivery up; sockets poll
                logger.warning(
                    "Shared job-done subscriber failed — streams poll until it is back",
                    exc_info=True,
                )
            finally:
                self.healthy = False
                for closable in (pubsub, client):
                    if closable is not None:
                        try:
                            await closable.aclose()
                        except Exception:  # noqa: BLE001 — best-effort cleanup only
                            logger.warning("Failed to close the job-done subscriber")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


_job_done_bus = _JobDoneBus()


async def close_job_done_bus() -> None:
    """Application shutdown hook (main.py lifespan)."""
    await _job_done_bus.close()


async def _wait_for_wake(event: asyncio.Event, timeout: float) -> bool:
    """Wait up to `timeout` for a push. True if one arrived (and is now consumed)."""
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return False
    event.clear()
    return True


async def _wait_for_disconnect(websocket: WebSocket) -> None:
    """Return once the client has gone, discarding anything it sends in the meantime.

    stream_var_result only sends, and Starlette reports a closed client only on a receive or a
    send, so without this reader a client that left was noticed when the 900 s wait ended and
    the final frame failed to send. Until then its handler kept polling Redis every poll
    interval and held its Redis connection and memory (135 abandoned sockets on dev: about
    4,000 reads a minute for 14 minutes, memory not released).
    """
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
    except (WebSocketDisconnect, RuntimeError):
        return


@router.websocket("/stream/{task_id}")
async def stream_var_result(websocket: WebSocket, task_id: str) -> None:
    """Push the VaR job result the instant it completes, instead of polling.

    Streaming job-completion push (docs/plan-streaming-realtime-pricing.md
    §3, shape #1) — same compute, same Monte Carlo kernel, just a different
    result-delivery transport than GET /var/result/{task_id}.

    Auth: the JWT travels as a ?token= query parameter, not the standard
    Authorization header — browser WebSocket clients cannot set arbitrary
    headers on the opening handshake, so this is the conventional pattern
    for token-authenticated WebSocket routes. Validated with the SAME
    decode_token_payload() get_current_user uses for every HTTP route, so
    the security boundary is identical either way.

    Authorization scope: deliberately mirrors GET /var/result/{task_id}
    exactly — any authenticated user who knows a task_id can stream its
    result, same as they can already poll it today. This route does not add
    a per-user ownership check the existing poll endpoint lacks; doing that
    for only one of the two transports would leave the same underlying
    resource with an inconsistent security model. Tightening both together
    is a separate decision, out of scope for this change.

    Reliability: waits on the shared Redis Pub/Sub subscription of this process
    (_JobDoneBus; tasks/var_task.py's _publish_job_event publishes on the channel) but never
    trusts it alone: Pub/Sub has no persistence or replay, so every wake-up, and a timer
    (cfg.var_stream_safety_poll_seconds while the subscriber is up, the shorter
    cfg.var_stream_poll_interval_seconds while it is not), re-reads the authoritative state via
    _build_job_result_response rather than trusting the message. The socket registers with the
    subscriber before its first state read, so a completion in between is not lost. A lost
    message therefore costs at most one timer interval, never a hung connection.
    A push can also arrive just before the result is stored (the worker publishes from inside
    the task, Celery stores after it returns), so after a push that still reads as pending the
    route re-checks cfg.var_stream_wake_recheck_count times, cfg.var_stream_wake_recheck_seconds
    apart, before it waits again.
    Bounded overall by cfg.var_stream_max_wait_seconds so a job that never
    reaches a terminal state cannot hold a worker slot open indefinitely.

    Resource limits: a waiting socket still costs memory, so the sockets that wait are capped
    per worker process and per user (cfg.var_stream_max_connections, ..._per_user; over a cap
    the route closes with 1013). A job that is already finished is answered before the cap applies. A reader
    task notices a client that has gone within one poll interval and ends the handler, which
    releases the slot and the Redis connection.
    """
    await websocket.accept()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")
        return
    try:
        user = decode_token_payload(token)
    except JWTError:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token"
        )
        return

    # Fast path: the job may already be terminal by the time the client connects.
    job_result = await _build_job_result_response(task_id)
    if job_result.status in (JobStatus.SUCCESS, JobStatus.FAILURE):
        await websocket.send_text(job_result.model_dump_json())
        await websocket.close()
        return

    refusal = _stream_slots.acquire(user.user_id)
    if refusal is not None:
        logger.warning(
            "VaR stream refused: open-stream cap reached",
            extra={"task_id": task_id, "reason": refusal, "open_streams": _stream_slots.active},
        )
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER, reason=refusal)
        return

    # Nothing between acquire() above and the try below may raise, or the slot leaks.
    disconnect_watcher = asyncio.create_task(_wait_for_disconnect(websocket))
    # Register before the state read below: a completion in between is then not lost.
    wake = _job_done_bus.register(task_id)
    try:
        if await _send_if_terminal(websocket, task_id):
            return

        deadline = time.monotonic() + cfg.var_stream_max_wait_seconds
        while time.monotonic() < deadline:
            if disconnect_watcher.done():
                logger.info("Client disconnected from VaR stream", extra={"task_id": task_id})
                return
            # The message itself is never trusted as the result — it only wakes this loop
            # promptly; _build_job_result_response below is the sole source of truth,
            # whether woken by a push or by this wait's own timeout (a plain poll tick).
            interval = (
                cfg.var_stream_safety_poll_seconds
                if _job_done_bus.healthy
                else cfg.var_stream_poll_interval_seconds
            )
            woken_by_push = await _wait_for_wake(wake, interval)

            if await _send_if_terminal(websocket, task_id):
                return
            if woken_by_push:
                # tasks/var_task.py publishes before the task returns, and Celery
                # stores the result only after that, so this read can lose the race
                # against the store. Re-check shortly rather than waiting a whole
                # poll interval (2.036 s measured on dev).
                for _ in range(cfg.var_stream_wake_recheck_count):
                    await asyncio.sleep(cfg.var_stream_wake_recheck_seconds)
                    if await _send_if_terminal(websocket, task_id):
                        return

        await websocket.send_text(
            JobResultResponse(
                task_id=task_id,
                status=JobStatus.PENDING,
                error=(
                    "Timed out waiting for job completion — the job may still be "
                    "running; poll GET /var/result/{task_id} to check."
                ),
            ).model_dump_json()
        )
        await websocket.close()
    except WebSocketDisconnect:
        logger.info("Client disconnected from VaR stream", extra={"task_id": task_id})
    finally:
        disconnect_watcher.cancel()
        _stream_slots.release(user.user_id)
        _job_done_bus.unregister(task_id, wake)

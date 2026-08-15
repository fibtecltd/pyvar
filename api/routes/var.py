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

import logging
import uuid
from datetime import datetime, timezone

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import update

from api.middleware.auth import TokenPayload, get_current_user
from api.middleware.rate_limit import enforce_compute_rate_limit
from api.responses import OrjsonResponse
from api.routes.caching import cache_check, write_result_to_cache
from config import get_settings
from schemas.var import JobResponse, JobResultResponse, JobStatus, VaRRequest, VaRResult
from storage.models import VaRJob
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

    async_result = AsyncResult(task_id, app=celery_app)
    state = async_result.state

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
        raw = async_result.result
        payload = (async_result.kwargs or {}).get("payload")
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
        error = str(async_result.result)

    # CloudFront's ApiCachePolicy (edge_stack.py) clamps TTL using this header —
    # min_ttl=0/max_ttl=3600 — so PENDING/STARTED/FAILURE are never cached
    # (a still-running or failed job may change on the next poll) and only an
    # immutable SUCCESS result is eligible to be served from the edge cache.
    cache_control = "public, max-age=3600" if job_status == JobStatus.SUCCESS else "no-store"

    return OrjsonResponse(
        content=JobResultResponse(
            task_id=task_id,
            status=job_status,
            result=result if result else None,
            error=error,
        ).model_dump(),
        headers={"Cache-Control": cache_control},
    )

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

- slowapi rate limiting (10 requests/minute per user) prevents abuse and
  controls Anthropic API cost exposure on the compute side.

- The result endpoint returns the full VaRResult including the loss_dist array.
  For very large n_simulations, consider returning a signed S3 URL instead
  (see storage/s3.py) and only returning scalar metrics inline.
"""

from __future__ import annotations

import logging

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.middleware.auth import TokenPayload, get_current_user
from api.responses import OrjsonResponse
from api.routes.caching import cache_check, write_result_to_cache
from schemas.var import JobResponse, JobResultResponse, JobStatus, VaRRequest, VaRResult
from tasks.var_task import celery_app, compute_var_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/var", tags=["VaR"])


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

    # Dispatch to Celery — payload must be JSON-serialisable (list, not np.ndarray)
    task = compute_var_task.apply_async(
        kwargs={"payload": body.model_dump()},
        task_id=None,  # auto-generate UUID
    )

    logger.info(
        "VaR job queued",
        extra={"task_id": task.id, "user_id": user.user_id, "n_sims": body.n_simulations},
    )

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
        result = VaRResult(**raw)
        payload = (async_result.kwargs or {}).get("payload")
        if isinstance(payload, dict):
            await write_result_to_cache("var", payload, raw)

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

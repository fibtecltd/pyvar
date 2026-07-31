"""
api/routes/internal.py — service-only ("internal" tier) endpoints.

Reasoning:
- Separate from api/routes/auth.py: that module's own docstring scopes it
  explicitly to "the minimum-viable human email -> verify -> JWT flow."
  This is the first service-to-service endpoint in the codebase (called by
  a Lambda, never by a human/browser) — a distinct file gives internal
  endpoints a home without touching auth.py's existing tests.
- Auth: reuses api/middleware/auth.py::get_current_user (the same JWT and
  jwt_secret every other authenticated route already trusts) plus an
  explicit tier check inline, rather than building a second auth mechanism.
  "internal" is already an established TokenPayload.tier value (minted by
  pyvar-cdk/lambda/public_data_publisher/handler.py's hand-rolled service
  JWT) and is already unconditionally exempt from rate limiting
  (api/middleware/rate_limit.py::_EXEMPT_TIERS) — this endpoint follows the
  same pattern, just also rejecting any non-internal tier outright since
  this one mutates account state rather than only reading it.
- No enforce_compute_rate_limit dependency: this isn't a compute endpoint,
  and "internal" tier is already exempt regardless.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from api.middleware.auth import TokenPayload, get_current_user
from schemas.internal import SuppressEmailRequest, SuppressEmailResponse
from storage.models import User
from storage.session import get_sessionmaker

router = APIRouter(prefix="/internal", tags=["Internal"])
logger = structlog.get_logger()


@router.post("/suppress-email", response_model=SuppressEmailResponse)
async def suppress_email(
    body: SuppressEmailRequest,
    user: TokenPayload = Depends(get_current_user),
) -> SuppressEmailResponse:
    """Flag a User row as suppressed (permanent bounce or complaint).

    Called only by pyvar-cdk/lambda/ses_suppression_handler/handler.py.
    Idempotent: suppressing an already-suppressed address just refreshes
    suppressed_at/suppression_reason and reports already_suppressed=True.
    """
    if user.tier != "internal":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Internal service callers only.")

    async with get_sessionmaker()() as session:
        existing = (
            await session.execute(select(User).where(User.email == body.email))
        ).scalar_one_or_none()

        if existing is None:
            logger.warning("suppress_email_no_matching_user", email=body.email, reason=body.reason)
            return SuppressEmailResponse(matched=False, already_suppressed=False)

        already_suppressed = existing.email_suppressed
        existing.email_suppressed = True
        existing.suppression_reason = body.reason
        existing.suppressed_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info(
        "email_suppressed",
        email=body.email,
        reason=body.reason,
        already_suppressed=already_suppressed,
    )
    return SuppressEmailResponse(matched=True, already_suppressed=already_suppressed)

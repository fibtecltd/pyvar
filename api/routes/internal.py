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
  (api/tiers.py (daily_requests is None)) — this endpoint follows the
  same pattern, just also rejecting any non-internal tier outright since
  this one mutates account state rather than only reading it.
- No enforce_compute_rate_limit dependency: this isn't a compute endpoint,
  and "internal" tier is already exempt regardless.
- The /internal/admin/education/* routes (docs/plan-education-tier.md) are the exception to the auth rule above:
  they take an ADMIN token (`aud` "pyvar-admin", 10 minutes, signed by scripts/education_grant.py), not a session
  JWT. A session JWT, an "internal" JWT, an API key and a stream token are all refused (require_admin_token), so
  holding any credential the API hands out is never enough to grant access. They are kept out of the public
  OpenAPI document. grant and extend answer 503 while `education_tier_enabled` is off; revoke, list and
  suspend-all always work (a way to end access must not depend on the flag).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from api import education_grants
from api.middleware.auth import AdminPayload, TokenPayload, get_current_user, require_admin_token
from config import get_settings
from observability.redact import email_domain
from schemas.internal import (
    EducationAccountOut,
    EducationChangeResponse,
    EducationExtendRequest,
    EducationGrantRequest,
    EducationListResponse,
    EducationRevokeRequest,
    EducationSuspendResponse,
    SuppressEmailRequest,
    SuppressEmailResponse,
    TokenReportResponse,
)
from storage.models import User
from storage.session import get_sessionmaker

router = APIRouter(prefix="/internal", tags=["Internal"])
logger = structlog.get_logger()
cfg = get_settings()


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
            logger.warning(
                "suppress_email_no_matching_user",
                email_domain=email_domain(body.email),
                reason=body.reason,
            )
            return SuppressEmailResponse(matched=False, already_suppressed=False)

        already_suppressed = existing.email_suppressed
        account_id = existing.external_id
        existing.email_suppressed = True
        existing.suppression_reason = body.reason
        existing.suppressed_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info(
        "email_suppressed",
        email_domain=email_domain(body.email),
        account_id=account_id,
        reason=body.reason,
        already_suppressed=already_suppressed,
    )
    return SuppressEmailResponse(matched=True, already_suppressed=already_suppressed)


@router.get("/token-report", response_model=TokenReportResponse)
async def token_report(
    user: TokenPayload = Depends(get_current_user),
) -> TokenReportResponse:
    """Daily/cumulative count of JWTs issued to users (verify() is the only
    real call site of create_access_token(), and it's single-use per user —
    see 0006_user_verified_at's migration docstring), for the scheduled
    pyvar-cdk/lambda/token_report_publisher email report.

    Cumulative is always exact (COUNT of email_verified=true). issued_today
    only reflects rows with a verified_at set today — rows verified before
    0006_user_verified_at was deployed have no recorded day and are excluded
    from issued_today (they're still counted in issued_cumulative).
    """
    if user.tier != "internal":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Internal service callers only.")

    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    async with get_sessionmaker()() as session:
        issued_today = (
            await session.execute(
                select(func.count())
                .select_from(User)
                .where(User.verified_at >= day_start, User.verified_at < day_end)
            )
        ).scalar_one_or_none() or 0

        issued_cumulative = (
            await session.execute(
                select(func.count()).select_from(User).where(User.email_verified.is_(True))
            )
        ).scalar_one_or_none() or 0

    return TokenReportResponse(
        env=cfg.app_env,
        date=day_start.date().isoformat(),
        issued_today=issued_today,
        issued_cumulative=issued_cumulative,
    )


# ── /internal/admin/education/* (admin token only) ────────────────────────────────────────────────────────


def _refuse(exc: education_grants.GrantRefused) -> HTTPException:
    return HTTPException(exc.status, exc.detail)


def _iso(moment: datetime | None) -> str | None:
    return moment.astimezone(timezone.utc).isoformat() if moment is not None else None


@router.post(
    "/admin/education/grant", response_model=EducationChangeResponse, include_in_schema=False
)
async def education_grant(
    body: EducationGrantRequest, admin: AdminPayload = Depends(require_admin_token)
) -> EducationChangeResponse:
    """Give a verified free account education access (a cohort and a per-domain cap apply)."""
    async with get_sessionmaker()() as session:
        try:
            expires = await education_grants.grant(
                session,
                email=body.email,
                months=body.months,
                cohort=body.cohort,
                allow_domain_over_cap=body.allow_domain_over_cap,
            )
        except education_grants.GrantRefused as exc:
            raise _refuse(exc) from exc
    logger.info("education_admin_grant", operator=admin.operator, cohort=body.cohort)
    return EducationChangeResponse(email=body.email, tier="education", expires_at=_iso(expires))


@router.post(
    "/admin/education/extend", response_model=EducationChangeResponse, include_in_schema=False
)
async def education_extend(
    body: EducationExtendRequest, admin: AdminPayload = Depends(require_admin_token)
) -> EducationChangeResponse:
    """Move an education account's end date out; at most 12 months from today."""
    async with get_sessionmaker()() as session:
        try:
            expires = await education_grants.extend(
                session,
                email=body.email,
                months=body.months,
                cohort=body.cohort,
                allow_domain_over_cap=body.allow_domain_over_cap,
            )
        except education_grants.GrantRefused as exc:
            raise _refuse(exc) from exc
    logger.info("education_admin_extend", operator=admin.operator, cohort=body.cohort)
    return EducationChangeResponse(email=body.email, tier="education", expires_at=_iso(expires))


@router.post(
    "/admin/education/revoke", response_model=EducationChangeResponse, include_in_schema=False
)
async def education_revoke(
    body: EducationRevokeRequest, admin: AdminPayload = Depends(require_admin_token)
) -> EducationChangeResponse:
    """End an education account's access now (back to the free tier)."""
    async with get_sessionmaker()() as session:
        try:
            await education_grants.revoke(session, email=body.email, cohort=body.cohort)
        except education_grants.GrantRefused as exc:
            raise _refuse(exc) from exc
    logger.info("education_admin_revoke", operator=admin.operator, cohort=body.cohort)
    return EducationChangeResponse(email=body.email, tier="free", expires_at=None)


@router.get("/admin/education/list", response_model=EducationListResponse, include_in_schema=False)
async def education_list(
    admin: AdminPayload = Depends(require_admin_token),
) -> EducationListResponse:
    """Every education account, active or run out, with its cohort label and end date."""
    async with get_sessionmaker()() as session:
        accounts = await education_grants.list_accounts(session)
    return EducationListResponse(
        active=sum(1 for a in accounts if a.active),
        cohort_cap=cfg.education_cohort_cap,
        domain_cap=cfg.education_domain_cap,
        enabled=cfg.education_tier_enabled,
        accounts=[
            EducationAccountOut(
                email=a.email, expires_at=_iso(a.expires_at), active=a.active, cohort=a.cohort
            )
            for a in accounts
        ],
    )


@router.post(
    "/admin/education/suspend-all", response_model=EducationSuspendResponse, include_in_schema=False
)
async def education_suspend_all(
    admin: AdminPayload = Depends(require_admin_token),
) -> EducationSuspendResponse:
    """The kill switch: end every active education grant now."""
    async with get_sessionmaker()() as session:
        count = await education_grants.suspend_all(session)
    logger.warning("education_admin_suspend_all", operator=admin.operator, accounts=count)
    return EducationSuspendResponse(suspended=count)

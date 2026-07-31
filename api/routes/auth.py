"""
api/routes/auth.py — minimum-viable account flow: email -> verify -> JWT

Reasoning:
- Minimum viable only (P8 Task 3 scope): no password, no login, no key
  rotation, no account dashboard beyond the one-time JWT display. Anything
  past that is a tracked follow-up (see module-level TODOs below), not
  built here.
- Verification email delivery (#149): real SES send via get_ses_client(),
  now that pyvar.com's DNS decision (P8 Task 7 / #158) is resolved — Aruba
  stays, and pyvar-cdk/stacks/ses_stack.py verifies the pyvar.com domain
  identity via DKIM. Note this identity starts in SES *sandbox* mode (the
  AWS default for new accounts/regions): only individually pre-verified
  recipient addresses can receive mail until an operator requests
  production access via an AWS Support case — a console/account-level
  action, not something this codebase or CDK can do. send_verification_email
  falls back to the original log-only stub if the SES call itself fails
  (sandbox rejection, no credentials in local dev, transient SES error) —
  see its own docstring for why that's deliberately non-fatal.
- Registering an already-registered-but-unverified email regenerates the
  token (handles a lost/expired first email) instead of erroring; an
  already-VERIFIED email is a no-op. Both return the identical response —
  the endpoint never reveals whether an address is registered.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from api.middleware.auth import create_access_token
from config import get_settings
from schemas.auth import RegisterRequest, RegisterResponse, VerifyResponse
from storage.models import User
from storage.session import get_sessionmaker

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = structlog.get_logger()
cfg = get_settings()


def get_ses_client() -> Any:
    """Build the boto3 SES client used to send verification email (#149).

    A one-off inline builder, not a shared module like storage/redis_client.py
    — this is the only caller, unlike the Redis URL fixup shared by
    api/routes/caching.py and api/middleware/rate_limit.py.
    """
    return boto3.client("ses", region_name=cfg.ses_region)


def send_verification_email(email: str, token: str) -> None:
    """Send the verification link via SES (#149); log-only fallback on failure.

    Links to dashboard.html?token=... (portal/dashboard.html, served by this
    same app at cfg.public_base_url — see fix/portal-root-serving), not the
    raw GET /auth/verify API route: a human clicking an email link should
    land on a page, not a bare JSON response. dashboard.html's own JS is what
    calls GET /auth/verify.

    Failure here is deliberately non-fatal: register() below calls this
    AFTER the user row is already committed, so raising would turn a
    successful registration into a confusing 500 for the caller without
    undoing anything. Falling back to the same log line the original stub
    always emitted keeps the token recoverable from CloudWatch — e.g. in
    local dev with no real AWS credentials, or while the SES identity is
    still in sandbox mode and the recipient isn't pre-verified.
    """
    verify_url = f"{cfg.public_base_url}/dashboard.html?token={token}"

    try:
        get_ses_client().send_email(
            Source=cfg.ses_sender_email,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": "Confirm your pyvar.com account"},
                "Body": {
                    "Text": {
                        "Data": (
                            "Confirm your pyvar.com account by visiting the link below.\n\n"
                            f"{verify_url}\n\n"
                            f"This link expires in {cfg.verification_token_expiry_minutes} "
                            "minutes."
                        )
                    }
                },
            },
        )
        logger.info("verification_email_sent", email=email)
    except Exception:  # noqa: BLE001 — best-effort send, see docstring for why
        logger.error(
            "verification_email_send_failed",
            email=email,
            token=token,
            verify_url=verify_url,
            exc_info=True,
        )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_202_ACCEPTED)
async def register(body: RegisterRequest) -> RegisterResponse:
    """Register an email; a verification token is issued (see send_verification_email)."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)

    async with get_sessionmaker()() as session:
        existing = (
            await session.execute(select(User).where(User.email == str(body.email)))
        ).scalar_one_or_none()

        if existing is not None and existing.email_verified:
            # Already active — never rotate a live account's token, never re-send.
            return RegisterResponse()

        if existing is not None and existing.email_suppressed:
            # Permanent bounce or complaint on record (api/routes/internal.py) —
            # SES's own account-level suppression list would already refuse this
            # send, but skip before touching the token fields at all rather than
            # relying on that silently. Same response shape as every other
            # branch: never reveal suppression state to the caller.
            logger.warning(
                "registration_skipped_suppressed_email",
                email=str(body.email),
                reason=existing.suppression_reason,
            )
            return RegisterResponse()

        if existing is not None:
            existing.verification_token = token
            existing.verification_sent_at = now
        else:
            session.add(
                User(
                    external_id=str(uuid.uuid4()),
                    email=str(body.email),
                    verification_token=token,
                    verification_sent_at=now,
                )
            )
        await session.commit()

    send_verification_email(str(body.email), token)
    return RegisterResponse()


@router.get("/verify", response_model=VerifyResponse)
async def verify(token: str) -> VerifyResponse:
    """Confirm a verification token and issue a free-tier JWT — shown once."""
    now = datetime.now(timezone.utc)
    expiry_cutoff = now - timedelta(minutes=cfg.verification_token_expiry_minutes)

    async with get_sessionmaker()() as session:
        user = (
            await session.execute(select(User).where(User.verification_token == token))
        ).scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Invalid or already-used verification link.",
            )
        if user.verification_sent_at is None or user.verification_sent_at < expiry_cutoff:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Verification link expired — register again.",
            )

        user.email_verified = True
        user.verification_token = None
        external_id = user.external_id
        tier = user.tier
        await session.commit()

    access_token = create_access_token(user_id=external_id, tier=tier)
    return VerifyResponse(access_token=access_token, tier=tier)

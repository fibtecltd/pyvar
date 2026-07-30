"""
api/routes/auth.py — minimum-viable account flow: email -> verify -> JWT

Reasoning:
- Minimum viable only (P8 Task 3 scope): no password, no login, no key
  rotation, no account dashboard beyond the one-time JWT display. Anything
  past that is a tracked follow-up (see module-level TODOs below), not
  built here.
- Verification email delivery has no real transport: no SES, no SMTP,
  anywhere in this codebase (confirmed by an exhaustive grep before writing
  this). Real delivery also needs a DNS-verified sending domain, which
  depends on P8 Task 7's pyvar.com DNS decision — deliberately deferred,
  high-risk, gated on operator confirmation at every step. Building SES
  sandbox-only sending now would only work for individually AWS-pre-verified
  recipients, which is unusable for a public registration flow. See #149 for
  the tracked follow-up once Task 7 lands. send_verification_email() is the
  single seam to change then — everything around it (token issuance,
  expiry, DB state, JWT minting) is real today.
- Registering an already-registered-but-unverified email regenerates the
  token (handles a lost/expired first email) instead of erroring; an
  already-VERIFIED email is a no-op. Both return the identical response —
  the endpoint never reveals whether an address is registered.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

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


def send_verification_email(email: str, token: str) -> None:
    """Verification email transport — see module docstring for why this is a stub.

    Logs a dashboard.html link rather than sending real email (no SES/SMTP
    transport exists yet, see #149). The portal is now served by this same
    app (fix/portal-root-serving), at cfg.public_base_url, so dashboard.html
    is a real reachable page rather than a URL that would 404.
    """
    logger.info(
        "verification_email_stubbed",
        email=email,
        token=token,
        verify_url=f"{cfg.public_base_url}/dashboard.html?token={token}",
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

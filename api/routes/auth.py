"""
api/routes/auth.py — minimum-viable account flow: email -> verify -> JWT

Reasoning:
- Minimum viable only (P8 Task 3 scope): no password, no login, no key
  rotation, no account dashboard beyond the one-time JWT display. Anything
  past that is a tracked follow-up, not built here.
- Verification email delivery (#149): real SES send via get_ses_client(),
  now that pyvar.com's DNS decision (P8 Task 7 / #158) is resolved — Aruba
  stays, and pyvar-cdk/stacks/ses_stack.py verifies the pyvar.com domain
  identity via DKIM. This identity started in SES *sandbox* mode (the AWS
  default for new accounts/regions: only individually pre-verified recipient
  addresses can receive mail) until AWS approved production access (2026-08)
  — sends to any recipient now succeed. send_verification_email falls back
  to the original log-only stub if the SES call itself fails (no credentials
  in local dev, a transient SES error, or a suppressed/bounced recipient) —
  see its own docstring for why that's deliberately non-fatal.
- Registering an already-registered-but-unverified email regenerates the
  token (handles a lost/expired first email) instead of erroring; an
  already-VERIFIED email is a no-op. Both return the identical response —
  the endpoint never reveals whether an address is registered.
- Anti-abuse: register() previously had no throttling and no domain check
  at all. It now rejects known disposable/throwaway domains (see
  api/middleware/disposable_email.py's own docstring for why this is
  scoped to throwaway providers specifically, not personal-looking domains
  like gmail.com) before touching the DB or SES, and is rate-limited
  per-IP (api/middleware/rate_limit.py::enforce_register_rate_limit) —
  both close a real gap: an attacker could otherwise spam SES sends or
  probe the blocklist without limit.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select

from api.middleware.auth import create_access_token
from api.middleware.disposable_email import is_disposable_email
from api.middleware.rate_limit import enforce_register_rate_limit
from config import get_settings
from schemas.auth import GoogleSignInRequest, RegisterRequest, RegisterResponse, VerifyResponse
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
    local dev with no real AWS credentials, or if SES itself rejects the
    send (a suppressed/bounced recipient, a transient SES error).
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
        if cfg.app_env == "development":
            # Dev-only: no real AWS/SES credentials locally, so this is the
            # only way to recover the token for manual testing (the exact
            # case this function's own docstring describes). Never do this
            # outside development — see the redacted branch below.
            logger.error(
                "verification_email_send_failed",
                email=email,
                token=token,
                verify_url=verify_url,
                exc_info=True,
            )
        else:
            # staging/production: never log a live bearer credential in
            # clear text — whoever can read these logs (CloudWatch access
            # is broader than "trusted operators only" for a real
            # customer-facing service, and logs can be shipped to
            # third-party aggregators) could otherwise complete email
            # verification for this account without owning the inbox. The
            # token is still recoverable from the `users` table's
            # verification_token column for legitimate manual recovery,
            # without duplicating a working secret into logs.
            logger.error("verification_email_send_failed", email=email, exc_info=True)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_register_rate_limit)],
)
async def register(body: RegisterRequest) -> RegisterResponse:
    """Register an email; a verification token is issued (see send_verification_email)."""
    if is_disposable_email(str(body.email)):
        # Same response shape as every other branch below — never reveal
        # *why* a registration didn't go through, so the blocklist itself
        # can't be probed/fingerprinted from the outside. No DB write, no
        # SES send: this domain never reaches either.
        logger.warning("registration_skipped_disposable_email", email=str(body.email))
        return RegisterResponse()

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
        user.verified_at = now
        external_id = user.external_id
        tier = user.tier
        await session.commit()

    access_token = create_access_token(user_id=external_id, tier=tier)
    return VerifyResponse(access_token=access_token, tier=tier)


# ── POST /auth/google ──────────────────────────────────────────────────────────


def _verify_google_id_token(raw_token: str) -> dict[str, Any]:
    """Verify a Google ID token's signature, issuer, audience, and expiry.

    A thin wrapper around google-auth's own verifier (not re-implemented here)
    so tests patch this one call site instead of mocking google.oauth2.id_token
    directly. Raises ValueError — google-auth's own exception type for every
    invalid-token case (bad signature, expired, wrong audience, wrong issuer) —
    on any verification failure; callers translate that into a 401, never a 500.

    Args:
        raw_token: the raw ID token JWT string from the frontend.

    Returns:
        The verified token's decoded claims (sub, email, email_verified, ...).
    """
    claims: dict[str, Any] = google_id_token.verify_oauth2_token(
        raw_token, google_requests.Request(), cfg.google_oauth_client_id
    )
    return claims


@router.post(
    "/google",
    response_model=VerifyResponse,
    dependencies=[Depends(enforce_register_rate_limit)],
)
async def google_sign_in(body: GoogleSignInRequest) -> VerifyResponse:
    """Sign in (or register) with a verified Google ID token.

    Google already cryptographically verifies the caller owns this email
    (the email_verified claim, checked again defensively below) — so unlike
    POST /auth/register, this path never runs is_disposable_email's
    blocklist (that check exists to stop a throwaway address from burning
    an SES send on a verification link that's never clicked; there is no
    such link here) and never needs the SES round-trip at all. A new
    account created via this path is already verified.

    Linking, not a second signup path for an existing address:
    storage.models.User.email already carries a unique constraint, so a
    Google sign-in for an email that already has a pyvar account just
    looks that row up and issues it a fresh JWT — same external_id, same
    tier, same usage history. Only a genuinely new email creates a new row.
    """
    if not cfg.google_oauth_client_id:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google sign-in is not configured.",
        )

    try:
        claims = _verify_google_id_token(body.id_token)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired Google sign-in token.",
        ) from exc

    email = str(claims.get("email", "")).strip().lower()
    if not email or not claims.get("email_verified"):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Google did not report a verified email address for this account.",
        )

    now = datetime.now(timezone.utc)

    async with get_sessionmaker()() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()

        if user is None:
            # external_id finally gets a real external-identity-provider value
            # here — storage/models.py's own docstring has documented this as
            # its intent since before any provider existed. "google:{sub}"
            # rather than Google's bare sub, so a future second provider
            # (e.g. Apple) can't collide on a numeric id another provider
            # happens to reuse.
            user = User(
                external_id=f"google:{claims['sub']}",
                email=email,
                tier="free",
                email_verified=True,
                verified_at=now,
            )
            session.add(user)
        elif not user.email_verified:
            # Existing row from an unfinished POST /auth/register — Google's
            # verification is at least as strong as SES's link click, so
            # finish what register() started rather than leaving this
            # account stuck pending forever.
            user.email_verified = True
            user.verified_at = now
            user.verification_token = None

        await session.commit()
        external_id = user.external_id
        tier = user.tier

    access_token = create_access_token(user_id=external_id, tier=tier)
    return VerifyResponse(access_token=access_token, tier=tier)

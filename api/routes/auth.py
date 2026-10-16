"""
api/routes/auth.py — minimum-viable account flow: email -> verify -> JWT

Reasoning:
- Started as minimum viable (P8 Task 3): no password, no login, no key
  rotation. That left a free "API key" that was a 60-minute JWT shown once and
  could not be re-issued by email, so plugin users were locked out an hour after
  installing. docs/plan-durable-api-keys.md added, still without passwords:
    * the register form doubles as sign-in: an already-verified address gets a
      short-lived single-use sign-in link (same response as every other outcome);
    * a signed-in SESSION (the 60-minute JWT) can create, list and revoke durable
      API keys (POST/GET/DELETE /auth/api-keys); the key is what a plugin holds.
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
  already-VERIFIED email gets a sign-in link (at most one per
  cfg.signin_link_min_interval_seconds, valid cfg.signin_link_expiry_minutes).
  Every outcome returns the identical response — the endpoint never reveals
  whether an address is registered.
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
from fastapi import APIRouter, Depends, HTTPException, Response, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select

from api.middleware.api_keys import generate_key, invalidate_cached_key
from api.middleware.auth import TokenPayload, create_access_token, require_session
from api.middleware.disposable_email import is_disposable_email
from api.middleware.rate_limit import enforce_register_rate_limit
from config import get_settings
from schemas.auth import (
    ApiKeyCreated,
    ApiKeyInfo,
    ApiKeyList,
    CreateApiKeyRequest,
    GoogleSignInRequest,
    RegisterRequest,
    RegisterResponse,
    VerifyResponse,
)
from storage.models import ApiKey, User
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


def send_verification_email(email: str, token: str, *, signin: bool = False) -> None:
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

    if signin:
        subject = "Sign in to pyvar.com"
        body = (
            "Use the link below to sign in to pyvar.com and manage your API keys.\n\n"
            f"{verify_url}\n\n"
            f"This link works once and expires in {cfg.signin_link_expiry_minutes} minutes. "
            "If you did not ask to sign in, you can ignore this email."
        )
    else:
        subject = "Confirm your pyvar.com account"
        body = (
            "Confirm your pyvar.com account by visiting the link below.\n\n"
            f"{verify_url}\n\n"
            f"This link expires in {cfg.verification_token_expiry_minutes} minutes."
        )

    try:
        get_ses_client().send_email(
            Source=cfg.ses_sender_email,
            Destination={"ToAddresses": [email]},
            Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}},
        )
        logger.info("verification_email_sent", email=email, signin=signin)
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
    """Register an email, or sign in with it: either way a link is emailed (see send_verification_email)."""
    if is_disposable_email(str(body.email)):
        # Same response shape as every other branch below — never reveal
        # *why* a registration didn't go through, so the blocklist itself
        # can't be probed/fingerprinted from the outside. No DB write, no
        # SES send: this domain never reaches either.
        logger.warning("registration_skipped_disposable_email", email=str(body.email))
        return RegisterResponse()

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    signin = False

    async with get_sessionmaker()() as session:
        existing = (
            await session.execute(select(User).where(User.email == str(body.email)))
        ).scalar_one_or_none()

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

        if existing is not None and existing.email_verified:
            # A returning user asking to sign in. Throttle per address (the per-IP limit
            # alone would let one caller flood a victim's inbox from many IPs), and keep
            # the link single-use and short-lived (verify() applies the shorter expiry).
            last_sent = existing.verification_sent_at
            if last_sent is not None and last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            if (
                last_sent is not None
                and (now - last_sent).total_seconds() < cfg.signin_link_min_interval_seconds
            ):
                return RegisterResponse()
            existing.verification_token = token
            existing.verification_sent_at = now
            signin = True
        elif existing is not None:
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

    send_verification_email(str(body.email), token, signin=signin)
    return RegisterResponse()


@router.get("/verify", response_model=VerifyResponse)
async def verify(token: str) -> VerifyResponse:
    """Confirm a link token and issue a 60-minute session JWT (for managing API keys)."""
    now = datetime.now(timezone.utc)

    async with get_sessionmaker()() as session:
        user = (
            await session.execute(select(User).where(User.verification_token == token))
        ).scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Invalid or already-used link.",
            )
        # A sign-in link (the account was already verified) lives minutes; the original
        # confirmation link lives a day.
        expiry_minutes = (
            cfg.signin_link_expiry_minutes
            if user.email_verified
            else cfg.verification_token_expiry_minutes
        )
        expiry_cutoff = now - timedelta(minutes=expiry_minutes)
        sent_at = user.verification_sent_at
        if sent_at is not None and sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        if sent_at is None or sent_at < expiry_cutoff:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "This link has expired — request a new one at https://www.pyvar.com#get-api-key.",
            )

        user.email_verified = True
        user.verification_token = None
        # verified_at feeds the daily "new verified accounts" count (api/routes/internal.py):
        # a returning user signing in must not be counted as newly verified.
        user.verified_at = user.verified_at or now
        external_id = user.external_id
        tier = user.tier
        await session.commit()

    access_token = create_access_token(user_id=external_id, tier=tier)
    return VerifyResponse(access_token=access_token, tier=tier)


# ── /auth/api-keys — durable keys, managed from a signed-in session ──────────────


def _key_info(row: ApiKey) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "prefix": row.prefix,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "last_used_at": row.last_used_at,
        "revoked_at": row.revoked_at,
    }


def _is_active(row: ApiKey, now: datetime) -> bool:
    if row.revoked_at is not None:
        return False
    if row.expires_at is None:
        return True
    expires = (
        row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    )
    return expires > now


async def _account_for(session: Any, user: TokenPayload) -> User:
    account = (
        await session.execute(select(User).where(User.external_id == user.user_id))
    ).scalar_one_or_none()
    if account is None or not account.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No verified account for this session.")
    return account


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: CreateApiKeyRequest, user: TokenPayload = Depends(require_session)
) -> ApiKeyCreated:
    """Create a durable API key. The secret is in this response only — it is not stored."""
    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as session:
        account = await _account_for(session, user)
        rows = (
            (await session.execute(select(ApiKey).where(ApiKey.user_id == account.id)))
            .scalars()
            .all()
        )
        if sum(1 for r in rows if _is_active(r, now)) >= cfg.api_key_max_active_per_user:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"You already have {cfg.api_key_max_active_per_user} active API keys. "
                "Revoke one before creating another.",
            )
        if len(rows) >= cfg.api_key_max_total_per_user:
            raise HTTPException(status.HTTP_409_CONFLICT, "API key limit reached for this account.")
        secret, prefix, digest = generate_key()
        row = ApiKey(
            user_id=account.id,
            name=body.name,
            prefix=prefix,
            key_hash=digest,
            created_at=now,
            expires_at=now + timedelta(days=cfg.api_key_default_expiry_days),
        )
        session.add(row)
        await session.commit()
        # Log the prefix only; the secret never reaches logs, Sentry or the database.
        logger.info("api_key_created", key_prefix=prefix, user_id=user.user_id)
        return ApiKeyCreated(**_key_info(row), key=secret)


@router.get("/api-keys", response_model=ApiKeyList)
async def list_api_keys(user: TokenPayload = Depends(require_session)) -> ApiKeyList:
    async with get_sessionmaker()() as session:
        account = await _account_for(session, user)
        rows = (
            (
                await session.execute(
                    select(ApiKey)
                    .where(ApiKey.user_id == account.id)
                    .order_by(ApiKey.created_at.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
        return ApiKeyList(keys=[ApiKeyInfo(**_key_info(r)) for r in rows])


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID, user: TokenPayload = Depends(require_session)
) -> Response:
    """Revoke a key (idempotent). The row is kept: keys are audit records."""
    async with get_sessionmaker()() as session:
        account = await _account_for(session, user)
        row = (
            await session.execute(
                select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == account.id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such API key.")
        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info("api_key_revoked", key_prefix=row.prefix, user_id=user.user_id)
        digest = row.key_hash
    await invalidate_cached_key(digest)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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

"""
api/middleware/auth.py — JWT bearer token validation

Reasoning:
- All pyvar API endpoints require authentication — financial computations
  must be tied to an account for rate limiting, audit logging, and billing.
- FastAPI's HTTPBearer dependency cleanly extracts the Authorization header.
- python-jose handles HS256 token decoding. In production, switch to RS256
  with a rotating key pair for proper asymmetric JWT security.
- The decoded payload is injected as a dependency into route handlers,
  giving each handler access to user_id, tier, and permissions without
  a separate DB lookup per request (claims are embedded in the token).
- Two kinds of bearer credential are accepted (docs/plan-durable-api-keys.md):
  a session JWT (60 minutes, what the dashboard and the "Try it" panel hold) and a
  durable API key ("pyvar_...", what plugins and scripts hold; see
  api/middleware/api_keys.py). Both resolve to the same TokenPayload, so rate
  limiting, billing and audit see one account either way. A key's tier is read
  from the database (cached briefly), a JWT's from its claims.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from api.middleware.api_keys import (
    looks_like_api_key,
    resolve_api_key,
    too_many_failures,
)
from config import get_settings

cfg = get_settings()
bearer_scheme = HTTPBearer()


class TokenPayload:
    """Decoded JWT claims injected into route handlers."""

    def __init__(
        self, sub: str, tier: str = "free", auth_method: str = "jwt", key_id: str | None = None
    ):
        self.user_id = sub
        # "jwt" (a signed session token) or "api_key". Key management endpoints
        # require "jwt": a leaked key must not be able to mint more keys.
        self.auth_method = auth_method
        self.key_id = key_id
        # "internal" (#146): the scheduled demo-refresh Lambda's service JWT
        # (pyvar-cdk/lambda/public_data_publisher/handler.py) — kept distinct
        # from "enterprise" so its calls don't pollute real customer-tier
        # usage analytics (api_usage.tier, var_jobs.tier), even though both
        # are unlimited for simulation size and, per
        # api/middleware/rate_limit.py, both exempt from the compute quota.
        self.tier = tier  # free | pro | enterprise | internal
        self.max_simulations = {
            "free": 10_000,
            "pro": 100_000,
            "enterprise": 500_000,
            "internal": 500_000,
        }.get(tier, 10_000)


def decode_token_payload(token: str) -> TokenPayload:
    """Decode and validate a raw JWT string into a TokenPayload.

    Shared by get_current_user (Authorization header, every HTTP route) and
    api/routes/var.py's WebSocket stream route (a ?token= query parameter —
    browser WebSocket clients cannot set a custom Authorization header on
    the opening handshake), so the validation logic is identical for both
    transports rather than duplicated.

    Raises:
        JWTError: on any validation failure (missing/invalid/expired token,
            missing subject claim). Callers translate this into the
            transport-appropriate rejection (401 for HTTP, a WebSocket
            close code for the streaming route).
    """
    payload = jwt.decode(
        token,
        cfg.jwt_secret,
        algorithms=[cfg.jwt_algorithm],
    )
    user_id: str = payload.get("sub")
    tier: str = payload.get("tier", "free")

    if not user_id:
        raise JWTError("Missing subject claim")

    return TokenPayload(sub=user_id, tier=tier)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> TokenPayload:
    """
    FastAPI dependency. Validates the bearer credential (session JWT or API key).
    Raises HTTP 401 on any validation failure, 503 if the key store is unavailable.
    """
    token = credentials.credentials
    if looks_like_api_key(token):
        payload = await _payload_from_api_key(request, token)
    else:
        try:
            payload = decode_token_payload(token)
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired token: {exc}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
    # The usage middleware runs around the DI graph, so it cannot see this result; it
    # reads the tier from here (an API key has no claims it could decode).
    request.state.pyvar_tier = payload.tier
    return payload


async def _payload_from_api_key(request: Request, token: str) -> TokenPayload:
    from api.middleware.rate_limit import get_trusted_client_ip

    try:
        resolved = await resolve_api_key(token)
    except Exception as exc:  # noqa: BLE001 - a store outage must not look like a bad key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable; retry shortly.",
        ) from exc
    if resolved is None:
        if await too_many_failures(get_trusted_client_ip(request)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many invalid API keys from this address; retry in a minute.",
                headers={"Retry-After": "60"},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Invalid, revoked or expired API key. Create a new one at "
                "https://www.pyvar.com#get-api-key"
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenPayload(
        sub=resolved.user_id, tier=resolved.tier, auth_method="api_key", key_id=resolved.key_id
    )


async def require_session(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """Only a signed-in session (JWT) may manage API keys, never an API key itself."""
    if user.auth_method != "jwt":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "API keys cannot manage API keys. Sign in at https://www.pyvar.com#get-api-key "
                "to create or revoke one."
            ),
        )
    return user


def create_access_token(user_id: str, tier: str = "free") -> str:
    """
    Utility for tests and the /auth/token endpoint (not shown here).
    Creates a signed JWT with user_id and tier embedded as claims.
    """
    from datetime import datetime, timedelta, timezone

    expire = datetime.now(timezone.utc) + timedelta(minutes=cfg.jwt_expiry_minutes)
    payload = {"sub": user_id, "tier": tier, "exp": expire}
    return str(jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm))

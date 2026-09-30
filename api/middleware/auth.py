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
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from config import get_settings

cfg = get_settings()
bearer_scheme = HTTPBearer()


class TokenPayload:
    """Decoded JWT claims injected into route handlers."""

    def __init__(self, sub: str, tier: str = "free"):
        self.user_id = sub
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
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> TokenPayload:
    """
    FastAPI dependency. Decodes and validates the JWT bearer token.
    Raises HTTP 401 on any validation failure.
    """
    try:
        return decode_token_payload(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def create_access_token(user_id: str, tier: str = "free") -> str:
    """
    Utility for tests and the /auth/token endpoint (not shown here).
    Creates a signed JWT with user_id and tier embedded as claims.
    """
    from datetime import datetime, timedelta, timezone

    expire = datetime.now(timezone.utc) + timedelta(minutes=cfg.jwt_expiry_minutes)
    payload = {"sub": user_id, "tier": tier, "exp": expire}
    return str(jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm))

"""
schemas/auth.py — Pydantic v2 request/response contracts for the minimum-viable
API key registration flow (P8 Task 3): email -> verify -> JWT.

Reasoning:
- EmailStr does real format validation (via the email-validator package,
  pydantic's [email] extra) rather than a hand-rolled regex, which is the
  well-known way to get email validation subtly wrong.
- RegisterResponse never echoes the email or reveals whether the address
  was already registered — same shape whether the account is new,
  re-registering unverified, or already verified (see api/routes/auth.py).
- email is normalized (stripped + lowercased) here, once, so every caller
  in api/routes/auth.py sees and stores the same canonical form. Without
  this, "User@x.com" and "user@x.com" pass EmailStr validation as distinct
  strings, bypass the case-sensitive uq_users_email unique constraint, and
  register as two separate accounts for what a human considers one address.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class RegisterResponse(BaseModel):
    # One message for every outcome (new, unverified, verified, suppressed, throttled):
    # the endpoint must never reveal whether an address already has an account.
    message: str = "If that address can receive mail, a link to continue has been sent."


class VerifyResponse(BaseModel):
    """Returned on GET /auth/verify and POST /auth/google: a 60-minute SESSION token.

    It is what the dashboard uses to manage API keys; it is not the credential to
    paste into a plugin (that is a durable key from POST /auth/api-keys)."""

    access_token: str
    token_type: str = "bearer"
    tier: str = "free"


class GoogleSignInRequest(BaseModel):
    """POST /auth/google — the raw ID token Google Identity Services hands
    the frontend's sign-in callback. Verified server-side (signature,
    issuer, audience, expiry) before anything in it is trusted."""

    id_token: str


class CreateApiKeyRequest(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=64)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class ApiKeyInfo(BaseModel):
    """A key as listed in the dashboard: never includes the secret."""

    id: str
    name: str
    prefix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyInfo):
    """Returned once, by POST /auth/api-keys. `key` is never retrievable again."""

    key: str


class ApiKeyList(BaseModel):
    keys: list[ApiKeyInfo]

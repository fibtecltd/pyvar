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

from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class RegisterResponse(BaseModel):
    message: str = "If that address isn't already verified, a verification link has been sent."


class VerifyResponse(BaseModel):
    """Returned on GET /auth/verify — the one time this JWT is shown."""

    access_token: str
    token_type: str = "bearer"
    tier: str = "free"

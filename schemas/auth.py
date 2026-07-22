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
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr


class RegisterResponse(BaseModel):
    message: str = "If that address isn't already verified, a verification link has been sent."


class VerifyResponse(BaseModel):
    """Returned on GET /auth/verify — the one time this JWT is shown."""

    access_token: str
    token_type: str = "bearer"
    tier: str = "free"

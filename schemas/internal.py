"""
schemas/internal.py — Pydantic v2 contracts for service-only ("internal" tier)
endpoints. First user: POST /internal/suppress-email (SES bounce/complaint
handling), called by pyvar-cdk/lambda/ses_suppression_handler/handler.py.

Reasoning:
- email is normalized (stripped + lowercased) the same way
  schemas.auth.RegisterRequest already does — the raw SES bounce/complaint
  payload's casing shouldn't be able to create a duplicate/mismatched lookup
  against the case-sensitive uq_users_email constraint.
- reason is a small closed vocabulary (Literal, not a free-form str) —
  matches exactly the two values api/routes/internal.py's caller can ever
  produce (see the bounce-subtype logic in
  pyvar-cdk/lambda/ses_suppression_handler/handler.py).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator


class SuppressEmailRequest(BaseModel):
    email: EmailStr
    reason: Literal["bounce_permanent", "complaint"]

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class SuppressEmailResponse(BaseModel):
    """matched=False (not a 404) when no User row has this email — an
    expected case (e.g. the address changed since the original send), not
    an error the caller needs to handle specially."""

    matched: bool
    already_suppressed: bool

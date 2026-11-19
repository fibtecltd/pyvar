"""
schemas/internal.py — Pydantic v2 contracts for service-only ("internal" tier)
endpoints. First user: POST /internal/suppress-email (SES bounce/complaint
handling), called by pyvar-cdk/lambda/ses_suppression_handler/handler.py.
Second user: GET /internal/token-report (daily JWT-issuance report), called
by pyvar-cdk/lambda/token_report_publisher/handler.py.

Reasoning:
- email is normalized (stripped + lowercased) the same way
  schemas.auth.RegisterRequest already does — the raw SES bounce/complaint
  payload's casing shouldn't be able to create a duplicate/mismatched lookup
  against the case-sensitive uq_users_email constraint.
- reason is a small closed vocabulary (Literal, not a free-form str) —
  matches exactly the two values api/routes/internal.py's caller can ever
  produce (see the bounce-subtype logic in
  pyvar-cdk/lambda/ses_suppression_handler/handler.py).
- TokenReportResponse.date is a plain ISO date string (not a datetime) —
  the caller (a daily-scheduled Lambda) only ever needs a human-readable
  day label for the email subject/body, never sub-day precision.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


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


class TokenReportResponse(BaseModel):
    """Returned by GET /internal/token-report."""

    env: str
    date: str
    issued_today: int
    issued_cumulative: int


# ── /internal/admin/education/* (docs/plan-education-tier.md) ─────────────────────────────────────────────
# The operator tool (scripts/education_grant.py) is the only caller. `cohort` is a short label the operator
# chooses, never an applicant's words: it is the only free-form value that reaches the billing_events audit row,
# and api/education_grants.py::check_cohort refuses anything that is not a token of letters, digits, . _ -.


class EducationGrantRequest(BaseModel):
    email: EmailStr
    months: int = Field(default=6, ge=1, le=12)
    cohort: str = Field(min_length=1, max_length=40)
    allow_domain_over_cap: bool = False

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class EducationExtendRequest(EducationGrantRequest):
    """Same fields: `months` is added to the current end date (or to today if the grant had run out)."""


class EducationRevokeRequest(BaseModel):
    email: EmailStr
    cohort: str = Field(min_length=1, max_length=40)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class EducationChangeResponse(BaseModel):
    """The new end date of a grant or extension (an ISO 8601 UTC time), or None after a revocation."""

    email: str
    tier: str
    expires_at: str | None


class EducationAccountOut(BaseModel):
    email: str
    expires_at: str | None
    active: bool
    cohort: str | None


class EducationListResponse(BaseModel):
    active: int
    cohort_cap: int
    domain_cap: int
    enabled: bool
    accounts: list[EducationAccountOut]


class EducationSuspendResponse(BaseModel):
    suspended: int

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

from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


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


class EducationTidyRequest(BaseModel):
    """`months` is how long ago a grant must have ended; `apply` False (the default) only counts."""

    months: int = Field(default=12, ge=1, le=120)
    apply: bool = False


class EducationTidyResponse(BaseModel):
    found: int
    applied: bool


# ── /internal/admin/accounts/erase (docs/plan-education-tier.md section 12) ───────────────────────────────


class AccountErasureRequest(BaseModel):
    email: EmailStr
    apply: bool = False

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class AccountErasureResponse(BaseModel):
    """What was or would be done. Carries the account identifier, never the address."""

    account_id: str
    old_tier: str
    keys_revoked: int
    keys_renamed: int
    stripe_linked: bool
    google_sign_in: bool
    applied: bool


# ── /internal/admin/audit/cleanup (docs/plan-education-tier.md section 12) ────────────────────────────────


class AuditCleanupRequest(BaseModel):
    """No retention period here on purpose: the six years are a constant in api/audit_retention.py."""

    apply: bool = False
    max_rows: int = Field(default=20000, ge=1, le=200000)


class AuditTableOut(BaseModel):
    found: int
    deleted: int
    remaining: int


class AuditCleanupResponse(BaseModel):
    """Counts only. `cutoff` is the instant six years before the call; `remaining` is what a rerun still has."""

    cutoff: str
    var_jobs: AuditTableOut
    billing_events: AuditTableOut
    applied: bool


# ── /internal/admin/accounts/export (docs/plan-education-tier.md section 12) ──────────────────────────────


class AccountExportRequest(BaseModel):
    email: EmailStr
    section: Literal["account", "api_keys", "billing_events", "var_jobs"]
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=1000)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class AccountExportResponse(BaseModel):
    """One page of one section of the copy. `next_offset` is None on the last page."""

    account_id: str
    section: str
    rows: list[dict[str, Any]]
    total: int
    next_offset: int | None
    not_included: list[str]


# ── /internal/admin/billing/checkout-allow (docs/plan-pro-tier-stripe.md section 11) ────────────────────────


class CheckoutAllowRequest(BaseModel):
    """Manage the set of accounts allowed to start a Pro checkout while Stripe is in test mode (api/billing_gate.py).

    `allow` and `remove` name an account by its address (looked up here, case-insensitively); `list` and `clear` take
    none. A dry run unless `apply` (list never changes anything).
    """

    action: Literal["allow", "remove", "list", "clear"]
    email: EmailStr | None = None
    apply: bool = False

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str | None) -> str | None:
        return None if v is None else v.strip().lower()

    @model_validator(mode="after")
    def _email_only_where_it_belongs(self) -> CheckoutAllowRequest:
        if self.action in ("allow", "remove") and self.email is None:
            raise ValueError("allow and remove need an email")
        if self.action in ("list", "clear") and self.email is not None:
            raise ValueError("list and clear take no email")
        return self


class CheckoutAllowResponse(BaseModel):
    """What was or would be done. Names an account by its identifier, never the address."""

    action: str
    applied: bool
    restricted: bool  # whether this deployment's gate is on (stripe_checkout_restricted)
    account_id: str | None = None
    tier: str | None = None
    was_allowed: bool | None = None  # allow and remove: whether the account was in the set before
    members: int  # accounts in the set after the action (or now, for a dry run)
    account_ids: list[str] = []  # list only

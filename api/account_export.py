"""api/account_export.py — a copy of the data we hold about one account (docs/plan-education-tier.md section 12).

Reasoning:
- The privacy policy tells people they can ask for a copy of what we hold about them (UK GDPR Article 15, and the
  right to receive it in a commonly used, machine-readable form, Article 20). There is no button, so this is the
  command: the owner runs scripts/account_export.py, which calls /internal/admin/accounts/export (admin token only),
  which calls this module, and sends the resulting JSON file to the person at the address on record.
- Read only. It finds the account by its e-mail address (the one thing the person can tell us), and returns, in
  four sections, only rows that belong to that account: the account row, its API keys, its tier-change records
  (`billing_events`) and its computation records (`var_jobs`), the last two joined on `users.external_id`. The
  three row sections are paged (`offset`, `limit`, oldest first) because a heavy user can have many computations.
- Never in the copy: the sign-in token (`verification_token`), the legacy key digest on the user row
  (`api_key_hash`), and every API key's digest (`key_hash`; the person has the key itself, and a digest is a
  credential-equivalent for someone who guessed it). What the copy says it does NOT cover is listed in
  `NOT_INCLUDED`, so the person is told what to ask Stripe, the mailbox or us for separately.
- The address is the lookup key and part of the person's own account row, so it appears in the `account` section
  (the person is entitled to it). It appears in no log line and in no other section.
- An unknown address, and an address that was erased, are the same 404: after an erasure there is nothing to find.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models import ApiKey, BillingEvent, User, VaRJob

Section = Literal["account", "api_keys", "billing_events", "var_jobs"]
SECTIONS: tuple[Section, ...] = ("account", "api_keys", "billing_events", "var_jobs")
MAX_LIMIT = 1000

# Columns that are never copied out (credentials, not data about the person). Pinned by tests/test_account_export.py.
SECRET_COLUMNS = frozenset({"verification_token", "api_key_hash", "key_hash"})

# Said in every answer, and written into the file, so that the copy cannot be mistaken for everything we hold.
NOT_INCLUDED = (
    "Messages in the company mailbox (application e-mails): ask us and we will send them.",
    "Stripe's own customer record, if the account was linked to one: ask Stripe.",
    "Server access logs and error reports, which hold no e-mail address and expire on their own.",
    "The result files of computations (Parquet, listed by result_s3_key where one exists) expire on their own.",
    "Sign-in tokens and key digests: credentials, deliberately left out.",
)


class ExportRefused(Exception):
    """A request the rules refuse. `status` is the HTTP status the route answers with."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class ExportPage:
    """One page of one section. `next_offset` is None on the last page; `total` is the section's row count."""

    account_id: str
    section: str
    rows: list[dict[str, Any]]
    total: int
    next_offset: int | None


def _value(value: Any) -> Any:
    """A column value as JSON can carry it."""
    if isinstance(value, datetime):
        # every timestamp is stored in UTC; say so even where a driver hands back a naive value
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _row(instance: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    return {name: _value(getattr(instance, name)) for name in columns}


def _columns(model: type) -> tuple[str, ...]:
    return tuple(c.key for c in model.__table__.columns if c.key not in SECRET_COLUMNS)  # type: ignore[attr-defined]


async def export_page(
    session: AsyncSession,
    *,
    email: str,
    section: Section,
    offset: int = 0,
    limit: int = 200,
) -> ExportPage:
    """One page of the copy of the account that holds `email`.

    Raises:
        ExportRefused: 404 no account has this address; 422 a bad section, offset or limit.
    """
    if section not in SECTIONS:
        raise ExportRefused(422, f"section must be one of: {', '.join(SECTIONS)}")
    if offset < 0 or not 1 <= limit <= MAX_LIMIT:
        raise ExportRefused(422, f"offset must be 0 or more and limit between 1 and {MAX_LIMIT}")
    user = (
        await session.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
    ).scalar_one_or_none()
    if user is None:
        raise ExportRefused(404, "No account has this address.")

    if section == "account":
        return ExportPage(user.external_id, section, [_row(user, _columns(User))], 1, None)

    if section == "api_keys":
        model: type = ApiKey
        owner = ApiKey.user_id == user.id
        order: tuple[Any, ...] = (ApiKey.created_at, ApiKey.id)
    elif section == "billing_events":
        model = BillingEvent
        owner = BillingEvent.user_id == user.external_id
        order = (BillingEvent.created_at, BillingEvent.id)
    else:
        model = VaRJob
        owner = VaRJob.user_id == user.external_id
        order = (VaRJob.created_at, VaRJob.id)

    total = int(
        (await session.execute(select(func.count()).select_from(model).where(owner))).scalar_one()
    )
    found = (
        (
            await session.execute(
                select(model).where(owner).order_by(*order).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    columns = _columns(model)
    rows = [_row(item, columns) for item in found]
    end = offset + len(rows)
    return ExportPage(user.external_id, section, rows, total, end if end < total else None)

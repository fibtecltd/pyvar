"""api/education_grants.py — granting, extending, revoking and listing education accounts (A2).

Reasoning:
- docs/plan-education-tier.md decision 2: no portal form. A person e-mails from an institutional address and the
  owner grants access with one command (scripts/education_grant.py -> the /internal/admin/education routes ->
  this module). Nothing an applicant wrote ever enters the database: an account is found by its e-mail address,
  the institution is that address's domain, and the audit trail is a `billing_events` row with a CODE and the
  operator's cohort label (a short token, validated below), nothing else.
- Every change writes its `billing_events` row in the SAME transaction as the `users` change (CLAUDE.md 3.3 and
  3.5), so the two cannot disagree. The route layer maps a `GrantRefused` to its HTTP status; this module knows
  nothing about HTTP.
- "Active" means `tier == "education"` AND `tier_expires_at` in the future. A row can keep tier "education" with
  a past expiry (a grant that ran out, or `suspend_all`); api/tiers.py::effective_tier already treats it as free,
  and `extend` brings it back. Caps count active rows only.
- Caps (config.py): `education_cohort_cap` active accounts in all, `education_domain_cap` per e-mail domain
  (`allow_domain_over_cap` lifts only the second, for a class; never the first). A grant is for 1 to
  `education_max_months` months, 6 by default; there is no open-ended grant.
- Only a verified FREE account can be granted: a Pro, enterprise or internal account is refused (an education
  grant must never replace a paid plan or a service role). A Stripe upgrade later replaces the grant, because
  `effective_tier` reads the date only while the tier is "education".
- After each commit the account's cached API keys are dropped, so a change reaches keys at once instead of
  after the key cache's TTL. Best effort: the TTL (60 s) and, for a grant's end, the entry's own cap bound it.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.api_keys import invalidate_cached_key
from api.middleware.billing_lifecycle import (
    EVENT_EDUCATION_EXTENDED,
    EVENT_EDUCATION_GRANTED,
    EVENT_EDUCATION_REVOKED,
    EVENT_EDUCATION_SUSPENDED,
    record_billing_event,
    send_tier_change_email,
)
from api.tiers import EDUCATION_TIER
from config import get_settings
from storage.models import ApiKey, BillingEvent, User

logger = structlog.get_logger()
cfg = get_settings()

# A cohort label is an operator's short token ("ucl-risk-2026"), never free text.
COHORT_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
_DOMAIN_PATTERN = re.compile(r"^[a-z0-9.-]{1,253}$")


class GrantRefused(Exception):
    """A request the rules refuse. `status` is the HTTP status the route answers with."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class Account:
    """One education account as `list_accounts` reports it (no identifier beyond the e-mail address)."""

    email: str
    expires_at: datetime | None
    active: bool
    cohort: str | None


def add_months(moment: datetime, months: int) -> datetime:
    """`moment` plus whole calendar months; a day past the end of the target month becomes its last day."""
    index = moment.month - 1 + months
    year, month = moment.year + index // 12, index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def _aware(moment: datetime | None) -> datetime | None:
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def check_cohort(cohort: str) -> str:
    """The cohort label, or a refusal: a short token only, so no applicant text can reach the audit log."""
    if not COHORT_PATTERN.fullmatch(cohort):
        raise GrantRefused(
            422, "cohort must be 1-40 characters of letters, digits, '.', '_' or '-'."
        )
    return cohort


def _domain_of(email: str) -> str:
    domain = email.rsplit("@", 1)[-1].lower()
    if "@" not in email or not _DOMAIN_PATTERN.fullmatch(domain):
        raise GrantRefused(422, "That is not an e-mail address this tool can read.")
    return domain


async def _user_by_email(session: AsyncSession, email: str) -> User:
    row = (
        await session.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
    ).scalar_one_or_none()
    if row is None:
        raise GrantRefused(
            404, "No account has this address. Ask them to sign in at pyvar.com first."
        )
    return row


async def _active_count(
    session: AsyncSession, now: datetime, *, domain: str | None = None, exclude: User | None = None
) -> int:
    query = (
        select(func.count())
        .select_from(User)
        .where(User.tier == EDUCATION_TIER, User.tier_expires_at > now)
    )
    if domain is not None:
        query = query.where(func.lower(User.email).like(f"%@{domain}"))
    if exclude is not None:
        query = query.where(User.id != exclude.id)
    return int((await session.execute(query)).scalar_one())


async def _enforce_caps(
    session: AsyncSession, user: User, now: datetime, *, allow_domain_over_cap: bool
) -> None:
    if await _active_count(session, now, exclude=user) >= cfg.education_cohort_cap:
        raise GrantRefused(
            409, f"The education cohort is full ({cfg.education_cohort_cap} active accounts)."
        )
    if allow_domain_over_cap:
        return
    domain = _domain_of(user.email or "")
    if await _active_count(session, now, domain=domain, exclude=user) >= cfg.education_domain_cap:
        raise GrantRefused(
            409,
            f"{cfg.education_domain_cap} education accounts are already active for {domain}. "
            "Use allow_domain_over_cap for a class.",
        )


def _check_months(months: int) -> int:
    if not 1 <= months <= cfg.education_max_months:
        raise GrantRefused(422, f"months must be between 1 and {cfg.education_max_months}.")
    return months


def _require_enabled() -> None:
    if not cfg.education_tier_enabled:
        raise GrantRefused(503, "The education tier is switched off in this environment.")


async def _drop_cached_keys(session: AsyncSession, users: list[User]) -> None:
    """Forget the cached resolution of each of these accounts' live API keys (best effort)."""
    ids = [u.id for u in users]
    if not ids:
        return
    digests = (
        (
            await session.execute(
                select(ApiKey.key_hash).where(ApiKey.user_id.in_(ids), ApiKey.revoked_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    for digest in digests:
        await invalidate_cached_key(digest)


async def grant(
    session: AsyncSession,
    *,
    email: str,
    months: int,
    cohort: str,
    allow_domain_over_cap: bool = False,
    now: datetime | None = None,
) -> datetime:
    """Give a verified free account education access for `months` months. Commits. Returns the expiry.

    Raises:
        GrantRefused: 503 flag off; 404 no such account; 409 not verified, not on the free tier, already an
            education account (use extend), or a cap reached; 422 a bad `months` or cohort label.
    """
    _require_enabled()
    check_cohort(cohort)
    _check_months(months)
    moment = now or datetime.now(timezone.utc)
    user = await _user_by_email(session, email)
    if not user.email_verified:
        raise GrantRefused(409, "That address has not been verified yet.")
    if user.tier == EDUCATION_TIER:
        raise GrantRefused(409, "That account is already an education account. Use extend.")
    if user.tier != "free":
        raise GrantRefused(
            409, f"That account is on the {user.tier!r} tier; only free accounts can be granted."
        )
    await _enforce_caps(session, user, moment, allow_domain_over_cap=allow_domain_over_cap)

    expires = add_months(moment, months)
    old_tier = user.tier
    user.tier = EDUCATION_TIER
    user.tier_expires_at = expires
    record_billing_event(
        session,
        user_id=user.external_id,
        event_type=EVENT_EDUCATION_GRANTED,
        old_tier=old_tier,
        new_tier=EDUCATION_TIER,
        reason=f"cohort={cohort}; months={months}; expires={expires.date().isoformat()}",
    )
    address, account = user.email, user.external_id
    await session.commit()
    await _drop_cached_keys(session, [user])
    logger.info("education_granted", cohort=cohort, months=months)
    send_tier_change_email(address, EVENT_EDUCATION_GRANTED, end_date=expires, account_id=account)
    return expires


async def extend(
    session: AsyncSession,
    *,
    email: str,
    months: int,
    cohort: str,
    allow_domain_over_cap: bool = False,
    now: datetime | None = None,
) -> datetime:
    """Move an education account's end date out by `months` months (from today if it already ended).

    The result may be at most `education_max_months` from now. An account whose grant had run out becomes
    active again, so the caps are checked for it. Commits. Returns the new expiry.

    Raises:
        GrantRefused: 503 flag off; 404 no such account; 409 not an education account, a cap reached, or the
            new date too far out; 422 a bad `months` or cohort label.
    """
    _require_enabled()
    check_cohort(cohort)
    _check_months(months)
    moment = now or datetime.now(timezone.utc)
    user = await _user_by_email(session, email)
    if user.tier != EDUCATION_TIER:
        raise GrantRefused(409, "That account is not an education account. Use grant.")
    current = _aware(user.tier_expires_at)
    was_active = current is not None and current > moment
    base = current if was_active and current is not None else moment
    expires = add_months(base, months)
    if expires > add_months(moment, cfg.education_max_months):
        raise GrantRefused(
            409, f"An education grant runs at most {cfg.education_max_months} months from today."
        )
    if not was_active:
        await _enforce_caps(session, user, moment, allow_domain_over_cap=allow_domain_over_cap)
    user.tier_expires_at = expires
    record_billing_event(
        session,
        user_id=user.external_id,
        event_type=EVENT_EDUCATION_EXTENDED,
        old_tier=EDUCATION_TIER,
        new_tier=EDUCATION_TIER,
        reason=f"cohort={cohort}; months={months}; expires={expires.date().isoformat()}",
    )
    address, account = user.email, user.external_id
    await session.commit()
    await _drop_cached_keys(session, [user])
    logger.info("education_extended", cohort=cohort, months=months)
    send_tier_change_email(address, EVENT_EDUCATION_EXTENDED, end_date=expires, account_id=account)
    return expires


async def revoke(session: AsyncSession, *, email: str, cohort: str) -> None:
    """End an education account's access now: back to the free tier, no expiry. Commits. Works with the
    feature flag off (a way to end access must never depend on the flag).

    Raises:
        GrantRefused: 404 no such account; 409 not an education account; 422 a bad cohort label.
    """
    check_cohort(cohort)
    user = await _user_by_email(session, email)
    if user.tier != EDUCATION_TIER:
        raise GrantRefused(409, "That account is not an education account.")
    user.tier = "free"
    user.tier_expires_at = None
    record_billing_event(
        session,
        user_id=user.external_id,
        event_type=EVENT_EDUCATION_REVOKED,
        old_tier=EDUCATION_TIER,
        new_tier="free",
        reason=f"cohort={cohort}",
    )
    address, account = user.email, user.external_id
    await session.commit()
    await _drop_cached_keys(session, [user])
    logger.info("education_revoked", cohort=cohort)
    send_tier_change_email(address, EVENT_EDUCATION_REVOKED, account_id=account)


async def suspend_all(session: AsyncSession, *, now: datetime | None = None) -> int:
    """The kill switch: end every ACTIVE education grant now. Commits. Returns how many.

    Each account keeps tier "education" with its expiry set to now, so it counts as free at once and `extend`
    can bring it back; one event per account. Works with the flag off.
    """
    moment = now or datetime.now(timezone.utc)
    rows = (
        (
            await session.execute(
                select(User).where(User.tier == EDUCATION_TIER, User.tier_expires_at > moment)
            )
        )
        .scalars()
        .all()
    )
    for user in rows:
        user.tier_expires_at = moment
        record_billing_event(
            session,
            user_id=user.external_id,
            event_type=EVENT_EDUCATION_SUSPENDED,
            old_tier=EDUCATION_TIER,
            new_tier="free",
            reason="code=suspend_all",
        )
    recipients = [(u.email, u.external_id) for u in rows]
    await session.commit()
    await _drop_cached_keys(session, list(rows))
    logger.warning("education_suspended_all", accounts=len(rows))
    for address, account in recipients:
        send_tier_change_email(address, EVENT_EDUCATION_SUSPENDED, account_id=account)
    return len(rows)


_COHORT_IN_REASON = re.compile(r"cohort=([A-Za-z0-9._-]{1,40})")


async def list_accounts(session: AsyncSession, *, now: datetime | None = None) -> list[Account]:
    """Every account whose tier is "education" (active or run out), soonest expiry first, with the cohort
    label of its latest grant or extension."""
    moment = now or datetime.now(timezone.utc)
    users = (
        (
            await session.execute(
                select(User)
                .where(User.tier == EDUCATION_TIER)
                .order_by(User.tier_expires_at.asc().nulls_first())
            )
        )
        .scalars()
        .all()
    )
    cohorts: dict[str, str] = {}
    if users:
        events = (
            await session.execute(
                select(BillingEvent.user_id, BillingEvent.reason)
                .where(
                    BillingEvent.user_id.in_([u.external_id for u in users]),
                    BillingEvent.event_type.in_(
                        [EVENT_EDUCATION_GRANTED, EVENT_EDUCATION_EXTENDED]
                    ),
                )
                .order_by(BillingEvent.created_at.asc())
            )
        ).all()
        for user_id, reason in events:  # ascending, so the latest event wins
            found = _COHORT_IN_REASON.search(reason or "")
            if found:
                cohorts[user_id] = found.group(1)
    accounts = []
    for user in users:
        expires = _aware(user.tier_expires_at)
        accounts.append(
            Account(
                email=user.email or "",
                expires_at=expires,
                active=expires is not None and expires > moment,
                cohort=cohorts.get(user.external_id),
            )
        )
    return accounts

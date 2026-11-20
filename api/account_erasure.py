"""api/account_erasure.py — erasing an account at its holder's request (docs/plan-education-tier.md section 12).

Reasoning:
- The privacy policy promises that on request we "delete your e-mail address and switch off your API keys" and
  that the records of tier changes then carry only an account identifier we can no longer match to the person.
  There is no button for it: the owner runs scripts/account_erase.py, which calls the /internal/admin/accounts/erase
  route, which calls this module.
- Erasure here is NOT deleting rows. `api_keys` rows are never deleted (CLAUDE.md 3.3 and 3.5: revoking sets
  `revoked_at`) and have a foreign key to `users.id`; `billing_events` and `var_jobs` are audit tables that name
  the account by `users.external_id`. So: the e-mail address is set to NULL (the column is nullable, and the
  application, not the schema, requires an address at sign-up), tokens are cleared, every live key is revoked and
  every key's name (free text the person chose) is blanked, and the `users` row stays as an identifier with no
  address. Nothing in it can then be tied to the person by us, and the audit joins keep working.
- What it does NOT do, and says so in its result: Stripe keeps its own customer record (`stripe_linked`); the
  company mailbox is the owner's to clear by hand; an account that signed up with Google keeps `google:<id>` as
  its identifier (needed so the audit rows still join), so that Google account cannot sign in again (the sign-in
  route would try to create a second row with the same identifier); the person can register by e-mail instead.
- Refused: a paid or service account (pro, enterprise, internal). Cancel the subscription first, or it is not a
  person's account to erase.
- Dry run by default at the route and in the script. One `billing_events` row (code=erase) in the same
  transaction; the address appears in no log line and in no row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.api_keys import invalidate_cached_key
from api.middleware.billing_lifecycle import EVENT_ACCOUNT_ERASED, record_billing_event
from api.tiers import EDUCATION_TIER
from storage.models import ApiKey, User

logger = structlog.get_logger()

# Tiers that are not one person's free account: refused, with the reason in the answer.
REFUSED_TIERS = frozenset({"pro", "enterprise", "internal"})
ERASED_KEY_NAME = "erased"


class ErasureRefused(Exception):
    """A request the rules refuse. `status` is the HTTP status the route answers with."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class ErasureResult:
    """What was (or, in a dry run, would be) done. No e-mail address: the account identifier is the handle."""

    account_id: str
    old_tier: str
    keys_revoked: int
    keys_renamed: int
    stripe_linked: bool
    google_sign_in: bool
    applied: bool


async def erase_account(
    session: AsyncSession, *, email: str, apply: bool = False, now: datetime | None = None
) -> ErasureResult:
    """Remove the e-mail address from the account that holds it and switch off its keys. Commits only with `apply`.

    Raises:
        ErasureRefused: 404 no account has this address; 409 a paid or service account.
    """
    user = (
        await session.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
    ).scalar_one_or_none()
    if user is None:
        raise ErasureRefused(404, "No account has this address.")
    if user.tier in REFUSED_TIERS:
        raise ErasureRefused(
            409,
            f"That is a {user.tier} account. Cancel its subscription or ask the owner of the service "
            "role first: this command only erases free and education accounts.",
        )

    keys = list((await session.execute(select(ApiKey).where(ApiKey.user_id == user.id))).scalars())
    live = [key for key in keys if key.revoked_at is None]
    result = ErasureResult(
        account_id=user.external_id,
        old_tier=user.tier,
        keys_revoked=len(live),
        keys_renamed=sum(1 for key in keys if key.name != ERASED_KEY_NAME),
        stripe_linked=user.stripe_customer_id is not None,
        google_sign_in=user.external_id.startswith("google:"),
        applied=apply,
    )
    if not apply:
        return result

    moment = now or datetime.now(timezone.utc)
    cached_digests = [key.key_hash for key in live]
    new_tier = "free" if user.tier == EDUCATION_TIER else user.tier
    user.email = None
    user.email_verified = False
    user.verification_token = None
    user.verification_sent_at = None
    user.api_key_hash = None
    if user.tier == EDUCATION_TIER:
        user.tier = "free"
        user.tier_expires_at = None
    for key in keys:
        if key.revoked_at is None:
            key.revoked_at = moment
        key.name = ERASED_KEY_NAME
    record_billing_event(
        session,
        user_id=user.external_id,
        event_type=EVENT_ACCOUNT_ERASED,
        old_tier=result.old_tier,
        new_tier=new_tier,
        reason="code=erase",
    )
    await session.commit()
    for digest in cached_digests:
        await invalidate_cached_key(digest)
    logger.info("account_erased", account_id=result.account_id, keys_revoked=result.keys_revoked)
    return result

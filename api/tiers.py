"""
api/tiers.py — what each tier may do, in one table (A1).

Reasoning:
- Before this module the answer was spread over four places: the simulation cap in `TokenPayload`
  (api/middleware/auth.py), the daily and monthly request quotas and the exempt set in
  api/middleware/rate_limit.py, the monthly simulation quota in api/routes/var.py and the assistant's per-tier
  daily quota. An unknown tier fell through to the free limits in each of them without a trace, so a new tier
  (the education tier, the anonymous plugin tier) would have had to be taught to all four, and forgetting one
  would have given it the free limits silently.
- A tier is now one `TierPolicy` row, built from the settings in config.py (the numbers stay configurable and
  tests that patch `cfg` keep working). Adding a tier means adding a row here; tests/test_tier_policy.py fails
  until every row is complete, and no other module may read the per-tier numbers (it greps for them).
- Behaviour for the four existing tiers is unchanged and pinned by tests/test_tier_limits_behaviour.py, which was
  written and run before this refactor. An unknown tier still gets the free tier's limits, but now logs a
  warning once per name so the gap is visible.
- "education" is a finite grant (docs/plan-education-tier.md): users.tier says "education" only while
  users.tier_expires_at is in the future. `effective_tier()` below is the ONE place that turns the stored pair into
  a tier, and every site where a tier leaves the database (the API-key lookup and the three session mints) calls
  it. It adds a per-minute burst cap (`burst_per_minute`).
- A monthly limit (Pro and education have one) is always a refusal: HTTP 429 that names the cap and says when it
  resets. It never changes the account's tier (docs/plan-pro-tier-stripe.md); only the end of a Stripe subscription
  moves a Pro account to Free.
- "trial" is the odd one out among the rows: the no-sign-up trial lane's calls carry it (api/routes/trial.py); no
  account ever has it.
- What a tier is NOT: the admin routes check the name "internal" (api/routes/internal.py) and the billing code
  moves users between "free" and "pro" (api/middleware/billing_lifecycle.py). Those are roles and transitions,
  not limits, and stay where they are.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from config import get_settings

logger = logging.getLogger(__name__)

# What an unknown tier gets (the same default `TokenPayload.max_simulations` always used).
FALLBACK_TIER = "free"

# The tiers that exist. Adding one needs a row in `_policies` and an entry here; the test of this module fails
# until both agree.
KNOWN_TIERS = frozenset({"free", "pro", "enterprise", "internal", "trial", "education"})

# The one tier whose stored value depends on a date (see effective_tier).
EDUCATION_TIER = "education"

_warned: set[str] = set()


@dataclass(frozen=True)
class TierPolicy:
    """The limits of one tier. `None` means "no such limit"."""

    name: str
    # Largest n_simulations one request may ask for; above it the route answers 403.
    max_simulations: int
    # Account-wide compute requests per day, over every /api/v1 compute endpoint. None: exempt from the quota.
    daily_requests: int | None
    # Compute requests per 30-day window; breaching it is a 429 until the window resets (the tier never changes).
    monthly_requests: int | None
    # VaR simulations per 30-day window (VaR only); same consequence.
    monthly_simulations: int | None
    # The assistant's view of the tier: "free", "pro" or "enterprise" (the service tier counts as enterprise),
    # used as a metrics label, and the assistant questions allowed per day.
    assistant_group: str
    assistant_daily: int
    # Compute requests per minute per account (all /api/v1 compute endpoints); None: no burst cap.
    burst_per_minute: int | None = None


def _policies() -> dict[str, TierPolicy]:
    """The table, built from the current settings (not at import, so patched settings are honoured)."""
    cfg = get_settings()
    return {
        "free": TierPolicy(
            name="free",
            max_simulations=10_000,
            daily_requests=cfg.rate_limit_free_daily,
            monthly_requests=None,
            monthly_simulations=None,
            assistant_group="free",
            assistant_daily=cfg.assistant_quota_free_daily,
        ),
        "pro": TierPolicy(
            name="pro",
            max_simulations=100_000,
            daily_requests=cfg.rate_limit_pro_daily,
            monthly_requests=cfg.rate_limit_pro_monthly_requests,
            monthly_simulations=cfg.rate_limit_pro_monthly_simulations,
            assistant_group="pro",
            assistant_daily=cfg.assistant_quota_pro_daily,
        ),
        "enterprise": TierPolicy(
            name="enterprise",
            max_simulations=500_000,
            daily_requests=None,
            monthly_requests=None,
            monthly_simulations=None,
            assistant_group="enterprise",
            assistant_daily=cfg.assistant_quota_enterprise_daily,
        ),
        # The scheduled demo-refresh Lambda's service token: kept apart from "enterprise" so its calls do not
        # pollute customer-tier usage analytics, with the same limits.
        "internal": TierPolicy(
            name="internal",
            max_simulations=500_000,
            daily_requests=None,
            monthly_requests=None,
            monthly_simulations=None,
            assistant_group="enterprise",
            assistant_daily=cfg.assistant_quota_enterprise_daily,
        ),
        # The education tier (docs/plan-education-tier.md): a finite, hand-given grant. Limits are starting values
        # (config.py); no extra assistant allowance.
        "education": TierPolicy(
            name="education",
            max_simulations=100_000,
            daily_requests=cfg.rate_limit_education_daily,
            monthly_requests=cfg.rate_limit_education_monthly_requests,
            monthly_simulations=cfg.rate_limit_education_monthly_simulations,
            assistant_group="free",
            assistant_daily=cfg.assistant_quota_free_daily,
            burst_per_minute=cfg.rate_limit_education_burst_per_minute,
        ),
        # The no-sign-up trial lane (docs/plan-trial-lane-throttle.md). It is not an account tier: no users or
        # api_keys row has it, and a ticket never carries it as a claim. The row exists so the lane's per-ticket
        # daily call count and the simulation cap come from this one table like everyone else's, and so the
        # api_usage rows of an allowed trial call carry the tier "trial". No assistant questions.
        "trial": TierPolicy(
            name="trial",
            max_simulations=10_000,
            daily_requests=5,
            monthly_requests=None,
            monthly_simulations=None,
            assistant_group="free",
            assistant_daily=0,
        ),
    }


def policy_for(tier: str) -> TierPolicy:
    """The policy of `tier`; an unknown tier gets the free tier's, and a warning once per name."""
    table = _policies()
    policy = table.get(tier)
    if policy is not None:
        return policy
    if tier not in _warned:
        _warned.add(tier)
        logger.warning(
            "Unknown tier %r: applying the %r tier's limits. Add a row to api/tiers.py.",
            tier,
            FALLBACK_TIER,
        )
    return table[FALLBACK_TIER]


def effective_tier(
    tier: str, tier_expires_at: datetime | None = None, now: datetime | None = None
) -> str:
    """The tier an account counts as right now, from the pair the database stores.

    Only "education" depends on the date: it counts while `tier_expires_at` is in the future and the
    feature flag is on; with no expiry, a past one or the flag off, the account is "free". Every other tier is
    returned as stored. Call this wherever a tier leaves the database: the API-key lookup and each session
    mint. A tier must never reach a token claim or a cache entry by any other route (CLAUDE.md 3.5).

    Args:
        tier: `users.tier` as stored.
        tier_expires_at: `users.tier_expires_at`; naive values are read as UTC.
        now: The current time (a parameter for tests).

    Returns:
        The tier to apply: `tier` itself, or "free" for an education account whose grant has lapsed.
    """
    if tier != EDUCATION_TIER:
        return tier
    if not get_settings().education_tier_enabled or tier_expires_at is None:
        return FALLBACK_TIER
    expires = tier_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    moment = now if now is not None else datetime.now(timezone.utc)
    return EDUCATION_TIER if expires > moment else FALLBACK_TIER


def seconds_until_expiry(
    tier: str, tier_expires_at: datetime | None, now: datetime | None = None
) -> int | None:
    """Seconds an education grant has left (at least 0), or None for any other tier or no expiry.

    The API-key cache uses it so a cached tier never outlives the grant it came from.
    """
    if tier != EDUCATION_TIER or tier_expires_at is None:
        return None
    expires = tier_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    moment = now if now is not None else datetime.now(timezone.utc)
    return max(0, int((expires - moment).total_seconds()))

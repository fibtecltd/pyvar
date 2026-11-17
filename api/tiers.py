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
- What a tier is NOT: the admin routes check the name "internal" (api/routes/internal.py) and the billing code
  moves users between "free" and "pro" (api/middleware/billing_lifecycle.py). Those are roles and transitions,
  not limits, and stay where they are.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from config import get_settings

logger = logging.getLogger(__name__)

# What an unknown tier gets (the same default `TokenPayload.max_simulations` always used).
FALLBACK_TIER = "free"

# The tiers that exist. Adding one needs a row in `_policies` and an entry here; the test of this module fails
# until both agree.
KNOWN_TIERS = frozenset({"free", "pro", "enterprise", "internal"})

_warned: set[str] = set()


@dataclass(frozen=True)
class TierPolicy:
    """The limits of one tier. `None` means "no such limit"."""

    name: str
    # Largest n_simulations one request may ask for; above it the route answers 403.
    max_simulations: int
    # Account-wide compute requests per day, over every /api/v1 compute endpoint. None: exempt from the quota.
    daily_requests: int | None
    # Compute requests per billing month; breaching it moves a Pro account to Free (billing_lifecycle.py).
    monthly_requests: int | None
    # VaR simulations per billing month (VaR only); same consequence.
    monthly_simulations: int | None
    # The assistant's view of the tier: "free", "pro" or "enterprise" (the service tier counts as enterprise),
    # used as a metrics label, and the assistant questions allowed per day.
    assistant_group: str
    assistant_daily: int


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

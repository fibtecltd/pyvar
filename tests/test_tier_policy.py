"""tests/test_tier_policy.py — api/tiers.py is the one table of tier limits (A1).

Reasoning:
- A new tier is a new row. These tests fail until the row exists and is complete, so a tier cannot reach the code
  without limits, and nothing else may read the per-tier numbers: another module that does would let a new tier be
  taught to three places and forgotten in the fourth. (The same gap once let an unknown tier get the free limits
  silently in every one of them.)
- tests/test_tier_limits_behaviour.py pins that the four existing tiers behave exactly as before the refactor.
- The fifth row, "trial", belongs to the no-sign-up trial lane (docs/plan-trial-lane-throttle.md): 10,000
  simulations, 5 calls a day per ticket, no assistant questions.
- The sixth, "education", is a finite grant (docs/plan-education-tier.md); its limits, the field only it uses
  (a burst cap) and its rules are tested in tests/test_education_tier.py.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import fields
from pathlib import Path

import pytest

from api import tiers
from api.tiers import FALLBACK_TIER, KNOWN_TIERS, TierPolicy, policy_for

ROOT = Path(__file__).resolve().parents[1]
PER_TIER_SETTINGS = re.compile(
    r"rate_limit_(free|pro|education)_daily|rate_limit_pro_monthly_(requests|simulations)"
    r"|rate_limit_education_(monthly_requests|monthly_simulations|burst_per_minute)"
    r"|assistant_quota_(free|pro|enterprise)_daily"
)  # matched against attribute names, so it must match a whole name


def test_the_known_tiers_are_exactly_the_six_that_exist() -> None:
    # "trial" is not an account tier: only the no-sign-up lane's calls carry it (api/routes/trial.py).
    assert KNOWN_TIERS == {"free", "pro", "enterprise", "internal", "trial", "education"}
    assert FALLBACK_TIER in KNOWN_TIERS


@pytest.mark.parametrize("tier", sorted(KNOWN_TIERS))
def test_every_known_tier_has_a_complete_row(tier: str) -> None:
    policy = policy_for(tier)
    assert policy.name == tier
    assert policy.max_simulations >= 1_000  # the schema's smallest request
    assert policy.assistant_group in {"free", "pro", "enterprise"}
    # Every tier may ask the assistant, except the no-sign-up trial lane, which gets no typed questions.
    assert (policy.assistant_daily == 0) == (tier == "trial")
    for value in (policy.daily_requests, policy.monthly_requests, policy.monthly_simulations):
        assert value is None or value > 0
    assert {f.name for f in fields(TierPolicy)} == {
        "name",
        "max_simulations",
        "daily_requests",
        "monthly_requests",
        "monthly_simulations",
        "assistant_group",
        "assistant_daily",
        "burst_per_minute",
    }, "a policy row has no downgrade option: a monthly cap is always a 429 (docs/plan-pro-tier-stripe.md)"
    assert policy.burst_per_minute is None or policy.burst_per_minute > 0


def test_the_table_and_the_known_tiers_agree() -> None:
    assert set(tiers._policies()) == KNOWN_TIERS


def test_an_unknown_tier_gets_the_free_limits_and_a_warning_once(caplog) -> None:
    tiers._warned.discard("mystery-tier")
    with caplog.at_level(logging.WARNING, logger="api.tiers"):
        first = policy_for("mystery-tier")
        second = policy_for("mystery-tier")
    free = policy_for("free")
    assert (first.max_simulations, first.daily_requests) == (
        free.max_simulations,
        free.daily_requests,
    )
    assert first == second
    warnings = [r for r in caplog.records if "mystery-tier" in r.getMessage()]
    assert len(warnings) == 1, "one warning per unknown name, not one per request"


def test_the_free_daily_quota_is_twenty_requests() -> None:
    """A6: the free tier's daily requests, doubled from 10 (decided 2026-11-16)."""
    from config import Settings

    assert Settings.model_fields["rate_limit_free_daily"].default == 20


def test_only_the_tier_table_reads_the_per_tier_settings() -> None:
    """Code only: a docstring or a comment may still name a setting."""
    offenders = []
    for path in sorted((ROOT / "api").rglob("*.py")):
        if path.name == "tiers.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and PER_TIER_SETTINGS.fullmatch(node.attr):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: .{node.attr}")
    assert not offenders, "read the per-tier numbers through api/tiers.py:\n" + "\n".join(offenders)


def test_the_trial_row_is_the_lanes_limits_and_nothing_else() -> None:
    trial = policy_for("trial")
    assert (trial.max_simulations, trial.daily_requests, trial.assistant_daily) == (10_000, 5, 0)
    assert trial.monthly_requests is None and trial.monthly_simulations is None
    assert trial.assistant_group == "free"

"""tests/test_billing_gate.py — who may start a Pro checkout while Stripe is in test mode (api/billing_gate.py).

Reasoning:
- pyvar's webhook has no live/test check and the dashboard offers "Upgrade to Pro" to every free account, so on a
  deployment whose Stripe keys are test keys anyone could pay the public test card and become Pro. Where
  `stripe_checkout_restricted` is on, only accounts in a Redis set an operator manages (scripts/billing_checkout_allow.py) may start a checkout.
- It FAILS CLOSED: Redis unconfigured or unreadable means nobody. With the setting off (dev, a new environment) the
  gate must not touch Redis at all, so a Redis outage cannot take checkout down where it is not needed.
- The key name is part of the operator's procedure (docs/plan-pro-tier-stripe.md section 11), so it is pinned.
"""

from __future__ import annotations

from typing import Any

import pytest

from api import billing_gate


class _Members:
    """Just the one command the gate uses."""

    def __init__(self, *members: str) -> None:
        self.members = set(members)
        self.asked: list[tuple[str, str]] = []

    async def sismember(self, key: str, member: str) -> bool:
        self.asked.append((key, member))
        return member in self.members


class _Broken:
    async def sismember(self, key: str, member: str) -> bool:
        raise ConnectionError("redis is down")


def _use(monkeypatch: pytest.MonkeyPatch, client: Any, *, restricted: bool) -> None:
    monkeypatch.setattr(billing_gate.cfg, "stripe_checkout_restricted", restricted)
    monkeypatch.setattr(billing_gate, "_redis", lambda: client)


def test_the_operators_key_name_is_pinned() -> None:
    assert billing_gate.CHECKOUT_ALLOW_KEY == "pyvar:billing:checkout:allow"


@pytest.mark.asyncio
async def test_with_the_restriction_off_everyone_is_allowed_and_redis_is_not_touched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def must_not_be_called() -> Any:
        raise AssertionError("Redis must not be touched while the restriction is off")

    monkeypatch.setattr(billing_gate.cfg, "stripe_checkout_restricted", False)
    monkeypatch.setattr(billing_gate, "_redis", must_not_be_called)
    assert await billing_gate.checkout_allowed("anyone") is True


@pytest.mark.asyncio
async def test_with_the_restriction_on_only_members_of_the_set_are_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    members = _Members("acct-1")
    _use(monkeypatch, members, restricted=True)
    assert await billing_gate.checkout_allowed("acct-1") is True
    assert await billing_gate.checkout_allowed("acct-2") is False
    assert members.asked == [
        ("pyvar:billing:checkout:allow", "acct-1"),
        ("pyvar:billing:checkout:allow", "acct-2"),
    ]


@pytest.mark.asyncio
async def test_an_empty_set_allows_nobody(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _Members(), restricted=True)
    assert await billing_gate.checkout_allowed("acct-1") is False


@pytest.mark.asyncio
async def test_no_redis_client_means_nobody_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, None, restricted=True)
    assert await billing_gate.checkout_allowed("acct-1") is False


@pytest.mark.asyncio
async def test_a_redis_failure_means_nobody_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _Broken(), restricted=True)
    assert await billing_gate.checkout_allowed("acct-1") is False

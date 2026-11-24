"""api/billing_gate.py — who may start a Pro checkout while Stripe is in test mode on a public deployment.

Why: pyvar's Stripe webhook acts on every verified checkout.session.completed and has no live/test check, and the
dashboard shows "Upgrade to Pro" to every signed-in free account. With test-mode Stripe keys on prod, anyone could
pay with Stripe's public test card and get Pro's limits for nothing, and a test subscription never lapses by itself.
So where `stripe_checkout_restricted` is true (prod, until Stripe goes live), a checkout may be started only by an
account an operator has put in a Redis set, with no deploy. The operator's command is
scripts/billing_checkout_allow.py (it calls /internal/admin/billing/checkout-allow with an admin token, looks the
account up by its address, and needs no Redis access):

    python scripts/billing_checkout_allow.py --env prod --yes-prod allow  --email <address> --yes
    python scripts/billing_checkout_allow.py --env prod --yes-prod remove --email <address> --yes
    python scripts/billing_checkout_allow.py --env prod --yes-prod list
    python scripts/billing_checkout_allow.py --env prod --yes-prod clear --yes

(Where Redis can be reached, the same set is SADD, SREM, SMEMBERS and DEL on pyvar:billing:checkout:allow.)

The account id is users.external_id, the `sub` of the account's session token. It is an opaque id, not an address.

Everyone else gets the answer they get today while billing is not configured (a returned 503, billing.py), so nothing
visible changes for them. Only the checkout is gated: a Stripe customer, and with it an upgrade, exists only after a
checkout, and the portal route needs a customer.

FAILS CLOSED, like the assistant's kill switch (api/assistant/store.py) and the opposite of the key cache: if Redis
is unconfigured or cannot be read, nobody is allowed. It protects what an upgrade gives away, so "cannot tell" is no.
Nothing about the visitor is logged here except the opaque account id the route already logs.
"""

from __future__ import annotations

from typing import Any

import structlog

from config import get_settings

logger = structlog.get_logger()
cfg = get_settings()

# A Redis set of account ids (users.external_id). Managed with scripts/billing_checkout_allow.py; see the module docstring.
CHECKOUT_ALLOW_KEY = "pyvar:billing:checkout:allow"


def _redis() -> Any:
    # imported here, not at module level: api.routes.caching imports from api.middleware
    from api.routes.caching import _get_redis_client

    return _get_redis_client()


class AllowListUnavailable(Exception):
    """The allow set could not be reached or read. The admin route answers 503; nothing was changed."""


def _admin_client() -> Any:
    """The Redis client for the operator's commands. Unlike the checkout check, a failure here is an error to show."""
    client = _redis()
    if client is None:
        raise AllowListUnavailable("no Redis client")
    return client


async def allow_list_members() -> list[str]:
    """Every account id in the allow set, sorted. Raises AllowListUnavailable."""
    try:
        return sorted(await _admin_client().smembers(CHECKOUT_ALLOW_KEY))
    except AllowListUnavailable:
        raise
    except Exception as exc:  # any storage failure is "unavailable": the operator is told
        raise AllowListUnavailable(type(exc).__name__) from exc


async def allow_list_add(user_id: str) -> None:
    """Put an account id in the allow set. Raises AllowListUnavailable."""
    try:
        await _admin_client().sadd(CHECKOUT_ALLOW_KEY, user_id)
    except AllowListUnavailable:
        raise
    except Exception as exc:
        raise AllowListUnavailable(type(exc).__name__) from exc


async def allow_list_remove(user_id: str) -> None:
    """Take an account id out of the allow set. Raises AllowListUnavailable."""
    try:
        await _admin_client().srem(CHECKOUT_ALLOW_KEY, user_id)
    except AllowListUnavailable:
        raise
    except Exception as exc:
        raise AllowListUnavailable(type(exc).__name__) from exc


async def allow_list_clear() -> None:
    """Empty the allow set: every account is refused at once. Raises AllowListUnavailable."""
    try:
        await _admin_client().delete(CHECKOUT_ALLOW_KEY)
    except AllowListUnavailable:
        raise
    except Exception as exc:
        raise AllowListUnavailable(type(exc).__name__) from exc


async def checkout_allowed(user_id: str) -> bool:
    """True when the restriction is off, or `user_id` is in the operator's allow set; False when it cannot be told."""
    if not cfg.stripe_checkout_restricted:
        return True
    client = _redis()
    if client is None:
        logger.warning("billing_checkout_gate_unreadable")
        return False
    try:
        return bool(await client.sismember(CHECKOUT_ALLOW_KEY, user_id))
    except Exception:  # noqa: BLE001 - any storage failure means "cannot tell", which is no
        logger.warning("billing_checkout_gate_unreadable")
        return False

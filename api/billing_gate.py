"""api/billing_gate.py — who may start a Pro checkout while Stripe is in test mode on a public deployment.

Why: pyvar's Stripe webhook acts on every verified checkout.session.completed and has no live/test check, and the
dashboard shows "Upgrade to Pro" to every signed-in free account. With test-mode Stripe keys on prod, anyone could
pay with Stripe's public test card and get Pro's limits for nothing, and a test subscription never lapses by itself.
So where `stripe_checkout_restricted` is true (prod, until Stripe goes live), a checkout may be started only by an
account an operator has put in a Redis set, by hand and with no deploy:

    redis-cli SADD     pyvar:billing:checkout:allow <account id>
    redis-cli SREM     pyvar:billing:checkout:allow <account id>
    redis-cli SMEMBERS pyvar:billing:checkout:allow

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

# A Redis set of account ids (users.external_id). Managed by hand; see the module docstring.
CHECKOUT_ALLOW_KEY = "pyvar:billing:checkout:allow"


def _redis() -> Any:
    # imported here, not at module level: api.routes.caching imports from api.middleware
    from api.routes.caching import _get_redis_client

    return _get_redis_client()


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

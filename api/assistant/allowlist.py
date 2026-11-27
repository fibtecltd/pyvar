"""
api/assistant/allowlist.py — the operator's side of the typed assistant's allowlist

Reasoning:
- While `assistant_allowlist_enabled` is on (the first weeks of the typed assistant in prod), only signed-in accounts
  in the Redis set `pyvar:assistant:allow` may ask a typed question. The READ is api/assistant/store.py::is_allowed,
  called from api/assistant/deps.py::require_allowed on every question, and it fails closed. This module is the
  WRITE side, called only by the admin route /internal/admin/assistant/allow (api/routes/internal.py), which the
  operator reaches with scripts/assistant_allow.py (wrapper: scripts/ops/assistant-allow.sh) and which needs no
  Redis access:

      python scripts/assistant_allow.py --env prod --yes-prod allow  --email <address> --yes
      python scripts/assistant_allow.py --env prod --yes-prod remove --email <address> --yes
      python scripts/assistant_allow.py --env prod --yes-prod list
      python scripts/assistant_allow.py --env prod --yes-prod clear --yes

  (Where Redis can be reached, the same set is SADD, SREM, SMEMBERS and DEL on pyvar:assistant:allow.)
- The set holds users.external_id, the `sub` of the account's session token: an opaque id, never an address. The
  route finds the account by its address and keeps only that id.
- It uses the same Redis client as the spend and the kill switch (api/assistant/store.py), so a deployment that can
  answer questions can also be managed.
- Unlike the question path, a failure here is an error to show the operator (AllowListUnavailable, a 503 from the
  route, nothing changed), not a silent "no".
"""

from __future__ import annotations

from typing import Any

from api.assistant.store import ALLOW_KEY, get_store


class AllowListUnavailable(Exception):
    """The allowlist could not be reached or read. The admin route answers 503; nothing was changed."""


def _redis() -> Any:
    """The assistant store's async Redis client (a test replaces this function)."""
    return get_store().client()


def _admin_client() -> Any:
    try:
        client = _redis()
    except Exception as exc:  # noqa: BLE001 - an unbuildable client is "unavailable"
        raise AllowListUnavailable(type(exc).__name__) from exc
    if client is None:
        raise AllowListUnavailable("no Redis client")
    return client


async def members() -> list[str]:
    """Every account id in the allowlist, sorted. Raises AllowListUnavailable."""
    try:
        return sorted(await _admin_client().smembers(ALLOW_KEY))
    except AllowListUnavailable:
        raise
    except Exception as exc:  # any storage failure is "unavailable": the operator is told
        raise AllowListUnavailable(type(exc).__name__) from exc


async def add(user_id: str) -> None:
    """Put an account id in the allowlist. Raises AllowListUnavailable."""
    try:
        await _admin_client().sadd(ALLOW_KEY, user_id)
    except AllowListUnavailable:
        raise
    except Exception as exc:
        raise AllowListUnavailable(type(exc).__name__) from exc


async def remove(user_id: str) -> None:
    """Take an account id out of the allowlist. Raises AllowListUnavailable."""
    try:
        await _admin_client().srem(ALLOW_KEY, user_id)
    except AllowListUnavailable:
        raise
    except Exception as exc:
        raise AllowListUnavailable(type(exc).__name__) from exc


async def clear() -> None:
    """Empty the allowlist: every account is refused at once. Raises AllowListUnavailable."""
    try:
        await _admin_client().delete(ALLOW_KEY)
    except AllowListUnavailable:
        raise
    except Exception as exc:
        raise AllowListUnavailable(type(exc).__name__) from exc

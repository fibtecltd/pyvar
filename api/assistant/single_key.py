"""api/assistant/single_key.py: Redis reads and deletes that touch one key per command.

Reasoning:
- The cache is ElastiCache Serverless, which runs in cluster mode: a command naming several keys is refused with
  CROSSSLOT unless every key hashes to the same slot, and the typed route's keys (the kill switch, each day's spend,
  the allowlist, the watchdog's per-function and per-writer keys) have no shared hash tag. The first live run of the
  typed route in dev (2026-11-27) answered 503 `assistant_unavailable` on every request because the gate read the
  kill switch and the day's spend with one MGET; the trial lane's code is single-key for the same reason
  (api/middleware/trial.py).
- So the typed route and its watchdog read several keys with one GET each, issued together (one round trip's wait
  for the group, not one per key), and delete several keys with one DEL each. Nothing else changes: a failure of
  any one command raises, exactly as the single MGET or DEL did, so the fail-closed gate and the fail-open watchdog
  keep their policies.
- tests/redis_slots.py makes the test doubles refuse a command over keys in different slots, and
  tests/test_assistant_single_key.py scans this package for the multi-key commands, so the next one fails in CI
  rather than on the first live request.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any


async def get_each(redis: Any, keys: Sequence[str]) -> list[str | None]:
    """The values of `keys`, in order (None for a missing key), by one GET per key."""
    return list(await asyncio.gather(*(redis.get(key) for key in keys)))


async def delete_each(redis: Any, *keys: str) -> int:
    """Delete `keys` by one DEL per key; the number of keys that existed."""
    return sum(await asyncio.gather(*(redis.delete(key) for key in keys)))

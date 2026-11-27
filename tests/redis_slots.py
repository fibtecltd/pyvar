"""Hash slots for the Redis test doubles: a command over keys in different slots is refused, as in cluster mode.

The cache in every deployed environment is ElastiCache Serverless, which runs in cluster mode. A command that names
several keys is answered CROSSSLOT unless all of them hash to the same slot (a `{tag}` inside a key hashes only the
tag). An in-process double that accepts any command hides that: the typed route's gate read two keys with one MGET,
passed every test and answered 503 on every live request (the dev run of 2026-11-27). The doubles in this suite call
`require_one_slot` for every command that takes more than one key, so such a command fails here.
"""

from __future__ import annotations

from collections.abc import Iterable

from redis.exceptions import ClusterCrossSlotError

SLOTS = 16384


def crc16(data: bytes) -> int:
    """CRC-16/XMODEM, the checksum the Redis Cluster specification hashes keys with."""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def hash_slot(key: str) -> int:
    """The cluster slot of `key`; with a non-empty `{tag}` only the tag is hashed."""
    raw = key.encode()
    start = raw.find(b"{")
    if start != -1:
        end = raw.find(b"}", start + 1)
        if end > start + 1:
            raw = raw[start + 1 : end]
    return crc16(raw) % SLOTS


def require_one_slot(keys: Iterable[str]) -> None:
    """Raise what redis-py raises when `keys` do not all hash to one slot: ClusterCrossSlotError (the server's CROSSSLOT
    reply, mapped to it; the live Sentry event of 2026-11-27 shows exactly this class and message).
    """
    slots = {hash_slot(key) for key in keys}
    if len(slots) > 1:
        raise ClusterCrossSlotError(ClusterCrossSlotError.message)

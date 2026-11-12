"""An in-memory stand-in for the async Redis commands the watchdog uses: no server, no network.

Only the commands api/assistant/watchdog.py and api/assistant/store.py call are here, with Redis's return
values. `ttls` records the last expiry set on each key, so a test can assert that nothing is kept forever;
`fail` makes every command raise, to test the fail-open policy.
"""

from __future__ import annotations

from typing import Any


class FakeWatchRedis:
    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, int]] = {}
        self.lists: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}
        self.fail = False
        self.commands: list[str] = []

    def _check(self, name: str) -> None:
        self.commands.append(name)
        if self.fail:
            raise ConnectionError("redis is down")

    # strings
    async def get(self, key: str) -> str | None:
        self._check("get")
        return self.strings.get(key)

    async def mget(self, keys: list[str]) -> list[str | None]:
        self._check("mget")
        return [self.strings.get(key) for key in keys]

    async def set(
        self, key: str, value: str, ex: int | None = None, nx: bool = False
    ) -> bool | None:
        self._check("set")
        if nx and key in self.strings:
            return None
        self.strings[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def incrby(self, key: str, amount: int) -> int:
        self._check("incrby")
        self.strings[key] = str(int(self.strings.get(key, 0)) + amount)
        return int(self.strings[key])

    async def decrby(self, key: str, amount: int) -> int:
        return await self.incrby(key, -amount)

    async def delete(self, *keys: str) -> int:
        self._check("delete")
        removed = 0
        for key in keys:
            for store in (self.strings, self.hashes, self.lists):
                if key in store:
                    del store[key]
                    removed += 1
            self.ttls.pop(key, None)
        return removed

    async def expire(self, key: str, seconds: int) -> bool:
        self._check("expire")
        self.ttls[key] = seconds
        return True

    # hashes
    async def hincrby(self, key: str, field: str, amount: int) -> int:
        self._check("hincrby")
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = bucket.get(field, 0) + amount
        return bucket[field]

    async def hgetall(self, key: str) -> dict[str, str]:
        self._check("hgetall")
        return {field: str(value) for field, value in self.hashes.get(key, {}).items()}

    # lists
    async def rpush(self, key: str, *values: Any) -> int:
        self._check("rpush")
        bucket = self.lists.setdefault(key, [])
        bucket.extend(str(v) for v in values)
        return len(bucket)

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        self._check("lrange")
        bucket = self.lists.get(key, [])
        stop = len(bucket) if stop == -1 else stop + 1
        return bucket[start:stop]

    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        self._check("ltrim")
        bucket = self.lists.get(key, [])
        keep = bucket[start:] if start < 0 and stop == -1 else bucket[start : stop + 1]
        self.lists[key] = keep
        return True

    def all_keys(self) -> set[str]:
        return set(self.strings) | set(self.hashes) | set(self.lists)

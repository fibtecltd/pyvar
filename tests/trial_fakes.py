"""tests/trial_fakes.py — an in-process Redis for the trial lane's tests (never a real server).

Reasoning:
- CLAUDE.md section 5 forbids a real backing service in tests, and the lane's budgets are the thing most worth
  testing. The lane uses only single-key commands (get, set with nx/ex/px, incrby, decrby, expire, delete) and
  WATCH/MULTI/EXEC on one key, so this double implements exactly those, with the semantics that matter:
  keys expire against an injected clock, a pipeline that WATCHed a key fails with WatchError when the key was
  written in between, and a command inside MULTI is queued until EXEC.
- `on_execute` lets a test write to a key between a pipeline's WATCH and its EXEC, which is how a second API
  task would interfere; `fail` makes every command raise, like an unreachable cache.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from redis.exceptions import WatchError


class FakeClock:
    """A settable time source; the store and the double share one."""

    def __init__(self, start: float) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeTrialRedis:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.data: dict[str, str] = {}
        self.expires_at: dict[str, float] = {}
        self.versions: dict[str, int] = {}
        self.fail = False
        self.on_execute: Callable[[], None] | None = None
        self.commands: list[str] = []

    # -- helpers -----------------------------------------------------------------------------------------

    def _check(self, name: str) -> None:
        self.commands.append(name)
        if self.fail:
            raise ConnectionError("redis is down")

    def _purge(self, key: str) -> None:
        deadline = self.expires_at.get(key)
        if deadline is not None and self.clock() >= deadline:
            self.data.pop(key, None)
            self.expires_at.pop(key, None)

    def _touch(self, key: str) -> None:
        self.versions[key] = self.versions.get(key, 0) + 1

    def ttl_seconds(self, key: str) -> float | None:
        self._purge(key)
        deadline = self.expires_at.get(key)
        return None if deadline is None else deadline - self.clock()

    # -- commands ----------------------------------------------------------------------------------------

    async def get(self, key: str) -> str | None:
        self._check("get")
        self._purge(key)
        return self.data.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        nx: bool = False,
        ex: int | None = None,
        px: int | None = None,
    ) -> bool | None:
        self._check("set")
        self._purge(key)
        if nx and key in self.data:
            return None
        self.data[key] = str(value)
        self.expires_at.pop(key, None)
        if ex is not None:
            self.expires_at[key] = self.clock() + ex
        if px is not None:
            self.expires_at[key] = self.clock() + px / 1000.0
        self._touch(key)
        return True

    async def incrby(self, key: str, amount: int) -> int:
        self._check("incrby")
        self._purge(key)
        self.data[key] = str(int(self.data.get(key, "0")) + amount)
        self._touch(key)
        return int(self.data[key])

    async def decrby(self, key: str, amount: int) -> int:
        return await self.incrby(key, -amount)

    async def expire(self, key: str, seconds: int) -> bool:
        self._check("expire")
        self._purge(key)
        if key not in self.data:
            return False
        self.expires_at[key] = self.clock() + seconds
        return True

    async def delete(self, *keys: str) -> int:
        self._check("delete")
        removed = 0
        for key in keys:
            self._purge(key)
            if key in self.data:
                del self.data[key]
                self.expires_at.pop(key, None)
                self._touch(key)
                removed += 1
        return removed

    def pipeline(self, transaction: bool = True) -> "FakePipeline":
        return FakePipeline(self)


class FakePipeline:
    """redis.asyncio.Pipeline as the lane uses it: queued commands, and WATCH with immediate reads."""

    def __init__(self, redis: FakeTrialRedis) -> None:
        self.redis = redis
        self.queue: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.watched: dict[str, int] = {}
        self.watching = False
        self.explicit = False

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.reset()

    async def reset(self) -> None:
        self.queue = []
        self.watched = {}
        self.watching = False
        self.explicit = False

    async def watch(self, *keys: str) -> bool:
        self.redis._check("watch")
        self.watched = {key: self.redis.versions.get(key, 0) for key in keys}
        self.watching = True
        return True

    async def unwatch(self) -> bool:
        self.watched = {}
        self.watching = False
        return True

    def multi(self) -> None:
        self.explicit = True

    def _command(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if self.watching and not self.explicit:
            return getattr(self.redis, name)(*args, **kwargs)  # a coroutine: the caller awaits it
        self.queue.append((name, args, kwargs))
        return self

    def get(self, key: str) -> Any:
        return self._command("get", key)

    def set(self, key: str, value: Any, **kwargs: Any) -> Any:
        return self._command("set", key, value, **kwargs)

    def incrby(self, key: str, amount: int) -> Any:
        return self._command("incrby", key, amount)

    def expire(self, key: str, seconds: int) -> Any:
        return self._command("expire", key, seconds)

    async def execute(self) -> list[Any]:
        self.redis._check("execute")
        if self.redis.on_execute is not None:
            hook, self.redis.on_execute = self.redis.on_execute, None
            hook()
        for key, version in self.watched.items():
            if self.redis.versions.get(key, 0) != version:
                await self.reset()
                raise WatchError("a watched key changed")
        results = [await getattr(self.redis, name)(*a, **kw) for name, a, kw in self.queue]
        await self.reset()
        return results

"""tests/test_job_done_bus.py — the process-wide Pub/Sub subscriber behind WS /var/stream.

Reasoning:
- One subscription per API process wakes every waiting socket (api/routes/var.py _JobDoneBus).
  Phase 0 on dev and a local reproduction against a TLS Redis showed why: a Redis client and
  subscription per socket cost about 1.7 MiB per socket and 1.2 to 1.8 Redis connections per
  socket; one shared subscriber costs about 0.6 MiB per socket and none.
- A message only wakes a waiter, so these tests check wiring and health, not results: which
  waiter wakes, what the subscriber subscribes to, that it reports itself unhealthy when Redis
  fails (the route then polls at the short interval) and that it reconnects.
- No Redis: the client is replaced by a stand-in whose Pub/Sub yields what the test pushes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.routes.var as var_routes

_REAL_SLEEP = asyncio.sleep


class _FakePubSub:
    def __init__(self, fail_subscribe=None):
        self.psubscribe = AsyncMock(side_effect=fail_subscribe)
        self.aclose = AsyncMock()
        self._queue: asyncio.Queue = asyncio.Queue()

    def push(self, message):
        self._queue.put_nowait(message)

    async def listen(self):
        while True:
            yield await self._queue.get()


def _client_for(*pubsubs):
    """aioredis.Redis.from_url stand-in: each call hands out the next client/Pub/Sub pair."""
    clients = []
    for pubsub in pubsubs:
        client = MagicMock()
        client.pubsub = MagicMock(return_value=pubsub)
        client.aclose = AsyncMock()
        clients.append(client)
    return MagicMock(side_effect=clients), clients


async def _settle():
    for _ in range(5):
        await _REAL_SLEEP(0)


def _message(task_id, kind="pmessage", channel_type=bytes):
    channel = f"pyvar:var-job-done:{task_id}"
    return {
        "type": kind,
        "pattern": b"pyvar:var-job-done:*",
        "channel": channel.encode() if channel_type is bytes else channel,
        "data": b"success",
    }


async def test_subscribes_once_to_the_pattern_using_the_shared_redis_url():
    bus = var_routes._JobDoneBus()
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with (
        patch.object(var_routes.aioredis.Redis, "from_url", from_url),
        patch.object(var_routes, "redis_url", return_value="rediss://shared-cache:6379/0"),
    ):
        bus.register("task-1")
        bus.register("task-2")
        await _settle()
        await bus.close()

    assert from_url.call_count == 1  # one client for every waiter
    assert from_url.call_args.args[0] == "rediss://shared-cache:6379/0"
    pubsub.psubscribe.assert_awaited_once_with("pyvar:var-job-done:*")


async def test_a_message_wakes_only_the_task_it_names():
    bus = var_routes._JobDoneBus()
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with patch.object(var_routes.aioredis.Redis, "from_url", from_url):
        woken = bus.register("task-1")
        other = bus.register("task-2")
        await _settle()
        assert bus.healthy
        pubsub.push(_message("task-1"))
        await _settle()
        await bus.close()

    assert woken.is_set()
    assert not other.is_set()


async def test_string_channels_and_every_waiter_of_a_task_are_handled():
    bus = var_routes._JobDoneBus()
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with patch.object(var_routes.aioredis.Redis, "from_url", from_url):
        first = bus.register("task-1")
        second = bus.register("task-1")  # two sockets on the same job
        await _settle()
        pubsub.push(_message("task-1", channel_type=str))
        await _settle()
        await bus.close()

    assert first.is_set() and second.is_set()


async def test_subscription_confirmations_wake_nobody():
    bus = var_routes._JobDoneBus()
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with patch.object(var_routes.aioredis.Redis, "from_url", from_url):
        waiter = bus.register("task-1")
        await _settle()
        pubsub.push(_message("task-1", kind="psubscribe"))
        await _settle()
        await bus.close()

    assert not waiter.is_set()


async def test_unregister_forgets_the_waiter():
    bus = var_routes._JobDoneBus()
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with patch.object(var_routes.aioredis.Redis, "from_url", from_url):
        event = bus.register("task-1")
        await _settle()
        bus.unregister("task-1", event)
        pubsub.push(_message("task-1"))
        await _settle()
        await bus.close()

    assert bus._waiters == {}
    assert not event.is_set()


async def test_reports_unhealthy_while_redis_is_down_and_reconnects():
    """A failed subscribe flips `healthy` off (the route then polls at the short interval),
    the subscriber backs off and tries again, and `healthy` returns once it is subscribed."""
    bus = var_routes._JobDoneBus()
    down = _FakePubSub(fail_subscribe=ConnectionError("cache unreachable"))
    up = _FakePubSub()
    from_url, clients = _client_for(down, up)
    sleeps = []

    async def quick_sleep(seconds):
        sleeps.append(seconds)
        await _REAL_SLEEP(0)

    with (
        patch.object(var_routes.aioredis.Redis, "from_url", from_url),
        patch.object(var_routes.asyncio, "sleep", quick_sleep),
    ):
        waiter = bus.register("task-1")
        await _settle()
        assert bus.healthy
        up.push(_message("task-1"))
        await _settle()
        await bus.close()

    assert from_url.call_count == 2
    assert sleeps == [1.0]  # the first back-off
    assert waiter.is_set()
    clients[0].aclose.assert_awaited()  # the failed attempt does not leak its client
    down.aclose.assert_awaited()


async def test_back_off_doubles_and_is_capped():
    bus = var_routes._JobDoneBus()
    failing = [_FakePubSub(fail_subscribe=ConnectionError("down")) for _ in range(8)]
    from_url, _clients = _client_for(*failing)
    sleeps = []

    async def quick_sleep(seconds):
        sleeps.append(seconds)
        await _REAL_SLEEP(0)

    with (
        patch.object(var_routes.aioredis.Redis, "from_url", from_url),
        patch.object(var_routes.asyncio, "sleep", quick_sleep),
    ):
        bus.register("task-1")
        for _ in range(60):
            await _REAL_SLEEP(0)
            if len(sleeps) >= 7:
                break
        await bus.close()

    assert sleeps[:7] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
    assert not bus.healthy


async def test_close_stops_the_reader_and_a_later_register_starts_a_new_one():
    bus = var_routes._JobDoneBus()
    first, second = _FakePubSub(), _FakePubSub()
    from_url, _clients = _client_for(first, second)

    with patch.object(var_routes.aioredis.Redis, "from_url", from_url):
        bus.register("task-1")
        await _settle()
        reader = bus._reader
        await bus.close()
        assert reader.done()
        assert not bus.healthy

        bus.register("task-2")
        await _settle()
        assert bus.healthy
        assert bus._reader is not reader
        await bus.close()

    assert from_url.call_count == 2


@pytest.mark.parametrize("pending", [0, 3])
async def test_wait_for_wake_reports_whether_a_push_arrived(pending):
    event = asyncio.Event()
    if pending:
        event.set()
    woken = await var_routes._wait_for_wake(event, timeout=0.05)
    assert woken is bool(pending)
    assert not event.is_set()  # a consumed push does not wake the next wait

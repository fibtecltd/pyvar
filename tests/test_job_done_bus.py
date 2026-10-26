"""tests/test_job_done_bus.py — the process-wide Pub/Sub connection behind WS /var/stream.

Reasoning:
- One Redis connection per API process wakes every waiting socket (api/routes/var.py
  _JobDoneBus). Phase 0 on dev and a local reproduction against a TLS Redis showed why: a client
  and subscription per socket cost about 1.7 MiB per socket and 1.2 to 1.8 Redis connections per
  socket; one shared connection costs about 0.6 MiB per socket and none.
- It subscribes to one channel per waiting job with SUBSCRIBE. The first version used PSUBSCRIBE,
  which the ElastiCache Serverless cache refuses ("unknown command"), and its retry loop spun
  once a second (Phase 0f): sending a subscription proves nothing, because the server's refusal
  arrives on the read. The fake below models that: it accepts the send and fails the next read.
- A message only wakes a waiter, so these tests check wiring and health, not results: which
  waiter wakes, what is subscribed and when it is dropped, that `healthy` follows the server's
  confirmation, and that the back-off grows until one arrives.
- No Redis: the client is replaced by a stand-in whose Pub/Sub yields what the test pushes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ResponseError

import api.routes.var as var_routes

_REAL_SLEEP = asyncio.sleep


class _FakePubSub:
    """Records subscribe/unsubscribe and answers like a server: a confirmation per channel, or,
    when `refuse` is given, that error on the next read (the send itself succeeds)."""

    def __init__(self, refuse=None):
        self.subscribed: set[str] = set()
        self.subscribe_calls: list[tuple] = []
        self.unsubscribe_calls: list[tuple] = []
        self.get_message_calls = 0
        self.aclose = AsyncMock()
        self._refuse = refuse
        self._queue: asyncio.Queue = asyncio.Queue()

    async def subscribe(self, *channels):
        self.subscribe_calls.append(channels)
        self.subscribed.update(channels)
        if self._refuse is not None:
            self._queue.put_nowait(self._refuse)
            return
        for channel in channels:
            self._queue.put_nowait(
                {"type": "subscribe", "channel": channel.encode(), "data": len(self.subscribed)}
            )

    async def unsubscribe(self, *channels):
        self.unsubscribe_calls.append(channels)
        self.subscribed.difference_update(channels)

    def push(self, task_id, channel_type=bytes):
        channel = f"pyvar:var-job-done:{task_id}"
        self._queue.put_nowait(
            {
                "type": "message",
                "channel": channel.encode() if channel_type is bytes else channel,
                "data": b"success",
            }
        )

    async def get_message(self, ignore_subscribe_messages=False, timeout=0.0):
        self.get_message_calls += 1
        try:
            item = await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            return None
        if isinstance(item, Exception):
            raise item
        return item


def _client_for(*pubsubs):
    """aioredis.Redis.from_url stand-in: each call hands out the next client/Pub/Sub pair."""
    clients = []
    for pubsub in pubsubs:
        client = MagicMock()
        client.pubsub = MagicMock(return_value=pubsub)
        client.aclose = AsyncMock()
        clients.append(client)
    return MagicMock(side_effect=clients), clients


@pytest.fixture
async def bus():
    """A fresh subscriber; its reader is stopped even when the test fails."""
    instance = var_routes._JobDoneBus()
    yield instance
    await instance.close()


@pytest.fixture(autouse=True)
def _quick_reader():
    """Short reads, so the reader applies changes and notices closes within milliseconds."""
    with (
        patch.object(var_routes, "_BUS_POLL_SECONDS", 0.01),
        patch.object(var_routes, "_BUS_IDLE_TICK_SECONDS", 0.05),
    ):
        yield


async def _settle(rounds=15):
    for _ in range(rounds):
        await _REAL_SLEEP(0.005)


def _recording_sleep(sleeps):
    """asyncio.sleep stand-in that records back-off waits (>= 1 s) and does not wait."""

    async def quick_sleep(seconds):
        if seconds >= 1.0:
            sleeps.append(seconds)
        await _REAL_SLEEP(0)

    return quick_sleep


async def test_one_client_for_every_waiter_subscribes_to_each_jobs_own_channel(bus):
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with (
        patch.object(var_routes.aioredis.Redis, "from_url", from_url),
        patch.object(var_routes, "redis_url", return_value="rediss://shared-cache:6379/0"),
    ):
        await bus.register("task-1")
        await bus.register("task-2")
        await _settle()
        await bus.close()

    assert from_url.call_count == 1  # one client for every waiter
    assert from_url.call_args.args[0] == "rediss://shared-cache:6379/0"
    assert pubsub.subscribed == {"pyvar:var-job-done:task-1", "pyvar:var-job-done:task-2"}


async def test_register_returns_only_after_the_subscription_was_sent(bus):
    """The route reads the job's state right after registering; the channel must be subscribed
    by then, or a completion in between is missed until the next timer tick."""
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with patch.object(var_routes.aioredis.Redis, "from_url", from_url):
        await bus.register("task-1")
        assert "pyvar:var-job-done:task-1" in pubsub.subscribed
        await bus.close()


async def test_a_waiter_wakes_an_idle_reader_at_once(bus):
    """Sockets that arrive together must be subscribed together: a reader that only looked every
    tick would hold them and release them in one burst, and each of them would then read the job
    state on its own thread and its own Redis connection (25 extra TLS connections per worker in
    a local run of 50 sockets)."""
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with (
        patch.object(var_routes.aioredis.Redis, "from_url", from_url),
        patch.object(var_routes, "_BUS_IDLE_TICK_SECONDS", 30.0),
    ):
        first = await bus.register("task-1")
        await _settle()
        bus.unregister("task-1", first)  # the reader now idles on its (long) tick
        await _settle()
        await asyncio.wait_for(bus.register("task-2"), timeout=1.0)  # not the 30 s tick
        assert "pyvar:var-job-done:task-2" in pubsub.subscribed


async def test_a_message_wakes_only_the_task_it_names(bus):
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with patch.object(var_routes.aioredis.Redis, "from_url", from_url):
        woken = await bus.register("task-1")
        other = await bus.register("task-2")
        await _settle()
        pubsub.push("task-1")
        await _settle()
        await bus.close()

    assert woken.is_set()
    assert not other.is_set()


async def test_string_channels_and_every_waiter_of_a_task_are_handled(bus):
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with patch.object(var_routes.aioredis.Redis, "from_url", from_url):
        first = await bus.register("task-1")
        second = await bus.register("task-1")  # two sockets on the same job
        await _settle()
        pubsub.push("task-1", channel_type=str)
        await _settle()
        await bus.close()

    assert first.is_set() and second.is_set()
    assert len(pubsub.subscribe_calls) == 1  # one subscription serves both


async def test_healthy_follows_the_servers_confirmation(bus):
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with patch.object(var_routes.aioredis.Redis, "from_url", from_url):
        assert not bus.healthy
        await bus.register("task-1")
        await _settle()
        assert bus.healthy  # the confirmation arrived
        await bus.close()
    assert not bus.healthy


async def test_a_refusal_that_arrives_on_the_read_keeps_the_back_off_growing(bus):
    """The Phase 0f bug. The server accepts the send and refuses on the read ("unknown command"),
    so resetting the back-off after the send retried every second for ever, one TLS connection
    each. It must reset only on a confirmation, so the waits double up to the cap."""
    refusing = [_FakePubSub(refuse=ResponseError("unknown command 'subscribe'")) for _ in range(8)]
    from_url, clients = _client_for(*refusing)
    sleeps = []

    with (
        patch.object(var_routes.aioredis.Redis, "from_url", from_url),
        patch.object(var_routes.asyncio, "sleep", _recording_sleep(sleeps)),
    ):
        await bus.register("task-1")
        for _ in range(400):
            await _REAL_SLEEP(0.005)
            assert not bus.healthy  # sending a subscription is not a subscription
            if len(sleeps) >= 7:
                break
        await bus.close()

    assert sleeps[:7] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
    for client, pubsub in zip(clients, refusing, strict=False):
        if pubsub.subscribe_calls:  # every attempted connection was closed again
            client.aclose.assert_awaited()
            pubsub.aclose.assert_awaited()


async def test_back_off_resets_once_a_subscription_is_confirmed_again(bus):
    first = _FakePubSub(refuse=ResponseError("unknown command"))
    second = _FakePubSub(refuse=ResponseError("unknown command"))
    working = _FakePubSub()
    third = _FakePubSub(refuse=ResponseError("connection reset"))
    from_url, _clients = _client_for(first, second, working, third)
    sleeps = []

    with (
        patch.object(var_routes.aioredis.Redis, "from_url", from_url),
        patch.object(var_routes.asyncio, "sleep", _recording_sleep(sleeps)),
    ):
        await bus.register("task-1")
        for _ in range(400):
            await _REAL_SLEEP(0.005)
            if bus.healthy:
                break
        assert bus.healthy
        # now the working connection drops: the next wait starts from 1 s again
        working._queue.put_nowait(ConnectionError("dropped"))
        for _ in range(400):
            await _REAL_SLEEP(0.005)
            if len(sleeps) >= 3:
                break
        await bus.close()

    assert sleeps[:3] == [1.0, 2.0, 1.0]


async def test_a_reconnect_subscribes_every_waiter_again_and_recovers(bus):
    down = _FakePubSub(refuse=ConnectionError("cache unreachable"))
    up = _FakePubSub()
    from_url, _clients = _client_for(down, up)
    sleeps = []

    with (
        patch.object(var_routes.aioredis.Redis, "from_url", from_url),
        patch.object(var_routes.asyncio, "sleep", _recording_sleep(sleeps)),
    ):
        first = await bus.register("task-1")
        second = await bus.register("task-2")
        for _ in range(400):
            await _REAL_SLEEP(0.005)
            if bus.healthy:
                break
        assert bus.healthy
        up.push("task-2")
        await _settle()
        await bus.close()

    assert up.subscribed == {"pyvar:var-job-done:task-1", "pyvar:var-job-done:task-2"}
    assert second.is_set() and not first.is_set()
    assert sleeps == [1.0]


async def test_a_channel_is_dropped_when_its_last_waiter_leaves(bus):
    pubsub = _FakePubSub()
    from_url, _clients = _client_for(pubsub)

    with patch.object(var_routes.aioredis.Redis, "from_url", from_url):
        one = await bus.register("task-1")
        two = await bus.register("task-1")
        other = await bus.register("task-2")
        await _settle()
        bus.unregister("task-1", one)
        await _settle()
        assert pubsub.unsubscribe_calls == []  # another socket still waits for task-1
        bus.unregister("task-1", two)
        await _settle()
        assert pubsub.unsubscribe_calls == [("pyvar:var-job-done:task-1",)]
        assert pubsub.subscribed == {"pyvar:var-job-done:task-2"}
        pubsub.push("task-1")  # nobody listens any more
        await _settle()
        await bus.close()

    assert not one.is_set() and not two.is_set() and not other.is_set()
    assert set(bus._waiters) == {"task-2"}


async def test_registering_while_the_connection_is_down_does_not_wait_for_it(bus):
    down = _FakePubSub(refuse=ConnectionError("cache unreachable"))
    from_url, _clients = _client_for(down)
    release = asyncio.Event()

    async def held_sleep(seconds):
        if seconds >= 1.0:
            await release.wait()  # stay in the back-off
        await _REAL_SLEEP(0)

    with (
        patch.object(var_routes.aioredis.Redis, "from_url", from_url),
        patch.object(var_routes.asyncio, "sleep", held_sleep),
        patch.object(var_routes, "_BUS_SUBSCRIBE_WAIT_SECONDS", 5.0),
    ):
        await bus.register("task-1")
        for _ in range(200):
            await _REAL_SLEEP(0.005)
            if not bus.healthy and bus._down:
                break
        # the sockets poll at the short interval meanwhile; they must not queue up behind it
        await asyncio.wait_for(bus.register("task-2"), timeout=0.5)
        release.set()
        await bus.close()


async def test_the_reader_gives_its_connection_back_when_nobody_waits_and_restarts_on_demand(bus):
    first, second = _FakePubSub(), _FakePubSub()
    from_url, clients = _client_for(first, second)

    with (
        patch.object(var_routes.aioredis.Redis, "from_url", from_url),
        patch.object(var_routes, "_BUS_IDLE_CLOSE_SECONDS", 0.05),
    ):
        event = await bus.register("task-1")
        await _settle()
        bus.unregister("task-1", event)
        for _ in range(200):
            await _REAL_SLEEP(0.005)
            if bus._reader.done():
                break
        assert bus._reader.done()
        clients[0].aclose.assert_awaited()
        assert first.get_message_calls > 0

        await bus.register("task-2")
        await _settle()
        assert bus.healthy
        assert "pyvar:var-job-done:task-2" in second.subscribed
        await bus.close()

    assert from_url.call_count == 2


async def test_close_stops_the_reader(bus):
    pubsub = _FakePubSub()
    from_url, clients = _client_for(pubsub)

    with patch.object(var_routes.aioredis.Redis, "from_url", from_url):
        await bus.register("task-1")
        await _settle()
        reader = bus._reader
        await bus.close()

    assert reader.done()
    assert not bus.healthy
    clients[0].aclose.assert_awaited()


@pytest.mark.parametrize("pending", [0, 3])
async def test_wait_for_wake_reports_whether_a_push_arrived(pending):
    event = asyncio.Event()
    if pending:
        event.set()
    woken = await var_routes._wait_for_wake(event, timeout=0.05)
    assert woken is bool(pending)
    assert not event.is_set()  # a consumed push does not wake the next wait

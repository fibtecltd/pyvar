"""tests/test_sqs_message_group.py — every job is published in an SQS message group of its own.

Reasoning:
- The queue is FIFO and kombu puts a message with no group into the group "default"; SQS FIFO lets one
  message per group be in flight, so jobs ran one at a time at any worker count (dev, 2026-11-14:
  352, 364 and 251 jobs a minute at 1, 2 and 4 workers; a real dev message carried "default").
  tasks/var_task.py now sets MessageGroupId to the task id before a message is published.
- These tests follow the real publish path: Celery's apply_async -> the before_task_publish signal -> the
  message dict a virtual transport receives in `_put` (the memory transport here, recorded) -> kombu's
  SQS `_put` against a mocked client. No AWS call is made and no broker is needed.
- The group is only set when the broker is SQS (`_is_sqs_broker`), so the Redis broker used in local
  development is untouched. The tests patch that check, because CI runs with the Redis URL.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from celery import Celery
from kombu.transport import memory

from tasks import var_task


@pytest.fixture
def published() -> Iterator[list[dict[str, Any]]]:
    """Messages that reach a virtual transport's `_put`, recorded; nothing is consumed."""
    messages: list[dict[str, Any]] = []
    original = memory.Channel._put

    def record(self: Any, queue: str, message: dict[str, Any], **kwargs: Any) -> Any:
        messages.append({"queue": queue, "message": message})
        return original(self, queue, message, **kwargs)

    with patch.object(memory.Channel, "_put", record):
        yield messages


@pytest.fixture(scope="module")
def other_app() -> Celery:
    """A throwaway app on the memory broker: the signal is global, so it sees this app's tasks too."""
    app = Celery("group-test", broker="memory://", backend="cache+memory://")
    app.conf.task_default_queue = "group-test.fifo"

    @app.task(name="group_test.noop")
    def noop(value: int) -> int:
        return value

    return app


@pytest.fixture
def connection(other_app: Celery) -> Iterator[Any]:
    """An explicit memory connection.

    Celery prefers the CELERY_BROKER_URL environment variable (CI sets it to Redis) over the `broker=` the app
    was given, so a test that relied on the app's own broker would publish to Redis and record nothing.
    """
    with other_app.connection_for_write("memory://") as conn:
        yield conn


def _group(entry: dict[str, Any]) -> Any:
    return entry["message"]["properties"].get("MessageGroupId")


def test_each_job_gets_its_own_group_equal_to_its_task_id(published, other_app, connection) -> None:
    with patch.object(var_task, "_is_sqs_broker", return_value=True):
        other_app.tasks["group_test.noop"].apply_async(
            args=[1], task_id="job-aaa", connection=connection
        )
        other_app.tasks["group_test.noop"].apply_async(
            args=[2], task_id="job-bbb", connection=connection
        )
    assert [_group(m) for m in published] == ["job-aaa", "job-bbb"]
    assert all(m["queue"] == "group-test.fifo" for m in published)


def test_no_group_is_added_when_the_broker_is_not_sqs(published, other_app, connection) -> None:
    """The test environment's broker is the Redis URL, so the real check is False."""
    assert var_task._is_sqs_broker() is False
    other_app.tasks["group_test.noop"].apply_async(
        args=[1], task_id="job-aaa", connection=connection
    )
    assert _group(published[0]) is None


def test_the_real_task_is_published_with_its_group(published) -> None:
    """The API's own dispatch call (api/routes/var.py) goes through this signal, with the real task."""
    from celery.backends.redis import RedisBackend

    with (
        patch.object(var_task, "_is_sqs_broker", return_value=True),
        patch.object(RedisBackend, "on_task_call", lambda *a, **k: None),
        var_task.celery_app.connection_for_write("memory://") as connection,
    ):
        var_task.compute_var_task.apply_async(
            kwargs={"payload": {}}, task_id="job-real", connection=connection
        )
    assert [_group(m) for m in published] == ["job-real"]


def test_a_group_already_on_the_message_is_kept() -> None:
    properties = {"MessageGroupId": "chosen"}
    with patch.object(var_task, "_is_sqs_broker", return_value=True):
        var_task._one_message_group_per_job(headers={"id": "job-1"}, properties=properties)
    assert properties == {"MessageGroupId": "chosen"}


@pytest.mark.parametrize("headers", [None, {}, {"id": ""}, {"other": "x"}])
def test_nothing_is_added_without_a_task_id(headers) -> None:
    properties: dict[str, Any] = {}
    with patch.object(var_task, "_is_sqs_broker", return_value=True):
        var_task._one_message_group_per_job(headers=headers, properties=properties)
    assert properties == {}


def test_a_missing_properties_dict_is_tolerated() -> None:
    with patch.object(var_task, "_is_sqs_broker", return_value=True):
        var_task._one_message_group_per_job(headers={"id": "job-1"}, properties=None)


def test_the_group_reaches_sqs_send_message(published, other_app, connection) -> None:
    """The message Celery publishes, handed to kombu's SQS `_put`, is sent with that group."""
    pytest.importorskip("boto3")
    sqs_module = pytest.importorskip("kombu.transport.SQS")
    with patch.object(var_task, "_is_sqs_broker", return_value=True):
        other_app.tasks["group_test.noop"].apply_async(
            args=[1], task_id="job-sqs", connection=connection
        )
    message = published[0]["message"]

    with patch.object(sqs_module.Channel, "__init__", lambda self, *a, **k: None):
        channel = sqs_module.Channel()
    client = MagicMock()
    channel.sqs = lambda queue=None: client
    channel._new_queue = lambda queue: "https://sqs.eu-west-1.amazonaws.com/1/" + queue
    channel.canonical_queue_name = lambda queue: queue
    channel.wait_time_seconds = 10
    channel.sqs_base64_encoding = False
    channel._put("pyvar-test-var-jobs.fifo", message)

    sent = client.send_message.call_args.kwargs
    assert sent["MessageGroupId"] == "job-sqs"
    assert len(sent["MessageDeduplicationId"]) == 36  # still unique per send

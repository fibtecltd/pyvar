"""What kombu's SQS transport does with a FIFO message and with a requeue (assumptions the queue design rests on).

Reasoning:
- "One retry for a lost worker" relies on kombu requeueing the SAME SQS message (so SQS's receive count and
  the queue's redrive policy keep counting). If a kombu release started sending a copy instead, the count
  would reset and a poison job could loop forever. This pins the behaviour, against a mocked SQS client.
- It also records the cause of the flat throughput measured on 2026-11-14 (docs/p9-aws-evidence-2026-11-13.md,
  section 7): a message sent with no MessageGroupId goes to the FIFO group "default", and SQS FIFO lets only one
  message per group be in flight. The repository sets no group, and kombu is not pinned (requirements.txt:
  celery>=5.3.6), so the version that is deployed decides; this test documents the installed one.
- The Channel constructor makes a real AWS call (ListQueues), so it is skipped, and only `_put` is run.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("boto3")
sqs_module = pytest.importorskip("kombu.transport.SQS")
Channel = sqs_module.Channel

QUEUE = "pyvar-test-var-jobs.fifo"


@pytest.fixture
def channel():
    with patch.object(Channel, "__init__", lambda self, *a, **k: None):
        chan = Channel()
    client = MagicMock()
    chan.sqs = lambda queue=None: client
    chan._new_queue = lambda queue: "https://sqs.eu-west-1.amazonaws.com/1/" + queue
    chan.canonical_queue_name = lambda queue: queue
    chan.wait_time_seconds = 10
    chan.sqs_base64_encoding = False
    chan.client = client
    return chan


def message(**extra):
    props = extra.pop("props", {})
    return {"body": "x", "properties": {"delivery_tag": "receipt-1", **props}, **extra}


def test_a_message_with_no_group_goes_to_the_default_group(channel):
    channel._put(QUEUE, message())
    sent = channel.client.send_message.call_args.kwargs
    assert sent["MessageGroupId"] == "default"


def test_an_explicit_group_is_used(channel):
    channel._put(QUEUE, message(props={"MessageGroupId": "job-123"}))
    assert channel.client.send_message.call_args.kwargs["MessageGroupId"] == "job-123"


def test_the_deduplication_id_is_unique_per_send(channel):
    channel._put(QUEUE, message())
    channel._put(QUEUE, message())
    ids = [c.kwargs["MessageDeduplicationId"] for c in channel.client.send_message.call_args_list]
    assert len(ids) == 2 and ids[0] != ids[1] and all(len(i) == 36 for i in ids)


def test_a_requeue_keeps_the_same_sqs_message(channel):
    """No new message is sent: the receipt handle's message becomes visible again, so the count goes on."""
    channel._put(QUEUE, message(redelivered=True))
    assert not channel.client.send_message.called
    call = channel.client.change_message_visibility.call_args.kwargs
    assert call["ReceiptHandle"] == "receipt-1"

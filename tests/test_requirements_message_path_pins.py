"""tests/test_requirements_message_path_pins.py — the packages the API and the workers share are pinned.

Reasoning:
- The API publishes Celery messages through kombu to SQS and the workers consume them. The API image is rebuilt
  from requirements.txt on every image-relevant change, while the worker AMIs are baked rarely, so an unpinned
  celery or kombu drifts: the API image of 2026-11-15 had kombu 5.7.0 and celery 5.7.0 and the workers still had
  5.6.2 and 5.6.3 (docs/p9-aws-evidence-2026-11-13.md, section 11).
- This pins that they stay pinned with `==`. The values are the worker AMIs' versions; change them together with
  pyvar-cdk/stacks/ami_stack.py at an intended AMI bake.
"""

from __future__ import annotations

import re
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"
MESSAGE_PATH = {
    "celery": "5.6.3",
    "kombu": "5.6.2",
    "billiard": "4.2.4",
    "amqp": "5.3.1",
    "vine": "5.1.0",
}


def _pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)\s*(#.*)?$", line.strip())
        if match:
            pins[match.group(1).lower()] = match.group(2)
    return pins


def test_celery_and_kombu_and_their_message_path_dependencies_are_pinned_exactly() -> None:
    pins = _pins()
    assert {name: pins.get(name) for name in MESSAGE_PATH} == MESSAGE_PATH


def test_celery_is_not_left_with_an_open_lower_bound() -> None:
    text = REQUIREMENTS.read_text(encoding="utf-8")
    assert not re.search(r"^(celery|kombu)\s*[<>~]", text, flags=re.MULTILINE)

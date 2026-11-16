"""One retry for a job whose worker is lost: the queue's receive limit and Celery's setting agree.

Reasoning:
- tasks/var_task.py sets task_reject_on_worker_lost, so a task whose worker process is lost is requeued
  instead of failed (the dev drill of 2026-11-14 lost 5 of 5 jobs without it). kombu's SQS transport
  requeues the SAME message, so its receive count carries on, and the queue's redrive policy
  (pyvar-cdk/config.py: queue_dlq_max_receive_count) decides how many deliveries a message gets before the
  dead-letter queue. Two deliveries (the first plus ONE retry) is the owner's decision of 2026-11-16: a job
  that keeps killing its worker must not loop. If the number drifts back up, the promise breaks silently, so
  it is pinned here.
- Same approach as tests/test_cdk_assistant_flag.py: the CDK code is read, not run.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

_CDK = Path(__file__).resolve().parents[1] / "pyvar-cdk"


def _cdk_config() -> ModuleType:
    path = _CDK / "config.py"
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    name = "pyvar_cdk_config_for_queue_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.mark.parametrize("env", ["dev", "staging", "prod"])
def test_every_environment_allows_exactly_one_retry(env):
    config = _cdk_config()
    assert config.PyvarConfig.for_env(env).queue_dlq_max_receive_count == 2


def test_the_queue_uses_that_setting_for_its_redrive_policy():
    path = _CDK / "stacks" / "queue_stack.py"
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    source = path.read_text(encoding="utf-8")
    assert re.search(r"max_receive_count\s*=\s*cfg\.queue_dlq_max_receive_count", source)


def test_celery_requeues_lost_workers_and_the_visibility_timeout_still_exceeds_a_job():
    import tasks.var_task as var_task

    assert var_task.celery_app.conf.task_reject_on_worker_lost is True
    assert var_task.celery_app.conf.task_acks_late is True  # without it there is nothing to requeue
    config = _cdk_config()
    # a job that is merely slow must not be redelivered while it still runs (CLAUDE.md 3.2)
    assert config.PyvarConfig.for_env("prod").queue_visibility_timeout_seconds >= 60

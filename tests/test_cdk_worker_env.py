"""tests/test_cdk_worker_env.py — the worker must be told which bucket to offload to.

Reasoning:
- tasks/var_task.py writes a result above cfg.s3_result_offload_threshold to
  cfg.s3_bucket and the API presigns from cfg.s3_bucket. config.py defaults it to
  "pyvar-results", which does not exist, so a service that is not given S3_BUCKET
  fails every offload with NoSuchBucket. The failure is a WARNING that falls back to
  an inline loss_dist (about 22 bytes per simulation, 10.9 MB at 500_000), so nothing
  alerts. api_stack.py set S3_BUCKET; compute_stack.py's worker env file did not,
  found by the Phase 0c run on dev.
- Same approach as tests/test_data_residency.py: the CDK source is parsed as text, so
  no aws-cdk-lib import is needed in the application test environment.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_STACKS = Path(__file__).resolve().parents[1] / "pyvar-cdk" / "stacks"

# Both stacks must hand the SAME bucket to the app: the worker writes, the API presigns.
_BUCKET_VALUE = "data.result_bucket.bucket_name"


def _read(name: str) -> str:
    path = _STACKS / name
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    return path.read_text(encoding="utf-8")


def test_worker_env_file_sets_s3_bucket_to_the_result_bucket():
    source = _read("compute_stack.py")
    block = source.split("celery_env_block = (", 1)[1].split("\n        )\n", 1)[0]
    match = re.search(r'f?"S3_BUCKET=\{([^}]+)\}\\n"', block)
    assert match, "worker celery.env has no S3_BUCKET line: offloads fall back to 'pyvar-results'"
    assert match.group(1) == _BUCKET_VALUE


def test_api_and_worker_use_the_same_bucket_expression():
    api = _read("api_stack.py")
    match = re.search(r'"S3_BUCKET":\s*([\w.]+),', api)
    assert match, "api_stack.py no longer sets S3_BUCKET"
    assert match.group(1) == _BUCKET_VALUE


def test_worker_role_can_write_the_bucket_it_is_told_to_use():
    source = _read("compute_stack.py")
    assert "data.result_bucket.grant_put(worker_role)" in source

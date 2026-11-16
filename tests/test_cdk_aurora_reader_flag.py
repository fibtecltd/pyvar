"""tests/test_cdk_aurora_reader_flag.py — the Aurora reader instance is one flag per environment.

Reasoning:
- Each Aurora cluster has one serverless v2 reader. It bills the cluster's minimum capacity all month
  whether or not anything connects, and the application connects only to the cluster (writer) endpoint
  from the database secret. pyvar-cdk/config.py carries `aurora_reader_enabled`; data_stack.py builds
  the readers list from it.
- The default is True so that a new environment, and prod, keep the failover target. Only the "dev"
  override sets False.
- Same approach as tests/test_cdk_assistant_flag.py: the CDK code is read, not run, so aws-cdk-lib is
  not needed in the application test environment.
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
    name = "pyvar_cdk_config_for_reader_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def test_only_dev_loses_the_reader_and_prod_and_staging_keep_it() -> None:
    config = _cdk_config()
    flags = {
        env: config.PyvarConfig.for_env(env).aurora_reader_enabled
        for env in ("dev", "staging", "prod")
    }
    assert flags == {"dev": False, "staging": True, "prod": True}


def test_the_default_keeps_the_reader_so_a_new_environment_has_a_failover_target() -> None:
    config = _cdk_config()
    assert config.PyvarConfig(env_name="x", account="1").aurora_reader_enabled is True


def test_the_cluster_builds_its_readers_list_from_the_flag() -> None:
    path = _CDK / "stacks" / "data_stack.py"
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    source = path.read_text(encoding="utf-8")
    assert re.search(
        r"if cfg\.aurora_reader_enabled\s+else \[\]", source
    ), "data_stack.py must pass readers=[] when cfg.aurora_reader_enabled is false"

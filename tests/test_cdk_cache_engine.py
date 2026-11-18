"""tests/test_cdk_cache_engine.py — the ElastiCache engine is one setting per environment.

Reasoning:
- ElastiCache Serverless bills a minimum of data stored (Redis OSS 1 GB, Valkey 100 MB). The two
  caches hold under 2 MB (docs/p9-aws-evidence-2026-11-13.md section 13), so the minimum is the whole
  bill. pyvar-cdk/config.py carries `cache_engine` and `cache_major_engine_version`; data_stack.py
  passes both to the cache.
- Dev moved to Valkey on 2026-11-17 and prod followed on 2026-11-18 (owner decisions) once dev had run
  cleanly; staging keeps Redis because no staging environment is deployed.
- The switch must be an IN-PLACE update. CloudFormation replaces a serverless cache when its name
  changes, and replaces any resource when its logical ID changes; a replacement would give a new
  endpoint and an empty cache. So the logical ID and the name are pinned here.
- Same approach as tests/test_cdk_aurora_reader_flag.py: the CDK code is read, not run, so
  aws-cdk-lib is not needed in the application test environment.
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
    name = "pyvar_cdk_config_for_cache_engine_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _data_stack_source() -> str:
    path = _CDK / "stacks" / "data_stack.py"
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    return path.read_text(encoding="utf-8")


def test_dev_and_prod_are_on_valkey_and_staging_stays_on_redis() -> None:
    config = _cdk_config()
    engines = {
        env: (
            config.PyvarConfig.for_env(env).cache_engine,
            config.PyvarConfig.for_env(env).cache_major_engine_version,
        )
        for env in ("dev", "staging", "prod")
    }
    assert engines == {
        "dev": ("valkey", "7"),
        "staging": ("redis", None),
        "prod": ("valkey", "7"),
    }


def test_the_default_is_redis_with_no_version_so_a_new_environment_changes_nothing() -> None:
    config = _cdk_config()
    cfg = config.PyvarConfig(env_name="x", account="1")
    assert (cfg.cache_engine, cfg.cache_major_engine_version) == ("redis", None)


def test_the_first_valkey_version_is_the_one_aws_can_roll_back_from() -> None:
    # AWS supports rolling back only from Valkey 7.2 to Redis OSS 7.1 (ElastiCache User Guide,
    # "Upgrading engine versions including cross engine upgrades"). A later bump is its own change.
    config = _cdk_config()
    for env in ("dev", "prod"):
        assert config.PyvarConfig.for_env(env).cache_major_engine_version == "7", env


def test_the_cache_takes_its_engine_and_version_from_the_config() -> None:
    source = _data_stack_source()
    assert re.search(
        r"engine=cfg\.cache_engine\b", source
    ), "engine must come from cfg.cache_engine"
    assert re.search(
        r"major_engine_version=cfg\.cache_major_engine_version\b", source
    ), "major_engine_version must come from cfg.cache_major_engine_version"
    assert 'engine="redis"' not in source, "a hard-coded engine would ignore the setting"


def test_the_logical_id_and_the_name_stay_so_the_engine_change_is_in_place() -> None:
    source = _data_stack_source()
    assert re.search(
        r'CfnServerlessCache\(\s*self,\s*"RedisServerless",', source
    ), 'the cache logical ID must stay "RedisServerless": a new ID makes CloudFormation replace it'
    assert (
        'serverless_cache_name=f"pyvar-{cfg.env_name}"' in source
    ), "the cache name must stay pyvar-{env}: a new name makes CloudFormation replace the cache"

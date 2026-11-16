"""tests/test_cdk_aurora_floor.py — prod's Aurora minimum capacity is 0.5 ACU, and the prod writer's CPU is watched.

Reasoning:
- Over the 14 days to 2026-11-16 the two prod instances averaged 1.01 and 1.02 ACU
  (docs/p9-aws-evidence-2026-11-13.md, section 12), so the floor is what is billed. pyvar-cdk/config.py
  lowers prod's `aurora_min_acu` from 1.0 to 0.5, the value dev has always run. The change is measured
  before and after (docs/plan-aurora-floor-measurement.md) and rolls back by setting 1.0 again.
- data_stack.py adds a writer CPU alarm in prod only. The alerts topic belongs to alerts_stack and is
  referenced by its ARN, as queue_stack.py does; the name must stay the same in both places.
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
    name = "pyvar_cdk_config_for_floor_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _source(stack: str) -> str:
    path = _CDK / "stacks" / stack
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    return path.read_text(encoding="utf-8")


def test_the_minimum_capacity_is_half_an_acu_everywhere_and_prod_keeps_its_maximum() -> None:
    config = _cdk_config()
    floors = {
        env: config.PyvarConfig.for_env(env).aurora_min_acu for env in ("dev", "staging", "prod")
    }
    assert floors == {"dev": 0.5, "staging": 0.5, "prod": 0.5}
    assert config.PyvarConfig.for_env("prod").aurora_max_acu == 16.0
    assert config.PyvarConfig.for_env("dev").aurora_max_acu == 2.0


def test_the_cpu_alarm_exists_in_prod_only_and_needs_fifteen_minutes_in_a_row() -> None:
    source = _source("data_stack.py")
    block = source[source.index('if cfg.env_name == "prod":') :]
    block = block[: block.index("# ── ElastiCache")]
    assert "AuroraWriterCpuAlarm" in block
    assert "threshold=85" in block
    assert re.search(r"evaluation_periods=3,\s+datapoints_to_alarm=3", block)
    assert "Duration.minutes(5)" in block


def test_the_alerts_topic_name_matches_the_topic_alerts_stack_creates() -> None:
    expected = 'f"pyvar-{cfg.env_name}-alerts"'
    assert expected in _source("alerts_stack.py")
    assert expected in _source("data_stack.py")
    assert expected in _source("queue_stack.py")

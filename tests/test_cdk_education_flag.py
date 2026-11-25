"""tests/test_cdk_education_flag.py — the education tier is on in dev and prod, off in staging, by one entry each.

Reasoning:
- The tier is off by default (docs/plan-education-tier.md): with the app's `education_tier_enabled` setting false,
  every account has its free limits and the grant and extend routes answer 503. pyvar-cdk/config.py carries a
  per-environment `education_tier_enabled`, true in the "dev" and "prod" overrides, and api_stack.py turns it into
  the container variable EDUCATION_TIER_ENABLED=true only where it is true, so staging's task definition does not
  change.
- Prod was switched on on 2026-11-25 by the owner's decision, as one line in the "prod" override, with this test
  changed in the same commit: the expected value below is the record of that decision, not an accident. To close
  it again, remove the line (and change the expected value here in the same commit), then end the grants already
  given with `scripts/education_grant.py suspend-all`.
- Same approach as tests/test_cdk_assistant_flag.py: the CDK code is read, not run, so aws-cdk-lib is not needed in
  the application test environment.
- The variable name must match the app's setting: pydantic-settings reads EDUCATION_TIER_ENABLED into
  `education_tier_enabled`, which is checked on the real Settings class.
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
    name = "pyvar_cdk_config_for_education_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # a dataclass under `from __future__ import annotations` looks its module up in sys.modules
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def test_the_education_tier_is_on_in_dev_and_prod_and_off_in_staging() -> None:
    config = _cdk_config()
    flags = {
        env: config.PyvarConfig.for_env(env).education_tier_enabled
        for env in ("dev", "staging", "prod")
    }
    assert flags == {"dev": True, "staging": False, "prod": True}


def test_the_default_is_off_so_a_new_environment_starts_without_the_tier() -> None:
    config = _cdk_config()
    assert config.PyvarConfig(env_name="x", account="1").education_tier_enabled is False


def test_the_api_container_gets_the_variable_only_where_the_flag_is_true() -> None:
    path = _CDK / "stacks" / "api_stack.py"
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    source = path.read_text(encoding="utf-8")
    assert re.search(
        r'\*\*\(\{"EDUCATION_TIER_ENABLED": "true"\} if cfg\.education_tier_enabled else \{\}\)',
        source,
    ), "api_stack.py must add EDUCATION_TIER_ENABLED=true only when cfg.education_tier_enabled is true"
    # never a literal "false" entry: that would change the task definition of every other environment
    assert '"EDUCATION_TIER_ENABLED": "false"' not in source


def test_only_the_api_task_gets_it() -> None:
    """effective_tier() and the grant routes run in the API process; no other stack needs the variable."""
    hits = [
        path.name
        for path in sorted((_CDK / "stacks").glob("*.py"))
        if "EDUCATION_TIER_ENABLED" in path.read_text(encoding="utf-8")
    ]
    assert hits == ["api_stack.py"]


def test_the_variable_name_is_the_one_the_application_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import Settings  # the application's settings, not pyvar-cdk/config.py

    monkeypatch.delenv("EDUCATION_TIER_ENABLED", raising=False)
    assert Settings().education_tier_enabled is False
    monkeypatch.setenv("EDUCATION_TIER_ENABLED", "true")
    assert Settings().education_tier_enabled is True

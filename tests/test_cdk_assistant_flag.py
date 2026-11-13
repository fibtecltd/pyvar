"""tests/test_cdk_assistant_flag.py — the portal assistant menus are switched on in dev and prod, by one environment entry.

Reasoning:
- The assistant's menu widget shows when the app's `assistant_enabled` setting (config.py) is true AND the
  committed answer bank is complete. The setting defaults to False. pyvar-cdk/config.py carries a per-environment
  `assistant_enabled`, true only in the "dev" and "prod" overrides, and api_stack.py turns it into the container
  variable ASSISTANT_ENABLED=true only where it is true. Staging therefore gets no new variable: its task
  definition does not change and no rolling deploy is caused there. Prod was switched on by a decision of
  2026-11-13 (docs/assistant-phase0-results.md 9.35); only the typed route, a different flag, stays off everywhere.
- Same approach as tests/test_cdk_worker_env.py: the CDK code is read, not run, so aws-cdk-lib is not needed in
  the application test environment. pyvar-cdk/config.py has no CDK import, so it is loaded under its own module
  name (the application's config.py has the same file name).
- The variable name must match the app's setting: pydantic-settings reads ASSISTANT_ENABLED into
  `assistant_enabled`, which is checked on the real Settings class.
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
    name = "pyvar_cdk_config_for_test"
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


def test_dev_and_prod_have_the_assistant_menus_on_and_staging_does_not() -> None:
    config = _cdk_config()
    flags = {
        env: config.PyvarConfig.for_env(env).assistant_enabled for env in ("dev", "staging", "prod")
    }
    assert flags == {"dev": True, "staging": False, "prod": True}


def test_the_default_is_off_so_a_new_environment_starts_without_the_assistant() -> None:
    config = _cdk_config()
    assert config.PyvarConfig(env_name="x", account="1").assistant_enabled is False


def test_the_api_container_gets_the_variable_only_where_the_flag_is_true() -> None:
    path = _CDK / "stacks" / "api_stack.py"
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    source = path.read_text(encoding="utf-8")
    assert re.search(
        r'\*\*\(\{"ASSISTANT_ENABLED": "true"\} if cfg\.assistant_enabled else \{\}\)', source
    ), "api_stack.py must add ASSISTANT_ENABLED=true only when cfg.assistant_enabled is true"
    # never a literal "false" entry: that would change staging's task definition
    assert '"ASSISTANT_ENABLED": "false"' not in source


def test_the_variable_name_is_the_one_the_application_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import Settings  # the application's settings, not pyvar-cdk/config.py

    monkeypatch.delenv("ASSISTANT_ENABLED", raising=False)
    assert Settings().assistant_enabled is False
    monkeypatch.setenv("ASSISTANT_ENABLED", "true")
    assert Settings().assistant_enabled is True

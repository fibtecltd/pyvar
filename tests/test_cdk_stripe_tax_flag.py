"""tests/test_cdk_stripe_tax_flag.py — Stripe Tax on the Pro Checkout is on in dev only, by one environment entry.

Reasoning:
- The Checkout sends automatic_tax, tax_id_collection and customer_update only when the app's
  `stripe_automatic_tax_enabled` setting is true (docs/plan-pro-tier-stripe.md section 10). Stripe Tax needs the
  full head-office address before that works, in test mode and again in live mode, so only dev (test mode, where
  the owner checked it on 2026-11-24) has it on; prod waits for live Stripe Tax. pyvar-cdk/config.py carries a per-environment `stripe_automatic_tax_enabled`, and api_stack.py turns it
  into the container variable STRIPE_AUTOMATIC_TAX_ENABLED=true only where it is true.
- Turning it on is then one line in that environment's override, and the expected value below is changed in the
  same commit: it is the record of the decision, not an accident.
- Same approach as tests/test_cdk_education_flag.py: the CDK code is read, not run, so aws-cdk-lib is not needed
  in the application test environment.
- The variable name must match the app's setting, which is checked on the real Settings class.
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
    name = "pyvar_cdk_config_for_stripe_tax_test"
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


def test_only_dev_has_stripe_tax_on() -> None:
    config = _cdk_config()
    flags = {
        env: config.PyvarConfig.for_env(env).stripe_automatic_tax_enabled
        for env in ("dev", "staging", "prod")
    }
    assert flags == {"dev": True, "staging": False, "prod": False}


def test_the_default_is_off_so_a_new_environment_starts_without_it() -> None:
    config = _cdk_config()
    assert config.PyvarConfig(env_name="x", account="1").stripe_automatic_tax_enabled is False


def test_the_api_container_gets_the_variable_only_where_the_flag_is_true() -> None:
    path = _CDK / "stacks" / "api_stack.py"
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    source = path.read_text(encoding="utf-8")
    assert re.search(
        r'\*\*\(\s*\{"STRIPE_AUTOMATIC_TAX_ENABLED": "true"\}\s*'
        r"if cfg\.stripe_automatic_tax_enabled\s*else \{\}\s*\)",
        source,
    ), "api_stack.py must add STRIPE_AUTOMATIC_TAX_ENABLED=true only when the flag is true"
    # never a literal "false" entry: that would change the task definition of every other environment
    assert '"STRIPE_AUTOMATIC_TAX_ENABLED": "false"' not in source


def test_only_the_api_task_gets_it() -> None:
    """The Checkout route runs in the API process; no other stack needs the variable."""
    hits = [
        path.name
        for path in sorted((_CDK / "stacks").glob("*.py"))
        if "STRIPE_AUTOMATIC_TAX_ENABLED" in path.read_text(encoding="utf-8")
    ]
    assert hits == ["api_stack.py"]


def test_the_variable_name_is_the_one_the_application_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import Settings  # the application's settings, not pyvar-cdk/config.py

    monkeypatch.delenv("STRIPE_AUTOMATIC_TAX_ENABLED", raising=False)
    assert Settings().stripe_automatic_tax_enabled is False
    monkeypatch.setenv("STRIPE_AUTOMATIC_TAX_ENABLED", "true")
    assert Settings().stripe_automatic_tax_enabled is True

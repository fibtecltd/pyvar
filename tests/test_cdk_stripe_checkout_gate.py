"""tests/test_cdk_stripe_checkout_gate.py — the Pro checkout is restricted on prod only, by one environment entry.

Reasoning:
- While Stripe is in test mode on prod, the webhook (no live/test check) and the public test card would give Pro to
  anyone who clicked "Upgrade", so api/billing_gate.py lets only operator-allowed accounts start a checkout where the
  app's `stripe_checkout_restricted` setting is true (docs/plan-pro-tier-stripe.md section 11). pyvar-cdk/config.py
  carries a per-environment `stripe_checkout_restricted`, true only in the "prod" override, and api_stack.py turns it
  into the container variable STRIPE_CHECKOUT_RESTRICTED=true only where it is true, so dev's and staging's task
  definitions do not change.
- When Stripe goes live on prod the prod line is removed and the expected value below is changed in the same commit:
  it is the record of that decision, not an accident. A default of False keeps a new environment open, which is why
  the restriction is an explicit prod entry and a forgotten removal fails safe (checkout stays closed).
- Same approach as tests/test_cdk_education_flag.py: the CDK code is read, not run, so aws-cdk-lib is not needed.
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
    name = "pyvar_cdk_config_for_checkout_gate_test"
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


def test_only_prod_restricts_the_checkout() -> None:
    config = _cdk_config()
    flags = {
        env: config.PyvarConfig.for_env(env).stripe_checkout_restricted
        for env in ("dev", "staging", "prod")
    }
    assert flags == {"dev": False, "staging": False, "prod": True}


def test_the_default_is_open_so_a_new_environment_starts_unrestricted() -> None:
    config = _cdk_config()
    assert config.PyvarConfig(env_name="x", account="1").stripe_checkout_restricted is False


def test_the_api_container_gets_the_variable_only_where_the_flag_is_true() -> None:
    path = _CDK / "stacks" / "api_stack.py"
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    source = path.read_text(encoding="utf-8")
    assert re.search(
        r'\*\*\(\s*\{"STRIPE_CHECKOUT_RESTRICTED": "true"\}\s*'
        r"if cfg\.stripe_checkout_restricted\s*else \{\}\s*\)",
        source,
    ), "api_stack.py must add STRIPE_CHECKOUT_RESTRICTED=true only when the flag is true"
    # never a literal "false" entry: that would change the task definition of every other environment
    assert '"STRIPE_CHECKOUT_RESTRICTED": "false"' not in source


def test_only_the_api_task_gets_it() -> None:
    """The Checkout route runs in the API process; no other stack needs the variable."""
    hits = [
        path.name
        for path in sorted((_CDK / "stacks").glob("*.py"))
        if "STRIPE_CHECKOUT_RESTRICTED" in path.read_text(encoding="utf-8")
    ]
    assert hits == ["api_stack.py"]


def test_the_variable_name_is_the_one_the_application_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import Settings  # the application's settings, not pyvar-cdk/config.py

    monkeypatch.delenv("STRIPE_CHECKOUT_RESTRICTED", raising=False)
    assert Settings().stripe_checkout_restricted is False
    monkeypatch.setenv("STRIPE_CHECKOUT_RESTRICTED", "true")
    assert Settings().stripe_checkout_restricted is True

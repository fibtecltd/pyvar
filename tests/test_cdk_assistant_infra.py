"""tests/test_cdk_assistant_infra.py — the typed assistant's flags, key, alarms and edge rule (all inert while it is off).

Reasoning:
- This is infrastructure a deploy cannot check: a flag that ships on, a secret name that differs from the one the
  application reads, an alarm that counts a log line the application no longer writes, or a rate rule that sits after
  the aggregate rule all pass `cdk synth` and fail silently. So the contracts are pinned here, as
  tests/test_cdk_trial_lane.py and tests/test_cdk_education_flag.py do for their features: the CDK source is READ
  (with `ast` and regular expressions), not run, so aws-cdk-lib is not needed in the application test environment.
  The synthesized templates were compared before and after by hand when this was written (the PR description).
- Contracts that cross the CDK/application line are tested from both sides: the secret name (api/assistant/key.py),
  the URL prefix of the route (api/assistant/routes.py), the environment variable names (config.py), and the log events
  (api/assistant/*.py).
- Nothing here turns the typed route on. tests/test_assistant_privacy_terms.py fails if a CDK environment ever sets
  `assistant_typed_enabled = True` without the model provider being named in the privacy policy and the terms.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from api.assistant import key as assistant_key
from api.assistant.routes import router as assistant_router
from config import Settings, get_settings

ROOT = Path(__file__).resolve().parents[1]
CDK = ROOT / "pyvar-cdk"
STACKS = CDK / "stacks"
AGGREGATE_PRIORITY = 25


def source(name: str) -> str:
    path = STACKS / name
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    return path.read_text(encoding="utf-8")


def constants(text: str) -> dict[str, Any]:
    """The module-level literal assignments of a source file (tuples, dicts, numbers and strings only)."""
    found: dict[str, Any] = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    continue
    return found


API = source("api_stack.py")
EDGE = source("edge_stack.py")
API_CONSTANTS = constants(API)
EDGE_CONSTANTS = constants(EDGE)


def cdk_config() -> ModuleType:
    path = CDK / "config.py"
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    name = "pyvar_cdk_config_for_assistant_infra_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = (
        module  # a dataclass under `from __future__ import annotations` looks itself up here
    )
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


# ── the flags ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "flag", ["assistant_typed_enabled", "assistant_watchdog_enabled", "assistant_allowlist_enabled"]
)
def test_the_flag_is_off_in_every_environment(flag: str) -> None:
    config = cdk_config()
    assert config.PyvarConfig(env_name="x", account="1").__dict__[flag] is False
    assert {
        env: getattr(config.PyvarConfig.for_env(env), flag) for env in ("dev", "staging", "prod")
    } == {"dev": False, "staging": False, "prod": False}


def test_wherever_typed_is_on_the_watchdog_is_on() -> None:
    # CLAUDE.md 3.8: the watchdog is the only thing that notices a function whose live answers keep going wrong.
    config = cdk_config()
    for env in ("dev", "staging", "prod"):
        cfg = config.PyvarConfig.for_env(env)
        if cfg.assistant_typed_enabled:
            assert cfg.assistant_watchdog_enabled, env


def test_the_api_container_gets_each_variable_only_where_its_flag_is_true() -> None:
    for variable, flag in (
        ("ASSISTANT_TYPED_ENABLED", "assistant_typed_enabled"),
        ("ASSISTANT_WATCHDOG_ENABLED", "assistant_watchdog_enabled"),
        ("ASSISTANT_ALLOWLIST_ENABLED", "assistant_allowlist_enabled"),
    ):
        assert re.search(
            rf'\*\*\(\s*\{{"{variable}": "true"\}}\s*if cfg\.{flag}\s*else\s*\{{\}}\s*,?\s*\)', API
        ), f"{variable} must be added only when cfg.{flag} is true"
        # never a literal "false" entry: that would change the task definition of every environment
        assert f'"{variable}": "false"' not in API


def test_the_variable_names_are_the_ones_the_application_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for variable, attribute in (
        ("ASSISTANT_TYPED_ENABLED", "assistant_typed_enabled"),
        ("ASSISTANT_WATCHDOG_ENABLED", "assistant_watchdog_enabled"),
        ("ASSISTANT_ALLOWLIST_ENABLED", "assistant_allowlist_enabled"),
    ):
        monkeypatch.delenv(variable, raising=False)
        assert getattr(Settings(), attribute) is False
        monkeypatch.setenv(variable, "true")
        assert getattr(Settings(), attribute) is True


# ── the key ─────────────────────────────────────────────────────────────────────


def test_the_secret_is_imported_by_name_and_granted_to_the_task_role() -> None:
    assert (
        'from_secret_name_v2(\n            self, "AnthropicSecret", '
        f'f"pyvar/{{cfg.env_name}}/{assistant_key.SECRET_SUFFIX}"\n        )'
    ) in API
    assert "anthropic_secret.grant_read(task_role)" in API


def test_the_secret_is_never_an_ecs_secrets_entry_so_it_cannot_stop_a_task_launching() -> None:
    # The reason the Sentry and Stripe secrets are read by the app: a missing secret in `secrets={}` fails every
    # new task launch, compute routes included, for a feature that is off.
    assert "from_secrets_manager(anthropic" not in API
    assert "anthropic_secret.grant_read(execution_role)" not in API
    assert not re.search(r'"ANTHROPIC_API_KEY"\s*:', API)


def test_the_name_the_stack_grants_is_the_name_the_application_reads() -> None:
    # The app reads pyvar/<app_env>/<suffix> and the stack grants pyvar/<env_name>/<suffix>; the deployed APP_ENV is
    # the short environment name (config.py), as it is for the Stripe secrets.
    assert assistant_key.SECRET_SUFFIX == "anthropic-api-key"
    for env in ("dev", "prod"):
        assert f"pyvar/{env}/{assistant_key.SECRET_SUFFIX}" == f"pyvar/{env}/anthropic-api-key"


# ── the alarms ──────────────────────────────────────────────────────────────────


def app_log_events() -> set[str]:
    events: set[str] = set()
    for path in sorted((ROOT / "api" / "assistant").glob("*.py")):
        events |= set(
            re.findall(
                r'logger\.(?:info|warning|error|exception)\(\s*"([a-z_]+)"',
                path.read_text(encoding="utf-8"),
            )
        )
    return events


def test_every_event_an_alarm_counts_is_one_the_application_writes() -> None:
    counted = set(API_CONSTANTS["ASSISTANT_LOG_EVENTS"])
    assert counted == {
        "assistant_client_unavailable",
        "assistant_store_unavailable",
        "assistant_ask_failed",
        "assistant_writer_degraded",
        "assistant_watchdog_error",
        "assistant_spend_not_recorded",
        "assistant_budget_high",
        "assistant_pinned",
    }
    assert counted <= app_log_events()


def test_the_alarm_table_is_consistent_with_the_event_table() -> None:
    alarms = API_CONSTANTS["ASSISTANT_ALARMS"]
    events = API_CONSTANTS["ASSISTANT_LOG_EVENTS"]
    assert [row[1] for row in alarms] == [
        "client-unavailable",
        "store-unavailable",
        "ask-failed",
        "writer-degraded",
        "watchdog-errors",
        "spend-not-recorded",
        "budget-high",
        "pinned",
    ]
    assert {row[2] for row in alarms} == set(
        events
    )  # every event has an alarm and every alarm an event
    assert len({row[0] for row in alarms}) == len(alarms)  # unique construct ids
    assert len(set(events.values())) == len(events)  # unique metric names
    for _, _, event, threshold, period_minutes, description in alarms:
        assert event in events
        assert threshold >= 1 and period_minutes in (5, 60) and description.endswith((".", ")"))


def test_the_thresholds_are_the_plans() -> None:
    by_name = {row[1]: row[3:5] for row in API_CONSTANTS["ASSISTANT_ALARMS"]}
    assert by_name["client-unavailable"] == (1, 5)  # one is already an outage
    assert by_name["store-unavailable"] == (1, 5)  # it fails closed: one is an outage
    assert by_name["ask-failed"] == (3, 5)
    assert by_name["watchdog-errors"] == (5, 5)
    assert by_name["spend-not-recorded"] == (3, 5)
    assert by_name["budget-high"] == (
        1,
        5,
    )  # the app logs the line at 80% of the cap (deps.BUDGET_HIGH_RATIO)
    assert by_name["pinned"] == (1, 60)


def test_the_alarms_use_the_alerts_topic_the_json_event_key_and_do_not_breach_on_silence() -> None:
    block = API[API.index("def assistant_metric") : API.index('cdk.CfnOutput(self, "AlbDnsName"')]
    assert 'FilterPattern.string_value("$.event", "=", event)' in block
    assert "log_group=self.api_log_group" in block
    assert "add_alarm_action(cw_actions.SnsAction(alerts_topic))" in block
    assert "treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING" in block
    assert "GREATER_THAN_OR_EQUAL_TO_THRESHOLD" in block
    assert 'alarm_name=f"pyvar-{cfg.env_name}-assistant-{alarm_suffix}"' in block
    assert 'metric_name = f"assistant-{ASSISTANT_LOG_EVENTS[event]}-{cfg.env_name}"' in block


def test_the_budget_line_matches_the_80_percent_the_app_logs() -> None:
    from api.assistant import deps

    assert deps.BUDGET_HIGH_RATIO == 0.8
    description = next(r[5] for r in API_CONSTANTS["ASSISTANT_ALARMS"] if r[1] == "budget-high")
    assert "80%" in description


def test_the_alarms_live_in_a_stack_the_pipeline_deploys() -> None:
    text = source("pipeline_stack.py")
    start = text.index("class PyvarDeployStage")
    following = re.search(r"^class ", text[start + 1 :], flags=re.M)
    stage = text[start : start + 1 + following.start()] if following else text[start:]
    assert "ApiStack" in stage
    assert "EdgeStack" in stage


# ── the edge rule ───────────────────────────────────────────────────────────────


def test_the_edge_prefix_is_the_prefix_of_the_assistant_router() -> None:
    assert EDGE_CONSTANTS["ASSISTANT_PATH_PREFIX"] == (
        get_settings().api_v1_prefix + assistant_router.prefix + "/"
    )
    # The menu buttons are static files outside the API prefix: the rule never touches them.
    assert not "/assistant/bank/".startswith(EDGE_CONSTANTS["ASSISTANT_PATH_PREFIX"])


def function_source(name: str) -> str:
    """One top-level function of edge_stack.py: from its `def` to the next top-level `def` or `class`."""
    start = EDGE.index(f"def {name}(")
    following = re.search(r"\n(?:def|class) ", EDGE[start + 1 :])
    return EDGE[start : start + 1 + following.start()] if following else EDGE[start:]


def test_function_source_isolates_one_function() -> None:
    body = function_source("_assistant_rate_rule")
    assert body.startswith("def _assistant_rate_rule(") and "class EdgeStack" not in body
    assert body.count("RuleActionProperty(") == 1 and "EmergencyKillSwitch" not in body


def test_the_scope_down_decodes_and_normalises_the_path_before_matching() -> None:
    body = function_source("_assistant_path_statement")
    assert 'positional_constraint="STARTS_WITH"' in body
    assert "search_string=ASSISTANT_PATH_PREFIX" in body
    assert body.index('type="URL_DECODE"') < body.index('type="NORMALIZE_PATH"')


def test_the_rate_rule_blocks_per_address_with_the_planned_numbers() -> None:
    assert EDGE_CONSTANTS["ASSISTANT_LIMIT_PER_IP"] == 30
    assert EDGE_CONSTANTS["ASSISTANT_WINDOW_PER_IP_SEC"] == 300
    body = function_source("_assistant_rate_rule")
    assert 'name = "AssistantRateLimitPerIp"' in body
    assert "block={}" in body  # a rate rule that only counted would stop nothing
    assert 'aggregate_key_type="IP"' in body
    assert "limit=ASSISTANT_LIMIT_PER_IP" in body
    assert "evaluation_window_sec=ASSISTANT_WINDOW_PER_IP_SEC" in body
    assert "scope_down_statement=_assistant_path_statement()" in body
    assert "metric_name=name" in body


def rule_priorities() -> list[int]:
    priorities: list[int] = []
    for node in ast.walk(ast.parse(EDGE)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "RuleProperty":
            for keyword in node.keywords:
                if keyword.arg == "priority" and isinstance(keyword.value, ast.Constant):
                    priorities.append(keyword.value.value)
        elif (
            name == "_trial_rate_rule"
            and len(node.args) > 1
            and isinstance(node.args[1], ast.Constant)
        ):
            priorities.append(node.args[1].value)
    return priorities


def test_the_assistant_rule_sits_before_the_aggregate_rule_and_priorities_stay_unique() -> None:
    priorities = rule_priorities()
    assert len(priorities) == len(set(priorities)), priorities
    assert 24 in priorities and AGGREGATE_PRIORITY in priorities
    assert 24 < AGGREGATE_PRIORITY
    assert "priority=24," in function_source("_assistant_rate_rule")
    # ...and the rule is actually in the ACL, in the list that holds the other rules
    calls = [m.start() for m in re.finditer(r"(?<!def )_assistant_rate_rule\(\)", EDGE)]
    assert len(calls) == 1
    assert calls[0] < EDGE.index('name="AggregateRateLimit"')

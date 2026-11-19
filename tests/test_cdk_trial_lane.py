"""tests/test_cdk_trial_lane.py — the edge and the alarms of the no-sign-up trial lane (trial lane PR 3).

Reasoning:
- docs/plan-trial-lane-throttle.md layers L5 and L8 and its "Operations" alarms are infrastructure that a
  deploy cannot check: a WAF rule on the wrong path, a rate rule that sits after the aggregate rule, a kill
  switch that ships engaged, or an alarm that counts a log line the lane no longer writes all pass `cdk synth`
  and fail silently in production. So the numbers and the contracts are pinned here.
- Same approach as tests/test_cdk_cache_engine.py: the CDK source is READ (with `ast` and regular
  expressions), not run, so aws-cdk-lib is not needed in the application test environment. The synthesized
  templates were compared before and after by hand when this was written (the PR description has the diff).
- Two contracts cross the CDK/application line and are tested from both sides: the URL prefix the WAF rules and
  the cache behaviour match (api/routes/trial.py's router), and the log-line names the metric filters count
  (api/middleware/trial.py; its own side is tests/test_trial_events.py).
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
_CDK = ROOT / "pyvar-cdk" / "stacks"

# Priorities that already existed before the trial rules, from edge_stack.py's own comments and rules.
AGGREGATE_PRIORITY = 25


def _source(name: str) -> str:
    path = _CDK / name
    if not path.exists():
        pytest.skip(f"source file not found (cannot audit): {path}")
    return path.read_text(encoding="utf-8")


def _evaluate(node: ast.expr, known: dict[str, Any]) -> Any:
    """A tiny evaluator for the module constants this test reads (no eval)."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return known[node.id]
    if isinstance(node, ast.Tuple):
        return tuple(_evaluate(item, known) for item in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _evaluate(k, known): _evaluate(v, known)
            for k, v in zip(node.keys, node.values, strict=True)
            if k is not None
        }
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _evaluate(node.left, known) + _evaluate(node.right, known)
    raise ValueError(ast.dump(node))


def _constants(source: str) -> dict[str, Any]:
    known: dict[str, Any] = {}
    for node in ast.parse(source).body:
        value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
        if value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                try:
                    known[target.id] = _evaluate(value, known)
                except (ValueError, KeyError):
                    continue  # not a plain constant: not read here
    return known


@pytest.fixture(scope="module")
def edge() -> str:
    return _source("edge_stack.py")


@pytest.fixture(scope="module")
def edge_constants(edge: str) -> dict[str, Any]:
    return _constants(edge)


@pytest.fixture(scope="module")
def alerts() -> str:
    return _source("alerts_stack.py")


# ── the path the edge matches is the path the API serves ───────────────────────────────────────────────────


def test_the_edge_matches_the_prefix_of_the_trial_router(edge_constants: dict[str, Any]) -> None:
    from api.routes.trial import router
    from config import get_settings

    assert edge_constants["TRIAL_PATH_PREFIX"] == f"{get_settings().api_v1_prefix}{router.prefix}/"
    assert edge_constants["TRIAL_PATH_PATTERN"] == edge_constants["TRIAL_PATH_PREFIX"] + "*"


def test_the_waf_scope_down_decodes_and_normalises_the_path_before_matching(edge: str) -> None:
    helper = edge[edge.index("def _trial_path_statement") : edge.index("def _trial_rate_rule")]
    assert 'positional_constraint="STARTS_WITH"' in helper
    assert "search_string=TRIAL_PATH_PREFIX" in helper
    # The API decodes %-escapes and collapses `//` before routing; a raw-path match would let both around.
    assert re.search(r'priority=0, type="URL_DECODE"', helper)
    assert re.search(r'priority=1, type="NORMALIZE_PATH"', helper)
    assert "uri_path={}" in helper


# ── the numbers of the plan (L8) ───────────────────────────────────────────────────────────────────────────


def test_the_rate_limits_are_the_plans_numbers(edge_constants: dict[str, Any]) -> None:
    c = edge_constants
    assert (
        c["TRIAL_LIMIT_PER_IP"],
        c["TRIAL_LIMIT_PER_ASN"],
        c["TRIAL_WINDOW_PER_IP_ASN_SEC"],
    ) == (
        30,
        600,
        600,
    )
    assert (c["TRIAL_LIMIT_ALL"], c["TRIAL_WINDOW_ALL_SEC"]) == (300, 300)
    # What WAF accepts: a limit of at least 10 and a window of 60, 120, 300 or 600 seconds.
    for limit in (c["TRIAL_LIMIT_PER_IP"], c["TRIAL_LIMIT_PER_ASN"], c["TRIAL_LIMIT_ALL"]):
        assert limit >= 10
    for window in (c["TRIAL_WINDOW_PER_IP_ASN_SEC"], c["TRIAL_WINDOW_ALL_SEC"]):
        assert window in (60, 120, 300, 600)


def _rate_rules(edge: str) -> dict[str, dict[str, str]]:
    rules: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r'_trial_rate_rule\(\s*"(?P<name>\w+)",\s*(?P<priority>\d+),\s*'
        r'aggregate_key_type="(?P<key>\w+)",\s*limit=(?P<limit>\w+),\s*window_sec=(?P<window>\w+)',
        edge,
    ):
        rules[match["name"]] = match.groupdict()
    return rules


def test_the_three_trial_rate_rules_have_the_planned_keys_and_sit_before_the_aggregate_rule(
    edge: str, edge_constants: dict[str, Any]
) -> None:
    rules = _rate_rules(edge)
    assert set(rules) == set(edge_constants["TRIAL_RATE_RULE_METRICS"])
    assert {name: rule["key"] for name, rule in rules.items()} == {
        "TrialRateLimitPerIp": "IP",
        "TrialRateLimitPerAsn": "CUSTOM_KEYS",
        "TrialRateLimitAll": "CONSTANT",
    }
    assert {name: rule["limit"] for name, rule in rules.items()} == {
        "TrialRateLimitPerIp": "TRIAL_LIMIT_PER_IP",
        "TrialRateLimitPerAsn": "TRIAL_LIMIT_PER_ASN",
        "TrialRateLimitAll": "TRIAL_LIMIT_ALL",
    }
    priorities = sorted(int(rule["priority"]) for rule in rules.values())
    # After the two managed rule groups (10, 20), before AggregateRateLimit: a trial flood is stopped
    # before it can use up the 6,000 that every other caller shares.
    assert priorities == [21, 22, 23]
    assert all(20 < p < AGGREGATE_PRIORITY for p in priorities)
    # The ASN rule keys on WAF's own ASN key, not on a header the viewer could set.
    assert "RateBasedStatementCustomKeyProperty(asn={})" in edge


def test_every_rule_priority_is_unique(edge: str) -> None:
    pairs = re.findall(r'name="(\w+)",\s*priority=(\d+),', edge)
    pairs += [(name, rule["priority"]) for name, rule in _rate_rules(edge).items()]
    numbers = [int(priority) for _, priority in pairs]
    assert len(numbers) == len(set(numbers)), sorted(pairs, key=lambda item: int(item[1]))
    # Guard against the regular expression matching nothing: the rules that already existed are in it.
    assert {name for name, _ in pairs} >= {
        "EmergencyKillSwitch",
        "TrialKillSwitch",
        "RateLimitPerIp",
        "AggregateRateLimit",
    }


# ── the kill switch ships inert, like the one that exists ──────────────────────────────────────────────────


def test_the_trial_kill_switch_ships_in_count_and_is_scoped_to_the_trial_path(edge: str) -> None:
    start = edge.index('name="TrialKillSwitch"')
    block = edge[start : edge.index("visibility_config", start)]
    assert "priority=5" in block
    assert (
        "count={}" in block and "block=" not in block
    )  # a deploy never changes live traffic by itself
    assert "_trial_path_statement()" in block
    assert "_match_all_statement()" not in block


def test_the_toggle_script_takes_only_the_two_switch_rules() -> None:
    script = ROOT / "scripts" / "toggle_kill_switch.sh"
    if not script.exists():
        pytest.skip("scripts/toggle_kill_switch.sh not found")
    text = script.read_text(encoding="utf-8")
    assert 'RULE_NAME="${3:-EmergencyKillSwitch}"' in text
    bogus = (
        subprocess.run(  # noqa: S603  # nosec B603 B607 -- fixed argv, rejected before any aws call
            ["bash", str(script), "status", "dev", "AggregateRateLimit"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    )
    assert bogus.returncode == 1
    assert "Unknown rule" in bogus.stderr
    assert "Looking up WebACL" not in bogus.stderr  # refused before it reached AWS


# ── the cache behaviour that carries the viewer's network to the API ──────────────────────────────────────


def test_the_trial_behaviour_forwards_the_viewer_asn_and_not_the_host(edge: str) -> None:
    policy = edge[edge.index("trial_origin_request_policy = cf.OriginRequestPolicy(") :]
    policy = policy[: policy.index("\n        )\n") + 1]
    assert '"CloudFront-Viewer-ASN"' in policy
    assert "allow_list(" in policy
    assert "Host" not in policy.replace("CloudFront-Viewer", "")
    assert "OriginRequestQueryStringBehavior.none()" in policy
    assert "OriginRequestCookieBehavior.none()" in policy
    behaviour = edge[edge.index("TRIAL_PATH_PATTERN: cf.BehaviorOptions(") :]
    behaviour = behaviour[: behaviour.index("\n                ),\n") + 1]
    assert "origin_request_policy=trial_origin_request_policy" in behaviour
    assert "cache_policy=api_cache_policy" in behaviour  # Authorization is in this policy's key
    assert "ALLOW_ALL" in behaviour  # a POST route


# ── the alarms count lines the lane writes ─────────────────────────────────────────────────────────────────


def _lane_log_events() -> set[str]:
    """Every `event` the lane can write that an alarm may count."""
    from api.middleware import trial as lane

    events = {"trial_issued"} | {f"trial_refused_{reason}" for reason in lane.RETRY_AFTER_SECONDS}
    source = (ROOT / "api" / "middleware" / "trial.py").read_text(encoding="utf-8")
    events |= set(re.findall(r'logger\.warning\("(trial_breaker_(?:strike|attack|pause))"', source))
    return events


def test_every_event_an_alarm_counts_is_one_the_lane_writes(alerts: str) -> None:
    counted = set(_constants(alerts)["TRIAL_LOG_EVENTS"])
    assert counted == {
        "trial_issued",
        "trial_refused_pow",
        "trial_refused_issuance",
        "trial_refused_asn",
        "trial_breaker_strike",
        "trial_breaker_attack",
        "trial_breaker_pause",
    }
    assert counted <= _lane_log_events()


def test_the_metric_filters_match_the_json_event_key_in_the_api_log_group(alerts: str) -> None:
    assert 'FilterPattern.string_value("$.event", "=", event)' in alerts
    assert "log_group=api.api_log_group" in alerts
    api = _source("api_stack.py")
    assert "self.api_log_group = api_log_driver.log_group" in api
    assert "logging=api_log_driver," in api


def test_the_alarms_are_the_plans_five_and_each_pages_the_alerts_topic(alerts: str) -> None:
    ids = re.findall(r'trial_alarm\(\s*"(Trial\w+Alarm)"', alerts)
    assert ids == [
        "TrialEmptyBudgetAlarm",
        "TrialIssuanceRefusalsAlarm",
        "TrialAsnCapAlarm",
        "TrialPowFailureRatioAlarm",
        "TrialBreakerStateAlarm",
    ]
    assert "add_alarm_action(cw_actions.SnsAction(self.topic))" in alerts
    consts = _constants(alerts)
    assert consts["TRIAL_ISSUANCE_REFUSALS_PER_HOUR"] == 50
    assert consts["TRIAL_POW_FAILURE_PERCENT"] == 20
    # Two consecutive hourly checks, not one.
    empty = alerts[alerts.index('"TrialEmptyBudgetAlarm"') :]
    assert "evaluation_periods=2" in empty[: empty.index('"TrialIssuanceRefusalsAlarm"')]


def test_the_edge_alarm_lives_in_the_edge_stack_and_names_the_three_blocking_rules(
    edge: str, edge_constants: dict[str, Any]
) -> None:
    assert edge_constants["TRIAL_WAF_BLOCKS_ALARM_THRESHOLD"] == 1000
    assert 'metric_name="BlockedRequests"' in edge
    assert 'namespace="AWS/WAFV2"' in edge
    # CloudFront web ACL metrics carry no Region dimension (AWS metric reference), only these two.
    assert 'dimensions_map={"WebACL": f"pyvar-{cfg.env_name}-waf", "Rule": rule}' in edge
    assert "add_alarm_action(cw_actions.SnsAction(self.edge_alerts_topic))" in edge
    # The metric name the alarm uses for the ACL is the one the ACL's visibility config sets.
    assert 'metric_name=f"pyvar-{cfg.env_name}-waf"' in edge

"""
tests/test_observability.py — regression coverage for #170: Sentry must
never actually connect during a test run.

Reasoning:
- tests/conftest.py's autouse `_no_sentry_in_tests` fixture patches
  sentry_sdk.init for every test in the suite (defense in depth — no test
  has to opt in). These two tests prove that fixture actually does
  something, not just that the default (no SENTRY_DSN) path is already
  harmless: the second test forces cfg.sentry_dsn truthy — the exact
  "SENTRY_DSN happens to be set" scenario that caused #170 — and asserts
  sentry_sdk.init was still only called against the mock, never the real
  SDK entrypoint.
- Patches observability.setup.cfg.sentry_dsn directly (the already-
  instantiated module-level Settings object), not config.get_settings():
  the latter is @lru_cache'd, so re-invoking it wouldn't reliably produce a
  new instance observability/setup.py would actually see.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from observability.setup import _resolve_sentry_dsn, cfg, setup_sentry


def test_setup_sentry_noop_with_no_dsn(_no_sentry_in_tests):
    """Default test config has no SENTRY_DSN — setup_sentry() must be a
    pure no-op, same as it always was."""
    setup_sentry()
    _no_sentry_in_tests.assert_not_called()


def test_setup_sentry_intercepted_when_dsn_present(_no_sentry_in_tests):
    """#170: even when SENTRY_DSN IS set (the scenario that actually caused
    real Sentry incidents from mocked test exceptions), sentry_sdk.init must
    never reach the real SDK — only the autouse fixture's mock sees the call.
    """
    with patch.object(cfg, "sentry_dsn", "https://fake-dsn@example.ingest.sentry.io/1"):
        setup_sentry()

    _no_sentry_in_tests.assert_called_once()
    assert _no_sentry_in_tests.call_args.kwargs["dsn"] == (
        "https://fake-dsn@example.ingest.sentry.io/1"
    )


def test_setup_sentry_noop_with_literal_none_string(_no_sentry_in_tests):
    """PR #229 review finding: `aws secretsmanager get-secret-value --query
    SecretString --output text` prints the literal text "None" (not empty)
    when a secret was created as SecretBinary instead of SecretString — an
    easy mistake for pyvar/{env}/sentry-dsn, created outside CDK. That
    string is truthy in Python, so it must be checked explicitly rather than
    relying on `if not cfg.sentry_dsn`.
    """
    with patch.object(cfg, "sentry_dsn", "None"):
        setup_sentry()

    _no_sentry_in_tests.assert_not_called()


def test_setup_sentry_survives_init_exception(_no_sentry_in_tests):
    """PR #229 review finding: a malformed DSN that reaches sentry_sdk.init
    must not crash API/worker startup — Sentry is optional observability,
    never a hard dependency. Forces the mock to raise the way a genuinely
    invalid DSN would inside the real SDK, and asserts setup_sentry() itself
    doesn't propagate it.
    """
    _no_sentry_in_tests.side_effect = ValueError("Invalid Sentry DSN")
    with patch.object(cfg, "sentry_dsn", "not-a-real-dsn"):
        setup_sentry()  # must not raise

    _no_sentry_in_tests.assert_called_once()


# ── _resolve_sentry_dsn ──────────────────────────────────────────────────────
# PR #229 follow-up: the API tier no longer gets SENTRY_DSN via ECS's native
# `secrets={}` injection (that mechanism has no "optional" mode and would
# make an observability nice-to-have a new hard dependency for task launch —
# see api_stack.py). Instead the app fetches it directly, but ONLY when
# actually running in a real ECS task, never in local dev/CI — these tests
# are the regression coverage for that boundary specifically.


def test_resolve_sentry_dsn_prefers_env_var_no_aws_call():
    """Workers already have SENTRY_DSN via fetch-config.sh -> env var. Must
    return it immediately without ever touching boto3."""
    with (
        patch.object(cfg, "sentry_dsn", "https://from-env@example.ingest.sentry.io/1"),
        patch("boto3.client") as mock_boto_client,
    ):
        result = _resolve_sentry_dsn()

    assert result == "https://from-env@example.ingest.sentry.io/1"
    mock_boto_client.assert_not_called()


def test_resolve_sentry_dsn_no_fetch_outside_ecs():
    """Rule 3 (CLAUDE.md/tests): never touch real AWS services in tests. CI's
    test job runs with APP_ENV=test, not "development" — this asserts the
    gate is real ECS presence (ecs_container_metadata_uri_v4), not an
    app_env string match, since a name-based check would have let this slip
    through in exactly that CI job.
    """
    with (
        patch.object(cfg, "sentry_dsn", None),
        patch.object(cfg, "ecs_container_metadata_uri_v4", None),
        patch("boto3.client") as mock_boto_client,
    ):
        result = _resolve_sentry_dsn()

    assert result == ""
    mock_boto_client.assert_not_called()


def test_resolve_sentry_dsn_fetches_from_secrets_manager_in_ecs():
    """In a real ECS task with no env-var DSN (the API tier's actual setup),
    fetches pyvar/{app_env}/sentry-dsn and returns SecretString."""
    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {
        "SecretString": "https://from-secrets-manager@example.ingest.sentry.io/1"
    }
    with (
        patch.object(cfg, "sentry_dsn", None),
        patch.object(cfg, "ecs_container_metadata_uri_v4", "http://169.254.170.2/v4/abc"),
        patch.object(cfg, "app_env", "production"),
        patch("boto3.client", return_value=mock_client) as mock_boto_client,
    ):
        result = _resolve_sentry_dsn()

    assert result == "https://from-secrets-manager@example.ingest.sentry.io/1"
    mock_boto_client.assert_called_once_with("secretsmanager")
    mock_client.get_secret_value.assert_called_once_with(SecretId="pyvar/production/sentry-dsn")


def test_resolve_sentry_dsn_degrades_on_secrets_manager_failure():
    """The whole point of moving this fetch out of ECS's native `secrets={}`:
    a Secrets Manager failure (deleted secret, IAM policy change, etc.) must
    degrade to "no Sentry", not raise and block API/worker startup."""
    mock_client = MagicMock()
    mock_client.get_secret_value.side_effect = Exception("AccessDeniedException")
    with (
        patch.object(cfg, "sentry_dsn", None),
        patch.object(cfg, "ecs_container_metadata_uri_v4", "http://169.254.170.2/v4/abc"),
        patch("boto3.client", return_value=mock_client),
    ):
        result = _resolve_sentry_dsn()  # must not raise

    assert result == ""

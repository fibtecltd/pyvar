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

import logging
from unittest.mock import MagicMock, patch

import structlog

from observability.setup import _redact_dsn, _resolve_sentry_dsn, cfg, setup_logging, setup_sentry


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


# ── _redact_dsn (CodeQL py/clear-text-logging-sensitive-data) ───────────────
# The init-failure warning below used to log the raw DSN, embedded public
# key and all. Regression coverage: the failure path must still log
# *something* useful (the host, for "wrong project" triage) but never the
# credential-shaped value CodeQL correctly flagged.


def test_redact_dsn_keeps_host_masks_key():
    redacted = _redact_dsn("https://abc123def@o456.ingest.sentry.io/789")
    assert redacted == "https://***@o456.ingest.sentry.io/789"
    assert "abc123def" not in redacted


def test_redact_dsn_handles_malformed_input():
    # Must never raise -- this runs inside an `except Exception:` handler
    # that's already reacting to a DSN failure; a second exception here
    # would replace a warning log with a crash.
    assert _redact_dsn("not-a-url-at-all") == "***"
    assert _redact_dsn("") == "***"


def test_setup_sentry_init_failure_log_never_contains_raw_dsn(_no_sentry_in_tests, caplog):
    """The actual regression this alert was about: assert the log record
    text itself, not just that _redact_dsn works in isolation."""
    _no_sentry_in_tests.side_effect = ValueError("Invalid Sentry DSN")
    raw_dsn = "https://super-secret-key@o456.ingest.sentry.io/789"
    with patch.object(cfg, "sentry_dsn", raw_dsn), caplog.at_level(logging.WARNING):
        setup_sentry()

    logged_text = "\n".join(caplog.messages)
    assert "super-secret-key" not in logged_text
    assert "o456.ingest.sentry.io" in logged_text


# ── traces_sample_rate (task #45) ────────────────────────────────────────────
# api_stack.py injects APP_ENV=cfg.env_name, the SHORT form CDK uses
# everywhere ("dev"/"staging"/"prod"), not the long form "production" this
# previously compared against -- which never matched any real deployment, so
# prod silently sampled 100% of traces instead of the intended 10%.


def test_setup_sentry_uses_reduced_sample_rate_for_prod(_no_sentry_in_tests):
    """task #45: traces_sample_rate must be 0.1 for app_env "prod" (the real
    value a deployed prod task actually has), not "production"."""
    with (
        patch.object(cfg, "sentry_dsn", "https://fake-dsn@example.ingest.sentry.io/1"),
        patch.object(cfg, "app_env", "prod"),
    ):
        setup_sentry()

    assert _no_sentry_in_tests.call_args.kwargs["traces_sample_rate"] == 0.1


def test_setup_sentry_uses_full_sample_rate_outside_prod(_no_sentry_in_tests):
    """task #45: every other app_env -- dev, staging, local dev's
    "development" default, CI's "test" -- keeps full trace sampling. Only
    prod's higher traffic volume justifies the reduced rate."""
    for env in ("dev", "staging", "development", "test"):
        with (
            patch.object(cfg, "sentry_dsn", "https://fake-dsn@example.ingest.sentry.io/1"),
            patch.object(cfg, "app_env", env),
        ):
            setup_sentry()
        assert _no_sentry_in_tests.call_args.kwargs["traces_sample_rate"] == 1.0


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


# ── structlog renderer (task #46) ────────────────────────────────────────────
# Same app_env short-vs-long-form mismatch as #45: real deployments use "dev"/
# "staging"/"prod", not "development"/"production". setup_logging() adds a
# StreamHandler to the real root logger and never removes it -- these tests
# clean up after themselves so they don't pollute other tests' log capture.


def _last_root_handler_processor():
    handler = logging.getLogger().handlers[-1]
    try:
        # ProcessorFormatter stores the renderer passed as `processor=` at
        # the end of its own `.processors` chain (preceded by
        # remove_processors_meta) -- there's no public singular `.processor`
        # attribute to read it back from directly.
        return handler.formatter.processors[-1]
    finally:
        logging.getLogger().removeHandler(handler)


def test_setup_logging_uses_json_for_any_real_deployment():
    """task #46: dev/staging/prod must all get JSONRenderer -- CloudWatch-
    searchable structured logs, not just prod specifically. Previously
    deployed dev ("dev") fell into the JSON branch only by accident (it
    simply didn't match the literal "development" the old code compared
    against) -- this asserts it's now deliberate for every real env."""
    for env in ("dev", "staging", "prod"):
        with patch.object(cfg, "app_env", env):
            setup_logging()
        assert isinstance(_last_root_handler_processor(), structlog.processors.JSONRenderer)


def test_setup_logging_uses_console_renderer_outside_real_deployments():
    """task #46: unrecognised app_env -- local dev's "development" default,
    CI's "test" -- gets the human-readable ConsoleRenderer, never JSON."""
    for env in ("development", "test"):
        with patch.object(cfg, "app_env", env):
            setup_logging()
        assert isinstance(_last_root_handler_processor(), structlog.dev.ConsoleRenderer)

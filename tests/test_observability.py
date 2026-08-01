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

from unittest.mock import patch

from observability.setup import cfg, setup_sentry


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

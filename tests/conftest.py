"""
tests/conftest.py — suite-wide fixtures

Reasoning:
- #146 added a rate-limit dependency (api/middleware/rate_limit.py) to
  var_router's POST /compute and all 8 domain routers. Its module-level
  `_limiter` is Redis-backed by default (storage/redis_client.py::redis_url(),
  pointing at cfg.redis_url — localhost:6379 unless overridden), which every
  test in the suite would otherwise try to reach for real on every request
  that hits a rate-limited route — violating the project's "never hit a real
  backing service in tests" rule (see tests/test_auth.py's own docstring) even
  though enforce_compute_rate_limit's fail-open behavior means those tests
  still pass. Autouse + function-scoped so every test gets Redis-free,
  mutually isolated rate-limit state without having to opt in individually,
  and so accumulated hits from one test/file can never spill into another
  and start producing spurious 429s (most existing domain API tests use a
  fixed 'tester'/enterprise token, but enterprise is exempt anyway; test_api.py
  reuses 'test-user'/free and 'pro-user'/free across many test functions,
  which is exactly the scenario a shared, non-isolated limiter would break).
- tests/test_rate_limit.py and tests/test_api.py's own 429-path test still
  swap in their OWN fresh Limiter (sometimes with a lowered quota) to exercise
  the throttling behavior itself — this fixture only has to guarantee no test
  ever falls through to a real Redis connection by default.
- #170: observability/setup.py::setup_sentry() only skips sentry_sdk.init()
  when cfg.sentry_dsn is falsy — nothing stops it from actually connecting to
  a real Sentry project if SENTRY_DSN happens to be set in whatever
  environment runs pytest (a local .env, a stray CI secret). That's exactly
  what happened: a batch of Sentry "incidents" turned out to be this test
  suite's own deliberately-mocked exceptions (side_effect= strings like
  "simulated DB outage", one traceback literally naming tests.test_var_task
  as the module), reported as real by whoever's local run had a live DSN.
  Patches sentry_sdk.init directly — not cfg.sentry_dsn — since
  config.get_settings() is an lru_cache singleton and observability/setup.py
  binds cfg = get_settings() at import time; forcing that specific field on
  the cached instance is sensitive to module-import/collection ordering
  across the whole suite, whereas sentry_sdk.init is the one true boundary
  to the outside world regardless of how cfg.sentry_dsn was resolved.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from slowapi import Limiter
from slowapi.util import get_remote_address


@pytest.fixture(autouse=True)
def _isolated_rate_limiter():
    fresh = Limiter(key_func=get_remote_address, storage_uri="memory://")
    with patch("api.middleware.rate_limit._limiter", fresh):
        yield fresh


@pytest.fixture(autouse=True)
def _no_sentry_in_tests():
    """#170: guarantees sentry_sdk.init is never actually called for real
    during a test run, regardless of what SENTRY_DSN is set to in the
    executing environment. Yields the mock so a test can assert on it
    directly (see tests/test_observability.py) without needing its own
    nested patch.
    """
    with patch("sentry_sdk.init") as mock_init:
        yield mock_init

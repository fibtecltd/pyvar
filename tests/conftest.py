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

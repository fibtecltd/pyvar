"""
tests/test_config.py — regression tests for config.py's Settings validators.

Reasoning:
- Settings is normally read via the cached get_settings() singleton, but its
  @model_validator(mode="after") methods are exercised here by constructing
  Settings(...) directly with explicit field overrides and _env_file=None --
  bypassing the cache and any real .env/OS-environment state, so these tests
  are hermetic and don't depend on what APP_ENV the test process happens to
  be started with.
"""

from __future__ import annotations

from config import Settings


def test_cors_origins_default_to_wildcard_for_unknown_app_env():
    """task #42: local dev ("development") and CI ("test") aren't in the
    deployed-env map -- must keep the permissive wildcard, since neither is
    a real credential-bearing deployment."""
    assert Settings(app_env="development", _env_file=None).cors_allowed_origins == ["*"]
    assert Settings(app_env="test", _env_file=None).cors_allowed_origins == ["*"]


def test_cors_origins_locked_down_for_prod():
    """task #42: prod was confirmed live to reflect an arbitrary Origin back
    with credentials allowed -- must be restricted to its own two real
    domains only."""
    settings = Settings(app_env="prod", _env_file=None)
    assert settings.cors_allowed_origins == ["https://pyvar.com", "https://www.pyvar.com"]


def test_cors_origins_locked_down_for_dev():
    """task #42: dev was ALSO confirmed wide open live (the cfg.debug-always
    -True root cause affected both environments equally, not just prod) --
    must be restricted too, not left on the wildcard."""
    settings = Settings(app_env="dev", _env_file=None)
    assert settings.cors_allowed_origins == ["https://dev.pyvar.com"]


def test_cors_origins_explicit_override_is_not_clobbered():
    """An explicitly-set cors_allowed_origins (e.g. via a
    CORS_ALLOWED_ORIGINS env var) must win over the app_env-based default."""
    settings = Settings(
        app_env="prod",
        cors_allowed_origins=["https://custom.example.com"],
        _env_file=None,
    )
    assert settings.cors_allowed_origins == ["https://custom.example.com"]


def test_public_base_url_defaults_to_localhost_for_unknown_app_env():
    """task #43: local dev ("development") and CI ("test") aren't in the
    deployed-env map -- must fall back to the local uvicorn address
    (CLAUDE.md section 9), not the stale AWS CloudFront literal this
    replaced, since main.py serves portal/dashboard.html at "/" locally
    too."""
    assert Settings(app_env="development", _env_file=None).public_base_url == (
        "http://localhost:8000"
    )
    assert Settings(app_env="test", _env_file=None).public_base_url == "http://localhost:8000"


def test_public_base_url_uses_real_domain_for_prod():
    """task #43: verification emails must link to prod's real domain, not
    dev's raw pre-cutover CloudFront URL."""
    settings = Settings(app_env="prod", _env_file=None)
    assert settings.public_base_url == "https://www.pyvar.com"


def test_public_base_url_uses_real_domain_for_dev():
    """task #43: dev gets its own real Stage-B subdomain, not the raw
    CloudFront literal either."""
    settings = Settings(app_env="dev", _env_file=None)
    assert settings.public_base_url == "https://dev.pyvar.com"


def test_public_base_url_explicit_override_is_not_clobbered():
    """An explicitly-set public_base_url (e.g. via a PUBLIC_BASE_URL env
    var) must win over the app_env-based default."""
    settings = Settings(
        app_env="prod",
        public_base_url="https://custom.example.com",
        _env_file=None,
    )
    assert settings.public_base_url == "https://custom.example.com"

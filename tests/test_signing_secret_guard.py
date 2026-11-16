"""config.require_real_signing_secret: a hosted API must not start on a public or short signing secret.

Reasoning:
- Whoever holds the JWT signing secret can sign a token of any tier, including `internal`, so the API
  must refuse to serve with the public fallback ("change-me-in-production") or a weak value. In AWS the
  secret is injected from Secrets Manager (pyvar-cdk/stacks/api_stack.py), so this only ever fires if that
  injection is lost.
- It is a start-up check of the API (main.lifespan), NOT part of Settings validation: the Celery workers do
  not verify tokens, are not given the secret and run on the fallback by design (no JWT_SECRET in
  pyvar-cdk/stacks/compute_stack.py), so a check inside Settings would stop every worker. A test pins that.
- Only hosted values of APP_ENV are checked: "dev", "staging", "prod" ("production" for the long form).
  Local runs use "development" and CI runs with "test"; checking "anything but development" would break CI.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import main as main_module
from config import (
    HOSTED_ENVS,
    MIN_SIGNING_SECRET_LENGTH,
    PUBLIC_DEFAULT_JWT_SECRET,
    Settings,
    require_real_signing_secret,
)

GOOD = "x" * 40


def settings(app_env: str, secret: str) -> Settings:
    return Settings(app_env=app_env, jwt_secret=secret)


@pytest.mark.parametrize("env", sorted(HOSTED_ENVS))
def test_a_hosted_environment_refuses_the_public_default(env):
    with pytest.raises(RuntimeError, match="refusing to start"):
        require_real_signing_secret(settings(env, PUBLIC_DEFAULT_JWT_SECRET))


@pytest.mark.parametrize("env", sorted(HOSTED_ENVS))
def test_a_hosted_environment_refuses_a_short_secret(env):
    with pytest.raises(RuntimeError):
        require_real_signing_secret(settings(env, "x" * (MIN_SIGNING_SECRET_LENGTH - 1)))
    with pytest.raises(RuntimeError):
        require_real_signing_secret(settings(env, ""))


@pytest.mark.parametrize("env", sorted(HOSTED_ENVS))
def test_a_hosted_environment_accepts_a_real_secret(env):
    require_real_signing_secret(settings(env, "x" * MIN_SIGNING_SECRET_LENGTH))
    require_real_signing_secret(settings(env, GOOD))


@pytest.mark.parametrize("env", ["development", "test", "ci", "local"])
def test_local_and_ci_environments_are_not_checked(env):
    require_real_signing_secret(settings(env, PUBLIC_DEFAULT_JWT_SECRET))
    require_real_signing_secret(settings(env, ""))


def test_the_message_never_contains_the_secret():
    secret = "short-but-secret"
    with pytest.raises(RuntimeError) as exc:
        require_real_signing_secret(settings("prod", secret))
    assert secret not in str(exc.value) and "'prod'" in str(exc.value)


def test_whitespace_does_not_make_a_short_secret_long_enough():
    with pytest.raises(RuntimeError):
        require_real_signing_secret(settings("prod", " " * 10 + "abc" + " " * 40))


def test_settings_themselves_still_load_in_a_hosted_env_with_the_default(monkeypatch):
    """The workers run like this: the guard must not live in Settings validation.

    CI sets JWT_SECRET for the whole run, so the variable is removed to see the fallback.
    """
    monkeypatch.delenv("JWT_SECRET", raising=False)
    loaded = Settings(app_env="prod")
    assert loaded.jwt_secret == PUBLIC_DEFAULT_JWT_SECRET


def test_the_default_is_the_public_constant(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    assert Settings().jwt_secret == PUBLIC_DEFAULT_JWT_SECRET


# ── the API's start-up ──────────────────────────────────────────────────────────


def run_lifespan() -> None:
    async def go() -> None:
        async with main_module.lifespan(MagicMock()):
            pass

    asyncio.run(go())


def test_the_api_does_not_start_in_prod_on_the_default_secret(monkeypatch):
    monkeypatch.setattr(main_module.cfg, "app_env", "prod")
    monkeypatch.setattr(main_module.cfg, "jwt_secret", PUBLIC_DEFAULT_JWT_SECRET)
    with patch("engine.montecarlo.run_monte_carlo_var") as warmup:
        with pytest.raises(RuntimeError, match="refusing to start"):
            run_lifespan()
    warmup.assert_not_called()  # it stops before any other start-up work


def test_the_api_starts_in_prod_with_a_real_secret(monkeypatch):
    monkeypatch.setattr(main_module.cfg, "app_env", "prod")
    monkeypatch.setattr(main_module.cfg, "jwt_secret", GOOD)
    with (
        patch("engine.montecarlo.run_monte_carlo_var") as warmup,
        patch.object(main_module, "close_job_done_bus", AsyncMock()),
    ):
        run_lifespan()
    warmup.assert_called_once()


def test_the_api_still_starts_under_test_with_the_default_secret(monkeypatch):
    monkeypatch.setattr(main_module.cfg, "app_env", "test")
    monkeypatch.setattr(main_module.cfg, "jwt_secret", PUBLIC_DEFAULT_JWT_SECRET)
    with (
        patch("engine.montecarlo.run_monte_carlo_var"),
        patch.object(main_module, "close_job_done_bus", AsyncMock()),
    ):
        run_lifespan()

"""The typed route's Anthropic key: read from Secrets Manager at call time (api/assistant/key.py).

Reasoning:
- The key must never be a reason an API task cannot launch (so it is not an ECS `secrets={}` entry), must be
  rotatable without a deploy (call-time read, one-minute cache, client rebuilt when the value changes), and must
  never reach a log line. These tests pin each of those with a fake boto3: no AWS, no Anthropic, no network.
- The rules are the Stripe resolver's (a key in settings wins; nothing is read outside an ECS task) plus etlgen's
  call-time cache (fibtec-etlgen api/lib/secret_value.py): a failed read never returns an empty or stale key.
- `assistant_budget_high` (the 80% line the CDK alarm counts) is pinned here too: it carries the ratio and nothing else.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from pydantic import SecretStr
from structlog.testing import capture_logs

from api.assistant import deps, key
from api.assistant.store import Gate
from assistant.client import AnthropicClient, MissingApiKey

CANARY = "sk-ant-api03-CANARY-0123456789abcdefghijklmnopqrstuvwxyz"
ECS_URI = "http://169.254.170.2/v4/test-task"


class FakeSecrets:
    """A stand-in for boto3.client("secretsmanager"): replays `outcomes` (a value, or an exception to raise)."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[str] = []

    def client(self, service: str, *args: Any, **kwargs: Any) -> FakeSecrets:
        assert service == "secretsmanager"
        return self

    def get_secret_value(
        self, *, SecretId: str
    ) -> dict[str, Any]:  # noqa: N803 — boto3's own spelling
        self.calls.append(SecretId)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return {"SecretString": outcome} if outcome is not None else {"SecretBinary": b"x"}


def not_found() -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": "ResourceNotFoundException",
                "Message": f"Secrets Manager can't find {CANARY}",
            }
        },
        "GetSecretValue",
    )


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def in_an_ecs_task(monkeypatch: pytest.MonkeyPatch):
    key.reset_cache()
    monkeypatch.setattr(key.cfg, "anthropic_api_key", None)
    monkeypatch.setattr(key.cfg, "ecs_container_metadata_uri_v4", ECS_URI)
    monkeypatch.setattr(key.cfg, "app_env", "production")
    monkeypatch.setattr(deps, "_client", None)
    monkeypatch.setattr(deps, "_client_key", None)
    yield
    key.reset_cache()


def use(monkeypatch: pytest.MonkeyPatch, *outcomes: Any) -> FakeSecrets:
    fake = FakeSecrets(*outcomes)
    monkeypatch.setattr(boto3, "client", fake.client)
    return fake


# ── the resolver ────────────────────────────────────────────────────────────────


def test_a_key_in_settings_wins_and_never_touches_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = use(monkeypatch, "from-aws")
    monkeypatch.setattr(key.cfg, "anthropic_api_key", SecretStr("from-settings"))
    assert key.resolve_key() == "from-settings"
    assert fake.calls == []


def test_outside_an_ecs_task_nothing_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = use(monkeypatch, "from-aws")
    monkeypatch.setattr(key.cfg, "ecs_container_metadata_uri_v4", None)
    assert key.resolve_key() is None
    assert fake.calls == []


def test_it_reads_this_environments_secret_and_caches_it_for_a_minute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = use(monkeypatch, "  key-one\n", "key-two")
    clock = Clock()
    assert key.resolve_key(clock=clock) == "key-one"  # stripped
    clock.now += key.CACHE_TTL_SECONDS - 1
    assert key.resolve_key(clock=clock) == "key-one"
    assert fake.calls == ["pyvar/production/anthropic-api-key"]  # one read
    clock.now += 2  # past the cache
    assert key.resolve_key(clock=clock) == "key-two"  # a rotation is picked up with no deploy
    assert len(fake.calls) == 2


def test_the_secret_name_follows_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(key.cfg, "app_env", "staging")
    assert key.secret_id() == "pyvar/staging/anthropic-api-key"


def test_a_failed_read_is_none_is_retried_soon_and_picks_up_a_secret_created_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = use(monkeypatch, not_found(), "key-late")
    clock = Clock()
    assert key.resolve_key(clock=clock) is None
    clock.now += key.FAILURE_RETRY_SECONDS - 1
    assert key.resolve_key(clock=clock) is None
    assert len(fake.calls) == 1  # one AWS call per retry window, however many questions arrive
    clock.now += 2
    assert key.resolve_key(clock=clock) == "key-late"
    assert len(fake.calls) == 2


def test_after_the_cache_expires_a_failing_read_gives_none_never_the_old_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(monkeypatch, "key-one", not_found())
    clock = Clock()
    assert key.resolve_key(clock=clock) == "key-one"
    clock.now += key.CACHE_TTL_SECONDS + 1
    assert key.resolve_key(clock=clock) is None


def test_an_empty_or_binary_secret_is_none_and_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    use(monkeypatch, None)  # SecretBinary: no SecretString
    with capture_logs() as logs:
        assert key.resolve_key() is None
    assert [entry["event"] for entry in logs] == ["assistant_key_empty"]


def test_the_value_is_never_logged_and_a_failure_logs_only_names_and_codes(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The failure's message here contains the canary (as an AWS message may name a secret); neither it nor the good
    # value may reach a log line, a field or an exception chain that is logged.
    use(monkeypatch, not_found())
    with capture_logs() as logs, caplog.at_level("DEBUG"):
        key.resolve_key()
    (entry,) = logs
    assert entry["event"] == "assistant_key_read_failed"
    assert entry["secret"] == "anthropic-api-key"
    assert entry["error"] == "ClientError" and entry["error_code"] == "ResourceNotFoundException"
    assert "exc_info" not in entry
    assert CANARY not in repr(logs) and CANARY not in caplog.text

    key.reset_cache()
    use(monkeypatch, CANARY)
    with capture_logs() as logs, caplog.at_level("DEBUG"):
        assert key.resolve_key() == CANARY
    assert CANARY not in repr(logs) and CANARY not in caplog.text


# ── the client follows the key ──────────────────────────────────────────────────


class RecordingClient:
    built: list[str | None] = []

    def __init__(self, *, api_key: str | None = None, **_: Any) -> None:
        self.api_key = api_key
        RecordingClient.built.append(api_key)


def test_the_client_is_built_once_and_rebuilt_only_when_the_key_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    RecordingClient.built = []
    monkeypatch.setattr(deps, "AnthropicClient", RecordingClient)
    keys = iter(["k1", "k1", "k2"])
    monkeypatch.setattr(deps, "resolve_key", lambda: next(keys))
    first, second, third = deps.get_model_client(), deps.get_model_client(), deps.get_model_client()
    assert first is second and third is not first
    assert RecordingClient.built == ["k1", "k2"]


def test_no_key_is_a_503_and_the_old_client_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps, "AnthropicClient", RecordingClient)
    monkeypatch.setattr(deps, "resolve_key", lambda: None)
    monkeypatch.setattr(deps, "_client", object())
    with capture_logs() as logs, pytest.raises(HTTPException) as refused:
        deps.get_model_client()
    assert refused.value.status_code == 503
    assert refused.value.detail["code"] == "assistant_unavailable"
    assert deps._client is None
    assert [e["event"] for e in logs] == ["assistant_client_unavailable"]


def test_anthropic_client_uses_the_key_it_is_given_and_not_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []
    fake_sdk = types.SimpleNamespace(Anthropic=lambda **kwargs: seen.append(kwargs) or object())
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)
    AnthropicClient(api_key="given-key")
    assert seen[0]["api_key"] == "given-key"


def test_anthropic_client_still_needs_some_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules, "anthropic", types.SimpleNamespace(Anthropic=lambda **_: object())
    )
    with pytest.raises(MissingApiKey):
        AnthropicClient()


# ── the 80% line ────────────────────────────────────────────────────────────────


class FakeStore:
    def __init__(self, spent: float) -> None:
        self.spent = spent

    async def gate(self, now: Any = None) -> Gate:
        return Gate(killed=False, spent_usd=self.spent)


@pytest.fixture
def typed_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps.cfg, "assistant_enabled", True)
    monkeypatch.setattr(deps.cfg, "assistant_typed_enabled", True)
    monkeypatch.setattr(deps.cfg, "assistant_daily_budget_usd", 5.0)


async def test_below_80_percent_of_the_cap_nothing_is_logged(typed_on: None) -> None:
    with capture_logs() as logs:
        await deps.require_available(store=FakeStore(3.99))  # type: ignore[arg-type]
    assert [e for e in logs if e["event"] == "assistant_budget_high"] == []


async def test_at_80_percent_one_line_with_the_ratio_only_and_the_question_still_passes(
    typed_on: None,
) -> None:
    with capture_logs() as logs:
        await deps.require_available(store=FakeStore(4.0))  # type: ignore[arg-type]
    (entry,) = [e for e in logs if e["event"] == "assistant_budget_high"]
    assert entry["ratio"] == 0.8
    assert set(entry) == {"event", "ratio", "log_level"}  # nothing from the visitor, nothing else


async def test_at_the_cap_it_is_still_logged_and_the_question_is_refused(typed_on: None) -> None:
    with capture_logs() as logs, pytest.raises(HTTPException) as refused:
        await deps.require_available(store=FakeStore(5.0))  # type: ignore[arg-type]
    assert refused.value.detail["code"] == "assistant_budget"
    assert any(e["event"] == "assistant_budget_high" for e in logs)

"""assistant/client.py: retries, backoff, the served-model check, cost, and the key staying out of logs.

Reasoning:
- No test here calls the network or needs a key: the SDK is replaced by a fake object with `messages.create`,
  or by a fake `anthropic` module placed in sys.modules.
- The retry rules were measured in scripts/assistant_eval/run_eval.py::call_model and are duplicated in the
  client (assistant/ must not import scripts/); the first test pins that the two sets stay the same.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest
import structlog
import structlog.testing
from pydantic import SecretStr

from assistant import client as client_module
from assistant.client import (
    AnthropicClient,
    MissingApiKey,
    ModelCallError,
    ServedModelMismatch,
    is_retryable,
)

REPO = Path(__file__).resolve().parent.parent
SECRET = "sk-ant-api03-THIS-MUST-NEVER-APPEAR"  # noqa: S105


class HttpError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"http {status_code}")
        self.status_code = status_code


class APIConnectionError(
    Exception
):  # same class name as the SDK's, which is what is_retryable reads
    pass


def reply(
    text: str = "hello", model: str = "claude-sonnet-5-5", stop: str = "end_turn", **usage: int
) -> Any:
    block = types.SimpleNamespace(type="text", text=text)
    thinking = types.SimpleNamespace(type="thinking", thinking="private")
    counts = {"input_tokens": 1000, "output_tokens": 500, **usage}
    return types.SimpleNamespace(
        model=model,
        content=[thinking, block],
        stop_reason=stop,
        usage=types.SimpleNamespace(**counts),
    )


class Sdk:
    """An object with the SDK's `messages.create`, answering from a script of replies or errors."""

    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.kwargs: list[dict[str, Any]] = []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.kwargs.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FixedRng:
    def uniform(self, low: float, high: float) -> float:
        return 1.0


def make(sdk: Sdk, sleeps: list[float], **kwargs: Any) -> AnthropicClient:
    return AnthropicClient(sdk_client=sdk, sleep=sleeps.append, rng=FixedRng(), **kwargs)  # type: ignore[arg-type]


REQUEST = {"system": "s", "messages": [{"role": "user", "content": "q"}], "max_tokens": 100}


def test_the_retryable_statuses_are_the_ones_the_harness_measured() -> None:
    sys.path.append(str(REPO / "scripts" / "assistant_eval"))
    import run_eval

    assert client_module.RETRYABLE_STATUS == run_eval.RETRYABLE_STATUS
    assert client_module.RETRYABLE_NAMES == run_eval.RETRYABLE_NAMES
    assert client_module.MAX_ATTEMPTS == run_eval.MAX_API_ATTEMPTS


def test_a_call_returns_text_usage_cost_and_the_served_model() -> None:
    sdk = Sdk(reply("the answer"))
    result = make(sdk, []).complete("claude-sonnet-5-5", REQUEST)
    assert result.text == "the answer"  # the thinking block is not part of the text
    assert result.stop_reason == "end_turn" and result.served == "claude-sonnet-5-5"
    assert result.usage == {
        "input_tokens": 1000,
        "output_tokens": 500,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    assert result.cost == pytest.approx((1000 * 2.00 + 500 * 10.00) / 1e6)
    assert sdk.kwargs[0]["model"] == "claude-sonnet-5-5" and sdk.kwargs[0]["max_tokens"] == 100


def test_cost_uses_the_rate_of_the_model_asked_for() -> None:
    opus = make(Sdk(reply(model="claude-opus-5-5")), []).complete("claude-opus-5-5", REQUEST)
    assert opus.cost == pytest.approx((1000 * 4.00 + 500 * 20.00) / 1e6)


def test_the_per_call_timeout_is_passed_to_every_request() -> None:
    sdk = Sdk(reply())
    make(sdk, [], timeout_s=33.0).complete("claude-sonnet-5-5", REQUEST)
    assert sdk.kwargs[0]["timeout"] == 33.0


@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504, 529])
def test_a_transient_status_is_retried_with_exponential_backoff(status: int) -> None:
    sleeps: list[float] = []
    sdk = Sdk(HttpError(status), HttpError(status), reply())
    result = make(sdk, sleeps).complete("claude-sonnet-5-5", REQUEST)
    assert result.text == "hello" and len(sdk.kwargs) == 3
    assert sleeps == [2.0, 4.0]  # 2**attempt, jitter pinned to 1.0


def test_backoff_is_capped_and_jittered() -> None:
    class Rng:
        def uniform(self, low: float, high: float) -> float:
            assert (low, high) == (0.5, 1.5)
            return high

    sleeps: list[float] = []
    sdk = Sdk(*[HttpError(529) for _ in range(5)], reply())
    c = AnthropicClient(sdk_client=sdk, sleep=sleeps.append, rng=Rng(), max_attempts=6)  # type: ignore[arg-type]
    c.complete("claude-sonnet-5-5", REQUEST)
    assert sleeps == [3.0, 6.0, 12.0, 24.0, 45.0]  # min(30, 2**n) * 1.5


def test_a_connection_error_is_retried_by_class_name() -> None:
    assert is_retryable(APIConnectionError())
    sdk = Sdk(APIConnectionError(), reply())
    assert make(sdk, []).complete("claude-sonnet-5-5", REQUEST).text == "hello"


def test_retries_stop_after_max_attempts_and_the_cause_is_kept() -> None:
    sleeps: list[float] = []
    sdk = Sdk(*[HttpError(429) for _ in range(4)])
    with pytest.raises(ModelCallError) as info:
        make(sdk, sleeps).complete("claude-sonnet-5-5", REQUEST)
    assert len(sdk.kwargs) == 4 and len(sleeps) == 3
    assert isinstance(info.value.__cause__, HttpError)
    assert "429" in str(info.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_a_client_error_is_not_retried(status: int) -> None:
    sleeps: list[float] = []
    sdk = Sdk(HttpError(status), reply())
    with pytest.raises(ModelCallError):
        make(sdk, sleeps).complete("claude-sonnet-5-5", REQUEST)
    assert len(sdk.kwargs) == 1 and sleeps == []


def test_a_reply_served_by_another_model_is_an_error_and_is_not_retried() -> None:
    sleeps: list[float] = []
    sdk = Sdk(reply(model="claude-haiku-5-5"), reply())
    with pytest.raises(ServedModelMismatch, match="claude-sonnet-5-5.*claude-haiku-5-5"):
        make(sdk, sleeps).complete("claude-sonnet-5-5", REQUEST)
    assert len(sdk.kwargs) == 1 and sleeps == []


def test_a_dated_model_id_that_starts_with_the_requested_one_is_accepted() -> None:
    result = make(Sdk(reply(model="claude-sonnet-5-5-20261101")), []).complete(
        "claude-sonnet-5-5", REQUEST
    )
    assert result.served == "claude-sonnet-5-5-20261101"


def test_max_attempts_must_be_positive() -> None:
    with pytest.raises(ValueError):
        make(Sdk(), [], max_attempts=0)


def fake_anthropic_module(created: list[dict[str, Any]], sdk: Sdk) -> types.ModuleType:
    module = types.ModuleType("anthropic")

    class Anthropic:
        def __init__(self, **kwargs: Any) -> None:
            created.append(kwargs)
            self.messages = sdk.messages

    module.Anthropic = Anthropic  # type: ignore[attr-defined]
    return module


def settings_with(key: str | None) -> Any:
    secret = SecretStr(key) if key is not None else None
    return lambda: types.SimpleNamespace(anthropic_api_key=secret)


def test_the_key_comes_from_the_settings_and_the_sdk_retries_are_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[dict[str, Any]] = []
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic_module(created, Sdk(reply())))
    monkeypatch.setattr(client_module, "get_settings", settings_with(SECRET))
    AnthropicClient(timeout_s=45.0)
    assert created == [{"api_key": SECRET, "max_retries": 0, "timeout": 45.0}]


def test_a_missing_key_is_a_clear_error_before_the_sdk_is_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sys.modules, "anthropic", None
    )  # an import would fail: it must not get that far
    for value in (None, ""):
        monkeypatch.setattr(client_module, "get_settings", settings_with(value))
        with pytest.raises(MissingApiKey, match="anthropic_api_key"):
            AnthropicClient()


def test_a_missing_sdk_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.setattr(client_module, "get_settings", settings_with(SECRET))
    with pytest.raises(
        RuntimeError, match="pip install -r scripts/assistant_eval/requirements.txt"
    ):
        AnthropicClient()


def test_the_key_is_never_logged_or_shown(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class LeakyError(HttpError):
        def __str__(self) -> str:  # an SDK error that carries the key in its message
            return f"401 for key {SECRET}"

    sdk = Sdk(LeakyError(529), reply(), LeakyError(401))
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic_module([], sdk))
    monkeypatch.setattr(client_module, "get_settings", settings_with(SECRET))
    with structlog.testing.capture_logs() as events:
        c = AnthropicClient(sleep=lambda s: None)
        c.complete("claude-sonnet-5-5", REQUEST)
        with pytest.raises(ModelCallError) as info:
            c.complete("claude-sonnet-5-5", REQUEST)
    assert [e["event"] for e in events] == ["model_call_retry", "model_call_failed"]
    assert SECRET not in repr(events) and SECRET not in repr(c) and SECRET not in caplog.text
    assert SECRET not in str(info.value)
    assert all(SECRET not in str(v) for v in vars(c).values())


def test_only_this_module_may_import_the_sdk() -> None:
    import ast

    importers = []
    for path in sorted((REPO / "assistant").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import) and any(a.name == "anthropic" for a in node.names):
                importers.append(path.name)
            if (
                isinstance(node, ast.ImportFrom)
                and (node.module or "").split(".")[0] == "anthropic"
            ):
                importers.append(path.name)
    assert importers == ["client.py"]

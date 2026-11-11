"""The one module under assistant/ that may reach the model provider.

Reasoning:
- Everything else in the package is a pure function of its arguments, so the measured prompts and graders can
  be imported anywhere. This module is the single place that imports the `anthropic` SDK, and it does so inside
  the constructor of `AnthropicClient`: importing assistant.client never needs the SDK, a key or the network,
  and the API process (which does not call a model in this release) never loads it. tests/test_assistant_core.py
  enforces "only this file imports `anthropic`".
- `ModelClient` is the small seam the bank builder and the gate are written against. A test passes a fake that
  answers from the record; only `AnthropicClient` costs money.
- The retry, served-model and cost rules are those of scripts/assistant_eval/run_eval.py::call_model (the
  harness measured them). They are duplicated here, not imported: assistant/ must not depend on scripts/, and
  call_model returns SDK content blocks for the typed tool loop, which this client does not need.
  tests/test_assistant_client.py pins that the two retryable-status sets stay equal.
- The key comes from `get_settings().anthropic_api_key` (a SecretStr) and goes straight to the SDK. It is not
  stored on the object (no attribute, no repr), not put in an exception, and never logged; log lines carry
  the model id, the attempt number and the HTTP status only, never a prompt or an answer.
- The SDK's own retries are off (`max_retries=0`) so the count of attempts and the sleeps are ours and show in
  the logs; a transient failure (429, 5xx, 529 overloaded, a connection error) is retried with jittered
  exponential backoff, anything else raises at once.
- A reply served by a different model from the one asked for is an error, never a result: the bank records
  which model wrote each answer, and a silent substitution would make that record false.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from assistant.cost import usage_cost
from config import get_settings

logger = structlog.get_logger()

RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
RETRYABLE_NAMES = frozenset(
    {"APIConnectionError", "APITimeoutError", "ConnectionError", "TimeoutError"}
)
MAX_ATTEMPTS = 4
DEFAULT_TIMEOUT_S = 120.0
USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


class ModelCallError(Exception):
    """A model call failed for good (retries used up, or an error that is not transient)."""


class MissingApiKey(ModelCallError):
    """No `anthropic_api_key` is configured."""


class ServedModelMismatch(ModelCallError):
    """The response names a different model from the one requested."""


@dataclass(frozen=True)
class Reply:
    """One successful model call.

    Attributes:
        text: the text blocks of the reply, joined (thinking blocks are not included).
        usage: token counts from the API's usage block (all four USAGE_KEYS, missing ones 0).
        stop_reason: the API's stop reason ("end_turn", "max_tokens", "refusal", ...).
        served: the model id that served the call.
        latency: seconds taken by the successful request alone (retries and sleeps excluded).
        cost: dollars, from `usage` at the served model's rate.
    """

    text: str
    usage: dict[str, int]
    stop_reason: str | None
    served: str
    latency: float
    cost: float


class ModelClient(Protocol):
    """What the bank builder and the gate need from a model provider."""

    def complete(self, model: str, request: dict[str, Any]) -> Reply:
        """Send `request` (the keyword arguments of `messages.create`, minus `model`) to `model`."""
        ...


def is_retryable(exc: BaseException) -> bool:
    """True for a transient failure: a retryable HTTP status or a connection or timeout error."""
    status = getattr(exc, "status_code", None)
    return status in RETRYABLE_STATUS or type(exc).__name__ in RETRYABLE_NAMES


def _settings_key() -> str | None:
    secret = get_settings().anthropic_api_key
    value = secret.get_secret_value() if secret is not None else ""
    return value or None


class AnthropicClient:
    """A `ModelClient` over the Anthropic Messages API (sync, one request per call)."""

    def __init__(
        self,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_attempts: int = MAX_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        sdk_client: Any | None = None,
    ) -> None:
        """Build a client.

        Args:
            timeout_s: per-request timeout in seconds, passed to every call.
            max_attempts: calls tried for one logical request before a transient error is raised.
            sleep: the backoff sleeper (a test passes a recorder).
            rng: source of backoff jitter.
            sdk_client: an object with the SDK's `messages.create`; a test passes a fake, so no
                SDK import, no key and no network is needed. In production leave it unset.

        Raises:
            MissingApiKey: if no sdk_client is given and `anthropic_api_key` is not set.
            RuntimeError: if the `anthropic` package is not installed.
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if sdk_client is None:
            key = _settings_key()
            if key is None:
                raise MissingApiKey("anthropic_api_key is not set (config.py)")
            try:
                import anthropic  # the only import of the SDK in assistant/
            except ImportError as exc:
                raise RuntimeError(
                    "the `anthropic` package is not installed; the answer-bank build needs it: "
                    "pip install -r scripts/assistant_eval/requirements.txt"
                ) from exc
            sdk_client = anthropic.Anthropic(api_key=key, max_retries=0, timeout=timeout_s)
        self._sdk = sdk_client
        self._timeout_s = timeout_s
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._rng = rng or random.Random()

    def __repr__(self) -> str:
        return f"AnthropicClient(timeout_s={self._timeout_s}, max_attempts={self._max_attempts})"

    def complete(self, model: str, request: dict[str, Any]) -> Reply:
        """One logical call, retried on transient errors.

        Args:
            model: the model id to ask for; the reply must be served by this model.
            request: keyword arguments for `messages.create`, minus `model` (system, messages,
                max_tokens, output_config).

        Returns:
            The reply, with its cost.

        Raises:
            ServedModelMismatch: the response names another model.
            ModelCallError: a transient error persisted for `max_attempts` calls, or an error that
                is not transient occurred (the original exception is the `__cause__`).
        """
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                response = self._sdk.messages.create(
                    model=model, timeout=self._timeout_s, **request
                )
            except Exception as exc:  # the SDK raises many types; is_retryable classifies them
                status = getattr(exc, "status_code", None)
                if is_retryable(exc) and attempt < self._max_attempts - 1:
                    attempt += 1
                    logger.warning(
                        "model_call_retry",
                        model=model,
                        attempt=attempt,
                        status=status,
                        error=type(exc).__name__,
                    )
                    self._sleep(min(30.0, 2.0**attempt) * self._rng.uniform(0.5, 1.5))
                    continue
                logger.error(
                    "model_call_failed", model=model, status=status, error=type(exc).__name__
                )
                raise ModelCallError(
                    f"model call failed: {type(exc).__name__} (status {status})"
                ) from exc
            latency = time.monotonic() - started
            served = str(getattr(response, "model", ""))
            if not served.startswith(model):
                raise ServedModelMismatch(f"asked for {model}, served by {served!r}")
            text = "".join(
                str(block.text)
                for block in response.content
                if getattr(block, "type", None) == "text"
            )
            usage = {k: int(getattr(response.usage, k, 0) or 0) for k in USAGE_KEYS}
            return Reply(
                text=text,
                usage=usage,
                stop_reason=getattr(response, "stop_reason", None),
                served=served,
                latency=latency,
                cost=usage_cost(model, usage),
            )

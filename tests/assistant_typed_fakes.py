"""A scripted `ModelClient` for the typed-agent tests: no SDK, no key, no network, no money.

`ScriptedClient` answers each call from a list of `Reply` objects (or raises an exception in the list) and
records every request, so a test can read exactly what the agent sent. `text_reply` and `tool_reply` build
replies in the shape `AnthropicClient` returns: `content` holds plain-dict blocks.
"""

from __future__ import annotations

import itertools
from typing import Any

from assistant.client import Reply

_IDS = itertools.count(1)


def text_reply(
    text: str,
    *,
    stop: str = "end_turn",
    cost: float = 0.001,
    latency: float = 0.1,
    model: str = "claude-haiku-5-5",
) -> Reply:
    """A reply that ends the turn with text (or a refusal or cut-off, with `stop`)."""
    usage = {
        "input_tokens": 1000,
        "output_tokens": 200,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    content = ({"type": "text", "text": text},) if text else ()
    return Reply(text, usage, stop, model, latency, cost, content)


def tool_reply(
    *calls: tuple[str, dict[str, Any]], cost: float = 0.001, model: str = "claude-haiku-5-5"
) -> Reply:
    """A reply that asks for one or more tool calls, each given as (tool name, input)."""
    blocks = tuple(
        {"type": "tool_use", "id": f"toolu_{next(_IDS)}", "name": name, "input": tool_input}
        for name, tool_input in calls
    )
    usage = {
        "input_tokens": 1000,
        "output_tokens": 50,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    return Reply("", usage, "tool_use", model, 0.1, cost, blocks)


class ScriptedClient:
    """A `ModelClient` that pops one scripted reply (or raises one scripted exception) per call."""

    def __init__(self, *script: Reply | Exception) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def complete(self, model: str, request: dict[str, Any]) -> Reply:
        self.calls.append((model, request))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

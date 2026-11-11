"""Fake model clients for the assistant tests: no network, no key, no SDK.

`FakeModelClient` answers like a model would, from the same record the writer is shown, so the bank builder
can be run end to end. By default the writer answers with `graders.oracle_text` (which passes every grader) and
the gate says "faithful"; a test replaces either with a function to script a failure.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from assistant import graders
from assistant.client import Reply
from assistant.cost import usage_cost
from assistant.gate import JUDGE_SYSTEM

Key = tuple[str, str, str | None]

FAITHFUL = json.dumps({"faithful": True, "useful": True, "plausible_values": None, "issues": []})
FLAGGED = json.dumps(
    {
        "faithful": False,
        "useful": True,
        "plausible_values": None,
        "issues": ["says the function fits a model it only filters"],
    }
)

_FUNCTION = re.compile(r"<function>(.*?)</function>", re.DOTALL)
_OTHER = re.compile(r"<other_function>(.*?)</other_function>", re.DOTALL)
_RECORD = re.compile(r"<record>(.*?)</record>", re.DOTALL)
_OTHER_RECORD = re.compile(r"<other_record>(.*?)</other_record>", re.DOTALL)
_ACTION = re.compile(r"<action>(\w+)</action>")


def _intent_from_task(content: str) -> str:
    if "'What does this function do?'" in content:
        return "explain"
    if "'When should I use it?'" in content:
        return "when"
    return "compare"


class FakeModelClient:
    """A scriptable `ModelClient`.

    Attributes:
        calls: one (model, role, key, attempt) per call, where role is "write" or "gate" and attempt
            counts the earlier calls of that role for that key and model.
        requests: every request dict received, in order.
    """

    def __init__(
        self,
        cases: list[dict[str, Any]],
        *,
        write: Callable[[Key, int, str, dict[str, Any]], str] | None = None,
        judge: Callable[[Key, int, str, dict[str, Any]], str] | None = None,
        stop_reason: Callable[[Key, int, str], str] = lambda key, attempt, model: "end_turn",
        fail: Callable[[str, str, Key], Exception | None] | None = None,
    ) -> None:
        self._by_key: dict[Key, dict[str, Any]] = {}
        for case in cases:
            other = case["other"]["name"] if case["intent"] == "compare" else None
            self._by_key[(case["record"]["name"], case["intent"], other)] = case
        self._write = write or (lambda key, attempt, model, request: self.oracle(key))
        self._judge = judge or (lambda key, attempt, model, request: FAITHFUL)
        self._stop = stop_reason
        self._fail = fail
        self.calls: list[tuple[str, str, Key, int]] = []
        self.requests: list[dict[str, Any]] = []

    def oracle(self, key: Key) -> str:
        """The text the harness's known-good baseline gives for this question."""
        return graders.oracle_text(self._by_key[key])

    def _key(self, role: str, request: dict[str, Any]) -> Key:
        content = request["messages"][0]["content"]
        if role == "write":
            name = json.loads(_FUNCTION.search(content).group(1))["name"]  # type: ignore[union-attr]
            intent = _intent_from_task(content)
            other_match = _OTHER.search(content)
            other = json.loads(other_match.group(1))["name"] if other_match else None
        else:
            name = json.loads(_RECORD.search(content).group(1))["name"]  # type: ignore[union-attr]
            intent = _ACTION.search(content).group(1)  # type: ignore[union-attr]
            other_match = _OTHER_RECORD.search(content)
            other = json.loads(other_match.group(1))["name"] if other_match else None
        return (name, intent, other)

    def complete(self, model: str, request: dict[str, Any]) -> Reply:
        role = "gate" if request["system"] == JUDGE_SYSTEM else "write"
        key = self._key(role, request)
        attempt = sum(1 for m, r, k, _ in self.calls if (m, r, k) == (model, role, key))
        self.calls.append((model, role, key, attempt))
        self.requests.append(request)
        if self._fail is not None:
            error = self._fail(model, role, key)
            if error is not None:
                raise error
        text = (self._write if role == "write" else self._judge)(key, attempt, model, request)
        usage = {
            "input_tokens": 1200 if role == "write" else 1500,
            "output_tokens": 250 if role == "write" else 120,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
        return Reply(
            text=text,
            usage=usage,
            stop_reason=self._stop(key, attempt, model),
            served=model,
            latency=0.01,
            cost=usage_cost(model, usage),
        )

    def count(self, role: str | None = None, model: str | None = None) -> int:
        """Number of calls, optionally of one role ("write" or "gate") and/or one model."""
        return sum(1 for m, r, _, _ in self.calls if role in (None, r) and model in (None, m))

"""The typed-question agent: the tool loop (plan 7), written against the `ModelClient` seam.

Reasoning:
- Moved out of scripts/assistant_eval/run_typed.py::run_case and rewritten for production: the same loop (the
  question, then up to four tool turns, then a last call with tools switched off so the model must answer in
  words), but on `assistant.client.ModelClient`, so a test drives it with a scripted fake and a gateway uses
  `AnthropicClient`. Nothing here imports the SDK, FastAPI or the network.
- One `TypedAgent` serves one visitor question. It owns that question's `ToolBox` (what the tools returned is the
  evidence the grader checks the answer against) and its running totals: dollars, seconds, tokens and calls.
  `ask` runs the loop; `revise` continues the same conversation with a list of failed checks (the guardrail's
  one retry), so the model keeps the tool results it already fetched.
- Hard limits, so no question can run away: at most MAX_TOOL_TURNS tool turns (REVISE_TOOL_TURNS more in a
  revision), a dollar cap and a wall-clock cap checked before every model call. A hit limit ends the loop with a
  status ("budget", "timeout", "tool_limit") instead of an exception; the guardrail then serves static text.
- The visitor's text is data: it goes only into a user turn, never into the system prompt, and its angle
  brackets are escaped so it cannot close the `<question>` tag the prompt wraps it in or open another one.
  Earlier turns sent by the browser are untrusted too: they are folded into the first user turn as
  `<earlier_turns>` data, never replayed as assistant turns, so a forged "assistant said" cannot steer the model.
  (The harness did not escape; the next measurement run uses this code, so it measures the escaping.)
- Nothing is logged here. The caller logs counts, costs and outcomes, never a question or an answer.
"""

from __future__ import annotations

import html
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from assistant.client import USAGE_KEYS, ModelClient
from assistant.prompts import EFFORT
from assistant.tools import ToolBox
from assistant.typed_prompts import MAX_TOOL_TURNS, build_typed_request, user_content

REVISE_TOOL_TURNS = 2
DEFAULT_MAX_USD = 0.15  # about ten times the measured Opus cost of a typed answer
DEFAULT_MAX_SECONDS = 30.0  # the measured p95 of a whole answer is 7 s (results 9.18)
MAX_HISTORY_TURNS = 3
MAX_TEXT_CHARS = 500

STATUS_OK = "ok"
STATUSES = ("ok", "refusal", "truncated", "tool_limit", "budget", "timeout", "empty")


@dataclass(frozen=True)
class AgentRun:
    """What one pass of the loop produced.

    Attributes:
        text: the model's final text, stripped (may be empty or partial unless status is "ok").
        status: "ok"; "refusal" or "truncated" (the API's stop reason); "tool_limit" (still asking for a tool
            after the tools were switched off); "budget" or "timeout" (a cap was reached before a call);
            "empty" (the model ended its turn with no text).
        messages: the whole conversation so far, for `TypedAgent.revise`.
        tool_turns: tool-using turns in this pass.
        model_calls: model calls in this pass.
        served: the model id that served the last call ("" if none was made).
    """

    text: str
    status: str
    messages: tuple[dict[str, Any], ...]
    tool_turns: int
    model_calls: int
    served: str


def clean_text(text: str) -> str:
    """Visitor text as data: stripped, cut to MAX_TEXT_CHARS, angle brackets and ampersands escaped."""
    return html.escape(text.strip()[:MAX_TEXT_CHARS], quote=False)


def history_block(history: Sequence[tuple[str, str]]) -> str:
    """The last MAX_HISTORY_TURNS (question, answer) pairs as one `<earlier_turns>` data block ('' if none)."""
    turns = [
        f"<earlier_turn><question>{clean_text(q)}</question><answer>{clean_text(a)}</answer></earlier_turn>"
        for q, a in list(history)[-MAX_HISTORY_TURNS:]
    ]
    return "<earlier_turns>\n" + "\n".join(turns) + "\n</earlier_turns>\n" if turns else ""


class TypedAgent:
    """The tool loop for one visitor question."""

    def __init__(
        self,
        client: ModelClient,
        model: str,
        catalogue: list[dict[str, Any]],
        *,
        effort: str = EFFORT,
        max_usd: float = DEFAULT_MAX_USD,
        max_seconds: float = DEFAULT_MAX_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Build the agent for one question.

        Args:
            client: the model client (a scripted fake in tests, `AnthropicClient` in production).
            model: the model id for every call of this question.
            catalogue: the entries of portal/functions.json the tools search and read.
            effort: the `output_config.effort` level (the measured default is low).
            max_usd: dollars this question may spend in all (ask and revise together).
            max_seconds: wall-clock seconds this question may take in all.
            clock: monotonic seconds; a test passes a fake.
        """
        self.client = client
        self.model = model
        self.effort = effort
        self.max_usd = max_usd
        self.max_seconds = max_seconds
        self.toolbox = ToolBox(catalogue)
        self.cost = 0.0
        self.latency_s = 0.0
        self.model_calls = 0
        self.usage = dict.fromkeys(USAGE_KEYS, 0)
        self._clock = clock
        self._started = clock()

    def ask(
        self,
        question: str,
        page_function: str | None = None,
        history: Sequence[tuple[str, str]] = (),
    ) -> AgentRun:
        """Answer one scrubbed question, with the page the visitor is on and up to three earlier turns.

        `page_function` must already be a catalogue name (the caller checks); `question` and `history` are
        visitor text and are escaped here.
        """
        first = history_block(history) + user_content(clean_text(question), page_function)
        return self._loop([{"role": "user", "content": first}], MAX_TOOL_TURNS)

    def revise(self, run: AgentRun, flags: list[str]) -> AgentRun:
        """Continue the conversation with the failed checks, asking for the answer again.

        Only for a run that ended on an assistant answer (status "ok", "refusal", "truncated" or "empty"); a
        run that stopped mid tool call has no answer to correct.
        """
        bullets = "\n".join(f"- {flag}" for flag in flags[:8])
        correction = (
            "That answer failed these checks:\n"
            f"{bullets}\n"
            "Write the answer again, fixing them and keeping every rule above."
        )
        messages = [*run.messages, {"role": "user", "content": correction}]
        return self._loop(messages, REVISE_TOOL_TURNS)

    def _loop(self, messages: list[dict[str, Any]], tool_turns_allowed: int) -> AgentRun:
        status, text, served = STATUS_OK, "", ""
        tool_turns, calls = 0, 0
        for call_number in range(tool_turns_allowed + 1):
            if self.cost >= self.max_usd:
                status = "budget"
                break
            if self._clock() - self._started > self.max_seconds:
                status = "timeout"
                break
            tools_allowed = call_number < tool_turns_allowed
            request = build_typed_request(list(messages), self.effort, tools_allowed=tools_allowed)
            reply = self.client.complete(self.model, request)
            calls += 1
            self.model_calls += 1
            self.cost += reply.cost
            self.latency_s += reply.latency
            served = reply.served
            for key in USAGE_KEYS:
                self.usage[key] += int(reply.usage.get(key, 0))
            blocks = list(reply.content) or [{"type": "text", "text": reply.text}]
            messages.append({"role": "assistant", "content": blocks})
            text = reply.text
            if reply.stop_reason == "refusal":
                status = "refusal"
                break
            if reply.stop_reason == "max_tokens":
                status = "truncated"
                break
            uses = [b for b in blocks if b.get("type") == "tool_use"]
            if reply.stop_reason != "tool_use" or not uses:
                break
            if not tools_allowed:
                status = "tool_limit"
                break
            results = [
                {
                    "type": "tool_result",
                    "tool_use_id": use["id"],
                    "content": self.toolbox.run(use["name"], use["input"]),
                }
                for use in uses
            ]
            messages.append({"role": "user", "content": results})
            tool_turns += 1
        if status == STATUS_OK and not text.strip():
            status = "empty"
        return AgentRun(text.strip(), status, tuple(messages), tool_turns, calls, served)

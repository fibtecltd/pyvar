"""
schemas/assistant.py — request and response contracts for POST /api/v1/assistant/ask.

Reasoning:
- The contract is docs/assistant-plan-implementation.md section 4. The question is 1 to 500 characters after
  trimming; `function` is the catalogue name of the page the visitor is on (the route ignores a name that is
  not in the catalogue); `history` is at most three earlier turns the browser keeps, which the route scrubs
  and treats as data, never as instructions.
- Bad input is a 422, like every other route here (the plan wrote 400; this repo's convention and its tests
  say 422 for a bad body).
- The response never carries the model id, only a tier label, and never a tool result. `source` says whether
  the text is the model's checked answer ("live") or fixed text from the catalogue and the bank ("static").
- `extra="forbid"` so a typo in a field name is an error, not a silently ignored field.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

QUESTION_MAX = 500
ANSWER_MAX = 1500
HISTORY_MAX = 3


class Turn(BaseModel):
    """One earlier question and answer, as the browser kept them."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str = Field(max_length=QUESTION_MAX)
    a: str = Field(max_length=ANSWER_MAX)


class AskRequest(BaseModel):
    """What a visitor typed, the page they are on, and up to three earlier turns."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=QUESTION_MAX)
    function: str | None = Field(default=None, max_length=100)
    history: list[Turn] = Field(default_factory=list, max_length=HISTORY_MAX)


class AskResponse(BaseModel):
    """The guarded answer."""

    answer: str
    source: Literal["live", "static"]
    model_tier: str  # haiku | sonnet | opus | fable | other; never the model id
    functions: list[str]
    suggested_parameters: dict[str, Any] | None = (
        None  # {"function", "values"}: a validated example
    )
    request_id: str

"""Removes keys and tokens from a visitor's question before any model call (used by assistant/guardrails.py).

Reasoning:
- The typed-question design (docs/assistant-plan-implementation.md, section on `assistant/scrub.py`) removes
  secrets before any model call. The eval's category H tests it with no model, and the production path
  (`guardrails.answer_question`) calls the same two functions, so what was measured is what ships.
- Shapes, from the code that issues them: a pyvar API key is "pyvar_" + token_urlsafe(32), that is 43
  characters of [A-Za-z0-9_-]; a session token is a JWT (three dot-separated base64url segments, the first
  starting "eyJ"); an Anthropic key starts "sk-ant-". Long hex runs (a hash or a secret) are removed too.
- Added for the gateway (plan 3): email addresses, and long base64 runs. A visitor's email is personal data
  the model has no use for, so it is removed (with its own marker, because it is not a key). A base64 run is
  removed only when it is 40 or more characters of the base64 and base64url alphabets AND mixes upper case,
  lower case and a digit, which is what random bytes look like and what a function name never does (every
  catalogue name is lower-case snake_case, at most 40 characters), so naming a function is never scrubbed.
- The markers are fixed text, so a scrubbed question is still a readable question.
"""

from __future__ import annotations

import re

MARKER = "[removed: looks like a key or token]"
EMAIL_MARKER = "[removed: email address]"
_B64 = r"[A-Za-z0-9+/_-]"
_PATTERNS = (
    re.compile(r"\bpyvar_[A-Za-z0-9_-]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{3,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\b[0-9a-fA-F]{32,}\b"),
    # a long base64 or base64url run with all three of upper case, lower case and a digit (see the docstring)
    re.compile(
        rf"(?<!{_B64})(?={_B64}*[A-Z])(?={_B64}*[a-z])(?={_B64}*\d){_B64}{{40,}}={{0,2}}(?!{_B64})"
    ),
)
_EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w-])")


def scrub_secrets(text: str) -> tuple[str, int]:
    """Return `text` with every key-like string and email address replaced by a marker, and how many."""
    total = 0
    for pattern in _PATTERNS:
        text, count = pattern.subn(MARKER, text)
        total += count
    text, count = _EMAIL.subn(EMAIL_MARKER, text)
    return text, total + count


def has_secret(text: str) -> bool:
    """True when `text` still contains something that looks like a key or token."""
    return any(pattern.search(text) for pattern in _PATTERNS)

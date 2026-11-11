"""A reference scrub for keys and tokens in a visitor's question (the eval's stand-in for plan 2's gateway).

Reasoning:
- The typed-question design (docs/assistant-plan-implementation.md, section on `assistant/scrub.py`) removes
  secrets before any model call. Plan 1 category H needs that behaviour to be testable now, with no model,
  so the eval carries a small scrub of its own. It is not the production module: plan 2 writes that one and
  must pass the same cases.
- Shapes, from the code that issues them: a pyvar API key is "pyvar_" + token_urlsafe(32), that is 43
  characters of [A-Za-z0-9_-]; a session token is a JWT (three dot-separated base64url segments, the first
  starting "eyJ"); an Anthropic key starts "sk-ant-". Long hex runs (a hash or a secret) are removed too.
- The marker is fixed text, so a scrubbed question is still a readable question.
"""

from __future__ import annotations

import re

MARKER = "[removed: looks like a key or token]"
_PATTERNS = (
    re.compile(r"\bpyvar_[A-Za-z0-9_-]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{3,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\b[0-9a-fA-F]{32,}\b"),
)


def scrub_secrets(text: str) -> tuple[str, int]:
    """Return `text` with every key-like string replaced by a marker, and how many were replaced."""
    total = 0
    for pattern in _PATTERNS:
        text, count = pattern.subn(MARKER, text)
        total += count
    return text, total


def has_secret(text: str) -> bool:
    """True when `text` still contains something that looks like a key or token."""
    return any(pattern.search(text) for pattern in _PATTERNS)

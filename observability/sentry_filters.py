"""
observability/sentry_filters.py — Sentry's `before_send`: the typed assistant's expected refusals are not errors

Reasoning:
- The typed route refuses by raising an HTTPException with status 503 (api/assistant/deps.py::refuse), and Sentry's
  FastAPI integration reports every 5xx HTTPException as an error event, with a "high priority issue" e-mail for each
  new issue. For four of the route's refusals that is noise by design, not a failure: `assistant_disabled` (the flag, or
  the kill switch pulled on purpose), `assistant_budget` (the day's spend cap, working as intended), `assistant_closed`
  (an anonymous or unlisted visitor while the allowlist is on: every press of Ask) and `assistant_busy` (the
  concurrency limit). Left alone, the kill switch or the prod allowlist stage would flood Sentry and its quota.
- `assistant_unavailable` is NOT in the set: it means the store, the key or the model path really failed (the first dev
  run's PYVAR-17 was exactly that), and that one should reach Sentry. The route's own counter
  (`pyvar_assistant_refused_total`) still counts every refusal, expected or not; only the Sentry event is dropped.
- Everything else goes through the address scrubber unchanged (observability/redact.py::scrub_event), so the privacy net
  under "do not send addresses" is the same as before. tests/test_assistant_sentry_filter.py pins the set against the
  codes `refuse()` actually raises, so a new refusal has to be classified.
"""

from __future__ import annotations

from typing import Any

from starlette.exceptions import HTTPException

from observability.redact import scrub_event

EXPECTED_ASSISTANT_REFUSALS = frozenset(
    {"assistant_disabled", "assistant_budget", "assistant_closed", "assistant_busy"}
)


def is_expected_assistant_refusal(hint: dict[str, Any] | None) -> bool:
    """True when the event is the typed route's deliberate 503 for one of the expected refusals."""
    exc_info = (hint or {}).get("exc_info")
    exc = exc_info[1] if isinstance(exc_info, tuple) and len(exc_info) > 1 else None
    if not isinstance(exc, HTTPException) or exc.status_code != 503:
        return False
    detail = exc.detail
    return isinstance(detail, dict) and detail.get("code") in EXPECTED_ASSISTANT_REFUSALS


def before_send(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Sentry `before_send`: drop an expected assistant refusal, else the event scrubbed of addresses (or None)."""
    if is_expected_assistant_refusal(hint):
        return None
    return scrub_event(event, hint)

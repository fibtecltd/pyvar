"""The typed route's expected 503 refusals are not Sentry errors; a real failure of it still is.

Found on 2026-11-27: Sentry PYVAR-17 (a "high priority" e-mail) for the dev run's 503. `refuse()` raises an
HTTPException, and the FastAPI integration reports every 5xx one. The kill switch, the spend cap, the allowlist's
`assistant_closed` (every press of Ask by an anonymous visitor) and the concurrency limit are working as designed;
`assistant_unavailable` is a real failure and must still arrive. observability/sentry_filters.py drops the first four.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from starlette.exceptions import HTTPException

from observability.redact import REDACTED, scrub_event
from observability.sentry_filters import (
    EXPECTED_ASSISTANT_REFUSALS,
    before_send,
    is_expected_assistant_refusal,
)
from tests.test_sentry_privacy import ADDRESS, events_in, recording_client

pytestmark = pytest.mark.filterwarnings("ignore:The send_default_pii option is deprecated")

ROOT = Path(__file__).resolve().parent.parent


def refusal(code: str, status: int = 503) -> HTTPException:
    detail = {"code": code, "message": "m", "hint": "h"}
    return HTTPException(status_code=status, detail=detail)


def hint_of(exc: BaseException) -> dict[str, Any]:
    return {"exc_info": (type(exc), exc, None)}


# ── the decision ───────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("code", sorted(EXPECTED_ASSISTANT_REFUSALS))
def test_an_expected_refusal_is_dropped(code: str) -> None:
    exc = refusal(code)
    assert is_expected_assistant_refusal(hint_of(exc)) is True
    assert before_send({"message": "x"}, hint_of(exc)) is None


def test_assistant_unavailable_is_still_reported() -> None:
    exc = refusal("assistant_unavailable")
    assert is_expected_assistant_refusal(hint_of(exc)) is False
    assert before_send({"message": "x"}, hint_of(exc)) == {"message": "x"}


@pytest.mark.parametrize(
    "exc",
    [
        refusal("assistant_budget", status=500),  # not the route's 503
        HTTPException(status_code=503, detail="assistant_budget"),  # a string, not the route's dict
        HTTPException(status_code=503, detail={"code": "billing_not_configured"}),
        ValueError("assistant_budget"),
        RuntimeError("boom"),
    ],
)
def test_nothing_else_is_dropped(exc: BaseException) -> None:
    assert is_expected_assistant_refusal(hint_of(exc)) is False
    assert before_send({"message": "x"}, hint_of(exc)) == {"message": "x"}


@pytest.mark.parametrize("hint", [None, {}, {"exc_info": None}, {"exc_info": (None, None, None)}])
def test_a_hint_without_an_exception_drops_nothing(hint: dict[str, Any] | None) -> None:
    assert is_expected_assistant_refusal(hint) is False
    assert before_send({"message": "x"}, hint) == {"message": "x"}


def test_what_is_kept_is_still_scrubbed_of_addresses() -> None:
    event = {"message": f"failed for {ADDRESS}", "level": "error"}
    kept = before_send(event, hint_of(RuntimeError("boom")))
    assert kept == scrub_event(event) and ADDRESS not in str(kept) and REDACTED in str(kept)


# ── the set cannot drift from what the route raises ────────────────────────────────────────────────────


def _codes_the_route_refuses_with() -> set[str]:
    codes: set[str] = set()
    for name in ("deps.py", "routes.py"):
        tree = ast.parse((ROOT / "api" / "assistant" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "refuse"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                codes.add(node.args[0].value)
    return codes


def test_every_refusal_the_route_raises_is_classified() -> None:
    """A new refusal code must be put in the expected set or deliberately left reportable, here."""
    raised = _codes_the_route_refuses_with()
    reportable = {"assistant_unavailable"}  # the store, the key or the model path really failed
    assert raised == EXPECTED_ASSISTANT_REFUSALS | reportable, raised ^ (
        EXPECTED_ASSISTANT_REFUSALS | reportable
    )


# ── through the real SDK: the hint really carries the exception, and the options are the production ones ──


def test_the_real_client_drops_an_expected_refusal_and_keeps_a_failure() -> None:
    import sentry_sdk

    with recording_client() as sent:
        for code in sorted(EXPECTED_ASSISTANT_REFUSALS):
            sentry_sdk.capture_exception(refusal(code))
        sentry_sdk.capture_exception(refusal("assistant_unavailable"))
        sentry_sdk.get_global_scope().client.flush(timeout=1)
    reported = events_in(sent)
    assert len(reported) == 1, reported
    value = reported[0]["exception"]["values"][0]["value"]
    assert "assistant_unavailable" in value

"""
api/assistant/routes.py — POST /api/v1/assistant/ask: a typed question, answered under guardrails

Reasoning:
- The plan is docs/assistant-plan-implementation.md section 4; the guarded answer itself is
  assistant/guardrails.py::answer_question (scrub, tool loop, grader, one retry, static fallback). This module is
  only the door: who may ask, how much, and what is never written down.
- The switch is OFF by default (`assistant_typed_enabled`, config.py). Until it is on, and until the privacy and
  terms pages name the model provider (plan 4.6), the route answers 503 `assistant_disabled` and calls nothing.
- Anyone may ask, signed in or not (the portal's box works for a visitor). A bearer credential, if sent, is
  validated like on every other route and picks the tier: the quota and the model. Dependency order, fixed
  below: available (switches, kill switch, spend cap) -> model client (a missing key) -> concurrency slot ->
  per-caller quota -> the handler. A refusal at any step costs the visitor no quota and costs no model call.
- `answer_question` is synchronous (the SDK client blocks), so it runs in a worker thread; the slot count bounds
  how many threads one API task spends on it.
- A question is never logged, stored or put in a metric. The structured line `assistant_ask` carries the
  request id, the caller's tier and auth kind, the outcome, the source, dollars and seconds; guardrails.py adds
  its own counts line. The usage middleware writes one api_usage row (domain "assistant"), as for every
  /api/v1 path: path, tier, status, duration, no text.
- After the answer, its dollar cost is added to the day's spend (api/assistant/store.py) so the circuit breaker
  can open; a failure to record is counted and logged, never shown to the visitor.
- An unexpected exception (a bug, not a model failure, which `answer_question` turns into static text) is
  logged with its stack and answered with the same 503 `assistant_unavailable`, so the page shows the static
  hint instead of a bare 500.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
import uuid

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends

from api.assistant import metrics
from api.assistant.deps import (
    get_audit_runner,
    get_catalogue,
    get_model_client,
    get_watchdog,
    limit_concurrency,
    model_for,
    refuse,
    require_available,
    tier_label,
)
from api.assistant.store import AssistantStore, get_store
from api.assistant.watchdog import AuditRunner, Watchdog, audit_after
from api.assistant_bank import BANK_DIR
from api.middleware.auth import TokenPayload, get_optional_user
from api.middleware.rate_limit import assistant_tier, enforce_assistant_rate_limit
from assistant.client import ModelClient
from assistant.guardrails import (
    LIVE,
    OUTCOME_DEGRADED,
    OUTCOME_PINNED,
    Answer,
    answer_question,
    static_answer,
)
from config import get_settings
from schemas.assistant import AskRequest, AskResponse

cfg = get_settings()
logger = structlog.get_logger()

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask the assistant a question about pyvar's functions",
    dependencies=[
        Depends(require_available),
        Depends(
            get_model_client
        ),  # resolved here so a missing key is refused before the quota is used
        Depends(limit_concurrency),
        Depends(enforce_assistant_rate_limit),
    ],
)
async def ask(
    body: AskRequest,
    background: BackgroundTasks,
    user: TokenPayload | None = Depends(get_optional_user),
    client: ModelClient = Depends(get_model_client),
    store: AssistantStore = Depends(get_store),
    watchdog: Watchdog | None = Depends(get_watchdog),
    runner: AuditRunner = Depends(get_audit_runner),
) -> AskResponse:
    """Answer a question about pyvar's functions, from the catalogue, in English.

    The answer is either the model's text after it passed the checks (`source: "live"`) or fixed text from the
    catalogue and the answer bank (`source: "static"`). The model's id is never returned, only its family.
    """
    request_id = uuid.uuid4().hex
    tier = assistant_tier(user)
    started = time.monotonic()
    model = model_for(tier)
    writer = tier_label(model)
    catalogue = get_catalogue()
    answer: Answer | None = None
    probe = False
    if watchdog is not None:  # a pinned function or a degraded writer never reaches the model
        standing = await watchdog.standing(body.function, writer)
        if standing.pinned:
            answer = static_answer(
                body.question,
                catalogue=catalogue,
                page_function=standing.pinned[0],
                bank_dir=BANK_DIR,
                outcome=OUTCOME_PINNED,
            )
            metrics.PINNED_SERVED.labels(when="pre").inc()
        elif standing.degraded:
            if watchdog.probe_traffic():
                probe = True  # answered live and audited at 100%: how a degraded writer earns its way back
                metrics.DEGRADED_SERVED.labels(writer=writer, kind="probe").inc()
            else:
                answer = static_answer(
                    body.question,
                    catalogue=catalogue,
                    page_function=body.function,
                    bank_dir=BANK_DIR,
                    outcome=OUTCOME_DEGRADED,
                    with_suggestions=True,
                )
                metrics.DEGRADED_SERVED.labels(writer=writer, kind="static").inc()
    if answer is None:
        try:
            answer = await asyncio.to_thread(
                answer_question,
                client,
                model,
                body.question,
                catalogue=catalogue,
                page_function=body.function,
                history=[(turn.q, turn.a) for turn in body.history],
                bank_dir=BANK_DIR,
                max_usd=cfg.assistant_max_usd_per_question,
                max_seconds=cfg.assistant_max_seconds_per_question,
            )
        except (
            Exception
        ) as exc:  # noqa: BLE001 — a bug must end as the static hint, with its stack logged
            metrics.UNEXPECTED_ERRORS.inc()
            logger.error(
                "assistant_ask_failed",
                request_id=request_id,
                tier=tier,
                error=type(exc).__name__,
                exc_info=True,
            )
            refuse("assistant_unavailable", "The assistant ran into a problem.", tier=tier)
        if watchdog is not None and answer.source == LIVE:
            pinned = await watchdog.pinned_among(answer.functions)
            # the answer cites a function that is pinned: serve its fixed text, but keep the bill
            if pinned:
                fixed = static_answer(
                    body.question,
                    catalogue=catalogue,
                    page_function=pinned[0],
                    bank_dir=BANK_DIR,
                    outcome=OUTCOME_PINNED,
                )
                answer = dataclasses.replace(
                    fixed,
                    tries=answer.tries,
                    model_calls=answer.model_calls,
                    tool_turns=answer.tool_turns,
                    cost=answer.cost,
                    latency_s=answer.latency_s,
                    served=answer.served,
                    usage=answer.usage,
                )
                metrics.PINNED_SERVED.labels(when="post").inc()

    seconds = time.monotonic() - started
    model_tier = tier_label(answer.served)
    metrics.ANSWERS.labels(
        source=answer.source, outcome=answer.outcome, tier=tier, model_tier=model_tier
    ).inc()
    metrics.ANSWER_SECONDS.observe(seconds)
    if answer.cost > 0:
        metrics.COST_USD.labels(model_tier=model_tier).inc(answer.cost)
        await store.add_spend(answer.cost)
    if watchdog is not None and answer.source == LIVE and tier != "enterprise":
        # decided and run after the response has gone: the question and the answer stay in memory until then
        background.add_task(
            audit_after,
            watchdog=watchdog,
            runner=runner,
            add_spend=store.add_spend,
            client=client,
            model=cfg.assistant_gate_model,
            question=body.question,
            page_function=body.function,
            answer_text=answer.text,
            evidence=answer.evidence,
            attached=answer.suggested_parameters,
            writer=writer,
            writer_probe=probe,
            by_name={e["name"]: e for e in catalogue},
        )
    logger.info(
        "assistant_ask",
        request_id=request_id,
        tier=tier,
        auth=user.auth_method if user else "none",
        source=answer.source,
        outcome=answer.outcome,
        model_tier=model_tier,
        cost_usd=answer.cost,
        seconds=round(seconds, 3),
        functions=len(answer.functions),
    )
    return AskResponse(
        answer=answer.text,
        source=answer.source,  # type: ignore[arg-type]  # "live" | "static", from assistant/guardrails.py
        model_tier=model_tier,
        functions=list(answer.functions),
        suggested_parameters=answer.suggested_parameters,
        request_id=request_id,
    )

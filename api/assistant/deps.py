"""
api/assistant/deps.py — what POST /api/v1/assistant/ask checks before it spends anything

Reasoning:
- Everything here is a FastAPI dependency, so a test replaces the model client, the store or the catalogue with
  `app.dependency_overrides` and the production path is otherwise the one that runs.
- Order matters and is fixed in routes.py: `require_available` (the switches, then the spend cap),
  `get_model_client` (a missing key) and `limit_concurrency` run BEFORE the per-caller quota, so a question
  refused because the service is off, over budget, not set up or busy does not use up the visitor's quota.
- Refusals are 503 with a JSON `detail` of {code, message, hint}. The hint is static text that is true whether or
  not the model is reachable: the menu buttons need no model, and the catalogue is on the home page. Codes:
  `assistant_disabled` (flags or kill switch), `assistant_budget` (the day's spend cap; Retry-After is the time
  to 00:00 UTC), `assistant_unavailable` (the spend store or the model key cannot be reached), `assistant_busy`
  (this API task is already answering `assistant_max_concurrent` questions).
- The model client is built on first use and kept: the SDK client is thread-safe, and building it reads the
  key, which a deployment without one must not fail at start-up. A missing key or SDK is `assistant_unavailable`.
- The catalogue is read once per process (portal/functions.json does not change while the app runs).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any, NoReturn

import structlog
from fastapi import Depends, HTTPException, status

from api.assistant import metrics
from api.assistant.store import (
    AssistantStore,
    StoreUnavailable,
    get_store,
    seconds_until_utc_midnight,
)
from api.assistant.watchdog import AuditRunner, Watchdog, WatchdogConfig
from api.assistant_bank import BANK_DIR
from assistant import bank, tools
from assistant.client import AnthropicClient, ModelCallError, ModelClient
from assistant.watchdog import Rules
from config import get_settings

cfg = get_settings()
logger = structlog.get_logger()

HINT = "The buttons on each function page still work, and every function is listed on the home page (/)."
MODEL_TIERS = ("haiku", "sonnet", "opus", "fable")

_client: ModelClient | None = None
_catalogue: list[dict[str, Any]] | None = None
_inflight = 0
_runner: AuditRunner | None = None


def refuse(
    code: str, message: str, *, retry_after: int | None = None, tier: str = "n/a"
) -> NoReturn:
    """Raise the 503 for `code` with the static hint, and count it (`tier` is "n/a" before the caller is known)."""
    metrics.REFUSED.labels(reason=code.removeprefix("assistant_"), tier=tier).inc()
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": code, "message": message, "hint": HINT},
        headers=headers,
    )


def model_for(tier: str) -> str:
    """The configured model id for a caller tier ("anon" uses the free tier's)."""
    return {
        "enterprise": cfg.assistant_model_enterprise,
        "pro": cfg.assistant_model_pro,
    }.get(tier, cfg.assistant_model_free)


def tier_label(served: str) -> str:
    """The model family of a served model id, never the id itself: haiku, sonnet, opus, fable, other, or
    none (no model was called)."""
    if not served:
        return "none"
    lower = served.lower()
    return next((family for family in MODEL_TIERS if family in lower), "other")


def get_catalogue() -> list[dict[str, Any]]:
    """The catalogue entries (portal/functions.json), read once. Callers must not modify them."""
    global _catalogue
    if _catalogue is None:
        _catalogue = tools.load_catalogue()
    return _catalogue


def get_model_client() -> ModelClient:
    """The Anthropic client, built on first use.

    Raises:
        HTTPException: 503 `assistant_unavailable` if the key or the SDK is missing.
    """
    global _client
    if _client is None:
        try:
            _client = AnthropicClient()
        except (ModelCallError, RuntimeError) as exc:
            logger.error("assistant_client_unavailable", error=type(exc).__name__)
            refuse("assistant_unavailable", "The assistant is not set up on this server.")
    return _client


async def require_available(store: AssistantStore = Depends(get_store)) -> None:
    """503 unless both switches are on, the kill switch is clear and today's spend is under the cap."""
    if not (cfg.assistant_enabled and cfg.assistant_typed_enabled):
        refuse("assistant_disabled", "Typed questions are not switched on.")
    now = dt.datetime.now(dt.timezone.utc)
    try:
        gate = await store.gate(now)
    except StoreUnavailable:
        logger.warning("assistant_store_unavailable")
        refuse("assistant_unavailable", "The assistant cannot check its spending limit right now.")
    if gate.killed:
        refuse("assistant_disabled", "The assistant has been switched off.")
    budget = cfg.assistant_daily_budget_usd
    metrics.BUDGET_USED_RATIO.set(gate.spent_usd / budget if budget > 0 else 1.0)
    if gate.spent_usd >= budget:
        refuse(
            "assistant_budget",
            "The assistant has reached its limit for today and will be back after midnight UTC.",
            retry_after=seconds_until_utc_midnight(now),
        )


async def limit_concurrency() -> AsyncIterator[None]:
    """Hold one of `assistant_max_concurrent` slots for the life of the request, or 503 `assistant_busy`."""
    global _inflight
    if _inflight >= cfg.assistant_max_concurrent:
        refuse("assistant_busy", "The assistant is busy answering other questions.", retry_after=5)
    _inflight += 1
    metrics.INFLIGHT.set(_inflight)
    try:
        yield
    finally:
        _inflight -= 1
        metrics.INFLIGHT.set(_inflight)


def bank_namespace() -> str:
    """The committed bank's version, which namespaces every function's watchdog state ("none" without one).

    A catalogue release builds a new bank with a new version, so every function's window and pin start afresh
    instead of the long tail being pinned together (plan section 13).
    """
    manifest = bank.read_manifest(BANK_DIR) or {}
    version = str(manifest.get("bank_version", ""))
    return version if version and set(version) <= bank.SAFE_VERSION_CHARS else "none"


def watchdog_config() -> WatchdogConfig:
    """The watchdog's numbers from the settings."""
    return WatchdogConfig(
        budget_usd=cfg.assistant_audit_budget_usd_day,
        coverage_share=cfg.assistant_audit_coverage_share,
        verdict_usd=cfg.assistant_audit_verdict_usd,
        probe_share=cfg.assistant_degrade_probe_share,
        rules=Rules(
            allowance=cfg.assistant_cusum_allowance,
            threshold=cfg.assistant_cusum_threshold,
            pin_days=cfg.assistant_pin_days,
            pin_days_max=cfg.assistant_pin_days * 4,
        ),
    )


def get_watchdog(store: AssistantStore = Depends(get_store)) -> Watchdog | None:
    """The watchdog for this request, or None while `assistant_watchdog_enabled` is off.

    Built per request because it holds nothing but the Redis handle and the numbers; a test overrides it.
    """
    if not cfg.assistant_watchdog_enabled:
        return None
    return Watchdog(store.client, watchdog_config(), bank_namespace())


def get_audit_runner() -> AuditRunner:
    """The process-wide audit runner (it counts the audits running on this API task)."""
    global _runner
    if _runner is None:
        _runner = AuditRunner(cfg.assistant_audit_max_concurrent)
    return _runner
